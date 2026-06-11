"""add price tables: products, product_prices

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-11

Adds two tables for price lookup feature:
- products: master catalog (sku, name, category, unit, attributes JSONB)
- product_prices: time-series price history (price, currency, date, supplier)

Indexes:
- products.name (GIN trigram for ILIKE search)
- product_prices (product_id, price_date) composite
- product_prices.price_date (single)

Both tables support PRD T2.1 RBAC, T3.x ingestion, T4.x RAG.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pg_trgm extension for GIN trigram index (used for ILIKE search)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(50), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index(
        "ix_products_name_trgm",
        "products",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "product_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("price", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="IDR"),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("supplier", sa.String(100), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_prices_product_date",
        "product_prices",
        ["product_id", "price_date"],
    )
    op.create_index(
        "ix_product_prices_price_date", "product_prices", ["price_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_product_prices_price_date", table_name="product_prices")
    op.drop_index(
        "ix_product_prices_product_date", table_name="product_prices"
    )
    op.drop_table("product_prices")
    op.drop_index("ix_products_name_trgm", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_table("products")
