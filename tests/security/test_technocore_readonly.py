"""Stage 3: the read-only Technocore client, and everything it must refuse.

No test here touches the network. Every request is answered by an
``httpx.MockTransport``, so the suite is deterministic and the live service is
never contacted - which is the specification's rule (§18.2) and also the only
way these tests could assert on a 429 or a redirect at all.

The client's safety rests on one structural fact: ``fetch`` takes a registry
entry, not a URL. Several tests below therefore assert that the dangerous
inputs are *unrepresentable* rather than merely rejected.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import inspect
import json
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from station_api.app import create_app
from station_api.config import Settings
from station_api.db.models import OfficialSourceSnapshot
from station_api.strict_json import StrictJsonError, loads_strict
from station_api.technocore.client import (
    ALLOWED_RESPONSE_HEADERS,
    MAX_ATTEMPTS,
    MAX_RETRY_AFTER_SECONDS,
    TIMEOUT,
    USER_AGENT,
    ReadOnlyTechnocoreClient,
    assert_allowed_url,
)
from station_api.technocore.errors import (
    ResponseTooLargeError,
    SourceFetchError,
    UnexpectedRedirectError,
)
from station_api.technocore.projection import DriftState, project
from station_api.technocore.service import TechnocoreService
from station_api.technocore.snapshot import (
    RETAINED_CHECKS,
    SnapshotOutcome,
    count_checks,
    count_snapshots,
)
from station_api.technocore.sources import (
    SOURCES,
    TECHNOCORE_ORIGIN,
    SourceId,
    get_source,
    required_sources,
)

from tests.conftest import TEST_PORT
from tests.security.conftest import establish_session
from tests.security.technocore_fixtures import build_documents

pytestmark = pytest.mark.security


def _handler(
    *, status_overrides: dict[str, int] | None = None
) -> httpx.MockTransport:
    """A transport that serves the canned official documents."""
    docs = build_documents()
    overrides = status_overrides or {}

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in overrides:
            return httpx.Response(overrides[path], text="nope")
        body = docs.get(path)
        if body is None:
            return httpx.Response(404, text="not found")
        if isinstance(body, dict):
            return httpx.Response(
                200,
                json=body,
                headers={
                    "ETag": '"abc123"',
                    "Last-Modified": "Sat, 30 Aug 2026 12:00:00 GMT",
                },
            )
        return httpx.Response(200, text=body, headers={"Content-Type": "text/plain"})

    return httpx.MockTransport(respond)


def _client(transport: httpx.MockTransport) -> ReadOnlyTechnocoreClient:
    return ReadOnlyTechnocoreClient(transport=transport, sleep=lambda _: None)


@pytest.fixture
def offline_client() -> ReadOnlyTechnocoreClient:
    return _client(_handler())


# ---------------------------------------------------------------------------
# The allow-list
# ---------------------------------------------------------------------------


def test_only_the_official_https_origin_is_allowed() -> None:
    assert TECHNOCORE_ORIGIN == "https://technocore.chat"
    for source in SOURCES:
        assert source.url.startswith("https://technocore.chat/")
        assert_allowed_url(source.url)


@pytest.mark.parametrize(
    "url",
    [
        "http://technocore.chat/config",
        "https://evil.example/config",
        "https://api.technocore.chat/config",
        "https://technocore.chat./config",
        "https://technocore.chat:8443/config",
        "https://user:pw@technocore.chat/config",
        "https://technocore.chat/config#frag",
        "https://93.184.216.34/config",
        "ftp://technocore.chat/config",
        "https://technocore.chat/a/../../etc/passwd",
        "https://technocore.chat/a/%2e%2e/b",
        "https://technocore.chat.evil.example/config",
    ],
)
def test_every_way_around_the_allow_list_is_refused(url: str) -> None:
    with pytest.raises(SourceFetchError):
        assert_allowed_url(url)


def test_the_client_takes_no_url_method_or_tls_setting() -> None:
    """Structural: the dangerous inputs do not exist as parameters."""
    fetch = inspect.signature(ReadOnlyTechnocoreClient.fetch)
    assert list(fetch.parameters) == ["self", "source"]

    init = inspect.signature(ReadOnlyTechnocoreClient.__init__)
    for forbidden in ("verify", "url", "method", "headers", "base_url", "ssl", "cert"):
        assert forbidden not in init.parameters


def test_tls_verification_is_never_disabled(api_source_root: Path) -> None:
    """No source line may switch verification off."""
    for path in api_source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "verify":
                pytest.fail(f"{path.name} passes verify= to a client")
        assert "_create_unverified_context" not in text
        assert "CERT_NONE" not in text


# ---------------------------------------------------------------------------
# Transport behaviour
# ---------------------------------------------------------------------------


def test_a_redirect_is_never_followed() -> None:
    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.example/x"})

    with pytest.raises(UnexpectedRedirectError):
        _client(httpx.MockTransport(redirect)).fetch(get_source(SourceId.CONFIG))


def test_every_timeout_phase_is_bounded() -> None:
    assert TIMEOUT.connect is not None
    assert TIMEOUT.read is not None
    assert TIMEOUT.write is not None
    assert TIMEOUT.pool is not None


def test_the_request_carries_no_identity_or_credential() -> None:
    seen: dict[str, httpx.Headers] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        return httpx.Response(200, json={"ok": True})

    _client(httpx.MockTransport(capture)).fetch(get_source(SourceId.CONFIG))

    headers = seen["headers"]
    assert headers["user-agent"] == USER_AGENT
    for forbidden in ("cookie", "authorization", "x-station-csrf", "x-did", "referer"):
        assert forbidden not in headers

    lowered = USER_AGENT.lower()
    for leak in ("windows", "tunik", "did:key", "python/"):
        assert leak not in lowered


def test_a_body_over_the_cap_is_refused_on_decompressed_bytes() -> None:
    """A small gzip that expands past the cap must not be buffered."""
    source = get_source(SourceId.HEALTH)
    payload = b"a" * (source.max_bytes + 1024)

    def bomb(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=gzip.compress(payload),
            headers={"Content-Encoding": "gzip", "Content-Type": "text/plain"},
        )

    with pytest.raises(ResponseTooLargeError):
        _client(httpx.MockTransport(bomb)).fetch(source)


def test_retries_are_bounded_and_then_give_up() -> None:
    attempts = {"count": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(503, text="down")

    with pytest.raises(SourceFetchError):
        _client(httpx.MockTransport(flaky)).fetch(get_source(SourceId.CONFIG))

    assert attempts["count"] == MAX_ATTEMPTS


def test_a_retry_after_header_is_honoured_but_clamped() -> None:
    waits: list[float] = []

    def rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "86400"}, text="slow down")

    client = ReadOnlyTechnocoreClient(
        transport=httpx.MockTransport(rate_limited), sleep=waits.append
    )
    with pytest.raises(SourceFetchError):
        client.fetch(get_source(SourceId.CONFIG))

    assert waits, "the client did not wait at all"
    assert max(waits) <= MAX_RETRY_AFTER_SECONDS


def test_a_transient_failure_then_success_is_recovered() -> None:
    state = {"calls": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(503, text="down")
        return httpx.Response(200, json={"service": "technocore-chat"})

    assert _client(httpx.MockTransport(flaky)).fetch(
        get_source(SourceId.CONFIG)
    ).status_code == 200


def test_only_allow_listed_headers_are_kept() -> None:
    assert ALLOWED_RESPONSE_HEADERS == ("content-type", "etag", "last-modified")

    def with_cookie(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True},
            headers={"Set-Cookie": "session=secret", "ETag": '"e1"'},
        )

    result = _client(httpx.MockTransport(with_cookie)).fetch(get_source(SourceId.CONFIG))

    assert result.etag == '"e1"'
    assert "secret" not in result.content_type + result.etag + result.last_modified


def test_the_hash_is_over_the_exact_response_bytes() -> None:
    body = b'{"service":"technocore-chat"}'

    def fixed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body, headers={"Content-Type": "application/json"}
        )

    result = _client(httpx.MockTransport(fixed)).fetch(get_source(SourceId.CONFIG))

    assert result.body == body
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.byte_count == len(body)


def test_fetched_at_is_timezone_aware_utc(
    offline_client: ReadOnlyTechnocoreClient,
) -> None:
    result = offline_client.fetch(get_source(SourceId.CONFIG))
    assert result.fetched_at.tzinfo is not None
    assert result.fetched_at.utcoffset() == datetime.now(UTC).utcoffset()


# ---------------------------------------------------------------------------
# Document parsing
# ---------------------------------------------------------------------------


def test_a_duplicate_json_key_is_refused() -> None:
    with pytest.raises(StrictJsonError):
        loads_strict(b'{"a": 1, "a": 2}')


@pytest.mark.parametrize(
    "literal", [b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}']
)
def test_non_finite_json_is_refused(literal: bytes) -> None:
    with pytest.raises(StrictJsonError):
        loads_strict(literal)


def test_an_oversize_document_is_refused() -> None:
    with pytest.raises(StrictJsonError):
        loads_strict(b'{"a": 1}', max_bytes=4)


def test_a_non_object_document_is_refused() -> None:
    with pytest.raises(StrictJsonError):
        loads_strict(b"[1, 2, 3]")


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


def _projected(documents: dict[str, Any]) -> Any:
    return project(
        {
            SourceId.OPENAPI: documents["openapi"],
            SourceId.AGENT_MANIFEST: documents["agent"],
        }
    )


def test_matching_documents_report_current() -> None:
    result = _projected(build_documents(parsed=True))
    assert result.state is DriftState.CURRENT
    assert result.critical_mismatches == ()


def _drop_message_lane(documents: dict[str, Any]) -> None:
    documents["openapi"]["paths"].pop("/r/{room}")


def _drop_note_lane(documents: dict[str, Any]) -> None:
    documents["openapi"]["paths"].pop("/kv/{ns}/{key}")


def _pad_the_signature(documents: dict[str, Any]) -> None:
    documents["agent"]["identity"]["signature_encoding"] = (
        "base64url, 88 characters, padded"
    )


def _reorder_the_payload(documents: dict[str, Any]) -> None:
    documents["agent"]["identity"]["message_signature_payload"] = "<room>|<text>|<nonce>"


def _swap_the_algorithm(documents: dict[str, Any]) -> None:
    documents["agent"]["identity"]["algorithms"] = ["Ed448"]


def _widen_the_name_pattern(documents: dict[str, Any]) -> None:
    documents["agent"]["conventions"]["name_pattern"] = "^[A-Za-z0-9_-]{1,64}$"


def _change_the_signature_pattern(documents: dict[str, Any]) -> None:
    schema = documents["openapi"]["paths"]["/r/{room}"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]["properties"]
    schema["sig"]["pattern"] = "^[A-Za-z0-9+/]{88}$"


def _drop_a_signed_field(documents: dict[str, Any]) -> None:
    schema = documents["openapi"]["paths"]["/r/{room}"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]["properties"]
    schema.pop("nonce")


@pytest.mark.parametrize(
    ("mutate", "expected_key"),
    [
        (_drop_message_lane, "signed_message_lane"),
        (_drop_note_lane, "signed_note_lane"),
        (_pad_the_signature, "signature_encoding"),
        (_reorder_the_payload, "message_signature_payload"),
        (_swap_the_algorithm, "identity_algorithm"),
        (_widen_the_name_pattern, "name_pattern"),
        (_change_the_signature_pattern, "signature_pattern"),
        (_drop_a_signed_field, "signed_fields_required"),
    ],
)
def test_a_critical_change_makes_the_manifest_not_current(
    mutate: Callable[[dict[str, Any]], None], expected_key: str
) -> None:
    """AC-15. Any of these breaks a signature, so the gate must close."""
    documents = build_documents(parsed=True)
    mutate(documents)
    result = _projected(documents)

    assert result.state is DriftState.DRIFTED
    assert expected_key in {item.field.key for item in result.critical_mismatches}


def test_a_capacity_change_is_a_warning_not_drift() -> None:
    """A limit change is real and shown, but a signature stays valid (§14.4)."""
    documents = build_documents(parsed=True)
    documents["agent"]["limits"]["message_chars"] = 8192
    result = _projected(documents)

    assert result.state is DriftState.CURRENT
    assert "message_chars" in {item.field.key for item in result.warnings}


def test_reordering_and_documentation_changes_are_not_drift() -> None:
    """Field order and prose must not be mistaken for a protocol change."""
    documents = build_documents(parsed=True)
    documents["agent"]["description"] = "totally rewritten prose"
    documents["agent"]["documentation"]["manual"] = "https://technocore.chat/other.txt"
    documents["agent"] = dict(reversed(list(documents["agent"].items())))

    assert _projected(documents).state is DriftState.CURRENT


def test_a_reworded_but_equivalent_encoding_statement_is_not_drift() -> None:
    documents = build_documents(parsed=True)
    documents["agent"]["identity"]["signature_encoding"] = (
        "Unpadded BASE64URL; the signature is 86 characters long."
    )
    assert _projected(documents).state is DriftState.CURRENT


def test_a_missing_required_document_is_never_current() -> None:
    documents = build_documents(parsed=True)
    result = project({SourceId.OPENAPI: documents["openapi"]})
    assert result.state is DriftState.DRIFTED


def test_remote_values_are_swept_and_truncated() -> None:
    """Level-1 authority is not a reason to trust bytes into a UI or a log."""
    documents = build_documents(parsed=True)
    documents["agent"]["identity"]["scheme"] = "did:key\x1b[31m\n" + "x" * 5000

    result = _projected(documents)
    observed = next(
        item.observed
        for item in result.observations
        if item.field.key == "identity_scheme"
    )
    assert "\x1b" not in observed
    assert "\n" not in observed
    assert len(observed) <= 210


# ---------------------------------------------------------------------------
# The service: state, persistence and fail-closed behaviour
# ---------------------------------------------------------------------------


def test_a_new_service_has_never_checked_and_contacts_nobody() -> None:
    def explode(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("constructing the service must not make a request")

    service = TechnocoreService(client=_client(httpx.MockTransport(explode)))
    assert service.status().state is DriftState.NEVER_CHECKED
    assert service.manifest_current is False


def test_a_successful_check_reports_current(engine: Engine) -> None:
    service = TechnocoreService(engine=engine, client=_client(_handler()))
    status = service.refresh()

    assert status.state is DriftState.CURRENT
    assert status.manifest_current is True
    assert status.last_success_at is not None
    assert len(status.sources) == len(SOURCES)


def test_a_network_failure_is_unavailable_and_closes_the_gate(engine: Engine) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    service = TechnocoreService(
        engine=engine, client=_client(httpx.MockTransport(down))
    )
    status = service.refresh()

    assert status.state is DriftState.UNAVAILABLE
    assert status.manifest_current is False


def test_a_later_failure_does_not_inherit_an_earlier_success(engine: Engine) -> None:
    """The load-bearing case: a stale success must never open the gate."""
    service = TechnocoreService(engine=engine, client=_client(_handler()))
    assert service.refresh().manifest_current is True

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    service._client = _client(httpx.MockTransport(down))  # noqa: SLF001
    after = service.refresh()

    assert after.state is DriftState.UNAVAILABLE
    assert after.manifest_current is False
    # The earlier success is still shown, beside the failure rather than
    # instead of it.
    assert after.last_success_at is not None


def test_a_failed_required_source_makes_the_whole_check_unavailable(
    engine: Engine,
) -> None:
    service = TechnocoreService(
        engine=engine,
        client=_client(_handler(status_overrides={"/openapi.json": 404})),
    )
    status = service.refresh()

    assert status.state is DriftState.UNAVAILABLE
    assert any("openapi" in reason for reason in status.reasons)


def test_a_supplementary_source_failure_does_not_decide_the_verdict(
    engine: Engine,
) -> None:
    """``/healthz`` has been seen answering 503 intermittently.

    It carries no protocol contract, so an infrastructure hiccup there must
    not flap the write gate - but it is still recorded and shown.
    """
    assert {source.id for source in required_sources()} == {
        SourceId.OPENAPI,
        SourceId.AGENT_MANIFEST,
    }

    service = TechnocoreService(
        engine=engine, client=_client(_handler(status_overrides={"/healthz": 503}))
    )
    status = service.refresh()

    assert status.state is DriftState.CURRENT
    health = next(item for item in status.sources if item.source_id == "health")
    assert health.outcome == SnapshotOutcome.FETCH_ERROR


def test_a_malformed_required_document_is_a_parse_error(engine: Engine) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/openapi.json":
            return httpx.Response(
                200, content=b'{"a": 1, "a": 2}', headers={"Content-Type": "application/json"}
            )
        return _handler().handler(request)  # type: ignore[attr-defined]

    service = TechnocoreService(
        engine=engine, client=_client(httpx.MockTransport(broken))
    )
    status = service.refresh()
    assert status.state is DriftState.UNAVAILABLE


def test_snapshots_are_written_and_retained_within_the_limit(engine: Engine) -> None:
    service = TechnocoreService(engine=engine, client=_client(_handler()))
    for _ in range(RETAINED_CHECKS + 5):
        service.refresh()

    assert count_checks(engine) == RETAINED_CHECKS
    assert count_snapshots(engine) == RETAINED_CHECKS * len(SOURCES)


def test_a_persisted_check_does_not_open_a_fresh_process(engine: Engine) -> None:
    """Restart semantics, simulated by a second service on the same database."""
    first = TechnocoreService(engine=engine, client=_client(_handler()))
    assert first.refresh().manifest_current is True
    assert count_checks(engine) >= 1

    restarted = TechnocoreService(engine=engine)
    assert restarted.status().state is DriftState.NEVER_CHECKED
    assert restarted.manifest_current is False


def test_the_database_never_stores_a_cookie_or_arbitrary_header(engine: Engine) -> None:
    def with_cookie(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=build_documents(parsed=True)["agent"],
            headers={"Set-Cookie": "sid=supersecret", "X-Tracking": "abc"},
        )

    service = TechnocoreService(
        engine=engine, client=_client(httpx.MockTransport(with_cookie))
    )
    service.refresh()

    with Session(engine) as session:
        rows = session.scalars(select(OfficialSourceSnapshot)).all()
        assert rows
        for row in rows:
            blob = " ".join(
                [
                    row.content_type,
                    row.etag,
                    row.last_modified,
                    row.snapshot_excerpt,
                    row.detail,
                ]
            )
            assert "supersecret" not in blob
            assert "X-Tracking" not in blob


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


def _app(
    settings: Settings, engine: Engine, transport: httpx.MockTransport
) -> FastAPI:
    return create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        technocore=TechnocoreService(engine=engine, client=_client(transport)),
    )


def test_status_requires_a_session(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    app = _app(settings, engine, _handler())
    with TestClient(app, base_url=base_url) as http:
        assert http.get("/api/technocore/status").status_code == 401


def test_refresh_requires_session_and_csrf(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    app = _app(settings, engine, _handler())
    with TestClient(app, base_url=base_url) as http:
        # CSRF is the outermost middleware, so an unauthenticated write is
        # refused there before the session check is reached. Either refusal is
        # correct; what matters is that it never runs.
        assert http.post("/api/technocore/refresh").status_code in {401, 403}

        csrf = establish_session(http, app)
        assert http.post("/api/technocore/refresh").status_code == 403

        ok = http.post("/api/technocore/refresh", headers={"X-Station-CSRF": csrf})
        assert ok.status_code == 200
        assert ok.json()["state"] == "current"


def test_reading_status_makes_no_outbound_request(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    calls = {"count": 0}

    def counting(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"ok": True})

    app = _app(settings, engine, httpx.MockTransport(counting))
    with TestClient(app, base_url=base_url) as http:
        assert establish_session(http, app)
        http.get("/api/technocore/status")
        http.get("/api/app/status")

    assert calls["count"] == 0


def test_the_response_carries_no_document_body(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    app = _app(settings, engine, _handler())
    with TestClient(app, base_url=base_url) as http:
        csrf = establish_session(http, app)
        payload = http.post(
            "/api/technocore/refresh", headers={"X-Station-CSRF": csrf}
        ).json()

    text = json.dumps(payload)
    # Distinctive strings that appear only inside the documents themselves.
    for body_marker in ("rendezvous", "env_prefix", "withheld", "room_classes"):
        assert body_marker not in text
    for secret in ("seed", "private", "passphrase", "vault"):
        assert secret not in text.lower()


def test_the_refresh_route_ignores_any_body(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """There is no URL, host or path for a caller to supply."""
    app = _app(settings, engine, _handler())
    with TestClient(app, base_url=base_url) as http:
        csrf = establish_session(http, app)
        response = http.post(
            "/api/technocore/refresh",
            headers={"X-Station-CSRF": csrf},
            json={"url": "https://evil.example/x"},
        )

    assert response.status_code == 200
    assert response.json()["origin"] == TECHNOCORE_ORIGIN


def test_the_write_gate_reads_the_same_verdict(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """API and gate must never disagree about whether the protocol is current."""
    app = _app(settings, engine, _handler())
    with TestClient(app, base_url=base_url) as http:
        csrf = establish_session(http, app)

        before = http.get("/api/write-gate").json()
        assert "manifest_current" in before["blocking_reasons"]

        http.post("/api/technocore/refresh", headers={"X-Station-CSRF": csrf})

        after = http.get("/api/write-gate").json()
        checks = {check["key"]: check for check in after["checks"]}
        assert checks["manifest_current"]["state"] == "passed"
        assert "manifest_current" not in after["blocking_reasons"]


def test_no_outbound_write_route_exists_even_when_every_check_passes(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """Preconditions met is not the same as a write being possible.

    Stage 3 finishes the precondition set. It ships no code that could send a
    message or a note, and this asserts that directly rather than trusting it.
    """
    app = _app(settings, engine, _handler())
    with TestClient(app, base_url=base_url) as http:
        csrf = establish_session(http, app)
        http.post("/api/technocore/refresh", headers={"X-Station-CSRF": csrf})

    paths = {getattr(route, "path", "") for route in app.routes}
    for path in paths:
        assert "say" not in path
        assert "/send" not in path
        assert "compose" not in path
        assert "sign" not in path


def test_tests_never_touch_the_real_installation(
    settings: Settings, data_dir: Path
) -> None:
    """No test may reach the user's real identity data."""
    resolved = str(settings.data_dir.resolve()).lower()
    assert str(data_dir.resolve()).lower() == resolved
    assert resolved.startswith(tempfile.gettempdir().lower())
    assert "technocorestation" not in resolved
