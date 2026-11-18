from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query, status
from prometheus_client import Counter
from service_kit import ApiError, BaseSettings, Database, build_app
from sqlalchemy import func, select, update

from .deps import require_internal_token
from .models import Product
from .schemas import ProductCreate, ProductList, ProductOut, ProductUpdateStock

DEFAULT_DB = "postgresql+asyncpg://platform:platform@localhost:5432/products"


@dataclass
class Settings(BaseSettings):
    service_name: str = "product-service"


settings = Settings(service_name="product-service", database_url=os.getenv("DATABASE_URL", DEFAULT_DB))
db = Database(settings.database_url)
STOCK_RESERVED = Counter("product_stock_reserved_total", "Units reserved")
STOCK_RELEASED = Counter("product_stock_released_total", "Units released after failed orders")


async def _startup() -> None:
    await db.init_models(retries=settings.db_max_retries, delay=2.0)


async def _shutdown() -> None:
    await db.dispose()


async def _ready() -> bool:
    return await db.ping()


app = build_app(
    settings,
    title="Product Service",
    description="Catalog and inventory service with atomic stock reservations.",
    startup=_startup,
    shutdown=_shutdown,
    ready_check=_ready,
)

router = APIRouter(
    prefix="/products", tags=["products"], dependencies=[Depends(require_internal_token)]
)


@router.get("", response_model=ProductList)
async def list_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=160),
    active_only: bool = Query(True),
) -> ProductList:
    async with db.session() as session:
        filters = []
        if active_only:
            filters.append(Product.active.is_(True))
        if q:
            filters.append(func.lower(Product.name).like(f"%{q.lower()}%"))
        total = (
            await session.execute(select(func.count()).select_from(Product).where(*filters))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(Product)
                    .where(*filters)
                    .order_by(Product.name)
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return ProductList(
            items=[ProductOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate) -> ProductOut:
    async with db.session() as session:
        if await session.scalar(select(Product).where(Product.sku == payload.sku.upper())):
            raise ApiError(409, "sku_exists", "A product with this SKU already exists")
        product = Product(
            sku=payload.sku.upper(),
            name=payload.name,
            description=payload.description,
            price_cents=payload.price_cents,
            currency=payload.currency.upper(),
            stock=payload.stock,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return ProductOut.model_validate(product)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: str) -> ProductOut:
    async with db.session() as session:
        product = await session.get(Product, product_id)
        if product is None:
            raise ApiError(404, "product_not_found", f"Product {product_id} does not exist")
        return ProductOut.model_validate(product)


@router.patch("/{product_id}/stock", response_model=ProductOut)
async def update_stock(product_id: str, payload: ProductUpdateStock) -> ProductOut:
    """Atomically adjust stock. Reservations never drive inventory negative."""
    async with db.session() as session:
        product = await session.get(Product, product_id)
        if product is None:
            raise ApiError(404, "product_not_found", f"Product {product_id} does not exist")
        if payload.delta == 0:
            return ProductOut.model_validate(product)

        sku, available = product.sku, product.stock
        if payload.delta < 0:
            result = await session.execute(
                update(Product)
                .where(Product.id == product_id, Product.stock >= -payload.delta)
                .values(stock=Product.stock + payload.delta)
            )
            if result.rowcount == 0:
                await session.rollback()
                raise ApiError(
                    409,
                    "insufficient_stock",
                    f"Only {available} units available for {sku}",
                    {"available": available, "requested": -payload.delta},
                )
            STOCK_RESERVED.inc(-payload.delta)
        else:
            await session.execute(
                update(Product).where(Product.id == product_id).values(stock=Product.stock + payload.delta)
            )
            STOCK_RELEASED.inc(payload.delta)
        await session.commit()
        refreshed = await session.get(Product, product_id)
        return ProductOut.model_validate(refreshed)


app.include_router(router)
