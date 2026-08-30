"""SI-11 .. SI-18 - Host, Origin and Sec-Fetch-Site guards."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import Settings, load_settings

from .conftest import DEV_ORIGIN, FOREIGN_ORIGIN, TEST_PORT

pytestmark = pytest.mark.security

EXPECTED_HOST = f"127.0.0.1:{TEST_PORT}"
EXPECTED_ORIGIN = f"http://127.0.0.1:{TEST_PORT}"


# --- Host ---------------------------------------------------------------


def test_exact_loopback_host_is_accepted(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Host": EXPECTED_HOST})
    assert response.status_code == 200


def test_localhost_host_rejected(client: TestClient) -> None:
    """`localhost` is a name, not the literal address we bound.

    Accepting names is what makes DNS rebinding work, so it is refused even
    though it resolves to the loopback address in practice.
    """
    response = client.get("/api/health", headers={"Host": f"localhost:{TEST_PORT}"})
    assert response.status_code == 421


def test_foreign_host_rejected_with_421(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Host": "evil.example"})
    assert response.status_code == 421


def test_wrong_port_host_rejected(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Host": "127.0.0.1:1"})
    assert response.status_code == 421


def test_host_guard_also_protects_the_session_handoff(
    client: TestClient, app: FastAPI
) -> None:
    token = app.state.bootstrap_tokens.issue()
    response = client.get(
        f"/session/{token}",
        headers={"Host": "evil.example"},
        follow_redirects=False,
    )
    assert response.status_code == 421


# --- Origin -------------------------------------------------------------


def test_same_origin_is_accepted(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": EXPECTED_ORIGIN})
    assert response.status_code == 200


def test_foreign_origin_rejected(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": FOREIGN_ORIGIN})
    assert response.status_code == 403


def test_dev_origin_rejected_in_production_mode(client: TestClient) -> None:
    """The Vite origin must never be honoured by a production build."""
    response = client.get("/api/health", headers={"Origin": DEV_ORIGIN})
    assert response.status_code == 403


def test_dev_origin_accepted_only_when_dev_mode_is_on(
    dev_settings: Settings, engine: Engine, base_url: str
) -> None:
    app = create_app(settings=dev_settings, port=TEST_PORT, engine=engine, web_dist=None)
    with TestClient(app, base_url=base_url) as client:
        assert client.get("/api/health", headers={"Origin": DEV_ORIGIN}).status_code == 200
        # Even in development, an unrelated origin is still refused.
        assert (
            client.get("/api/health", headers={"Origin": FOREIGN_ORIGIN}).status_code == 403
        )


# --- Sec-Fetch-Site -----------------------------------------------------


def test_same_origin_fetch_metadata_is_accepted(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Sec-Fetch-Site": "same-origin"})
    assert response.status_code == 200


def test_cross_site_fetch_metadata_rejected(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_same_site_fetch_metadata_rejected(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Sec-Fetch-Site": "same-site"})
    assert response.status_code == 403


def test_sec_fetch_site_none_allowed_for_safe_navigation(
    client: TestClient, app: FastAPI
) -> None:
    """The launcher's own tab arrives with Sec-Fetch-Site: none."""
    token = app.state.bootstrap_tokens.issue()
    response = client.get(
        f"/session/{token}",
        headers={"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_sec_fetch_site_none_rejected_on_state_change(
    probe_client: TestClient, probe_csrf_token: str
) -> None:
    response = probe_client.post(
        "/api/probe/echo",
        headers={"Sec-Fetch-Site": "none", "X-Station-CSRF": probe_csrf_token},
    )
    assert response.status_code == 403


# --- STATION_DEV fail-closed -------------------------------------------


def test_station_dev_defaults_to_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STATION_DEV", raising=False)
    assert load_settings().dev_mode is False


@pytest.mark.parametrize("value", ["", "0", "no", "off", "false", "maybe", "TRUE ish", "2"])
def test_station_dev_only_opens_on_an_explicit_truthy_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("STATION_DEV", value)
    assert load_settings().dev_mode is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " true "])
def test_station_dev_opens_on_recognised_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("STATION_DEV", value)
    assert load_settings().dev_mode is True
