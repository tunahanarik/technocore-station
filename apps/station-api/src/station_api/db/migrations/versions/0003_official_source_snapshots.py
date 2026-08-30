"""Official source snapshots and manifest checks.

Stage 3 records what the official read-only sources looked like each time the
user ran a check. The tables are evidence: the write gate reads its verdict
from the in-process service, never from a row here, so an old successful
check can never re-open the outbound door on its own.

No column added here holds a seed, a private key, a passphrase, a vault path
or an arbitrary response header. Only the three cache-identity headers are
stored, and the body is kept as a bounded, swept excerpt.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "manifest_check",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("critical_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasons", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id", name="pk_manifest_check"),
    )
    op.create_index("ix_manifest_check_completed_at", "manifest_check", ["completed_at"])

    op.create_table(
        "official_source_snapshot",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("check_id", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("authority", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "content_type", sa.String(length=128), nullable=False, server_default=""
        ),
        sa.Column("etag", sa.String(length=256), nullable=False, server_default=""),
        sa.Column(
            "last_modified", sa.String(length=128), nullable=False, server_default=""
        ),
        sa.Column(
            "content_sha256", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column("byte_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id", name="pk_official_source_snapshot"),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["manifest_check.id"],
            name="fk_official_source_snapshot_check",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_official_source_snapshot_check_id",
        "official_source_snapshot",
        ["check_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_official_source_snapshot_check_id", table_name="official_source_snapshot"
    )
    op.drop_table("official_source_snapshot")
    op.drop_index("ix_manifest_check_completed_at", table_name="manifest_check")
    op.drop_table("manifest_check")
