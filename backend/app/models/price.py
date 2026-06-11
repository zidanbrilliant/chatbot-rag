import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ProductCategory(str, enum.Enum):
    PRODUCT = "product"
    STOCK = "stock"
    CRYPTO = "crypto"
    MATERIAL = "material"
    SERVICE = "service"
    OTHER = "other"


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku = Column(String(50), unique=True, nullable=True, index=True)
    name = Column(Text, nullable=False)
    category = Column(String(50), nullable=True)
    unit = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    attributes = Column(JSONB, nullable=True)
    source = Column(String(20), nullable=False, default="manual")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    prices = relationship(
        "ProductPrice",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="desc(ProductPrice.price_date)",
    )
    ohlc_prices = relationship(
        "PriceOHLC",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="desc(PriceOHLC.trade_date)",
    )

    __table_args__ = (
        Index("ix_products_name_idx", "name"),
        Index("ix_products_category_idx", "category"),
    )

    def latest_price(self) -> "ProductPrice | None":
        if not self.prices:
            return None
        return max(self.prices, key=lambda p: p.price_date)

    def price_on_date(self, target: date) -> "ProductPrice | None":
        for p in self.prices:
            if p.price_date == target:
                return p
        return None

    def latest_ohlc(self) -> "PriceOHLC | None":
        if not self.ohlc_prices:
            return None
        return max(self.ohlc_prices, key=lambda o: o.trade_date)

    def ohlc_on_date(self, target: date) -> "PriceOHLC | None":
        for o in self.ohlc_prices:
            if o.trade_date == target:
                return o
        return None


class ProductPrice(Base):
    __tablename__ = "product_prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="IDR")
    price_date = Column(Date, nullable=False, index=True)
    supplier = Column(String(100), nullable=True)
    source = Column(String(20), nullable=False, default="manual")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="prices")

    __table_args__ = (
        Index("ix_product_prices_product_date_idx", "product_id", "price_date"),
    )

    def to_decimal(self) -> Decimal:
        return Decimal(str(self.price))


class PriceOHLC(Base):
    __tablename__ = "price_ohlc"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trade_date = Column(Date, nullable=False, index=True)
    open = Column(Numeric(18, 2), nullable=True)
    high = Column(Numeric(18, 2), nullable=True)
    low = Column(Numeric(18, 2), nullable=True)
    close = Column(Numeric(18, 2), nullable=True)
    volume = Column(Numeric(20, 4), nullable=True)
    currency = Column(String(10), nullable=False, default="IDR")
    source = Column(String(20), nullable=False, default="manual")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="ohlc_prices")

    __table_args__ = (
        UniqueConstraint("product_id", "trade_date", name="uq_ohlc_product_date"),
        Index("ix_ohlc_product_date_idx", "product_id", "trade_date"),
    )

    def get_field(self, field: str) -> Decimal | None:
        """Return OHLC field by name. Field: open|high|low|close."""
        val = getattr(self, field, None)
        if val is None:
            return None
        return Decimal(str(val))

