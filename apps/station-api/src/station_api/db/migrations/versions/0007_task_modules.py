"""Task records, their four evidence fields, and the transition ledger.

Package F's storage. Purely additive: no existing table is renamed, no
existing column is altered and no record identity changes (ADR-0004 11).

Three tables, and the shape of the middle one is the decision:

``task_record``            one task, bound to a registry module, a registry
                           source id and a content version.
``task_evidence_outcome``  the **four fields**, as four separate groups of
                           columns rather than one status or one boolean
                           (ADR-0004 4). ``public_share_*`` is written by
                           nothing in this release; the columns exist so the
                           absence can be stated instead of inferred.
``task_state_transition``  every accepted state change, appended.

No column name contains ``seed``, ``secret``, ``key``, ``private``,
``mnemonic``, ``passphrase`` or ``password``. Everything stored here is a
registry identifier, a digest, a public reference or a Turkish sentence.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: None = None
depends_on: None = None


def _evidence_field_columns(prefix: str) -> list[sa.Column[Any]]:
    """One field's five columns.

    Written as a helper so the four groups cannot drift apart in the DDL, and
    so adding a column to one field without the others is a visible edit
    rather than a copy-paste omission.
    """
    return [
        sa.Column(f"{prefix}_ref_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            f"{prefix}_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            f"{prefix}_version_id", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column(f"{prefix}_detail", sa.Text(), nullable=False, server_default=""),
        sa.Column(f"{prefix}_recorded_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "task_record",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("module_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_version_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_record_module_id", "task_record", ["module_id"])
    op.create_index(
        "ix_task_record_source_version_id", "task_record", ["source_version_id"]
    )

    op.create_table(
        "task_evidence_outcome",
        sa.Column(
            "task_id",
            sa.String(length=32),
            sa.ForeignKey("task_record.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        *_evidence_field_columns("task_outcome"),
        *_evidence_field_columns("test_result"),
        *_evidence_field_columns("user_acceptance"),
        *_evidence_field_columns("public_share"),
    )

    op.create_table(
        "task_state_transition",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(length=32),
            sa.ForeignKey("task_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_state", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_task_state_transition_task_id", "task_state_transition", ["task_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_task_state_transition_task_id", table_name="task_state_transition")
    op.drop_table("task_state_transition")
    op.drop_table("task_evidence_outcome")
    op.drop_index("ix_task_record_source_version_id", table_name="task_record")
    op.drop_index("ix_task_record_module_id", table_name="task_record")
    op.drop_table("task_record")
