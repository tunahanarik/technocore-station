"""The nine task states, the explicit transition table, and the honest half.

ADR-0004 3. Nine states are defined and the transitions between them are
written down **once**, in :data:`ALLOWED_TRANSITIONS`, rather than scattered
across database constraints and a "on failure go to cancel, not forward"
convention the way the write path's rules were before this package.

The honest half
---------------
Defining nine states does not make nine states reachable, and saying so is the
point:

* ``suggested`` needs a suggestion producer. That is Package H1.
* ``running`` and ``paused`` need an executor. That is Package H2.

What this release can genuinely produce is the six in :data:`PRODUCIBLE_STATES`.
The other three stay **defined** - so the machine is reviewable as a whole and
so H1/H2 do not have to re-derive it - and no code path can reach them:
:func:`validate_transition` refuses a target in :data:`UNPRODUCIBLE_STATES`
even though the table lists the edge. Opening one means deleting its entry
here, which is a deliberate change a reviewer sees.

That is ``CheckState.NOT_IMPLEMENTED``'s rule applied to a state machine: a
thing that has not been built does not get to sit there looking available.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskState(StrEnum):
    """The nine states a task can be defined in."""

    SUGGESTED = "suggested"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    FAILED = "failed"
    REVIEW_NEEDED = "review_needed"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"


#: One Turkish sentence per state, safe to show, in its own mapping rather than
#: on the enum - the ``CAPTURE_DETAIL`` pattern. None of them claims more than
#: the state establishes.
STATE_DETAIL: dict[TaskState, str] = {
    TaskState.SUGGESTED: (
        "Bir oneri ureticisi tarafindan onerildi. Bu surumde hicbir kod yolu "
        "bu durumu uretemez; oneri uretimi Paket H1'in konusudur."
    ),
    TaskState.AWAITING_APPROVAL: (
        "Gorev tanimlandi ve kullanicinin onayini bekliyor. Onay olmadan "
        "hicbir sey yurutulmez."
    ),
    TaskState.RUNNING: (
        "Gorev yurutuluyor. Bu surumde hicbir kod yolu bu durumu uretemez; "
        "yurutucu Paket H2'nin konusudur."
    ),
    TaskState.PAUSED: (
        "Yurutme duraklatildi. Bu surumde hicbir kod yolu bu durumu uretemez; "
        "yurutucu Paket H2'nin konusudur."
    ),
    TaskState.BLOCKED: (
        "Gorev ilerleyemiyor: bir on kosul saglanmadi. Engel kalkinca gorev "
        "yeniden onay bekleme durumuna doner."
    ),
    TaskState.FAILED: (
        "Gorev basarisiz bitti. Bu bir son durumdur; ayni gorev ileri "
        "tasinmaz, yeni bir gorev acilir."
    ),
    TaskState.REVIEW_NEEDED: (
        "Cikti uretildi ve incelenmeyi bekliyor. Inceleme, kanitlarin "
        "toplanmasi anlamina gelir; tek basina bir basari isareti degildir."
    ),
    TaskState.READY_TO_PUBLISH: (
        "Gorev ciktisi, test sonucu ve kullanici kabulu ayri ayri kanitlandi. "
        "Bu durum kanittan turer; elle isaretlenemez."
    ),
    TaskState.PUBLISHED: (
        "Gorevin sonucu yayimlandi. Dis paylasim bu surumde yoktur ve bu "
        "durum onu ima etmez (ADR-0004 4)."
    ),
}


#: The complete state machine, written once. Every edge the product may ever
#: have is here, including edges into states nothing can produce yet: a
#: transition table with holes in it is a table a later package rewrites from
#: memory.
ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.SUGGESTED: frozenset({TaskState.AWAITING_APPROVAL, TaskState.FAILED}),
    TaskState.AWAITING_APPROVAL: frozenset(
        {
            TaskState.RUNNING,
            TaskState.BLOCKED,
            TaskState.REVIEW_NEEDED,
            TaskState.FAILED,
        }
    ),
    TaskState.RUNNING: frozenset(
        {
            TaskState.PAUSED,
            TaskState.BLOCKED,
            TaskState.REVIEW_NEEDED,
            TaskState.FAILED,
        }
    ),
    TaskState.PAUSED: frozenset(
        {TaskState.RUNNING, TaskState.BLOCKED, TaskState.FAILED}
    ),
    TaskState.BLOCKED: frozenset({TaskState.AWAITING_APPROVAL, TaskState.FAILED}),
    # Terminal. A failed task is not walked forward; a new one is opened.
    TaskState.FAILED: frozenset(),
    TaskState.REVIEW_NEEDED: frozenset(
        {TaskState.READY_TO_PUBLISH, TaskState.BLOCKED, TaskState.FAILED}
    ),
    TaskState.READY_TO_PUBLISH: frozenset(
        {TaskState.PUBLISHED, TaskState.REVIEW_NEEDED, TaskState.BLOCKED}
    ),
    # Terminal. Publishing is not undone by moving a row.
    TaskState.PUBLISHED: frozenset(),
}

#: Where a task starts. Never ``suggested``: nothing suggests anything yet.
INITIAL_STATE: TaskState = TaskState.AWAITING_APPROVAL

#: The states this release can genuinely reach.
PRODUCIBLE_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.AWAITING_APPROVAL,
        TaskState.BLOCKED,
        TaskState.FAILED,
        TaskState.REVIEW_NEEDED,
        TaskState.READY_TO_PUBLISH,
        TaskState.PUBLISHED,
    }
)

#: Defined, listed in the table, and unreachable. Derived rather than written
#: out a second time, so the two lists cannot disagree.
UNPRODUCIBLE_STATES: frozenset[TaskState] = frozenset(TaskState) - PRODUCIBLE_STATES

#: Nothing leaves these.
TERMINAL_STATES: frozenset[TaskState] = frozenset(
    state for state, targets in ALLOWED_TRANSITIONS.items() if not targets
)

#: The state that may only be entered from real evidence, never by request.
EVIDENCE_DERIVED_STATES: frozenset[TaskState] = frozenset(
    {TaskState.READY_TO_PUBLISH, TaskState.PUBLISHED}
)


@dataclass(frozen=True, slots=True)
class TransitionVerdict:
    """Whether one transition is permitted, and precisely why not.

    A verdict rather than an exception, for the same reason
    ``write_gate.evaluate`` returns a status: the decision is a value that can
    be tested, logged and shown, and the caller decides what a refusal costs.
    """

    allowed: bool
    reason: str
    detail: str


def validate_transition(current: TaskState, target: TaskState) -> TransitionVerdict:
    """Apply the transition rules. Pure function; the service calls it.

    Three refusals, in the order they matter:

    1. the target is a state nothing in this build can produce;
    2. the edge is not in the table;
    3. the current state is terminal (a special case of 2, reported on its own
       because "this task is finished" is a different sentence from "that step
       does not exist").
    """
    if target in UNPRODUCIBLE_STATES:
        return TransitionVerdict(
            allowed=False,
            reason="state_not_producible",
            detail=(
                f"'{target.value}' bu surumde uretilemez. {STATE_DETAIL[target]}"
            ),
        )
    if current is target:
        return TransitionVerdict(
            allowed=False,
            reason="no_transition",
            detail="Gorev zaten bu durumda.",
        )
    if current in TERMINAL_STATES:
        return TransitionVerdict(
            allowed=False,
            reason="terminal_state",
            detail=(
                f"Gorev '{current.value}' durumunda bitti; bu bir son "
                "durumdur ve ileri tasinmaz."
            ),
        )
    if target not in ALLOWED_TRANSITIONS[current]:
        return TransitionVerdict(
            allowed=False,
            reason="transition_not_allowed",
            detail=(
                f"'{current.value}' durumundan '{target.value}' durumuna "
                "gecis tanimli degil."
            ),
        )
    return TransitionVerdict(
        allowed=True, reason="", detail=STATE_DETAIL[target]
    )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "EVIDENCE_DERIVED_STATES",
    "INITIAL_STATE",
    "PRODUCIBLE_STATES",
    "STATE_DETAIL",
    "TERMINAL_STATES",
    "UNPRODUCIBLE_STATES",
    "TaskState",
    "TransitionVerdict",
    "validate_transition",
]
