"""The third registry, the evidence client, and the streaming scanner.

Three properties are being defended here.

**The read registry did not grow.** ``SOURCES`` is still exactly six fixed
documents and still contains no room path. The evidence lane lives in its own
closed registry, which is the ADR-0003 1 decision made checkable.

**The scanner does not buffer the stream.** A 12 MiB cap that is enforced by
joining chunks and slicing afterwards is not a cap, and that mistake is
invisible by eye - it is exactly what ``write_client`` shipped with until
IMP-289. The memory assertions below are on retained bytes, not on the cap.

**Evidence is raw bytes.** A record located by parsing is stored as the bytes
that arrived, never as a re-serialisation of the parse; the pinned export
lane exists precisely so a signed record re-verifies from its exported line
alone.
"""

from __future__ import annotations

import hashlib
import inspect
import json

import httpx
import pytest
from station_api.evidence.stream import (
    MAX_LINE_BYTES,
    MAX_STREAM_BYTES,
    MAX_WINDOW_LINE_BYTES,
    MAX_WINDOW_LINES,
    LineMatch,
    scan_export_stream,
)
from station_api.technocore.evidence_client import (
    EvidenceClient,
    EvidenceFetchError,
    ExportRead,
)
from station_api.technocore.evidence_targets import (
    EXPORT_LANE_TEMPLATE,
    EXPORT_METHOD,
    GENERATION_HEADER,
    resolve_export_target,
)
from station_api.technocore.sources import SOURCES, SourceId
from station_api.technocore.write_targets import DENIED_ROOMS, RoomPolicyError

from tests.security.compose_fixtures import TEST_ONLY_DID, TEST_ROOM
from tests.security.evidence_fixtures import (
    TEST_ONLY_GENERATION,
    export_handler,
    export_transport,
    ndjson,
    record_line,
    recording_transport,
)

pytestmark = pytest.mark.security

#: Real markers, in the shape the live manifest publishes them.
MARKERS = frozenset({"p", "mb", "d", "e"})

#: An 86-character canonical signature shape. TEST-ONLY, not a real signature.
TEST_ONLY_SIGNATURE = "z" * 85 + "A"

OURS = LineMatch(did=TEST_ONLY_DID, nonce="1757000000000", signature=TEST_ONLY_SIGNATURE)


def our_line(*, seq: int = 3, text: str = "TEST-ONLY kendi mesajimiz") -> bytes:
    return record_line(
        seq=seq,
        did=OURS.did,
        text=text,
        nonce=int(OURS.nonce),
        signature=OURS.signature,
    )


def other_line(seq: int) -> bytes:
    return record_line(
        seq=seq,
        did="did:key:z6MkTESTONLYotherpartydoesnotmatterhere00000000000",
        text=f"TEST-ONLY baska kayit {seq}",
        nonce=seq,
        signature="q" * 85 + "Q",
    )


# ---------------------------------------------------------------------------
# The registry stayed six, and the third one holds exactly one template
# ---------------------------------------------------------------------------


def test_the_document_registry_still_holds_exactly_six_fixed_documents() -> None:
    """Package E must not have widened ``SOURCES`` to reach a room.

    This is the assertion ADR-0003 1 promised to keep: the read-monitoring
    registry enumerates documents, so "the monitoring path cannot address a
    room" stays a structural fact rather than a habit.
    """
    assert {source.id for source in SOURCES} == set(SourceId)
    assert len(SOURCES) == 6
    for source in SOURCES:
        assert "/r/" not in source.path
        assert "{" not in source.path


def test_the_evidence_registry_holds_the_export_template_and_nothing_else() -> None:
    assert EXPORT_LANE_TEMPLATE == "/r/{room}/export"
    assert EXPORT_METHOD == "GET"

    target = resolve_export_target(TEST_ROOM, markers=MARKERS)
    assert target.path == f"/r/{TEST_ROOM}/export"
    assert target.url == f"https://technocore.chat/r/{TEST_ROOM}/export"


def test_the_evidence_lane_refuses_every_denied_room() -> None:
    """The write path's policy, unchanged, applied to the read (ADR-0002 4.1).

    A capture is a read, but it is a request that names a room, and the set
    of rooms Station will name is one set. Lobby is in ``DENIED_ROOMS``, so a
    capture cannot address it either.
    """
    assert "lobby" in DENIED_ROOMS
    for room in sorted(DENIED_ROOMS):
        with pytest.raises(RoomPolicyError):
            resolve_export_target(room, markers=MARKERS)


def test_the_evidence_lane_refuses_a_room_with_no_manifest_markers() -> None:
    """Fail-closed with no successful check, exactly as the write path is."""
    with pytest.raises(RoomPolicyError):
        resolve_export_target(TEST_ROOM, markers=frozenset())


@pytest.mark.parametrize(
    "room",
    ["../etc/passwd", "Room", "r/x", "a" * 49, "", "-leading", "with space"],
)
def test_the_evidence_lane_refuses_a_name_that_is_not_a_room(room: str) -> None:
    with pytest.raises(RoomPolicyError):
        resolve_export_target(room, markers=MARKERS)


def test_the_evidence_client_takes_no_url_method_or_tls_setting() -> None:
    """Structural: the dangerous inputs do not exist as parameters."""
    init = inspect.signature(EvidenceClient.__init__)
    export = inspect.signature(EvidenceClient.export)

    for forbidden in ("verify", "url", "method", "headers", "base_url", "ssl", "cert"):
        assert forbidden not in init.parameters
        assert forbidden not in export.parameters
    # The room is a name, validated against the official pattern and resolved
    # through the closed registry; it is never a path or an address.
    assert "room" in export.parameters


def test_a_transport_with_tls_verification_off_cannot_be_injected() -> None:
    """SI-165, extended to the third client."""
    with pytest.raises(TypeError):
        EvidenceClient(transport=httpx.HTTPTransport(verify=False))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EvidenceClient(transport=httpx.HTTPTransport())  # type: ignore[arg-type]


def test_the_read_only_client_signature_is_unchanged() -> None:
    """``fetch(self, source)`` did not grow a room parameter (ADR-0003 1)."""
    from station_api.technocore.client import ReadOnlyTechnocoreClient

    assert list(inspect.signature(ReadOnlyTechnocoreClient.fetch).parameters) == [
        "self",
        "source",
    ]


# ---------------------------------------------------------------------------
# The scanner
# ---------------------------------------------------------------------------


def test_our_own_line_comes_back_as_the_bytes_that_arrived() -> None:
    """Byte-exact, with an offset, and never a re-serialisation.

    The pinned export lane publishes records "bytes exactly as written, never
    re-serialized - so a signed record re-verifies from its exported line
    alone". A scanner that rebuilt the line from its parse would produce
    something that verifies against itself and proves nothing.
    """
    mine = our_line()
    body = ndjson([other_line(1), other_line(2), mine, other_line(4)])

    result = scan_export_stream([body], match=OURS)

    assert result.line == mine
    assert result.line_offset is not None
    assert body[result.line_offset : result.line_offset + len(mine)] == mine
    assert result.line_count == 4
    assert result.unreadable_lines == 0
    assert not result.truncated


def test_a_nineteen_digit_nonce_is_compared_without_rounding() -> None:
    """2^53 is passed at 16 digits; a float-rounded nonce would mis-match.

    The pinned description warns about exactly this: "up to 19 digits is past
    2^53, and a float-rounded nonce fails good signatures". Two nonces that
    differ only past the 53rd bit must not be treated as the same record.
    """
    big = "9007199254740993"  # 2**53 + 1
    neighbour = "9007199254740992"  # 2**53, indistinguishable as a float
    assert float(big) == float(neighbour)

    match = LineMatch(did=TEST_ONLY_DID, nonce=big, signature=TEST_ONLY_SIGNATURE)
    right = record_line(
        seq=1, did=TEST_ONLY_DID, nonce=int(big), signature=TEST_ONLY_SIGNATURE
    )
    wrong = record_line(
        seq=2, did=TEST_ONLY_DID, nonce=int(neighbour), signature=TEST_ONLY_SIGNATURE
    )

    assert scan_export_stream([ndjson([right])], match=match).line == right
    assert scan_export_stream([ndjson([wrong])], match=match).line is None


def test_a_nonce_published_as_a_float_is_not_rounded_into_a_match() -> None:
    """A JSON float is not a nonce, and is not coerced into one."""
    line = b'{"seq":1,"ts":"t","from":"%s","text":"x","nonce":1.0,"sig":"%s"}' % (
        TEST_ONLY_DID.encode(),
        TEST_ONLY_SIGNATURE.encode(),
    )
    match = LineMatch(did=TEST_ONLY_DID, nonce="1", signature=TEST_ONLY_SIGNATURE)
    assert scan_export_stream([ndjson([line])], match=match).line is None


def test_a_duplicate_key_line_cannot_claim_to_be_ours() -> None:
    """Strict parsing, on a line we did not write.

    ``json.loads`` keeps the last of duplicate keys, so a crafted line could
    carry someone else's ``sig`` for one reader and ours for another. A
    document that means two things is not evidence of either.
    """
    forged = (
        b'{"seq":1,"ts":"t","from":"' + TEST_ONLY_DID.encode() + b'",'
        b'"text":"x","nonce":1757000000000,'
        b'"sig":"' + (b"a" * 86) + b'","sig":"' + TEST_ONLY_SIGNATURE.encode() + b'"}'
    )
    result = scan_export_stream([ndjson([forged])], match=OURS)
    assert result.line is None
    assert result.unreadable_lines == 1


def test_the_scanner_never_holds_the_stream_it_scanned() -> None:
    """The memory bound, asserted on retained bytes rather than on the cap.

    Two megabytes in, a few kilobytes kept. ``_read_capped``'s
    ``b"".join(chunks)`` would have kept all of it, and would have looked
    exactly as correct.
    """
    filler = [other_line(index) for index in range(1, 4001)]
    mine = our_line(seq=4001)
    body = ndjson([*filler, mine, *[other_line(index) for index in range(4002, 8001)]])
    assert len(body) > 1_000_000

    result = scan_export_stream(
        [body[index : index + 65536] for index in range(0, len(body), 65536)],
        match=OURS,
    )

    assert result.line == mine
    assert result.scanned_bytes == len(body)
    # Everything kept: our line, plus at most two bounded neighbours on each
    # side. Nothing that grows with the body.
    ceiling = len(mine) + 2 * MAX_WINDOW_LINES * MAX_WINDOW_LINE_BYTES
    assert result.retained_bytes <= ceiling
    assert result.retained_bytes < len(body) // 10


def test_the_window_is_bounded_in_lines_and_in_bytes() -> None:
    """Two bounds, because a line count alone bounds nothing.

    Three short lines and three 10 MiB lines are both "three lines"; only the
    byte ceiling separates them.
    """
    huge = record_line(seq=1, text="T" * 40_000)
    body = ndjson([huge, huge, our_line(), huge, huge])

    result = scan_export_stream([body], match=OURS)

    assert len(result.window_before) <= MAX_WINDOW_LINES
    assert len(result.window_after) <= MAX_WINDOW_LINES
    for line in result.window_before + result.window_after:
        assert len(line) <= MAX_WINDOW_LINE_BYTES


def test_the_cap_stops_the_scan_and_says_so() -> None:
    """Reaching the cap is reported, because absence inside it means nothing."""
    body = ndjson([other_line(index) for index in range(1, 200)])
    result = scan_export_stream([body], match=OURS, cap=200)

    assert result.truncated
    assert result.scanned_bytes == 200
    assert result.line is None


def test_a_body_exactly_at_the_cap_is_not_reported_as_truncated() -> None:
    """A complete scan is a complete scan. Off-by-one here is a false alarm."""
    body = ndjson([our_line()])
    result = scan_export_stream([body], match=OURS, cap=len(body))

    assert not result.truncated
    assert result.line is not None


def test_an_overlong_line_is_dropped_rather_than_buffered() -> None:
    """A line longer than any record we wrote is not held to find out."""
    body = b"x" * (MAX_LINE_BYTES + 5000) + b"\n" + ndjson([our_line()])
    result = scan_export_stream(
        [body[index : index + 65536] for index in range(0, len(body), 65536)],
        match=OURS,
    )

    assert result.unreadable_lines >= 1
    assert result.line == our_line()
    assert result.retained_bytes < MAX_LINE_BYTES


def test_unreadable_lines_are_counted_rather_than_treated_as_altered() -> None:
    """IMP-238's distinction: unreadable is not changed."""
    body = ndjson([b"{not json", other_line(2), b'"a string, not an object"'])
    result = scan_export_stream([body], match=OURS)

    assert result.unreadable_lines == 2
    assert result.line is None


def test_the_running_hash_covers_the_whole_stream_including_after_the_match() -> None:
    """The hash is of the export, not of the part before our line.

    After the match the scanner stops buffering; if it also stopped hashing,
    the "integrity note" would describe a prefix and be quietly useless.
    """
    body = ndjson([our_line(), *[other_line(index) for index in range(2, 500)]])
    result = scan_export_stream([body], match=OURS)

    assert result.stream_sha256 == hashlib.sha256(body).hexdigest()
    assert result.scanned_bytes == len(body)


def test_an_unterminated_final_record_is_read_only_on_a_complete_scan() -> None:
    """A torn tail is a record; a fragment at the cap is not.

    The reference heals a torn tail on its next append, so an unterminated
    last line is often a real record. At the cap, though, the tail is the
    middle of a line the scan did not finish - and reading a fragment as a
    record is how a scanner invents evidence.
    """
    mine = our_line()
    complete = ndjson([other_line(1)]) + mine  # no trailing newline
    assert scan_export_stream([complete], match=OURS).line == mine

    capped = scan_export_stream([complete], match=OURS, cap=len(complete) - 5)
    assert capped.truncated
    assert capped.line is None


def test_the_default_cap_is_the_ring_plus_headroom() -> None:
    """10 MiB of ring (``limits.room_ring_bytes``) plus room to grow."""
    assert MAX_STREAM_BYTES == 12 * 1024 * 1024
    assert MAX_STREAM_BYTES > 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


def _client(transport: httpx.MockTransport) -> EvidenceClient:
    return EvidenceClient(transport=transport)


def test_the_client_requests_the_fixed_export_path_and_nothing_else() -> None:
    seen: list[httpx.Request] = []
    body = ndjson([our_line()])
    transport = recording_transport(export_handler(body), seen)

    read = _client(transport).export(TEST_ROOM, markers=MARKERS, match=OURS)

    assert read.ok
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert str(seen[0].url) == f"https://technocore.chat/r/{TEST_ROOM}/export"
    assert seen[0].url.query == b""
    # No cookie, no authorization, no identity of any kind.
    for header in ("cookie", "authorization", "x-station-csrf"):
        assert header not in seen[0].headers


def test_the_client_refuses_a_denied_room_before_any_request() -> None:
    seen: list[httpx.Request] = []
    transport = recording_transport(lambda request: httpx.Response(200), seen)

    with pytest.raises(EvidenceFetchError):
        _client(transport).export("lobby", markers=MARKERS, match=OURS)

    assert seen == [], "a refused room must produce no outbound request at all"


def test_a_redirect_is_a_failed_read_and_is_never_followed() -> None:
    seen: list[httpx.Request] = []
    transport = recording_transport(
        lambda request: httpx.Response(302, headers={"Location": "https://evil.example/"}),
        seen,
    )

    read = _client(transport).export(TEST_ROOM, markers=MARKERS, match=OURS)

    assert not read.ok
    assert read.http_status == 302
    assert len(seen) == 1
    assert "evil.example" not in read.failure_detail


def test_a_transport_failure_is_a_result_rather_than_an_exception() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("TEST-ONLY timeout", request=request)

    read = _client(httpx.MockTransport(boom)).export(
        TEST_ROOM, markers=MARKERS, match=OURS
    )

    assert isinstance(read, ExportRead)
    assert not read.ok
    assert read.http_status == 0


def test_the_generation_header_is_kept_as_digits_or_dropped() -> None:
    body = ndjson([our_line()])

    good = _client(export_transport(body, generation=TEST_ONLY_GENERATION)).export(
        TEST_ROOM, markers=MARKERS, match=OURS
    )
    assert good.generation == TEST_ONLY_GENERATION

    # Not digits: dropped rather than guessed at. A missing generation makes
    # a later comparison incomparable, which is the fail-closed direction.
    odd = _client(export_transport(body, generation="seven")).export(
        TEST_ROOM, markers=MARKERS, match=OURS
    )
    assert odd.generation == ""
    assert GENERATION_HEADER == "X-Room-Generation"


def test_a_body_larger_than_the_cap_is_reported_truncated_not_buffered() -> None:
    """A ring far past the cap ends as ``stream_truncated``, not as memory."""
    body = ndjson([other_line(index) for index in range(1, 3000)])
    read = _client(export_transport(body)).export(
        TEST_ROOM, markers=MARKERS, match=OURS
    )
    assert read.ok

    capped = _client(export_transport(body)).export(
        TEST_ROOM, markers=MARKERS, match=OURS, cap=4096
    )
    assert capped.scan.truncated
    assert capped.scan.scanned_bytes == 4096
    assert capped.scan.retained_bytes < 4096


def test_a_record_is_json_parseable_but_stored_as_bytes() -> None:
    """The parse is how the line is *found*; the bytes are what is kept."""
    mine = our_line(text="TEST-ONLY  bosluklu   metin")
    read = _client(export_transport(ndjson([mine]))).export(
        TEST_ROOM, markers=MARKERS, match=OURS
    )

    assert read.scan.line == mine
    # Re-serialising the parse produces different bytes, which is why the
    # parse is not what gets stored.
    reserialised = json.dumps(json.loads(mine)).encode("utf-8")
    assert reserialised != mine
