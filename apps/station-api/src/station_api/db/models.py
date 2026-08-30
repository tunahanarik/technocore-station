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

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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
