"""add market_price_snapshots table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17

Adds market_price_snapshots table for caching marketplace prices with
timestamps. Used by the comparison flow to avoid hitting DDG on every
query. Cache TTL is 24 hours.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_price_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_sku", sa.String(50), nullable=True),
        sa.Column("product_query", sa.Text(), nullable=False),
        sa.Column("marketplace", sa.String(50), nullable=False),
        sa.Column("price", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="IDR"),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("snippet_excerpt", sa.Text(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("age_days", sa.Integer(), nullable=True),
    )
    op.create_index("ix_market_price_snapshots_product_sku",
                    "market_price_snapshots", ["product_sku"])
    op.create_index("ix_market_price_snapshots_product_query",
                    "market_price_snapshots", ["product_query"])
    op.create_index("ix_market_price_snapshots_marketplace",
                    "market_price_snapshots", ["marketplace"])
    op.create_index("ix_market_price_snapshots_scraped_at",
                    "market_price_snapshots", ["scraped_at"])
    op.create_index("ix_market_cache_query_mp_time",
                    "market_price_snapshots",
                    ["product_query", "marketplace", "scraped_at"])
    op.create_unique_constraint(
        "uq_market_query_mp_time",
        "market_price_snapshots",
        ["product_query", "marketplace", "scraped_at"],
    )


def downgrade() -> None:
    op.drop_table("market_price_snapshots")
