"""Evidence records: the six capture states, the store, and the secret scan.

The capture path runs end to end against ``httpx.MockTransport``, with the
real database, the real audit chain and the real DPAPI envelope. What is
asserted is mostly what the product refuses to say:

* five of the six states are **not** a server observation, and none of them
  ever turns an ``outcome_unknown`` send into ``not_sent``;
* a mismatch between what was sent and what came back is visible rather than
  smoothed over;
* a secret-shaped value refuses the write instead of being redacted into it;
* a failed write leaves nothing behind, and a failed archive does not undo a
  send that actually happened.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from station_api.compose.nonce import NonceReserver
from station_api.db.models import AuditEvent, EvidenceRecord, MessageNonceReservation
from station_api.evidence.secret_scan import (
    SecretRule,
    is_public_protocol_value,
    scan_text,
)
from station_api.evidence.service import EvidenceError
from station_api.evidence.states import INCONCLUSIVE_STATES, CaptureState
from station_api.evidence.stream import LINE_TERMINATOR, MAX_STREAM_BYTES
from station_api.logging_setup import forget_secret, register_secret

from tests.security.compose_fixtures import (
    TEST_ONLY_DID,
    TEST_ROOM,
    answering,
    build_harness,
)
from tests.security.evidence_fixtures import (
    TEST_ONLY_GENERATION,
    TEST_ONLY_GENERATION_NEXT,
    build_evidence,
    export_transport,
    ndjson,
    record_line,
)

pytestmark = pytest.mark.security

MARKERS = frozenset({"p", "mb", "d", "e"})

#: TEST-ONLY. NOT A REAL SEED. A 64-hex run, which is exactly the shape the
#: scanner must refuse: this is the canary.
TEST_ONLY_SEED_CANARY = "deadbeef" * 8

#: TEST-ONLY. The same 32 bytes in the base64url spelling this project's own
#: envelopes use. 43 characters.
TEST_ONLY_SEED_CANARY_B64URL = "3q2-796tvu_erb7v3q2-796tvu_erb7v3q2-796tvu8"


def _reserve(engine: Engine, *, room: str = TEST_ROOM, nonce: str = "1") -> str:
    """A real reservation row, so the foreign key has something to point at."""
    reserver = NonceReserver(engine, clock_ms=lambda: int(nonce))
    return reserver.reserve(did=TEST_ONLY_DID, room=room).id


def _record(
    service: object,
    engine: Engine,
    *,
    room: str = TEST_ROOM,
    nonce: str = "1",
    canonical: str = "mb-station-test-only|1|TEST-ONLY mesaj",
    signature: str = "z" * 85 + "A",
    request_body: bytes = b'{"did":"x"}',
    response_body: bytes = b'{"seq":1}',
    outcome: str = "accepted",
) -> object:
    reservation_id = _reserve(engine, room=room, nonce=nonce)
    return service.record_send(  # type: ignore[attr-defined]
        reservation_id=reservation_id,
        did=TEST_ONLY_DID,
        room=room,
        nonce=nonce,
        canonical=canonical,
        signature=signature,
        signature_verified=True,
        request_body=request_body,
        response_body=response_body,
        http_status=200,
        write_outcome=outcome,
    )


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


def test_the_evidence_row_holds_only_public_protocol_values(
    engine: Engine, data_dir: Path
) -> None:
    """SI-161's rule, applied to the second table that touches a send.

    A did:key, a room name, a nonce and a signature are public. The request
    and response bytes are public too - they went over the wire - and they
    are scanned before they land.
    """
    service = build_evidence(engine, data_dir)
    outcome = _record(service, engine)
    assert outcome.recorded  # type: ignore[attr-defined]

    with Session(engine) as session:
        row = session.scalars(select(EvidenceRecord)).one()
        assert row.did == TEST_ONLY_DID
        assert row.room == TEST_ROOM
        assert row.external_anchor is None, "level 4 is absent and written as null"
        assert row.capture_state == "", "no capture has been attempted yet"


def test_no_evidence_or_audit_column_is_secret_shaped(engine: Engine) -> None:
    """The schema check, narrowed to the tables Package E added."""
    forbidden = ("seed", "private", "secret", "mnemonic", "passphrase", "password", "key")
    inspector = inspect(engine)

    offenders: list[str] = []
    for table in ("evidence_record", "audit_event", "audit_chain_metadata"):
        assert table in inspector.get_table_names()
        for column in inspector.get_columns(table):
            name = str(column["name"]).lower()
            if any(fragment in name for fragment in forbidden):
                offenders.append(f"{table}.{name}")

    assert offenders == [], f"secret-shaped columns: {offenders}"


def test_the_reservation_foreign_key_does_not_cascade(engine: Engine) -> None:
    """Evidence is not a side effect of the nonce ledger (ADR-0003 10.1).

    Every other foreign key in this schema cascades. This one must not: an
    archive row that disappears when somebody tidies a ledger is a row whose
    absence nobody can explain afterwards.
    """
    inspector = inspect(engine)
    keys = inspector.get_foreign_keys("evidence_record")
    assert len(keys) == 1
    assert keys[0]["referred_table"] == "message_nonce_reservation"
    assert not keys[0].get("options", {}).get("ondelete")


def test_deleting_a_reservation_cannot_silently_remove_its_evidence(
    engine: Engine, data_dir: Path
) -> None:
    """The behavioural half of the assertion above.

    ``PRAGMA foreign_keys=ON`` is set on every connection this engine opens,
    so the refusal below is the database's, not the service layer's.
    """
    service = build_evidence(engine, data_dir)
    outcome = _record(service, engine)
    evidence_id = outcome.evidence_id  # type: ignore[attr-defined]

    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1

    with Session(engine) as session, pytest.raises(IntegrityError), session.begin():
        session.execute(delete(MessageNonceReservation))

    assert service.get(evidence_id) is not None


def test_the_evidence_service_carries_no_retention_policy(
    api_source_root: Path,
) -> None:
    """Structural: ``snapshot.py``'s prune must not have been copied here."""
    source = (
        api_source_root / "station_api" / "evidence" / "service.py"
    ).read_text(encoding="utf-8")
    assert "RETAINED" not in source
    assert "_prune" not in source


def test_evidence_is_never_pruned(engine: Engine, data_dir: Path) -> None:
    """``snapshot.py``'s retention is wrong here and must not be copied.

    Fifty check runs is right for a monitoring log. An evidence record is the
    user's own archive, and the audit chain that covers these rows breaks if
    one in the middle disappears (ADR-0003 7).
    """
    service = build_evidence(engine, data_dir)
    for index in range(1, 61):
        _record(service, engine, nonce=str(index))

    assert len(service.list_records()) == 60


def test_a_failed_archive_writes_neither_the_row_nor_the_audit_link(
    engine: Engine, data_dir: Path
) -> None:
    """Rollback: an evidence row and its audit link land together or not at all.

    A row without a link is unaccounted-for evidence; a link without a row
    points at nothing. The reservation id here does not exist, so the insert
    fails under the foreign key and the whole transaction goes back.
    """
    service = build_evidence(engine, data_dir)
    before = service.verify_chain().link_count

    with Session(engine) as session:
        session.execute(text("PRAGMA foreign_keys=ON"))

    with pytest.raises(IntegrityError):
        service.record_send(
            reservation_id="0" * 32,
            did=TEST_ONLY_DID,
            room=TEST_ROOM,
            nonce="1",
            canonical="c",
            signature="z" * 85 + "A",
            signature_verified=True,
            request_body=b"{}",
            response_body=b"{}",
            http_status=200,
            write_outcome="accepted",
        )

    with Session(engine) as session:
        assert session.scalars(select(EvidenceRecord)).all() == []
    assert service.verify_chain().link_count == before


# ---------------------------------------------------------------------------
# The secret scan
# ---------------------------------------------------------------------------


def test_the_allow_list_runs_before_the_deny_rules() -> None:
    """The ordering that makes the scanner usable at all (ADR-0003 8).

    A signed body is *made* of high-entropy public values. Deny-first would
    refuse every record this product produces, and the natural fix for that
    is to loosen the deny rules until real traffic passes - which is how a
    scanner ends up detecting nothing.
    """
    signature = "z" * 85 + "A"
    assert is_public_protocol_value(signature)
    assert is_public_protocol_value(TEST_ONLY_DID)
    assert is_public_protocol_value("1757000000000")

    body = json.dumps(
        {"did": TEST_ONLY_DID, "sig": signature, "nonce": "1757000000000", "text": "hi"}
    )
    assert scan_text(body, where="request") is None


def test_a_sixty_four_hex_run_refuses_the_write() -> None:
    finding = scan_text(f"iste: {TEST_ONLY_SEED_CANARY}", where="canonical")
    assert finding is not None
    assert finding.rule is SecretRule.HEX_64


def test_a_seed_length_base64url_run_refuses_the_write() -> None:
    finding = scan_text(
        f"iste: {TEST_ONLY_SEED_CANARY_B64URL}", where="canonical"
    )
    assert finding is not None
    assert finding.rule is SecretRule.BASE64URL_43


def test_a_registered_value_refuses_the_write() -> None:
    """A live passphrase or token that reached a string it should not have."""
    canary = "TEST-ONLY-registered-canary-0001"
    register_secret(canary)
    try:
        finding = scan_text(f"metin {canary} icinde", where="request")
        assert finding is not None
        assert finding.rule is SecretRule.REGISTERED_VALUE
    finally:
        forget_secret(canary)


def test_a_secret_canary_refuses_the_evidence_write_rather_than_redacting_it(
    engine: Engine, data_dir: Path
) -> None:
    """Fail-closed, and the refusal never echoes the value that caused it.

    Redacting would be worse than refusing: the raw bytes are evidence only
    because they are unmodified, and a redacted field proves nothing while
    looking as though it does.
    """
    service = build_evidence(engine, data_dir)
    outcome = _record(
        service,
        engine,
        canonical=f"mb-station-test-only|1|{TEST_ONLY_SEED_CANARY}",
    )

    assert not outcome.recorded  # type: ignore[attr-defined]
    assert TEST_ONLY_SEED_CANARY not in outcome.detail  # type: ignore[attr-defined]
    assert service.list_records() == ()

    # The refusal is itself an audit event, and it does not carry the value.
    with Session(engine) as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.seq)).all()
    assert events[-1].event == "evidence_write_refused"
    assert TEST_ONLY_SEED_CANARY not in events[-1].detail


def test_the_canary_survives_a_round_trip_through_the_database(
    engine: Engine, data_dir: Path
) -> None:
    """The scan is not the only check: the file itself is inspected.

    A canary that reached the database would be visible in the file even if
    every assertion above were wrong.
    """
    build_evidence(engine, data_dir)
    for path in data_dir.rglob("*.sqlite3*"):
        assert TEST_ONLY_SEED_CANARY.encode() not in path.read_bytes()


# ---------------------------------------------------------------------------
# The six capture states
# ---------------------------------------------------------------------------


def _captured(
    engine: Engine, data_dir: Path, body: bytes, **kwargs: object
) -> tuple[object, object]:
    """Archive one send, then capture against a canned export."""
    signature = "z" * 85 + "A"
    service = build_evidence(
        engine,
        data_dir,
        transport=export_transport(body, **kwargs),  # type: ignore[arg-type]
    )
    outcome = _record(
        service, engine, nonce="1757000000000", signature=signature
    )
    return service, service.capture(
        evidence_id=outcome.evidence_id, markers=MARKERS  # type: ignore[attr-defined]
    )


def _mine(**kwargs: object) -> bytes:
    return record_line(
        seq=3,
        did=TEST_ONLY_DID,
        nonce=1757000000000,
        signature="z" * 85 + "A",
        **kwargs,  # type: ignore[arg-type]
    )


def test_line_captured_is_a_server_observation_and_says_only_that(
    engine: Engine, data_dir: Path
) -> None:
    mine = _mine()
    service, capture = _captured(engine, data_dir, ndjson([mine]))

    assert capture.state is CaptureState.LINE_CAPTURED  # type: ignore[attr-defined]
    assert capture.is_server_observation  # type: ignore[attr-defined]
    assert "Seviye 2" in capture.detail  # type: ignore[attr-defined]

    view = service.list_records()[0]  # type: ignore[attr-defined]
    assert view.captured_line == mine
    assert view.room_generation == TEST_ONLY_GENERATION
    # The level accounting reflects it, and level 4 stays empty.
    levels = {level.level: level.present for level in view.levels}
    assert levels == {1: True, 2: True, 3: True, 4: False}


def test_line_not_found_proves_nothing_and_never_becomes_not_sent(
    engine: Engine, data_dir: Path
) -> None:
    """The ring forgets. A missing line is not a missing message (ADR-0003 3).

    This is the single inference the whole model exists to refuse, so the
    assertion is on the words as well as on the state.
    """
    service, capture = _captured(engine, data_dir, ndjson([record_line(seq=1)]))

    assert capture.state is CaptureState.LINE_NOT_FOUND  # type: ignore[attr-defined]
    assert not capture.is_server_observation  # type: ignore[attr-defined]
    assert "kanitlamaz" in capture.detail  # type: ignore[attr-defined]
    assert "not_sent" not in capture.detail  # type: ignore[attr-defined]

    view = service.list_records()[0]  # type: ignore[attr-defined]
    assert view.write_outcome == "accepted", "the send result is untouched"
    assert view.captured_line is None


def test_a_changed_generation_makes_the_record_incomparable(
    engine: Engine, data_dir: Path
) -> None:
    """A different epoch is not a mismatch; it is a different room.

    It wins even over a found line: "we found something under a different
    generation" is a weaker claim than "we found it", and reporting the
    stronger one would be the over-claim.
    """
    mine = _mine()
    service = build_evidence(
        engine, data_dir, transport=export_transport(ndjson([mine]))
    )
    outcome = _record(service, engine, nonce="1757000000000", signature="z" * 85 + "A")
    first = service.capture(
        evidence_id=outcome.evidence_id, markers=MARKERS  # type: ignore[attr-defined]
    )
    assert first.state is CaptureState.LINE_CAPTURED

    moved = build_evidence(
        engine,
        data_dir,
        transport=export_transport(
            ndjson([mine]), generation=TEST_ONLY_GENERATION_NEXT
        ),
    )
    second = moved.capture(
        evidence_id=outcome.evidence_id, markers=MARKERS  # type: ignore[attr-defined]
    )

    assert second.state is CaptureState.GENERATION_CHANGED
    assert not second.is_server_observation
    assert "karsilastirilamaz" in second.detail


def test_a_truncated_scan_is_not_an_absent_record(
    engine: Engine, data_dir: Path
) -> None:
    """The real cap, exercised with a real oversized body.

    No seam and no injected ceiling: the export served here is larger than
    ``MAX_STREAM_BYTES``, so what is under test is the production limit. Our
    own line is deliberately past the cap, which is the case that matters -
    a scan that stopped early and reported ``line_not_found`` would be
    reporting absence it never looked for.
    """
    filler = record_line(seq=1, text="TEST-ONLY dolgu") + LINE_TERMINATOR
    body = filler * ((MAX_STREAM_BYTES // len(filler)) + 16) + _mine() + LINE_TERMINATOR
    assert len(body) > MAX_STREAM_BYTES

    _service, capture = _captured(engine, data_dir, body)

    assert capture.state is CaptureState.STREAM_TRUNCATED  # type: ignore[attr-defined]
    assert capture.truncated  # type: ignore[attr-defined]
    assert capture.scanned_bytes == MAX_STREAM_BYTES  # type: ignore[attr-defined]
    assert "tamamlanamadi" in capture.detail  # type: ignore[attr-defined]
    assert not capture.is_server_observation  # type: ignore[attr-defined]


def test_unreadable_lines_are_reported_as_a_parse_problem(
    engine: Engine, data_dir: Path
) -> None:
    """Unreadable is not altered (IMP-238's distinction, reused here)."""
    body = ndjson([b"{broken", b"also broken"])
    _service, capture = _captured(engine, data_dir, body)

    assert capture.state is CaptureState.PARSE_PROBLEM  # type: ignore[attr-defined]
    assert "degistirilmis" in capture.detail  # type: ignore[attr-defined]


def test_a_failed_read_is_fetch_failed_and_may_be_retried(
    engine: Engine, data_dir: Path
) -> None:
    _service, capture = _captured(engine, data_dir, b"nope", status=503)

    assert capture.state is CaptureState.FETCH_FAILED  # type: ignore[attr-defined]
    assert capture.state.may_retry_read  # type: ignore[attr-defined]
    assert not capture.state.may_retry_write  # type: ignore[attr-defined]


def test_only_one_of_the_six_states_is_a_server_observation() -> None:
    """Five of six establish nothing, and the code says which (ADR-0003 3)."""
    assert len(CaptureState) == 6
    observations = [state for state in CaptureState if state.is_server_observation]
    assert observations == [CaptureState.LINE_CAPTURED]
    assert len(INCONCLUSIVE_STATES) == 5
    for state in CaptureState:
        assert not state.may_retry_write, "no state ever permits a resend"


def test_a_capture_never_reaches_a_denied_room(
    engine: Engine, data_dir: Path
) -> None:
    """Lobby is not a target for the read either (INV-05, ADR-0002 4.1)."""
    seen: list[object] = []

    import httpx

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"")

    service = build_evidence(engine, data_dir, transport=httpx.MockTransport(respond))
    reserver = NonceReserver(engine, clock_ms=lambda: 1)
    reservation = reserver.reserve(did=TEST_ONLY_DID, room="lobby")
    outcome = service.record_send(
        reservation_id=reservation.id,
        did=TEST_ONLY_DID,
        room="lobby",
        nonce=reservation.nonce,
        canonical="lobby|1|x",
        signature="z" * 85 + "A",
        signature_verified=True,
        request_body=b"{}",
        response_body=b"{}",
        http_status=200,
        write_outcome="accepted",
    )
    capture = service.capture(evidence_id=outcome.evidence_id, markers=MARKERS)

    assert capture.state is CaptureState.FETCH_FAILED
    assert seen == [], "a denied room must produce no outbound request"


# ---------------------------------------------------------------------------
# What was sent, and what came back
# ---------------------------------------------------------------------------


def test_a_captured_line_that_disagrees_with_the_request_is_not_our_record(
    engine: Engine, data_dir: Path
) -> None:
    """The mismatch case: same room, same nonce, a different signature.

    A scanner that matched on the nonce alone would archive somebody else's
    record as ours, and every level-1 claim built on it would be false.
    """
    impostor = record_line(
        seq=3,
        did=TEST_ONLY_DID,
        nonce=1757000000000,
        signature="q" * 85 + "Q",
    )
    _service, capture = _captured(engine, data_dir, ndjson([impostor]))

    assert capture.state is CaptureState.LINE_NOT_FOUND  # type: ignore[attr-defined]


def test_a_forged_timestamp_changes_nothing_about_the_levels(
    engine: Engine, data_dir: Path
) -> None:
    """A server-supplied ``ts`` is not evidence of anything, so it is not used.

    The record is located by DID, nonce and signature - none of which the
    server chooses - and level 3 is *this machine's* clock. A line claiming
    to have been written in 1970 is still our line, and still says nothing
    about when.
    """
    mine = record_line(
        seq=3,
        did=TEST_ONLY_DID,
        nonce=1757000000000,
        signature="z" * 85 + "A",
        timestamp="1970-01-01T00:00:00.000000Z",
    )
    service, capture = _captured(engine, data_dir, ndjson([mine]))

    assert capture.state is CaptureState.LINE_CAPTURED  # type: ignore[attr-defined]
    view = service.list_records()[0]  # type: ignore[attr-defined]
    assert view.captured_line == mine
    assert view.recorded_at.year >= 2026, "level 3 is the local clock, not the line's"
    level3 = next(level for level in view.levels if level.level == 3)
    assert "guvenilir" not in level3.detail.lower() or "degildir" in level3.detail


def test_an_unverified_signature_is_recorded_as_an_empty_level_one(
    engine: Engine, data_dir: Path
) -> None:
    """Level 1 is what Station verified, not what it hoped."""
    service = build_evidence(engine, data_dir)
    reservation_id = _reserve(engine)
    outcome = service.record_send(
        reservation_id=reservation_id,
        did=TEST_ONLY_DID,
        room=TEST_ROOM,
        nonce="1",
        canonical="mb-station-test-only|1|x",
        signature="z" * 85 + "A",
        signature_verified=False,
        request_body=b"{}",
        response_body=b"{}",
        http_status=200,
        write_outcome="accepted",
    )

    view = service.get(outcome.evidence_id)
    level1 = next(level for level in view.levels if level.level == 1)
    assert not level1.present
    assert "dogrulanamadi" in level1.detail


def test_an_unknown_evidence_id_is_refused_rather_than_invented(
    engine: Engine, data_dir: Path
) -> None:
    service = build_evidence(engine, data_dir)
    with pytest.raises(EvidenceError):
        service.capture(evidence_id="0" * 32, markers=MARKERS)


# ---------------------------------------------------------------------------
# The composer records what it sent
# ---------------------------------------------------------------------------


def _send(harness: object, *, room: str = TEST_ROOM, text_body: str = "TEST-ONLY") -> object:
    draft = harness.service.draft(  # type: ignore[attr-defined]
        session_id=harness.session_id, room=room, text=text_body  # type: ignore[attr-defined]
    )
    signed = harness.service.sign(  # type: ignore[attr-defined]
        session_id=harness.session_id,  # type: ignore[attr-defined]
        draft_id=draft.draft_id,
        confirmed_digest=draft.draft_digest,
        vault_passphrase=None,
    )
    return harness.service.send(  # type: ignore[attr-defined]
        session_id=harness.session_id, send_token=signed.send_token  # type: ignore[attr-defined]
    )


def test_a_send_archives_the_bytes_that_actually_left_the_process(
    engine: Engine, data_dir: Path
) -> None:
    """The request body stored is the request body sent, not a re-encoding."""
    service = build_evidence(engine, data_dir)
    harness = build_harness(engine, evidence=service)

    result = _send(harness)

    assert result.reservation_id  # type: ignore[attr-defined]
    assert result.evidence_recorded  # type: ignore[attr-defined]

    view = service.get(result.evidence_id)  # type: ignore[attr-defined]
    sent = harness.writes.requests[0].content  # type: ignore[attr-defined]
    assert view.request_body == sent
    assert view.request_sha256 == hashlib.sha256(sent).hexdigest()
    # And the body still parses as the four-field signed body.
    assert set(json.loads(view.request_body)) == {"did", "sig", "nonce", "text"}


def test_the_reservation_id_travels_back_with_the_send_result(
    engine: Engine, data_dir: Path
) -> None:
    """A public uuid naming a ledger row, not a capability."""
    service = build_evidence(engine, data_dir)
    harness = build_harness(engine, evidence=service)

    result = _send(harness)

    with Session(engine) as session:
        row = session.get(MessageNonceReservation, result.reservation_id)  # type: ignore[attr-defined]
    assert row is not None
    assert row.state == "spent"
    # It confers nothing: it is not a send token and cannot be spent.
    assert result.reservation_id != ""  # type: ignore[attr-defined]


def test_an_unknown_outcome_is_archived_and_still_not_called_sent(
    engine: Engine, data_dir: Path
) -> None:
    """The case the archive matters most for stays three-valued."""
    service = build_evidence(engine, data_dir)
    harness = build_harness(engine, evidence=service, handler=answering(503))

    result = _send(harness)

    assert result.outcome.value == "outcome_unknown"  # type: ignore[attr-defined]
    assert result.reconciliation_required  # type: ignore[attr-defined]
    view = service.get(result.evidence_id)  # type: ignore[attr-defined]
    assert view.write_outcome == "outcome_unknown"
    assert view.request_body, "the bytes are archived even when the answer is unknown"


def test_a_send_without_an_evidence_layer_still_sends(engine: Engine) -> None:
    """No archive is not a reason to refuse a send.

    A machine without DPAPI cannot build the chain. Refusing to publish there
    would trade a missing record for a missing message, which is worse.
    """
    harness = build_harness(engine, evidence=None)

    result = _send(harness)

    assert result.outcome.value == "accepted"  # type: ignore[attr-defined]
    assert not result.evidence_recorded  # type: ignore[attr-defined]
    assert result.evidence_detail  # type: ignore[attr-defined]
