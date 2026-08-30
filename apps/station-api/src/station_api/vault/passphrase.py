"""Argon2id + ChaCha20-Poly1305 inner layer, and the passphrase policy.

Used in two places with the same primitives but different envelopes:

* the optional inner layer of the vault (``dpapi+passphrase``), and
* the ``.tcrec`` recovery file, which has no DPAPI layer at all.

The KDF policy is a value object rather than a set of constants so that slow
unit tests can inject a cheap policy. Production code paths always construct
``PRODUCTION_KDF_POLICY``; the accept-bounds on that policy reject a file made
with cheap test parameters, so a low-cost artefact can never be opened by a
production endpoint.
"""

from __future__ import annotations

import secrets
import unicodedata
from dataclasses import dataclass

from argon2.exceptions import Argon2Error
from argon2.low_level import Type as Argon2Type
from argon2.low_level import hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from station_api.vault.errors import VaultUnlockError

SALT_LENGTH = 16
NONCE_LENGTH = 12
KEY_LENGTH = 32

#: Minimum passphrase length in Unicode characters.
#:
#: Length is the only rule. Forced character-class composition pushes people
#: toward predictable patterns and does not raise real entropy.
MIN_PASSPHRASE_CHARS = 16

#: Upper bound on the UTF-8 encoding, so a huge passphrase cannot be used to
#: burn CPU inside Argon2id.
MAX_PASSPHRASE_BYTES = 1024

KDF_ARGON2ID = "argon2id"
AEAD_CHACHA20POLY1305 = "chacha20poly1305"


class PassphrasePolicyError(ValueError):
    """The passphrase does not satisfy the length policy."""


@dataclass(frozen=True)
class KdfPolicy:
    """Argon2id parameters plus the bounds accepted when reading a file.

    ``time_cost`` / ``memory_cost_kib`` / ``parallelism`` are used when
    deriving. The ``min_*`` / ``max_*`` fields validate the parameters found in
    an untrusted header **before** any derivation runs, so a hostile file
    cannot make us allocate gigabytes or spin for minutes.
    """

    time_cost: int = 3
    memory_cost_kib: int = 65536  # 64 MiB
    parallelism: int = 1
    hash_length: int = KEY_LENGTH

    min_time_cost: int = 3
    max_time_cost: int = 10
    min_memory_cost_kib: int = 65536
    max_memory_cost_kib: int = 262144  # 256 MiB ceiling
    min_parallelism: int = 1
    max_parallelism: int = 4

    def validate_untrusted(
        self, *, time_cost: int, memory_cost_kib: int, parallelism: int, hash_length: int
    ) -> None:
        """Refuse header parameters outside policy, before deriving anything."""
        if not self.min_time_cost <= time_cost <= self.max_time_cost:
            raise VaultUnlockError("kdf time cost is outside policy")
        if not self.min_memory_cost_kib <= memory_cost_kib <= self.max_memory_cost_kib:
            raise VaultUnlockError("kdf memory cost is outside policy")
        if not self.min_parallelism <= parallelism <= self.max_parallelism:
            raise VaultUnlockError("kdf parallelism is outside policy")
        if hash_length != KEY_LENGTH:
            raise VaultUnlockError("kdf output length is outside policy")


#: The only policy production code uses.
PRODUCTION_KDF_POLICY = KdfPolicy()


def normalise_passphrase(passphrase: str) -> bytes:
    """NFC-normalise then UTF-8 encode.

    Without normalisation the same typed passphrase can produce different
    bytes on different keyboards or platforms, which would make a recovery
    file unopenable on another machine.
    """
    return unicodedata.normalize("NFC", passphrase).encode("utf-8")


def validate_passphrase(passphrase: str) -> None:
    """Enforce the length policy. Never logs or echoes the value."""
    if not isinstance(passphrase, str):
        raise PassphrasePolicyError("Parola metin olmalidir.")
    if len(passphrase) < MIN_PASSPHRASE_CHARS:
        raise PassphrasePolicyError(f"Parola en az {MIN_PASSPHRASE_CHARS} karakter olmalidir.")
    if len(normalise_passphrase(passphrase)) > MAX_PASSPHRASE_BYTES:
        raise PassphrasePolicyError("Parola cok uzun.")


def derive_key(
    passphrase: str, salt: bytes, policy: KdfPolicy = PRODUCTION_KDF_POLICY
) -> bytes:
    """Argon2id key derivation.

    Argon2 rejects some parameter *combinations* that pass our individual
    bounds - notably ``memory_cost < 8 * parallelism``. A hostile file could
    otherwise crash the request with a library exception instead of failing
    closed, so any such error is mapped onto the single unlock failure.
    """
    try:
        return hash_secret_raw(
            secret=normalise_passphrase(passphrase),
            salt=salt,
            time_cost=policy.time_cost,
            memory_cost=policy.memory_cost_kib,
            parallelism=policy.parallelism,
            hash_len=policy.hash_length,
            type=Argon2Type.ID,
        )
    except Argon2Error as exc:
        raise VaultUnlockError("kdf parameters were rejected") from exc


def new_salt() -> bytes:
    return secrets.token_bytes(SALT_LENGTH)


def new_nonce() -> bytes:
    return secrets.token_bytes(NONCE_LENGTH)


def aead_encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    return ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)


def aead_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """Decrypt, mapping every AEAD failure onto the single unlock error."""
    try:
        return ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise VaultUnlockError("aead verification failed") from exc


def aead_self_test() -> bool:
    """Prove ChaCha20-Poly1305 is usable in this environment."""
    try:
        key = secrets.token_bytes(KEY_LENGTH)
        nonce = new_nonce()
        probe = b"technocore-station-aead-self-test"
        return aead_decrypt(key, nonce, aead_encrypt(key, nonce, probe, b"aad"), b"aad") == probe
    except Exception:
        return False


__all__ = [
    "AEAD_CHACHA20POLY1305",
    "KDF_ARGON2ID",
    "KEY_LENGTH",
    "MAX_PASSPHRASE_BYTES",
    "MIN_PASSPHRASE_CHARS",
    "NONCE_LENGTH",
    "PRODUCTION_KDF_POLICY",
    "SALT_LENGTH",
    "KdfPolicy",
    "PassphrasePolicyError",
    "aead_decrypt",
    "aead_encrypt",
    "aead_self_test",
    "derive_key",
    "new_nonce",
    "new_salt",
    "normalise_passphrase",
    "validate_passphrase",
]
