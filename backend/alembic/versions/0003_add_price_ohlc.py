"""add price_ohlc table for OHLC time-series

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11

Adds separate table for OHLC (Open/High/Low/Close) time-series data
used for stocks, crypto, and other financial instruments.

Why a separate table:
- product_prices is single-value per date (generic)
- price_ohlc is multi-value per date (financial instruments)
- Different aggregation patterns (MAX/MIN over ranges)
- Cleaner indexing strategy

Fields:
- open, high, low, close: OHLC values
- volume: optional trading volume
- trade_date: the date this row represents (UNIQUE per product)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_ohlc",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(18, 2), nullable=True),
        sa.Column("high", sa.Numeric(18, 2), nullable=True),
        sa.Column("low", sa.Numeric(18, 2), nullable=True),
        sa.Column("close", sa.Numeric(18, 2), nullable=True),
        sa.Column("volume", sa.Numeric(20, 4), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="IDR"),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "trade_date", name="uq_ohlc_product_date"),
    )
    op.create_index("ix_ohlc_product_date", "price_ohlc", ["product_id", "trade_date"])
    op.create_index("ix_ohlc_trade_date", "price_ohlc", ["trade_date"])


def downgrade() -> None:
    op.drop_index("ix_ohlc_trade_date", table_name="price_ohlc")
    op.drop_index("ix_ohlc_product_date", table_name="price_ohlc")
    op.drop_table("price_ohlc")
