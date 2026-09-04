"""The OpenCode connection's three tables.

Package G's storage. Purely additive: no existing table is renamed, no
existing column is altered and no record identity changes.

``opencode_credential_metadata``  where the DPAPI envelope is (relative), when
                                  it was written, and a fingerprint. **Never
                                  the credential.**
``opencode_catalog_check``        one user-initiated read of the public model
                                  catalog, in the ``official_source_snapshot``
                                  shape.
``opencode_model_snapshot``       the rows that read returned, joined to the
                                  compile-time protocol table.

No column name contains ``seed``, ``secret``, ``key``, ``private``,
``mnemonic``, ``passphrase`` or ``password`` - ``key`` included, which is why
the credential column is ``envelope_relpath`` and the fingerprint column is
``fingerprint``.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "opencode_credential_metadata",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("envelope_relpath", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "opencode_catalog_check",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("http_status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "content_sha256", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column("byte_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_excerpt", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "opencode_model_snapshot",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "check_id",
            sa.String(length=32),
            sa.ForeignKey("opencode_catalog_check.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("owned_by", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_stamp", sa.BigInteger(), nullable=True),
        sa.Column(
            "selectable", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("protocol", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("mapping_state", sa.String(length=32), nullable=False),
        sa.Column(
            "training_use",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.create_index(
        "ix_opencode_model_snapshot_check_id", "opencode_model_snapshot", ["check_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opencode_model_snapshot_check_id", table_name="opencode_model_snapshot"
    )
    op.drop_table("opencode_model_snapshot")
    op.drop_table("opencode_catalog_check")
    op.drop_table("opencode_credential_metadata")
