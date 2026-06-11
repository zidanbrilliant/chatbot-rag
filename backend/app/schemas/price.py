from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ProductPriceOut(BaseModel):
    id: str
    price: Decimal
    currency: str
    price_date: date
    supplier: str | None = None
    source: str | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: str
    sku: str | None = None
    name: str
    category: str | None = None
    unit: str | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    latest_price: ProductPriceOut | None = None

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    sku: str | None = None
    name: str = Field(..., min_length=1, max_length=500)
    category: str | None = None
    unit: str | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    source: str = "manual"


class ProductPriceCreate(BaseModel):
    product_id: str
    price: Decimal = Field(..., ge=0)
    currency: str = "IDR"
    price_date: date
    supplier: str | None = None
    source: str = "manual"
    notes: str | None = None


class PriceLookupResult(BaseModel):
    """Unified price result from any source (postgres, csv, xlsx, web)."""

    product_name: str
    price: Decimal
    currency: str
    unit: str | None = None
    source: str  # "postgres" | "csv" | "xlsx" | "web"
    source_detail: str  # filename or product_id or url
    price_date: date | None = None
    attributes: dict[str, Any] | None = None
    relevance_score: float = 1.0
    url: str | None = None  # for web sources
    title: str | None = None  # for web sources


class PriceTableRow(BaseModel):
    source: str
    product: str
    price: str
    unit: str = "-"
    type: str  # "internal" | "external"
    date: str = "-"
    url: str | None = None
