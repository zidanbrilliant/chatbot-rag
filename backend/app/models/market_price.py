"""MarketPriceSnapshot model — caches marketplace prices with timestamps.

Each row is a single price observation from one marketplace, scraped on a
specific datetime. Used by the comparison flow to avoid hitting DDG on every
query. Cache TTL is 24 hours (older snapshots are considered stale and
re-scraped on demand).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


# Marketplace identifiers used throughout the system.
MARKETPLACE_TOKOPEDIA = "tokopedia"
MARKETPLACE_SHOPEE = "shopee"
MARKETPLACE_LAZADA = "lazada"
MARKETPLACE_BUKALAPAK = "bukalapak"
MARKETPLACE_BHINNEKA = "bhinneka"
MARKETPLACE_BLIBLI = "blibli"
MARKETPLACE_BRAND_STORE = "brand_store"

SUPPORTED_MARKETPLACES: list[str] = [
    MARKETPLACE_TOKOPEDIA,
    MARKETPLACE_SHOPEE,
    MARKETPLACE_LAZADA,
    MARKETPLACE_BUKALAPAK,
    MARKETPLACE_BHINNEKA,
    MARKETPLACE_BLIBLI,
    MARKETPLACE_BRAND_STORE,
]

MARKETPLACE_BRANDS = [
    "polytron.co.id", "sharpindonesia.com", "lg.com/id",
    "samsung.com/id", "aqua.co.id", "mi.co.id",
]

# Map marketplace ID -> DuckDuckGo `site:` domain. Used to scope searches.
MARKETPLACE_DOMAINS: dict[str, list[str]] = {
    MARKETPLACE_TOKOPEDIA: ["tokopedia.com"],
    MARKETPLACE_SHOPEE: ["shopee.co.id"],
    MARKETPLACE_LAZADA: ["lazada.co.id"],
    MARKETPLACE_BUKALAPAK: ["bukalapak.com"],
    MARKETPLACE_BHINNEKA: ["bhinneka.com"],
    MARKETPLACE_BLIBLI: ["blibli.com"],
    MARKETPLACE_BRAND_STORE: MARKETPLACE_BRANDS,
}


class MarketPriceSnapshot(Base):
    __tablename__ = "market_price_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_sku = Column(String(50), nullable=True, index=True)
    product_query = Column(Text, nullable=False, index=True)
    marketplace = Column(String(50), nullable=False, index=True)
    price = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="IDR")
    url = Column(Text, nullable=True)
    snippet_excerpt = Column(Text, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    age_days = Column(Integer, nullable=True)

    __table_args__ = (
        # Cache lookup: same query + same marketplace, latest first
        Index(
            "ix_market_cache_query_mp_time",
            "product_query", "marketplace", "scraped_at",
        ),
        UniqueConstraint("product_query", "marketplace", "scraped_at",
                         name="uq_market_query_mp_time"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "product_sku": self.product_sku,
            "product_query": self.product_query,
            "marketplace": self.marketplace,
            "price": float(self.price),
            "currency": self.currency,
            "url": self.url,
            "snippet_excerpt": (self.snippet_excerpt or "")[:200],
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "age_days": self.age_days,
        }
