"""Message nonce reservations.

Stage 4 hands out one strictly increasing nonce per ``(did, room)`` pair and
records what became of it. The table is the counter itself - there is no
"last value" row that could drift away from the reservations - so a crash
between reserving and sending leaves the number burnt rather than available.

The unique constraint is the load-bearing part: it is what makes a lost race
impossible even between two processes sharing this database file, rather than
merely unlikely under one process's lock.

No column added here holds a seed, a private key, a passphrase or a vault
path. A did:key, a room name and a nonce are all public protocol values.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "message_nonce_reservation",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("did", sa.String(length=128), nullable=False),
        sa.Column("room", sa.String(length=48), nullable=False),
        sa.Column("nonce", sa.String(length=19), nullable=False),
        sa.Column("nonce_value", sa.BigInteger(), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id", name="pk_message_nonce_reservation"),
        sa.UniqueConstraint("did", "room", "nonce_value", name="uq_nonce_per_did_room"),
    )
    # The reservation path asks exactly one question - "what is the highest
    # number this pair has used?" - on every draft signature, so it gets an
    # index shaped like that question.
    op.create_index(
        "ix_message_nonce_reservation_pair",
        "message_nonce_reservation",
        ["did", "room", "nonce_value"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_message_nonce_reservation_pair", table_name="message_nonce_reservation"
    )
    op.drop_table("message_nonce_reservation")
