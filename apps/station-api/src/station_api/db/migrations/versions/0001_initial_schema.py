"""Initial infrastructure schema.

Creates ``app_metadata`` only. The ``schema_migrations`` ledger is created by
Alembic itself. No table here holds a seed, private key or any other secret.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "app_metadata",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_app_metadata"),
    )


def downgrade() -> None:
    op.drop_table("app_metadata")
