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
    DateTime,
    ForeignKey,
    Integer,
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
