from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from prometheus_client import Counter
from sqlalchemy import func, select

from service_kit import ApiError, BaseSettings, Database, build_app, get_logger

from .deps import require_internal_token
from .models import Notification
from .schemas import NotificationCreate, NotificationList, NotificationOut

logger = get_logger("notification.dispatcher")
DEFAULT_DB = "postgresql+asyncpg://platform:platform@localhost:5432/notifications"

SENT = Counter("notifications_sent_total", "Notifications dispatched", ["channel", "status"])


@dataclass
class Settings(BaseSettings):
    service_name: str = "notification-service"
    failure_rate: float = field(
        default_factory=lambda: float(os.getenv("NOTIFICATION_FAILURE_RATE", "0"))
    )


settings = Settings(
    service_name="notification-service", database_url=os.getenv("DATABASE_URL", DEFAULT_DB)
)
db = Database(settings.database_url)


async def _startup() -> None:
    await db.init_models(retries=settings.db_max_retries, delay=2.0)


async def _shutdown() -> None:
    await db.dispose()


async def _ready() -> bool:
    return await db.ping()


app = build_app(
    settings,
    title="Notification Service",
    description="Outbound notification dispatch with retryable delivery records.",
    startup=_startup,
    shutdown=_shutdown,
    ready_check=_ready,
)

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_internal_token)],
)


def _dispatch(notification: Notification) -> str:
    """Simulated provider call.

    NOTIFICATION_FAILURE_RATE allows deterministic failure drills in the demo;
    it defaults to 0 so normal operation always succeeds.
    """
    if settings.failure_rate > 0 and random.random() < settings.failure_rate:
        return "failed"
    logger.info(
        "notification_dispatched",
        extra={
            "notification_id": notification.id,
            "order_id": notification.order_id,
            "channel": notification.channel,
            "recipient": notification.recipient,
        },
    )
    return "sent"


@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
async def create_notification(payload: NotificationCreate) -> NotificationOut:
    async with db.session() as session:
        duplicate = await session.scalar(
            select(Notification).where(
                Notification.order_id == payload.order_id,
                Notification.subject == payload.subject,
            )
        )
        if duplicate is not None:
            return NotificationOut.model_validate(duplicate)

        notification = Notification(
            order_id=payload.order_id,
            user_id=payload.user_id,
            recipient=payload.recipient,
            channel=payload.channel,
            subject=payload.subject,
            message=payload.message,
            status="queued",
            attempts=1,
        )
        notification.status = _dispatch(notification)
        if notification.status == "sent":
            notification.sent_at = datetime.now(UTC)
        session.add(notification)
        await session.commit()
        await session.refresh(notification)
        SENT.labels(notification.channel, notification.status).inc()
        return NotificationOut.model_validate(notification)


@router.get("", response_model=NotificationList)
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    order_id: str | None = Query(None, max_length=36),
    status_filter: str | None = Query(None, alias="status", max_length=20),
) -> NotificationList:
    async with db.session() as session:
        filters = []
        if order_id:
            filters.append(Notification.order_id == order_id)
        if status_filter:
            filters.append(Notification.status == status_filter)
        total = (
            await session.execute(select(func.count()).select_from(Notification).where(*filters))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    select(Notification)
                    .where(*filters)
                    .order_by(Notification.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return NotificationList(
            items=[NotificationOut.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )


@router.post("/{notification_id}/retry", response_model=NotificationOut)
async def retry_notification(notification_id: str) -> NotificationOut:
    async with db.session() as session:
        notification = await session.get(Notification, notification_id)
        if notification is None:
            raise ApiError(404, "notification_not_found", "Notification does not exist")
        if notification.status == "sent":
            return NotificationOut.model_validate(notification)
        notification.attempts += 1
        notification.status = _dispatch(notification)
        if notification.status == "sent":
            notification.sent_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(notification)
        SENT.labels(notification.channel, notification.status).inc()
        return NotificationOut.model_validate(notification)


app.include_router(router)
