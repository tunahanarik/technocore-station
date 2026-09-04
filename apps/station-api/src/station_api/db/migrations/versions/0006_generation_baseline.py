"""Separate the generation baseline from the generation a line was read under.

``0005`` gave ``evidence_record`` a single ``room_generation`` column and the
capture path overwrote it with whatever the latest read published. That made
two different things share one column, and both were wrong afterwards:

* the **baseline** was gone. ``generation_changed`` is decided by comparing a
  read against the epoch the record was first seen under; once the new epoch
  had been written over the old one, the next capture compared the room
  against itself and reported ``line_not_found`` - "your message is not
  there", said about a room that is not the same room. A state that is only
  ever reported once is not a state, it is a notification;
* the **stored line** kept no epoch of its own. A line captured under
  generation 7 was exported beside the value 8 with nothing saying the two
  came from different rooms.

So the baseline stays in ``room_generation`` and is written once,
``capture_generation`` records the epoch the stored line was actually read
under, and ``generation_changed`` makes the verdict sticky rather than
recomputing it from a value that has since moved.

Existing rows: ``capture_generation`` is backfilled from ``room_generation``
where a line was captured, because that is what it was - and left empty where
no line was captured, because there is nothing to stamp. ``generation_changed``
is backfilled from ``capture_state``, which is the only surviving record of a
verdict that was reached.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "evidence_record",
        sa.Column(
            "capture_generation", sa.String(length=32), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "evidence_record",
        sa.Column(
            "generation_changed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.execute(
        sa.text(
            "UPDATE evidence_record SET capture_generation = room_generation "
            "WHERE captured_line IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE evidence_record SET generation_changed = 1 "
            "WHERE capture_state = 'generation_changed'"
        )
    )


def downgrade() -> None:
    op.drop_column("evidence_record", "generation_changed")
    op.drop_column("evidence_record", "capture_generation")
