"""The composer over HTTP, with the real guards and the real vault.

Two halves, and they cover different things.

The first half needs no identity: it pins the HTTP contract - session, CSRF,
the refusal codes, the reason header, and the fact that a closed gate refuses
every step rather than only the last one. It runs everywhere.

The second half creates a real identity in a temporary directory, proves the
recovery file restores it, runs a manifest check against the pinned documents
through a mock transport, and then walks the whole chain: draft, sign with the
real DPAPI-backed signer, and send. That is the only place the vault signer is
exercised end to end, so it is gated on Windows the same way
``test_identity_vault.py`` is - DPAPI is not optional, and a fake vault would
let production quietly store an unprotected seed.

Nothing here contacts Technocore. Both the read and the write client are
driven through ``httpx.MockTransport``; the target is a TEST-ONLY room and
never the lobby (INV-05).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import Settings
from station_api.schemas import CREATE_IDENTITY_CONFIRMATION
from station_api.technocore.client import ReadOnlyTechnocoreClient
from station_api.technocore.service import TechnocoreService
from station_api.technocore.write_client import SignedWriteClient
from technocore_conform import canonical_message, verify_payload

from tests.conftest import (
    TEST_ONLY_RECOVERY_PASSPHRASE,
    TEST_ONLY_VAULT_PASSPHRASE,
)
from tests.security.compose_fixtures import TEST_ROOM, official_documents_transport
from tests.security.conftest import TEST_PORT, establish_session

pytestmark = pytest.mark.integration

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI vault is required to sign with a real key"
)

TEXT = "TEST ONLY - bu mesaj hicbir yere gitmez."


@pytest.fixture
def sent_requests() -> list[httpx.Request]:
    return []


@pytest.fixture
def app(
    settings: Settings, engine: Engine, sent_requests: list[httpx.Request]
) -> FastAPI:
    """The real application, with both outbound transports mocked."""

    def write_handler(request: httpx.Request) -> httpx.Response:
        sent_requests.append(request)
        return httpx.Response(200, json={"seq": 1, "ok": True})

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
            transport=httpx.MockTransport(write_handler)
        ),
    )


@pytest.fixture
def api(app: FastAPI, base_url: str) -> Iterator[tuple[TestClient, str]]:
    with TestClient(app, base_url=base_url) as client:
        yield client, establish_session(client, app)


# ---------------------------------------------------------------------------
# The HTTP contract, with no identity installed
# ---------------------------------------------------------------------------


def test_every_composer_route_requires_a_session(
    app: FastAPI, base_url: str
) -> None:
    with TestClient(app, base_url=base_url) as client:
        assert client.get("/api/compose/capability").status_code == 401
        for path in ("/api/compose/draft", "/api/compose/sign", "/api/compose/send"):
            assert client.post(path, json={}).status_code in {401, 403}


def test_a_state_changing_composer_call_without_csrf_is_refused(
    api: tuple[TestClient, str],
) -> None:
    """The write surface is behind the same CSRF middleware as everything else."""
    client, _ = api

    for path in ("/api/compose/draft", "/api/compose/sign", "/api/compose/send"):
        assert client.post(path, json={}).status_code == 403


def test_a_closed_gate_refuses_every_step_not_just_the_last(
    api: tuple[TestClient, str], sent_requests: list[httpx.Request]
) -> None:
    """No identity, so nothing may be drafted, signed or sent.

    Refusing only at ``send`` would mean a user could reserve a nonce and
    produce a signature against a gate that was never open.
    """
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}

    draft = client.post(
        "/api/compose/draft", headers=headers, json={"room": TEST_ROOM, "text": TEXT}
    )
    assert draft.status_code == 409
    assert draft.headers["x-station-compose-reason"] == "write_gate_closed"

    signed = client.post(
        "/api/compose/sign",
        headers=headers,
        json={"draft_id": "nope", "draft_digest": "nope"},
    )
    assert signed.status_code == 409
    assert signed.headers["x-station-compose-reason"] == "write_gate_closed"

    sent = client.post(
        "/api/compose/send", headers=headers, json={"send_token": "nope"}
    )
    assert sent.status_code == 409
    # Send checks the approval first: there is no approval, so that is the
    # honest reason rather than the gate.
    assert sent.headers["x-station-compose-reason"] == "approval_invalid"

    assert sent_requests == []


def test_the_capability_read_explains_the_closed_door(
    api: tuple[TestClient, str],
) -> None:
    client, _ = api

    payload = client.get("/api/compose/capability").json()

    assert payload["can_compose"] is False
    assert "identity_present" in payload["blocking_reasons"]
    assert payload["write_method"] == "POST"
    assert payload["write_path_template"] == "/r/{room}"
    assert "lobby" in payload["denied_rooms"]
    assert payload["note_lane_available"] is False
    assert payload["note_lane_detail"]
    assert payload["approval_ttl_seconds"] == 180


def test_composer_responses_are_never_cached(api: tuple[TestClient, str]) -> None:
    """Every one of them is session-scoped or carries a capability token."""
    client, _ = api

    response = client.get("/api/compose/capability")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_the_composer_rejects_an_unknown_body_field(
    api: tuple[TestClient, str],
) -> None:
    """``extra="forbid"``: a field nobody validates cannot ride along."""
    client, csrf = api

    response = client.post(
        "/api/compose/draft",
        headers={"X-Station-CSRF": csrf},
        json={"room": TEST_ROOM, "text": TEXT, "url": "https://evil.example/r/x"},
    )

    assert response.status_code == 422


def test_no_composer_route_accepts_a_get_write(
    api: tuple[TestClient, str], sent_requests: list[httpx.Request]
) -> None:
    """Technocore writes over GET. Station's own API must not.

    An operator reaching for ``curl`` must not be able to publish anything by
    accident, and a browser prefetch must not be able to publish at all.
    """
    client, _ = api

    for path in ("/api/compose/draft", "/api/compose/sign", "/api/compose/send"):
        assert client.get(path).status_code == 405

    assert sent_requests == []


# ---------------------------------------------------------------------------
# The whole chain, with a real identity and the real vault signer
# ---------------------------------------------------------------------------


def _install_identity(client: TestClient, csrf: str) -> str:
    """Create an identity and prove its recovery file restores it."""
    created = client.post(
        "/api/identity",
        headers={"X-Station-CSRF": csrf},
        json={
            "protection": "dpapi+passphrase",
            "passphrase": TEST_ONLY_VAULT_PASSPHRASE,
            "passphrase_confirm": TEST_ONLY_VAULT_PASSPHRASE,
            "label": "TEST ONLY",
            "confirmation": CREATE_IDENTITY_CONFIRMATION,
        },
    )
    assert created.status_code == 201
    did: str = created.json()["identity"]["did"]

    exported = client.post(
        "/api/identity/recovery/export",
        headers={"X-Station-CSRF": csrf},
        json={
            "recovery_passphrase": TEST_ONLY_RECOVERY_PASSPHRASE,
            "recovery_passphrase_confirm": TEST_ONLY_RECOVERY_PASSPHRASE,
            "vault_passphrase": TEST_ONLY_VAULT_PASSPHRASE,
        },
    )
    assert exported.status_code == 200

    verified = client.post(
        "/api/identity/recovery/verify",
        headers={"X-Station-CSRF": csrf},
        files={"recovery_file": ("identity.tcrec", exported.content)},
        data={"recovery_passphrase": TEST_ONLY_RECOVERY_PASSPHRASE},
    )
    assert verified.status_code == 200
    return did


@windows_only
def test_the_whole_chain_publishes_exactly_what_the_user_approved(
    api: tuple[TestClient, str], sent_requests: list[httpx.Request]
) -> None:
    """Draft, sign with the real vault, send - over HTTP, end to end.

    The assertion that matters is the last one: the bytes that left the
    process verify under the DID the user was shown, over the canonical
    string the user read. Every intermediate step is checked against that
    same string rather than against a restatement of it.
    """
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}

    if not client.get("/api/identity").json()["capability"]["usable"]:
        pytest.skip("vault capability unavailable on this platform")

    did = _install_identity(client, csrf)

    # Nothing has been checked yet, so the gate is still shut.
    assert client.get("/api/compose/capability").json()["can_compose"] is False

    refreshed = client.post("/api/technocore/refresh", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["manifest_current"] is True

    capability = client.get("/api/compose/capability").json()
    assert capability["can_compose"] is True
    assert capability["blocking_reasons"] == []
    assert set(capability["room_class_markers"]) == {"p", "mb", "d", "e"}

    draft = client.post(
        "/api/compose/draft", headers=headers, json={"room": TEST_ROOM, "text": TEXT}
    )
    assert draft.status_code == 200
    drafted = draft.json()
    assert drafted["swept_text"] == TEXT
    assert sent_requests == [], "the draft step sent something"

    signed = client.post(
        "/api/compose/sign",
        headers=headers,
        json={
            "draft_id": drafted["draft_id"],
            "draft_digest": drafted["draft_digest"],
            "vault_passphrase": TEST_ONLY_VAULT_PASSPHRASE,
        },
    )
    assert signed.status_code == 200
    approval = signed.json()
    assert approval["did"] == did
    assert approval["canonical"] == f"{TEST_ROOM}|{approval['nonce']}|{TEXT}"
    assert sent_requests == [], "the sign step sent something"

    sent = client.post(
        "/api/compose/send",
        headers=headers,
        json={"send_token": approval["send_token"]},
    )
    assert sent.status_code == 200
    result = sent.json()
    assert result["outcome"] == "accepted"
    assert result["reconciliation_required"] is False

    assert len(sent_requests) == 1
    body = json.loads(sent_requests[0].content)
    assert set(body) == {"did", "sig", "nonce", "text"}
    assert body["text"] == TEXT

    payload = canonical_message(
        room=TEST_ROOM, nonce=body["nonce"], text=body["text"]
    )
    assert payload.canonical == approval["canonical"]
    verify_payload(payload, did=did, signature=body["sig"])


@windows_only
def test_a_wrong_vault_passphrase_refuses_the_signature(
    api: tuple[TestClient, str], sent_requests: list[httpx.Request]
) -> None:
    """The key is used for one call and only with the right passphrase.

    And the refusal happens at signing, before any nonce could be committed
    to a send.
    """
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}

    if not client.get("/api/identity").json()["capability"]["usable"]:
        pytest.skip("vault capability unavailable on this platform")

    _install_identity(client, csrf)
    client.post("/api/technocore/refresh", headers=headers)

    drafted = client.post(
        "/api/compose/draft", headers=headers, json={"room": TEST_ROOM, "text": TEXT}
    ).json()

    refused = client.post(
        "/api/compose/sign",
        headers=headers,
        json={
            "draft_id": drafted["draft_id"],
            "draft_digest": drafted["draft_digest"],
            "vault_passphrase": "TEST-ONLY-wrong-passphrase-9999",
        },
    )

    assert refused.status_code == 400
    assert refused.headers["x-station-compose-reason"] == "vault_locked"
    assert sent_requests == []


@windows_only
def test_the_lobby_is_refused_over_http(
    api: tuple[TestClient, str], sent_requests: list[httpx.Request]
) -> None:
    """INV-05, through the surface a user actually reaches."""
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}

    if not client.get("/api/identity").json()["capability"]["usable"]:
        pytest.skip("vault capability unavailable on this platform")

    _install_identity(client, csrf)
    client.post("/api/technocore/refresh", headers=headers)

    refused = client.post(
        "/api/compose/draft", headers=headers, json={"room": "lobby", "text": TEXT}
    )

    assert refused.status_code == 400
    assert refused.headers["x-station-compose-reason"] == "room_refused"
    assert sent_requests == []


@windows_only
def test_no_response_in_the_chain_carries_key_material(
    api: tuple[TestClient, str],
) -> None:
    """The seed never leaves the signer, so it never reaches the wire."""
    client, csrf = api
    headers = {"X-Station-CSRF": csrf}

    if not client.get("/api/identity").json()["capability"]["usable"]:
        pytest.skip("vault capability unavailable on this platform")

    _install_identity(client, csrf)
    client.post("/api/technocore/refresh", headers=headers)

    drafted = client.post(
        "/api/compose/draft", headers=headers, json={"room": TEST_ROOM, "text": TEXT}
    )
    signed = client.post(
        "/api/compose/sign",
        headers=headers,
        json={
            "draft_id": drafted.json()["draft_id"],
            "draft_digest": drafted.json()["draft_digest"],
            "vault_passphrase": TEST_ONLY_VAULT_PASSPHRASE,
        },
    )
    sent = client.post(
        "/api/compose/send",
        headers=headers,
        json={"send_token": signed.json()["send_token"]},
    )

    blob = (drafted.text + signed.text + sent.text).lower()
    assert TEST_ONLY_VAULT_PASSPHRASE.lower() not in blob
    for forbidden in ("seed", "private_key", "mnemonic", "passphrase"):
        assert forbidden not in blob
