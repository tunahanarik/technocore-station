"""SI-215 .. SI-218, SI-226, SI-277 - nine states, one explicit table, seven real.

ADR-0004 3 asks for two things that pull against each other and this file
holds both. The whole nine-state machine is written down once, so a later
package does not re-derive it from memory; and **no code path can reach the
states nothing produces yet**, so nobody reads the table as a list of things
that work.

Package H1 moved one name across that line, and the move is recorded rather
than quiet: ``suggested`` became producible when its producer was written
(ADR-0007 7). The oracles below were edited by hand on the same change and the
reason is written beside them. ``running`` and ``paused`` still await the
executor.

Two tests carry that claim, one behavioural and one structural, because the
first version of this file carried it with one and the one was narrower than
the sentence beside it:

* :func:`test_no_code_path_can_produce_an_unproducible_state` walks the real
  service against a real database. It no longer walks ``transition`` alone -
  it enumerates **every public method of** :class:`TaskService` by
  introspection and drives each with every argument its annotations admit, so
  a future ``start_running()`` that writes a row directly is driven too. The
  earlier version searched over transitions only, and the reviewer's probe -
  a four-line method setting ``state`` in a session - broke nothing.
* :func:`test_only_the_transition_method_writes_a_task_state` reads the
  syntax tree of the two Package F packages and requires that the *only* write
  to a ``.state`` attribute anywhere in them is the one in
  ``TaskService.transition``. The behavioural test can only find what it knows
  how to call; this one finds the writer regardless.

The oracle is written out here as :data:`EXPECTED_PRODUCIBLE` rather than
imported. ``UNPRODUCIBLE_STATES`` is derived from ``PRODUCIBLE_STATES`` and
``validate_transition`` refuses exactly that derived set, so a mutation that
adds ``running`` to the constant lifts the refusal *and* widens the expected
set at once - the walk found ``awaiting_approval -> running`` and agreed with
itself. Comparing against a set typed out from ADR-0004 3 is what makes
"editing the constant without opening anything breaks this" true.
"""

from __future__ import annotations

import ast
import inspect
import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args, get_type_hints

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from station_api.db.models import TaskRecord
from station_api.modules.fields import PUBLICATION_FIELDS, EvidenceField
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

#: What this release can genuinely reach. **Typed out, not imported**: this is
#: the oracle the reachability walk is compared against, and an oracle read out
#: of the constant under test proves only that the code agrees with itself.
#:
#: It was six under Package F and is seven under H1. That edit is the point at
#: which this file has to be read carefully rather than trusted, so the reason
#: is written here and not only in a commit message: ADR-0007 7 opened
#: ``suggested`` **because H1 built its producer**
#: (``TaskService.suggest_task``, driven by ``station_api.workscan``), which is
#: exactly the condition Package F's own docstring set for opening it. This is
#: a recorded opening, not a loosened assertion - and it is loosened in the
#: weakest possible sense, because the walk below still has to *reach*
#: ``suggested`` through the real service against a real database before this
#: set is believed. Adding a name here without a producer turns the walk red.
#:
#: What deliberately did not change is ``INITIAL_STATE``: see
#: ``test_the_initial_state_is_not_suggested``, which is the assertion that
#: keeps a user's own task and a scanned candidate distinguishable by the row.
EXPECTED_PRODUCIBLE = frozenset(
    {
        TaskState.SUGGESTED,
        TaskState.AWAITING_APPROVAL,
        TaskState.BLOCKED,
        TaskState.FAILED,
        TaskState.REVIEW_NEEDED,
        TaskState.READY_TO_PUBLISH,
        TaskState.PUBLISHED,
    }
)

#: The two that need the executor this release does not have. Also typed out.
EXPECTED_UNPRODUCIBLE = frozenset({TaskState.RUNNING, TaskState.PAUSED})

TEST_ONLY_CONTENT = b"TEST-ONLY task content, not a real work item."

#: The two packages Package F added. A state writer that moved out of
#: ``service.py`` would be the same hole in a different file.
PACKAGE_F_DIRS = ("modules", "tasks")

#: The one function permitted to write a task's state, as
#: ``<file>:<function>``. Anything else in the two packages is an offender.
THE_ONLY_STATE_WRITER = "service.py:transition"


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


class _TaskIdSentinel:
    """Stands in for "the task this walk opened", substituted at replay time.

    A move has to be replayable on a *fresh* task - transitions are not
    undoable, so every candidate path starts over - and the id is not known
    until the walk opens one.
    """

    def __repr__(self) -> str:  # pragma: no cover - failure output only
        return "<the task this walk opened>"


TASK_ID = _TaskIdSentinel()


@dataclass(frozen=True)
class Move:
    """One call on the service: a public method and one argument set."""

    method: str
    arguments: tuple[tuple[str, Any], ...]

    def bind(self, task_id: str) -> dict[str, Any]:
        return {
            name: (task_id if isinstance(value, _TaskIdSentinel) else value)
            for name, value in self.arguments
        }

    def __repr__(self) -> str:  # pragma: no cover - failure output only
        shown = ", ".join(f"{name}={value!r}" for name, value in self.arguments)
        return f"{self.method}({shown})"


def _candidate_values(name: str, annotation: Any) -> tuple[Any, ...]:
    """Every value worth passing for one parameter.

    Deliberately exhaustive over the enums: the walk is looking for a method
    that produces a state, and ``transition(task_id, TaskState.RUNNING)`` and
    ``start_running(task_id)`` have to be equally findable.

    An annotation this function does not recognise is an **error**, not a
    skip. A new producer with an argument nobody taught the walk about would
    otherwise be silently left undriven, which is the exact failure this test
    is being repaired for.
    """
    union = get_args(annotation)
    if union:
        values: list[Any] = [None] if type(None) in union else []
        for member in union:
            if member is not type(None):
                values.extend(_candidate_values(name, member))
        return tuple(values)
    if annotation is str:
        if name.endswith("task_id") or name == "id":
            return (TASK_ID,)
        if name == "ref_id":
            return ("TEST-ONLY-ref",)
        return ("TEST-ONLY metin",)
    if annotation is bytes:
        return (TEST_ONLY_CONTENT,)
    if annotation is bool:
        return (True, False)
    if annotation is TaskState:
        return tuple(TaskState)
    if annotation is EvidenceField:
        return tuple(EvidenceField)
    if annotation is ModuleId:
        return (ModuleId.PROJECT_ZERO,)
    if annotation is TaskSourceId:
        return tuple(TaskSourceId)
    raise AssertionError(
        f"the producer walk does not know how to supply {name}: {annotation!r}. "
        "Teach it, rather than letting a new producer go undriven."
    )


def _moves_for(method: str) -> list[Move]:
    """Every call of one public method the walk should try."""
    function = getattr(TaskService, method)
    hints = get_type_hints(function)
    hints.pop("return", None)
    names = [
        name
        for name in inspect.signature(function).parameters
        if name != "self"
    ]
    missing = [name for name in names if name not in hints]
    assert not missing, f"{method} has an unannotated parameter: {missing}"

    choices = [_candidate_values(name, hints[name]) for name in names]
    return [
        Move(method, tuple(zip(names, combination, strict=True)))
        for combination in itertools.product(*choices)
    ]


def _all_moves() -> list[Move]:
    """Every public method of the service, driven every way it accepts.

    ``dir`` rather than a hand-written list: a method added tomorrow is
    included tomorrow, without anybody remembering to add it here.
    """
    methods = sorted(
        name
        for name in dir(TaskService)
        if not name.startswith("_") and callable(getattr(TaskService, name))
    )
    assert methods, "the service should expose public methods"
    return [move for method in methods for move in _moves_for(method)]


def _states_in_database(engine: Engine) -> dict[str, str]:
    """Every task row's state, read straight from the table.

    Not through ``TaskService.get``: the question is what is *in the database*,
    and a producer that wrote a row the service declines to show would still
    have produced the state.
    """
    with Session(engine) as session:
        rows = session.execute(select(TaskRecord)).scalars().all()
        return {row.id: row.state for row in rows}


def _drive(
    service: TaskService, engine: Engine, moves: list[Move]
) -> tuple[str | None, set[str]]:
    """Replay ``moves`` on a fresh task.

    Returns the walked task's final state - ``None`` when a move was refused,
    so the path is not extended from there - and every state string any row
    created during this walk held at any point.
    """
    before = set(_states_in_database(engine))
    view = _open(service, with_evidence=True)
    observed = {_states_in_database(engine)[view.id]}

    for move in moves:
        try:
            getattr(service, move.method)(**move.bind(view.id))
        except TaskError:
            return None, observed
        rows = _states_in_database(engine)
        observed |= {
            state for task_id, state in rows.items() if task_id not in before
        }
    return _states_in_database(engine).get(view.id), observed


def _reachable_states(service: TaskService, engine: Engine) -> set[str]:
    """Every state any public method of the service can put a row into.

    Breadth-first over *moves* rather than over transition targets, so a
    producer that is not ``transition`` extends the frontier exactly the same
    way ``transition`` does. Bounded by the state set: at most nine frontier
    nodes, each expanded once.
    """
    moves = _all_moves()
    reached = {INITIAL_STATE.value}
    paths: dict[str, list[Move]] = {INITIAL_STATE.value: []}
    queue = [INITIAL_STATE.value]

    while queue:
        current = queue.pop()
        for move in moves:
            candidate = [*paths[current], move]
            final, observed = _drive(service, engine, candidate)
            reached |= observed
            if final is not None and final not in paths:
                paths[final] = candidate
                queue.append(final)
    return reached


class _StateWriteFinder(ast.NodeVisitor):
    """Every write to a ``.state`` attribute, with the function it is in."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self._stack: list[str] = []
        self.offenders: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check(node.target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # ``setattr(row, "state", ...)`` is the same write with a comma in it.
        if isinstance(node.func, ast.Name) and node.func.id == "setattr":
            named = node.args[1] if len(node.args) > 1 else None
            if isinstance(named, ast.Constant) and named.value == "state":
                self._record()
        self.generic_visit(node)

    def _check(self, target: ast.expr) -> None:
        if isinstance(target, ast.Attribute) and target.attr == "state":
            self._record()

    def _record(self) -> None:
        where = self._stack[-1] if self._stack else "<module>"
        self.offenders.append(f"{self.filename}:{where}")


def _state_writers(api_source_root: Path) -> list[str]:
    """``<file>:<function>`` for every state write in the two F packages."""
    writers: list[str] = []
    for name in PACKAGE_F_DIRS:
        for path in (api_source_root / "station_api" / name).rglob("*.py"):
            finder = _StateWriteFinder(path.name)
            finder.visit(ast.parse(path.read_text(encoding="utf-8")))
            writers.extend(finder.offenders)
    return sorted(writers)


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
    """Kept unchanged through H1, and it is now doing more work than before.

    While ``suggested`` was unproducible this said "nothing suggests anything
    yet". H1 built a suggester, and the assertion stays exactly as it was on
    purpose (ADR-0007 7): a task the **user** opened must not be born in the
    state a **scan** produces, because the starting state is one of the two
    independent layers that keep the two apart - the other being the source
    identifier, and therefore ``source_version_id``.

    A future change that made ``suggested`` the initial state would collapse
    both layers into one column and is refused here.
    """
    assert INITIAL_STATE is TaskState.AWAITING_APPROVAL
    assert INITIAL_STATE in PRODUCIBLE_STATES
    assert INITIAL_STATE is not TaskState.SUGGESTED


# ---------------------------------------------------------------------------
# The pure transition function
# ---------------------------------------------------------------------------


def test_the_unproducible_states_are_exactly_the_two_that_await_an_executor() -> None:
    assert set(UNPRODUCIBLE_STATES) == EXPECTED_UNPRODUCIBLE
    assert set(PRODUCIBLE_STATES) == EXPECTED_PRODUCIBLE
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
    service: TaskService, engine: Engine
) -> None:
    """Driven through the real service, against a real database.

    Every public method, every argument its annotations admit, breadth-first
    until the frontier stops growing - and the states are read back out of the
    table, not out of the return value. A producer that writes a row directly
    instead of going through ``transition`` is found here, which the earlier
    transition-only search was not able to do.

    The comparison is against :data:`EXPECTED_PRODUCIBLE`, typed out from
    ADR-0004 3. Comparing against ``PRODUCIBLE_STATES`` alone would let a
    single edit to that constant both lift the refusal and move the goalposts;
    the constant is checked too, on the line after, so the two claims are
    separable.
    """
    reached = _reachable_states(service, engine)

    assert reached == {state.value for state in EXPECTED_PRODUCIBLE}
    assert reached == {state.value for state in PRODUCIBLE_STATES}
    assert not reached & {state.value for state in EXPECTED_UNPRODUCIBLE}


def test_the_producer_walk_actually_drives_every_public_method() -> None:
    """The walk's own coverage, pinned.

    ``_all_moves`` is introspective, so it silently covers a method added
    later - and would just as silently cover *nothing* if the introspection
    broke. This states what it found: every public method of the service, and
    ``transition`` driven at all nine targets.
    """
    moves = _all_moves()
    driven = {move.method for move in moves}
    expected = {
        name
        for name in dir(TaskService)
        if not name.startswith("_") and callable(getattr(TaskService, name))
    }

    assert driven == expected
    assert "transition" in driven and "record_evidence" in driven
    targets = {
        dict(move.arguments)["target"]
        for move in moves
        if move.method == "transition"
    }
    assert targets == set(TaskState)


def test_only_the_transition_method_writes_a_task_state(
    api_source_root: Path,
) -> None:
    """The structural half, beside the behavioural one.

    The reachability walk can only find a producer it knows how to call. This
    one does not call anything: it reads the syntax tree of both Package F
    packages and requires that the single write to a ``.state`` attribute -
    plain assignment, annotated, augmented or through ``setattr`` with a
    literal name - is the one inside ``TaskService.transition``, the function
    that runs ``validate_transition`` first.

    A method that opened ``running`` by writing the row itself fails here even
    if nothing ever calls it.
    """
    assert _state_writers(api_source_root) == [THE_ONLY_STATE_WRITER]


def test_the_state_write_scan_would_see_a_second_writer(tmp_path: Path) -> None:
    """The scan, checked against the shape it exists to catch.

    A structural test that never fires is a structural test nobody has
    verified. This feeds it the reviewer's own probe - a method that sets
    ``state`` inside a session - plus the ``setattr`` spelling of the same
    write, and requires both to be reported.
    """
    package = tmp_path / "station_api" / "tasks"
    package.mkdir(parents=True)
    (tmp_path / "station_api" / "modules").mkdir()
    (package / "service.py").write_text(
        "class TaskService:\n"
        "    def transition(self, task_id):\n"
        "        row.state = 'published'\n"
        "    def start_running(self, task_id):\n"
        "        row.state = 'running'\n"
        "    def start_paused(self, task_id):\n"
        "        setattr(row, 'state', 'paused')\n",
        encoding="utf-8",
    )

    assert _state_writers(tmp_path) == [
        "service.py:start_paused",
        "service.py:start_running",
        THE_ONLY_STATE_WRITER,
    ]


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
