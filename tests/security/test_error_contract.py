"""SI-125, SI-126 - the error contract.

Two additive guarantees. Every response - success, guard rejection, error -
carries a fresh ``X-Station-Request-Id``. And an unhandled exception is
shielded: the client sees a constant ``{"detail": "internal_error"}`` body
with the full hardening header set, while the traceback goes to the server
log only, keyed by the same request id.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from collections.abc import Iterator
from typing import NoReturn

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from station_api.config import REQUEST_ID_HEADER_NAME
from station_api.routes import api as api_routes

from .conftest import FOREIGN_ORIGIN

pytestmark = pytest.mark.security

PROBE_PATH = "/api/probe/echo"

#: ``uuid4().hex``: exactly 32 lowercase hex characters.
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")

#: TEST-ONLY. Planted in the raised exception so the tests can prove where
#: the message does (server log) and does not (response body) end up.
BOOM_MARKER = "TEST-ONLY-unhandled-exception-marker"

#: A path outside both NO_STORE_PREFIXES. In production this family is the
#: SPA catch-all, which is exactly where an uncached 500 was being lost.
OUTSIDE_NO_STORE_PATH = "/probe-boom"


def _request_id(response: httpx.Response) -> str:
    """The response's request id, after asserting it is well-formed."""
    value = response.headers[REQUEST_ID_HEADER_NAME]
    assert REQUEST_ID_RE.fullmatch(value), f"malformed request id: {value!r}"
    return value


@pytest.fixture
def exploding_client(
    app: FastAPI, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A client whose ``/api/health`` raises an unhandled exception.

    The route is broken by monkeypatching the response model it constructs,
    so no product code changes and no probe route ships. The client does not
    re-raise server exceptions: these tests assert what an attacker's HTTP
    client would actually receive.
    """

    def _boom() -> NoReturn:
        raise RuntimeError(BOOM_MARKER)

    monkeypatch.setattr(api_routes, "HealthResponse", _boom)
    with TestClient(app, base_url=base_url, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def exploding_outside_api_client(app: FastAPI, base_url: str) -> Iterator[TestClient]:
    """A client whose exploding route lives **outside** ``/api`` and ``/session``.

    ``NO_STORE_PREFIXES`` covers only those two families, so a 500 born on any
    other path - the SPA catch-all in production - is the case that proves the
    shield forces the cache directives itself rather than inheriting them from
    the request path (SI-128).
    """

    @app.get(OUTSIDE_NO_STORE_PATH, include_in_schema=False)
    async def probe_boom() -> dict[str, str]:
        raise RuntimeError(BOOM_MARKER)

    with TestClient(app, base_url=base_url, raise_server_exceptions=False) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# SI-125 - the request id header
# ---------------------------------------------------------------------------


def test_every_response_class_carries_a_unique_request_id(
    client: TestClient, app: FastAPI
) -> None:
    """Success, auth failure, handoff, 404 and both guard rejections alike."""
    token = app.state.bootstrap_tokens.issue()

    responses = [
        client.get("/api/health"),  # 200 public
        client.get("/api/app/status"),  # 401 protected
        client.get(f"/session/{token}", follow_redirects=False),  # 303 handoff
        client.get("/session/not-a-live-token"),  # 404 HTTPException
        client.get("/api/health", headers={"Host": "evil.example"}),  # 421 host guard
        client.get("/api/health", headers={"Origin": FOREIGN_ORIGIN}),  # 403 fetch guard
        client.get("/no-such-path"),  # 404 router
    ]

    ids = {_request_id(response) for response in responses}
    assert len(ids) == len(responses), "request ids must be unique per request"


def test_two_consecutive_requests_get_different_ids(client: TestClient) -> None:
    first = _request_id(client.get("/api/health"))
    second = _request_id(client.get("/api/health"))
    assert first != second


def test_a_csrf_rejection_carries_a_request_id(
    probe_client: TestClient, probe_csrf_token: str
) -> None:
    """The id is present even when a middleware refuses before any route."""
    assert probe_csrf_token  # a session exists; only the header is missing
    response = probe_client.post(PROBE_PATH)
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_token_invalid"
    _request_id(response)


def test_a_sessionless_write_rejection_carries_a_request_id(
    probe_client: TestClient,
) -> None:
    response = probe_client.post(PROBE_PATH, headers={"X-Station-CSRF": "anything"})
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_session_required"
    _request_id(response)


def test_a_client_supplied_request_id_is_never_reflected(client: TestClient) -> None:
    """Ids are minted by the server, so a caller cannot forge log correlation."""
    forged = "TEST-ONLY-forged-request-id-value"
    response = client.get("/api/health", headers={REQUEST_ID_HEADER_NAME: forged})
    assert _request_id(response) != forged
    assert forged not in response.text


def test_the_request_id_lives_in_the_header_not_the_body(
    client: TestClient, app: FastAPI
) -> None:
    """The header adds no field to any response model (StrictModel contract)."""
    assert client.get("/api/health").json() == {"status": "ok", "service": "station-api"}
    assert "request_id" not in json.dumps(app.openapi()).lower()


# ---------------------------------------------------------------------------
# SI-126 - the unhandled-exception shield
# ---------------------------------------------------------------------------


def test_an_unhandled_exception_returns_exactly_the_contract_body(
    exploding_client: TestClient,
) -> None:
    response = exploding_client.get("/api/health")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal_error"}


def test_the_500_body_leaks_no_traceback_and_no_secret_shape(
    exploding_client: TestClient,
) -> None:
    body = exploding_client.get("/api/health").text
    for fragment in (BOOM_MARKER, "Traceback", "RuntimeError", ".py", "station_api"):
        assert fragment not in body, f"500 body leaks {fragment!r}"
    lowered = body.lower()
    for name in ("seed", "private", "secret", "mnemonic"):
        assert name not in lowered


def _assert_hardened_500(response: httpx.Response) -> None:
    """Every header a 500 must carry, whatever path produced it."""
    assert response.status_code == 500
    headers = response.headers
    assert "default-src 'none'" in headers["content-security-policy"]
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store"
    assert headers["pragma"] == "no-cache"
    _request_id(response)


def test_the_500_response_is_as_hardened_as_any_other(
    exploding_client: TestClient,
) -> None:
    """The shield builds its response outside the middleware chain, so the
    hardening headers and the request id must be proven, not assumed."""
    response = exploding_client.get("/api/health")
    headers = response.headers
    assert "default-src 'none'" in headers["content-security-policy"]
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store"  # an /api/ path stays no-store
    _request_id(response)
    _assert_hardened_500(response)


def test_a_500_outside_the_no_store_prefixes_is_still_uncacheable(
    exploding_outside_api_client: TestClient,
) -> None:
    """SI-128. ``NO_STORE_PREFIXES`` covers ``/api`` and ``/session`` only; an
    error response must never be cached no matter which path produced it."""
    response = exploding_outside_api_client.get(OUTSIDE_NO_STORE_PATH)
    assert response.json() == {"detail": "internal_error"}
    _assert_hardened_500(response)


def test_a_success_outside_the_no_store_prefixes_stays_cacheable(
    client: TestClient,
) -> None:
    """The shield forcing no-store must not have widened the prefix rule: a
    non-error response outside ``/api`` and ``/session`` is unchanged."""
    response = client.get("/no-such-path")
    assert response.status_code == 404
    assert "cache-control" not in response.headers


def test_the_traceback_reaches_the_server_log_keyed_by_the_request_id(
    exploding_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        response = exploding_client.get("/api/health")

    request_id = _request_id(response)
    matching = [
        record
        for record in caplog.records
        if record.exc_info is not None and request_id in record.getMessage()
    ]
    assert matching, "the shield must log the traceback with the request id"

    exception = matching[0].exc_info[1]
    assert exception is not None
    formatted = "".join(traceback.format_exception(exception))
    assert BOOM_MARKER in formatted
