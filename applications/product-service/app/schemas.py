from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    sku: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9\-_]+$")
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=500)
    price_cents: int = Field(ge=1, le=100_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    stock: int = Field(default=0, ge=0, le=1_000_000)


class ProductUpdateStock(BaseModel):
    delta: int = Field(ge=-10_000, le=10_000, description="Negative reserves, positive restocks")


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sku: str
    name: str
    description: str
    price_cents: int
    currency: str
    stock: int
    active: bool
    updated_at: datetime


class ProductList(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int
