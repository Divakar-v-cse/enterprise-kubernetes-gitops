from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NotificationCreate(BaseModel):
    order_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    recipient: str = Field(min_length=3, max_length=255)
    channel: Literal["email", "sms", "webhook"] = "email"
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    user_id: str
    recipient: str
    channel: str
    subject: str
    message: str
    status: str
    attempts: int
    created_at: datetime
    sent_at: datetime | None


class NotificationList(BaseModel):
    items: list[NotificationOut]
    total: int
    limit: int
    offset: int
