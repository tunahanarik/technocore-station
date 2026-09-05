"""The run: planned first, bounded, stoppable, and honest about the test field.

ADR-0008 3 and 7. The properties this file holds are the ones that make a run
reviewable after the fact rather than merely observable while it happens:

* **the plan exists before the run does.** Steps, promised artifacts and the
  check that would establish success are recorded, digested, and re-checked
  when the run starts. Changing any of them changes the digest, so a success
  criterion cannot be loosened after the fact and then reported as met.
* **a produced file is not a passed test.** The runner records
  ``task_outcome`` from what it actually produced and **never** records
  ``test_result``, because running the check is exactly the capability
  ADR-0008 1 closes. So a finished run leaves the task in ``review_needed``
  and ``ready_to_publish`` stays unreachable - SI-222, unchanged.
* **four endings, four sentences.** The ceiling, a tool failure, a user stop
  and a promise that was not kept are distinct phases. A user who cannot tell
  "you ran out of budget" from "your input was broken" cannot act on either.
* **stop means the next call does not happen**, and a result that arrives
  after the stop leaves nothing behind - including the file it wrote.
* **a restart loads the plan and resumes nothing** (SI-224).
* **an out-of-scope request is recorded, not worked around.** The task is not
  quietly re-pointed at something the agent *can* do.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from station_api.agent import budget as budget_module
from station_api.agent.activity import ActivityAction, ActivityLog, ActivityOutcome
from station_api.agent.budget import CEILING, RunCeiling
from station_api.agent.errors import RunError, ToolArgumentError, ToolRegistryError
from station_api.agent.service import (
    TEST_RESULT_STATE,
    AgentService,
    RunPhase,
    StepPhase,
)
from station_api.agent.workspace import list_files
from station_api.db.models import AgentRun, AgentRunStep
from station_api.modules.fields import EvidenceField
from station_api.tasks.service import TaskError, TaskService, TaskView
from station_api.tasks.states import TaskState

from tests.security.agent_fixtures import TEST_ONLY_CONDITION, write_plan

pytestmark = pytest.mark.security

#: The tool-call ceiling, typed out rather than imported. An oracle read out
#: of the constant under test proves only that the code agrees with itself -
#: which is how a review was able to raise the real ceiling to 9999 with the
#: whole suite staying green.
EXPECTED_MAX_TOOL_CALLS = 32


def _actions(log: ActivityLog, run_id: str = "") -> list[str]:
    return [view.action.value for view in log.list_events(run_id=run_id)]


# ---------------------------------------------------------------------------
# The plan comes first
# ---------------------------------------------------------------------------


def test_planning_records_everything_and_runs_nothing(
    agent: AgentService, task: TaskView, tasks: TaskService, activity_log: ActivityLog
) -> None:
    """Two decisions, not one - the composer's shape (ADR-0002 2).

    A person approves *what will be done*, and then separately that it be
    done. Planning must therefore leave the task exactly where it was and the
    workspace empty.
    """
    run_id = write_plan(agent, task.id)
    view = agent.get_run(run_id)

    assert view.phase is RunPhase.PLANNED
    assert [step.phase for step in view.steps] == [StepPhase.PLANNED] * 2
    assert view.test_condition == TEST_ONLY_CONDITION
    assert view.expected_artifacts == ("rapor.json",)
    assert view.plan_sha256
    assert tasks.get(task.id).state is TaskState.AWAITING_APPROVAL
    assert agent.workspace_files(task.id) == ()
    assert _actions(activity_log, run_id) == ["run_planned"]


def test_a_plan_without_a_success_criterion_is_refused(
    agent: AgentService, task: TaskView
) -> None:
    """"How would we know it worked" is not an optional field.

    A plan with no criterion is a plan that can be declared successful
    afterwards on whatever grounds are convenient, which is the failure the
    whole recording exercise exists to prevent.
    """
    with pytest.raises(RunError) as caught:
        agent.plan_run(
            task.id,
            steps=[("read_run_status", {})],
            expected_artifacts=[],
            test_condition="   ",
        )

    assert caught.value.reason == "plan_has_no_test_condition"


def test_a_plan_can_only_be_recorded_for_a_task_awaiting_approval(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    tasks.transition(task.id, TaskState.BLOCKED, detail="TEST-ONLY")

    with pytest.raises(RunError) as caught:
        write_plan(agent, task.id)

    assert caught.value.reason == "task_not_awaiting_approval"


def test_an_unregistered_tool_is_refused_and_recorded_as_a_permission_denial(
    agent: AgentService, task: TaskView, tasks: TaskService, activity_log: ActivityLog
) -> None:
    """ADR-0008 7: recorded, and the task is **not** re-pointed somewhere else.

    An agent that answered "I cannot do that, so I will do this other thing
    instead" would be choosing its own objective. The refusal is an event;
    the task stays exactly where it was.

    This test used to plant ``run_shell_command`` here. It cannot any more,
    and the reason is a repair rather than a rename: a name that reads as a
    command now earns ``execution_unavailable`` - the measured reason, with
    the isolation inventory's sentence - instead of being folded into
    "unknown tool". ``test_agent_activity.py`` drives that half. What is left
    here is the half this test was actually about: an identifier that is
    simply not in the registry.
    """
    with pytest.raises(ToolRegistryError) as caught:
        agent.plan_run(
            task.id,
            steps=[("read_mailbox", {"folder": "inbox"})],
            expected_artifacts=[],
            test_condition=TEST_ONLY_CONDITION,
        )

    assert caught.value.reason == "tool_unknown"
    assert "permission_denied" in _actions(activity_log)
    assert tasks.get(task.id).state is TaskState.AWAITING_APPROVAL
    assert agent.list_runs(task.id) == ()


def test_a_refused_command_leaves_the_task_exactly_where_it_was(
    agent: AgentService, task: TaskView, tasks: TaskService, activity_log: ActivityLog
) -> None:
    """The same ADR-0008 7 property, on the other refusal.

    A different reason must not mean a different amount of damage: nothing is
    recorded as a run, nothing moves, and the workspace stays empty.
    """
    with pytest.raises(ToolRegistryError) as caught:
        agent.plan_run(
            task.id,
            steps=[("execute_python", {"code": "TEST-ONLY"})],
            expected_artifacts=[],
            test_condition=TEST_ONLY_CONDITION,
        )

    assert caught.value.reason == "execution_unavailable"
    assert _actions(activity_log) == ["execution_unavailable"]
    assert tasks.get(task.id).state is TaskState.AWAITING_APPROVAL
    assert agent.list_runs(task.id) == ()
    assert agent.workspace_files(task.id) == ()


def test_a_started_run_cannot_be_started_again(
    agent: AgentService, task: TaskView
) -> None:
    """``start_run``'s phase check, driven.

    A review measured that deleting the check left the whole suite green -
    every test started each run exactly once, so the guard had never been
    asked a question. Starting twice is what a double-clicked button does,
    and the second call must be a refusal rather than a second pass over a
    plan whose steps have already run.
    """
    run_id = write_plan(agent, task.id)
    first = agent.start_run(run_id)

    assert first.phase is RunPhase.COMPLETED

    with pytest.raises(RunError) as caught:
        agent.start_run(run_id)

    assert caught.value.reason == "run_not_planned"
    assert agent.get_run(run_id).tool_calls_used == first.tool_calls_used


def test_a_planned_run_that_was_paused_cannot_be_started_either(
    agent: AgentService, task: TaskView
) -> None:
    """The same check from the other side: ``paused`` is resumed, never started.

    Two phases rather than one, because a check written as
    ``if view.finished`` would pass the test above and still let a paused run
    be restarted from the top.
    """
    run_id = write_plan(agent, task.id)
    agent.request_stop(run_id)
    paused = agent.start_run(run_id)

    assert paused.phase is RunPhase.PAUSED

    with pytest.raises(RunError) as caught:
        agent.start_run(run_id)

    assert caught.value.reason == "run_not_planned"


def test_a_plan_longer_than_the_tool_call_ceiling_is_refused(
    agent: AgentService, task: TaskView
) -> None:
    """The ceiling's **value**, driven behaviourally rather than compared to itself.

    ``test_agent_http`` asserts the published ceiling equals
    ``CEILING.max_tool_calls``, which checks the wiring and not the number: a
    review raised the ceiling to 9999 and the suite stayed green. Here the
    number decides an outcome. A plan of exactly ``max_tool_calls`` steps is
    accepted and runs to the end; one step more is refused, because a plan
    the ceiling could never let finish is a plan this product declines to
    record.

    The number is typed out rather than read from the constant under test:
    an oracle taken from ``CEILING`` proves only that the code agrees with
    itself, which is exactly how a ceiling of 9999 stayed invisible.
    """
    assert CEILING.max_tool_calls == EXPECTED_MAX_TOOL_CALLS

    at_the_ceiling = [("read_run_status", {})] * EXPECTED_MAX_TOOL_CALLS

    with pytest.raises(RunError) as caught:
        agent.plan_run(
            task.id,
            steps=[*at_the_ceiling, ("read_run_status", {})],
            expected_artifacts=[],
            test_condition=TEST_ONLY_CONDITION,
        )

    assert caught.value.reason == "plan_too_long"
    assert agent.list_runs(task.id) == ()

    # The refused plan first, because a completed run moves the task out of
    # ``awaiting_approval`` and the next refusal would then be about the
    # task's state rather than about the plan's length.
    view = agent.plan_run(
        task.id,
        steps=at_the_ceiling,
        expected_artifacts=[],
        test_condition=TEST_ONLY_CONDITION,
    )
    finished = agent.start_run(view.id)

    assert finished.phase is RunPhase.COMPLETED
    assert finished.tool_calls_used == EXPECTED_MAX_TOOL_CALLS
    assert len(finished.steps) == EXPECTED_MAX_TOOL_CALLS


def test_an_out_of_scope_artifact_name_is_refused_and_recorded(
    agent: AgentService, task: TaskView, activity_log: ActivityLog
) -> None:
    from station_api.agent.errors import WorkspaceError

    with pytest.raises(WorkspaceError):
        agent.plan_run(
            task.id,
            steps=[("read_run_status", {})],
            expected_artifacts=["../escape.txt"],
            test_condition=TEST_ONLY_CONDITION,
        )

    assert "permission_denied" in _actions(activity_log)


def test_a_bad_argument_is_refused_while_planning_not_half_way_through(
    agent: AgentService, task: TaskView
) -> None:
    """Validation at plan time is what makes the recorded plan meaningful.

    A plan that records a step nobody checked is a plan that can fail at step
    seven for a reason that was visible at step zero.
    """
    with pytest.raises(ToolArgumentError):
        agent.plan_run(
            task.id,
            steps=[("verify_file_digest", {"name": "a.json", "digest": "nope"})],
            expected_artifacts=[],
            test_condition=TEST_ONLY_CONDITION,
        )


# ---------------------------------------------------------------------------
# The plan is frozen
# ---------------------------------------------------------------------------


def test_an_edited_plan_is_refused_rather_than_carried_out(
    agent: AgentService, task: TaskView, engine: Engine
) -> None:
    """The success criterion cannot be loosened after the fact.

    The row is edited underneath the run - the strongest form of the attack,
    since it bypasses every route - and the run refuses to start because the
    recomputed digest no longer matches the one recorded at plan time.
    """
    run_id = write_plan(agent, task.id)

    with Session(engine) as session, session.begin():
        row = session.get(AgentRun, run_id)
        assert row is not None
        row.test_condition = "TEST-ONLY gevsetilmis olcut"

    with pytest.raises(RunError) as caught:
        agent.start_run(run_id)

    assert caught.value.reason == "plan_changed"
    assert agent.get_run(run_id).phase is RunPhase.PLANNED


def test_edited_step_arguments_are_refused_at_the_call(
    agent: AgentService, task: TaskView, engine: Engine, tasks: TaskService
) -> None:
    """The second half: the digest is re-derived per step, not once per run."""
    run_id = write_plan(agent, task.id)

    with Session(engine) as session, session.begin():
        row = session.scalars(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == run_id)
            .where(AgentRunStep.ordinal == 1)
        ).one()
        row.arguments_json = json.dumps({"name": "baska.json", "body": "TEST-ONLY"})

    agent.start_run(run_id)
    view = agent.get_run(run_id)

    assert view.phase is RunPhase.TOOL_ERROR
    assert view.steps[0].phase is StepPhase.REFUSED
    assert "baska.json" not in {item.name for item in agent.workspace_files(task.id)}
    assert tasks.get(task.id).state is TaskState.BLOCKED


def test_replanning_opens_a_new_run_and_leaves_the_old_digest_alone(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    """There is no plan edit. A different plan is a different run.

    So an old run keeps the criterion it was actually judged against, and a
    reviewer comparing two runs is comparing two records rather than one
    record that changed.
    """
    first = agent.get_run(write_plan(agent, task.id))
    second = agent.get_run(
        agent.plan_run(
            task.id,
            steps=[("read_run_status", {})],
            expected_artifacts=[],
            test_condition="TEST-ONLY ikinci olcut",
        ).id
    )

    assert first.id != second.id
    assert first.plan_sha256 != second.plan_sha256
    assert agent.get_run(first.id).test_condition == TEST_ONLY_CONDITION
    assert tasks.get(task.id).state is TaskState.AWAITING_APPROVAL


# ---------------------------------------------------------------------------
# A successful run
# ---------------------------------------------------------------------------


def test_a_finished_run_produces_files_and_still_cannot_be_published(
    agent: AgentService, task: TaskView, tasks: TaskService, activity_log: ActivityLog
) -> None:
    """The single most important assertion in this package.

    Files were produced, a deterministic checker ran and reported, the run
    completed - and the task is in ``review_needed``, not
    ``ready_to_publish``, because no ``test_result`` evidence exists and none
    can. Code that was never run is not code that was tested.
    """
    run_id = write_plan(agent, task.id)
    view = agent.start_run(run_id)

    assert view.phase is RunPhase.COMPLETED
    assert [step.phase for step in view.steps] == [StepPhase.RAN] * 2
    assert view.test_result_state == TEST_RESULT_STATE == "not_implemented"
    assert {item.name for item in agent.workspace_files(task.id)} == {"rapor.json"}

    after = tasks.get(task.id)
    assert after.state is TaskState.REVIEW_NEEDED

    gate = tasks.gate(task.id)
    assert gate.ready_to_publish is False
    assert "test_result" in gate.blocking_fields

    with pytest.raises(TaskError) as caught:
        tasks.transition(task.id, TaskState.READY_TO_PUBLISH)
    assert caught.value.reason == "evidence_incomplete"


def test_the_runner_records_the_output_it_produced_and_no_test_result(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    """``task_outcome`` is written from what exists; the other two are not.

    ``test_result`` would be a claim the build cannot support, and
    ``user_acceptance`` is a person's act that no automatic path may fill.
    """
    agent.start_run(write_plan(agent, task.id))
    fields = {ref.field for ref in tasks.get(task.id).refs}

    assert fields == {EvidenceField.TASK_OUTCOME}
    assert EvidenceField.TEST_RESULT not in fields
    assert EvidenceField.USER_ACCEPTANCE not in fields


def test_the_timeline_separates_planning_running_producing_and_awaiting(
    agent: AgentService, task: TaskView, activity_log: ActivityLog
) -> None:
    """ADR-0008 6: five kinds of moment, five actions, never one ``step_done``."""
    run_id = write_plan(agent, task.id)
    agent.start_run(run_id)

    actions = set(_actions(activity_log, run_id))

    assert {
        "run_planned",
        "run_started",
        "tool_called",
        "artifact_produced",
        "check_recorded",
        "run_finished",
        "approval_awaited",
    } <= actions


def test_the_approval_event_is_pending_rather_than_ok(
    agent: AgentService, task: TaskView, activity_log: ActivityLog
) -> None:
    """"Awaiting approval" is not a success. The outcome column says so."""
    run_id = write_plan(agent, task.id)
    agent.start_run(run_id)

    awaiting = [
        view
        for view in activity_log.list_events(run_id=run_id)
        if view.action is ActivityAction.APPROVAL_AWAITED
    ]

    assert awaiting
    assert all(view.outcome is ActivityOutcome.PENDING for view in awaiting)


# ---------------------------------------------------------------------------
# The four endings
# ---------------------------------------------------------------------------


def test_a_promised_artifact_that_was_not_produced_is_not_a_success(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    """The reason the promise is written down before the run.

    Every step ran without error and the run still did not succeed, because
    the plan said a file would exist and it does not. Without the recorded
    promise this run would have been indistinguishable from the one above.
    """
    run_id = agent.plan_run(
        task.id,
        steps=[("read_run_status", {})],
        expected_artifacts=["soz-verilen.md"],
        test_condition=TEST_ONLY_CONDITION,
    ).id
    view = agent.start_run(run_id)

    assert view.phase is RunPhase.ARTIFACT_MISSING
    assert "soz-verilen.md" in view.detail
    assert tasks.get(task.id).state is TaskState.BLOCKED


def test_the_ceiling_ends_a_run_with_its_own_phase_and_audit_event(
    agent: AgentService,
    task: TaskView,
    tasks: TaskService,
    activity_log: ActivityLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Budget exhaustion is not "failed". It is its own ending.

    Driven with a one-call ceiling, because the product's own ceiling is
    larger than the longest plan it accepts - which is deliberate, and would
    otherwise leave this path unexecuted.
    """
    monkeypatch.setattr(
        budget_module,
        "CEILING",
        RunCeiling(max_tool_calls=1, max_wall_clock_seconds=120, max_concurrency=1),
    )
    run_id = write_plan(agent, task.id)
    view = agent.start_run(run_id)

    assert view.phase is RunPhase.BUDGET_EXHAUSTED
    assert view.steps[0].phase is StepPhase.RAN
    assert view.steps[1].phase is StepPhase.PLANNED
    assert tasks.get(task.id).state is TaskState.BLOCKED
    assert "budget_exhausted" in _actions(activity_log, run_id)


def test_a_tool_failure_is_a_different_ending_from_the_ceiling(
    agent: AgentService, task: TaskView, tasks: TaskService
) -> None:
    run_id = agent.plan_run(
        task.id,
        steps=[("read_workspace_file", {"name": "yok.md"})],
        expected_artifacts=[],
        test_condition=TEST_ONLY_CONDITION,
    ).id
    view = agent.start_run(run_id)

    assert view.phase is RunPhase.TOOL_ERROR
    assert view.phase is not RunPhase.BUDGET_EXHAUSTED
    assert tasks.get(task.id).state is TaskState.BLOCKED


def test_a_stop_blocks_the_next_tool_call(
    agent: AgentService, task: TaskView, tasks: TaskService, activity_log: ActivityLog
) -> None:
    """Stop is a flag the runner reads before every call, not an interruption.

    There is nothing to interrupt: one call at a time, synchronously. What
    "stop" means is exactly that the next one does not happen.
    """
    run_id = write_plan(agent, task.id)
    agent.request_stop(run_id)
    view = agent.start_run(run_id)

    assert view.phase is RunPhase.PAUSED
    assert [step.phase for step in view.steps] == [StepPhase.PLANNED] * 2
    assert agent.workspace_files(task.id) == ()
    assert tasks.get(task.id).state is TaskState.PAUSED
    assert "run_stopped" in _actions(activity_log, run_id)


def test_a_result_arriving_after_a_stop_leaves_nothing_behind(
    agent: AgentService, task: TaskView, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The late-reply rule, driven rather than described.

    A tool that sets the stop flag *while it runs* stands in for the reply
    that arrives after cancellation. Its result is not recorded and the file
    it wrote is removed, so a cancelled run has no side effect a user would
    later find and mistake for output.
    """
    run_id = write_plan(agent, task.id)
    real_call = AgentService._call

    def _stopping_call(self, record, arguments, task_view, directory):  # type: ignore[no-untyped-def]
        outcome = real_call(self, record, arguments, task_view, directory)
        self.request_stop(run_id)
        return outcome

    monkeypatch.setattr(AgentService, "_call", _stopping_call)
    view = agent.start_run(run_id)

    assert view.phase is RunPhase.PAUSED
    assert view.steps[0].phase is StepPhase.SKIPPED
    assert agent.workspace_files(task.id) == ()
    assert "kaldirildi" in view.steps[0].detail


def test_a_stopped_run_continues_only_because_a_person_asked(
    agent: AgentService, task: TaskView, tasks: TaskService, activity_log: ActivityLog
) -> None:
    run_id = write_plan(agent, task.id)
    agent.request_stop(run_id)
    agent.start_run(run_id)

    resumed = agent.resume_run(run_id)

    assert resumed.phase is RunPhase.COMPLETED
    assert "run_resumed" in _actions(activity_log, run_id)
    assert tasks.get(task.id).state is TaskState.REVIEW_NEEDED


def test_a_finished_run_cannot_be_stopped_or_resumed(
    agent: AgentService, task: TaskView
) -> None:
    run_id = write_plan(agent, task.id)
    agent.start_run(run_id)

    with pytest.raises(RunError) as stop:
        agent.request_stop(run_id)
    assert stop.value.reason == "run_finished"

    with pytest.raises(RunError) as resume:
        agent.resume_run(run_id)
    assert resume.value.reason == "run_not_paused"


# ---------------------------------------------------------------------------
# Restart
# ---------------------------------------------------------------------------


def test_a_run_interrupted_by_a_restart_is_listed_and_never_resumed(
    agent: AgentService, task: TaskView, engine: Engine, tasks: TaskService
) -> None:
    """SI-224, carried into H2.

    A crash leaves a row in ``running``. The plan can be loaded and looked at;
    nothing continues, and continuing is a person's act. There is no startup
    hook that calls ``resume_run`` - ``create_app`` never touches this
    service beyond constructing it.
    """
    run_id = write_plan(agent, task.id)
    with Session(engine) as session, session.begin():
        row = session.get(AgentRun, run_id)
        assert row is not None
        row.phase = RunPhase.RUNNING.value

    interrupted = agent.interrupted_runs()

    assert [view.id for view in interrupted] == [run_id]
    assert interrupted[0].test_condition == TEST_ONLY_CONDITION
    # Listing it changed nothing: still running, still no files, task untouched.
    assert agent.get_run(run_id).phase is RunPhase.RUNNING
    assert agent.workspace_files(task.id) == ()
    assert tasks.get(task.id).state is TaskState.AWAITING_APPROVAL


def test_creating_the_application_starts_no_run(
    engine: Engine, settings, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """Building the service contacts nobody and runs nothing.

    Asserted by counting rows rather than by reading the constructor: a future
    constructor that scheduled something would pass a source review and fail
    here.
    """
    from station_api.app import create_app

    from tests.conftest import TEST_PORT

    application = create_app(
        settings=settings, port=TEST_PORT, engine=engine, web_dist=None
    )
    service: AgentService = application.state.agent

    assert service is not None
    with Session(engine) as session:
        assert session.scalars(select(AgentRun)).all() == []
    assert service.activity.count() == 0


# ---------------------------------------------------------------------------
# The workspace is the run's only output surface
# ---------------------------------------------------------------------------


def test_a_run_writes_only_inside_its_own_task_workspace(
    agent: AgentService, task: TaskView, data_dir  # type: ignore[no-untyped-def]
) -> None:
    run_id = write_plan(agent, task.id)
    agent.start_run(run_id)

    from station_api.agent.workspace import task_workspace

    directory = task_workspace(data_dir, task.id)
    produced = {item.name for item in list_files(directory)}

    assert produced == {"rapor.json"}
    # And nothing was dropped beside the workspace root.
    from station_api.agent.workspace import workspace_root

    strays = [
        path.name
        for path in workspace_root(data_dir).iterdir()
        if path.is_file()
    ]
    assert strays == []
