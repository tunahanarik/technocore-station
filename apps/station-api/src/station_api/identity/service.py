"""Identity lifecycle orchestration.

This module is the only place a seed exists in process memory, and it holds
one for the shortest window it can: generate or unlock, use, drop. Callers
receive ``IdentityView`` objects, which carry public material only.

Rollback matters here because two stores must agree - a file on disk and a row
in SQLite. Every mutating operation cleans up the half it already did if the
other half fails, so there is never an orphan vault or an identity row whose
secret does not exist.

Honest limit: ``bytearray`` scrubbing is best-effort. CPython may have copied
the seed during allocation or garbage collection, and there is no portable way
to guarantee erasure. Documented, not papered over.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from technocore_conform import (
    ConformanceError,
    did_key_from_seed,
    fingerprint_from_public_key,
    public_key_from_seed,
)

from station_api.db.models import (
    ACTIVE_SLOT,
    Identity,
    IdentityStatus,
    RecoveryRecord,
    SecretMetadata,
)
from station_api.identity import write_gate
from station_api.identity.write_gate import WriteGateInput, WriteGateStatus
from station_api.recovery import create_recovery, file_fingerprint, open_recovery
from station_api.vault import DpapiVault, ProtectionMode, VaultCapability
from station_api.vault.passphrase import KDF_ARGON2ID, PRODUCTION_KDF_POLICY, KdfPolicy
from station_api.vault.paths import new_identity_id

#: The seed is exactly 32 bytes of CSPRNG output. There is no other source:
#: no passphrase derivation, no user-supplied entropy, no counter.
SEED_LENGTH = 32


class IdentityState(StrEnum):
    """What the Identity surface should render."""

    NO_IDENTITY = "no_identity"
    CREATING = "creating"
    RECOVERY_PENDING = "recovery_pending"
    READY = "ready"
    REVOKED = "revoked"
    CAPABILITY_ERROR = "capability_error"


class IdentityServiceError(Exception):
    """A lifecycle operation was refused. Message is safe to show a user."""


@dataclass(frozen=True)
class RecoveryView:
    exported_at: datetime | None
    verified_at: datetime | None
    file_fingerprint: str | None
    kdf: str | None
    kdf_time_cost: int | None
    kdf_memory_kib: int | None
    kdf_parallelism: int | None


@dataclass(frozen=True)
class IdentityView:
    """Public projection of an identity. Contains no secret material."""

    state: IdentityState
    did: str | None
    public_key: str | None
    fingerprint: str | None
    label: str | None
    protection: str | None
    created_at: datetime | None
    revoked_at: datetime | None
    recovery: RecoveryView
    capability: VaultCapability
    gate: WriteGateStatus


_EMPTY_RECOVERY = RecoveryView(None, None, None, None, None, None, None)


def generate_seed() -> bytes:
    """32 bytes from the OS CSPRNG. The only way a seed is ever born."""
    return secrets.token_bytes(SEED_LENGTH)


class IdentityService:
    """Coordinates the vault, the recovery format and the database."""

    def __init__(
        self,
        *,
        engine: Engine,
        data_dir: Path,
        vault: DpapiVault | None = None,
        kdf_policy: KdfPolicy = PRODUCTION_KDF_POLICY,
    ) -> None:
        self._engine = engine
        self._data_dir = data_dir
        self._kdf_policy = kdf_policy
        self._vault = vault or DpapiVault(data_dir, kdf_policy=kdf_policy)

    # --- read ----------------------------------------------------------

    def _current(self, session: Session) -> Identity | None:
        """The active identity, or the most recent revoked one."""
        active = session.scalar(select(Identity).where(Identity.active_slot == ACTIVE_SLOT))
        if active is not None:
            return active
        return session.scalar(select(Identity).order_by(Identity.created_at.desc()).limit(1))

    def describe(self) -> IdentityView:
        capability = self._vault.capability()
        with Session(self._engine) as session:
            identity = self._current(session)
            return self._view(session, identity, capability)

    def _view(
        self,
        session: Session,
        identity: Identity | None,
        capability: VaultCapability,
    ) -> IdentityView:
        if identity is None:
            state = (
                IdentityState.CAPABILITY_ERROR
                if not capability.usable
                else IdentityState.NO_IDENTITY
            )
            return IdentityView(
                state=state,
                did=None,
                public_key=None,
                fingerprint=None,
                label=None,
                protection=None,
                created_at=None,
                revoked_at=None,
                recovery=_EMPTY_RECOVERY,
                capability=capability,
                gate=write_gate.evaluate(
                    WriteGateInput(
                        has_identity=False,
                        identity_revoked=False,
                        vault_present=False,
                        recovery_verified=False,
                    )
                ),
            )

        metadata = session.get(SecretMetadata, identity.id)
        record = session.scalar(
            select(RecoveryRecord)
            .where(RecoveryRecord.identity_id == identity.id)
            .order_by(RecoveryRecord.created_at.desc())
            .limit(1)
        )
        revoked = identity.status == IdentityStatus.REVOKED
        vault_present = (not revoked) and self._vault.exists(identity.id)
        verified_at = metadata.recovery_verified_at if metadata else None

        state = (
            IdentityState.CAPABILITY_ERROR
            if not capability.usable
            else IdentityState(identity.status)
        )

        recovery = RecoveryView(
            exported_at=record.created_at if record else None,
            verified_at=verified_at,
            file_fingerprint=record.file_fingerprint if record else None,
            kdf=record.kdf if record else None,
            kdf_time_cost=record.kdf_time_cost if record else None,
            kdf_memory_kib=record.kdf_memory_kib if record else None,
            kdf_parallelism=record.kdf_parallelism if record else None,
        )

        return IdentityView(
            state=state,
            did=identity.did,
            public_key=identity.public_key,
            fingerprint=identity.fingerprint,
            label=identity.label,
            protection=metadata.protection if metadata else None,
            created_at=identity.created_at,
            revoked_at=identity.revoked_at,
            recovery=recovery,
            capability=capability,
            gate=write_gate.evaluate(
                WriteGateInput(
                    has_identity=True,
                    identity_revoked=revoked,
                    vault_present=vault_present,
                    recovery_verified=verified_at is not None,
                )
            ),
        )

    # --- create --------------------------------------------------------

    def create(
        self,
        *,
        protection: ProtectionMode,
        passphrase: str | None,
        label: str = "",
    ) -> IdentityView:
        """Generate a brand new identity. Refuses if one is already active."""
        seed = bytearray(generate_seed())
        try:
            return self._adopt_seed(
                seed=bytes(seed), protection=protection, passphrase=passphrase, label=label
            )
        finally:
            for index in range(len(seed)):
                seed[index] = 0

    def import_seed(
        self,
        *,
        seed: bytes,
        protection: ProtectionMode,
        passphrase: str | None,
        label: str = "",
    ) -> IdentityView:
        """Adopt an existing 32-byte seed. Reached only from the local CLI."""
        if len(seed) != SEED_LENGTH:
            raise IdentityServiceError("Seed tam olarak 32 bayt olmalidir.")
        return self._adopt_seed(
            seed=seed, protection=protection, passphrase=passphrase, label=label
        )

    def _adopt_seed(
        self,
        *,
        seed: bytes,
        protection: ProtectionMode,
        passphrase: str | None,
        label: str,
        recovery_already_verified: bool = False,
        recovery_metadata: tuple[str, int, int, int, str] | None = None,
    ) -> IdentityView:
        """Shared path for create, CLI import and clean-profile adoption."""
        capability = self._vault.capability()
        if not capability.usable:
            raise IdentityServiceError(capability.detail)

        try:
            public_key = public_key_from_seed(seed)
            did = did_key_from_seed(seed)
            fingerprint = fingerprint_from_public_key(public_key)
        except ConformanceError as exc:
            raise IdentityServiceError("Seed gecerli bir Ed25519 anahtari uretmedi.") from exc

        identity_id = new_identity_id()
        now = datetime.now(UTC)

        with Session(self._engine) as session:
            if session.scalar(select(Identity).where(Identity.active_slot == ACTIVE_SLOT)):
                raise IdentityServiceError(
                    "Bu bilgisayarda zaten aktif bir kimlik var. Once onu revoke edin."
                )
            if session.scalar(select(Identity).where(Identity.did == did)):
                raise IdentityServiceError("Bu DID zaten kayitli.")

            session.add(
                Identity(
                    id=identity_id,
                    did=did,
                    public_key=public_key.hex(),
                    fingerprint=fingerprint,
                    label=label,
                    status=IdentityStatus.CREATING,
                    active_slot=ACTIVE_SLOT,
                    created_at=now,
                    revoked_at=None,
                )
            )
            session.commit()

        vault_written = False
        try:
            vault_path = self._vault.store(
                identity_id=identity_id,
                seed=seed,
                protection=protection,
                passphrase=passphrase,
            )
            vault_written = True

            with Session(self._engine) as session:
                identity = session.get(Identity, identity_id)
                if identity is None:  # pragma: no cover - just inserted
                    raise IdentityServiceError("Kimlik kaydi kayboldu.")
                identity.status = (
                    IdentityStatus.READY
                    if recovery_already_verified
                    else IdentityStatus.RECOVERY_PENDING
                )
                session.add(
                    SecretMetadata(
                        identity_id=identity_id,
                        vault_relpath=str(vault_path.relative_to(self._data_dir)),
                        protection=protection.value,
                        created_at=now,
                        last_used_at=None,
                        recovery_verified_at=now if recovery_already_verified else None,
                    )
                )
                if recovery_metadata is not None:
                    digest, time_cost, memory_kib, parallelism, kdf_name = recovery_metadata
                    session.add(
                        RecoveryRecord(
                            id=uuid.uuid4().hex,
                            identity_id=identity_id,
                            file_fingerprint=digest,
                            kdf=kdf_name,
                            kdf_time_cost=time_cost,
                            kdf_memory_kib=memory_kib,
                            kdf_parallelism=parallelism,
                            created_at=now,
                            verified_at=now if recovery_already_verified else None,
                        )
                    )
                session.commit()
        except BaseException:
            # Undo both halves so no orphan vault or identity row survives.
            if vault_written:
                self._vault.delete(identity_id)
            with Session(self._engine) as session:
                identity = session.get(Identity, identity_id)
                if identity is not None:
                    session.delete(identity)
                    session.commit()
            raise

        return self.describe()

    # --- recovery export -----------------------------------------------

    def export_recovery(
        self, *, recovery_passphrase: str, vault_passphrase: str | None
    ) -> tuple[bytes, str]:
        """Produce a ``.tcrec``. Returns (file bytes, did).

        The seed is unlocked, used to build the file, and dropped. Neither the
        ciphertext nor either passphrase reaches the database.
        """
        with Session(self._engine) as session:
            identity = session.scalar(
                select(Identity).where(Identity.active_slot == ACTIVE_SLOT)
            )
            if identity is None:
                raise IdentityServiceError("Aktif kimlik yok.")
            identity_id = identity.id
            did = identity.did

        seed = bytearray(self._vault.load(identity_id=identity_id, passphrase=vault_passphrase))
        try:
            payload = create_recovery(
                seed=bytes(seed), passphrase=recovery_passphrase, policy=self._kdf_policy
            )
        finally:
            for index in range(len(seed)):
                seed[index] = 0

        now = datetime.now(UTC)
        with Session(self._engine) as session:
            session.add(
                RecoveryRecord(
                    id=uuid.uuid4().hex,
                    identity_id=identity_id,
                    file_fingerprint=file_fingerprint(payload),
                    kdf=KDF_ARGON2ID,
                    kdf_time_cost=self._kdf_policy.time_cost,
                    kdf_memory_kib=self._kdf_policy.memory_cost_kib,
                    kdf_parallelism=self._kdf_policy.parallelism,
                    created_at=now,
                    verified_at=None,
                )
            )
            metadata = session.get(SecretMetadata, identity_id)
            if metadata is not None:
                metadata.last_used_at = now
            session.commit()

        return payload, did

    # --- restore test ---------------------------------------------------

    def restore_test(self, *, payload: bytes, recovery_passphrase: str) -> IdentityView:
        """Prove the recovery file really reconstructs the installed identity.

        Writes nothing but the verification timestamps, and only on success.
        The vault is not touched at all: the seed comes from the file.
        """
        with Session(self._engine) as session:
            identity = session.scalar(
                select(Identity).where(Identity.active_slot == ACTIVE_SLOT)
            )
            if identity is None:
                raise IdentityServiceError("Aktif kimlik yok.")
            identity_id = identity.id
            installed_did = identity.did

        opened = open_recovery(payload, passphrase=recovery_passphrase, policy=self._kdf_policy)
        seed = bytearray(opened.seed)
        try:
            derived_did = did_key_from_seed(bytes(seed))
        finally:
            for index in range(len(seed)):
                seed[index] = 0

        # Three-way agreement: derived, header, installed.
        if derived_did != opened.did or derived_did != installed_did:
            raise IdentityServiceError("Recovery dosyasi bu bilgisayardaki kimlige ait degil.")

        now = datetime.now(UTC)
        digest = file_fingerprint(payload)
        with Session(self._engine) as session:
            metadata = session.get(SecretMetadata, identity_id)
            if metadata is None:
                raise IdentityServiceError("Secret metadata bulunamadi.")
            metadata.recovery_verified_at = now

            record = session.scalar(
                select(RecoveryRecord).where(
                    RecoveryRecord.identity_id == identity_id,
                    RecoveryRecord.file_fingerprint == digest,
                )
            )
            if record is None:
                session.add(
                    RecoveryRecord(
                        id=uuid.uuid4().hex,
                        identity_id=identity_id,
                        file_fingerprint=digest,
                        kdf=opened.kdf.kdf,
                        kdf_time_cost=opened.kdf.time_cost,
                        kdf_memory_kib=opened.kdf.memory_kib,
                        kdf_parallelism=opened.kdf.parallelism,
                        created_at=now,
                        verified_at=now,
                    )
                )
            else:
                record.verified_at = now

            identity = session.get(Identity, identity_id)
            if identity is not None and identity.status != IdentityStatus.REVOKED:
                identity.status = IdentityStatus.READY
            session.commit()

        return self.describe()

    # --- clean profile adoption -----------------------------------------

    def inspect_recovery(self, *, payload: bytes, recovery_passphrase: str) -> str:
        """Open a ``.tcrec`` only far enough to show the user its public DID.

        Nothing is written. This is the confirmation step before adoption.
        """
        opened = open_recovery(payload, passphrase=recovery_passphrase, policy=self._kdf_policy)
        seed = bytearray(opened.seed)
        for index in range(len(seed)):
            seed[index] = 0
        return opened.did

    def adopt_from_recovery(
        self,
        *,
        payload: bytes,
        recovery_passphrase: str,
        protection: ProtectionMode,
        vault_passphrase: str | None,
        label: str = "",
    ) -> IdentityView:
        """Install an identity on a clean profile from a recovery file.

        Depends on nothing from the original machine: no DPAPI blob, no old
        Windows profile, only the ``.tcrec`` and its passphrase. The restored
        identity is marked recovery-verified, because opening the file *is*
        the restore test.
        """
        opened = open_recovery(payload, passphrase=recovery_passphrase, policy=self._kdf_policy)
        seed = bytearray(opened.seed)
        try:
            return self._adopt_seed(
                seed=bytes(seed),
                protection=protection,
                passphrase=vault_passphrase,
                label=label,
                recovery_already_verified=True,
                recovery_metadata=(
                    file_fingerprint(payload),
                    opened.kdf.time_cost,
                    opened.kdf.memory_kib,
                    opened.kdf.parallelism,
                    opened.kdf.kdf,
                ),
            )
        finally:
            for index in range(len(seed)):
                seed[index] = 0

    # --- revoke ---------------------------------------------------------

    def revoke(self, *, confirm_did: str) -> IdentityView:
        """Delete the vault envelope and mark the identity revoked.

        Not a secure wipe, and existing recovery files stay valid. Both are
        stated in the UI rather than implied away.
        """
        with Session(self._engine) as session:
            identity = session.scalar(
                select(Identity).where(Identity.active_slot == ACTIVE_SLOT)
            )
            if identity is None:
                raise IdentityServiceError("Aktif kimlik yok.")
            if confirm_did != identity.did:
                raise IdentityServiceError("Onay icin DID tam olarak yazilmalidir.")
            identity_id = identity.id

        self._vault.delete(identity_id)

        now = datetime.now(UTC)
        with Session(self._engine) as session:
            identity = session.get(Identity, identity_id)
            if identity is not None:
                identity.status = IdentityStatus.REVOKED
                identity.revoked_at = now
                identity.active_slot = None  # frees the single-active slot
            metadata = session.get(SecretMetadata, identity_id)
            if metadata is not None:
                metadata.recovery_verified_at = None
            session.commit()

        return self.describe()

    # --- gate -----------------------------------------------------------

    def write_gate_status(self) -> WriteGateStatus:
        return self.describe().gate


__all__ = [
    "SEED_LENGTH",
    "IdentityService",
    "IdentityServiceError",
    "IdentityState",
    "IdentityView",
    "RecoveryView",
    "generate_seed",
]
