"""ORM models.

Stage 1 defines infrastructure tables only:

``schema_migrations``  the Alembic version ledger (created and owned by
                       Alembic, renamed from its default; not modelled here)
``app_metadata``       small key/value facts about this installation

There is no ``Identity``, ``SecretMetadata`` or ``Evidence`` table yet, and by
construction no column anywhere holds a seed or private key (SI-43).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Alembic version table name. Kept as ``schema_migrations`` to match the
#: project brief rather than Alembic's ``alembic_version`` default (IMP-102).
VERSION_TABLE_NAME = "schema_migrations"


class Base(DeclarativeBase):
    pass


class AppMetadata(Base):
    """Key/value facts about this installation. Never holds a secret."""

    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AppMetadata(key={self.key!r})"


class ManifestCheck(Base):
    """One user-initiated read-only check of the official sources.

    Evidence, not authority. The write gate reads its verdict from the
    in-process service, never from this table: a row here proves a check once
    ran, and a check that ran an hour ago says nothing about the protocol
    right now. Reading a stored boolean to open an outbound door is exactly
    the mistake this separation exists to prevent.
    """

    __tablename__ = "manifest_check"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: One of the DriftState values: current, drifted or unavailable.
    #: ``never_checked`` is a process state and is never persisted.
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Newline-separated, already swept and length-bounded by the projection.
    reasons: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ManifestCheck(id={self.id!r}, state={self.state!r})"


class OfficialSourceSnapshot(Base):
    """What one official document looked like during one check.

    Only allow-listed response headers are kept. An arbitrary header store
    would eventually hold a ``Set-Cookie`` or a tracking value that nothing
    here needs, so the three headers that carry cache identity are named
    explicitly and everything else is dropped at the client boundary.

    No column holds a seed, a private key, a passphrase or a vault path; this
    table describes public documents fetched from a public origin.
    """

    __tablename__ = "official_source_snapshot"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    check_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("manifest_check.id", ondelete="CASCADE"), nullable=False
    )
    #: The registry identifier, not a caller-supplied string.
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The fixed official URL this source resolves to.
    url: Mapped[str] = mapped_column(Text, nullable=False)
    authority: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: 0 when the request never produced a status (DNS, TLS, timeout).
    http_status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    etag: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    last_modified: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    #: SHA-256 over the exact response bytes. Empty when nothing was received.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: A bounded, control-character-swept excerpt. Kept for human review and
    #: never returned over HTTP.
    snapshot_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: ok | fetch_error | parse_error
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"OfficialSourceSnapshot(source_id={self.source_id!r}, "
            f"outcome={self.outcome!r})"
        )


class IdentityStatus(StrEnum):
    """Lifecycle of the single active identity."""

    CREATING = "creating"
    RECOVERY_PENDING = "recovery_pending"
    READY = "ready"
    REVOKED = "revoked"


#: Sentinel written into ``Identity.active_slot`` while an identity is live.
#: The column is UNIQUE and nullable, and SQLite does not treat NULLs as equal,
#: so this enforces "at most one non-revoked identity" in the database itself
#: rather than only in the service layer.
ACTIVE_SLOT = 1


class Identity(Base):
    """The agent identity. Public material only.

    There is no seed and no private key here, in any column, ever. The secret
    lives exclusively in the DPAPI vault file (INV-01).
    """

    __tablename__ = "identity"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    did: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Identity(did={self.did!r}, status={self.status!r})"


class SecretMetadata(Base):
    """Facts *about* the stored secret. Never the secret itself.

    ``vault_relpath`` is stored relative to the application data directory so
    the absolute path is not baked into the database. It is never returned by
    any API response model (SI-36, and the Stage 2 allow-list).
    """

    __tablename__ = "secret_metadata"

    identity_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("identity.id", ondelete="CASCADE"), primary_key=True
    )
    vault_relpath: Mapped[str] = mapped_column(Text, nullable=False)
    protection: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recovery_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SecretMetadata(identity_id={self.identity_id!r})"


class NonceState(StrEnum):
    """What happened to one reserved nonce.

    Three states, and none of them ever returns the number to circulation.
    ``CANCELLED`` is not "unused": the protocol counter is strictly
    increasing per ``(did, room)``, so a number handed out and then dropped
    is still burnt. Re-issuing it would mean signing two different payloads
    under one nonce, which is precisely the replay shape the counter exists
    to prevent.
    """

    #: Allocated, not yet committed to a request.
    RESERVED = "reserved"
    #: Committed: the request either went out or was about to.
    SPENT = "spent"
    #: Abandoned before any request left the process.
    CANCELLED = "cancelled"


class WriteOutcomeValue(StrEnum):
    """How a committed nonce's request ended (ADR-0002 3)."""

    #: Spent, and the request had not returned when the row was written.
    IN_FLIGHT = "in_flight"
    #: 2xx.
    ACCEPTED = "accepted"
    #: A response that proves nothing was written: 400, 403, 413, 422.
    REFUSED = "refused"
    #: Timeout, transport failure, malformed response, 429 or 5xx. The
    #: server may or may not have written. Never presented as either.
    OUTCOME_UNKNOWN = "outcome_unknown"
    #: No request was attempted (the gate shut, or the approval was stale).
    NOT_SENT = "not_sent"


class MessageNonceReservation(Base):
    """One nonce handed out for one ``(did, room)`` pair.

    This table *is* the monotonic counter. There is no separate "last value"
    row to fall out of step with the reservations: the next nonce is derived
    from ``MAX(nonce_value)`` over every row for the pair, whatever state
    those rows are in, so a crash between reservation and send cannot make a
    number available again (docs/protocol-contract.md 5).

    ``nonce`` and ``nonce_value`` are deliberately both stored. The signature
    covers the canonical string, which carries the nonce as **text**; the
    server compares it as an integer. Keeping the exact signed characters
    beside the number they represent means neither side of that mismatch has
    to be reconstructed later, and a leading zero could never be introduced
    by a round trip through ``int``.

    No column here holds key material: a DID is public, a room name is
    public, and a nonce is public.
    """

    __tablename__ = "message_nonce_reservation"
    __table_args__ = (
        # The database, not the service layer, is what makes a lost race
        # impossible. Two processes sharing this file cannot both commit the
        # same number for the same pair.
        UniqueConstraint("did", "room", "nonce_value", name="uq_nonce_per_did_room"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    #: The signing identity's public did:key.
    did: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Target room name, already validated against the official name pattern.
    room: Mapped[str] = mapped_column(String(48), nullable=False)
    #: The exact characters that go into the canonical string. Never parsed
    #: back out of ``nonce_value``.
    nonce: Mapped[str] = mapped_column(String(19), nullable=False)
    #: The same value as an integer, for the monotonic comparison and the
    #: uniqueness constraint.
    nonce_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: One of the NonceState values.
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    #: One of the WriteOutcomeValue values; empty while still reserved.
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: A short, swept explanation. Never a response body, never a signature.
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"MessageNonceReservation(room={self.room!r}, nonce={self.nonce!r}, "
            f"state={self.state!r}, outcome={self.outcome!r})"
        )


class EvidenceRecord(Base):
    """One send, and everything that is honestly known about it.

    The four trust levels are kept in four separate groups of columns and are
    never summed into one boolean (charter 15, ADR-0003). Level 4 is a single
    nullable column that this release always leaves ``NULL``: an empty level
    is written as empty, not as a plausible guess.

    Not pruned, ever
    ----------------
    ``snapshot.py`` keeps the newest fifty check runs and deletes the rest,
    which is right for a monitoring log and wrong here twice over: an evidence
    record is the user's own archive of something they published, and the
    audit chain that covers these rows breaks if a row in the middle
    disappears (ADR-0003 7). Growth is one row per send, which is a bound set
    by human hands on a button. Deletion happens only when a user asks, and
    that deletion is itself an audit event.

    No column holds a seed, a private key, a passphrase or a vault path. The
    DID, the room, the nonce and the signature are public protocol values; the
    request and response bytes are scanned for secret shapes before they are
    written, and a hit **refuses the write** rather than redacting it
    (``secret_scan.py``): redacting the raw bytes would destroy the one
    property that makes them evidence.
    """

    __tablename__ = "evidence_record"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    #: The nonce reservation this send spent. No ``ON DELETE CASCADE``: a
    #: reservation row is a ledger entry, and a ledger entry that silently
    #: takes the evidence with it is not a ledger. Removing evidence is an
    #: explicit user action, never a side effect of touching something else.
    reservation_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("message_nonce_reservation.id"),
        nullable=False,
        unique=True,
    )

    # --- level 1: signature proof -----------------------------------------
    did: Mapped[str] = mapped_column(String(128), nullable=False)
    room: Mapped[str] = mapped_column(String(48), nullable=False)
    nonce: Mapped[str] = mapped_column(String(19), nullable=False)
    #: The exact canonical string the signature was taken over.
    canonical: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Station verified its own signature against its own canonical bytes
    #: before sending. That is level 1 and nothing beyond it.
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # --- level 2: server observation --------------------------------------
    #: The approved request bytes, exactly as they went on the wire. Stored so
    #: the record can be re-read later; the charter is explicit that this does
    #: **not** license the sentence "the signature covers this JSON"
    #: (protocol-contract.md 2.4) - it covers the canonical string above.
    request_body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The response, already bounded by the write client's streaming cap.
    response_body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    response_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: One of the WriteOutcomeValue values.
    write_outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    #: One of the CaptureState values; empty until a capture is attempted.
    capture_state: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    capture_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The fixed export URL the capture read. Built from the closed registry.
    export_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: The room's conversation epoch as first observed, kept as digits. Set
    #: once and **never overwritten**: it is the baseline every later capture
    #: is compared against, and overwriting it with the epoch that differed
    #: made ``generation_changed`` a one-off - the third capture compared the
    #: new room against itself and reported ``line_not_found``, which reads as
    #: "your message is not there" about a room that is not the same room.
    room_generation: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    #: The epoch the currently stored ``captured_line`` was read under. Equal
    #: to ``room_generation`` in the ordinary case; it exists so a line and
    #: the generation beside it can never belong to different epochs.
    capture_generation: Mapped[str] = mapped_column(
        String(32), nullable=False, default=""
    )
    #: Sticky. Once a room has been seen under a different epoch the two sides
    #: are not comparable, and a later read must not walk that back into a
    #: weaker, more alarming state.
    generation_changed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    #: Our own record's raw exported bytes, without the line terminator.
    captured_line: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    captured_line_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_line_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: The bounded neighbourhood, as canonical JSON of base64url strings.
    captured_window: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: SHA-256 over every byte of the export that was read.
    stream_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    stream_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stream_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    stream_line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unreadable_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- level 3: local receipt time --------------------------------------
    #: This machine's clock. Not a trusted timestamp, and never presented as
    #: one (the phrase is on the forbidden list).
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # --- level 4: external anchoring --------------------------------------
    #: Always ``NULL`` in this release. The column exists so the export can
    #: state the level as absent rather than omit it, which is the difference
    #: between "there is no anchor" and "nobody looked".
    external_anchor: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"EvidenceRecord(room={self.room!r}, nonce={self.nonce!r}, "
            f"capture_state={self.capture_state!r})"
        )


class AuditEvent(Base):
    """One link in the append-only HMAC chain.

    ``prev_mac -> mac`` over a canonical line (charter 15.3). What that buys
    is stated once and not embellished: **an offline change made without the
    chain's MAC material is detectable**. It is not tamper-proof, it is not
    a trusted clock, and it is not proof to a third party - an attacker
    running as this Windows user can recompute both the chain and its head
    (ADR-0003 5, SECURITY.md 7).

    Never pruned. Deleting a row from the middle is precisely what the chain
    exists to make visible, so a retention policy here would be a policy of
    breaking our own evidence on a schedule.
    """

    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    #: Strictly increasing from 1, with no gaps. Both properties are checked
    #: on verification: a gap is a removed row, and an out-of-order pair is a
    #: reordered one.
    seq: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    #: What the event is about: an evidence id, a reservation id, a room.
    subject: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    #: A short, swept, already-redacted sentence. Never a response body.
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prev_mac: Mapped[str] = mapped_column(String(64), nullable=False)
    mac: Mapped[str] = mapped_column(String(64), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AuditEvent(seq={self.seq!r}, event={self.event!r})"


class AuditChainMetadata(Base):
    """Facts *about* the chain's MAC material. Never the material itself.

    The same shape as :class:`SecretMetadata`, for the same reason: the file
    path relative to the application data directory, when it was created, and
    a fingerprint derived from the material - which is an HMAC of a fixed
    public label, so it identifies the material without revealing it.

    Nothing here is ever returned by an API response model.
    """

    __tablename__ = "audit_chain_metadata"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    envelope_relpath: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AuditChainMetadata(id={self.id!r})"


class TaskRecord(Base):
    """One task, bound to the module it belongs to and the content it is for.

    ``module_id`` is a value from the compile-time registry
    (:mod:`station_api.modules.registry`), not a caller-supplied string, and
    ``source_id`` likewise comes from :class:`~station_api.tasks.sources.TaskSourceId`.
    ``source_version_id`` is the domain-separated digest over the two of them
    plus the content hash: when the content changes the identity changes, so
    evidence recorded against the old bytes stops matching (ADR-0004 5).

    No column holds a seed, a private key, a passphrase or a vault path. A
    module id, a source id, a digest and a title are all public values.
    """

    __tablename__ = "task_record"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    #: A ``ModuleId`` value. The registry is fixed at build time.
    module_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: A ``TaskSourceId`` value.
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: SHA-256 over the exact content bytes this task was opened for.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The domain-separated binding of ``source_id`` and ``content_sha256``.
    source_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: One of the nine ``TaskState`` values. Only six are producible in this
    #: release, and the service refuses the other three (ADR-0004 3).
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TaskRecord(id={self.id!r}, state={self.state!r})"


class TaskEvidenceOutcome(Base):
    """The four fields of one task, in four separate groups of columns.

    Deliberately **not** four rows and deliberately not one boolean. Task
    success, test result, user acceptance and public sharing answer four
    different questions (ADR-0004 4), and the ``EvidenceRecord`` precedent is
    followed exactly: a group per field, each with its own reference, its own
    ``verified`` verdict, its own content version and its own timestamp.

    ``public_share_*`` is the level-4 column of this table: present so the
    absence can be *stated* rather than inferred from a missing key, and never
    written in this release. External sharing is Package H3's subject.

    ``verified`` is the load-bearing column. A reference with ``verified``
    false is a record that exists and was not checked, and the gate reports it
    as blocked - the existence of a result is not the success of one.
    """

    __tablename__ = "task_evidence_outcome"

    task_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("task_record.id", ondelete="CASCADE"), primary_key=True
    )

    # --- field 1: the task's own output -----------------------------------
    task_outcome_ref_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    task_outcome_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    task_outcome_version_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    task_outcome_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_outcome_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- field 2: the check that ran over it -------------------------------
    test_result_ref_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    test_result_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    test_result_version_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    test_result_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    test_result_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- field 3: the person who accepted it -------------------------------
    user_acceptance_ref_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    user_acceptance_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    user_acceptance_version_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    user_acceptance_detail: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    user_acceptance_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- field 4: external sharing (always empty in this release) ----------
    public_share_ref_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    public_share_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    public_share_version_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    public_share_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    public_share_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TaskEvidenceOutcome(task_id={self.task_id!r})"


class TaskStateTransition(Base):
    """One state change, appended. The state machine's own ledger.

    Kept because a status column answers "where is this now" and nothing else.
    A refused transition is not recorded here - nothing happened - but every
    accepted one is, with the sentence that was shown at the time.
    """

    __tablename__ = "task_state_transition"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("task_record.id", ondelete="CASCADE"), nullable=False
    )
    #: Empty for the row that records a task being opened.
    from_state: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"TaskStateTransition(task_id={self.task_id!r}, "
            f"to_state={self.to_state!r})"
        )


class RecoveryRecord(Base):
    """A ``.tcrec`` that was exported, and whether it has been restore-tested.

    Holds the file's SHA-256 and its KDF parameters. It never holds the
    ciphertext and never holds the recovery passphrase.
    """

    __tablename__ = "recovery_record"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    identity_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("identity.id", ondelete="CASCADE"), nullable=False
    )
    file_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    kdf: Mapped[str] = mapped_column(String(32), nullable=False)
    kdf_time_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    kdf_memory_kib: Mapped[int] = mapped_column(Integer, nullable=False)
    kdf_parallelism: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"RecoveryRecord(id={self.id!r}, verified={self.verified_at is not None})"


class OpenCodeCredentialMetadata(Base):
    """Facts *about* the stored provider credential. Never the credential.

    The ``secret_metadata`` pattern, applied to the second thing this
    application holds that is worth stealing. Three columns and no fourth:
    where the envelope is (relative to the data directory, never absolute -
    SI-36), when it was written, and a fingerprint that names the value
    without revealing it.

    There is no column here, and no endpoint anywhere, that returns or copies
    the credential itself. ``updated_at`` moves because a provider key is
    replaceable, which is the one deliberate difference from the audit
    chain's never-overwrite rule (ADR-0005 7).
    """

    __tablename__ = "opencode_credential_metadata"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    envelope_relpath: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"OpenCodeCredentialMetadata(id={self.id!r})"


class OpenCodeCatalogCheck(Base):
    """One user-initiated read of the public model catalog.

    The ``official_source_snapshot`` shape: what we asked for, what came
    back, and a bounded excerpt kept for human review and never returned over
    HTTP. The catalog answers without a credential, so a row here proves a
    document was readable and nothing at all about whether the stored
    credential is valid.
    """

    __tablename__ = "opencode_catalog_check"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: ok | fetch_error | parse_error
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: 0 when the request never produced a status (DNS, TLS, timeout).
    http_status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Bounded and control-character-swept. Kept for human review; never
    #: returned over HTTP.
    snapshot_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"OpenCodeCatalogCheck(id={self.id!r}, state={self.state!r})"


class OpenCodeModelSnapshot(Base):
    """One catalog row as it arrived, joined to what this build knows.

    ``selectable`` and ``protocol`` are written from the **compile-time**
    table, never from the document: a fetched catalog cannot make a model
    addressable, which is the property ADR-0005 5 is about.
    """

    __tablename__ = "opencode_model_snapshot"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    check_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("opencode_catalog_check.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    owned_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    #: The provider's own stamp when it sent one; NULL when it did not.
    created_stamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    selectable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    mapping_state: Mapped[str] = mapped_column(String(32), nullable=False)
    training_use: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"OpenCodeModelSnapshot(model_id={self.model_id!r}, "
            f"selectable={self.selectable!r})"
        )


class AgentRun(Base):
    """One bounded run of registered tools over one task.

    Package H2's storage, and the reason it is a table rather than a field on
    ``task_record``: a plan, its steps, its expected artifacts and its test
    condition are written down **before** the run starts (ADR-0008 7), and a
    row created at plan time and never rewritten is what makes "changing the
    plan cannot quietly loosen the success criterion" a structural claim.
    ``plan_sha256`` covers the ordered steps together with the expected
    artifacts and the test condition, so an edited plan is a different plan
    and says so.

    ``phase`` is deliberately **not** called ``state``. The task's state is
    the nine-value machine in :mod:`station_api.tasks.states`, written by one
    function; this column is the run's own bookkeeping, and giving the two the
    same name is how a reader ends up believing there are two state machines
    for one thing. The naming also keeps the state-write scan
    (``test_only_the_transition_method_writes_a_task_state``, extended to this
    package in H2) meaningful rather than noisy.

    The ceiling columns are a **copy** taken at plan time, for the record. No
    code path writes them afterwards and nothing reads them to decide
    anything: the live decision is made by
    :func:`station_api.agent.budget.check` against the compile-time constant.

    No column holds a model reasoning trace, a provider payload, a credential,
    a filesystem path or a seed. The model lane is closed (ADR-0008 2), so
    there is nothing of the kind to store.
    """

    __tablename__ = "agent_run"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("task_record.id", ondelete="CASCADE"), nullable=False
    )
    #: ``planned``, ``running``, ``paused``, ``completed``, ``cancelled``,
    #: ``tool_error``, ``budget_exhausted`` or ``artifact_missing``. Kept
    #: apart so "the ceiling was reached", "a tool failed" and "the user
    #: stopped it" are three different sentences (ADR-0008 7).
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Set by the stop route. The runner reads it before every tool call.
    stop_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    #: Digest over the frozen plan: steps, expected artifacts, test condition
    #: **and the acceptance conditions**.
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The sentence the plan says would establish success. Recorded, never
    #: run: a sentence is not a check, and interpreting one would be the
    #: arbitrary execution ADR-0008 1 closes.
    test_condition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Canonical JSON array of the machine-checkable acceptance conditions,
    #: each a member of the closed registry in
    #: :mod:`station_api.agent.acceptance` with arguments already validated
    #: against that member's declared parameter types. Empty for a plan that
    #: recorded only the sentence above, which is what every row written
    #: before migration ``0010`` carries and exactly what those rows meant.
    #:
    #: Inside ``plan_sha256`` on purpose: an acceptance condition edited after
    #: a plan was approved is a *loosened success criterion*, and the whole
    #: point of writing the plan down first is that this is a refusal rather
    #: than a silent change.
    acceptance_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    #: Canonical JSON array of the file names the plan promises to produce.
    expected_artifacts: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    tool_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    max_wall_clock_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AgentRun(id={self.id!r}, phase={self.phase!r})"


class AgentRunStep(Base):
    """One planned tool call, and what became of it.

    Written at plan time with ``phase='planned'`` and updated once, when the
    runner reaches it. A step that was never reached keeps its planned row,
    which is what lets a stopped run show what it was going to do next
    instead of ending in silence.
    """

    __tablename__ = "agent_run_step"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    #: A ``ToolId`` value from the compile-time registry, never a free string.
    tool_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The tool's declared ``ToolScope``, copied so a review can read the
    #: permission a step needed without resolving the registry again.
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    #: The validated arguments, as a canonical JSON object. The user's own
    #: text, swept and bounded before it got here. Stored rather than kept in
    #: memory so a run interrupted by a restart can be *loaded* and looked at,
    #: and so a resume executes what was written down rather than what a later
    #: request rebuilt (ADR-0008 7).
    arguments_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    #: Digest over those arguments. Re-derived before every call, so a row
    #: edited underneath the run is a refusal rather than a silent change.
    arguments_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: ``planned``, ``ran``, ``refused``, ``failed`` or ``skipped``.
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    artifact_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AgentRunStep(run_id={self.run_id!r}, ordinal={self.ordinal!r})"


class ActivityEvent(Base):
    """The Activity Desk log: append-only, and a different layer from the chain.

    ADR-0008 6 keeps two things apart that a single table would merge:

    * **this table** is the step-by-step record. It is voluminous, it has its
      own retention (``RETAINED_EVENTS``), and its rows are **not chain
      links** - deleting one cannot break any MAC.
    * **the audit chain** carries only decision points, as new
      ``AuditEventName`` members. It is never pruned (ADR-0003 7).

    ``chain_referenced`` is what makes the two compatible rather than merely
    adjacent: when a decision point is written into the chain it names this
    row's id, and retention refuses to delete a row carrying the flag. So
    "the chain is never pruned" and "the timeline has a retention policy" are
    both true, and neither is achieved by weakening the other.

    What is **not** here, and could not be added without a migration a
    reviewer would see: a reasoning trace, a prompt, a completion, a raw
    provider payload. The model lane is closed, and this table has nowhere to
    put such a thing (ADR-0008 6).
    """

    __tablename__ = "activity_event"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: Empty when the event is not about one run.
    run_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    task_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    #: ``user`` or ``station_runner``. There is no ``model`` actor.
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    #: An ``ActivityAction`` value. "planned", "ran", "check recorded",
    #: "artifact produced" and "awaiting approval" are separate members.
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    #: ``ok``, ``refused``, ``failed`` or ``pending``.
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: The digest of the deterministic checker's own output, when one ran.
    check_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: One safe sentence. Swept, redacted and bounded before it is stored.
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: True once an audit link names this row. Retention may not remove it.
    chain_referenced: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ActivityEvent(id={self.id!r}, action={self.action!r})"
