"""The acceptance registry, and the day a task could finally be finished.

Package H4. The fact this file records is a change of fact, not a change of
rule, and the distinction is the whole of it:

* **arbitrary execution is still closed** (ADR-0008 1). Nothing here runs a
  process, and a plan's ``test_condition`` *sentence* is still never
  interpreted. ``test_agent_boundary.py``'s syntax-tree scans are unchanged
  and still red on a planted ``subprocess``;
* **what changed** is that a plan may now also record conditions from a
  closed, compile-time registry, and those conditions are decided by reading
  bytes the run left behind. That was always possible - three deterministic
  checkers have been in the tool registry since H2 - it simply had no way of
  adding up to a verdict about the task;
* **``not_implemented`` did not become a lie.** It is what a plan with no
  machine-checkable condition still reports, and such a plan still leaves
  ``ready_to_publish`` out of reach. Every test written before this file that
  asserted that is still here, still green, and still driving the same path;
* **SI-222 is unchanged.** ``ready_to_publish`` is derived from three
  separately verified fields and cannot be asked for:
  ``TaskUserTransitionName`` still omits it, and the route that derives it
  carries no target field to name it with.

The load-bearing assertion in this file is
``test_a_condition_that_holds_is_not_the_same_as_a_file_existing``: a verdict
has to be able to come out *false*, or the whole thing is a rubber stamp with
extra steps.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from station_api.agent import acceptance as acceptance_module
from station_api.agent.acceptance import (
    ACCEPTANCE_CHECKS,
    MAX_ACCEPTANCE_CONDITIONS,
    AcceptanceKind,
    AcceptanceState,
    bind_condition,
    evaluate,
    parse_keys,
    resolve_check,
)
from station_api.agent.errors import RunError, ToolArgumentError, ToolRegistryError
from station_api.agent.service import AgentService, RunPhase
from station_api.agent.tools import ToolParamType
from station_api.agent.workspace import ensure_workspace, task_workspace, write_text
from station_api.modules.fields import EvidenceField
from station_api.schemas import AgentPlanRequest
from station_api.tasks.service import TaskError, TaskService, TaskView
from station_api.tasks.states import TaskState

from tests.security.agent_fixtures import TEST_ONLY_CONDITION

pytestmark = pytest.mark.security


@pytest.fixture
def task_id(app) -> str:  # type: ignore[no-untyped-def]
    """A task opened through the application's own service, for the HTTP half."""
    from station_api.modules.registry import ModuleId
    from station_api.tasks.sources import TaskSourceId

    return str(
        app.state.tasks.open_task(
            module_id=ModuleId.AGENT_WORKSPACE,
            source=TaskSourceId.OPERATOR_REQUEST,
            content=b"TEST-ONLY acceptance task",
            title="TEST-ONLY",
        ).id
    )

#: The conditions this release can decide, typed out rather than imported. An
#: oracle read out of the constant under test proves only that the code agrees
#: with itself - which is how a review was once able to raise the real tool
#: ceiling to 9999 with the whole suite staying green.
EXPECTED_KINDS = frozenset(
    {
        "artifact_exists",
        "artifact_is_json",
        "artifact_has_json_keys",
        "artifact_contains",
        "artifact_digest_is",
    }
)

#: A document that satisfies every kind below, so one file drives all five.
BODY = '{"TEST_ONLY": true, "report": "hazir"}'

def _digest(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plan(
    agent: AgentService,
    task_id: str,
    *,
    conditions: list[tuple[str, dict[str, str]]],
    body: str = BODY,
    name: str = "rapor.json",
) -> str:
    """A one-step plan that writes ``body`` and is judged by ``conditions``."""
    return agent.plan_run(
        task_id,
        steps=[("write_workspace_file", {"name": name, "body": body})],
        expected_artifacts=[name],
        test_condition=TEST_ONLY_CONDITION,
        acceptance_conditions=conditions,
    ).id


# ---------------------------------------------------------------------------
# The registry is closed
# ---------------------------------------------------------------------------


def test_the_registry_is_exactly_the_conditions_this_release_has() -> None:
    assert {check.kind.value for check in ACCEPTANCE_CHECKS} == EXPECTED_KINDS
    assert {member.value for member in AcceptanceKind} == EXPECTED_KINDS
    assert len({check.kind for check in ACCEPTANCE_CHECKS}) == len(ACCEPTANCE_CHECKS)


def test_no_condition_parameter_can_carry_an_address() -> None:
    """The tool registry's rule, and it is the same rule because it is the same types.

    A condition names a file by a bare name. There is no ``path`` and no
    ``url``, so a success criterion cannot be pointed at the disk outside one
    task's workspace - which would otherwise be a read primitive wearing a
    test result's clothes.
    """
    for check in ACCEPTANCE_CHECKS:
        for param in check.params:
            assert isinstance(param.type, ToolParamType), (check.kind, param.name)
            assert param.type in {
                ToolParamType.FILE_NAME,
                ToolParamType.TEXT,
                ToolParamType.DIGEST,
            }
            assert param.name not in {"path", "url", "command", "script"}


def test_every_condition_declares_a_purpose_in_the_products_language() -> None:
    for check in ACCEPTANCE_CHECKS:
        assert check.purpose.strip(), check.kind
        assert not set(check.purpose) & set("çğıöşüÇĞİÖŞÜ"), check.kind


def test_an_unregistered_condition_gets_a_shown_refusal() -> None:
    """A refusal a user can read, not a ``KeyError`` that becomes a 500.

    The names chosen are the ones somebody would actually reach for when they
    wanted the closed capability: running a test command. They are refused as
    *unregistered conditions* rather than executed, which is the sentence this
    whole registry exists to be able to say.
    """
    for name in ("run_pytest", "shell_exit_code_is_zero", "npm test", ""):
        with pytest.raises(ToolRegistryError) as caught:
            resolve_check(name)
        assert caught.value.reason == "acceptance_condition_unknown"
        assert name not in str(caught.value) or not name


def test_an_argument_of_the_wrong_type_is_refused_while_planning() -> None:
    with pytest.raises(ToolArgumentError) as traversal:
        bind_condition("artifact_exists", {"name": "../gizli.txt"})
    assert traversal.value.reason == "argument_not_a_bare_name"

    with pytest.raises(ToolArgumentError) as unknown:
        bind_condition("artifact_exists", {"name": "a.json", "path": "C:/"})
    assert unknown.value.reason == "argument_unknown"

    with pytest.raises(ToolArgumentError) as digest:
        bind_condition("artifact_digest_is", {"name": "a.json", "digest": "kisa"})
    assert digest.value.reason == "argument_not_a_digest"


def test_a_key_list_is_parsed_into_bare_keys_and_bounded() -> None:
    assert parse_keys(" a , b ,a ") == ("a", "b")

    with pytest.raises(ToolArgumentError) as empty:
        parse_keys("  , ,")
    assert empty.value.reason == "acceptance_key_list_empty"

    with pytest.raises(ToolArgumentError) as many:
        parse_keys(",".join(f"k{index}" for index in range(100)))
    assert many.value.reason == "acceptance_too_many_keys"


# ---------------------------------------------------------------------------
# Every kind is driven, in both directions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "satisfied_arguments", "unsatisfied_arguments"),
    [
        (
            "artifact_exists",
            {"name": "rapor.json"},
            {"name": "yok.json"},
        ),
        (
            "artifact_is_json",
            {"name": "rapor.json"},
            {"name": "duz.txt"},
        ),
        (
            "artifact_has_json_keys",
            {"name": "rapor.json", "keys": "TEST_ONLY,report"},
            {"name": "rapor.json", "keys": "TEST_ONLY,eksik"},
        ),
        (
            "artifact_contains",
            {"name": "rapor.json", "text": "hazir"},
            {"name": "rapor.json", "text": "bulunmayan"},
        ),
        (
            "artifact_digest_is",
            {"name": "rapor.json", "digest": _digest(BODY)},
            {"name": "rapor.json", "digest": "0" * 64},
        ),
    ],
)
def test_a_condition_that_holds_is_not_the_same_as_a_file_existing(
    data_dir: Path,
    task: TaskView,
    kind: str,
    satisfied_arguments: dict[str, str],
    unsatisfied_arguments: dict[str, str],
) -> None:
    """Both directions for all five, over one real workspace on real bytes.

    The load-bearing test in the file. A checker that answered "yes" to
    everything would satisfy any test that only ever asked it satisfiable
    questions, so every kind is asked one it must refuse - and the refusing
    argument differs from the satisfying one in exactly the thing the kind is
    about, so a checker that happened to be reading the file name would fail
    three of the five.
    """
    directory = ensure_workspace(data_dir, task.id)
    write_text(directory, "rapor.json", BODY, replace_existing=False)
    write_text(directory, "duz.txt", "bu bir JSON belgesi degil", replace_existing=False)

    holds = evaluate((bind_condition(kind, satisfied_arguments),), directory)
    fails = evaluate((bind_condition(kind, unsatisfied_arguments),), directory)

    assert holds.state is AcceptanceState.PASSED, holds
    assert fails.state is AcceptanceState.FAILED, fails
    assert fails.failing_labels, "a failure has to name what failed"
    assert fails.results[0].detail.strip()


def test_a_condition_naming_a_missing_file_is_unsatisfied_rather_than_an_error(
    data_dir: Path, task: TaskView
) -> None:
    """A check that could not be made is not a check that passed.

    The exception a missing file raises is caught **here**, at the condition,
    rather than escaping into a run report or a 500 - and it is turned into
    ``failed`` with the reason attached rather than into a skipped condition,
    because a skipped condition would leave a plan able to pass by naming a
    file that never existed.
    """
    directory = ensure_workspace(data_dir, task.id)

    outcome = evaluate(
        (bind_condition("artifact_is_json", {"name": "hicyok.json"}),), directory
    )

    assert outcome.state is AcceptanceState.FAILED
    assert outcome.results[0].satisfied is False
    assert outcome.results[0].detail.strip()


def test_no_condition_at_all_is_not_a_pass(data_dir: Path, task: TaskView) -> None:
    """The vacuous-truth refusal, in the one place it would be most expensive.

    ``all([])`` is ``True``. A verdict built that way would report every plan
    that wrote no condition as having passed its own test, which is precisely
    the inference - "a file appeared, so it worked" - this product exists to
    refuse. It is a set equality instead, and this drives it.
    """
    outcome = evaluate((), task_workspace(data_dir, task.id))

    assert outcome.state is AcceptanceState.NOT_IMPLEMENTED
    assert outcome.state is not AcceptanceState.PASSED
    assert outcome.results == ()
    assert "uygulanmadi" in outcome.detail


# ---------------------------------------------------------------------------
# The plan carries the conditions, and the digest carries the plan
# ---------------------------------------------------------------------------


def test_the_conditions_are_inside_the_plan_digest(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    """Two plans that differ only in their success criterion are two plans.

    Without this, "the success criterion cannot be quietly loosened" would be
    false in the newest and most tempting way: the steps stay identical, the
    promised artifacts stay identical, and the condition that decides whether
    the work counts is swapped for an easier one.
    """
    strict = agent.get_run(
        _plan(
            agent,
            task.id,
            conditions=[("artifact_has_json_keys", {"name": "rapor.json", "keys": "a,b"})],
        )
    )
    loose = agent.get_run(
        _plan(agent, task.id, conditions=[("artifact_exists", {"name": "rapor.json"})])
    )
    none = agent.get_run(_plan(agent, task.id, conditions=[]))

    assert tasks.get(task.id).state is TaskState.AWAITING_APPROVAL
    assert len({strict.plan_sha256, loose.plan_sha256, none.plan_sha256}) == 3


def test_a_condition_edited_after_approval_refuses_the_run(
    agent: AgentService, task: TaskView, engine  # type: ignore[no-untyped-def]
) -> None:
    """The row is not the authority; the digest recorded at plan time is.

    Somebody who could edit the database could otherwise approve a plan judged
    by "the report carries these four keys" and run one judged by "a file
    exists" - and the run would report a pass against a criterion nobody
    approved.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from station_api.db.models import AgentRun

    run_id = _plan(
        agent,
        task.id,
        conditions=[("artifact_has_json_keys", {"name": "rapor.json", "keys": "a,b"})],
    )

    with Session(engine) as session, session.begin():
        row = session.scalars(select(AgentRun).where(AgentRun.id == run_id)).one()
        row.acceptance_json = json.dumps(
            {
                "conditions": [
                    {"arguments": {"name": "rapor.json"}, "kind": "artifact_exists"}
                ]
            }
        )

    with pytest.raises(RunError) as caught:
        agent.start_run(run_id)

    assert caught.value.reason == "plan_changed"


def test_a_plan_cannot_carry_more_conditions_than_the_bound(
    agent: AgentService, task: TaskView
) -> None:
    with pytest.raises(RunError) as caught:
        _plan(
            agent,
            task.id,
            conditions=[("artifact_exists", {"name": f"a{index}.json"}) for index in range(20)],
        )

    assert caught.value.reason == "plan_too_many_acceptance_conditions"
    assert str(MAX_ACCEPTANCE_CONDITIONS) in str(caught.value)


def test_the_request_bound_is_the_same_number_the_service_enforces() -> None:
    """The wire's ``max_length`` and the registry's ceiling are one number.

    They are written twice and cannot be written once:
    :mod:`station_api.schemas` imports nothing from ``station_api`` on purpose
    - every field that may leave this process is declared in a leaf module, so
    it cannot reach into a service package for a constant.

    ``agent.service`` used to carry a ``MAX_PLAN_ACCEPTANCE`` alias whose
    comment said it existed "so the route layer bounds the request body
    against the same number the service does". No route layer ever imported
    it, so the two numbers were in fact unguarded while a constant claimed to
    be guarding them - the drift ADR-0004 2 names, with a comment on top of
    it. The alias was removed and this assertion put in its place: it is the
    guard the alias only described.

    A wire bound *below* the service ceiling would refuse a plan the product
    accepts, and one *above* it would let a 422's job be done by a 400 deeper
    in - so equality, not an inequality, is the property.
    """
    field = AgentPlanRequest.model_fields["acceptance"]
    bounds = [
        item.max_length
        for item in field.metadata
        if getattr(item, "max_length", None) is not None
    ]

    assert bounds == [MAX_ACCEPTANCE_CONDITIONS]


def test_an_unregistered_condition_in_a_plan_is_recorded_as_a_denial(
    agent: AgentService, task: TaskView, tasks: TaskService, activity_log  # type: ignore[no-untyped-def]
) -> None:
    """ADR-0008 7's rule, on the newest surface a caller can reach.

    A refusal is an event, the task is not moved, and it is **not** quietly
    re-pointed at a condition the product does happen to support.
    """
    with pytest.raises(ToolRegistryError):
        _plan(agent, task.id, conditions=[("run_pytest", {"name": "rapor.json"})])

    actions = [view.action.value for view in activity_log.list_events()]

    assert "permission_denied" in actions
    assert tasks.get(task.id).state is TaskState.AWAITING_APPROVAL
    assert agent.list_runs(task.id) == ()


# ---------------------------------------------------------------------------
# A run reports a real verdict
# ---------------------------------------------------------------------------


def test_a_plan_with_no_condition_still_reports_not_implemented(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    """The old behaviour, kept and still driven.

    This is the assertion Package H2 built the whole runtime around, and
    nothing about H4 weakens it: a plan that recorded a sentence and no
    machine-checkable condition has not been checked, reports so, writes no
    ``test_result`` evidence and leaves the task short of publication.
    """
    view = agent.start_run(_plan(agent, task.id, conditions=[]))

    assert view.phase is RunPhase.COMPLETED
    assert view.test_result_state == "not_implemented"
    assert {ref.field for ref in tasks.get(task.id).refs} == {EvidenceField.TASK_OUTCOME}
    assert tasks.gate(task.id).ready_to_publish is False
    assert "test_result" in tasks.gate(task.id).blocking_fields


def test_a_run_whose_conditions_hold_records_a_verified_test_result(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    view = agent.start_run(
        _plan(
            agent,
            task.id,
            conditions=[
                ("artifact_is_json", {"name": "rapor.json"}),
                (
                    "artifact_has_json_keys",
                    {"name": "rapor.json", "keys": "TEST_ONLY,report"},
                ),
            ],
        )
    )

    assert view.phase is RunPhase.COMPLETED
    assert view.test_result_state == "passed"

    refs = {ref.field: ref for ref in tasks.get(task.id).refs}
    assert refs[EvidenceField.TEST_RESULT].verified is True
    assert refs[EvidenceField.TEST_RESULT].ref_id == view.id
    assert tasks.gate(task.id).blocking_fields == ("user_acceptance",)


def test_a_run_whose_conditions_do_not_hold_records_an_unverified_one(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    """A failure is recorded, named and blocking - not silence.

    Recording nothing would have been indistinguishable from a plan that
    never wrote a condition, and those are different situations: one is a gap
    in the plan, the other is a gap in the output.
    """
    view = agent.start_run(
        _plan(
            agent,
            task.id,
            conditions=[("artifact_contains", {"name": "rapor.json", "text": "yokbu"})],
        )
    )

    assert view.test_result_state == "failed"
    assert "artifact_contains" in view.test_result_detail

    refs = {ref.field: ref for ref in tasks.get(task.id).refs}
    assert refs[EvidenceField.TEST_RESULT].verified is False
    assert tasks.gate(task.id).ready_to_publish is False
    assert "test_result" in tasks.gate(task.id).blocking_fields


def test_the_verdict_follows_the_bytes_rather_than_the_moment_it_was_taken(
    agent: AgentService, task: TaskView, tasks: TaskService, data_dir: Path
) -> None:
    """A pass computed from bytes stops being a pass when the bytes change.

    Two independent mechanisms, and the test drives both, because either one
    alone would leave a stale pass reachable:

    * the **run** recomputes its verdict on every read, so it never serves a
      stored one;
    * the **evidence reference** the runner wrote is bound to the output
      revision, so a workspace edited from outside the runner drops it back to
      unverified and the gate closes again.
    """
    run_id = _plan(
        agent,
        task.id,
        conditions=[
            ("artifact_has_json_keys", {"name": "rapor.json", "keys": "TEST_ONLY"})
        ],
    )
    assert agent.start_run(run_id).test_result_state == "passed"

    directory = task_workspace(data_dir, task.id)
    write_text(directory, "rapor.json", '{"baska": 1}', replace_existing=True)

    assert agent.get_run(run_id).test_result_state == "failed"
    refs = {ref.field: ref for ref in tasks.get(task.id).refs}
    assert refs[EvidenceField.TEST_RESULT].verified is False
    assert tasks.gate(task.id).ready_to_publish is False


# ---------------------------------------------------------------------------
# The gate, and the state that is derived rather than asked for
# ---------------------------------------------------------------------------


def test_a_task_reaches_ready_to_publish_only_from_three_verified_fields(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    """The path this product could not walk before, walked - and only just.

    Each field is added one at a time and the gate is asked in between, so
    "all three" is measured rather than assumed: a gate that opened on two
    would be caught by the assertion before the third is recorded.
    """
    run_id = _plan(
        agent, task.id, conditions=[("artifact_is_json", {"name": "rapor.json"})]
    )
    agent.start_run(run_id)

    # task_outcome and test_result, both written by the run.
    assert tasks.gate(task.id).ready_to_publish is False
    assert tasks.gate(task.id).blocking_fields == ("user_acceptance",)
    with pytest.raises(TaskError) as early:
        tasks.transition(task.id, TaskState.READY_TO_PUBLISH)
    assert early.value.reason == "evidence_incomplete"

    # The third is a person's act and no automatic path fills it (SI-308).
    tasks.record_evidence(
        task.id,
        field=EvidenceField.USER_ACCEPTANCE,
        ref_id="TEST-ONLY-kabul",
        verified=True,
        detail="TEST-ONLY kullanici kabulu",
    )

    assert tasks.gate(task.id).ready_to_publish is True
    assert tasks.gate(task.id).blocking_fields == ()
    assert (
        tasks.transition(task.id, TaskState.READY_TO_PUBLISH).state
        is TaskState.READY_TO_PUBLISH
    )


def test_the_state_is_still_derived_and_still_cannot_be_named(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    """SI-222, re-driven now that the state is actually reachable.

    An invariant that was true only because nothing could produce the state is
    an invariant nobody has tested. Now that the evidence can be complete, the
    refusal has to be measured on a task that is genuinely *nearly* there: two
    of three fields verified, and the transition still refused.
    """
    from typing import get_args

    from station_api.schemas import TaskUserTransitionName

    agent.start_run(
        _plan(agent, task.id, conditions=[("artifact_exists", {"name": "rapor.json"})])
    )

    assert "ready_to_publish" not in get_args(TaskUserTransitionName)

    with pytest.raises(TaskError) as caught:
        tasks.transition(task.id, TaskState.READY_TO_PUBLISH)

    assert caught.value.reason == "evidence_incomplete"
    assert tasks.get(task.id).state is TaskState.REVIEW_NEEDED


def test_the_registry_cannot_be_extended_at_runtime() -> None:
    """A tuple literal, and a lookup nothing mutates.

    The same property the tool registry has, asserted the same way: the module
    exposes no registration function, and the record type refuses a write.
    """
    from dataclasses import FrozenInstanceError

    assert isinstance(ACCEPTANCE_CHECKS, tuple)
    with pytest.raises(FrozenInstanceError):
        ACCEPTANCE_CHECKS[0].kind = AcceptanceKind.ARTIFACT_EXISTS  # type: ignore[misc]

    public = {name for name in dir(acceptance_module) if not name.startswith("_")}
    for forbidden in ("register", "add_check", "install", "load_plugin"):
        assert forbidden not in public


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------


def test_the_surface_publishes_the_conditions_a_plan_may_be_judged_by(
    client, csrf_token: str  # type: ignore[no-untyped-def]
) -> None:
    """A set a person cannot enumerate is a set they cannot check.

    The conditions are published beside the tools for the same reason the
    tools are: approving a plan means approving what "it worked" was defined
    to mean, and that definition has to be visible before the run rather than
    discoverable after it.
    """
    assert csrf_token
    payload = client.get("/api/tasks/surface").json()

    assert {row["kind"] for row in payload["acceptance_checks"]} == EXPECTED_KINDS
    for row in payload["acceptance_checks"]:
        assert row["purpose"].strip()
        for param in row["params"]:
            assert param["type"] in {"text", "file_name", "digest"}


def test_the_publish_readiness_route_refuses_and_names_the_missing_fields(
    client, csrf_token: str, task_id: str  # type: ignore[no-untyped-def]
) -> None:
    response = client.post(
        f"/api/tasks/{task_id}/publish-readiness",
        json={},
        headers={"X-Station-CSRF": csrf_token},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    for field in ("task_outcome", "test_result", "user_acceptance"):
        assert field in detail


def test_the_publish_readiness_body_cannot_name_a_state(
    client, csrf_token: str, task_id: str  # type: ignore[no-untyped-def]
) -> None:
    """SI-222 at the HTTP surface: there is no field to put the state in.

    ``extra="forbid"`` on every body in this product means a caller who tries
    to supply one gets a 422 from the model rather than having it ignored -
    and "ignored" is the failure mode that would let somebody believe they had
    asked for something.
    """
    response = client.post(
        f"/api/tasks/{task_id}/publish-readiness",
        json={"target": "ready_to_publish"},
        headers={"X-Station-CSRF": csrf_token},
    )

    assert response.status_code == 422


def test_the_publish_readiness_route_derives_the_state_when_the_evidence_is_there(
    client, csrf_token: str, task_id: str, app  # type: ignore[no-untyped-def]
) -> None:
    """End to end over HTTP: plan, run, accept, derive.

    The whole path the product could not walk. Every step is a separate
    request a person made, and the last one names no state - it asks Station
    to read three fields and act on what they say.
    """
    headers = {"X-Station-CSRF": csrf_token}
    planned = client.post(
        f"/api/tasks/{task_id}/runs",
        json={
            "steps": [
                {
                    "tool_id": "write_workspace_file",
                    "arguments": {"name": "rapor.json", "body": BODY},
                }
            ],
            "expected_artifacts": ["rapor.json"],
            "test_condition": "TEST-ONLY olcut",
            "acceptance": [
                {
                    "kind": "artifact_has_json_keys",
                    "arguments": {"name": "rapor.json", "keys": "TEST_ONLY,report"},
                }
            ],
        },
        headers=headers,
    )
    assert planned.status_code == 200, planned.text
    run_id = planned.json()["runs"][0]["id"]

    started = client.post(
        f"/api/tasks/{task_id}/runs/{run_id}/start", json=None, headers=headers
    )
    assert started.status_code == 200, started.text
    run = started.json()["runs"][0]
    assert run["phase"] == "completed"
    assert run["test_result_state"] == "passed"
    assert [row["satisfied"] for row in run["acceptance"]] == [True]
    assert started.json()["task"]["ready_to_publish"] is False

    # The third field is a person's act, recorded through the service the
    # acceptance route already owns; no route here can fill it.
    app.state.tasks.record_evidence(
        task_id,
        field=EvidenceField.USER_ACCEPTANCE,
        ref_id="TEST-ONLY-kabul",
        verified=True,
        detail="TEST-ONLY",
    )

    derived = client.post(
        f"/api/tasks/{task_id}/publish-readiness",
        json={"detail": "TEST-ONLY"},
        headers=headers,
    )

    assert derived.status_code == 200, derived.text
    assert derived.json()["state"] == "ready_to_publish"
    assert derived.json()["ready_to_publish"] is True
    assert derived.headers["cache-control"] == "no-store"
