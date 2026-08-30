"""Identity, secret metadata and recovery records.

No column added here holds a seed, a private key, a passphrase or recovery
ciphertext. The secret lives only in the DPAPI vault file.

``identity.active_slot`` is a nullable UNIQUE column holding 1 while an
identity is live and NULL once revoked. SQLite does not treat NULLs as equal,
so this enforces "at most one non-revoked identity" in the schema.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "identity",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("did", sa.String(length=128), nullable=False),
        sa.Column("public_key", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_identity"),
        sa.UniqueConstraint("did", name="uq_identity_did"),
        sa.UniqueConstraint("active_slot", name="uq_identity_active_slot"),
    )

    op.create_table(
        "secret_metadata",
        sa.Column("identity_id", sa.String(length=32), nullable=False),
        sa.Column("vault_relpath", sa.Text(), nullable=False),
        sa.Column("protection", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("identity_id", name="pk_secret_metadata"),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["identity.id"],
            name="fk_secret_metadata_identity",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "recovery_record",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("identity_id", sa.String(length=32), nullable=False),
        sa.Column("file_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("kdf", sa.String(length=32), nullable=False),
        sa.Column("kdf_time_cost", sa.Integer(), nullable=False),
        sa.Column("kdf_memory_kib", sa.Integer(), nullable=False),
        sa.Column("kdf_parallelism", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_recovery_record"),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["identity.id"],
            name="fk_recovery_record_identity",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_recovery_record_identity_id", "recovery_record", ["identity_id"])


def downgrade() -> None:
    op.drop_index("ix_recovery_record_identity_id", table_name="recovery_record")
    op.drop_table("recovery_record")
    op.drop_table("secret_metadata")
    op.drop_table("identity")
