"""The DPAPI vault.

Layout of a stored secret, outermost first:

    vault file (strict JSON envelope, version 1)
      -> dpapi_blob            DPAPI, current-user scope
           -> inner payload
                protection "dpapi"            : the raw 32-byte seed
                protection "dpapi+passphrase" : Argon2id + ChaCha20-Poly1305
                                                over the seed

The passphrase layer sits *inside* the DPAPI envelope on purpose. Someone who
copies the file to another machine gets nothing, because DPAPI is bound to
this Windows user; someone already running as this Windows user still faces
Argon2id.

Honest limit: Python cannot guarantee that seed bytes are wiped from memory.
The ``bytearray`` scrubbing below is best-effort - the interpreter may have
copied the value during allocation or garbage collection. This is documented
in SECURITY.md rather than dressed up as a guarantee.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from station_api.strict_json import (
    StrictJsonError,
    b64u_decode,
    b64u_encode,
    canonical_json_bytes,
    loads_strict,
    require_exact_keys,
    require_int,
    require_str,
)
from station_api.vault import dpapi, windows_acl
from station_api.vault.errors import (
    VaultAlreadyExistsError,
    VaultCapabilityError,
    VaultFormatError,
    VaultNotFoundError,
    VaultUnlockError,
    VaultUnsupportedPlatformError,
)
from station_api.vault.passphrase import (
    AEAD_CHACHA20POLY1305,
    KDF_ARGON2ID,
    PRODUCTION_KDF_POLICY,
    KdfPolicy,
    aead_decrypt,
    aead_encrypt,
    aead_self_test,
    derive_key,
    new_nonce,
    new_salt,
)
from station_api.vault.paths import validate_identity_id, vault_dir, vault_file

VAULT_FORMAT = "technocore-station.vault"
VAULT_VERSION = 1

#: A vault envelope is tiny; anything larger is not ours.
MAX_VAULT_BYTES = 64 * 1024

SEED_LENGTH = 32

_ENVELOPE_KEYS = frozenset(
    {"format", "version", "identity_id", "protection", "created_at", "dpapi_blob"}
)
_INNER_KEYS = frozenset({"kdf", "t", "m", "p", "salt", "nonce", "aead", "ciphertext"})


class ProtectionMode(StrEnum):
    """How a stored seed is protected."""

    DPAPI = "dpapi"
    # The suppression below is deliberate: this string is the NAME of a
    # protection mode, not a password. No secret is hardcoded here.
    DPAPI_PASSPHRASE = "dpapi+passphrase"  # noqa: S105


#: Recommended and default. The passphrase layer is what survives an attacker
#: who is already running as this Windows user.
DEFAULT_PROTECTION = ProtectionMode.DPAPI_PASSPHRASE


@dataclass(frozen=True)
class VaultCapability:
    """Result of the startup self-test."""

    platform_supported: bool
    dpapi_available: bool
    aead_available: bool
    detail: str

    @property
    def usable(self) -> bool:
        return self.platform_supported and self.dpapi_available and self.aead_available


def _inner_aad(identity_id: str) -> bytes:
    """Bind the inner ciphertext to the identity it belongs to."""
    return f"technocore-station/vault/v1/{identity_id}".encode()


class DpapiVault:
    """Current-user DPAPI vault with an optional Argon2id passphrase layer.

    There is no fake or in-memory implementation of this class. A test that
    needs a vault runs the real one on Windows, or asserts the fail-closed
    behaviour elsewhere. A silent fallback would let production quietly store
    an unprotected seed.
    """

    def __init__(self, data_dir: Path, *, kdf_policy: KdfPolicy = PRODUCTION_KDF_POLICY) -> None:
        self._data_dir = data_dir
        self._kdf_policy = kdf_policy

    # --- capability ----------------------------------------------------

    def capability(self) -> VaultCapability:
        if not dpapi.is_supported():
            return VaultCapability(
                platform_supported=False,
                dpapi_available=False,
                aead_available=aead_self_test(),
                detail="Bu surum yalniz Windows uzerinde calisir (DPAPI gerekli).",
            )
        dpapi_ok = dpapi.self_test()
        aead_ok = aead_self_test()
        if dpapi_ok and aead_ok:
            detail = "DPAPI ve AEAD kullanilabilir."
        elif not dpapi_ok:
            detail = "DPAPI self-test basarisiz oldu."
        else:
            detail = "AEAD self-test basarisiz oldu."
        return VaultCapability(
            platform_supported=True,
            dpapi_available=dpapi_ok,
            aead_available=aead_ok,
            detail=detail,
        )

    def require_capability(self) -> None:
        capability = self.capability()
        if not capability.platform_supported:
            raise VaultUnsupportedPlatformError(capability.detail)
        if not capability.usable:
            raise VaultCapabilityError(capability.detail)

    # --- paths ---------------------------------------------------------

    def path_for(self, identity_id: str) -> Path:
        return vault_file(self._data_dir, identity_id)

    def exists(self, identity_id: str) -> bool:
        return self.path_for(identity_id).is_file()

    # --- write ---------------------------------------------------------

    def store(
        self,
        *,
        identity_id: str,
        seed: bytes,
        protection: ProtectionMode,
        passphrase: str | None,
    ) -> Path:
        """Write a new vault envelope atomically. Never overwrites."""
        self.require_capability()
        validate_identity_id(identity_id)

        if len(seed) != SEED_LENGTH:
            raise VaultFormatError("seed must be exactly 32 bytes")
        if protection is ProtectionMode.DPAPI_PASSPHRASE and not passphrase:
            raise VaultFormatError("this protection mode requires a passphrase")

        target = self.path_for(identity_id)
        if target.exists():
            raise VaultAlreadyExistsError("a vault already exists for this identity")

        inner = self._build_inner(identity_id, seed, protection, passphrase)
        envelope = {
            "format": VAULT_FORMAT,
            "version": VAULT_VERSION,
            "identity_id": identity_id,
            "protection": protection.value,
            "created_at": datetime.now(UTC).isoformat(),
            "dpapi_blob": b64u_encode(dpapi.protect(inner)),
        }

        self._atomic_write(target, canonical_json_bytes(envelope))
        return target

    def _build_inner(
        self,
        identity_id: str,
        seed: bytes,
        protection: ProtectionMode,
        passphrase: str | None,
    ) -> bytes:
        if protection is ProtectionMode.DPAPI:
            return bytes(seed)

        if passphrase is None:  # pragma: no cover - guarded by the caller
            raise VaultFormatError("this protection mode requires a passphrase")

        salt = new_salt()
        nonce = new_nonce()
        key = bytearray(derive_key(passphrase, salt, self._kdf_policy))
        try:
            ciphertext = aead_encrypt(bytes(key), nonce, bytes(seed), _inner_aad(identity_id))
        finally:
            # Best-effort scrub; see the module docstring on memory limits.
            for index in range(len(key)):
                key[index] = 0

        return canonical_json_bytes(
            {
                "kdf": KDF_ARGON2ID,
                "t": self._kdf_policy.time_cost,
                "m": self._kdf_policy.memory_cost_kib,
                "p": self._kdf_policy.parallelism,
                "salt": b64u_encode(salt),
                "nonce": b64u_encode(nonce),
                "aead": AEAD_CHACHA20POLY1305,
                "ciphertext": b64u_encode(ciphertext),
            }
        )

    def _atomic_write(self, target: Path, payload: bytes) -> None:
        """Write via a temp file in the same directory, then rename.

        The ACL is applied to the temporary file before the *rename*, and
        again afterwards because a rename can carry a different security
        descriptor depending on the volume. Any failure raises
        ``VaultAclError`` and the temporary file is removed, so a vault whose
        ACL could not be applied is never left behind.

        Two claims that used to be here are gone because neither was true of
        this code. It said the secret is "never briefly readable under
        inherited permissions": the order is write, fsync, ACL, rename, ACL,
        so the payload is on disk under the directory's inherited DACL for
        the moment between the write and the first ACL call - what sits there
        is the DPAPI blob, not the seed. And it said the ACL is "verified":
        nothing here reads the DACL back. ``windows_acl.acl_grantee_sids``
        does, and the vault's tests use it, but this method does not, so it
        does not claim to.

        The directory is created with ``mkdir`` and left on inherited
        permissions; only the file carries a protected DACL. That is an
        accepted limitation, recorded in ``docs/security-invariants.md``
        (SI-266) rather than implied away here.
        """
        directory = vault_dir(self._data_dir)
        directory.mkdir(parents=True, exist_ok=True)

        handle, temp_name = tempfile.mkstemp(dir=directory, suffix=".tmp")
        temp_path = Path(temp_name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

            windows_acl.restrict_to_current_user(temp_path)
            os.replace(temp_path, target)
            windows_acl.restrict_to_current_user(target)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

    # --- read ----------------------------------------------------------

    def load(self, *, identity_id: str, passphrase: str | None = None) -> bytes:
        """Open the vault and return the raw seed.

        The caller must use the value for the shortest possible time. Every
        failure mode - missing passphrase, wrong passphrase, tampered inner
        ciphertext, failed DPAPI unprotect - raises ``VaultUnlockError``.
        """
        self.require_capability()
        validate_identity_id(identity_id)

        target = self.path_for(identity_id)
        if not target.is_file():
            raise VaultNotFoundError("no vault envelope exists for this identity")

        envelope = self._read_envelope(target, identity_id)
        protection = ProtectionMode(envelope["protection"])
        inner = dpapi.unprotect(b64u_decode(envelope["dpapi_blob"]))

        if protection is ProtectionMode.DPAPI:
            if len(inner) != SEED_LENGTH:
                raise VaultUnlockError("vault payload has an unexpected length")
            return inner

        if not passphrase:
            raise VaultUnlockError("this vault requires a passphrase")
        return self._open_inner(inner, identity_id, passphrase)

    def _read_envelope(self, target: Path, identity_id: str) -> dict[str, Any]:
        raw = target.read_bytes()
        try:
            envelope = loads_strict(raw, max_bytes=MAX_VAULT_BYTES)
            require_exact_keys(envelope, _ENVELOPE_KEYS)
            if require_str(envelope, "format") != VAULT_FORMAT:
                raise VaultFormatError("unexpected vault format")
            if require_int(envelope, "version") != VAULT_VERSION:
                raise VaultFormatError("unsupported vault version")
            if require_str(envelope, "identity_id") != identity_id:
                raise VaultFormatError("vault envelope belongs to another identity")
            protection = require_str(envelope, "protection")
            if protection not in {mode.value for mode in ProtectionMode}:
                raise VaultFormatError("unknown protection mode")
            require_str(envelope, "created_at")
            require_str(envelope, "dpapi_blob")
        except StrictJsonError as exc:
            raise VaultFormatError(str(exc)) from exc
        return envelope

    def _open_inner(self, inner: bytes, identity_id: str, passphrase: str) -> bytes:
        try:
            payload = loads_strict(inner, max_bytes=MAX_VAULT_BYTES)
            require_exact_keys(payload, _INNER_KEYS)
            if require_str(payload, "kdf") != KDF_ARGON2ID:
                raise VaultUnlockError("unsupported kdf")
            if require_str(payload, "aead") != AEAD_CHACHA20POLY1305:
                raise VaultUnlockError("unsupported aead")

            time_cost = require_int(payload, "t")
            memory_cost = require_int(payload, "m")
            parallelism = require_int(payload, "p")
            self._kdf_policy.validate_untrusted(
                time_cost=time_cost,
                memory_cost_kib=memory_cost,
                parallelism=parallelism,
                hash_length=self._kdf_policy.hash_length,
            )

            salt = b64u_decode(require_str(payload, "salt"))
            nonce = b64u_decode(require_str(payload, "nonce"))
            ciphertext = b64u_decode(require_str(payload, "ciphertext"))
        except StrictJsonError as exc:
            raise VaultUnlockError("vault payload is malformed") from exc

        policy = KdfPolicy(
            time_cost=time_cost,
            memory_cost_kib=memory_cost,
            parallelism=parallelism,
            hash_length=self._kdf_policy.hash_length,
        )
        key = bytearray(derive_key(passphrase, salt, policy))
        try:
            seed = aead_decrypt(bytes(key), nonce, ciphertext, _inner_aad(identity_id))
        finally:
            for index in range(len(key)):
                key[index] = 0

        if len(seed) != SEED_LENGTH:
            raise VaultUnlockError("vault payload has an unexpected length")
        return seed

    # --- delete --------------------------------------------------------

    def delete(self, identity_id: str) -> bool:
        """Remove the envelope.

        This unlinks a file. It is **not** a secure disk wipe: copies may
        remain in filesystem journals, shadow copies or backups, and existing
        recovery files stay valid. Both facts are stated in the UI.
        """
        validate_identity_id(identity_id)
        target = self.path_for(identity_id)
        if not target.is_file():
            return False
        target.unlink()
        return True


__all__ = [
    "DEFAULT_PROTECTION",
    "MAX_VAULT_BYTES",
    "SEED_LENGTH",
    "VAULT_FORMAT",
    "VAULT_VERSION",
    "DpapiVault",
    "ProtectionMode",
    "VaultCapability",
]
