from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Tier = Literal["standard", "premium", "internal"]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    tier: Tier = "standard"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    tier: Tier
    created_at: datetime


class UserList(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int
