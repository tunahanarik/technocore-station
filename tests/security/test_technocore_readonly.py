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
from station_api.technocore.projection import (
    EXPECTED_DID_CHARS,
    EXPECTED_DID_PATTERN,
    EXPECTED_NAME_PATTERN,
    EXPECTED_NONCE_PATTERN,
    EXPECTED_SIGNATURE_PATTERN,
    MAX_PROSE_CHARS,
    NONCE_MAX_DIGITS,
    NONCE_MIN_DIGITS,
    PLANNED_BODY_FIELDS,
    PROTOCOL_FIELDS,
    STATION_FIELD_LENGTHS,
    UNDERSTOOD_FIELD_KEYS,
    DriftState,
    FieldOutcome,
    Lane,
    SentLength,
    project,
)
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
from technocore_conform import (
    NAME_PATTERN,
    NONCE_PATTERN,
    SIGNATURE_CHARS,
    SIGNATURE_PATTERN,
)

from tests.conftest import TEST_PORT
from tests.security.conftest import establish_session
from tests.security.technocore_fixtures import (
    build_documents,
    message_body_schema,
    note_body_schema,
    signed_lane,
)

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
#
# The documents these run against are generated by the pinned official
# generator, not hand-written. Stage 3's fixture put the signed-lane
# constraints under ``schema.properties``; the reference publishes them under
# ``schema.dependentSchemas.did``, and the fixture and the projection agreed
# with each other while both were wrong. See
# ``technocore_reference/PROVENANCE.md``.
# ---------------------------------------------------------------------------


def _projected(documents: dict[str, Any]) -> Any:
    return project(
        {
            SourceId.OPENAPI: documents["openapi"],
            SourceId.AGENT_MANIFEST: documents["agent"],
        }
    )


def _lanes(documents: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    openapi = documents["openapi"]
    return message_body_schema(openapi), note_body_schema(openapi)


def test_matching_documents_report_current() -> None:
    result = _projected(build_documents(parsed=True))
    assert result.state is DriftState.CURRENT
    assert result.critical_mismatches == ()
    assert result.critical_unevaluable == ()


def test_the_official_documents_raise_no_missing_field_alarm() -> None:
    """The regression. Stage 3 reported four critical fields as ``<yok>``.

    They were not missing; they were being looked for under ``properties``,
    where the reference publishes only a description. Every critical field
    must be *found* in the official document, whatever its verdict.
    """
    result = _projected(build_documents(parsed=True))

    unread = [
        item.field.key
        for item in result.observations
        if item.outcome in (FieldOutcome.MISSING, FieldOutcome.UNSUPPORTED)
    ]
    assert unread == [], f"fields not found in the official document: {unread}"


def test_every_signed_credential_constraint_is_actually_checked() -> None:
    """Both lanes publish the same facts, and both are projected."""
    keys = {field.key for field in PROTOCOL_FIELDS}
    for prefix in ("", "note_"):
        for suffix in (
            "signature_type",
            "signature_pattern",
            "signature_min_length",
            "signature_max_length",
            "nonce_type",
            "nonce_pattern",
            "signed_fields_required",
            "did_pattern",
            "did_max_length",
        ):
            assert f"{prefix}{suffix}" in keys, f"{prefix}{suffix} is not projected"


# --- mutations that must close the gate ------------------------------------


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


def _reorder_the_note_payload(documents: dict[str, Any]) -> None:
    documents["agent"]["identity"]["note_signature_payload"] = (
        "<namespace>|<nonce>|<key>|<value>"
    )


def _swap_the_algorithm(documents: dict[str, Any]) -> None:
    documents["agent"]["identity"]["algorithms"] = ["Ed448"]


def _drop_the_scheme(documents: dict[str, Any]) -> None:
    documents["agent"]["identity"]["scheme"] = "did:web"


def _widen_the_name_pattern(documents: dict[str, Any]) -> None:
    documents["agent"]["conventions"]["name_pattern"] = "^[A-Za-z0-9_-]{1,64}$"


def _change_the_signature_pattern(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["sig"]["pattern"] = "^[A-Za-z0-9+/]{88}$"


def _widen_the_signature_pattern(documents: dict[str, Any]) -> None:
    """The exact pattern Stage 3 expected, which is looser than the real one.

    ``[A-Za-z0-9_-]{86}`` accepts a final character whose four slack bits are
    not zero. A 64-byte Ed25519 signature never produces one, so a server
    publishing this would be accepting signatures we do not generate.
    """
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["sig"]["pattern"] = "^[A-Za-z0-9_-]{86}$"


def _change_the_note_signature_pattern(documents: dict[str, Any]) -> None:
    _, note = _lanes(documents)
    signed_lane(note)["properties"]["sig"]["pattern"] = "^[A-Za-z0-9_-]{86}$"


def _change_the_nonce_pattern(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["nonce"]["pattern"] = "^[0-9]{1,32}$"


def _stringify_the_signature_length(documents: dict[str, Any]) -> None:
    """``"86"`` is not ``86``: a string bound is a different schema."""
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["sig"]["maxLength"] = "86"


def _boolify_the_signature_length(documents: dict[str, Any]) -> None:
    """``True == 1`` in Python, and a published ``true`` is not a length."""
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["sig"]["minLength"] = True


def _drop_the_signature_min_length(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["sig"].pop("minLength")


def _drop_the_signature_max_length(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["sig"].pop("maxLength")


def _retype_the_nonce_as_integer(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["nonce"]["type"] = "integer"


def _stringify_the_did_length(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    message["properties"]["did"]["maxLength"] = "56"


def _change_the_did_pattern(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    message["properties"]["did"]["pattern"] = "^did:key:.+$"


def _drop_sig_from_required(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    signed_lane(message)["required"] = ["nonce"]


def _drop_nonce_from_required(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    signed_lane(message)["required"] = ["sig"]


def _drop_sig_from_note_required(documents: dict[str, Any]) -> None:
    _, note = _lanes(documents)
    signed_lane(note)["required"] = ["nonce"]


def _drop_nonce_from_note_required(documents: dict[str, Any]) -> None:
    _, note = _lanes(documents)
    signed_lane(note)["required"] = ["sig"]


def _empty_the_required_list(documents: dict[str, Any]) -> None:
    message, _ = _lanes(documents)
    signed_lane(message)["required"] = []


@pytest.mark.parametrize(
    ("mutate", "expected_key"),
    [
        (_drop_message_lane, "signed_message_lane"),
        (_drop_note_lane, "signed_note_lane"),
        (_pad_the_signature, "signature_encoding"),
        (_reorder_the_payload, "message_signature_payload"),
        (_reorder_the_note_payload, "note_signature_payload"),
        (_swap_the_algorithm, "identity_algorithm"),
        (_drop_the_scheme, "identity_scheme"),
        (_widen_the_name_pattern, "name_pattern"),
        (_change_the_signature_pattern, "signature_pattern"),
        (_widen_the_signature_pattern, "signature_pattern"),
        (_change_the_note_signature_pattern, "note_signature_pattern"),
        (_change_the_nonce_pattern, "nonce_pattern"),
        (_stringify_the_signature_length, "signature_max_length"),
        (_boolify_the_signature_length, "signature_min_length"),
        (_drop_the_signature_min_length, "signature_min_length"),
        (_drop_the_signature_max_length, "signature_max_length"),
        (_retype_the_nonce_as_integer, "nonce_type"),
        (_stringify_the_did_length, "did_max_length"),
        (_change_the_did_pattern, "did_pattern"),
        (_drop_sig_from_required, "signed_fields_required"),
        (_drop_nonce_from_required, "signed_fields_required"),
        (_drop_sig_from_note_required, "note_signed_fields_required"),
        (_drop_nonce_from_note_required, "note_signed_fields_required"),
        (_empty_the_required_list, "signed_fields_required"),
    ],
)
def test_a_critical_change_makes_the_manifest_not_current(
    mutate: Callable[[dict[str, Any]], None], expected_key: str
) -> None:
    """AC-15. Any of these breaks a signature, so the gate must close."""
    documents = build_documents(parsed=True)
    mutate(documents)
    result = _projected(documents)

    assert result.state is not DriftState.CURRENT
    assert expected_key in {item.field.key for item in result.critical_failures}


def test_a_missing_conditional_schema_is_not_rescued_by_properties() -> None:
    """The wrong, older fixture shape must not pass.

    Publishing the constraints on ``properties`` and dropping
    ``dependentSchemas`` describes a body where ``sig`` and ``nonce`` are
    never *required* on the signed lane. That is a real weakening, and it is
    the shape Stage 3 believed was normal, so it is asserted explicitly.
    """
    documents = build_documents(parsed=True)
    message, _ = _lanes(documents)
    lane = signed_lane(message)

    message["properties"]["sig"] = dict(lane["properties"]["sig"])
    message["properties"]["nonce"] = dict(lane["properties"]["nonce"])
    message.pop("dependentSchemas")

    result = _projected(documents)
    assert result.state is not DriftState.CURRENT
    assert "signature_pattern" in {item.field.key for item in result.critical_failures}


# --- schemas we do not understand must fail closed, not pass ---------------


@pytest.mark.parametrize(
    "keyword", ["$ref", "allOf", "oneOf", "not", "if", "$dynamicRef"]
)
def test_an_unsupported_conditional_schema_is_never_current(keyword: str) -> None:
    """A keyword that can redirect or negate meaning stops the check.

    The gate stays shut, and the reason says the schema could not be read -
    not that the server changed the signature format.
    """
    documents = build_documents(parsed=True)
    message, _ = _lanes(documents)
    message[keyword] = {"$comment": "something this projection cannot evaluate"}

    result = _projected(documents)

    assert result.state is DriftState.UNAVAILABLE
    unsupported = [
        item for item in result.observations if item.outcome is FieldOutcome.UNSUPPORTED
    ]
    assert unsupported
    assert any(keyword in item.problem for item in unsupported)
    assert all("dogrulanamadi" in item.reason for item in unsupported)


def test_a_replaced_dependent_schema_is_unsupported_not_current() -> None:
    documents = build_documents(parsed=True)
    message, _ = _lanes(documents)
    message["dependentSchemas"] = {"did": "see the manual"}

    assert _projected(documents).state is DriftState.UNAVAILABLE


def test_a_missing_dependent_schema_is_reported_as_unverifiable() -> None:
    documents = build_documents(parsed=True)
    message, _ = _lanes(documents)
    message.pop("dependentSchemas")

    result = _projected(documents)
    assert result.state is DriftState.UNAVAILABLE
    assert any("dependentSchemas" in reason for reason in result.reasons)


def test_an_unevaluable_field_never_claims_the_server_changed_anything() -> None:
    """AC-15 honesty. Evidence we do not have must not be asserted."""
    documents = build_documents(parsed=True)
    message, _ = _lanes(documents)
    message.pop("dependentSchemas")

    result = _projected(documents)
    joined = " ".join(result.reasons).lower()

    assert "dogrulanamadi" in joined
    assert "beklenen" not in joined, "an unread field must not be reported as a diff"


def test_a_shadow_key_cannot_redirect_a_pointer() -> None:
    """A remote document must not be able to answer for a nested location.

    The old reader split a dotted path and matched the longest key present, so
    a literal top-level key spelled like the path shadowed the real one. The
    pointer is walked segment by segment now, so these decoys are ignored.
    """
    documents = build_documents(parsed=True)
    forged = {
        "properties": {
            "did": {"pattern": EXPECTED_DID_PATTERN, "maxLength": 56},
            "sig": {"pattern": "^.*$"},
            "nonce": {"pattern": "^.*$"},
        },
        "dependentSchemas": {
            "did": {
                "required": ["sig", "nonce"],
                "properties": {
                    "sig": {"type": "string", "pattern": "^.*$"},
                    "nonce": {"type": "string", "pattern": "^.*$"},
                },
            }
        },
    }
    documents["openapi"]["paths./r/{room}.post.requestBody"] = forged
    documents["openapi"]["paths"]["/r/{room}.post"] = forged

    # The genuine location is untouched, so the verdict is unchanged.
    assert _projected(documents).state is DriftState.CURRENT

    # And when the genuine location is gone, the decoy cannot rescue it.
    documents["openapi"]["paths"].pop("/r/{room}")
    assert _projected(documents).state is not DriftState.CURRENT


# ---------------------------------------------------------------------------
# The combined meaning of a body schema
#
# Finding the right value somewhere in a schema does not establish that the
# schema accepts our request. Three documents that reject every signed write
# were reporting `current`, because the projection read the keys it wanted and
# ignored everything else at the same level. These fix the family, not the
# three examples: the evaluator works from an allow-list, so a keyword nobody
# has thought of yet is unevaluable rather than invisible.
# ---------------------------------------------------------------------------

#: Both lanes go through one evaluator, so both are asserted every time. The
#: note lane silently losing a check is exactly what a copy-pasted
#: single-lane test misses.
_LANES = [
    pytest.param(message_body_schema, "text", id="message"),
    pytest.param(note_body_schema, "value", id="note"),
]

BodyOf = Callable[[dict[str, Any]], dict[str, Any]]


def _closed(documents: dict[str, Any]) -> Any:
    result = _projected(documents)
    assert result.state is not DriftState.CURRENT, (
        "this schema rejects every signed request and must not report current"
    )
    return result


# --- a field node that matches nothing --------------------------------------


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
@pytest.mark.parametrize("credential", ["sig", "nonce"])
def test_a_negated_credential_schema_is_not_current(
    body_of: BodyOf, payload: str, credential: str
) -> None:
    """``not: {}`` beside a correct pattern accepts nothing at all.

    The pattern, the type and both lengths are still exactly right, and were
    still being read. ``not: {}`` negates the empty schema, which every value
    satisfies, so the node matches no value whatsoever - no signature would be
    accepted, and the check said `current`.
    """
    del payload
    documents = build_documents(parsed=True)
    signed_lane(body_of(documents["openapi"]))["properties"][credential]["not"] = {}

    result = _closed(documents)
    assert result.state is DriftState.UNAVAILABLE
    assert any("not" in item.problem for item in result.critical_unevaluable)


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
@pytest.mark.parametrize(
    "keyword", ["$ref", "allOf", "oneOf", "if", "enum", "const", "anyOf"]
)
def test_any_unreadable_keyword_in_a_field_node_closes_the_gate(
    body_of: BodyOf, payload: str, keyword: str
) -> None:
    """The family, not the three examples.

    The evaluator names what it understands. Anything else - including a
    keyword this test does not anticipate - makes the node unevaluable.
    """
    del payload
    documents = build_documents(parsed=True)
    signed_lane(body_of(documents["openapi"]))["properties"]["sig"][keyword] = {}

    assert _closed(documents).state is DriftState.UNAVAILABLE


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_an_unreadable_keyword_on_the_unconditional_did_closes_the_gate(
    body_of: BodyOf, payload: str
) -> None:
    """``did`` selects the signed lane, so its own node is read too."""
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["properties"]["did"]["not"] = {}

    assert _closed(documents).state is DriftState.UNAVAILABLE


# --- constraints published at both levels apply together --------------------


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_an_unconditional_length_that_contradicts_the_conditional_one(
    body_of: BodyOf, payload: str
) -> None:
    """``maxLength: 1`` beside a conditional ``minLength: 86``.

    Keywords at a level are conjunctive: both bounds apply, and no string is
    at once no longer than one character and at least eighty-six. Reported as
    a mismatch rather than as unsupported, because it was evaluated - this is
    a demonstrated fact about the document, not a gap in what we can read.
    """
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["properties"]["sig"]["maxLength"] = 1

    result = _closed(documents)
    assert result.state is DriftState.DRIFTED
    assert any(
        "uzunluk araligi bos" in item.reason for item in result.critical_mismatches
    )


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_an_unconditional_type_that_contradicts_the_conditional_one(
    body_of: BodyOf, payload: str
) -> None:
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["properties"]["nonce"]["type"] = "integer"

    assert _closed(documents).state is DriftState.DRIFTED


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_second_unconditional_pattern_is_not_silently_ignored(
    body_of: BodyOf, payload: str
) -> None:
    """Two regexes on one value intersect; this module does not compute that.

    Unsupported rather than a mismatch: a different pattern is not by itself a
    contradiction, and calling one would assert more than was checked.
    """
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["properties"]["sig"]["pattern"] = "^[a-z]+$"

    assert _closed(documents).state is DriftState.UNAVAILABLE


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_repeated_identical_constraint_is_accepted(
    body_of: BodyOf, payload: str
) -> None:
    """Publishing the same rule twice says nothing new, and must not alarm."""
    del payload
    documents = build_documents(parsed=True)
    body = body_of(documents["openapi"])
    conditional = signed_lane(body)["properties"]["sig"]
    body["properties"]["sig"] = {
        "description": "unchanged prose",
        "type": conditional["type"],
        "pattern": conditional["pattern"],
        "minLength": conditional["minLength"],
        "maxLength": conditional["maxLength"],
    }

    assert _projected(documents).state is DriftState.CURRENT


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_wider_unconditional_bound_is_not_a_contradiction(
    body_of: BodyOf, payload: str
) -> None:
    """A looser bound leaves the conditional one deciding; nothing is empty."""
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["properties"]["sig"]["minLength"] = 1

    assert _projected(documents).state is DriftState.CURRENT


# --- anyOf must leave a branch a signed body can satisfy --------------------


def test_the_reference_really_publishes_the_two_branch_any_of() -> None:
    """The shape the evaluator supports is the shape upstream actually ships.

    Asserted against the generated reference so that supporting exactly this
    form stays an evidence-backed decision rather than a guess.
    """
    documents = build_documents(parsed=True)
    branches = message_body_schema(documents["openapi"])["anyOf"]

    assert branches == [{"required": ["from"]}, {"required": ["did"]}]
    assert _projected(documents).state is DriftState.CURRENT


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_an_any_of_that_forbids_the_did_is_not_current(
    body_of: BodyOf, payload: str
) -> None:
    """``anyOf: [{"not": {"required": ["did"]}}]`` forbids the signed lane.

    The previous reasoning was that ``anyOf`` could only *add* a constraint,
    so it could not loosen ``dependentSchemas`` - true, and beside the point.
    A constraint it adds can reject us, and this one rejects every body
    carrying the field that selects the signed lane.
    """
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["anyOf"] = [{"not": {"required": ["did"]}}]

    assert _closed(documents).state is DriftState.UNAVAILABLE


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_an_any_of_with_no_satisfiable_branch_is_not_current(
    body_of: BodyOf, payload: str
) -> None:
    """Every branch readable, none reachable by a signed body.

    A conflict rather than unsupported: each branch was understood, and none
    can be met by a body carrying did/sig/nonce and the payload.
    """
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["anyOf"] = [
        {"required": ["from"]},
        {"required": ["apiKey"]},
    ]

    assert _closed(documents).state is DriftState.DRIFTED


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_the_signed_branch_may_name_the_payload_field(
    body_of: BodyOf, payload: str
) -> None:
    """A branch a signed body does satisfy keeps the verdict current."""
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["anyOf"] = [
        {"required": ["from"]},
        {"required": ["did", payload]},
    ]

    assert _projected(documents).state is DriftState.CURRENT


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_an_any_of_branch_with_an_unreadable_shape_closes_the_gate(
    body_of: BodyOf, payload: str
) -> None:
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["anyOf"] = [{"properties": {"did": {}}}]

    assert _closed(documents).state is DriftState.UNAVAILABLE


# --- documentation and ordering are still not protocol changes --------------


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_annotations_anywhere_in_the_body_are_not_a_protocol_change(
    body_of: BodyOf, payload: str
) -> None:
    """The allow-list separates prose from constraints, so this must pass.

    A fixed key list that treated ``description`` like a validation keyword
    would turn every upstream wording change into a closed write gate.
    """
    del payload
    documents = build_documents(parsed=True)
    body = body_of(documents["openapi"])
    lane = signed_lane(body)

    for node in (body["properties"]["sig"], body["properties"]["did"], body):
        node["description"] = "rewritten prose"
        node["$comment"] = "an editorial note"
    for node in lane["properties"].values():
        node["title"] = "Signature"
        node["examples"] = ["not a constraint"]

    assert _projected(documents).state is DriftState.CURRENT


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_reordering_the_body_schema_keys_is_not_a_protocol_change(
    body_of: BodyOf, payload: str
) -> None:
    del payload
    documents = build_documents(parsed=True)
    body = body_of(documents["openapi"])
    reordered = dict(reversed(list(body.items())))
    body.clear()
    body.update(reordered)

    assert _projected(documents).state is DriftState.CURRENT


# ---------------------------------------------------------------------------
# Allowed keys are not enough: their values decide too
#
# The allow-list fixed *which* keywords may appear. It did not read what they
# said. Eleven single-key mutations - each a schema that refuses the request
# Station would send - still reported `current`, on both lanes, because the
# evaluator checked names and skipped values:
#
#   * `type` and `required` were never read on the body or the conditional
#     node, so a body typed `"string"` and a body requiring a field we do not
#     send both looked fine;
#   * only `dependentSchemas.did` was consulted, though a signed body also
#     carries `sig`, `nonce` and its payload field - so a dependency keyed on
#     any of those applied to us unseen;
#   * only `sig` and `nonce` were read inside the conditional properties, so a
#     `did` sitting there went unexamined;
#   * a malformed bound (`"1"`, `null`) read as *no bound at all*, which is
#     the dangerous direction to guess in.
#
# The rule these settle: a key on the allow-list must have its value checked
# and its effect on the planned signed body evaluated.
# ---------------------------------------------------------------------------


def _mutate_body_type(body: dict[str, Any], payload: str) -> None:
    body["type"] = "string"


def _mutate_conditional_type(body: dict[str, Any], payload: str) -> None:
    signed_lane(body)["type"] = "string"


def _mutate_extra_required(body: dict[str, Any], payload: str) -> None:
    body["required"] = [*body["required"], "extraProof"]


def _mutate_conditional_did_negated(body: dict[str, Any], payload: str) -> None:
    signed_lane(body)["properties"]["did"] = {"not": {}}


def _mutate_sig_dependency_negated(body: dict[str, Any], payload: str) -> None:
    body["dependentSchemas"]["sig"] = {"not": {}}


def _mutate_did_type(body: dict[str, Any], payload: str) -> None:
    body["properties"]["did"]["type"] = "integer"


def _mutate_did_min_length(body: dict[str, Any], payload: str) -> None:
    body["properties"]["did"]["minLength"] = 100


def _mutate_nonce_max_length(body: dict[str, Any], payload: str) -> None:
    signed_lane(body)["properties"]["nonce"]["maxLength"] = 0


def _mutate_sig_max_length_string(body: dict[str, Any], payload: str) -> None:
    body["properties"]["sig"]["maxLength"] = "1"


def _mutate_sig_type_null(body: dict[str, Any], payload: str) -> None:
    body["properties"]["sig"]["type"] = None


def _mutate_any_of_required_null(body: dict[str, Any], payload: str) -> None:
    body["anyOf"] = [{"required": None}]


#: Each row is one single-key mutation and the verdict it must produce.
#:
#: ``drifted`` where the schema is well-formed and readable and simply refuses
#: us - a contract difference we can state. ``unavailable`` where the schema is
#: malformed or uses a form outside the supported shape: there the honest
#: answer is that it could not be evaluated, not a claim about what the server
#: decided. Both leave ``manifest_current`` false.
_VALUE_MUTATIONS = [
    ("body-type-not-object", _mutate_body_type, DriftState.DRIFTED),
    ("conditional-type-not-object", _mutate_conditional_type, DriftState.DRIFTED),
    ("body-requires-unknown-field", _mutate_extra_required, DriftState.DRIFTED),
    ("conditional-did-negated", _mutate_conditional_did_negated, DriftState.UNAVAILABLE),
    ("sig-dependency-negated", _mutate_sig_dependency_negated, DriftState.UNAVAILABLE),
    ("did-type-integer", _mutate_did_type, DriftState.DRIFTED),
    ("did-min-length-above-max", _mutate_did_min_length, DriftState.DRIFTED),
    ("nonce-max-length-zero", _mutate_nonce_max_length, DriftState.DRIFTED),
    ("sig-max-length-string", _mutate_sig_max_length_string, DriftState.UNAVAILABLE),
    ("sig-type-null", _mutate_sig_type_null, DriftState.UNAVAILABLE),
    ("any-of-required-null", _mutate_any_of_required_null, DriftState.UNAVAILABLE),
]


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        pytest.param(mutate, expected, id=label)
        for label, mutate, expected in _VALUE_MUTATIONS
    ],
)
def test_a_schema_that_refuses_the_signed_body_is_never_current(
    body_of: BodyOf,
    payload: str,
    mutate: Callable[[dict[str, Any], str], None],
    expected: DriftState,
) -> None:
    """Every one of these reported `current` before the values were read."""
    documents = build_documents(parsed=True)
    mutate(body_of(documents["openapi"]), payload)

    result = _projected(documents)

    assert result.state is not DriftState.CURRENT
    assert result.state is expected
    assert result.critical_failures != ()


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_malformed_bound_is_not_read_as_no_bound(
    body_of: BodyOf, payload: str
) -> None:
    """The direction of the guess matters.

    Treating ``maxLength: "1"`` as "no ceiling published" is the permissive
    reading of a schema nobody can satisfy. It is reported as unreadable.
    """
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["properties"]["sig"]["maxLength"] = "1"

    result = _projected(documents)
    assert result.state is DriftState.UNAVAILABLE
    assert any("sayi degil" in item.problem for item in result.critical_unevaluable)


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
@pytest.mark.parametrize("published", [None, False, 0, [], {}, "string"])
def test_a_required_list_that_is_not_a_list_of_names_is_unreadable(
    body_of: BodyOf, payload: str, published: object
) -> None:
    """``required: null`` is not the same as no ``required``.

    ``[]`` is the interesting row: an empty list is a *valid* required list,
    so it must stay readable rather than being swept up with the malformed
    ones.
    """
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["required"] = published

    result = _projected(documents)
    if published == []:
        assert result.state is DriftState.CURRENT
    else:
        assert result.state is not DriftState.CURRENT


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
@pytest.mark.parametrize("published", [None, 0, False, [], {"const": "x"}])
def test_a_type_that_is_not_a_string_is_unreadable(
    body_of: BodyOf, payload: str, published: object
) -> None:
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["properties"]["did"]["type"] = published

    assert _projected(documents).state is DriftState.UNAVAILABLE


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_negative_length_bound_is_unreadable(body_of: BodyOf, payload: str) -> None:
    del payload
    documents = build_documents(parsed=True)
    signed_lane(body_of(documents["openapi"]))["properties"]["sig"]["minLength"] = -1

    assert _projected(documents).state is DriftState.UNAVAILABLE


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_boolean_is_not_accepted_as_a_length(body_of: BodyOf, payload: str) -> None:
    """``True == 1`` in Python; a published ``true`` is still not a length."""
    del payload
    documents = build_documents(parsed=True)
    signed_lane(body_of(documents["openapi"]))["properties"]["sig"]["maxLength"] = True

    assert _projected(documents).state is DriftState.UNAVAILABLE


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_pattern_that_is_not_a_string_is_unreadable(
    body_of: BodyOf, payload: str
) -> None:
    del payload
    documents = build_documents(parsed=True)
    signed_lane(body_of(documents["openapi"]))["properties"]["nonce"]["pattern"] = None

    assert _projected(documents).state is DriftState.UNAVAILABLE


# --- every dependency a signed body switches on is read ---------------------


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
@pytest.mark.parametrize("keyed_on", ["did", "sig", "nonce"])
def test_a_dependency_on_any_carried_field_applies(
    body_of: BodyOf, payload: str, keyed_on: str
) -> None:
    """``dependentSchemas`` applies its subschema to the whole body.

    A signed body carries all three credentials, so a dependency keyed on any
    of them switches on. Reading only ``did`` left the others unexamined.
    """
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["dependentSchemas"][keyed_on] = {
        "required": ["extraProof"]
    }

    result = _projected(documents)
    assert result.state is DriftState.DRIFTED
    assert any("extraProof" in item.reason for item in result.critical_mismatches)


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_dependency_on_the_payload_field_applies(
    body_of: BodyOf, payload: str
) -> None:
    """``text`` on the message lane, ``value`` on the note lane."""
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["dependentSchemas"][payload] = {"type": "string"}

    assert _projected(documents).state is DriftState.DRIFTED


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_dependency_on_a_field_we_do_not_send_does_not_apply(
    body_of: BodyOf, payload: str
) -> None:
    """``from`` is ignored on the signed lane, so Station does not send it.

    A dependency keyed on it can never switch on for our body, and treating it
    as binding would close the gate over a rule that does not reach us.
    """
    del payload
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["dependentSchemas"]["from"] = {"not": {}}

    assert _projected(documents).state is DriftState.CURRENT


# --- the bounds are judged against what Station actually sends -------------


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
@pytest.mark.parametrize(
    ("field", "bound", "value"),
    [
        ("did", "minLength", EXPECTED_DID_CHARS + 1),
        ("did", "maxLength", EXPECTED_DID_CHARS - 1),
        ("sig", "minLength", SIGNATURE_CHARS + 1),
        ("sig", "maxLength", SIGNATURE_CHARS - 1),
        ("nonce", "minLength", NONCE_MAX_DIGITS + 1),
        ("nonce", "maxLength", NONCE_MIN_DIGITS - 1),
    ],
)
def test_a_bound_excluding_what_station_sends_closes_the_gate(
    body_of: BodyOf, payload: str, field: str, bound: str, value: int
) -> None:
    """A bound is not wrong for being unusual, but for excluding our value.

    This is the comparison the name-only allow-list could not make: it needs a
    number from our side of the protocol, and those come from
    ``STATION_FIELD_LENGTHS``.
    """
    del payload
    documents = build_documents(parsed=True)
    body = body_of(documents["openapi"])
    node = body["properties"] if field == "did" else signed_lane(body)["properties"]
    node[field][bound] = value

    assert _projected(documents).state is not DriftState.CURRENT


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_an_empty_range_on_the_payload_field_closes_the_gate(
    body_of: BodyOf, payload: str
) -> None:
    """Emptiness needs no knowledge of what we send.

    ``text`` and ``value`` carry whatever the user writes, so there is no fixed
    length to compare a bound against - and that is exactly why the check that
    *does* apply to them must not be skipped along with the one that does not.
    A range with no values in it rejects every request, ours included.
    """
    documents = build_documents(parsed=True)
    node = body_of(documents["openapi"])["properties"][payload]
    node["minLength"] = 100
    node["maxLength"] = 5

    result = _projected(documents)
    assert result.state is DriftState.DRIFTED
    assert any(
        "uzunluk araligi bos" in item.reason for item in result.critical_mismatches
    )


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_an_ordinary_payload_bound_is_not_a_finding(
    body_of: BodyOf, payload: str
) -> None:
    """The mirror: a payload length limit is normal and must not alarm."""
    documents = build_documents(parsed=True)
    body_of(documents["openapi"])["properties"][payload]["maxLength"] = 4096

    assert _projected(documents).state is DriftState.CURRENT


@pytest.mark.parametrize(("body_of", "payload"), _LANES)
def test_a_bound_that_still_admits_our_value_is_accepted(
    body_of: BodyOf, payload: str
) -> None:
    """The mirror of the row above, so the check is not simply "any bound"."""
    del payload
    documents = build_documents(parsed=True)
    signed_lane(body_of(documents["openapi"]))["properties"]["nonce"]["minLength"] = (
        NONCE_MIN_DIGITS
    )

    assert _projected(documents).state is DriftState.CURRENT


# --- what the expectations are anchored to ---------------------------------


def test_the_nonce_digit_counts_match_the_conformance_pattern() -> None:
    """The two must not drift apart; the pattern is the authority."""
    assert f"[0-9]{{{NONCE_MIN_DIGITS},{NONCE_MAX_DIGITS}}}" == NONCE_PATTERN


def test_the_sent_lengths_come_from_our_own_contract() -> None:
    assert STATION_FIELD_LENGTHS["did"] == SentLength(
        EXPECTED_DID_CHARS, EXPECTED_DID_CHARS
    )
    assert STATION_FIELD_LENGTHS["sig"] == SentLength(SIGNATURE_CHARS, SIGNATURE_CHARS)
    assert STATION_FIELD_LENGTHS["nonce"] == SentLength(
        NONCE_MIN_DIGITS, NONCE_MAX_DIGITS
    )


def test_the_planned_body_names_the_fields_station_signs() -> None:
    """Both lanes carry the three credentials plus their own payload field."""
    credentials = {"did", "sig", "nonce"}
    assert PLANNED_BODY_FIELDS[Lane.MESSAGE_BODY] == credentials | {"text"}
    assert PLANNED_BODY_FIELDS[Lane.NOTE_BODY] == credentials | {"value"}
    assert (
        PLANNED_BODY_FIELDS[Lane.MESSAGE_SIGNED]
        == PLANNED_BODY_FIELDS[Lane.MESSAGE_BODY]
    )
    assert PLANNED_BODY_FIELDS[Lane.NOTE_SIGNED] == PLANNED_BODY_FIELDS[Lane.NOTE_BODY]
    # `from` is deliberately absent: the reference ignores it on the signed
    # lane, so Station does not send it and must not depend on it.
    assert "from" not in PLANNED_BODY_FIELDS[Lane.MESSAGE_BODY]


def test_every_allowed_validation_keyword_is_actually_evaluated() -> None:
    """An allow-listed keyword that nothing reads would be a silent gap.

    Each name is paired with a mutation that must close the gate, which is the
    evidence that permitting a keyword and evaluating it are the same list.
    """

    def probe_type(body: dict[str, Any]) -> None:
        body["properties"]["did"]["type"] = "integer"

    def probe_pattern(body: dict[str, Any]) -> None:
        signed_lane(body)["properties"]["sig"]["pattern"] = "^[a-z]+$"

    def probe_min(body: dict[str, Any]) -> None:
        body["properties"]["did"]["minLength"] = 100

    def probe_max(body: dict[str, Any]) -> None:
        signed_lane(body)["properties"]["nonce"]["maxLength"] = 0

    probes: dict[str, Callable[[dict[str, Any]], None]] = {
        "type": probe_type,
        "pattern": probe_pattern,
        "minLength": probe_min,
        "maxLength": probe_max,
    }
    assert set(probes) == set(UNDERSTOOD_FIELD_KEYS)

    for name, probe in probes.items():
        documents = build_documents(parsed=True)
        probe(message_body_schema(documents["openapi"]))
        assert _projected(documents).state is not DriftState.CURRENT, (
            f"{name} is allowed but nothing evaluates it"
        )


# --- comparison must not normalise a difference away -----------------------


@pytest.mark.parametrize(
    "decorated",
    [
        "<room>|<nonce>|<text>\n",
        "<room>|<nonce>|<text> ",
        " <room>|<nonce>|<text>",
        "<room>|<nonce>|<text>" + chr(0x200B),  # zero-width space
        "<room>|<nonce>|<text>\x00",
        "<room>|<nonce>|<text>\u00a0",
    ],
)
def test_whitespace_around_a_canonical_payload_is_not_the_same_payload(
    decorated: str,
) -> None:
    """The comparison runs on the original value, never on the swept display.

    ``safe_display`` turns a control character into a space and strips the
    ends. Comparing its output would make every string here equal to the
    canonical payload - and they are all different bytes to sign.
    """
    documents = build_documents(parsed=True)
    documents["agent"]["identity"]["message_signature_payload"] = decorated

    result = _projected(documents)
    assert result.state is DriftState.DRIFTED
    assert "message_signature_payload" in {
        item.field.key for item in result.critical_mismatches
    }


@pytest.mark.parametrize("published", ["86", 86.5, True, None, ["86"]])
def test_a_length_bound_of_the_wrong_type_is_not_accepted(published: object) -> None:
    documents = build_documents(parsed=True)
    message, _ = _lanes(documents)
    signed_lane(message)["properties"]["sig"]["maxLength"] = published

    assert _projected(documents).state is not DriftState.CURRENT


def test_a_required_list_containing_extra_names_is_not_equal() -> None:
    documents = build_documents(parsed=True)
    message, _ = _lanes(documents)
    signed_lane(message)["required"] = ["sig", "nonce", "from"]

    assert _projected(documents).state is not DriftState.CURRENT


# --- prose: bounded, and never satisfied by a sentence that denies it ------


@pytest.mark.parametrize(
    "denial",
    [
        "base64url, 86 characters, but not unpadded",
        "base64url, 86 characters; padded",
        "base64url and 86 characters - unpadded is deprecated",
        "unpadded base64url 86 was removed in 0.12",
        "base64url, 86 characters, no longer unpadded",
        "unpadded base64url, 86 characters - obsolete, use the new lane instead",
    ],
)
def test_a_description_that_denies_the_contract_does_not_pass(denial: str) -> None:
    """Containing the right words is not agreeing with them.

    The old check asked only whether ``base64url``, ``86`` and ``unpadded``
    appeared anywhere in the sentence, so a sentence rejecting the contract
    passed for carrying the words it rejected.
    """
    documents = build_documents(parsed=True)
    documents["agent"]["identity"]["signature_encoding"] = denial

    result = _projected(documents)
    assert result.state is not DriftState.CURRENT
    assert "signature_encoding" in {item.field.key for item in result.critical_failures}


def test_a_reworded_but_equivalent_encoding_statement_is_not_drift() -> None:
    documents = build_documents(parsed=True)
    documents["agent"]["identity"]["signature_encoding"] = (
        "Unpadded BASE64URL; the signature is 86 characters long."
    )
    assert _projected(documents).state is DriftState.CURRENT


def test_the_real_pinned_description_is_accepted() -> None:
    """The negation list must not trip on the words the reference really uses.

    It says "Re-encode the raw signature *rather than* editing its tail", and
    "unpadded" contains "padded" as a substring. Both are asserted here so a
    future addition to the marker list cannot silently reject the real
    document.
    """
    documents = build_documents(parsed=True)
    published = documents["agent"]["identity"]["signature_encoding"]

    assert "rather than" in published
    assert "unpadded" in published
    assert _projected(documents).state is DriftState.CURRENT


def test_an_unbounded_description_is_not_judged() -> None:
    """A denial could be sitting past whatever bound was scanned."""
    documents = build_documents(parsed=True)
    documents["agent"]["identity"]["signature_encoding"] = (
        "base64url 86 unpadded " + "x" * (MAX_PROSE_CHARS + 1)
    )

    result = _projected(documents)
    assert result.state is DriftState.UNAVAILABLE
    assert any(
        item.outcome is FieldOutcome.UNSUPPORTED
        for item in result.observations
        if item.field.key == "signature_encoding"
    )


# --- changes that are real but do not invalidate a signature ---------------


def test_a_capacity_change_is_a_warning_not_drift() -> None:
    """A limit change is real and shown, but a signature stays valid."""
    documents = build_documents(parsed=True)
    documents["agent"]["limits"]["message_chars"] = 8192
    result = _projected(documents)

    assert result.state is DriftState.CURRENT
    assert "message_chars" in {item.field.key for item in result.warnings}


def test_a_newer_service_version_is_a_warning_and_stays_one() -> None:
    """The live service was 0.11.2 while the pin was 0.10.0.

    That is a difference worth showing and not a reason to close the gate -
    and not a reason to quietly move the expectation either, which would
    delete the only signal that the pin is behind.
    """
    documents = build_documents(parsed=True)
    documents["agent"]["version"] = "0.11.2"
    result = _projected(documents)

    assert result.state is DriftState.CURRENT
    assert "service_version" in {item.field.key for item in result.warnings}
    assert result.critical_mismatches == ()


def test_reordering_and_documentation_changes_are_not_drift() -> None:
    """Field order and prose must not be mistaken for a protocol change."""
    documents = build_documents(parsed=True)
    documents["agent"]["description"] = "totally rewritten prose"
    documents["agent"]["documentation"]["manual"] = "https://technocore.chat/other.txt"
    documents["agent"] = dict(reversed(list(documents["agent"].items())))

    assert _projected(documents).state is DriftState.CURRENT


def test_a_missing_required_document_is_never_current() -> None:
    """Without the manifest the agent-side facts cannot be read at all.

    Reported as unavailable rather than drift: nothing was observed to have
    changed. The gate is shut either way, which is the security property.
    """
    documents = build_documents(parsed=True)
    result = project({SourceId.OPENAPI: documents["openapi"]})

    assert result.state is not DriftState.CURRENT
    assert result.state is DriftState.UNAVAILABLE
    assert result.critical_mismatches == ()
    assert result.critical_unevaluable != ()


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


def test_the_expectation_comes_from_our_own_conformance_engine() -> None:
    """Not copied from the live document, which would be self-fulfilling."""
    assert f"^{SIGNATURE_PATTERN}$" == EXPECTED_SIGNATURE_PATTERN
    assert EXPECTED_SIGNATURE_PATTERN == r"^[A-Za-z0-9_-]{85}[AQgw]$"
    assert f"^{NONCE_PATTERN}$" == EXPECTED_NONCE_PATTERN
    assert f"^{NAME_PATTERN}$" == EXPECTED_NAME_PATTERN


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


# ---------------------------------------------------------------------------
# The 503 the user saw
#
# The service answers 503 intermittently. What that must mean depends entirely
# on *which* document was refused, and these three pin the difference. A 503
# says the request was not served; it does not say why, and none of these
# infers load, rate limiting or an outage from it.
# ---------------------------------------------------------------------------


def test_only_health_returning_503_leaves_the_protocol_verdict_intact(
    engine: Engine,
) -> None:
    """``/healthz`` carries no protocol contract, so it cannot decide one.

    The failure is still recorded and shown - it is not swallowed - but the
    verdict comes from the two required documents.
    """
    service = TechnocoreService(
        engine=engine, client=_client(_handler(status_overrides={"/healthz": 503}))
    )
    status = service.refresh()

    assert status.state is DriftState.CURRENT
    assert status.manifest_current is True

    health = next(item for item in status.sources if item.source_id == "health")
    assert health.outcome == SnapshotOutcome.FETCH_ERROR
    assert "503" in health.detail


def test_openapi_returning_503_closes_the_gate(engine: Engine) -> None:
    """A required document that never arrived is not a protocol finding.

    ``unavailable`` rather than ``drifted``: nothing was observed to have
    changed, and the reason names the document rather than the protocol.
    """
    service = TechnocoreService(
        engine=engine, client=_client(_handler(status_overrides={"/openapi.json": 503}))
    )
    status = service.refresh()

    assert status.state is DriftState.UNAVAILABLE
    assert status.manifest_current is False
    assert any("openapi" in reason for reason in status.reasons)


def test_a_503_after_a_success_shows_the_old_time_but_not_the_old_verdict(
    engine: Engine,
) -> None:
    """The load-bearing one, and the shape of what the user reported.

    The earlier success is still worth showing - it says when the protocol was
    last confirmed - but it is displayed *beside* the failure, never instead of
    it, and it cannot reopen the gate.
    """
    service = TechnocoreService(engine=engine, client=_client(_handler()))
    first = service.refresh()
    assert first.state is DriftState.CURRENT
    assert first.manifest_current is True
    earlier_success = first.last_success_at
    assert earlier_success is not None

    service._client = _client(
        _handler(status_overrides={"/openapi.json": 503})
    )
    second = service.refresh()

    assert second.state is DriftState.UNAVAILABLE
    assert second.manifest_current is False
    assert second.last_success_at == earlier_success
    assert second.last_attempt_at != earlier_success


def test_a_required_document_is_retried_a_bounded_number_of_times() -> None:
    """Three attempts, then it gives up. No unbounded retry to paper over a 503."""
    attempts = 0

    def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="Service Unavailable")

    client = _client(httpx.MockTransport(flaky))
    with pytest.raises(SourceFetchError):
        client.fetch(get_source(SourceId.OPENAPI))

    assert attempts == MAX_ATTEMPTS


def test_a_later_failure_does_not_inherit_an_earlier_success(engine: Engine) -> None:
    """The load-bearing case: a stale success must never open the gate."""
    service = TechnocoreService(engine=engine, client=_client(_handler()))
    assert service.refresh().manifest_current is True

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    service._client = _client(httpx.MockTransport(down))
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
