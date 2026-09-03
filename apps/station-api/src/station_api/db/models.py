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
    #: The room's conversation epoch, kept as digits.
    room_generation: Mapped[str] = mapped_column(String(32), nullable=False, default="")
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
