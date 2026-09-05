"""Security-test fixtures.

The CSRF probe application is built **here**, in the test suite, rather than
in the product. A side-effect-free echo route is all the CSRF middleware needs
to be exercised, and building it in tests guarantees no probe endpoint can
ever ship in a release (IMP-108).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from starlette.routing import BaseRoute
from station_api.agent.activity import ActivityLog
from station_api.agent.service import AgentService
from station_api.app import create_app
from station_api.config import Settings
from station_api.evidence.audit import AuditChain
from station_api.evidence.audit_envelope import AuditEnvelope
from station_api.evidence.service import EvidenceService
from station_api.logging_setup import clear_secret_registry
from station_api.modules.registry import ModuleId
from station_api.proof.service import ProofService
from station_api.security.tokens import BootstrapTokenStore
from station_api.tasks.service import TaskService, TaskView
from station_api.tasks.sources import TaskSourceId

from tests.conftest import TEST_PORT
from tests.security.agent_fixtures import TEST_ONLY_CONTENT

FOREIGN_ORIGIN = "http://evil.example"
DEV_ORIGIN = "http://127.0.0.1:5173"


def collect_route_paths(application: FastAPI) -> frozenset[str]:
    """Every path the application actually serves.

    Written because the obvious spelling stopped working and nobody noticed.
    This FastAPI version wraps an included router in an ``_IncludedRouter``
    object that carries no ``path``, so
    ``{getattr(route, "path", "") for route in app.routes}`` returned a set
    of empty strings - and every assertion of the form "no route path
    contains 'say'" passed while inspecting nothing at all.

    Callers therefore assert against a **known** path as well as against the
    forbidden ones, so a walk that goes blind again fails instead of
    reporting success.
    """

    def walk(routes: Iterable[BaseRoute]) -> Iterator[str]:
        for route in routes:
            included = getattr(route, "original_router", None)
            if included is not None:
                yield from walk(included.routes)
                continue
            path = getattr(route, "path", "")
            if path:
                yield path

    return frozenset(walk(application.routes))


@pytest.fixture(autouse=True)
def _reset_secret_registry() -> Iterator[None]:
    """Keep the redaction registry from leaking between tests."""
    clear_secret_registry()
    yield
    clear_secret_registry()


@pytest.fixture
def app(settings: Settings, engine: Engine) -> FastAPI:
    return create_app(settings=settings, port=TEST_PORT, engine=engine, web_dist=None)


def build_probe_app(
    *,
    settings: Settings,
    engine: Engine | None = None,
    port: int = TEST_PORT,
    token_store: BootstrapTokenStore | None = None,
) -> FastAPI:
    """An app with one side-effect-free POST route, for CSRF tests only.

    The route stores nothing, mutates nothing and returns a constant, so
    exercising it can never leave state behind.
    """
    application = create_app(
        settings=settings,
        port=port,
        engine=engine,
        web_dist=None,
        token_store=token_store,
    )

    @application.post("/api/probe/echo")
    async def probe_echo() -> dict[str, bool]:
        return {"accepted": True}

    return application


@pytest.fixture
def probe_app(settings: Settings, engine: Engine) -> FastAPI:
    return build_probe_app(settings=settings, engine=engine)


@pytest.fixture
def client(app: FastAPI, base_url: str) -> Iterator[TestClient]:
    with TestClient(app, base_url=base_url) as test_client:
        yield test_client


@pytest.fixture
def probe_client(probe_app: FastAPI, base_url: str) -> Iterator[TestClient]:
    with TestClient(probe_app, base_url=base_url) as test_client:
        yield test_client


def establish_session(test_client: TestClient, application: FastAPI) -> str:
    """Redeem a fresh bootstrap token and return the session's CSRF value."""
    token = application.state.bootstrap_tokens.issue()
    redirect = test_client.get(f"/session/{token}", follow_redirects=False)
    assert redirect.status_code == 303
    bootstrap = test_client.get("/api/session/bootstrap")
    assert bootstrap.status_code == 200
    csrf_token: str = bootstrap.json()["csrf_token"]
    return csrf_token


@pytest.fixture
def csrf_token(client: TestClient, app: FastAPI) -> str:
    return establish_session(client, app)


@pytest.fixture
def probe_csrf_token(probe_client: TestClient, probe_app: FastAPI) -> str:
    return establish_session(probe_client, probe_app)


# ---------------------------------------------------------------------------
# Package H2: the agent runtime and the Activity Desk
# ---------------------------------------------------------------------------
#
# Declared here rather than in ``agent_fixtures.py`` so test files use them by
# name. A fixture that is imported and then named as a parameter is a
# redefinition of the imported name, which the linter reports and which hides
# the fact that the parameter is resolved by pytest rather than by the import.


@pytest.fixture
def tasks(engine: Engine) -> TaskService:
    return TaskService(engine=engine)


@pytest.fixture
def activity_log(engine: Engine, data_dir: Path) -> ActivityLog:
    """A log wired to a real audit chain, so a decision point really links."""
    chain = AuditChain(engine, AuditEnvelope(data_dir))
    chain.ensure_ready()
    return ActivityLog(engine=engine, chain=chain)


@pytest.fixture
def unchained_activity_log(engine: Engine) -> ActivityLog:
    """A log with no chain, as a machine where DPAPI is missing would have.

    The timeline still records; what it must never do is *claim* a decision
    reached the chain when it did not.
    """
    return ActivityLog(engine=engine, chain=None)


@pytest.fixture
def agent(
    engine: Engine, data_dir: Path, tasks: TaskService, activity_log: ActivityLog
) -> AgentService:
    return AgentService(
        engine=engine, data_dir=data_dir, tasks=tasks, activity=activity_log
    )


@pytest.fixture
def task(tasks: TaskService) -> TaskView:
    """One task in ``awaiting_approval``, which is where a run may be planned."""
    return tasks.open_task(
        module_id=ModuleId.AGENT_WORKSPACE,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=TEST_ONLY_CONTENT,
        title="TEST-ONLY agent gorevi",
    )


# ---------------------------------------------------------------------------
# Package H3: the proof workspace
# ---------------------------------------------------------------------------
#
# Declared here rather than in a fixtures module for the reason the H2 block
# above gives: a fixture that is imported and then named as a parameter is a
# redefinition of the imported name, which hides the fact that the parameter
# is resolved by pytest rather than by the import.


@pytest.fixture
def evidence(engine: Engine, data_dir: Path) -> EvidenceService:
    """A started evidence archive, so the public-share lookup has one to read.

    ``start()`` creates the chain's MAC material through the same DPAPI
    envelope the application uses. Nothing here contacts anything.
    """
    service = EvidenceService(
        engine=engine, chain=AuditChain(engine, AuditEnvelope(data_dir))
    )
    service.start()
    return service


@pytest.fixture
def proof(
    tasks: TaskService, agent: AgentService, evidence: EvidenceService
) -> ProofService:
    return ProofService(tasks=tasks, agent=agent, evidence=evidence)


@pytest.fixture
def proof_without_archive(tasks: TaskService, agent: AgentService) -> ProofService:
    """A proof workspace on a machine where the audit envelope did not open.

    The bundle still assembles; the one operation that needs the archive -
    marking the fourth field from an archived send - refuses instead of
    pretending.
    """
    return ProofService(tasks=tasks, agent=agent, evidence=None)
