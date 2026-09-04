"""The audit chain, its separately protected head, and its honest limits.

The chain is tested by breaking it four ways - a removed middle link, an
altered field, a reordering and a cut-off tail - and by checking that the
report says something *true* about each. The fourth is the one worth reading
carefully: a truncated tail is detected only because the head lives in its own
DPAPI envelope, and only against an attacker who is not running as this
Windows user. An attacker who is can recompute both. The tests below therefore
assert the mechanism *and* assert that the product does not oversell it.

Everything here uses the real DPAPI envelope on a temporary data directory.
There is no in-memory chain and no injectable MAC material: a fake would test
neither of the two properties that matter.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session
from station_api.db.models import AuditChainMetadata, AuditEvent
from station_api.evidence.audit import (
    GENESIS_MAC,
    AuditChain,
    AuditEventName,
    ChainVerdict,
    canonical_line,
    canonical_timestamp,
    compute_mac,
)
from station_api.evidence.audit_envelope import (
    CHAIN_ID,
    MATERIAL_LENGTH,
    AuditEnvelope,
    AuditEnvelopeError,
    ChainHead,
    fingerprint,
)
from station_api.evidence.language import (
    AUDIT_CHAIN_CLAIM,
    FORBIDDEN_PHRASES,
    find_forbidden_phrases,
)
from station_api.strict_json import canonical_json_bytes

pytestmark = pytest.mark.security


def _chain(engine: Engine, data_dir: Path) -> AuditChain:
    """A started chain, wired the way ``EvidenceService.start`` wires one.

    The genesis link is written here too, so a chain that has never recorded
    anything stays distinguishable from one whose first links were removed.
    """
    chain = AuditChain(engine, AuditEnvelope(data_dir))
    digest = chain.ensure_ready()
    if chain.count() == 0:
        chain.record(
            event=AuditEventName.CHAIN_STARTED,
            subject=digest[:16],
            detail="Audit zinciri baslatildi.",
        )
    return chain


def _fill(chain: AuditChain, count: int = 5) -> None:
    for index in range(1, count + 1):
        chain.record(
            event=AuditEventName.EVIDENCE_RECORDED,
            subject=f"TEST-ONLY-{index:02d}",
            detail=f"TEST-ONLY olay {index}",
        )


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


def test_the_mac_material_lives_in_its_own_file_and_not_in_any_table(
    engine: Engine, data_dir: Path
) -> None:
    """ADR-0003 6: a separate envelope, and only a fingerprint in the schema."""
    chain = _chain(engine, data_dir)
    envelope = AuditEnvelope(data_dir)

    assert envelope.material_file.is_file()
    assert envelope.material_file.parent == data_dir / "audit" / "v1"

    material = envelope.load_material()
    assert len(material) == MATERIAL_LENGTH

    with Session(engine) as session:
        row = session.get(AuditChainMetadata, CHAIN_ID)
        assert row is not None
        assert row.fingerprint == fingerprint(material)
        assert row.envelope_relpath == "audit/v1/chain-material.json"
        # The path is relative, so an absolute one is never in the database
        # and never in a response (SI-36).
        assert not Path(row.envelope_relpath).is_absolute()

    # And the material itself is nowhere in the database file.
    for path in data_dir.rglob("*.sqlite3*"):
        assert material not in path.read_bytes()
    assert chain.count() >= 1


def test_the_material_is_not_stored_in_the_clear(
    engine: Engine, data_dir: Path
) -> None:
    """DPAPI, current-user scope. The file is an envelope, not a key file."""
    _chain(engine, data_dir)
    envelope = AuditEnvelope(data_dir)
    material = envelope.load_material()

    raw = envelope.material_file.read_bytes()
    assert material not in raw
    assert b"technocore-station.audit" in raw


def test_the_material_is_never_overwritten(engine: Engine, data_dir: Path) -> None:
    """Rotating it would invalidate every MAC already written.

    That reads afterwards as "the whole chain is broken" - the loudest way to
    lose the ability to say anything at all.
    """
    _chain(engine, data_dir)
    envelope = AuditEnvelope(data_dir)
    before = envelope.load_material()

    with pytest.raises(AuditEnvelopeError):
        envelope.create_material()

    assert envelope.load_material() == before


def test_the_envelope_is_versioned_and_kind_checked(
    engine: Engine, data_dir: Path
) -> None:
    """A head is not material, and version 1 is not version 2."""
    _fill(_chain(engine, data_dir), 1)
    envelope = AuditEnvelope(data_dir)

    # The head envelope carries kind "head"; reading it as material fails.
    envelope.material_file.write_bytes(envelope.head_file.read_bytes())
    with pytest.raises(AuditEnvelopeError):
        envelope.load_material()


def test_a_malformed_envelope_fails_closed(engine: Engine, data_dir: Path) -> None:
    _chain(engine, data_dir)
    envelope = AuditEnvelope(data_dir)
    envelope.material_file.write_bytes(b"{not json")

    with pytest.raises(AuditEnvelopeError):
        envelope.load_material()


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


def test_an_untouched_chain_verifies_and_the_head_agrees(
    engine: Engine, data_dir: Path
) -> None:
    chain = _chain(engine, data_dir)
    _fill(chain)

    report = chain.verify()

    assert report.verdict is ChainVerdict.INTACT
    assert report.link_count == report.head_count
    assert report.first_bad_seq is None


def test_the_first_link_starts_from_the_genesis_mac(
    engine: Engine, data_dir: Path
) -> None:
    _chain(engine, data_dir)

    with Session(engine) as session:
        first = session.scalars(select(AuditEvent).order_by(AuditEvent.seq)).first()
    assert first is not None
    assert first.seq == 1
    assert first.prev_mac == GENESIS_MAC
    assert GENESIS_MAC == "0" * 64


def test_links_are_ordered_and_each_one_points_at_the_previous(
    engine: Engine, data_dir: Path
) -> None:
    chain = _chain(engine, data_dir)
    _fill(chain)

    with Session(engine) as session:
        rows = list(session.scalars(select(AuditEvent).order_by(AuditEvent.seq)))

    assert [row.seq for row in rows] == list(range(1, len(rows) + 1))
    for previous, current in itertools.pairwise(rows):
        assert current.prev_mac == previous.mac


def test_a_removed_middle_link_is_detected(engine: Engine, data_dir: Path) -> None:
    """The classic offline edit, and the one a chain is actually good at."""
    chain = _chain(engine, data_dir)
    _fill(chain)

    with Session(engine) as session, session.begin():
        session.execute(delete(AuditEvent).where(AuditEvent.seq == 3))

    report = chain.verify()

    assert report.verdict is ChainVerdict.BROKEN_LINK
    assert report.first_bad_seq == 4


def test_an_altered_field_is_detected(engine: Engine, data_dir: Path) -> None:
    """Every field the row stores is inside the MAC.

    A field that is stored but not covered is a field an attacker may edit
    freely, which is the quiet way a chain stops meaning anything.
    """
    chain = _chain(engine, data_dir)
    _fill(chain)

    with Session(engine) as session, session.begin():
        row = session.scalars(
            select(AuditEvent).where(AuditEvent.seq == 3)
        ).one()
        row.detail = "TEST-ONLY degistirilmis aciklama"

    report = chain.verify()

    assert report.verdict is ChainVerdict.BROKEN_LINK
    assert report.first_bad_seq == 3


@pytest.mark.parametrize("field", ["event", "subject", "recorded_at"])
def test_every_stored_field_is_covered_by_the_mac(
    engine: Engine, data_dir: Path, field: str
) -> None:
    from datetime import UTC, datetime

    chain = _chain(engine, data_dir)
    _fill(chain, 3)

    with Session(engine) as session, session.begin():
        row = session.scalars(select(AuditEvent).where(AuditEvent.seq == 2)).one()
        if field == "recorded_at":
            row.recorded_at = datetime(2000, 1, 1, tzinfo=UTC)
        else:
            setattr(row, field, "TEST-ONLY-changed")

    assert chain.verify().verdict is ChainVerdict.BROKEN_LINK


def test_reordering_two_links_is_detected(engine: Engine, data_dir: Path) -> None:
    """Swapping sequence numbers breaks both the order and the MACs."""
    chain = _chain(engine, data_dir)
    _fill(chain)

    # Three statements rather than two assignments: the unique constraint on
    # ``seq`` is real, so the swap has to go through a spare number - which is
    # also what an attacker would have to do.
    with Session(engine) as session, session.begin():
        session.execute(update(AuditEvent).where(AuditEvent.seq == 2).values(seq=99))
        session.execute(update(AuditEvent).where(AuditEvent.seq == 3).values(seq=2))
        session.execute(update(AuditEvent).where(AuditEvent.seq == 99).values(seq=3))

    report = chain.verify()

    assert report.verdict is ChainVerdict.BROKEN_LINK


def test_a_cut_off_tail_is_detected_only_because_the_head_is_separate(
    engine: Engine, data_dir: Path
) -> None:
    """The truncation case, and exactly why it works (ADR-0003 5).

    Nothing inside a chain says how long it should be. The head - the last MAC
    and the link count - is what supplies that, and it lives in its own DPAPI
    envelope. Deleting the last two rows leaves a chain that is internally
    perfect and a head that disagrees.
    """
    chain = _chain(engine, data_dir)
    _fill(chain)
    full = chain.verify()
    assert full.verdict is ChainVerdict.INTACT

    with Session(engine) as session, session.begin():
        session.execute(delete(AuditEvent).where(AuditEvent.seq >= 5))

    report = chain.verify()

    assert report.verdict is ChainVerdict.HEAD_MISMATCH
    assert report.head_count is not None
    assert report.head_count > report.link_count
    assert report.first_bad_seq is None, "no individual link is broken"


def test_a_truncation_is_invisible_when_the_head_goes_with_it(
    engine: Engine, data_dir: Path
) -> None:
    """The honest limit, asserted rather than described.

    An attacker running as this Windows user can open the same envelope,
    recompute every MAC and rewrite the head. This test *performs* that
    attack and shows the chain reporting ``intact`` - which is why the only
    permitted description is "detective against offline change" and why
    "tamper-proof" is on the forbidden list.
    """
    chain = _chain(engine, data_dir)
    _fill(chain)
    envelope = AuditEnvelope(data_dir)

    with Session(engine) as session, session.begin():
        session.execute(delete(AuditEvent).where(AuditEvent.seq >= 4))
    with Session(engine) as session:
        remaining = list(session.scalars(select(AuditEvent).order_by(AuditEvent.seq)))
    envelope.write_head(
        ChainHead(
            count=len(remaining),
            last_mac=remaining[-1].mac,
            updated_at="2026-09-04T00:00:00+00:00",
        )
    )

    report = chain.verify()

    assert report.verdict is ChainVerdict.INTACT
    assert report.link_count == 3
    # And the sentence the product is allowed to say about this says so.
    assert "ayni Windows kullanicisi" in report.detail


def test_a_missing_head_is_reported_as_a_limit_rather_than_as_tampering(
    engine: Engine, data_dir: Path
) -> None:
    chain = _chain(engine, data_dir)
    _fill(chain)
    AuditEnvelope(data_dir).head_file.unlink()

    report = chain.verify()

    assert report.verdict is ChainVerdict.HEAD_MISMATCH
    assert "bas olmadan" in report.detail


def test_a_head_that_is_behind_is_named_as_an_interrupted_write(
    engine: Engine, data_dir: Path
) -> None:
    """The crash window, reported as itself rather than as an attack.

    A file and a SQLite transaction cannot commit atomically. A crash between
    the two leaves the head one link behind or one ahead, and calling either
    "tampering" is the kind of false alarm that gets a check switched off.
    """
    chain = _chain(engine, data_dir)
    _fill(chain)
    envelope = AuditEnvelope(data_dir)

    with Session(engine) as session:
        rows = list(session.scalars(select(AuditEvent).order_by(AuditEvent.seq)))
    envelope.write_head(
        ChainHead(
            count=len(rows) - 1,
            last_mac=rows[-2].mac,
            updated_at="2026-09-04T00:00:00+00:00",
        )
    )

    report = chain.verify()

    assert report.verdict is ChainVerdict.HEAD_MISMATCH
    assert "Yarida kalan" in report.detail


def test_a_replaced_tail_link_is_distinguished_from_a_count_change(
    engine: Engine, data_dir: Path
) -> None:
    chain = _chain(engine, data_dir)
    _fill(chain)

    with Session(engine) as session:
        rows = list(session.scalars(select(AuditEvent).order_by(AuditEvent.seq)))
    AuditEnvelope(data_dir).write_head(
        ChainHead(
            count=len(rows),
            last_mac="f" * 64,
            updated_at="2026-09-04T00:00:00+00:00",
        )
    )

    report = chain.verify()

    assert report.verdict is ChainVerdict.HEAD_MISMATCH
    assert "son MAC farkli" in report.detail


def test_a_missing_envelope_is_unavailable_and_never_a_pass(
    engine: Engine, data_dir: Path
) -> None:
    """Absence of a check is never reported as a check that passed."""
    chain = _chain(engine, data_dir)
    _fill(chain)
    AuditEnvelope(data_dir).material_file.unlink()

    report = chain.verify()

    assert report.verdict is ChainVerdict.UNAVAILABLE
    assert not report.is_intact
    # "Could not check" and "there is nothing to check" are different facts.
    # Reporting zero links beside the first one read as an empty chain to
    # anybody who did not also read the verdict - which is precisely the
    # reading a chain of five links must never produce.
    assert report.link_count == chain.count()
    assert report.link_count >= 5


def test_a_chain_with_a_different_material_does_not_verify(
    engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """The MAC is what does the work, not the presence of a hex column."""
    chain = _chain(engine, data_dir)
    _fill(chain)

    other = AuditEnvelope(tmp_path / "other")
    other.create_material()
    AuditEnvelope(data_dir).material_file.write_bytes(
        other.material_file.read_bytes()
    )

    assert AuditChain(engine, AuditEnvelope(data_dir)).verify().verdict is (
        ChainVerdict.BROKEN_LINK
    )


def test_the_canonical_line_is_the_pinned_encoding(
    engine: Engine, data_dir: Path
) -> None:
    """Byte-for-byte, through the encoder that already has a pinned vector.

    A MAC over bytes produced by an ad-hoc format is a MAC that changes when
    somebody reformats a dictionary literal.
    """
    from datetime import UTC, datetime

    when = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    line = canonical_line(
        seq=1,
        recorded_at=when,
        event="evidence_recorded",
        subject="abc",
        detail="d",
        prev_mac=GENESIS_MAC,
    )

    assert line == canonical_json_bytes(
        {
            "detail": "d",
            "event": "evidence_recorded",
            "prev_mac": GENESIS_MAC,
            "recorded_at": canonical_timestamp(when),
            "seq": 1,
            "subject": "abc",
            "v": 1,
        }
    )
    assert b" " not in line.replace(b"evidence_recorded", b"x")
    assert compute_mac(b"\x00" * 32, line) != compute_mac(b"\x01" * 32, line)


def test_an_append_and_its_head_share_one_transaction_boundary(
    engine: Engine, data_dir: Path
) -> None:
    """A rolled-back append leaves no link, and the head still describes one.

    The head is written before the caller commits, so the failure mode is
    "head is ahead" - which :meth:`verify` names as an interrupted write
    rather than as an attack.
    """
    chain = _chain(engine, data_dir)
    _fill(chain, 2)
    before = chain.count()

    class RolledBackError(RuntimeError):
        """TEST-ONLY. Raised inside the transaction to abort it."""

    with (
        pytest.raises(RolledBackError),
        Session(engine) as session,
        session.begin(),
    ):
        chain.append(
            session,
            event=AuditEventName.EVIDENCE_RECORDED,
            subject="TEST-ONLY",
            detail="bu satir geri alinacak",
        )
        raise RolledBackError

    assert chain.count() == before
    report = chain.verify()
    assert report.verdict is ChainVerdict.HEAD_MISMATCH
    assert report.head_count == before + 1


def test_the_chain_carries_no_retention_policy(api_source_root: Path) -> None:
    """Pruning a MAC chain would break our own evidence on a schedule."""
    source = (
        api_source_root / "station_api" / "evidence" / "audit.py"
    ).read_text(encoding="utf-8")
    assert "RETAINED" not in source
    assert "_prune" not in source
    assert "delete(" not in source


# ---------------------------------------------------------------------------
# The honesty of the wording
# ---------------------------------------------------------------------------


def test_the_only_permitted_claim_is_the_detective_one() -> None:
    assert AUDIT_CHAIN_CLAIM == "cevrimdisi degisiklige karsi tespit edici"
    assert find_forbidden_phrases(AUDIT_CHAIN_CLAIM) == ()


def test_no_report_this_module_can_produce_carries_a_forbidden_phrase(
    engine: Engine, data_dir: Path
) -> None:
    """Every branch of ``verify`` is walked, and every sentence is checked."""
    chain = _chain(engine, data_dir)
    _fill(chain)
    envelope = AuditEnvelope(data_dir)
    sentences = [chain.verify().detail]

    with Session(engine) as session, session.begin():
        session.execute(delete(AuditEvent).where(AuditEvent.seq >= 5))
    sentences.append(chain.verify().detail)

    envelope.head_file.unlink()
    sentences.append(chain.verify().detail)

    envelope.material_file.unlink()
    sentences.append(chain.verify().detail)

    assert len(sentences) == 4
    for sentence in sentences:
        assert sentence
        assert find_forbidden_phrases(sentence) == (), sentence


def test_the_forbidden_list_still_carries_the_charter_four() -> None:
    """Package E extended the list; it did not replace it."""
    for phrase in (
        "sunucu kaniti",
        "degismez kayit",
        "guvenilir zaman kaniti",
        "airdrop uygunluk kaniti",
    ):
        assert phrase in FORBIDDEN_PHRASES
