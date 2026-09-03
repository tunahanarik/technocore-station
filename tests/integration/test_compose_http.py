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

import inspect
import json
import sys
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import Settings
from station_api.routes.compose import send_message, sign_draft
from station_api.schemas import CREATE_IDENTITY_CONFIRMATION
from station_api.technocore.client import ReadOnlyTechnocoreClient
from station_api.technocore.service import TechnocoreService
from station_api.technocore.write_client import SignedWriteClient
from technocore_conform import canonical_message, verify_payload

from tests.conftest import (
    TEST_ONLY_RECOVERY_PASSPHRASE,
    TEST_ONLY_VAULT_PASSPHRASE,
)
from tests.security.compose_fixtures import (
    TEST_ROOM,
    ComposeHarness,
    build_harness,
    official_documents_transport,
)
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


# ---------------------------------------------------------------------------
# The blocking work runs off the event loop
#
# The composer harness is swapped in for ``app.state.compose`` so the whole
# chain can be walked over HTTP on any platform, without a DPAPI vault. The
# routes, the middleware, the session and the CSRF guard are the real ones;
# only the identity and the signer behind them are the published TEST-ONLY
# fixtures. Nothing here contacts Technocore.
# ---------------------------------------------------------------------------


def _app_with_harness(
    settings: Settings,
    engine: Engine,
    handler: object | None = None,
) -> tuple[FastAPI, ComposeHarness]:
    app = create_app(settings=settings, port=TEST_PORT, engine=engine, web_dist=None)
    harness = build_harness(engine, handler=handler)  # type: ignore[arg-type]
    app.state.compose = harness.service
    return app, harness


def _walk_to_a_send_token(client: TestClient, csrf: str) -> str:
    headers = {"X-Station-CSRF": csrf}
    drafted = client.post(
        "/api/compose/draft", headers=headers, json={"room": TEST_ROOM, "text": TEXT}
    )
    assert drafted.status_code == 200, drafted.text
    body = drafted.json()

    signed = client.post(
        "/api/compose/sign",
        headers=headers,
        json={"draft_id": body["draft_id"], "draft_digest": body["draft_digest"]},
    )
    assert signed.status_code == 200, signed.text
    token: str = signed.json()["send_token"]
    return token


def test_the_blocking_composer_routes_are_not_coroutines() -> None:
    """Structural, because the bug is invisible in a passing functional test.

    ``async def`` on these two reads perfectly and behaves perfectly until two
    requests overlap. FastAPI runs a sync path operation in a worker thread;
    an ``async`` one holds the event loop for the whole call, which here means
    an Argon2id derivation and a 15-second outbound read timeout.
    """
    assert not inspect.iscoroutinefunction(send_message)
    assert not inspect.iscoroutinefunction(sign_draft)


def test_a_send_in_flight_does_not_stall_another_request(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """The actual property, not the shape of the declaration.

    One send is parked inside the write client - the position a real 15-second
    read timeout puts it in - and a second, unrelated request has to be served
    while it sits there. On the event loop it would have waited for the first
    to finish.
    """
    entered = threading.Event()
    release = threading.Event()

    def blocking(request: httpx.Request) -> httpx.Response:
        entered.set()
        assert release.wait(30), "the parked send was never released"
        return httpx.Response(200, json={"ok": True})

    app, _ = _app_with_harness(settings, engine, blocking)

    with TestClient(app, base_url=base_url) as client:
        csrf = establish_session(client, app)
        token = _walk_to_a_send_token(client, csrf)

        sent: dict[str, httpx.Response] = {}

        def do_send() -> None:
            sent["response"] = client.post(
                "/api/compose/send",
                headers={"X-Station-CSRF": csrf},
                json={"send_token": token},
            )

        sender = threading.Thread(target=do_send)
        sender.start()
        try:
            assert entered.wait(30), "the send never reached the write client"

            started = time.monotonic()
            other = client.get("/api/compose/capability")
            elapsed = time.monotonic() - started

            assert other.status_code == 200
            assert elapsed < 5.0, (
                "an unrelated request waited on the parked send; the route is "
                "holding the event loop"
            )
        finally:
            release.set()
            sender.join(timeout=30)

        assert not sender.is_alive()
        assert sent["response"].status_code == 200
        assert sent["response"].json()["outcome"] == "accepted"


def test_two_concurrent_sends_over_http_publish_exactly_once(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """The property the threading change must not have cost.

    Moving the route into a worker thread means two clicks really can run at
    the same instant rather than being serialised by the loop. The approval
    token is consumed under a lock before anything leaves, so one wins and one
    is refused - and exactly one request reaches the transport.
    """
    app, harness = _app_with_harness(settings, engine)

    with TestClient(app, base_url=base_url) as client:
        csrf = establish_session(client, app)
        token = _walk_to_a_send_token(client, csrf)

        barrier = threading.Barrier(2)
        responses: list[httpx.Response] = []
        lock = threading.Lock()

        def click() -> None:
            barrier.wait(timeout=30)
            response = client.post(
                "/api/compose/send",
                headers={"X-Station-CSRF": csrf},
                json={"send_token": token},
            )
            with lock:
                responses.append(response)

        threads = [threading.Thread(target=click) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            assert not thread.is_alive()

    assert harness.writes.send_count == 1, "a double click published twice"
    assert sorted(response.status_code for response in responses) == [200, 409]
    refused = next(item for item in responses if item.status_code == 409)
    assert refused.headers["x-station-compose-reason"] == "approval_invalid"


def test_a_slow_signature_does_not_stall_another_request(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """The same property on the step that runs the key derivation.

    ``sign`` unlocks a passphrase-protected vault, which is an Argon2id
    derivation sized to take real time, and it holds a database transaction
    while it does.
    """
    entered = threading.Event()
    release = threading.Event()

    app, harness = _app_with_harness(settings, engine)
    inner = harness.service._signer

    class _SlowSigner:
        def sign(self, payload, *, identity_id, passphrase):  # type: ignore[no-untyped-def]
            entered.set()
            assert release.wait(30), "the parked signature was never released"
            return inner.sign(payload, identity_id=identity_id, passphrase=passphrase)

    harness.service._signer = _SlowSigner()

    with TestClient(app, base_url=base_url) as client:
        csrf = establish_session(client, app)
        headers = {"X-Station-CSRF": csrf}
        drafted = client.post(
            "/api/compose/draft",
            headers=headers,
            json={"room": TEST_ROOM, "text": TEXT},
        ).json()

        signed: dict[str, httpx.Response] = {}

        def do_sign() -> None:
            signed["response"] = client.post(
                "/api/compose/sign",
                headers=headers,
                json={
                    "draft_id": drafted["draft_id"],
                    "draft_digest": drafted["draft_digest"],
                },
            )

        signer_thread = threading.Thread(target=do_sign)
        signer_thread.start()
        try:
            assert entered.wait(30), "the signature never reached the signer"

            started = time.monotonic()
            other = client.get("/api/compose/capability")
            elapsed = time.monotonic() - started

            assert other.status_code == 200
            assert elapsed < 5.0, "the sign route is holding the event loop"
        finally:
            release.set()
            signer_thread.join(timeout=30)

        assert not signer_thread.is_alive()
        assert signed["response"].status_code == 200
