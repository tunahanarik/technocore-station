"""SI-19 .. SI-22 - CSRF enforcement on state-changing requests.

These run against the probe application defined in conftest: one POST route
that returns a constant and touches nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .conftest import establish_session

pytestmark = pytest.mark.security

PROBE_PATH = "/api/probe/echo"


def test_state_change_with_valid_csrf_passes(
    probe_client: TestClient, probe_csrf_token: str
) -> None:
    response = probe_client.post(PROBE_PATH, headers={"X-Station-CSRF": probe_csrf_token})
    assert response.status_code == 200
    assert response.json() == {"accepted": True}


def test_state_change_without_csrf_header_is_403(
    probe_client: TestClient, probe_csrf_token: str
) -> None:
    assert probe_csrf_token  # a session exists; only the header is missing
    response = probe_client.post(PROBE_PATH)
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_token_invalid"


def test_state_change_with_wrong_csrf_is_403(
    probe_client: TestClient, probe_csrf_token: str
) -> None:
    wrong = "x" * len(probe_csrf_token)
    assert wrong != probe_csrf_token
    response = probe_client.post(PROBE_PATH, headers={"X-Station-CSRF": wrong})
    assert response.status_code == 403


def test_state_change_with_empty_csrf_is_403(
    probe_client: TestClient, probe_csrf_token: str
) -> None:
    assert probe_csrf_token
    response = probe_client.post(PROBE_PATH, headers={"X-Station-CSRF": ""})
    assert response.status_code == 403


def test_state_change_without_a_session_is_403(probe_client: TestClient) -> None:
    """No cookie at all: the CSRF layer refuses before any route is reached."""
    response = probe_client.post(PROBE_PATH, headers={"X-Station-CSRF": "anything"})
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_session_required"


def test_csrf_value_of_one_session_is_rejected_for_another(
    probe_app: FastAPI, base_url: str
) -> None:
    """Sessions must not share a CSRF value."""
    with TestClient(probe_app, base_url=base_url) as first:
        first_token = establish_session(first, probe_app)

    with TestClient(probe_app, base_url=base_url) as second:
        second_token = establish_session(second, probe_app)
        assert first_token != second_token
        response = second.post(PROBE_PATH, headers={"X-Station-CSRF": first_token})
        assert response.status_code == 403


def test_safe_methods_need_no_csrf_header(
    probe_client: TestClient, probe_csrf_token: str
) -> None:
    assert probe_csrf_token
    assert probe_client.get("/api/app/status").status_code == 200


def test_csrf_comparison_is_constant_time(api_source_root: Path) -> None:
    """A plain == would leak the value one byte at a time under timing."""
    middleware = (
        api_source_root / "station_api" / "security" / "middleware.py"
    ).read_text(encoding="utf-8")
    assert "compare_digest" in middleware


def test_csrf_value_is_not_echoed_in_a_rejection(
    probe_client: TestClient, probe_csrf_token: str
) -> None:
    response = probe_client.post(PROBE_PATH, headers={"X-Station-CSRF": "wrong-value"})
    body = response.text
    assert probe_csrf_token not in body
    assert "wrong-value" not in body
