"""SI-04 .. SI-10 - bootstrap token lifetime, session cookie, unauthenticated access."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import SESSION_COOKIE_NAME, Settings
from station_api.security.tokens import TOKEN_ENTROPY_BYTES, BootstrapTokenStore

pytestmark = pytest.mark.security


class FakeClock:
    """A monotonic clock the test drives by hand."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_bootstrap_token_entropy() -> None:
    assert TOKEN_ENTROPY_BYTES == 32  # 256 bits

    store = BootstrapTokenStore()
    tokens = {store.issue() for _ in range(200)}

    assert len(tokens) == 200, "tokens must never repeat"
    for token in tokens:
        # base64url of 32 bytes, unpadded.
        assert len(token) >= 43


def test_bootstrap_token_is_single_use(client: TestClient, app: FastAPI) -> None:
    token = app.state.bootstrap_tokens.issue()

    first = client.get(f"/session/{token}", follow_redirects=False)
    assert first.status_code == 303

    second = client.get(f"/session/{token}", follow_redirects=False)
    assert second.status_code == 404


def test_bootstrap_token_expires_after_30_seconds(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    clock = FakeClock()
    store = BootstrapTokenStore(ttl_seconds=30, clock=clock)
    app = create_app(
        settings=settings, port=49731, engine=engine, web_dist=None, token_store=store
    )

    with TestClient(app, base_url=base_url) as client:
        token = store.issue()
        clock.advance(30.5)
        assert client.get(f"/session/{token}", follow_redirects=False).status_code == 404


def test_bootstrap_token_still_valid_just_before_expiry(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """The boundary matters: an off-by-one would silently shorten the window."""
    clock = FakeClock()
    store = BootstrapTokenStore(ttl_seconds=30, clock=clock)
    app = create_app(
        settings=settings, port=49731, engine=engine, web_dist=None, token_store=store
    )

    with TestClient(app, base_url=base_url) as client:
        token = store.issue()
        clock.advance(29.5)
        assert client.get(f"/session/{token}", follow_redirects=False).status_code == 303


def test_unknown_token_is_rejected(client: TestClient) -> None:
    response = client.get("/session/not-a-real-token", follow_redirects=False)
    assert response.status_code == 404


def test_session_cookie_flags(client: TestClient, app: FastAPI) -> None:
    token = app.state.bootstrap_tokens.issue()
    response = client.get(f"/session/{token}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/" in set_cookie

    # Deliberately absent: the session runs over loopback HTTP, where browsers
    # do not treat Secure cookies consistently. Claiming Secure here would be
    # a guarantee the transport cannot keep (SECURITY.md 3, IMP-103).
    assert "secure" not in set_cookie


def test_protected_endpoint_without_cookie_is_401(client: TestClient) -> None:
    assert client.get("/api/app/status").status_code == 401
    assert client.get("/api/session/bootstrap").status_code == 401


def test_health_endpoint_is_public_and_minimal(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "station-api"}


def test_protected_endpoint_with_session_succeeds(client: TestClient, app: FastAPI) -> None:
    token = app.state.bootstrap_tokens.issue()
    client.get(f"/session/{token}", follow_redirects=False)
    assert client.get("/api/app/status").status_code == 200


def test_session_store_is_memory_only(
    client: TestClient, data_dir: Path, csrf_token: str
) -> None:
    """Neither the session id nor the CSRF value may reach the filesystem."""
    session_id = client.cookies[SESSION_COOKIE_NAME]
    assert session_id

    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        assert session_id.encode() not in blob, f"session id persisted in {path}"
        assert csrf_token.encode() not in blob, f"csrf value persisted in {path}"


def test_revoked_session_stops_working(client: TestClient, app: FastAPI) -> None:
    token = app.state.bootstrap_tokens.issue()
    client.get(f"/session/{token}", follow_redirects=False)
    session_id = client.cookies[SESSION_COOKIE_NAME]

    app.state.sessions.revoke(session_id)

    assert client.get("/api/app/status").status_code == 401
