"""58b5423 review reproductions. Temporary data, no provider or live writes."""

from pathlib import Path

import pytest
from sqlalchemy import Engine
from station_api.agent import workspace
from station_api.agent.activity import ActivityLog
from station_api.agent.service import AgentService, RunPhase
from station_api.identity.write_gate import CheckState
from station_api.modules.fields import EvidenceField
from station_api.proof.service import ProofService
from station_api.tasks.service import TaskService, TaskView
from station_api.tasks.states import TaskState

pytestmark = pytest.mark.security


@pytest.mark.parametrize("updating", [False, True])
def test_stop_restores_previous_bytes_and_resume_retries_discarded_step(
    agent: AgentService,
    task: TaskView,
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    updating: bool,
) -> None:
    root = workspace.ensure_workspace(data_dir, task.id)
    if updating:
        workspace.write_text(root, "report.txt", "TEST-ONLY ORIGINAL\r\n", replace_existing=False)
    run = agent.plan_run(
        task.id,
        steps=[
            (
                "update_workspace_file" if updating else "write_workspace_file",
                {"name": "report.txt", "body": "TEST-ONLY UPDATED"},
            )
        ],
        expected_artifacts=["report.txt"],
        test_condition="TEST-ONLY preserve bytes",
    )
    original = agent._call

    def stopped(*args):  # type: ignore[no-untyped-def]
        outcome = original(*args)
        agent.request_stop(run.id)
        return outcome

    monkeypatch.setattr(agent, "_call", stopped)
    assert agent.start_run(run.id).phase is RunPhase.PAUSED
    if updating:
        assert (root / "report.txt").read_bytes() == b"TEST-ONLY ORIGINAL\r\n"
    else:
        assert not (root / "report.txt").exists()
    monkeypatch.setattr(agent, "_call", original)
    assert agent.resume_run(run.id).phase is RunPhase.COMPLETED
    assert (root / "report.txt").read_bytes() == b"TEST-ONLY UPDATED"


def test_new_run_invalidates_previous_acceptance(
    agent: AgentService,
    task: TaskView,
    tasks: TaskService,
    proof: ProofService,
) -> None:
    for body in ("TEST-ONLY A", "TEST-ONLY B"):
        run = agent.plan_run(
            task.id,
            steps=[
                (
                    "write_workspace_file" if body.endswith("A") else "update_workspace_file",
                    {"name": "report.txt", "body": body},
                )
            ],
            expected_artifacts=["report.txt"],
            test_condition="TEST-ONLY revision",
        )
        agent.start_run(run.id)
        if body.endswith("A"):
            proof.record_acceptance(task.id, bundle_sha256=proof.build(task.id).sha256)
            assert tasks.gate(task.id).check_for(EvidenceField.USER_ACCEPTANCE).satisfied
            tasks.transition(task.id, TaskState.BLOCKED)
            tasks.transition(task.id, TaskState.AWAITING_APPROVAL)
    assert tasks.gate(task.id).check_for(EvidenceField.USER_ACCEPTANCE).state is CheckState.BLOCKED


def test_restart_before_first_tool_can_resume_only_on_user_request(
    agent: AgentService,
    task: TaskView,
    tasks: TaskService,
    engine: Engine,
    data_dir: Path,
    activity_log: ActivityLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = agent.plan_run(
        task.id,
        steps=[("write_workspace_file", {"name": "report.txt", "body": "TEST-ONLY"})],
        expected_artifacts=["report.txt"],
        test_condition="TEST-ONLY recovery",
    )

    def crash(_run_id: str) -> None:
        raise RuntimeError("TEST-ONLY simulated process loss")

    monkeypatch.setattr(agent, "_execute", crash)
    with pytest.raises(RuntimeError, match="TEST-ONLY"):
        agent.start_run(run.id)
    fresh = AgentService(engine=engine, data_dir=data_dir, tasks=tasks, activity=activity_log)
    assert [item.id for item in fresh.interrupted_runs()] == [run.id]
    assert fresh.workspace_files(task.id) == ()
    assert fresh.resume_run(run.id).phase is RunPhase.COMPLETED
    assert (
        workspace.read_text(workspace.task_workspace(data_dir, task.id), "report.txt")
        == "TEST-ONLY"
    )


def test_acceptance_is_stale_when_output_changes_outside_runner(
    agent: AgentService,
    task: TaskView,
    tasks: TaskService,
    proof: ProofService,
    data_dir: Path,
) -> None:
    run = agent.plan_run(
        task.id,
        steps=[("write_workspace_file", {"name": "report.txt", "body": "TEST-ONLY A"})],
        expected_artifacts=["report.txt"],
        test_condition="TEST-ONLY revision",
    )
    agent.start_run(run.id)
    proof.record_acceptance(task.id, bundle_sha256=proof.build(task.id).sha256)
    # Recording acceptance changes the bundle, but must not invalidate itself.
    assert tasks.gate(task.id).check_for(EvidenceField.USER_ACCEPTANCE).satisfied
    workspace.write_text(
        workspace.task_workspace(data_dir, task.id),
        "report.txt",
        "TEST-ONLY B",
        replace_existing=True,
    )
    assert not tasks.gate(task.id).check_for(EvidenceField.USER_ACCEPTANCE).satisfied
    assert not tasks.gate(task.id).check_for(EvidenceField.TASK_OUTCOME).satisfied
