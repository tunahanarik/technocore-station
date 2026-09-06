"""One column: the plan's machine-checkable acceptance conditions.

Purely additive. No existing table is renamed, no existing column is altered
and no record identity changes; every ``agent_run`` row written before this
revision keeps its data and gets ``[]``, which is exactly what it meant - a
plan that recorded a success criterion as a sentence and nothing a machine
could decide.

``agent_run.acceptance_json``  the conditions, as a canonical JSON array of
                               ``{"kind": ..., "arguments": {...}}`` objects,
                               every one of them a member of the closed
                               registry in :mod:`station_api.agent.acceptance`
                               with arguments already validated against that
                               member's declared parameter types.

It is a column on the run rather than a row somewhere else because it is part
of the **plan**: ``plan_sha256`` covers it along with the steps, the expected
artifacts and the test condition, so a plan whose success criterion is edited
after the fact is a different plan and ``start_run`` refuses it. Storing the
conditions anywhere the digest did not reach would have made "the success
criterion cannot be quietly loosened" a sentence rather than a property.

What this column is **not**: it holds no free text to be executed, no command,
no path and no address. A ``kind`` is a registry member and an argument is a
bare file name, a bounded piece of text or a hex digest. Arbitrary execution
stays closed (ADR-0008 1) and nothing in this build reads this column as code.

No column name added here contains ``seed``, ``secret``, ``key``, ``private``,
``mnemonic``, ``passphrase``, ``password`` or ``token``, and none holds a
model reasoning trace, a prompt, a completion or a raw provider payload.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "agent_run",
        sa.Column("acceptance_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("agent_run", "acceptance_json")
