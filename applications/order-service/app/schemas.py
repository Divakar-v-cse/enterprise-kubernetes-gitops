from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderItemIn(BaseModel):
    product_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=50)


class OrderCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    items: list[OrderItemIn] = Field(min_length=1, max_length=20)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    sku: str
    name: str
    quantity: int
    unit_price_cents: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    status: str
    total_cents: int
    currency: str
    created_at: datetime
    items: list[OrderItemOut]


class OrderList(BaseModel):
    items: list[OrderOut]
    total: int
    limit: int
    offset: int
