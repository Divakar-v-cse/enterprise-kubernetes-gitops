from __future__ import annotations

import os
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Header, Query, Request, status
from prometheus_client import Counter
from sqlalchemy import func, select

from service_kit import (
    ApiError,
    BaseSettings,
    CircuitOpenError,
    Database,
    UpstreamError,
    build_app,
    get_logger,
)

from .clients import build_clients
from .deps import require_internal_token
from .models import Order, OrderItem
from .schemas import OrderCreate, OrderList, OrderOut

logger = get_logger("order.workflow")
DEFAULT_DB = "postgresql+asyncpg://platform:platform@localhost:5432/orders"

ORDERS_CREATED = Counter("orders_created_total", "Orders created", ["status"])
ORDER_FAILURES = Counter("orders_failed_total", "Orders rejected", ["reason"])
STOCK_COMPENSATIONS = Counter("order_stock_compensations_total", "Stock reservations compensated")


@dataclass
class Settings(BaseSettings):
    service_name: str = "order-service"
    notification_required: bool = field(
        default_factory=lambda: os.getenv("NOTIFICATION_REQUIRED", "false").lower() == "true"
    )


settings = Settings(service_name="order-service", database_url=os.getenv("DATABASE_URL", DEFAULT_DB))
db = Database(settings.database_url)
clients = build_clients(settings.request_timeout_seconds, settings.internal_token)


async def _startup() -> None:
    await db.init_models(retries=settings.db_max_retries, delay=2.0)
    for client in clients.values():
        await client.start()


async def _shutdown() -> None:
    for client in clients.values():
        await client.close()
    await db.dispose()


async def _ready() -> bool:
    return await db.ping()


app = build_app(
    settings,
    title="Order Service",
    description="Order orchestration with saga-style stock reservation and compensation.",
    startup=_startup,
    shutdown=_shutdown,
    ready_check=_ready,
)

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(require_internal_token)])


def _upstream_down(exc: Exception, target: str) -> ApiError:
    logger.warning("upstream_unavailable", extra={"target": target, "error": str(exc)[:300]})
    return ApiError(
        503,
        "dependency_unavailable",
        f"Dependency '{target}' is unavailable, please retry",
        {"target": target, "retryable": True},
    )


@router.get("", response_model=OrderList)
async def list_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status", max_length=32),
    user_id: str | None = Query(None, max_length=64),
) -> OrderList:
    async with db.session() as session:
        filters = []
        if status_filter:
            filters.append(Order.status == status_filter)
        if user_id:
            filters.append(Order.user_id == user_id)
        total = (
            await session.execute(select(func.count()).select_from(Order).where(*filters))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(Order)
                    .where(*filters)
                    .order_by(Order.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return OrderList(
            items=[OrderOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: str) -> OrderOut:
    async with db.session() as session:
        order = await session.get(Order, order_id)
        if order is None:
            raise ApiError(404, "order_not_found", f"Order {order_id} does not exist")
        return OrderOut.model_validate(order)


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=80),
) -> OrderOut:
    if idempotency_key:
        async with db.session() as session:
            existing = await session.scalar(
                select(Order).where(Order.idempotency_key == idempotency_key)
            )
            if existing is not None:
                logger.info("idempotent_replay", extra={"order_id": existing.id})
                return OrderOut.model_validate(existing)

    # 1. Validate the customer through user-service.
    try:
        user = await clients["users"].get_json(f"/users/{payload.user_id}")
    except UpstreamError as exc:
        if exc.status_code == 404:
            ORDER_FAILURES.labels("unknown_user").inc()
            raise ApiError(422, "unknown_user", "Referenced user does not exist") from exc
        raise _upstream_down(exc, "user-service") from exc
    except CircuitOpenError as exc:
        raise _upstream_down(exc, "user-service") from exc

    # 2. Price the basket and reserve stock, compensating on any failure (saga).
    reserved: list[tuple[str, int]] = []
    line_items: list[OrderItem] = []
    total_cents = 0
    currency = payload.currency.upper()

    try:
        for item in payload.items:
            try:
                product = await clients["products"].get_json(f"/products/{item.product_id}")
            except UpstreamError as exc:
                if exc.status_code == 404:
                    ORDER_FAILURES.labels("unknown_product").inc()
                    raise ApiError(
                        422, "unknown_product", f"Product {item.product_id} does not exist"
                    ) from exc
                raise _upstream_down(exc, "product-service") from exc

            if not product.get("active", True):
                raise ApiError(409, "product_inactive", f"Product {product['sku']} is not for sale")

            try:
                reserve = await clients["products"].request(
                    "PATCH",
                    f"/products/{item.product_id}/stock",
                    json={"delta": -item.quantity},
                )
            except (UpstreamError, CircuitOpenError) as exc:
                raise _upstream_down(exc, "product-service") from exc

            if reserve.status_code == 409:
                ORDER_FAILURES.labels("insufficient_stock").inc()
                raise ApiError(
                    409,
                    "insufficient_stock",
                    f"Product {product['sku']} does not have enough stock",
                )
            if reserve.status_code >= 400:
                raise _upstream_down(
                    UpstreamError("product-service", reserve.text[:120], reserve.status_code),
                    "product-service",
                )

            reserved.append((item.product_id, item.quantity))
            currency = product.get("currency", currency)
            total_cents += product["price_cents"] * item.quantity
            line_items.append(
                OrderItem(
                    product_id=product["id"],
                    sku=product["sku"],
                    name=product["name"],
                    quantity=item.quantity,
                    unit_price_cents=product["price_cents"],
                )
            )
    except Exception:
        for product_id, quantity in reserved:
            try:
                await clients["products"].request(
                    "PATCH", f"/products/{product_id}/stock", json={"delta": quantity}
                )
                STOCK_COMPENSATIONS.inc()
            except Exception as compensate_error:  # pragma: no cover - requires outage
                logger.error(
                    "compensation_failed",
                    extra={"product_id": product_id, "quantity": quantity,
                           "error": str(compensate_error)[:200]},
                )
        raise

    # 3. Persist the order; notification failure must not lose the order.
    order = Order(
        user_id=user["id"],
        status="confirmed",
        total_cents=total_cents,
        currency=currency,
        idempotency_key=idempotency_key,
        items=line_items,
    )
    async with db.session() as session:
        session.add(order)
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            if idempotency_key:
                existing = await session.scalar(
                    select(Order).where(Order.idempotency_key == idempotency_key)
                )
                if existing is not None:
                    return OrderOut.model_validate(existing)
            raise ApiError(500, "order_persist_failed", "Could not persist the order") from exc
        await session.refresh(order)

    # 4. Notify asynchronously-by-contract: a hard failure is recorded, not hidden.
    try:
        await clients["notifications"].post_json(
            "/notifications",
            {
                "order_id": order.id,
                "user_id": user["id"],
                "recipient": user["email"],
                "channel": "email",
                "subject": f"Order {order.id[:8]} confirmed",
                "message": f"Your order of {len(line_items)} item(s) totalling "
                           f"{total_cents / 100:.2f} {currency} is confirmed.",
            },
        )
    except (UpstreamError, CircuitOpenError) as exc:
        logger.warning("notification_failed", extra={"order_id": order.id, "error": str(exc)[:200]})
        if settings.notification_required:
            async with db.session() as session:
                stored = await session.get(Order, order.id)
                if stored is not None:
                    stored.status = "notification_failed"
                    await session.commit()
            ORDER_FAILURES.labels("notification_failed").inc()
            raise ApiError(502, "notification_failed", "Order stored but notification failed") from exc
        order.status = "notification_pending"

    ORDERS_CREATED.labels(order.status).inc()
    request.app.state.last_order_id = order.id
    logger.info("order_created", extra={"order_id": order.id, "total_cents": total_cents})
    return OrderOut.model_validate(order)


app.include_router(router)
