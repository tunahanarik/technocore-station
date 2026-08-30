"""The ``.tcrec`` v1 portable recovery file.

Specified in ``docs/recovery-format-v1.md``. Two properties define it:

* It is **independent of DPAPI**. A ``.tcrec`` opens on any machine, in any
  Windows account, given only the recovery passphrase. That is what makes it
  a real backup rather than a second copy of the same failure domain.
* Every header field except ``ciphertext`` is authenticated as AAD. Editing
  the DID, the timestamp, an algorithm name or a KDF parameter breaks
  decryption instead of silently changing meaning.

The recovery passphrase is a separate concept from the vault passphrase. It is
never stored, never logged, and never written to the database.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from technocore_conform import did_key_from_seed

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
from station_api.vault.errors import VaultUnlockError
from station_api.vault.passphrase import (
    AEAD_CHACHA20POLY1305,
    KDF_ARGON2ID,
    NONCE_LENGTH,
    PRODUCTION_KDF_POLICY,
    SALT_LENGTH,
    KdfPolicy,
    aead_decrypt,
    aead_encrypt,
    derive_key,
    new_nonce,
    new_salt,
)

RECOVERY_FORMAT = "technocore-station.recovery"
RECOVERY_VERSION = 1
RECOVERY_SUFFIX = ".tcrec"

#: Hard ceiling. A real file is well under 1 KiB; anything larger is hostile
#: or corrupt, and we refuse it before parsing.
MAX_RECOVERY_BYTES = 64 * 1024

SEED_LENGTH = 32

#: Every field, in the order documented. ``ciphertext`` is the only one that
#: is not part of the AAD.
_HEADER_KEYS = frozenset(
    {
        "format",
        "version",
        "did",
        "created_at",
        "kdf",
        "kdf_time_cost",
        "kdf_memory_kib",
        "kdf_parallelism",
        "salt",
        "aead",
        "nonce",
        "ciphertext",
    }
)

_AAD_EXCLUDED_KEY = "ciphertext"

#: The single external message for every failure to open a recovery file.
#: Wrong passphrase, tampered ciphertext and tampered header are
#: indistinguishable to the caller.
RECOVERY_FAILURE_MESSAGE = (
    "Recovery dosyasi acilamadi. Parola yanlis olabilir veya dosya degistirilmis olabilir."
)


@dataclass(frozen=True)
class RecoveryKdfMetadata:
    """Non-secret KDF parameters, safe to persist and to display."""

    kdf: str
    time_cost: int
    memory_kib: int
    parallelism: int


@dataclass(frozen=True)
class OpenedRecovery:
    """Result of opening a ``.tcrec``. ``seed`` must be used and dropped."""

    seed: bytes
    did: str
    created_at: str
    kdf: RecoveryKdfMetadata


def aad_for_header(header: dict[str, Any]) -> bytes:
    """AAD v1: canonical JSON of every header field except ``ciphertext``.

    Keys sorted by Unicode code point, separators ``,`` and ``:`` with no
    whitespace, non-ASCII preserved, UTF-8 encoded.
    """
    return canonical_json_bytes(
        {key: value for key, value in header.items() if key != _AAD_EXCLUDED_KEY}
    )


def file_fingerprint(payload: bytes) -> str:
    """SHA-256 of the whole file, lowercase hex. Safe to store: not a secret."""
    return hashlib.sha256(payload).hexdigest()


def create_recovery(
    *,
    seed: bytes,
    passphrase: str,
    policy: KdfPolicy = PRODUCTION_KDF_POLICY,
    created_at: datetime | None = None,
) -> bytes:
    """Build a ``.tcrec`` file for ``seed``.

    A fresh salt and a fresh nonce are drawn per file, so two exports of the
    same seed with the same passphrase are byte-different.
    """
    if len(seed) != SEED_LENGTH:
        raise ValueError("seed must be exactly 32 bytes")

    salt = new_salt()
    nonce = new_nonce()
    moment = created_at or datetime.now(UTC)

    header: dict[str, Any] = {
        "format": RECOVERY_FORMAT,
        "version": RECOVERY_VERSION,
        "did": did_key_from_seed(seed),
        "created_at": moment.isoformat(),
        "kdf": KDF_ARGON2ID,
        "kdf_time_cost": policy.time_cost,
        "kdf_memory_kib": policy.memory_cost_kib,
        "kdf_parallelism": policy.parallelism,
        "salt": b64u_encode(salt),
        "aead": AEAD_CHACHA20POLY1305,
        "nonce": b64u_encode(nonce),
    }

    key = bytearray(derive_key(passphrase, salt, policy))
    try:
        ciphertext = aead_encrypt(bytes(key), nonce, bytes(seed), aad_for_header(header))
    finally:
        for index in range(len(key)):
            key[index] = 0

    header[_AAD_EXCLUDED_KEY] = b64u_encode(ciphertext)
    return canonical_json_bytes(header)


def open_recovery(
    payload: bytes,
    *,
    passphrase: str,
    policy: KdfPolicy = PRODUCTION_KDF_POLICY,
) -> OpenedRecovery:
    """Open a ``.tcrec`` and return the seed plus its public metadata.

    Fail-closed at every step, and every failure raises ``VaultUnlockError``
    so the caller cannot distinguish a wrong passphrase from a tampered file.
    """
    try:
        header = loads_strict(payload, max_bytes=MAX_RECOVERY_BYTES)
        require_exact_keys(header, _HEADER_KEYS)

        if require_str(header, "format") != RECOVERY_FORMAT:
            raise VaultUnlockError("unexpected recovery format")
        if require_int(header, "version") != RECOVERY_VERSION:
            raise VaultUnlockError("unsupported recovery version")
        if require_str(header, "kdf") != KDF_ARGON2ID:
            raise VaultUnlockError("unsupported kdf")
        if require_str(header, "aead") != AEAD_CHACHA20POLY1305:
            raise VaultUnlockError("unsupported aead")

        time_cost = require_int(header, "kdf_time_cost")
        memory_kib = require_int(header, "kdf_memory_kib")
        parallelism = require_int(header, "kdf_parallelism")

        # Bounds are checked BEFORE any derivation, so a hostile header can
        # never make us allocate gigabytes or spin for minutes.
        policy.validate_untrusted(
            time_cost=time_cost,
            memory_cost_kib=memory_kib,
            parallelism=parallelism,
            hash_length=policy.hash_length,
        )

        salt = b64u_decode(require_str(header, "salt"))
        nonce = b64u_decode(require_str(header, "nonce"))
        ciphertext = b64u_decode(require_str(header, _AAD_EXCLUDED_KEY))
        header_did = require_str(header, "did")
        created_at = require_str(header, "created_at")
    except StrictJsonError as exc:
        raise VaultUnlockError("recovery file is malformed") from exc

    if len(salt) != SALT_LENGTH:
        raise VaultUnlockError("salt has the wrong length")
    if len(nonce) != NONCE_LENGTH:
        raise VaultUnlockError("nonce has the wrong length")

    derivation = KdfPolicy(
        time_cost=time_cost,
        memory_cost_kib=memory_kib,
        parallelism=parallelism,
        hash_length=policy.hash_length,
    )
    key = bytearray(derive_key(passphrase, salt, derivation))
    try:
        seed = aead_decrypt(bytes(key), nonce, ciphertext, aad_for_header(header))
    finally:
        for index in range(len(key)):
            key[index] = 0

    if len(seed) != SEED_LENGTH:
        raise VaultUnlockError("recovered seed has the wrong length")

    # The header DID is authenticated, but a file could still have been built
    # with a DID that does not belong to its seed. Refuse that outright.
    if did_key_from_seed(seed) != header_did:
        raise VaultUnlockError("recovered seed does not match the did in the header")

    return OpenedRecovery(
        seed=seed,
        did=header_did,
        created_at=created_at,
        kdf=RecoveryKdfMetadata(
            kdf=KDF_ARGON2ID,
            time_cost=time_cost,
            memory_kib=memory_kib,
            parallelism=parallelism,
        ),
    )


__all__ = [
    "MAX_RECOVERY_BYTES",
    "RECOVERY_FAILURE_MESSAGE",
    "RECOVERY_FORMAT",
    "RECOVERY_SUFFIX",
    "RECOVERY_VERSION",
    "OpenedRecovery",
    "RecoveryKdfMetadata",
    "aad_for_header",
    "create_recovery",
    "file_fingerprint",
    "open_recovery",
]
