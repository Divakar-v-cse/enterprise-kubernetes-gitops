from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query, Request, status
from prometheus_client import Counter
from service_kit import ApiError, BaseSettings, Database, build_app
from sqlalchemy import func, select

from .deps import require_internal_token
from .models import User
from .schemas import UserCreate, UserList, UserOut

DEFAULT_DB = "postgresql+asyncpg://platform:platform@localhost:5432/users"


@dataclass
class Settings(BaseSettings):
    service_name: str = "user-service"
    port: int = int(os.getenv("PORT", "8001"))


settings = Settings(service_name="user-service", database_url=os.getenv("DATABASE_URL", DEFAULT_DB))
db = Database(settings.database_url)
USERS_CREATED = Counter("users_created_total", "Users created via the API")


async def _startup() -> None:
    await db.init_models(retries=settings.db_max_retries, delay=2.0)


async def _shutdown() -> None:
    await db.dispose()


async def _ready() -> bool:
    return await db.ping()


app = build_app(
    settings,
    title="User Service",
    description="Customer identity and profile store for the platform.",
    startup=_startup,
    shutdown=_shutdown,
    ready_check=_ready,
)

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_internal_token)])


@router.get("", response_model=UserList)
async def list_users(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=120),
) -> UserList:
    async with db.session() as session:
        stmt = select(User)
        count_stmt = select(func.count()).select_from(User)
        if q:
            pattern = f"%{q.lower()}%"
            stmt = stmt.where(func.lower(User.email).like(pattern) | func.lower(User.full_name).like(pattern))
            count_stmt = count_stmt.where(
                func.lower(User.email).like(pattern) | func.lower(User.full_name).like(pattern)
            )
        total = (await session.execute(count_stmt)).scalar_one()
        rows = (
            (await session.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)))
            .scalars()
            .all()
        )
        return UserList(
            items=[UserOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, request: Request) -> UserOut:
    async with db.session() as session:
        existing = await session.scalar(select(User).where(User.email == payload.email.lower()))
        if existing is not None:
            raise ApiError(409, "email_exists", "A user with this email already exists")
        user = User(email=payload.email.lower(), full_name=payload.full_name, tier=payload.tier)
        session.add(user)
        try:
            await session.commit()
        except Exception as exc:  # unique constraint race
            await session.rollback()
            raise ApiError(409, "email_exists", "A user with this email already exists") from exc
        await session.refresh(user)
        USERS_CREATED.inc()
        request.app.state.last_user_id = user.id
        return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str) -> UserOut:
    async with db.session() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise ApiError(404, "user_not_found", f"User {user_id} does not exist")
        return UserOut.model_validate(user)


app.include_router(router)
