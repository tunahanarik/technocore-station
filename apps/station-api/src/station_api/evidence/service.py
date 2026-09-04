"""The evidence service: record a send, capture a line, export, verify.

Four operations, and the boundaries between them are the interesting part.

``record`` runs immediately after a send, in one transaction with the audit
link that says it happened. It never raises into the composer: a send that
was made is a send that was made, and an evidence failure must be reported
*beside* the send result rather than replacing it. What it does refuse is to
write bytes that carry a secret shape (``secret_scan``); that refusal is
itself recorded, without the offending value.

``capture`` runs **only when a person asks** (ADR-0003 4). It is a read, it
may be repeated, and it can be attempted for an ``accepted`` send and for an
``outcome_unknown`` one alike. What it can never do is change an
``outcome_unknown`` into ``not_sent``: the ring forgets, so an absent line is
not an absent message. Nothing here offers to send anything again.

``export`` needs an :class:`~station_api.evidence.export.ExportConsent`, which
cannot be constructed without an explicit acknowledgement.

``verify`` recomputes the audit chain and compares it to its separately
protected head.

Retention: none. Evidence rows and audit links are never pruned (ADR-0003 7).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from station_api.db.models import EvidenceRecord
from station_api.evidence.audit import (
    AuditChain,
    AuditEventName,
    ChainReport,
)
from station_api.evidence.export import (
    EXPORT_MEDIA_TYPE,
    EXPORT_SUFFIX,
    ExportConsent,
    ExportFormat,
    ExportRefusedError,
    build_export,
)
from station_api.evidence.language import (
    ForbiddenClaimError,
    neutralise_forbidden_claims,
)
from station_api.evidence.records import EvidenceView, encode_window, to_view
from station_api.evidence.secret_scan import SecretPatternRefusedError, require_no_secrets
from station_api.evidence.states import CAPTURE_DETAIL, CaptureState
from station_api.evidence.stream import LineMatch
from station_api.technocore.evidence_client import (
    EvidenceClient,
    EvidenceFetchError,
    ExportRead,
)
from station_api.technocore.projection import safe_display

#: Most records one listing or export returns. Evidence is never pruned, so
#: the bound belongs on the read rather than on the store.
MAX_RECORDS = 500


class EvidenceError(Exception):
    """An evidence operation was refused. The message is safe to show."""


@dataclass(frozen=True, slots=True)
class RecordOutcome:
    """What happened when a send was archived.

    Deliberately not a bare ``bool``. "Evidence was not written" and "evidence
    was refused because the bytes carry a secret shape" are different facts,
    and the composer shows the second one to the user.
    """

    recorded: bool
    evidence_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class CaptureOutcome:
    """One capture attempt, as one of the six states and nothing more."""

    state: CaptureState
    evidence_id: str
    detail: str
    #: The epoch **this read** published, or "" when it published none. The
    #: record's frozen baseline is a different value answering a different
    #: question, and lives on the row (``room_generation``).
    generation: str = ""
    line_offset: int | None = None
    line_length: int | None = None
    stream_sha256: str = ""
    scanned_bytes: int = 0
    truncated: bool = False

    @property
    def is_server_observation(self) -> bool:
        return self.state.is_server_observation


@dataclass(frozen=True, slots=True)
class ExportResult:
    """A finished export: bytes, media type and the download name's suffix."""

    payload: bytes
    media_type: str
    suffix: str
    record_count: int
    #: When the file was asked for. Carried **beside** the bytes rather than
    #: inside them, which is what makes ``payload`` byte-identical between two
    #: exports of the same archive (:mod:`station_api.evidence.export`).
    exported_at: datetime


class EvidenceService:
    """Owns evidence rows and the audit chain. One instance per process."""

    def __init__(
        self,
        *,
        engine: Engine,
        chain: AuditChain,
        client: EvidenceClient | None = None,
    ) -> None:
        self._engine = engine
        self._chain = chain
        self._client = client if client is not None else EvidenceClient()

    def start(self) -> str:
        """Create the chain's MAC material on first use, and say so.

        The genesis link is written by the chain itself, so a chain that has
        never recorded anything is still distinguishable from one whose first
        links were removed.
        """
        digest = self._chain.ensure_ready()
        if self._chain.count() == 0:
            self._chain.record(
                event=AuditEventName.CHAIN_STARTED,
                subject=digest[:16],
                detail="Audit zinciri baslatildi.",
            )
        return digest

    # --- record ------------------------------------------------------------

    def record_send(
        self,
        *,
        reservation_id: str,
        did: str,
        room: str,
        nonce: str,
        canonical: str,
        signature: str,
        signature_verified: bool,
        request_body: bytes,
        response_body: bytes,
        http_status: int,
        write_outcome: str,
    ) -> RecordOutcome:
        """Archive one send and its audit link, in one transaction.

        The scan runs **before** anything is written. A hit refuses the whole
        row rather than redacting part of it: the request bytes are evidence
        precisely because they are unmodified, and a redacted field would be
        a field that proves nothing while looking as though it does.
        """
        try:
            require_no_secrets(
                {
                    "canonical": canonical,
                    "request_body": request_body,
                    "response_body": response_body,
                },
                # The only high-entropy values a signed body legitimately
                # carries, named by the caller that produced them. A shape
                # allow-list could not do this job: at 86 base64url characters
                # a padded seed and a real signature are the same shape.
                public_values=frozenset({did, signature, nonce}),
            )
        except SecretPatternRefusedError as exc:
            # Recorded without the offending value: the refusal is the event,
            # and re-logging what triggered it would be the leak it prevented.
            self._chain.record(
                event=AuditEventName.EVIDENCE_WRITE_REFUSED,
                subject=reservation_id,
                detail=f"Secret sekil taramasi ({exc.rule.value}) kaydi reddetti.",
            )
            return RecordOutcome(recorded=False, evidence_id="", detail=str(exc))

        evidence_id = uuid.uuid4().hex
        now = datetime.now(UTC)

        with Session(self._engine) as session, session.begin():
            session.add(
                EvidenceRecord(
                    id=evidence_id,
                    reservation_id=reservation_id,
                    did=did,
                    room=room,
                    nonce=nonce,
                    canonical=canonical,
                    canonical_sha256=hashlib.sha256(
                        canonical.encode("utf-8")
                    ).hexdigest(),
                    signature=signature,
                    signature_verified=signature_verified,
                    request_body=request_body,
                    request_sha256=hashlib.sha256(request_body).hexdigest(),
                    response_body=response_body,
                    response_sha256=hashlib.sha256(response_body).hexdigest(),
                    http_status=http_status,
                    write_outcome=write_outcome,
                    capture_state="",
                    capture_detail="",
                    captured_at=None,
                    export_url="",
                    # No generation is known at send time: Station does not
                    # read the room's export in order to publish to it, and
                    # writing a value here that no read produced would be an
                    # invention. The baseline is set by the first capture.
                    room_generation="",
                    capture_generation="",
                    generation_changed=False,
                    captured_line=None,
                    captured_line_offset=None,
                    captured_line_length=None,
                    captured_window="",
                    stream_sha256="",
                    stream_bytes=0,
                    stream_truncated=False,
                    stream_line_count=0,
                    unreadable_lines=0,
                    recorded_at=now,
                    # Level 4. Written as NULL, on purpose, every time.
                    external_anchor=None,
                )
            )
            self._chain.append(
                session,
                event=AuditEventName.EVIDENCE_RECORDED,
                subject=evidence_id,
                detail=f"{room} / {write_outcome} / HTTP {http_status}",
            )

        return RecordOutcome(
            recorded=True,
            evidence_id=evidence_id,
            detail="Kanit kaydi yazildi.",
        )

    # --- capture -----------------------------------------------------------

    def capture(self, *, evidence_id: str, markers: frozenset[str]) -> CaptureOutcome:
        """Read the room's export and look for our own line. On request only.

        Never automatic, never on a timer, and never a prelude to sending
        anything again.
        """
        view = self.get(evidence_id)
        match = LineMatch(did=view.did, nonce=view.nonce, signature=view.signature)

        try:
            read = self._client.export(view.room, markers=markers, match=match)
        except EvidenceFetchError as exc:
            return self._settle(
                view,
                CaptureState.FETCH_FAILED,
                detail=str(exc),
                read=None,
            )

        state = _classify(
            read,
            expected_generation=view.room_generation,
            generation_already_changed=view.generation_changed,
        )
        return self._settle(view, state, detail="", read=read)

    def _settle(
        self,
        view: EvidenceView,
        state: CaptureState,
        *,
        detail: str,
        read: ExportRead | None,
    ) -> CaptureOutcome:
        """Persist one capture attempt and its audit link, together."""
        # ``detail`` and ``failure_detail`` can both carry an excerpt from a
        # remote body. It is neutralised at the door it came through
        # (``evidence_client._error_excerpt``); it is neutralised again here
        # because this is where it becomes part of a sentence in *our* voice,
        # and the guarantee that matters is about this string, not about the
        # path it took to get here.
        sentence = safe_display(detail) if detail else CAPTURE_DETAIL[state]
        if read is not None and read.failure_detail:
            sentence = f"{CAPTURE_DETAIL[state]} {read.failure_detail}"
        sentence = neutralise_forbidden_claims(sentence)
        now = datetime.now(UTC)

        with Session(self._engine) as session, session.begin():
            row = session.get(EvidenceRecord, view.id)
            if row is None:  # pragma: no cover - read one line earlier
                raise EvidenceError("Kanit kaydi bulunamadi.")

            row.capture_state = state.value
            row.capture_detail = sentence
            row.captured_at = now
            if state is CaptureState.GENERATION_CHANGED:
                # Sticky. A room that has been seen under two epochs stays
                # incomparable; the next read must not report the weaker,
                # more alarming ``line_not_found`` about a different room.
                row.generation_changed = True
            if read is not None:
                row.export_url = read.url
                # The baseline is written **once**. A generation is only
                # recorded when one was actually published, and overwriting a
                # known one - with "" or with a newer epoch - erases the value
                # the next comparison needs.
                if read.generation and not row.room_generation:
                    row.room_generation = read.generation
                scan = read.scan
                row.stream_sha256 = scan.stream_sha256
                row.stream_bytes = scan.scanned_bytes
                row.stream_truncated = scan.truncated
                row.stream_line_count = scan.line_count
                row.unreadable_lines = scan.unreadable_lines
                # Only a real observation replaces the stored line, and it is
                # stamped with the epoch it was read under. A line found while
                # the room reports a different generation is *not* stored: the
                # state says the two sides are incomparable, and keeping bytes
                # from that read would put them beside a baseline they do not
                # belong to.
                if state is CaptureState.LINE_CAPTURED and scan.line is not None:
                    row.captured_line = scan.line
                    row.captured_line_offset = scan.line_offset
                    row.captured_line_length = scan.line_length
                    row.capture_generation = read.generation
                    row.captured_window = encode_window(
                        scan.window_before + scan.window_after
                    )

            self._chain.append(
                session,
                event=AuditEventName.CAPTURE_ATTEMPTED,
                subject=view.id,
                detail=f"{view.room} / {state.value}",
            )

        final_scan = read.scan if read is not None else None
        return CaptureOutcome(
            state=state,
            evidence_id=view.id,
            detail=sentence,
            generation="" if read is None else read.generation,
            line_offset=None if final_scan is None else final_scan.line_offset,
            line_length=(
                None
                if final_scan is None or final_scan.line is None
                else final_scan.line_length
            ),
            stream_sha256="" if final_scan is None else final_scan.stream_sha256,
            scanned_bytes=0 if final_scan is None else final_scan.scanned_bytes,
            truncated=False if final_scan is None else final_scan.truncated,
        )

    # --- reads -------------------------------------------------------------

    def get(self, evidence_id: str) -> EvidenceView:
        with Session(self._engine) as session:
            row = session.get(EvidenceRecord, evidence_id)
            if row is None:
                raise EvidenceError("Kanit kaydi bulunamadi.")
            return to_view(row)

    def list_records(self, *, limit: int = MAX_RECORDS) -> tuple[EvidenceView, ...]:
        """Newest first, bounded. Ordered by ``(recorded_at, id)``.

        The id is in the ordering so two records written in the same clock
        tick still come back in a stable order - an export whose record order
        depended on the query planner would not be deterministic.
        """
        bounded = max(1, min(limit, MAX_RECORDS))
        with Session(self._engine) as session:
            rows = session.scalars(
                select(EvidenceRecord)
                .order_by(EvidenceRecord.recorded_at.desc(), EvidenceRecord.id.desc())
                .limit(bounded)
            ).all()
            return tuple(to_view(row) for row in rows)

    def verify_chain(self) -> ChainReport:
        return self._chain.verify()

    # --- export ------------------------------------------------------------

    def export(
        self,
        *,
        export_format: ExportFormat,
        consent: ExportConsent,
        records: Sequence[EvidenceView] | None = None,
    ) -> ExportResult:
        """Build the file. Refuses without consent, and records that it ran.

        The export is an audit event in its own right: a copy of the archive
        leaving the machine is exactly the kind of thing the archive should
        remember.
        """
        selected = self.list_records() if records is None else tuple(records)
        try:
            payload = build_export(
                selected, export_format=export_format, consent=consent
            )
        except (ExportRefusedError, ForbiddenClaimError) as exc:
            # ``ForbiddenClaimError`` is a ``ValueError``, and a ValueError that
            # escapes here reaches the route as an unhandled exception and the
            # user as a 500. It cannot be raised by anything a user or a server
            # supplies any more - it means one of *our* fixed sentences carries
            # a forbidden claim - but a bug in our own wording is still a
            # refusal to state plainly, not a crash to guess at.
            raise EvidenceError(str(exc)) from exc

        self._chain.record(
            event=AuditEventName.EVIDENCE_EXPORTED,
            subject=export_format,
            detail=f"{len(selected)} kayit disa aktarildi.",
        )
        return ExportResult(
            payload=payload,
            media_type=EXPORT_MEDIA_TYPE[export_format],
            suffix=EXPORT_SUFFIX[export_format],
            record_count=len(selected),
            exported_at=consent.requested_at,
        )


def _classify(
    read: ExportRead,
    *,
    expected_generation: str,
    generation_already_changed: bool = False,
) -> CaptureState:
    """Turn one completed read into exactly one of the six states.

    Precedence, and every step of it is a decision:

    1. a failed read establishes nothing, so it wins outright;
    2. a **changed generation** wins next, even over a found line: the two
       sides are from different epochs of the room and are not comparable,
       which is a stronger statement than "found";
    3. a room already **known** to have changed epoch stays incomparable, even
       when this read published no generation at all. Without this the verdict
       was a one-off: the third capture of a moved room fell through to
       ``line_not_found``, which reads as "your message is not there" and is
       said about a room that is not the same room;
    4. a found line is a server observation;
    5. a truncated scan beats "not found", because a partial scan did not
       look everywhere;
    6. unreadable lines beat "not found" for the same reason;
    7. only then is absence reported - and absence still proves nothing.
    """
    if not read.ok:
        return CaptureState.FETCH_FAILED
    if expected_generation and read.generation and read.generation != expected_generation:
        return CaptureState.GENERATION_CHANGED
    if generation_already_changed:
        return CaptureState.GENERATION_CHANGED
    if read.scan.found:
        return CaptureState.LINE_CAPTURED
    if read.scan.truncated:
        return CaptureState.STREAM_TRUNCATED
    if read.scan.unreadable_lines:
        return CaptureState.PARSE_PROBLEM
    return CaptureState.LINE_NOT_FOUND


__all__ = [
    "MAX_RECORDS",
    "CaptureOutcome",
    "EvidenceError",
    "EvidenceService",
    "ExportResult",
    "RecordOutcome",
]
