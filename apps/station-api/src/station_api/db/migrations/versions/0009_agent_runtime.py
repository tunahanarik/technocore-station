"""The agent runtime's three tables.

Package H2's storage. Purely additive: no existing table is renamed, no
existing column is altered and no record identity changes.

``agent_run``       one bounded run of registered tools over one task, with
                    the plan digest, the frozen success criterion and the
                    ceiling that was in force, recorded before it starts.
``agent_run_step``  one planned tool call and what became of it.
``activity_event``  the Activity Desk's append-only timeline. Separate from
                    the audit chain on purpose (ADR-0008 6): these rows are
                    not chain links, so their retention cannot break a MAC,
                    and ``chain_referenced`` marks the ones a chain link
                    names so retention refuses to remove them.

No column name contains ``seed``, ``secret``, ``key``, ``private``,
``mnemonic``, ``passphrase``, ``password`` or ``token``, and none holds a
model reasoning trace, a prompt, a completion or a raw provider payload -
there is no model lane in this build to produce one (ADR-0008 2).

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "agent_run",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(length=32),
            sa.ForeignKey("task_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "stop_requested", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("plan_sha256", sa.String(length=64), nullable=False),
        sa.Column("test_condition", sa.Text(), nullable=False, server_default=""),
        sa.Column("expected_artifacts", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("tool_calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False),
        sa.Column("max_wall_clock_seconds", sa.Integer(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_agent_run_task_id", "agent_run", ["task_id"])

    op.create_table(
        "agent_run_step",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=32),
            sa.ForeignKey("agent_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("tool_id", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("arguments_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("arguments_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "phase", sa.String(length=32), nullable=False, server_default="planned"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "artifact_name", sa.String(length=200), nullable=False, server_default=""
        ),
        sa.Column(
            "artifact_sha256", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_agent_run_step_run_id", "agent_run_step", ["run_id"])

    op.create_table(
        "activity_event",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("task_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "artifact_sha256", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column(
            "check_sha256", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "chain_referenced", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_activity_event_run_id", "activity_event", ["run_id"])
    op.create_index(
        "ix_activity_event_recorded_at", "activity_event", ["recorded_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_activity_event_recorded_at", table_name="activity_event")
    op.drop_index("ix_activity_event_run_id", table_name="activity_event")
    op.drop_table("activity_event")
    op.drop_index("ix_agent_run_step_run_id", table_name="agent_run_step")
    op.drop_table("agent_run_step")
    op.drop_index("ix_agent_run_task_id", table_name="agent_run")
    op.drop_table("agent_run")
