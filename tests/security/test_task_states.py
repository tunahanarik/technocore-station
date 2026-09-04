"""SI-215 .. SI-218 - nine states, one explicit table, and six of them real.

ADR-0004 3 asks for two things that pull against each other and this file
holds both. The whole nine-state machine is written down once, so a later
package does not re-derive it from memory; and **no code path can reach the
three states nothing produces yet**, so nobody reads the table as a list of
things that work.

The load-bearing test is
:func:`test_no_code_path_can_produce_an_unproducible_state`. It does not read
the source and it does not trust ``PRODUCIBLE_STATES``: it drives the real
service through every transition the machine offers, from a real database,
collects the states it actually reached, and compares that set against the
constant. If a future package opens ``running`` without editing
``PRODUCIBLE_STATES``, this fails. If it edits the constant without opening
anything, this fails too.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine
from station_api.modules.fields import PUBLICATION_FIELDS
from station_api.modules.registry import ModuleId
from station_api.tasks.service import TaskError, TaskService, TaskView
from station_api.tasks.sources import TaskSourceId
from station_api.tasks.states import (
    ALLOWED_TRANSITIONS,
    EVIDENCE_DERIVED_STATES,
    INITIAL_STATE,
    PRODUCIBLE_STATES,
    STATE_DETAIL,
    TERMINAL_STATES,
    UNPRODUCIBLE_STATES,
    TaskState,
    validate_transition,
)

pytestmark = pytest.mark.security

#: The nine names the prompt and ADR-0004 3 enumerate. Written out rather than
#: derived, so a rename or a deletion fails instead of agreeing with itself.
CHARTER_STATE_NAMES = frozenset(
    {
        "suggested",
        "awaiting_approval",
        "running",
        "paused",
        "blocked",
        "failed",
        "review_needed",
        "ready_to_publish",
        "published",
    }
)

#: The three that need a producer this release does not have.
EXPECTED_UNPRODUCIBLE = frozenset(
    {TaskState.SUGGESTED, TaskState.RUNNING, TaskState.PAUSED}
)

TEST_ONLY_CONTENT = b"TEST-ONLY task content, not a real work item."


@pytest.fixture
def service(engine: Engine) -> TaskService:
    return TaskService(engine=engine)


def _open(service: TaskService, *, with_evidence: bool) -> TaskView:
    """A fresh task, optionally with all three publication fields verified.

    The evidence matters for this file only because ``ready_to_publish`` is
    derived from it: a reachability walk that never recorded any would find
    that state unreachable for the wrong reason and would then "prove" the
    machine is smaller than it is.
    """
    view = service.open_task(
        module_id=ModuleId.PROJECT_ZERO,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=TEST_ONLY_CONTENT,
        title="TEST-ONLY gorev",
    )
    if with_evidence:
        for index, field in enumerate(sorted(PUBLICATION_FIELDS)):
            view = service.record_evidence(
                view.id,
                field=field,
                ref_id=f"TEST-ONLY-ref-{index}",
                verified=True,
                detail="TEST-ONLY dogrulandi.",
            )
    return view


def _walk(service: TaskService, path: list[TaskState]) -> TaskState | None:
    """Follow ``path`` on a fresh task; ``None`` when a step is refused."""
    view = _open(service, with_evidence=True)
    for target in path:
        try:
            view = service.transition(view.id, target)
        except TaskError:
            return None
    return view.state


def _reachable_states(service: TaskService) -> set[TaskState]:
    """Every state the service can actually put a task into.

    Breadth-first over the nine possible targets, with a fresh task per path
    because transitions are not undoable. Bounded by the state set, so this is
    at most nine short walks and not a combinatorial search.
    """
    reached = {INITIAL_STATE}
    paths: dict[TaskState, list[TaskState]] = {INITIAL_STATE: []}
    queue = [INITIAL_STATE]

    while queue:
        current = queue.pop()
        for target in TaskState:
            if target in reached:
                continue
            candidate = [*paths[current], target]
            if _walk(service, candidate) is target:
                reached.add(target)
                paths[target] = candidate
                queue.append(target)
    return reached


# ---------------------------------------------------------------------------
# The nine states and the table
# ---------------------------------------------------------------------------


def test_all_nine_states_are_defined() -> None:
    assert {state.value for state in TaskState} == CHARTER_STATE_NAMES


def test_every_state_carries_one_sentence() -> None:
    """The ``CAPTURE_DETAIL`` pattern: sentences beside the enum, not on it."""
    assert set(STATE_DETAIL) == set(TaskState)
    for state, sentence in STATE_DETAIL.items():
        assert sentence.strip(), state
        # Diacritic-free Turkish, like every other user-visible string here.
        assert not set(sentence) & set("çğıöşüÇĞİÖŞÜ"), state


def test_the_transition_table_is_explicit_and_total() -> None:
    """Every state has an entry, and every target is a known state.

    Explicit is the point (ADR-0004 3): before this package the rules lived in
    database constraints and a "on failure go to cancel, not forward"
    convention, and there was no one place to read them.
    """
    assert set(ALLOWED_TRANSITIONS) == set(TaskState)

    for source, targets in ALLOWED_TRANSITIONS.items():
        assert isinstance(targets, frozenset), source
        for target in targets:
            assert target in TaskState
            assert target is not source, f"{source} lists itself"


def test_terminal_states_have_no_exit() -> None:
    assert set(TERMINAL_STATES) == {TaskState.FAILED, TaskState.PUBLISHED}
    for state in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[state] == frozenset()


def test_the_table_still_lists_the_edges_into_unbuilt_states() -> None:
    """The other half of the honesty rule.

    Deleting ``running`` from the table would make H2 re-invent the machine,
    and a machine re-invented from memory is a machine that disagrees with the
    one that came before. The edges stay; the *service* is what refuses them.
    """
    assert TaskState.RUNNING in ALLOWED_TRANSITIONS[TaskState.AWAITING_APPROVAL]
    assert TaskState.PAUSED in ALLOWED_TRANSITIONS[TaskState.RUNNING]
    assert TaskState.AWAITING_APPROVAL in ALLOWED_TRANSITIONS[TaskState.SUGGESTED]


def test_the_initial_state_is_not_suggested() -> None:
    """Nothing suggests anything yet, so nothing may start there."""
    assert INITIAL_STATE is TaskState.AWAITING_APPROVAL
    assert INITIAL_STATE in PRODUCIBLE_STATES


# ---------------------------------------------------------------------------
# The pure transition function
# ---------------------------------------------------------------------------


def test_the_unproducible_states_are_exactly_the_three_the_adr_names() -> None:
    assert set(UNPRODUCIBLE_STATES) == EXPECTED_UNPRODUCIBLE
    assert set(TaskState) == PRODUCIBLE_STATES | UNPRODUCIBLE_STATES
    assert not PRODUCIBLE_STATES & UNPRODUCIBLE_STATES


def test_the_pure_function_refuses_every_edge_into_an_unbuilt_state() -> None:
    """From any state, to any of the three: refused, and told why."""
    for current in TaskState:
        for target in UNPRODUCIBLE_STATES:
            verdict = validate_transition(current, target)
            assert verdict.allowed is False, (current, target)
            assert verdict.reason == "state_not_producible"
            assert target.value in verdict.detail


def test_an_edge_that_is_not_in_the_table_is_refused() -> None:
    verdict = validate_transition(
        TaskState.AWAITING_APPROVAL, TaskState.READY_TO_PUBLISH
    )

    assert verdict.allowed is False
    assert verdict.reason == "transition_not_allowed"


def test_a_terminal_state_is_named_as_finished_rather_than_as_a_bad_edge() -> None:
    """Two different sentences for two different situations."""
    verdict = validate_transition(TaskState.FAILED, TaskState.REVIEW_NEEDED)

    assert verdict.allowed is False
    assert verdict.reason == "terminal_state"


def test_a_no_op_transition_is_refused() -> None:
    verdict = validate_transition(TaskState.BLOCKED, TaskState.BLOCKED)

    assert verdict.allowed is False
    assert verdict.reason == "no_transition"


def test_every_permitted_edge_between_producible_states_is_permitted() -> None:
    for source, targets in ALLOWED_TRANSITIONS.items():
        if source in UNPRODUCIBLE_STATES:
            continue
        for target in targets:
            if target in UNPRODUCIBLE_STATES:
                continue
            assert validate_transition(source, target).allowed, (source, target)


# ---------------------------------------------------------------------------
# The behavioural pin
# ---------------------------------------------------------------------------


def test_no_code_path_can_produce_an_unproducible_state(
    service: TaskService,
) -> None:
    """Driven through the real service, against a real database.

    This is the test ADR-0004 3 asks for: the set of states any producer can
    reach, compared against the set the code claims. Opening ``running`` later
    means editing ``PRODUCIBLE_STATES`` deliberately, which is the point -
    a future package cannot open one by accident and have the suite agree.
    """
    reached = _reachable_states(service)

    assert reached == set(PRODUCIBLE_STATES)
    assert not reached & UNPRODUCIBLE_STATES


@pytest.mark.parametrize("target", sorted(EXPECTED_UNPRODUCIBLE))
def test_the_service_refuses_a_direct_request_for_an_unbuilt_state(
    service: TaskService, target: TaskState
) -> None:
    view = _open(service, with_evidence=True)

    with pytest.raises(TaskError) as caught:
        service.transition(view.id, target)

    assert caught.value.reason == "state_not_producible"
    assert service.get(view.id).state is INITIAL_STATE


def test_a_refused_transition_leaves_no_ledger_row(service: TaskService) -> None:
    """Nothing happened, so nothing is recorded. Only accepted moves append."""
    view = _open(service, with_evidence=False)
    before = len(service.transitions(view.id))

    with pytest.raises(TaskError):
        service.transition(view.id, TaskState.RUNNING)

    assert len(service.transitions(view.id)) == before


def test_every_accepted_transition_is_appended_to_the_ledger(
    service: TaskService,
) -> None:
    view = _open(service, with_evidence=True)
    service.transition(view.id, TaskState.REVIEW_NEEDED)
    service.transition(view.id, TaskState.READY_TO_PUBLISH)
    final = service.transition(view.id, TaskState.PUBLISHED)

    ledger = service.transitions(view.id)

    assert final.state is TaskState.PUBLISHED
    assert [row.to_state for row in ledger] == [
        TaskState.AWAITING_APPROVAL.value,
        TaskState.REVIEW_NEEDED.value,
        TaskState.READY_TO_PUBLISH.value,
        TaskState.PUBLISHED.value,
    ]
    assert ledger[0].from_state == ""


def test_a_published_task_cannot_be_walked_back(service: TaskService) -> None:
    view = _open(service, with_evidence=True)
    service.transition(view.id, TaskState.REVIEW_NEEDED)
    service.transition(view.id, TaskState.READY_TO_PUBLISH)
    service.transition(view.id, TaskState.PUBLISHED)

    for target in TaskState:
        with pytest.raises(TaskError):
            service.transition(view.id, target)


def test_the_evidence_derived_states_are_the_two_that_are_derived() -> None:
    assert set(EVIDENCE_DERIVED_STATES) == {
        TaskState.READY_TO_PUBLISH,
        TaskState.PUBLISHED,
    }
