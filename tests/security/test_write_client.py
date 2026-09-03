"""The signed-write client: POST once, three outcomes, no retry.

Every request here is answered by an ``httpx.MockTransport``. Nothing
contacts Technocore, no room is ever a real one, and the lobby is never a
target (INV-05).

The property that carries the most weight is the negative one. The read-only
client retries transport faults, 5xx and 429 up to three times because
re-reading a document is free; a write client that inherited that policy
would turn one approved message into several published ones. So the tests
below count attempts, not just outcomes.
"""

from __future__ import annotations

import ast
import gzip
import inspect
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from station_api.technocore.client import MAX_ATTEMPTS, ReadOnlyTechnocoreClient
from station_api.technocore.errors import SourceFetchError
from station_api.technocore.sources import TECHNOCORE_ORIGIN
from station_api.technocore.write_client import (
    MAX_EXCERPT_CHARS,
    MAX_RESPONSE_BYTES,
    REFUSED_STATUSES,
    UNREAD_BODY_NOTE,
    WRITE_TIMEOUT,
    SignedWriteClient,
    WriteOutcome,
)
from station_api.technocore.write_targets import (
    DENIED_ROOMS,
    UNDERSTOOD_ROOM_CLASSES,
    RoomPolicyError,
    WriteTarget,
    classes_of,
    published_markers,
    resolve_message_target,
)

pytestmark = pytest.mark.security

#: The markers the pinned manifest publishes. Read from the document in one
#: test below rather than assumed everywhere.
MARKERS = frozenset({"p", "mb", "d", "e"})

#: TEST-ONLY target. A mailbox room that does not exist, and never the lobby.
TEST_TARGET = WriteTarget(room="mb-station-test-only", classes=("mb",))

#: TEST-ONLY body. The DID and signature are fixture shapes, not real ones.
TEST_BODY = {
    "did": "did:key:z6MkTESTONLYnotarealidentity0000000000000000000000000",
    "sig": "TEST-ONLY-not-a-real-signature",
    "nonce": "1764000000000",
    "text": "TEST ONLY - never sent anywhere real",
}


Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> SignedWriteClient:
    return SignedWriteClient(transport=httpx.MockTransport(handler))


def _answering(
    status: int, *, body: str = "{}"
) -> tuple[Handler, list[httpx.Request]]:
    """A handler that answers with one status and records what it received."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, text=body)

    return handler, seen


# ---------------------------------------------------------------------------
# The three outcomes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [200, 201, 202, 204, 299])
def test_a_2xx_is_accepted(status: int) -> None:
    handler, _ = _answering(status)

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert result.outcome is WriteOutcome.ACCEPTED
    assert result.is_accepted is True
    assert result.http_status == status


@pytest.mark.parametrize("status", sorted(REFUSED_STATUSES))
def test_a_response_that_proves_nothing_was_written_is_refused(status: int) -> None:
    """400, 403, 413 and 422 are the four that carry that proof.

    Nothing else does. A 500 might mean the write landed and the receipt did
    not, so it is deliberately absent from this list.
    """
    handler, _ = _answering(status)

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert result.outcome is WriteOutcome.REFUSED
    assert result.http_status == status
    assert result.detail


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 418, 301, 302, 307])
def test_everything_else_is_outcome_unknown(status: int) -> None:
    """Including the redirects, which are never followed.

    A 3xx is not a refusal: the origin may have acted before answering, and
    following the hop to find out is precisely how a request leaves the
    allow-listed origin.
    """
    handler, _ = _answering(status)

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert result.outcome is WriteOutcome.OUTCOME_UNKNOWN
    assert result.http_status == status
    assert "bilinmiyor" in result.detail


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectTimeout("connect timed out"),
        httpx.ReadTimeout("read timed out"),
        httpx.ConnectError("connection refused"),
        httpx.RemoteProtocolError("malformed response"),
    ],
)
def test_a_lost_response_is_outcome_unknown_not_a_failure(
    failure: Exception,
) -> None:
    """The case the pinned manual names: a fetch failure is not proof.

    The server may have stored the message and lost the receipt. Reporting
    this as "failed" is the mistake that produces a duplicate the moment the
    user tries again.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise failure

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert result.outcome is WriteOutcome.OUTCOME_UNKNOWN
    assert result.http_status == 0
    assert "bilinmiyor" in result.detail


def test_a_duplicate_filter_refusal_says_retrying_will_not_help() -> None:
    """422 is the refusal a user is most tempted to retry.

    Retrying it sends the same bytes to the same filter for the same answer,
    so the sentence has to say so rather than leaving it to be discovered.
    """
    handler, _ = _answering(422)

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert result.outcome is WriteOutcome.REFUSED
    assert "yine reddedilir" in result.detail


def test_send_never_raises_for_a_network_condition() -> None:
    """An exception here would be caught somewhere as "it did not work".

    Which is the one claim this module exists to refuse to make. Every
    transport condition has to arrive as a result.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    result = _client(handler).send(TEST_TARGET, TEST_BODY)
    assert result.outcome is WriteOutcome.OUTCOME_UNKNOWN


# ---------------------------------------------------------------------------
# One attempt. Never two.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_a_retryable_looking_status_is_not_retried(status: int) -> None:
    """The read client would try three times. This one must try once.

    ``MAX_ATTEMPTS`` is imported from the read client so the contrast is
    asserted against the real policy rather than against a copy of the
    number that could drift.
    """
    handler, seen = _answering(status)

    _client(handler).send(TEST_TARGET, TEST_BODY)

    assert len(seen) == 1
    assert MAX_ATTEMPTS > 1, "the read client's policy is what must not be inherited"


def test_a_retry_after_header_is_ignored_entirely() -> None:
    """There is nothing to wait for, so the header is not even read."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "1"}, text="slow down")

    calls = 0

    def counting(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return handler(request)

    result = _client(counting).send(TEST_TARGET, TEST_BODY)

    assert calls == 1
    assert result.outcome is WriteOutcome.OUTCOME_UNKNOWN


def test_a_transport_failure_is_not_retried_either() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("timed out")

    _client(handler).send(TEST_TARGET, TEST_BODY)

    assert calls == 1


def test_the_module_contains_no_attempt_loop(api_source_root: Path) -> None:
    """Structural, because "we do not retry" is easy to reintroduce.

    A loop over attempts, a backoff constant or a sleep would all be the
    read client's policy arriving by the back door. None of them may exist.
    """
    source = (
        api_source_root / "station_api" / "technocore" / "write_client.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
        elif isinstance(node, ast.arg):
            names.add(node.arg.lower())

    for smell in ("sleep", "backoff", "max_attempts", "retry_after"):
        assert smell not in names, f"the write client grew a {smell} affordance"


# ---------------------------------------------------------------------------
# Transport posture
# ---------------------------------------------------------------------------


def test_the_request_is_a_post_to_the_message_lane() -> None:
    handler, seen = _answering(200)

    _client(handler).send(TEST_TARGET, TEST_BODY)

    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert str(seen[0].url) == f"{TECHNOCORE_ORIGIN}/r/mb-station-test-only"


def test_the_body_travels_as_json_and_carries_no_extra_field() -> None:
    """The signature covers the canonical string, not the JSON.

    Which is exactly why the JSON must not carry anything the signature does
    not cover and the server does not validate.
    """
    handler, seen = _answering(200)

    _client(handler).send(TEST_TARGET, TEST_BODY)

    sent = json.loads(seen[0].content)
    assert sent == TEST_BODY
    assert "from" not in sent


def test_the_request_carries_no_identity_or_credential_header() -> None:
    handler, seen = _answering(200)

    _client(handler).send(TEST_TARGET, TEST_BODY)

    headers = seen[0].headers
    for forbidden in ("cookie", "authorization", "x-station-csrf", "x-did", "referer"):
        assert forbidden not in headers


def test_every_timeout_phase_is_bounded() -> None:
    assert WRITE_TIMEOUT.connect is not None
    assert WRITE_TIMEOUT.read is not None
    assert WRITE_TIMEOUT.write is not None
    assert WRITE_TIMEOUT.pool is not None


def test_redirects_are_not_followed() -> None:
    """A 302 must arrive as a result, not as a second request elsewhere."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/r/x"})

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert len(seen) == 1
    assert result.outcome is WriteOutcome.OUTCOME_UNKNOWN


def test_a_target_outside_the_allow_list_is_refused_before_the_request() -> None:
    """The URL is re-checked even though it is built from constants.

    Redundant by design: the registry itself being wrong is the mistake a
    reviewer is least likely to catch by eye and the one with the worst
    consequences.
    """

    class _Elsewhere(WriteTarget):
        """A target that lies about where it points."""

        @property
        def url(self) -> str:
            return "https://evil.example/r/test-only"

    handler, seen = _answering(200)

    with pytest.raises(SourceFetchError):
        _client(handler).send(_Elsewhere(room="test-only", classes=()), TEST_BODY)

    assert seen == [], "a request left before the allow-list was checked"


def test_the_response_excerpt_is_bounded_and_swept() -> None:
    """A server answer is untrusted input that a human will read."""
    hostile = "x" * 50_000 + "\x1b[31mred\x1b[0m‮"
    handler, _ = _answering(400, body=hostile)

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert len(result.response_excerpt) < 500
    assert "\x1b" not in result.response_excerpt
    assert "‮" not in result.response_excerpt


# ---------------------------------------------------------------------------
# The body cap is on what is buffered, not on what is kept
# ---------------------------------------------------------------------------


def _streaming(
    status: int, chunks: list[bytes], *, headers: dict[str, str] | None = None
) -> tuple[Handler, dict[str, int]]:
    """A handler whose body is a generator, so consumption can be counted.

    This is the whole point of the fixture. A short excerpt proves nothing
    about buffering - ``response.content[:cap]`` produces a short excerpt too,
    after materialising the entire body. Counting the bytes the *server side*
    was asked for is the only observation that separates the two.
    """
    pulled = {"bytes": 0}

    def generate() -> Iterator[bytes]:
        for chunk in chunks:
            pulled["bytes"] += len(chunk)
            yield chunk

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=generate(), headers=headers or {})

    return handler, pulled


def test_an_oversized_body_is_never_fully_buffered() -> None:
    """The reviewer's probe, as a test: 8 MiB offered, a cap's worth taken.

    ``response.content[:MAX_RESPONSE_BYTES]`` passed every excerpt assertion
    in this file while buffering all eight megabytes first, because the slice
    ran after the buffering. So this asserts on the bytes actually read.
    """
    chunk = b"x" * 8192
    offered = [chunk] * 1024  # 8 MiB
    handler, pulled = _streaming(200, offered)

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert result.outcome is WriteOutcome.ACCEPTED, "a long receipt is not a refusal"
    assert pulled["bytes"] <= MAX_RESPONSE_BYTES + len(chunk)
    assert pulled["bytes"] < 8 * 1024 * 1024, "the whole body was buffered"
    assert len(result.response_excerpt) <= MAX_EXCERPT_CHARS


def test_a_compressed_bomb_is_never_decompressed_at_all() -> None:
    """65 KB on the wire, 64 MiB decompressed - and not one byte read.

    ``Accept-Encoding: identity`` is a request the server may ignore, which is
    exactly what this handler does. The cap alone would still have to decode
    to find out how big the body was; refusing the encoding means nothing is
    decoded, so nothing can expand.
    """
    payload = b" " * (64 * 1024 * 1024)
    compressed = gzip.compress(payload)
    assert len(compressed) < 512 * 1024, "the fixture is not a bomb"

    raw = [compressed[at : at + 4096] for at in range(0, len(compressed), 4096)]
    handler, pulled = _streaming(200, raw, headers={"Content-Encoding": "gzip"})

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert result.outcome is WriteOutcome.ACCEPTED
    assert pulled["bytes"] == 0, "a body we refuse to decode was still read"
    assert result.response_excerpt == UNREAD_BODY_NOTE.decode("ascii")


@pytest.mark.parametrize("encoding", ["gzip", "deflate", "br", "zstd", "GZIP"])
def test_any_unrequested_content_encoding_leaves_the_body_unread(
    encoding: str,
) -> None:
    """Not a gzip special case: anything but identity is left alone."""
    handler, pulled = _streaming(
        400, [b"{}"], headers={"Content-Encoding": encoding}
    )

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert result.outcome is WriteOutcome.REFUSED, "the status still classifies"
    assert pulled["bytes"] == 0


def test_an_identity_encoded_body_is_still_read() -> None:
    """The guard must not swallow the ordinary case it was built around."""
    handler, pulled = _streaming(
        200, [b'{"seq": 1}'], headers={"Content-Encoding": "identity"}
    )

    result = _client(handler).send(TEST_TARGET, TEST_BODY)

    assert pulled["bytes"] == len(b'{"seq": 1}')
    assert "seq" in result.response_excerpt


def test_the_write_client_streams_rather_than_buffering(
    api_source_root: Path,
) -> None:
    """Structural, because the buffering version reads correctly by eye.

    ``response.content`` is one attribute access away and looks like a bounded
    read the moment a slice is written next to it. It must not come back.
    """
    source = (
        api_source_root / "station_api" / "technocore" / "write_client.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert ".stream(" in source
    assert "iter_bytes" in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("content", "text"):
            pytest.fail("the write client reads a whole response body again")


def test_no_tls_setting_is_passed_anywhere(api_source_root: Path) -> None:
    """``verify`` is never named, so there is no line to flip to False."""
    source = (
        api_source_root / "station_api" / "technocore" / "write_client.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            assert node.arg != "verify"
    assert "_create_unverified_context" not in source
    assert "CERT_NONE" not in source


def test_a_transport_with_tls_verification_off_cannot_be_injected() -> None:
    """The hole the source scan above cannot see.

    ``verify`` being absent from every line of this module says nothing about
    the *object graph*: ``httpx.HTTPTransport(verify=False)`` carries the
    disabled check inside it and used to be accepted through the test seam
    without a word. Narrowing the seam to ``MockTransport`` - which speaks no
    TLS at all - is what makes the docstring's claim true rather than
    aspirational.
    """
    with pytest.raises(TypeError) as caught:
        SignedWriteClient(transport=httpx.HTTPTransport(verify=False))

    assert "MockTransport" in str(caught.value)


def test_even_a_verifying_real_transport_is_refused() -> None:
    """The rule is the type, not an inspection of the SSL context.

    Reading ``verify`` back off a transport would mean reaching into httpx's
    private attributes, and a guard that silently stops matching after an
    upgrade is worse than none. A type check cannot rot that way.
    """
    with pytest.raises(TypeError):
        SignedWriteClient(transport=httpx.HTTPTransport())


def test_the_read_client_refuses_the_same_injection() -> None:
    """Both outbound clients, because both carried the same claim."""
    with pytest.raises(TypeError):
        ReadOnlyTechnocoreClient(transport=httpx.HTTPTransport(verify=False))


def test_a_mock_transport_is_still_accepted() -> None:
    """The seam has to keep working, or it gets removed and nothing is tested."""
    handler, seen = _answering(200)

    _client(handler).send(TEST_TARGET, TEST_BODY)

    assert len(seen) == 1


# ---------------------------------------------------------------------------
# Room policy: the target is validated against the live convention
# ---------------------------------------------------------------------------


def test_the_markers_are_read_from_the_pinned_manifest() -> None:
    """Not guessed. The manifest publishes them; this reads them from it."""
    from tests.security.technocore_fixtures import build_documents

    agent = build_documents(parsed=True)["agent"]
    markers = published_markers(agent["conventions"])

    assert markers == UNDERSTOOD_ROOM_CLASSES
    assert markers == MARKERS


def test_without_a_manifest_convention_no_room_resolves() -> None:
    """Fail-closed: an unchecked manifest means an unresolvable target.

    The gate is already shut in that state, and refusing here as well means
    the two cannot disagree about whether a write may happen.
    """
    with pytest.raises(RoomPolicyError):
        resolve_message_target("mb-station-test-only", markers=frozenset())


@pytest.mark.parametrize(
    ("room", "expected"),
    [
        ("pastel", ()),
        ("p-secret", ("p",)),
        ("mb-p-secret", ("mb", "p")),
        ("e-p-secret", ("e", "p")),
        ("d-owned", ("d",)),
        ("e-commerce", ("e",)),
        ("p-", ("p",)),
        ("d", ()),
        ("nothing-here", ()),
    ],
)
def test_room_classes_follow_the_references_own_rule(
    room: str, expected: tuple[str, ...]
) -> None:
    """The parsing rule is the reference's, applied to published markers.

    ``e-commerce`` is the interesting row: it really is an ephemeral room by
    this rule, and the reference says so explicitly. Inventing a friendlier
    rule would mean Station and the server disagreeing about what a name
    means.
    """
    assert classes_of(room, MARKERS) == expected


@pytest.mark.parametrize("room", sorted(DENIED_ROOMS))
def test_a_rendezvous_room_is_refused(room: str) -> None:
    """ADR-0002 4.1 and INV-05. The lobby is never a target."""
    with pytest.raises(RoomPolicyError) as caught:
        resolve_message_target(room, markers=MARKERS)

    assert room in str(caught.value)


def test_the_lobby_is_in_the_denied_set() -> None:
    """Stated on its own so the set cannot be emptied without failing."""
    assert "lobby" in DENIED_ROOMS


@pytest.mark.parametrize(
    "room",
    [
        "",
        "Uppercase",
        "has space",
        "has.dot",
        "has/slash",
        "-leading-hyphen",
        "a" * 49,
        "room\n",
        "..",
    ],
)
def test_a_name_outside_the_official_pattern_is_refused(room: str) -> None:
    with pytest.raises(RoomPolicyError):
        resolve_message_target(room, markers=MARKERS)


def test_a_room_class_this_build_does_not_understand_is_refused() -> None:
    """A live manifest publishing a new marker closes the door on it.

    We would not know what writing to such a room means - whether it is
    world-readable, whether it decays, whether an owner gates it - and
    guessing is the one thing the room convention exists to avoid.
    """
    with pytest.raises(RoomPolicyError) as caught:
        resolve_message_target("x-brand-new", markers=MARKERS | {"x"})

    assert "tanimadigi" in str(caught.value)


def test_a_resolved_target_reports_what_publishing_there_means() -> None:
    ephemeral = resolve_message_target("e-station-test-only", markers=MARKERS)
    unlisted = resolve_message_target("p-station-test-only", markers=MARKERS)
    ownable = resolve_message_target("d-station-test-only", markers=MARKERS)
    mailbox = resolve_message_target("mb-station-test-only", markers=MARKERS)

    assert ephemeral.is_ephemeral and not ephemeral.is_unlisted
    assert unlisted.is_unlisted
    assert ownable.is_ownable
    assert mailbox.is_mailbox


def test_the_send_signature_takes_a_resolved_target_not_a_name() -> None:
    """Structural: a raw string cannot become a URL without the policy."""
    parameters = inspect.signature(SignedWriteClient.send).parameters
    assert parameters["target"].annotation in (WriteTarget, "WriteTarget")
