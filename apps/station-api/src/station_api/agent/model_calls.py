"""The model-call counter: per task, durable, and it only goes up.

ADR-0013. This module exists because the number it holds is the **only spend
control this product owns**. ADR-0012 3 decided that on purpose: the provider
sends ``usage`` and ``cost``, both are recorded exactly as it stated them, and
neither is ever read as a limit, because a ceiling denominated in a number the
counterparty supplies is a ceiling the counterparty sets. What is left is the
count of requests Station itself made, and that count is the whole budget.

Why it is not a field on a session
-----------------------------------
It was one, and that was the defect. ``ModelPlannerService`` kept the count
inside the in-memory session, and ``forget`` - the "start over" button - drops
the session. So pressing a button handed back a fresh ceiling, as many times
as somebody pressed it, against a metered endpoint. The same was true of
closing and reopening the application, with more friction and the same result.

The conversation *should* die with the process (SI-224: a restart resumes
nothing, and there is nowhere in this schema to put model output anyway,
ADR-0008 6). The count should not. They are two different facts that happened
to share a home, and this module is the count moving out.

Why here and not somewhere else
--------------------------------
* **not on ``task_record``.** SI-225 says the task layer opens no budget
  field and ``test_the_task_layer_opens_no_budget_field`` reads that table's
  columns directly, so putting it there would be the rule being edited to fit
  the code rather than the other way round.
* **not derived from ``activity_event``.** Every counted turn does write a
  ``model_called`` row, so counting those rows looks free - and it would be a
  ceiling with a retention policy (``RETAINED_EVENTS``) and a user-invoked
  ``delete_events`` behind it. "Clear your timeline to clear your ceiling" is
  the same defect ``forget`` was, through a tidier door.
* **not in ``budget.py``.** That module is the ceiling: a frozen constant, no
  I/O, and an AST scan that requires ``CEILING`` be assigned exactly once. The
  limit and the meter are different things and stay in different files.

What this module cannot do
---------------------------
There is no ``reset``, no ``clear`` and no setter. :meth:`ModelCallCounter.record_call`
adds one and returns the new total; :meth:`ModelCallCounter.used` reads. A
count that could be lowered from anywhere would put the defect back with a
different name, so the absence is structural rather than a convention -
``test_nothing_lowers_the_model_call_counter`` reads the syntax tree of this
package and refuses any write to ``model_calls_used`` outside the one method
that increments it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from station_api.db.models import ModelCallLedger


class ModelCallCounter:
    """One task's spent model turns, read and incremented. Nothing else.

    Held by :class:`~station_api.agent.service.AgentService` and reached
    through its ``model_calls`` property, so the planning lane asks the same
    object the rest of the agent layer would.
    """

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def used(self, task_id: str) -> int:
        """How many turns this task has spent. A read; writes no row.

        A task with no row has spent nothing, and that is a real answer rather
        than a missing one: the row is written by the first counted turn, so
        "no row" and "zero" mean the same thing and always have.
        """
        with Session(self._engine) as session:
            spent = session.scalar(
                select(ModelCallLedger.model_calls_used).where(
                    ModelCallLedger.task_id == task_id
                )
            )
        return int(spent or 0)

    def record_call(self, task_id: str) -> int:
        """Count one turn against this task and return the new total.

        The **only** writer in this build, and it only adds. Called once, from
        the planning service, immediately after a provider answer has been
        parsed - the same place the in-memory counter used to be incremented,
        so what a turn costs did not change when where it is written did.

        The row is created on first use rather than when a task is opened: a
        task nobody ever asks a model about should not carry a spend record,
        and a ledger full of zeroes would make "this task has spent something"
        harder to read rather than easier.
        """
        now = datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            row = session.get(ModelCallLedger, task_id)
            if row is None:
                row = ModelCallLedger(
                    task_id=task_id,
                    model_calls_used=1,
                    first_call_at=now,
                    last_call_at=now,
                )
                session.add(row)
            else:
                row.model_calls_used += 1
                row.last_call_at = now
            session.flush()
            return int(row.model_calls_used)


__all__ = ["ModelCallCounter"]
