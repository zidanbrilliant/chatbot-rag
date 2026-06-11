"""add attributes JSONB column to documents

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11

Adds JSONB column 'attributes' to documents table for storing
file-specific metadata (e.g., csv_products_imported: true, source_format, etc.)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "attributes")
