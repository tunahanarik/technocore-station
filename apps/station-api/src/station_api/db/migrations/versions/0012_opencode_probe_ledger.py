"""One table: what the connection probe spent, and what it last answered.

Purely additive. No existing table is renamed, no existing column is altered
and no record identity changes; a database upgraded to this revision has every
row it had, plus an empty table.

``opencode_probe_ledger``  one row per credential **fingerprint**, created the
                           first time that credential is probed.
                           ``probes_used`` is the ceiling ADR-0015 puts on a
                           button that spends a metered model turn, and the
                           three verdict columns are what keeps
                           ``GET /api/opencode/status`` free of the probe while
                           still able to report its result.

The key is the fingerprint and **not** a foreign key to
``opencode_credential_metadata``. That row is deleted whenever a key is
forgotten or replaced, so a cascade would hand back a fresh ceiling for two
button presses - the ``forget`` defect ADR-0013 was written about. Keyed to the
fingerprint, re-saving the same key finds the same row.

There is no backfill and none would be honest: no installation written before
this revision ever ran a probe, so every credential's true count is zero, which
is exactly what "no row" already means.

No column name added here contains ``seed``, ``secret``, ``key``, ``private``,
``mnemonic``, ``passphrase``, ``password`` or ``token``. ``detail`` holds the
bounded, credential-redacted, reasoning-stripped excerpt the client already
produces; it never holds a prompt, a completion or a raw provider payload.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "opencode_probe_ledger",
        sa.Column("fingerprint", sa.String(length=64), primary_key=True),
        sa.Column("probes_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_probe_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("opencode_probe_ledger")
