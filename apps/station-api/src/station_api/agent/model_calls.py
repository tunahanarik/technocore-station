"""The model-call counters: they only go up, and neither has a reset.

Two of them since ADR-0014, for two lanes that spend the same unit against
the same ceiling. :class:`ModelCallCounter` is the planning lane's, keyed by
task and written to a row. :class:`ScanModelCallCounter` is the work scan's,
keyed by nothing because a scan is one request, and its own docstring states
what that costs rather than leaving the asymmetry to be discovered. What they
share is the part that matters: one writer each, addition only, no setter,
and :func:`station_api.agent.budget.check` deciding whether one more turn may
be spent.

The rest of this docstring is about the first one.

The model-call counter: per task, durable, and it only goes up.

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

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from station_api.agent import budget
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


@dataclass(slots=True)
class ScanModelCallCounter:
    """Model turns one **scan** has spent. Per scan, monotonic, no reset.

    ADR-0014 4. The work scan spends model turns now, so it needs the same two
    things the planning lane needs: a number this process counts itself, and a
    limit expressed in that number. Both are the ones that already exist -
    :func:`station_api.agent.budget.check` and
    :attr:`station_api.agent.budget.RunCeiling.max_model_calls` - so there is
    no second ceiling anywhere and ``budget.py`` is untouched.

    Why this one is not a row, when the planning lane's is
    ------------------------------------------------------
    ADR-0013 moved the planning count to ``model_call_ledger`` because the
    defect there was a **refillable counter for a long-lived subject**: the
    number was a field on a task's in-memory session, and "start over" dropped
    the session, so a button handed back a fresh ceiling against a metered
    endpoint.

    A scan has no such subject. It is one synchronous request: there is no
    button inside it, no session to resume and no restart to survive. A row
    keyed by a fresh scan id would be refilled by the next scan exactly as
    this object is, so it would bound nothing that this does not bound - and a
    control that can be deleted with nothing going red is the shape ADR-0012 1
    removed rather than kept.

    The cost is stated rather than hidden: **a second scan starts with a fresh
    ceiling.** That is the same sentence ADR-0013 3.1 writes about a second
    task, and it needs the same thing - a deliberate user action. What stands
    between a person and an unbounded bill is therefore the ceiling *inside* a
    scan plus the cost sentence beside the button, and both are stated on the
    surface (ADR-0014 6).

    What this class cannot do
    --------------------------
    There is no ``reset``, no ``clear`` and no setter, for
    :class:`ModelCallCounter`'s reason. :meth:`record_call` adds one;
    :attr:`used` reads. ``test_nothing_lowers_the_scan_model_call_counter``
    reads the syntax tree of the whole ``station_api`` package and refuses any
    write to ``_scan_model_calls_used`` outside the one method that increments
    it, and a second test requires that write to be an addition.
    """

    #: Declared rather than assigned in a body, and that is not a style
    #: choice. ``test_nothing_lowers_the_scan_model_call_counter`` requires
    #: exactly **one** write to this attribute in the whole product; an
    #: ``__init__`` that set it to zero would be a second one, and a second
    #: one is a method somebody can call again. The dataclass generates the
    #: initialisation, so the only write in the source is the increment.
    _scan_model_calls_used: int = field(default=0, init=False)

    @property
    def used(self) -> int:
        """Turns this scan has spent so far."""
        return self._scan_model_calls_used

    @property
    def max_model_calls(self) -> int:
        """The ceiling, read from the one place a ceiling is decided."""
        return budget.CEILING.max_model_calls

    def verdict(self) -> budget.BudgetVerdict:
        """May one more turn be spent? The planning lane's own pure check.

        Called **before** a request is built, so a refusal here costs nothing
        because nothing was sent. ``tool_calls`` and ``elapsed_seconds`` are
        zero because this lane makes no tool call and takes no wall-clock
        budget of its own; the only unit it spends is the one it is asking
        about.
        """
        return budget.check(
            budget.RunUsage(
                tool_calls=0,
                model_calls=self._scan_model_calls_used,
                elapsed_seconds=0.0,
            )
        )

    def record_call(self) -> int:
        """Count one turn against this scan and return the new total.

        The **only** writer, and it only adds. Called once, immediately after
        a provider answer has been parsed - the same moment the planning lane
        counts one, so what a turn costs means the same thing on both lanes.
        A turn the provider never answered is not counted, because nothing
        came back to count.
        """
        self._scan_model_calls_used += 1
        return self._scan_model_calls_used


__all__ = ["ModelCallCounter", "ScanModelCallCounter"]
