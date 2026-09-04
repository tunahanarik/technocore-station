"""The append-only audit chain.

Each line is bound to the one before it::

    mac(n) = HMAC-SHA256(material, canonical_line(n, prev_mac = mac(n-1)))

The canonical line is produced by
:func:`station_api.strict_json.canonical_json_bytes` - the same encoding the
vault envelope uses, already pinned byte for byte by a test vector, so the
bytes a MAC covers cannot drift with a formatting change.

What this detects, stated once and not embellished
--------------------------------------------------
* a line removed from the **middle**: the next line's ``prev_mac`` no longer
  matches, and its sequence number leaves a gap;
* a field **altered** in any line: that line's MAC no longer recomputes;
* lines **reordered**: sequence numbers and ``prev_mac`` disagree.

What it does not detect on its own
----------------------------------
* the **tail being cut off**. Nothing inside a chain says how long it should
  be. The chain head - the last MAC and the link count - is kept in a
  separate DPAPI envelope and updated inside the same transaction block as
  the append, which detects a truncation performed by someone who is **not
  running as this Windows user**.
* An attacker who *is* running as this Windows user can open the same
  envelope, recompute every MAC and rewrite the head. That is not a gap in
  the implementation; it is what "protected by DPAPI current-user scope"
  means (SECURITY.md 7). It is why the only permitted description of this
  mechanism is **"cevrimdisi degisiklige karsi tespit edici"** and why the
  words that would over-claim it are refused by
  :mod:`station_api.evidence.language`.
* a trusted time. ``recorded_at`` is this machine's clock, level 3.

Never pruned
------------
There is no retention policy here and there must not be one: deleting a link
from the middle is the thing the chain exists to reveal (ADR-0003 7).
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from station_api.db.models import AuditChainMetadata, AuditEvent
from station_api.evidence.audit_envelope import (
    CHAIN_ID,
    AuditEnvelope,
    AuditEnvelopeError,
    ChainHead,
    fingerprint,
)
from station_api.evidence.language import assert_no_forbidden_claim
from station_api.logging_setup import redact
from station_api.strict_json import canonical_json_bytes
from station_api.technocore.projection import safe_display

#: ``prev_mac`` of the first link. Sixty-four zeros rather than an empty
#: string, so every row has the same shape and a missing value cannot be
#: mistaken for the genesis one.
GENESIS_MAC = "0" * 64

#: Longest detail a link carries. A detail is a sentence, not a payload.
MAX_DETAIL_CHARS = 500


class AuditEventName(StrEnum):
    """The events this release records. A closed set, like every registry."""

    EVIDENCE_RECORDED = "evidence_recorded"
    EVIDENCE_WRITE_REFUSED = "evidence_write_refused"
    CAPTURE_ATTEMPTED = "capture_attempted"
    EVIDENCE_EXPORTED = "evidence_exported"
    CHAIN_STARTED = "chain_started"
    # ``evidence_deleted`` is deliberately **absent**. ADR-0003 7 has two
    # halves: evidence is never pruned automatically, and a deletion a user
    # asks for is itself an audit event. The first half is implemented; the
    # second is not - there is no deletion route, and a name in this enum that
    # nothing can ever record would be a reader's evidence for a feature that
    # does not exist. The deferral is recorded in ``docs/decisions/README.md``
    # (IMP-329) rather than hinted at here.


class ChainVerdict(StrEnum):
    """What a verification pass established."""

    #: Every link recomputes and the head agrees.
    INTACT = "intact"
    #: No links yet, and no head claiming otherwise.
    EMPTY = "empty"
    #: A link does not recompute, a sequence number is missing, or a
    #: ``prev_mac`` does not match its predecessor.
    BROKEN_LINK = "broken_link"
    #: Every link recomputes, but the head describes a different chain -
    #: which is what a cut-off tail looks like, and also what an interrupted
    #: append looks like. The report says which of the two the numbers fit.
    HEAD_MISMATCH = "head_mismatch"
    #: The MAC material could not be opened, so nothing was checked. Absence
    #: of a check is never reported as a pass (IMP-215's rule, applied here).
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ChainReport:
    """The result of one verification pass. Facts, then one verdict."""

    verdict: ChainVerdict
    #: Links present in the database. Counted on every verdict, ``UNAVAILABLE``
    #: included: how many links there are and whether any of them could be
    #: checked are two different facts, and merging them loses the first.
    link_count: int
    #: Links the head says there should be, or ``None`` when there is no head.
    head_count: int | None
    #: The first sequence number that failed, when one did.
    first_bad_seq: int | None
    detail: str

    @property
    def is_intact(self) -> bool:
        return self.verdict is ChainVerdict.INTACT


def canonical_timestamp(value: datetime) -> str:
    """One spelling of an instant, on both sides of a database round trip.

    SQLite has no timestamp type. SQLAlchemy's ``DateTime(timezone=True)``
    writes the wall clock and hands it back **naive**, so a MAC taken over
    ``value.isoformat()`` would cover ``"...+00:00"`` at append time and
    ``"..."`` at verification - and every chain would read as broken the first
    time it was verified from disk rather than from memory. That failure would
    have looked exactly like tampering, which is the worst possible thing for
    a tamper-detection mechanism to get wrong.

    A naive value is therefore treated as the UTC it was written as, and an
    aware one is converted, so both sides produce the same string.
    """
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def canonical_line(
    *,
    seq: int,
    recorded_at: datetime,
    event: str,
    subject: str,
    detail: str,
    prev_mac: str,
) -> bytes:
    """The exact bytes a MAC is taken over.

    Keys sorted, no whitespace, UTF-8 - and every field the row stores is in
    here. A field a row keeps but the MAC does not cover is a field an
    attacker may edit freely, which is the quiet way a chain stops meaning
    anything.
    """
    return canonical_json_bytes(
        {
            "detail": detail,
            "event": event,
            "prev_mac": prev_mac,
            "recorded_at": canonical_timestamp(recorded_at),
            "seq": seq,
            "subject": subject,
            "v": 1,
        }
    )


def compute_mac(material: bytes, line: bytes) -> str:
    return hmac.new(material, line, sha256).hexdigest()


def _clean(text: str) -> str:
    """Redact known secrets, sweep control characters, then bound the length.

    In that order. Sweeping first would break an exact-match redaction of a
    value that happens to contain a swept character, which is the one way a
    registered secret could survive this function.
    """
    return safe_display(redact(text))[:MAX_DETAIL_CHARS]


class AuditChain:
    """Appends links and verifies the chain. One instance per process."""

    def __init__(self, engine: Engine, envelope: AuditEnvelope) -> None:
        self._engine = engine
        self._envelope = envelope

    # --- setup -------------------------------------------------------------

    def ensure_ready(self) -> str:
        """Create the MAC material on first use and record its fingerprint.

        Returns the fingerprint. The material never leaves this module's
        callers; the table gets a path, a time and this value, exactly as
        ``secret_metadata`` does for the vault.
        """
        material = self._envelope.ensure_material()
        digest = fingerprint(material)
        now = datetime.now(UTC)

        with Session(self._engine) as session, session.begin():
            row = session.get(AuditChainMetadata, CHAIN_ID)
            if row is None:
                session.add(
                    AuditChainMetadata(
                        id=CHAIN_ID,
                        envelope_relpath=self._envelope.material_relpath(),
                        fingerprint=digest,
                        created_at=now,
                    )
                )
        return digest

    # --- append ------------------------------------------------------------

    def append(
        self,
        session: Session,
        *,
        event: AuditEventName,
        subject: str,
        detail: str = "",
    ) -> AuditEvent:
        """Add one link, inside the caller's transaction.

        Taking a ``Session`` rather than opening one is the whole point: an
        evidence row and the audit line that says it was written have to land
        together or not at all. A caller that wants a standalone link uses
        :meth:`record`.

        The head file is replaced *before* the caller commits, so a failure to
        write it aborts the append rather than leaving a link the head does
        not know about.
        """
        material = self._envelope.load_material()
        safe_detail = _clean(detail)
        assert_no_forbidden_claim(safe_detail, where="audit detail")

        previous = session.scalars(
            select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1)
        ).first()
        seq = 1 if previous is None else previous.seq + 1
        prev_mac = GENESIS_MAC if previous is None else previous.mac
        recorded_at = datetime.now(UTC)

        mac = compute_mac(
            material,
            canonical_line(
                seq=seq,
                recorded_at=recorded_at,
                event=event.value,
                subject=subject[:128],
                detail=safe_detail,
                prev_mac=prev_mac,
            ),
        )

        row = AuditEvent(
            id=uuid.uuid4().hex,
            seq=seq,
            recorded_at=recorded_at,
            event=event.value,
            subject=subject[:128],
            detail=safe_detail,
            prev_mac=prev_mac,
            mac=mac,
        )
        session.add(row)
        # Flush before the head is written so a uniqueness violation on
        # ``seq`` surfaces here, while the head still describes the old chain.
        session.flush()

        self._envelope.write_head(
            ChainHead(count=seq, last_mac=mac, updated_at=recorded_at.isoformat())
        )
        return row

    def record(
        self, *, event: AuditEventName, subject: str, detail: str = ""
    ) -> AuditEvent:
        """Append one link in a transaction of its own."""
        with Session(self._engine) as session, session.begin():
            return self.append(session, event=event, subject=subject, detail=detail)

    # --- verification ------------------------------------------------------

    def verify(self) -> ChainReport:
        """Recompute every link, then compare the chain against its head."""
        try:
            material = self._envelope.load_material()
        except AuditEnvelopeError as exc:
            # The rows are counted even though none of them could be checked.
            # Reporting ``link_count=0`` beside "could not verify" read as an
            # empty chain to anyone who did not also read the verdict, which
            # is the one reading a chain of five links must never produce.
            return ChainReport(
                verdict=ChainVerdict.UNAVAILABLE,
                link_count=self.count(),
                head_count=None,
                first_bad_seq=None,
                detail=f"Zincir dogrulanamadi: {exc}",
            )

        with Session(self._engine) as session:
            rows = list(session.scalars(select(AuditEvent).order_by(AuditEvent.seq)))

        expected_prev = GENESIS_MAC
        for index, row in enumerate(rows, start=1):
            if row.seq != index:
                return ChainReport(
                    verdict=ChainVerdict.BROKEN_LINK,
                    link_count=len(rows),
                    head_count=None,
                    first_bad_seq=row.seq,
                    detail=(
                        f"Sira numarasi {index} beklenirken {row.seq} bulundu: "
                        "aradan bir satir silinmis veya sira degistirilmis."
                    ),
                )
            if row.prev_mac != expected_prev:
                return ChainReport(
                    verdict=ChainVerdict.BROKEN_LINK,
                    link_count=len(rows),
                    head_count=None,
                    first_bad_seq=row.seq,
                    detail=(
                        f"{row.seq}. satirin onceki MAC degeri zinciri "
                        "izlemiyor: satirlar yeniden siralanmis olabilir."
                    ),
                )
            recomputed = compute_mac(
                material,
                canonical_line(
                    seq=row.seq,
                    recorded_at=row.recorded_at,
                    event=row.event,
                    subject=row.subject,
                    detail=row.detail,
                    prev_mac=row.prev_mac,
                ),
            )
            if not hmac.compare_digest(recomputed, row.mac):
                return ChainReport(
                    verdict=ChainVerdict.BROKEN_LINK,
                    link_count=len(rows),
                    head_count=None,
                    first_bad_seq=row.seq,
                    detail=(
                        f"{row.seq}. satirin MAC degeri yeniden hesaplanan "
                        "degerle uyusmuyor: satirdaki bir alan degistirilmis."
                    ),
                )
            expected_prev = row.mac

        return self._compare_head(rows, expected_prev)

    def _compare_head(self, rows: list[AuditEvent], last_mac: str) -> ChainReport:
        """Every link recomputed; now ask the head whether any are missing."""
        try:
            head = self._envelope.read_head()
        except AuditEnvelopeError as exc:
            return ChainReport(
                verdict=ChainVerdict.HEAD_MISMATCH,
                link_count=len(rows),
                head_count=None,
                first_bad_seq=None,
                detail=f"Zincir basi okunamadi: {exc}",
            )

        if head is None:
            if not rows:
                return ChainReport(
                    verdict=ChainVerdict.EMPTY,
                    link_count=0,
                    head_count=None,
                    first_bad_seq=None,
                    detail="Henuz audit satiri yok.",
                )
            return ChainReport(
                verdict=ChainVerdict.HEAD_MISMATCH,
                link_count=len(rows),
                head_count=None,
                first_bad_seq=None,
                detail=(
                    "Zincir basi yok. Satirlar kendi icinde tutarli, fakat "
                    "sonundan satir kesilip kesilmedigi bas olmadan "
                    "soylenemez."
                ),
            )

        if head.count == len(rows) and hmac.compare_digest(head.last_mac, last_mac):
            return ChainReport(
                verdict=ChainVerdict.INTACT,
                link_count=len(rows),
                head_count=head.count,
                first_bad_seq=None,
                detail=(
                    "Zincir kendi icinde tutarli ve bas ile ayni sayida satiri "
                    "gosteriyor. Bu, cevrimdisi degisiklige karsi tespit "
                    "edicidir; ayni Windows kullanicisi olarak calisan bir "
                    "saldirgana karsi bir guvence degildir."
                ),
            )

        if head.count == len(rows):
            return ChainReport(
                verdict=ChainVerdict.HEAD_MISMATCH,
                link_count=len(rows),
                head_count=head.count,
                first_bad_seq=None,
                detail=(
                    "Satir sayisi bas ile ayni, fakat son MAC farkli: zincirin "
                    "sonundaki satir baska bir satirla degistirilmis olabilir."
                ),
            )

        if head.count > len(rows):
            return ChainReport(
                verdict=ChainVerdict.HEAD_MISMATCH,
                link_count=len(rows),
                head_count=head.count,
                first_bad_seq=None,
                detail=(
                    f"Bas {head.count} satir gosteriyor, veritabaninda "
                    f"{len(rows)} satir var: zincirin sonu kesilmis olabilir. "
                    "Yarida kalan bir yazma da ayni sayilari uretir."
                ),
            )

        return ChainReport(
            verdict=ChainVerdict.HEAD_MISMATCH,
            link_count=len(rows),
            head_count=head.count,
            first_bad_seq=None,
            detail=(
                f"Bas {head.count} satir gosteriyor, veritabaninda "
                f"{len(rows)} satir var: bas geride kalmis. Yarida kalan bir "
                "yazma bu sayilari uretir."
            ),
        )

    # --- reads -------------------------------------------------------------

    def count(self) -> int:
        with Session(self._engine) as session:
            return int(session.scalar(select(func.count(AuditEvent.id))) or 0)


__all__ = [
    "GENESIS_MAC",
    "MAX_DETAIL_CHARS",
    "AuditChain",
    "AuditEventName",
    "ChainReport",
    "ChainVerdict",
    "canonical_line",
    "canonical_timestamp",
    "compute_mac",
]
