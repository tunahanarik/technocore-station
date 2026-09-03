"""The evidence surface over HTTP, with the real guards.

Two things are pinned here that the unit tests cannot reach: the HTTP contract
(session, CSRF, the download header, the refusal codes) and the absence of a
route that would let a user re-send anything.

Nothing here contacts Technocore. Both outbound clients are driven through
``httpx.MockTransport``; the target is a TEST-ONLY room and never the lobby
(INV-05).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import Settings
from station_api.evidence.language import find_forbidden_phrases
from station_api.routes.compose import send_message
from station_api.routes.evidence import capture_line
from station_api.technocore.client import ReadOnlyTechnocoreClient
from station_api.technocore.service import TechnocoreService
from station_api.technocore.write_client import SignedWriteClient

from tests.security.compose_fixtures import official_documents_transport
from tests.security.conftest import TEST_PORT, collect_route_paths, establish_session

pytestmark = pytest.mark.integration

windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="the audit chain's DPAPI envelope is required for the evidence surface",
)

EVIDENCE_ROUTES = (
    "/api/evidence/records",
    "/api/evidence/capture",
    "/api/evidence/export",
    "/api/evidence/audit",
)


@pytest.fixture
def app(settings: Settings, engine: Engine) -> FastAPI:
    return create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        technocore=TechnocoreService(
            engine=engine,
            client=ReadOnlyTechnocoreClient(
                transport=official_documents_transport(), sleep=lambda _: None
            ),
        ),
        write_client=SignedWriteClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"seq": 1})
            )
        ),
    )


@pytest.fixture
def api(app: FastAPI, base_url: str) -> Iterator[tuple[TestClient, str]]:
    with TestClient(app, base_url=base_url) as client:
        yield client, establish_session(client, app)


# ---------------------------------------------------------------------------
# The guards
# ---------------------------------------------------------------------------


def test_every_evidence_route_requires_a_session(
    app: FastAPI, base_url: str
) -> None:
    with TestClient(app, base_url=base_url) as client:
        assert client.get("/api/evidence/records").status_code == 401
        assert client.get("/api/evidence/audit").status_code == 401
        for path in ("/api/evidence/capture", "/api/evidence/export"):
            assert client.post(path, json={}).status_code in {401, 403}


def test_a_state_changing_evidence_call_without_csrf_is_refused(
    api: tuple[TestClient, str],
) -> None:
    client, _csrf = api
    for path in ("/api/evidence/capture", "/api/evidence/export"):
        assert client.post(path, json={}).status_code == 403


def test_no_evidence_route_accepts_a_get_write(api: tuple[TestClient, str]) -> None:
    client, _csrf = api
    for path in ("/api/evidence/capture", "/api/evidence/export"):
        assert client.get(path).status_code == 405


def test_the_evidence_surface_adds_no_resend_route(app: FastAPI) -> None:
    """A capture is a read. There is no route that publishes anything again.

    ``line_not_found`` is not a reason to send a second message, and the
    absence of a way to is what makes that a property rather than advice
    (ADR-0002 3, ADR-0003 4).
    """
    paths = collect_route_paths(app)

    assert "/api/evidence/capture" in paths, "the walk must not be looking at nothing"
    evidence = {path for path in paths if path.startswith("/api/evidence")}
    assert evidence == set(EVIDENCE_ROUTES)
    for path in evidence:
        lowered = path.lower()
        for forbidden in ("send", "resend", "retry", "say", "note", "publish"):
            assert forbidden not in lowered


def test_the_capture_route_is_not_a_coroutine() -> None:
    """It reads a stream under a 30-second timeout through synchronous httpx.

    On the event loop that would stall every other request for the whole
    scan - the same reason the composer's blocking routes are ``def``
    (IMP-296).
    """
    import inspect

    assert not inspect.iscoroutinefunction(capture_line)
    assert not inspect.iscoroutinefunction(send_message)


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


@windows_only
def test_the_archive_reads_empty_with_the_chain_verdict_beside_it(
    api: tuple[TestClient, str],
) -> None:
    """A reader never sees records without the chain's own verdict."""
    client, _csrf = api
    response = client.get("/api/evidence/records")

    assert response.status_code == 200
    payload = response.json()
    assert payload["records"] == []
    assert payload["record_count"] == 0
    assert payload["chain_state"] in {"intact", "empty"}
    assert response.headers["Cache-Control"] == "no-store"


@windows_only
def test_the_audit_read_carries_the_only_permitted_claim(
    api: tuple[TestClient, str],
) -> None:
    client, _csrf = api
    payload = client.get("/api/evidence/audit").json()

    assert "tespit edici" in payload["claim"]
    assert find_forbidden_phrases(payload["claim"]) == ()
    assert find_forbidden_phrases(payload["detail"]) == ()


@windows_only
def test_no_evidence_response_body_carries_a_forbidden_phrase(
    api: tuple[TestClient, str],
) -> None:
    """The backend half of a rule that lived only in a frontend test."""
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}

    bodies = [
        client.get("/api/evidence/records").text,
        client.get("/api/evidence/audit").text,
        client.post(
            "/api/evidence/capture", headers=headers, json={"evidence_id": "0" * 32}
        ).text,
        client.post(
            "/api/evidence/export",
            headers=headers,
            json={"format": "markdown", "acknowledged": True},
        ).text,
    ]

    for body in bodies:
        assert find_forbidden_phrases(body) == (), body[:200]


@windows_only
def test_an_export_without_the_acknowledgement_is_refused(
    api: tuple[TestClient, str],
) -> None:
    """Two refusals: the model has no default, and the handler re-checks."""
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}

    missing = client.post("/api/evidence/export", headers=headers, json={"format": "json"})
    assert missing.status_code == 422

    refused = client.post(
        "/api/evidence/export",
        headers=headers,
        json={"format": "json", "acknowledged": False},
    )
    assert refused.status_code == 400
    assert "onay" in refused.json()["detail"]


@windows_only
def test_a_consented_export_is_a_download_with_a_safe_name(
    api: tuple[TestClient, str],
) -> None:
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}

    for export_format, suffix, media in (
        ("json", ".json", "application/json"),
        ("markdown", ".md", "text/markdown"),
    ):
        response = client.post(
            "/api/evidence/export",
            headers=headers,
            json={"format": export_format, "acknowledged": True},
        )
        assert response.status_code == 200
        assert media in response.headers["content-type"]

        disposition = response.headers["Content-Disposition"]
        assert disposition.startswith('attachment; filename="')
        assert disposition.endswith(f'{suffix}"')
        assert disposition.count('"') == 2
        assert "\r" not in disposition and "\n" not in disposition
        assert disposition.isascii()
        assert response.headers["Cache-Control"] == "no-store"


@windows_only
def test_the_export_is_byte_identical_on_a_second_request(
    api: tuple[TestClient, str],
) -> None:
    """Deterministic across requests, not merely across calls in one process.

    The exported-at stamp is a wall clock, so the two documents differ only
    there; everything about the records themselves is identical.
    """
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}
    body = {"format": "json", "acknowledged": True}

    first = client.post("/api/evidence/export", headers=headers, json=body).json()
    second = client.post("/api/evidence/export", headers=headers, json=body).json()

    del first["exported_at"], second["exported_at"]
    assert first == second


@windows_only
def test_an_unknown_evidence_id_is_a_refusal_rather_than_an_invention(
    api: tuple[TestClient, str],
) -> None:
    client, csrf = api
    response = client.post(
        "/api/evidence/capture",
        headers={"X-Station-CSRF": csrf},
        json={"evidence_id": "0" * 32},
    )

    assert response.status_code == 404
    assert set(response.json()) == {"detail"}, "the error contract is {detail}"
