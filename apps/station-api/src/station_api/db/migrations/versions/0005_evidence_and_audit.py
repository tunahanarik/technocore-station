"""Evidence records and the append-only audit chain.

Three tables, and one deliberate omission in each.

``evidence_record``
    has a foreign key to ``message_nonce_reservation`` and **no**
    ``ON DELETE CASCADE``. Every other foreign key in this schema cascades,
    because a snapshot without its check or a vault record without its
    identity is meaningless. Evidence is the opposite case: it is the user's
    own archive of something they published, and a row that vanishes as a
    side effect of tidying the nonce ledger is a row whose absence nobody can
    explain afterwards (ADR-0003 10.1).

``audit_event``
    is append-only and has no retention policy at all. Deleting a row from
    the middle of a MAC chain is exactly what the chain exists to make
    visible, so pruning it on a schedule would mean breaking our own evidence
    on a schedule (ADR-0003 7).

``audit_chain_metadata``
    holds a path, a timestamp and a fingerprint - the ``secret_metadata``
    shape. The MAC material itself lives in a separate DPAPI envelope and
    enters no table.

No column added here holds a seed, a private key, a passphrase or a vault
path. The request and response bodies are scanned for secret shapes before a
row is written, and a hit refuses the write.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "evidence_record",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("reservation_id", sa.String(length=32), nullable=False),
        # Level 1: signature proof.
        sa.Column("did", sa.String(length=128), nullable=False),
        sa.Column("room", sa.String(length=48), nullable=False),
        sa.Column("nonce", sa.String(length=19), nullable=False),
        sa.Column("canonical", sa.Text(), nullable=False),
        sa.Column("canonical_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column(
            "signature_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        # Level 2: server observation.
        sa.Column("request_body", sa.LargeBinary(), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_body", sa.LargeBinary(), nullable=False),
        sa.Column("response_sha256", sa.String(length=64), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("write_outcome", sa.String(length=32), nullable=False),
        sa.Column("capture_state", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("capture_detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("export_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("room_generation", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("captured_line", sa.LargeBinary(), nullable=True),
        sa.Column("captured_line_offset", sa.Integer(), nullable=True),
        sa.Column("captured_line_length", sa.Integer(), nullable=True),
        sa.Column("captured_window", sa.Text(), nullable=False, server_default=""),
        sa.Column("stream_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("stream_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "stream_truncated", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("stream_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unreadable_lines", sa.Integer(), nullable=False, server_default="0"),
        # Level 3: local receipt time.
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        # Level 4: external anchoring. Always NULL in this release.
        sa.Column("external_anchor", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_record"),
        sa.UniqueConstraint("reservation_id", name="uq_evidence_per_reservation"),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["message_nonce_reservation.id"],
            name="fk_evidence_reservation",
            # No ondelete. See the module docstring.
        ),
    )
    op.create_index(
        "ix_evidence_record_recorded_at", "evidence_record", ["recorded_at"]
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("prev_mac", sa.String(length=64), nullable=False),
        sa.Column("mac", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_event"),
        # The database refuses a duplicate sequence number, so two writers
        # cannot both believe they appended link N.
        sa.UniqueConstraint("seq", name="uq_audit_event_seq"),
    )

    op.create_table(
        "audit_chain_metadata",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("envelope_relpath", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_chain_metadata"),
    )


def downgrade() -> None:
    op.drop_table("audit_chain_metadata")
    op.drop_table("audit_event")
    op.drop_index("ix_evidence_record_recorded_at", table_name="evidence_record")
    op.drop_table("evidence_record")
