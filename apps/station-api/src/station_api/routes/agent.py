"""Task and Activity Desk endpoints. The surface Package F deliberately withheld.

    GET  /api/tasks                                  the tasks, bounded
    GET  /api/tasks/surface                          tools, ceiling, isolation
    GET  /api/tasks/{task_id}                        one task, four fields apart
    POST /api/tasks/{task_id}/transition             a user-driven state change
    POST /api/tasks/{task_id}/publish-readiness      re-derive it from evidence
    GET  /api/tasks/{task_id}/runs                   runs and workspace files
    POST /api/tasks/{task_id}/runs                   record a plan; runs nothing
    POST /api/tasks/{task_id}/runs/{run_id}/start    carry the recorded plan out
    POST /api/tasks/{task_id}/runs/{run_id}/stop     block the next tool call
    POST /api/tasks/{task_id}/runs/{run_id}/resume   continue, in the same scope
    GET  /api/activity                               the timeline, newest first
    POST /api/activity/delete                        remove rows; recorded as an event

Package F wrote "the task layer has no routes in this release - the tasks
section stays closed (ADR-0004 9)". H2 opens them, and the shape of what is
opened is where the care went.

What is deliberately absent
---------------------------
* **No route that runs a command.** There is no endpoint here, and no
  parameter on any endpoint here, that reaches a shell, a process or an
  interpreter. ``execution_unavailable`` is reported by
  ``GET /api/tasks/surface`` as a reason with a sentence rather than being an
  absence a user has to infer from a missing button (ADR-0008 1).
* **No route that records evidence.** ``task_outcome`` is written by the
  runner from what it actually produced; ``test_result`` is written by
  nothing, which is why a finished run leaves a task in ``review_needed``;
  ``user_acceptance`` is a person's act and belongs to the surface that asks
  for it, not to a POST body that could assert it. An endpoint that let a
  caller set a field to ``verified`` would undo the entire evidence model.
* **No transition to ``running`` or ``paused``.**
  :data:`~station_api.schemas.TaskUserTransitionName` omits both. They are
  reached through the run routes, which record a plan, its promised artifacts
  and its success criterion **before** anything executes. A direct transition
  would be a way into the executing state with no plan written down.
* **No plan edit.** A recorded plan is frozen: re-planning opens a *new* run
  and the old one keeps its digest, so a success criterion cannot be loosened
  after the fact and then reported as met (ADR-0008 7).
* **No timer, no background task, no long poll.** Every outbound-shaped verb
  here is local; a run happens inside the request that asked for it, and a
  restart resumes nothing on its own (SI-224, SI-272).
* **No path parameter anywhere.** A workspace file is addressed by a bare
  name that goes through the download sanitiser and a containment check; no
  request can name a directory, a drive or a traversal segment.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel

from station_api.agent import budget, isolation
from station_api.agent.acceptance import (
    ACCEPTANCE_CHECKS,
    AcceptanceCheck,
    AcceptanceKind,
    AcceptanceState,
)
from station_api.agent.activity import RETAINED_EVENTS, ActivityLog, ActivityView
from station_api.agent.errors import (
    ActivityError,
    AgentError,
    RunError,
    ToolArgumentError,
    ToolRegistryError,
    WorkspaceError,
)
from station_api.agent.language import RUN_HONESTY_SENTENCE, STOP_HONESTY_SENTENCE
from station_api.agent.service import AgentService, RunView
from station_api.agent.tools import TOOLS, ToolRecord, ToolScope
from station_api.agent.workspace import WorkspaceFile
from station_api.dependencies import require_session
from station_api.schemas import (
    ActivityDeleteRequest,
    ActivityDeleteResponse,
    ActivityEventStatus,
    ActivityListResponse,
    AgentAcceptanceCheckStatus,
    AgentAcceptanceConditionStatus,
    AgentAcceptanceKindName,
    AgentCeilingStatus,
    AgentExecutionStatus,
    AgentIsolationFindingStatus,
    AgentPlanRequest,
    AgentRunStatus,
    AgentRunStepStatus,
    AgentSurfaceResponse,
    AgentTaskRunsResponse,
    AgentTestResultStateName,
    AgentToolParamStatus,
    AgentToolScopeName,
    AgentToolStatus,
    AgentWorkspaceFileStatus,
    TaskListResponse,
    TaskPublishReadinessRequest,
    TaskStatusResponse,
    TaskTransitionRequest,
)
from station_api.security.sessions import Session
from station_api.tasks.service import TaskError, TaskService
from station_api.tasks.states import TaskState
from station_api.tasks.views import to_task_list, to_task_status

router = APIRouter(prefix="/api")

CurrentSession = Annotated[Session, Depends(require_session)]

#: Run and task state is local, momentary and never belongs in a cache.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

#: Which refusal reason gets which status code. A closed mapping rather than
#: a guess per raise site, so two refusals of the same kind cannot answer
#: differently depending on which function raised them.
_CONFLICT_REASONS = frozenset(
    {
        "task_not_awaiting_approval",
        "run_not_planned",
        "run_not_paused",
        "run_finished",
        "plan_changed",
        "plan_arguments_changed",
        "state_not_producible",
        "transition_not_allowed",
        "terminal_state",
        "no_transition",
        "evidence_incomplete",
    }
)

_MISSING_REASONS = frozenset({"run_missing", "task_missing"})


def _refuse(exc: AgentError | TaskError) -> HTTPException:
    """One refusal, one status code, one sentence the user can read."""
    if exc.reason in _MISSING_REASONS:
        code = status.HTTP_404_NOT_FOUND
    elif exc.reason in _CONFLICT_REASONS:
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=str(exc), headers=_NO_STORE)


def _tasks(request: Request) -> TaskService:
    service: TaskService | None = getattr(request.app.state, "tasks", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gorev yuzeyi kullanilabilir degil.",
            headers=_NO_STORE,
        )
    return service


def _agent(request: Request) -> AgentService:
    service: AgentService | None = getattr(request.app.state, "agent", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent calisma ortami kullanilabilir degil.",
            headers=_NO_STORE,
        )
    return service


def _activity(request: Request) -> ActivityLog:
    return _agent(request).activity


def _json(model: BaseModel) -> Response:
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


#: The registry's scopes, spelled as the wire literals. A mapping rather than
#: ``scope.value`` with a cast: a scope added to the enum without a name here
#: is a type error at build time, which is the point of typing the field as a
#: closed literal in the first place.
_SCOPE_NAMES: dict[ToolScope, AgentToolScopeName] = {
    ToolScope.READ_APPROVED_INPUT: "read_approved_input",
    ToolScope.WRITE_WORKSPACE: "write_workspace",
    ToolScope.DETERMINISTIC_CHECK: "deterministic_check",
    ToolScope.READ_RUN_STATE: "read_run_state",
}


def _tool(record: ToolRecord) -> AgentToolStatus:
    return AgentToolStatus(
        id=record.id.value,
        scope=_SCOPE_NAMES[record.scope],
        purpose=record.purpose,
        params=[
            AgentToolParamStatus(
                name=param.name,
                type=param.type.value,
                required=param.required,
                detail=param.detail,
            )
            for param in record.params
        ],
        call_cost=record.call_cost,
        produces_artifact=record.produces_artifact,
    )


#: The acceptance registry's kinds and its three verdicts, spelled as the
#: wire literals. Mappings rather than ``.value`` with a cast, for
#: :data:`_SCOPE_NAMES`'s reason: a member added to either enum without a name
#: here is a type error at build time, which is the point of typing the fields
#: as closed literals in the first place.
_ACCEPTANCE_KIND_NAMES: dict[AcceptanceKind, AgentAcceptanceKindName] = {
    AcceptanceKind.ARTIFACT_EXISTS: "artifact_exists",
    AcceptanceKind.ARTIFACT_IS_JSON: "artifact_is_json",
    AcceptanceKind.ARTIFACT_HAS_JSON_KEYS: "artifact_has_json_keys",
    AcceptanceKind.ARTIFACT_CONTAINS: "artifact_contains",
    AcceptanceKind.ARTIFACT_DIGEST_IS: "artifact_digest_is",
}

_TEST_RESULT_NAMES: dict[AcceptanceState, AgentTestResultStateName] = {
    AcceptanceState.PASSED: "passed",
    AcceptanceState.FAILED: "failed",
    AcceptanceState.NOT_IMPLEMENTED: "not_implemented",
}


def _acceptance_check(record: AcceptanceCheck) -> AgentAcceptanceCheckStatus:
    return AgentAcceptanceCheckStatus(
        kind=_ACCEPTANCE_KIND_NAMES[record.kind],
        purpose=record.purpose,
        params=[
            AgentToolParamStatus(
                name=param.name,
                type=param.type.value,
                required=param.required,
                detail=param.detail,
            )
            for param in record.params
        ],
    )


def _ceiling() -> AgentCeilingStatus:
    return AgentCeilingStatus(
        max_tool_calls=budget.CEILING.max_tool_calls,
        max_wall_clock_seconds=budget.CEILING.max_wall_clock_seconds,
        units=list(budget.BUDGET_UNITS),
        refused_units=list(budget.REFUSED_UNITS),
        refused_units_detail=budget.REFUSED_UNITS_DETAIL,
        detail=budget.describe_ceiling(),
    )


def _execution() -> AgentExecutionStatus:
    """The isolation surface, taken from the module rather than restated here.

    ``arbitrary_execution_supported`` is passed explicitly, from
    :data:`~station_api.agent.isolation.ARBITRARY_EXECUTION_SUPPORTED`, even
    though the field's default is the same value. Leaving it to the default
    is what made the wire a *second* hard-coded ``False`` with no link to the
    module - two claims about one fact, either of which could have been
    edited alone.
    """
    verdict = isolation.execution_verdict()
    return AgentExecutionStatus(
        arbitrary_execution_supported=isolation.ARBITRARY_EXECUTION_SUPPORTED,
        reason=isolation.EXECUTION_UNAVAILABLE_REASON,
        detail=verdict.detail,
        inventory=[
            AgentIsolationFindingStatus(
                facility=finding.facility.value,
                measured=finding.measured.value,
                measured_at=finding.measured_at,
                detail=finding.detail,
            )
            for finding in isolation.ISOLATION_INVENTORY
        ],
    )


def run_status(view: RunView) -> AgentRunStatus:
    """One run, projected onto the wire.

    Public rather than private since Package H4, because
    ``routes/planner.py`` returns the same runs after a model turn and a
    second projection is a second place for the two to disagree about what a
    run looks like - which is the duplication ADR-0004 2 named.
    """
    return AgentRunStatus(
        id=view.id,
        task_id=view.task_id,
        phase=view.phase.value,
        created_at=view.created_at,
        started_at=view.started_at,
        finished_at=view.finished_at,
        stop_requested=view.stop_requested,
        plan_sha256=view.plan_sha256,
        test_condition=view.test_condition,
        acceptance=[
            AgentAcceptanceConditionStatus(
                kind=_ACCEPTANCE_KIND_NAMES[result.kind],
                label=result.label,
                satisfied=result.satisfied,
                detail=result.detail,
            )
            for result in view.test_result.results
        ],
        test_result_state=_TEST_RESULT_NAMES[view.test_result.state],
        test_result_detail=view.test_result_detail,
        expected_artifacts=list(view.expected_artifacts),
        steps=[
            AgentRunStepStatus(
                ordinal=step.ordinal,
                tool_id=step.tool_id,
                scope=_SCOPE_NAMES[ToolScope(step.scope)],
                arguments_sha256=step.arguments_sha256,
                phase=step.phase.value,
                started_at=step.started_at,
                finished_at=step.finished_at,
                artifact_name=step.artifact_name,
                artifact_sha256=step.artifact_sha256,
                detail=step.detail,
            )
            for step in view.steps
        ],
        tool_calls_used=view.tool_calls_used,
        elapsed_ms=view.elapsed_ms,
        max_tool_calls=view.max_tool_calls,
        max_wall_clock_seconds=view.max_wall_clock_seconds,
        detail=view.detail,
    )


def _file(item: WorkspaceFile) -> AgentWorkspaceFileStatus:
    return AgentWorkspaceFileStatus(
        name=item.name, byte_count=item.byte_count, sha256=item.sha256
    )


def _event(view: ActivityView) -> ActivityEventStatus:
    return ActivityEventStatus(
        id=view.id,
        recorded_at=view.recorded_at,
        run_id=view.run_id,
        task_id=view.task_id,
        actor=view.actor.value,
        action=view.action.value,
        outcome=view.outcome.value,
        duration_ms=view.duration_ms,
        artifact_sha256=view.artifact_sha256,
        check_sha256=view.check_sha256,
        detail=view.detail,
        chain_referenced=view.chain_referenced,
    )


def _task_status(tasks: TaskService, task_id: str) -> TaskStatusResponse:
    return to_task_status(tasks.get(task_id), tasks.gate(task_id))


def _task_runs(
    tasks: TaskService, agent: AgentService, task_id: str
) -> AgentTaskRunsResponse:
    return AgentTaskRunsResponse(
        task=_task_status(tasks, task_id),
        runs=[run_status(view) for view in agent.list_runs(task_id)],
        workspace_files=[_file(item) for item in agent.workspace_files(task_id)],
        honesty=RUN_HONESTY_SENTENCE,
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(request: Request, session: CurrentSession) -> Response:
    """The tasks, newest first, bounded. Contacts nobody and runs nothing."""
    del session
    service = _tasks(request)
    views = service.list_tasks()
    return _json(to_task_list([(view, service.gate(view.id)) for view in views]))


@router.get("/tasks/surface", response_model=AgentSurfaceResponse)
async def read_surface(request: Request, session: CurrentSession) -> Response:
    """The agent surface as it is: what runs, what does not, and why.

    Declared **before** ``/tasks/{task_id}`` so the literal path wins. Route
    order is the only thing that separates them, and a task id is a 32-hex
    string that could never be the word ``surface`` anyway - both, because
    relying on either one alone is how a static path quietly becomes
    unreachable.
    """
    del session
    agent = _agent(request)
    return _json(
        AgentSurfaceResponse(
            execution=_execution(),
            ceiling=_ceiling(),
            tools=[_tool(record) for record in TOOLS],
            acceptance_checks=[
                _acceptance_check(record) for record in ACCEPTANCE_CHECKS
            ],
            honesty=RUN_HONESTY_SENTENCE,
            stop_statement=STOP_HONESTY_SENTENCE,
            interrupted_runs=[run_status(view) for view in agent.interrupted_runs()],
        )
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def read_task(
    request: Request, session: CurrentSession, task_id: str
) -> Response:
    """One task, with its four evidence fields reported separately."""
    del session
    service = _tasks(request)
    try:
        return _json(_task_status(service, task_id))
    except TaskError as exc:
        raise _refuse(exc) from exc


@router.post("/tasks/{task_id}/transition", response_model=TaskStatusResponse)
def move_task(
    request: Request,
    session: CurrentSession,
    task_id: str,
    body: TaskTransitionRequest,
) -> Response:
    """Move a task the way a person may move it.

    The target is typed as :data:`TaskUserTransitionName`, which omits
    ``running`` and ``paused`` (the runner's) and ``ready_to_publish``
    (derived from evidence, never asked for). A value outside that set is a
    422 from the model, before this function is entered.
    """
    del session
    service = _tasks(request)
    try:
        service.transition(
            task_id, TaskState(body.target), detail=body.detail
        )
        return _json(_task_status(service, task_id))
    except TaskError as exc:
        raise _refuse(exc) from exc


@router.post("/tasks/{task_id}/publish-readiness", response_model=TaskStatusResponse)
def derive_publish_readiness(
    request: Request,
    session: CurrentSession,
    task_id: str,
    body: TaskPublishReadinessRequest,
) -> Response:
    """Re-derive whether this task is ready to publish, and move it if it is.

    The route that finally makes ``ready_to_publish`` reachable, and it is a
    **separate** route rather than a new value on the transition literal on
    purpose. SI-222's rule is that the state is derived from evidence and
    cannot be asked for; :data:`~station_api.schemas.TaskUserTransitionName`
    still omits it, so no request in this product can name it, and
    :class:`~station_api.schemas.TaskPublishReadinessRequest` carries no
    target field to name it with.

    What the caller is asking for is a re-reading of three fields that three
    different acts filled: ``task_outcome`` from what the runner produced,
    ``test_result`` from the plan's own acceptance conditions decided over
    those bytes, and ``user_acceptance`` from a person (ADR-0009 8). If any
    of them is missing, unverified, or bound to a superseded output, the gate
    refuses and the refusal names them - and it refuses in
    :meth:`~station_api.tasks.service.TaskService.transition`, which is the
    only function in this product that writes a task state, so this route
    cannot be the second one.
    """
    del session
    service = _tasks(request)
    try:
        status_before = service.gate(task_id)
        if not status_before.ready_to_publish:
            raise TaskError(
                "Gorev yayima hazir degil; su alanlar dogrulanmis degil: "
                + ", ".join(status_before.blocking_fields)
                + ". Bu durum istenerek degil kanittan turer.",
                reason="evidence_incomplete",
            )
        service.transition(
            task_id,
            TaskState.READY_TO_PUBLISH,
            detail=body.detail
            or (
                "Uc kanit alani ayri ayri dogrulandi; durum kanittan "
                "turetildi."
            ),
        )
        return _json(_task_status(service, task_id))
    except TaskError as exc:
        raise _refuse(exc) from exc


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/runs", response_model=AgentTaskRunsResponse)
def read_runs(request: Request, session: CurrentSession, task_id: str) -> Response:
    """One task's runs and what its workspace holds. Reads the filesystem.

    Blocking, and therefore ``def``: reading and digesting a directory on the
    event loop would stall every other request.
    """
    del session
    tasks = _tasks(request)
    agent = _agent(request)
    try:
        return _json(_task_runs(tasks, agent, task_id))
    except (TaskError, AgentError) as exc:
        raise _refuse(exc) from exc


@router.post("/tasks/{task_id}/runs", response_model=AgentTaskRunsResponse)
def plan_run(
    request: Request, session: CurrentSession, task_id: str, body: AgentPlanRequest
) -> Response:
    """Record a plan. **Runs nothing**: starting is a separate request.

    Two decisions rather than one is the same shape the composer uses for
    signing and sending (ADR-0002 2): a person approves *what will be done*
    and then, separately, that it be done.
    """
    del session
    tasks = _tasks(request)
    agent = _agent(request)
    try:
        agent.plan_run(
            task_id,
            steps=[(step.tool_id, dict(step.arguments)) for step in body.steps],
            expected_artifacts=body.expected_artifacts,
            test_condition=body.test_condition,
            acceptance_conditions=[
                (condition.kind, dict(condition.arguments))
                for condition in body.acceptance
            ],
        )
        return _json(_task_runs(tasks, agent, task_id))
    except (ToolRegistryError, ToolArgumentError, WorkspaceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    except (TaskError, AgentError) as exc:
        raise _refuse(exc) from exc


@router.post(
    "/tasks/{task_id}/runs/{run_id}/start", response_model=AgentTaskRunsResponse
)
def start_run(
    request: Request, session: CurrentSession, task_id: str, run_id: str
) -> Response:
    """Carry the recorded plan out, here, inside this request.

    Blocking and synchronous on purpose. A background task would need a
    scheduler, and there is none in this product (SI-272); it would also make
    "stop blocks the next tool call" a statement about two processes rather
    than about one loop with a flag in it.
    """
    del session
    tasks = _tasks(request)
    agent = _agent(request)
    _assert_run_belongs(agent, task_id, run_id)
    try:
        agent.start_run(run_id)
        return _json(_task_runs(tasks, agent, task_id))
    except (TaskError, AgentError) as exc:
        raise _refuse(exc) from exc


@router.post(
    "/tasks/{task_id}/runs/{run_id}/stop", response_model=AgentTaskRunsResponse
)
def stop_run(
    request: Request, session: CurrentSession, task_id: str, run_id: str
) -> Response:
    """Block the next tool call. A late result is discarded, not applied."""
    del session
    tasks = _tasks(request)
    agent = _agent(request)
    _assert_run_belongs(agent, task_id, run_id)
    try:
        agent.request_stop(run_id)
        return _json(_task_runs(tasks, agent, task_id))
    except (TaskError, AgentError) as exc:
        raise _refuse(exc) from exc


@router.post(
    "/tasks/{task_id}/runs/{run_id}/resume", response_model=AgentTaskRunsResponse
)
def resume_run(
    request: Request, session: CurrentSession, task_id: str, run_id: str
) -> Response:
    """Continue a paused run, within the scope already approved.

    The only way a paused or interrupted run continues. Nothing on startup
    calls it, so a restart loads the plan and stops there (SI-224).
    """
    del session
    tasks = _tasks(request)
    agent = _agent(request)
    _assert_run_belongs(agent, task_id, run_id)
    try:
        agent.resume_run(run_id)
        return _json(_task_runs(tasks, agent, task_id))
    except (TaskError, AgentError) as exc:
        raise _refuse(exc) from exc


def _assert_run_belongs(agent: AgentService, task_id: str, run_id: str) -> None:
    """A run id in the path must be a run of the task in the path.

    Without this, ``/api/tasks/<mine>/runs/<somebody-elses>/start`` would act
    on the second one and report the first. There is one user on this
    machine, so it is not a privilege boundary; it is the guard that keeps
    the response from describing a different object than the one that was
    acted on.
    """
    try:
        view = agent.get_run(run_id)
    except RunError as exc:
        raise _refuse(exc) from exc
    if view.task_id != task_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bu calisma bu goreve ait degil.",
            headers=_NO_STORE,
        )


# ---------------------------------------------------------------------------
# The Activity Desk
# ---------------------------------------------------------------------------


@router.get("/activity", response_model=ActivityListResponse)
async def read_activity(
    request: Request, session: CurrentSession, run_id: str = ""
) -> Response:
    """The timeline, newest first, bounded.

    ``run_id`` narrows the listing and is the only query parameter: it is
    matched for equality against a column and never becomes a path, a name or
    an address.
    """
    del session
    log = _activity(request)
    events = log.list_events(run_id=run_id[:32])
    return _json(
        ActivityListResponse(
            events=[_event(view) for view in events],
            event_count=log.count(),
            chain_referenced_count=log.count_chain_referenced(),
            retained_events=RETAINED_EVENTS,
            detail=(
                "Aktivite satirlari audit zincirinin halkasi degildir: "
                "silinmeleri hicbir MAC'i kirmaz. Zincirin atifta bulundugu "
                "satirlar ise ne budanir ne silinir."
            ),
        )
    )


@router.post("/activity/delete", response_model=ActivityDeleteResponse)
def delete_activity(
    request: Request, session: CurrentSession, body: ActivityDeleteRequest
) -> Response:
    """Remove timeline rows, and record that removal as an audit event.

    Chain-referenced rows are kept and counted separately. The two numbers
    are never summed: "twelve removed" and "three kept because the chain
    refers to them" answer different questions, and a single total would hide
    the one that explains why the timeline is not empty.
    """
    del session
    log = _activity(request)
    try:
        report = log.delete_events(run_id=body.run_id)
    except ActivityError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(
        ActivityDeleteResponse(
            deleted=report.deleted,
            kept_because_chain_referenced=report.kept_because_chain_referenced,
            detail=report.detail,
        )
    )


__all__ = ["router", "run_status"]
