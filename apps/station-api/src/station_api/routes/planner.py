"""The model planning endpoint. One turn per request, and it starts nothing.

    POST /api/tasks/{task_id}/model-plan          spend one turn; record a plan
    POST /api/tasks/{task_id}/model-plan/forget   drop the session and start over

Why this router is separate from ``routes/agent.py``
-----------------------------------------------------
Not tidiness. ``test_agent_boundary.py`` reads the syntax tree of every file
in ``station_api/agent`` **and of ``routes/agent.py``**, and refuses an import
of ``station_api.opencode`` in either - because a service that reaches the
network on a caller's behalf is an outbound surface with one function call in
the way. The model call has to be imported somewhere, so it is imported here,
in a file that is scanned by ``test_planner_boundary.py`` instead: same scans,
one deliberate and named exception, and the agent's own boundary stays exactly
where it was.

What this route cannot do
--------------------------
* **It cannot run anything.** The best outcome is ``planned``: a recorded plan
  in the ``planned`` phase, waiting for the start route a person invokes. This
  module does not import ``start_run``, does not call it and could not reach
  it; a test reads the syntax tree to say so, because "we just do not call it"
  is a property of today's code and not of the design.
* **It cannot choose a model, a prompt or a tool list.** The model comes from
  the stored selection, the tools are the whole compile-time registry and the
  system prompt is a constant. A request body that could set any of them would
  be a body that could widen what a proposal is allowed to be.
* **It cannot record evidence or move a task.** Neither ``test_result`` nor
  ``user_acceptance`` is reachable from here, and the only state write in this
  product is still ``TaskService.transition``.
* **It cannot schedule a second turn.** One turn per request, inside the
  request. There is no timer and no background task (SI-272).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel

from station_api.agent.errors import AgentError, RunError
from station_api.agent.service import AgentService
from station_api.dependencies import require_session
from station_api.opencode.errors import (
    ModelNotSelectableError,
    OpenCodeConfigurationError,
    OpenCodeError,
)
from station_api.opencode.planner import TOOL_CALL_PROVENANCE
from station_api.planner.service import ModelPlannerService, ProposalOutcome
from station_api.routes.agent import run_status
from station_api.schemas import (
    ModelProposalOutcomeName,
    ModelProposalResponse,
    ModelProposeRequest,
)
from station_api.security.sessions import Session
from station_api.tasks.service import TaskError, TaskService
from station_api.tasks.views import to_task_status

router = APIRouter(prefix="/api")

CurrentSession = Annotated[Session, Depends(require_session)]

_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

#: The outcomes, spelled as the wire literals. A mapping rather than
#: ``outcome.value`` with a cast, so a member added to the enum without a name
#: here is a type error at build time.
_OUTCOME_NAMES: dict[ProposalOutcome, ModelProposalOutcomeName] = {
    ProposalOutcome.PLANNED: "planned",
    ProposalOutcome.FINISHED: "finished",
    ProposalOutcome.TRUNCATED: "truncated",
    ProposalOutcome.INCONCLUSIVE: "inconclusive",
    ProposalOutcome.REFUSED: "refused",
    ProposalOutcome.BUDGET_EXHAUSTED: "budget_exhausted",
    ProposalOutcome.PROVIDER_FAILED: "provider_failed",
}

#: A member of the enum with no name in the table above would be a
#: ``KeyError`` inside the response builder - an armoured 500 in place of an
#: answer - so the mapping is asserted total at import rather than trusted to
#: stay total. Cheap, once, at startup, and it fails where a reader can see
#: which member was forgotten.
assert set(_OUTCOME_NAMES) == set(ProposalOutcome), sorted(
    outcome.value for outcome in ProposalOutcome if outcome not in _OUTCOME_NAMES
)


def _unavailable(sentence: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=sentence,
        headers=_NO_STORE,
    )


def _planner(request: Request) -> ModelPlannerService:
    service: ModelPlannerService | None = getattr(
        request.app.state, "model_planner", None
    )
    if service is None:
        raise _unavailable("Model plan yolu kullanilabilir degil.")
    return service


def _tasks(request: Request) -> TaskService:
    service: TaskService | None = getattr(request.app.state, "tasks", None)
    if service is None:
        raise _unavailable("Gorev yuzeyi kullanilabilir degil.")
    return service


def _agent(request: Request) -> AgentService:
    service: AgentService | None = getattr(request.app.state, "agent", None)
    if service is None:
        raise _unavailable("Agent calisma ortami kullanilabilir degil.")
    return service


def _json(model: BaseModel) -> Response:
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


@router.post("/tasks/{task_id}/model-plan", response_model=ModelProposalResponse)
def propose_plan(
    request: Request,
    session: CurrentSession,
    task_id: str,
    body: ModelProposeRequest,
) -> Response:
    """Spend one model turn. Blocking, synchronous, and it starts nothing.

    ``def`` rather than ``async def`` for the reason the run routes are: the
    call is blocking, and doing it on the event loop would stall every other
    request.

    The refusals a caller can meet, and why each is the status it is:

    * **503** - the planning lane is not wired at all (no database);
    * **400** - no credential, or no model chosen, or a model whose protocol
      family is not the one whose tool-call shape was measured. Configuration
      the person can fix;
    * **404** - no such task;
    * **200 with an outcome that is not ``planned``** - the turn happened (or
      was refused before it was sent) and the response says which. A provider
      failure, a proposal that named an unregistered tool, and a session that
      hit its ceiling are not HTTP errors: they are results of an operation
      that ran, and flattening them into a 4xx would lose which one it was.
    """
    del session
    planner = _planner(request)
    tasks = _tasks(request)
    agent = _agent(request)
    try:
        view = planner.propose(task_id, instruction=body.instruction)
    except RunError as exc:
        raise _refuse(exc) from exc
    except (ModelNotSelectableError, OpenCodeConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    except OpenCodeError as exc:  # pragma: no cover - the service maps the rest
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc

    try:
        task = to_task_status(tasks.get(task_id), tasks.gate(task_id))
        runs = [run_status(item) for item in agent.list_runs(task_id)]
    except (TaskError, AgentError) as exc:  # pragma: no cover - read one call ago
        raise _refuse(exc) from exc

    return _json(
        ModelProposalResponse(
            outcome=_OUTCOME_NAMES[view.outcome],
            run_id=view.run_id,
            detail=view.detail,
            model_calls_used=view.model_calls_used,
            max_model_calls=view.max_model_calls,
            usage_detail=view.usage_detail,
            closing_text=view.closing_text,
            tool_call_provenance=TOOL_CALL_PROVENANCE,
            task=task,
            runs=runs,
        )
    )


@router.post("/tasks/{task_id}/model-plan/forget", response_model=ModelProposalResponse)
def forget_session(
    request: Request, session: CurrentSession, task_id: str
) -> Response:
    """Drop this task's planning session so the next turn starts from nothing.

    A person starting over is not a resume, and it is not a way around the
    ceiling either - the recorded runs, the workspace and the task's evidence
    are all untouched, and the next turn will re-read them. What is discarded
    is the in-memory conversation, which is the only thing this lane keeps.
    """
    del session
    planner = _planner(request)
    tasks = _tasks(request)
    agent = _agent(request)
    planner.forget(task_id)
    try:
        task = to_task_status(tasks.get(task_id), tasks.gate(task_id))
        runs = [run_status(item) for item in agent.list_runs(task_id)]
    except (TaskError, AgentError) as exc:
        raise _refuse(exc) from exc

    state = planner.session_state(task_id)
    return _json(
        ModelProposalResponse(
            outcome="finished",
            run_id="",
            detail=(
                "Bu gorevin model oturumu unutuldu. Kaydedilmis planlar, "
                "calisma alani ve kanitlar oldugu gibi durur."
            ),
            model_calls_used=state.model_calls_used,
            max_model_calls=state.max_model_calls,
            usage_detail="",
            closing_text="",
            tool_call_provenance=TOOL_CALL_PROVENANCE,
            task=task,
            runs=runs,
        )
    )


def _refuse(exc: AgentError | TaskError) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if exc.reason in {"task_missing", "run_missing"}
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=code, detail=str(exc), headers=_NO_STORE)


__all__ = ["router"]
