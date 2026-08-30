"""Security-test fixtures.

The CSRF probe application is built **here**, in the test suite, rather than
in the product. A side-effect-free echo route is all the CSRF middleware needs
to be exercised, and building it in tests guarantees no probe endpoint can
ever ship in a release (IMP-108).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import Settings
from station_api.logging_setup import clear_secret_registry
from station_api.security.tokens import BootstrapTokenStore

from tests.conftest import TEST_PORT

FOREIGN_ORIGIN = "http://evil.example"
DEV_ORIGIN = "http://127.0.0.1:5173"


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
