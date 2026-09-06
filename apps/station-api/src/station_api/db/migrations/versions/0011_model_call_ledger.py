"""One table: how many model turns a task has spent.

Purely additive. No existing table is renamed, no existing column is altered
and no record identity changes; a database upgraded to this revision has every
row it had, plus an empty table.

``model_call_ledger``  one row per task, created the first time that task
                       spends a model turn. ``model_calls_used`` is the count
                       ADR-0012 3 made this product's only ceiling, and this
                       revision is what makes it survive both "start over"
                       and a relaunch (ADR-0013).

A task with no row has spent nothing, which is exactly what every task in a
database written before this revision had: the count lived in process memory
and there was none of it left to migrate. So there is no backfill, and none
would have been honest - a number invented for a task whose turns nobody
recorded would be a ceiling built out of a guess.

Why a table rather than a column on ``task_record``: SI-225 says the task
layer opens no budget field and
``test_the_task_layer_opens_no_budget_field`` reads that table's columns
directly, so a count added there would be the rule being rewritten to fit the
code. Why not derived from ``activity_event``: that table has a retention
policy (``RETAINED_EVENTS``) and a user-invoked delete, so a ceiling read out
of it would be a ceiling a person clears by tidying their timeline.

The foreign key cascades on delete for ``agent_run``'s reason: a task that no
longer exists has no ceiling, and a row pointing at nothing is a row somebody
has to explain later.

No column name added here contains ``seed``, ``secret``, ``key``, ``private``,
``mnemonic``, ``passphrase``, ``password`` or ``token``, and none holds a
model reasoning trace, a prompt, a completion or a raw provider payload. The
table holds a task id, an integer and two timestamps.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "model_call_ledger",
        sa.Column(
            "task_id",
            sa.String(length=32),
            sa.ForeignKey("task_record.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "model_calls_used", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("first_call_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_call_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("model_call_ledger")
