"""The task and Activity Desk routes: what they expose, and what they refuse.

Package F wrote "the task layer has no routes in this release". H2 opens
them, and the shape of what is opened is the whole question. This file holds
the boundary at the HTTP surface, where a client - a browser, a script,
anything - meets it.

Four refusals matter more than the rest:

* **there is no route that runs a command**, and the surface says so as a
  reason with a sentence rather than by omitting a button (ADR-0008 1);
* **there is no route that records evidence.** ``test_result`` in particular
  is written by nothing, which is what keeps a finished run in
  ``review_needed``. A route that let a caller mark it verified would undo
  the evidence model in one POST;
* **there is no transition to ``running`` or ``paused``.** Those belong to the
  run routes, which record a plan first; a direct transition would be a way
  into the executing state with no plan written down (ADR-0008 7);
* **a run id in the path must belong to the task in the path**, so a response
  never describes a different object than the one that was acted on.

The ordinary guarantees are checked too - ``no-store``, CSRF on every
state-changing route, ``extra="forbid"`` on every body - because a new router
is exactly where a project stops inheriting them by accident.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from station_api.agent.budget import BUDGET_UNITS, CEILING
from station_api.agent.isolation import (
    ARBITRARY_EXECUTION_SUPPORTED,
    execution_verdict,
)
from station_api.agent.language import RUN_HONESTY_SENTENCE
from station_api.agent.tools import TOOLS
from station_api.modules.registry import ModuleId
from station_api.tasks.service import TaskService
from station_api.tasks.sources import TaskSourceId

from tests.security.conftest import collect_route_paths

pytestmark = pytest.mark.security

CSRF = "X-Station-CSRF"

TASKS_PATH = "/api/tasks"
SURFACE_PATH = "/api/tasks/surface"
ACTIVITY_PATH = "/api/activity"

#: Exactly the paths this router serves. Written out, so a route added later
#: is a change somebody reviews rather than a surface that grew.
EXPECTED_PATHS = {
    "/api/tasks",
    "/api/tasks/surface",
    "/api/tasks/{task_id}",
    "/api/tasks/{task_id}/transition",
    "/api/tasks/{task_id}/publish-readiness",
    "/api/tasks/{task_id}/runs",
    "/api/tasks/{task_id}/runs/{run_id}/start",
    "/api/tasks/{task_id}/runs/{run_id}/stop",
    "/api/tasks/{task_id}/runs/{run_id}/resume",
    # Package H4's planning lane. It lives in its own router
    # (``routes/planner.py``) because ``routes/agent.py`` may not import
    # ``station_api.opencode`` - ``test_agent_boundary`` reads its syntax
    # tree and refuses it - but the paths hang off ``/api/tasks``, so they
    # are part of the surface this inventory covers and are listed here.
    "/api/tasks/{task_id}/model-plan",
    "/api/tasks/{task_id}/model-plan/forget",
    "/api/activity",
    "/api/activity/delete",
}

#: State-changing routes, and a body each one accepts. Used to check that
#: every one of them is behind CSRF rather than checking one and assuming.
STATE_CHANGING = (
    ("/api/tasks/{task_id}/transition", {"target": "blocked"}),
    ("/api/tasks/{task_id}/publish-readiness", {}),
    ("/api/tasks/{task_id}/runs", {"steps": [], "test_condition": "x"}),
    ("/api/tasks/{task_id}/model-plan", {"instruction": "TEST-ONLY"}),
    ("/api/tasks/{task_id}/model-plan/forget", None),
    ("/api/activity/delete", {}),
)


@pytest.fixture
def task_id(app: FastAPI) -> str:
    service: TaskService = app.state.tasks
    return service.open_task(
        module_id=ModuleId.AGENT_WORKSPACE,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=b"TEST-ONLY http task",
        title="TEST-ONLY",
    ).id


def _plan_body(name: str = "rapor.json") -> dict[str, object]:
    return {
        "steps": [
            {
                "tool_id": "write_workspace_file",
                "arguments": {"name": name, "body": '{"TEST_ONLY": true}'},
            },
            {"tool_id": "validate_json_file", "arguments": {"name": name}},
        ],
        "expected_artifacts": [name],
        "test_condition": "TEST-ONLY olcut",
    }


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------


def test_the_router_serves_exactly_these_paths(app: FastAPI) -> None:
    paths = {path for path in collect_route_paths(app) if _is_h2(path)}

    assert paths == EXPECTED_PATHS


def _is_h2(path: str) -> bool:
    return path.startswith(("/api/tasks", "/api/activity"))


def test_no_route_names_a_write_lane_or_a_note(app: FastAPI) -> None:
    """The composer's rule, re-checked on a new router.

    A known path is asserted first, so a walk that went blind fails instead of
    reporting success over an empty set.
    """
    paths = collect_route_paths(app)

    assert TASKS_PATH in paths
    for path in paths:
        assert "note" not in path.lower()
        assert "say" not in path.lower()
        assert "exec" not in path.lower()
        assert "shell" not in path.lower()


def test_the_surface_states_that_execution_is_closed_and_why(
    client: TestClient, csrf_token: str
) -> None:
    """``execution_unavailable`` is a reason with a sentence, not a silence.

    And the measured inventory travels with it: Docker is reported as
    **present and not relied upon** rather than omitted, which is ADR-0008 1's
    whole point - an absence is stated, a presence that changes nothing says
    so.
    """
    assert csrf_token
    payload = client.get(SURFACE_PATH).json()

    assert payload["execution"]["arbitrary_execution_supported"] is False
    assert payload["execution"]["reason"] == "execution_unavailable"
    assert payload["execution"]["detail"].strip()

    # The wire is the module's own values, not a second copy of them. It used
    # to be the second copy: ``schemas.py`` spelled ``False`` again with no
    # link to ``isolation``, and an independent review measured that editing
    # either one left the other - and the whole suite - untouched.
    assert payload["execution"]["detail"] == execution_verdict().detail
    assert payload["execution"]["reason"] == execution_verdict().reason

    inventory = {row["facility"]: row for row in payload["execution"]["inventory"]}
    assert inventory["docker_desktop"]["measured"] == "present"
    assert inventory["docker_desktop"]["relied_upon"] is False
    assert inventory["windows_optional_features"]["measured"] == "not_measured"
    assert all(row["relied_upon"] is False for row in inventory.values())


def test_the_verdicts_allowed_field_is_the_module_constant(
    client: TestClient, csrf_token: str
) -> None:
    """One fact, one place, and the wire follows it.

    ``execution_verdict().allowed`` used to be a hard-coded ``False`` that
    **nothing read** - both call sites take only ``.reason`` and ``.detail``,
    so turning it into ``True`` left the entire suite green. It is now
    ``ARBITRARY_EXECUTION_SUPPORTED``, and the route passes that same
    constant to a response field typed ``Literal[False]``. Editing the
    constant therefore breaks the verdict, the wire and ``mypy`` together,
    which is what "structural" has to mean to be worth the word.
    """
    assert csrf_token
    assert ARBITRARY_EXECUTION_SUPPORTED is False
    assert execution_verdict().allowed is ARBITRARY_EXECUTION_SUPPORTED

    published = client.get(SURFACE_PATH).json()["execution"]

    assert published["arbitrary_execution_supported"] is ARBITRARY_EXECUTION_SUPPORTED


def test_the_surface_publishes_the_ceiling_and_the_units_it_refuses(
    client: TestClient, csrf_token: str
) -> None:
    assert csrf_token
    ceiling = client.get(SURFACE_PATH).json()["ceiling"]

    assert ceiling["max_tool_calls"] == CEILING.max_tool_calls
    assert ceiling["max_concurrency"] == 1
    assert ceiling["units"] == list(BUDGET_UNITS)
    assert ceiling["refused_units"] == ["token", "currency"]
    assert ceiling["agent_can_raise_ceiling"] is False


def test_the_surface_publishes_the_whole_tool_registry(
    client: TestClient, csrf_token: str
) -> None:
    """A permission is a thing to approve before a run, not to discover after."""
    assert csrf_token
    tools = client.get(SURFACE_PATH).json()["tools"]

    assert {tool["id"] for tool in tools} == {record.id.value for record in TOOLS}
    assert all(tool["call_cost"] == 1 for tool in tools)
    assert all(tool["purpose"].strip() for tool in tools)


def test_the_surface_resumes_nothing(client: TestClient, csrf_token: str) -> None:
    """SI-224 on the wire: a read lists interrupted runs and continues none."""
    assert csrf_token
    payload = client.get(SURFACE_PATH).json()

    assert payload["resumed_any"] is False
    assert payload["interrupted_runs"] == []
    assert payload["honesty"] == RUN_HONESTY_SENTENCE


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def test_the_task_listing_reports_an_empty_unproducible_set(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    """The field stayed and its contents changed, which is the honest shape.

    A client that showed three unreachable states last release is told the set
    is empty, rather than being left to notice a key went away.
    """
    assert csrf_token and task_id
    payload = client.get(TASKS_PATH).json()

    assert payload["unproducible_states"] == []
    assert set(payload["producible_states"]) == {
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
    assert payload["unproducible_detail"].strip()


def test_a_task_reports_its_four_fields_separately(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    assert csrf_token
    payload = client.get(f"{TASKS_PATH}/{task_id}").json()

    assert {row["evidence_field"] for row in payload["evidence_fields"]} == {
        "task_outcome",
        "test_result",
        "user_acceptance",
        "public_share",
    }
    assert payload["ready_to_publish"] is False
    assert payload["budget_available"] is False


@pytest.mark.parametrize("target", ["running", "paused", "ready_to_publish"])
def test_a_person_cannot_ask_for_the_runners_states_over_http(
    client: TestClient, csrf_token: str, task_id: str, target: str
) -> None:
    """A 422 from the model, before the route body runs.

    ``running`` and ``paused`` belong to the run routes, which record a plan
    first; ``ready_to_publish`` is derived from evidence and cannot be asked
    for at all. Typing the field as a closed literal is what makes all three
    refusals happen in one place.
    """
    response = client.post(
        f"{TASKS_PATH}/{task_id}/transition",
        json={"target": target},
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 422


def test_a_permitted_transition_works_and_is_not_cached(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    response = client.post(
        f"{TASKS_PATH}/{task_id}/transition",
        json={"target": "blocked", "detail": "TEST-ONLY"},
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["state"] == "blocked"


def test_an_undefined_edge_is_a_conflict_not_a_five_hundred(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    response = client.post(
        f"{TASKS_PATH}/{task_id}/transition",
        json={"target": "published"},
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 409
    assert response.json()["detail"].strip()


def test_an_unknown_task_is_a_404(client: TestClient, csrf_token: str) -> None:
    assert csrf_token
    assert client.get(f"{TASKS_PATH}/{'0' * 32}").status_code == 404


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_planning_and_starting_are_two_requests(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    """The composer's two-approval shape, on the run surface.

    Planning records what will be done and runs nothing; starting is a second
    deliberate act. A single endpoint that did both would be one button for
    two decisions the user is meant to make separately.
    """
    planned = client.post(
        f"{TASKS_PATH}/{task_id}/runs",
        json=_plan_body(),
        headers={CSRF: csrf_token},
    )

    assert planned.status_code == 200
    body = planned.json()
    assert body["task"]["state"] == "awaiting_approval"
    assert body["workspace_files"] == []
    run_id = body["runs"][0]["id"]
    assert body["runs"][0]["phase"] == "planned"

    started = client.post(
        f"{TASKS_PATH}/{task_id}/runs/{run_id}/start", headers={CSRF: csrf_token}
    )

    assert started.status_code == 200
    finished = started.json()
    assert finished["runs"][0]["phase"] == "completed"
    assert finished["task"]["state"] == "review_needed"
    assert [file["name"] for file in finished["workspace_files"]] == ["rapor.json"]


def test_a_finished_run_reports_its_test_field_as_not_implemented(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    """The claim this whole package is arranged around.

    Files exist, a checker ran, and the run still says the test was not
    implemented - so the task is in ``review_needed`` and cannot be published.
    """
    plan = client.post(
        f"{TASKS_PATH}/{task_id}/runs", json=_plan_body(), headers={CSRF: csrf_token}
    ).json()
    run_id = plan["runs"][0]["id"]
    body = client.post(
        f"{TASKS_PATH}/{task_id}/runs/{run_id}/start", headers={CSRF: csrf_token}
    ).json()

    run = body["runs"][0]
    assert run["test_result_state"] == "not_implemented"
    assert run["test_condition"] == "TEST-ONLY olcut"
    assert run["test_result_detail"].strip()
    assert body["task"]["ready_to_publish"] is False
    assert "test_result" in body["task"]["blocking_fields"]


def test_an_unregistered_tool_in_a_plan_is_a_four_hundred(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    """"There is no such tool" - the refusal an unknown identifier earns.

    This test used to name ``run_shell_command`` here. It no longer can: a
    name that reads as a command now gets the *other* refusal, below, and
    keeping both cases on one identifier is how the two would have quietly
    merged back into one answer.
    """
    response = client.post(
        f"{TASKS_PATH}/{task_id}/runs",
        json={
            "steps": [{"tool_id": "read_mailbox", "arguments": {}}],
            "expected_artifacts": [],
            "test_condition": "TEST-ONLY",
        },
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 400
    assert "derleme zamaninda" in response.json()["detail"]


def test_asking_for_a_command_is_refused_with_the_measured_reason(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    """``execution_unavailable`` on the wire, as a 400 the user can read.

    ADR-0008 1 asks for the closed capability to be a *reason with a
    sentence* rather than an absence. On the plan route that means a step
    naming a command comes back with the measured detail - the isolation
    inventory's own words - and not folded into "unknown tool", which is
    what it used to get.
    """
    response = client.post(
        f"{TASKS_PATH}/{task_id}/runs",
        json={
            "steps": [{"tool_id": "run_shell_command", "arguments": {"cmd": "dir"}}],
            "expected_artifacts": [],
            "test_condition": "TEST-ONLY",
        },
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == execution_verdict().detail


def test_a_traversal_in_an_artifact_name_is_a_four_hundred(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    response = client.post(
        f"{TASKS_PATH}/{task_id}/runs",
        json={
            "steps": [{"tool_id": "read_run_status", "arguments": {}}],
            "expected_artifacts": ["../escape.txt"],
            "test_condition": "TEST-ONLY",
        },
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 400


def test_a_run_belonging_to_another_task_is_not_acted_on(
    client: TestClient, csrf_token: str, task_id: str, app: FastAPI
) -> None:
    """A response must never describe a different object than the one acted on."""
    other = app.state.tasks.open_task(
        module_id=ModuleId.AGENT_WORKSPACE,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=b"TEST-ONLY other",
        title="TEST-ONLY other",
    )
    plan = client.post(
        f"{TASKS_PATH}/{other.id}/runs", json=_plan_body(), headers={CSRF: csrf_token}
    ).json()
    run_id = plan["runs"][0]["id"]

    response = client.post(
        f"{TASKS_PATH}/{task_id}/runs/{run_id}/start", headers={CSRF: csrf_token}
    )

    assert response.status_code == 404


def test_a_stop_before_a_start_leaves_the_workspace_empty(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    plan = client.post(
        f"{TASKS_PATH}/{task_id}/runs", json=_plan_body(), headers={CSRF: csrf_token}
    ).json()
    run_id = plan["runs"][0]["id"]

    client.post(
        f"{TASKS_PATH}/{task_id}/runs/{run_id}/stop", headers={CSRF: csrf_token}
    )
    body = client.post(
        f"{TASKS_PATH}/{task_id}/runs/{run_id}/start", headers={CSRF: csrf_token}
    ).json()

    assert body["runs"][0]["phase"] == "paused"
    assert body["workspace_files"] == []
    assert body["task"]["state"] == "paused"


# ---------------------------------------------------------------------------
# The Activity Desk
# ---------------------------------------------------------------------------


def test_the_timeline_reports_which_rows_the_chain_refers_to(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    plan = client.post(
        f"{TASKS_PATH}/{task_id}/runs", json=_plan_body(), headers={CSRF: csrf_token}
    ).json()
    run_id = plan["runs"][0]["id"]
    client.post(
        f"{TASKS_PATH}/{task_id}/runs/{run_id}/start", headers={CSRF: csrf_token}
    )

    payload = client.get(f"{ACTIVITY_PATH}?run_id={run_id}").json()

    actions = {row["action"] for row in payload["events"]}
    assert {"run_planned", "run_started", "tool_called", "run_finished"} <= actions
    assert all(row["actor"] in {"user", "station_runner"} for row in payload["events"])
    assert payload["retained_events"] > 0
    assert payload["detail"].strip()


def test_no_timeline_row_carries_a_reasoning_or_payload_field(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    """The wire half of ADR-0008 6, asserted over the keys that arrive.

    ``test_agent_boundary.py`` says the columns do not exist; this says the
    response cannot grow one either, because the model forbids extras.
    """
    assert csrf_token and task_id
    payload = client.get(ACTIVITY_PATH).json()
    client.post(
        f"{TASKS_PATH}/{task_id}/runs", json=_plan_body(), headers={CSRF: csrf_token}
    )
    payload = client.get(ACTIVITY_PATH).json()

    assert payload["events"]
    for row in payload["events"]:
        assert set(row) == {
            "id",
            "recorded_at",
            "run_id",
            "task_id",
            "actor",
            "action",
            "outcome",
            "duration_ms",
            "artifact_sha256",
            "check_sha256",
            "detail",
            "chain_referenced",
        }


def test_deleting_the_timeline_reports_both_counts_and_says_it_was_recorded(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    client.post(
        f"{TASKS_PATH}/{task_id}/runs", json=_plan_body(), headers={CSRF: csrf_token}
    )

    response = client.post(
        f"{ACTIVITY_PATH}/delete", json={}, headers={CSRF: csrf_token}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] >= 1
    assert body["kept_because_chain_referenced"] >= 0
    assert body["recorded_in_audit_chain"] is True
    assert body["detail"].strip()


# ---------------------------------------------------------------------------
# The guarantees a new router must not lose
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [TASKS_PATH, SURFACE_PATH, ACTIVITY_PATH])
def test_every_read_is_no_store(
    client: TestClient, csrf_token: str, path: str
) -> None:
    assert csrf_token
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("template, body", STATE_CHANGING)
def test_every_state_changing_route_requires_csrf(
    client: TestClient, csrf_token: str, task_id: str, template: str, body: dict
) -> None:
    """Inherited from middleware, and inherited controls are the ones that lapse.

    Checked on every state-changing path rather than on one of them: a router
    that opted out on a single route would pass a spot check.
    """
    assert csrf_token
    path = template.format(task_id=task_id, run_id="0" * 32)

    assert client.post(path, json=body).status_code == 403


def test_every_request_model_forbids_extra_fields() -> None:
    """``extra='forbid'`` on the new bodies, so a stray key is refused."""
    from station_api import schemas

    for name in (
        "AgentPlanRequest",
        "AgentPlanStepRequest",
        "TaskTransitionRequest",
        "ActivityDeleteRequest",
    ):
        model = getattr(schemas, name)
        assert model.model_config.get("extra") == "forbid", name


def test_a_body_with_an_unknown_key_is_refused(
    client: TestClient, csrf_token: str, task_id: str
) -> None:
    response = client.post(
        f"{TASKS_PATH}/{task_id}/transition",
        json={"target": "blocked", "shell": "cmd.exe"},
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 422
