"""SI-274, SI-275 - staleness is measured, the ring drop is the server's signal.

Two claims are tested here and they are deliberately separate. The staleness
note is a *pair of measured facts* with no verdict attached, and the ring-drop
notice is a *machine-readable statement the service publishes about itself*.
Folding them together would turn "you have unread messages and they are gone"
into a general caveat about freshness.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from station_api.workscan.authority import (
    CALLER_WRITTEN_ROOM_FIELDS,
    AuthorityLevel,
    describe_author,
    is_did_key,
)
from station_api.workscan.client import RoomScanClient
from station_api.workscan.errors import SnapshotParseError
from station_api.workscan.snapshot import (
    MAX_MESSAGES,
    MAX_ROOMS,
    parse_room_index,
    parse_room_messages,
    ring_drop_notice,
    staleness_note,
)
from station_api.workscan.targets import (
    ROOMS_CACHE_SECONDS_DECLARED,
    resolve_room_target,
)

from tests.security.workscan_fixtures import (
    DID_KEY_TEST_ONLY,
    HELP_LINE,
    MARKERS,
    NICKNAME,
    ROOM,
    index_document,
    json_transport,
    message,
    recording_transport,
    room_document,
)

pytestmark = pytest.mark.security


def _read_room(document: dict[str, object], *, since: int | None = None):  # type: ignore[no-untyped-def]
    transport, _ = json_transport(document)  # type: ignore[arg-type]
    client = RoomScanClient(transport=transport, sleep=lambda _: None)
    result = client.fetch_room_messages(
        resolve_room_target(ROOM, markers=MARKERS), since=since
    )
    return parse_room_messages(result, since=since)


def _read_index(document: dict[str, object]):  # type: ignore[no-untyped-def]
    transport, _ = json_transport(document)  # type: ignore[arg-type]
    client = RoomScanClient(transport=transport, sleep=lambda _: None)
    return parse_room_index(client.fetch_room_index())


# ---------------------------------------------------------------------------
# Staleness: measured, never a threshold
# ---------------------------------------------------------------------------


def test_the_staleness_note_carries_the_reading_time_and_the_declared_bound() -> None:
    """ADR-0007 5: no invented threshold, and the label always carries both."""
    read_at = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    note = staleness_note(read_at)

    assert note.read_at == read_at
    assert note.declared_cache_seconds == ROOMS_CACHE_SECONDS_DECLARED == 3
    assert note.declared_by.strip()
    assert read_at.isoformat() in note.detail
    assert "3" in note.detail


def test_the_snapshot_has_no_freshness_verdict_field() -> None:
    """A verdict would need a cut-off this build is not entitled to choose."""
    snapshot = _read_index(index_document())

    assert not hasattr(snapshot.staleness, "is_stale")
    assert not hasattr(snapshot.staleness, "fresh")
    assert snapshot.staleness.detail


def test_the_note_is_present_on_every_snapshot_and_not_only_on_a_bad_one() -> None:
    """A provenance line that only appears when something is wrong is unseen."""
    assert _read_index(index_document()).staleness.detail
    assert _read_room(room_document()).staleness.detail


# ---------------------------------------------------------------------------
# The ring drop: the server's own signal
# ---------------------------------------------------------------------------


def test_the_ring_drop_fires_on_exactly_the_published_rule() -> None:
    """``first_seq > since + 1``, and nothing looser."""
    assert ring_drop_notice(since=10, first_seq=11) is None
    assert ring_drop_notice(since=10, first_seq=10) is None

    notice = ring_drop_notice(since=10, first_seq=15)
    assert notice is not None
    assert notice.expected_first == 11
    assert notice.first_seq == 15
    assert "15" in notice.detail and "11" in notice.detail


def test_no_cursor_means_no_ring_drop_claim() -> None:
    """With nothing to compare against, the honest answer is silence."""
    assert ring_drop_notice(since=None, first_seq=99) is None
    assert _read_room(room_document()).ring_drop is None


def test_a_snapshot_with_a_gap_carries_its_own_notice_beside_the_staleness_one() -> None:
    snapshot = _read_room(
        room_document(messages=[message(40, HELP_LINE)], first_seq=40), since=10
    )

    assert snapshot.ring_drop is not None
    assert snapshot.ring_drop.since == 10
    # Two distinct sentences, not one merged caveat.
    assert snapshot.ring_drop.detail != snapshot.staleness.detail


# ---------------------------------------------------------------------------
# count / last_seq / first_seq are read, never assumed
# ---------------------------------------------------------------------------


def test_the_counts_are_read_from_the_reply_and_the_disagreement_is_shown() -> None:
    """The published advice is "read ``count``, do not assume it".

    So both numbers are carried and a mismatch produces a sentence rather than
    a silent choice of one.
    """
    snapshot = _read_room(
        room_document(messages=[message(1, HELP_LINE)], count=7, last_seq=99)
    )

    assert snapshot.reported_count == 7
    assert snapshot.received_count == 1
    assert snapshot.last_seq == 99
    assert "7" in snapshot.count_disagreement
    assert "1" in snapshot.count_disagreement


def test_agreeing_counts_produce_no_sentence() -> None:
    assert _read_room(room_document()).count_disagreement == ""


def test_a_boolean_is_not_accepted_as_a_count() -> None:
    """``isinstance(True, int)`` is true in Python; the type check is explicit."""
    document = room_document()
    document["count"] = True

    with pytest.raises(SnapshotParseError):
        _read_room(document)


def test_a_missing_required_field_refuses_the_whole_document() -> None:
    for key in ("room", "count", "last_seq", "messages"):
        document = room_document()
        del document[key]
        with pytest.raises(SnapshotParseError):
            _read_room(document)


def test_a_null_first_seq_is_accepted_because_the_schema_publishes_it() -> None:
    snapshot = _read_room(room_document(messages=[], count=0, first_seq=None, last_seq=0))

    assert snapshot.first_seq is None
    assert snapshot.ring_drop is None
    assert snapshot.received_count == 0


def test_a_document_that_repeats_a_key_is_refused_whole() -> None:
    """Strict parsing: a document meaning two things to two readers is refused."""
    transport, _ = recording_transport(
        lambda _: __import__("httpx").Response(
            200,
            content=b'{"room":"a","room":"b","count":0,"last_seq":0,"messages":[]}',
            headers={"content-type": "application/json"},
        )
    )
    client = RoomScanClient(transport=transport, sleep=lambda _: None)
    result = client.fetch_room_messages(resolve_room_target(ROOM, markers=MARKERS))

    with pytest.raises(SnapshotParseError):
        parse_room_messages(result)


def test_the_kept_counts_are_bounded_and_the_services_total_is_reported_separately() -> None:
    """Truncating here never becomes a claim about how many rooms exist."""
    rooms = [{"room": f"test-only-{index}", "topic": ""} for index in range(MAX_ROOMS + 5)]
    snapshot = _read_index(index_document(rooms=rooms))

    assert snapshot.kept_count == MAX_ROOMS
    assert snapshot.total == MAX_ROOMS + 5
    assert snapshot.truncated is True


def test_the_message_cap_matches_the_published_ceiling() -> None:
    assert MAX_MESSAGES == 200


# ---------------------------------------------------------------------------
# The third authority level
# ---------------------------------------------------------------------------


def test_room_content_is_level_three_even_though_the_path_is_level_one() -> None:
    """ADR-0007 6. Both facts are true at once and neither is collapsed."""
    from station_api.workscan.targets import SCAN_TARGETS

    for target in SCAN_TARGETS:
        assert target.path_authority == 1

    snapshot = _read_room(room_document())
    assert snapshot.messages[0].authority is AuthorityLevel.COMMUNITY
    assert int(AuthorityLevel.COMMUNITY) == 3

    index = _read_index(index_document())
    assert index.rooms[0].authority is AuthorityLevel.COMMUNITY


def test_a_did_key_author_and_a_nickname_get_different_sentences() -> None:
    """``from`` is a key-shaped identifier or a self-asserted nickname."""
    assert is_did_key(DID_KEY_TEST_ONLY)
    assert not is_did_key(NICKNAME)

    keyed = describe_author(DID_KEY_TEST_ONLY)
    named = describe_author(NICKNAME)

    assert keyed.is_did_key is True
    assert named.is_did_key is False
    assert keyed.detail != named.detail
    # And the key-shaped one still does not claim the message was signed.
    assert "imzalandigini soylemez" in keyed.detail
    # Both stay community content: the level does not move, the sentence does.
    assert keyed.authority is AuthorityLevel.COMMUNITY


def test_an_absent_author_says_so_rather_than_inventing_one() -> None:
    absent = describe_author("")
    assert absent.value == ""
    assert absent.is_did_key is False
    assert absent.detail.strip()


def test_a_lookalike_did_is_treated_as_a_nickname() -> None:
    """Compared literally, so one extra character is a nickname, not a key."""
    assert not is_did_key(DID_KEY_TEST_ONLY + "1")
    assert not is_did_key(DID_KEY_TEST_ONLY[:-1])
    assert not is_did_key("did:key:z6Mk")


def test_the_caller_written_fields_are_named_in_our_own_module() -> None:
    """A reply that shortened its own ``untrusted`` list must not widen trust."""
    assert set(CALLER_WRITTEN_ROOM_FIELDS) == {"room", "topic"}

    lying = index_document()
    lying["untrusted"] = {"fields": [], "note": "TEST-ONLY: nothing is untrusted."}
    snapshot = _read_index(lying)

    assert snapshot.rooms[0].authority is AuthorityLevel.COMMUNITY


def test_invisible_characters_in_remote_text_are_swept() -> None:
    """Remote content is data: it is swept before it is stored or shown."""
    hostile = "yardimci olabilir" + chr(0x202E) + "mi" + chr(0) + "acaba"
    snapshot = _read_room(room_document(messages=[message(1, hostile)]))
    text = snapshot.messages[0].text

    assert chr(0x202E) not in text
    assert chr(0) not in text
    assert "yardimci olabilir" in text
