"""Ed25519 ``did:key`` derivation and resolution.

Scope for Stage 2 is deliberately narrow: seed -> public key -> ``did:key``,
and the reverse resolution ``did:key`` -> public key. Sweep, canonical strings,
signing and verification belong to Stage 2B and are not implemented here.

The construction is specified in ``docs/protocol-contract.md`` and must agree
character-for-character with the pinned official reference
(``vendor/technocore-reference/scripts/sign.py``), which is used as a
differential test oracle. This module implements that specification
independently; no implementation line is copied from the Apache-2.0 reference.

    did:key = "did:key:" + "z" + base58btc(0xed 0x01 || public_key)

A note on the base58 encoder: it is a plain big-integer conversion with **no**
leading-zero handling. That is correct here and only here, because the payload
always starts with the multicodec byte 0xed, so it can never have a leading
zero byte. A general-purpose base58btc encoder would need an extra '1' per
leading zero byte; reusing this one outside this construction would be a bug.
"""

from __future__ import annotations

import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from technocore_conform.errors import (
    InvalidDidError,
    InvalidPublicKeyError,
    InvalidSeedError,
)

#: Ed25519 seed length in bytes. The protocol admits no other size.
SEED_LENGTH = 32

#: Raw Ed25519 public key length in bytes.
PUBLIC_KEY_LENGTH = 32

#: Unsigned varint for the multicodec code ``ed25519-pub`` (0xed).
MULTICODEC_ED25519_PUB = b"\xed\x01"

#: base58btc alphabet (Bitcoin ordering).
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

DID_KEY_PREFIX = "did:key:"

#: Multibase tag for base58btc.
MULTIBASE_BASE58BTC = "z"

#: 'z' + 47 base58 chars. 2 multicodec bytes + 32 key bytes always encode to
#: exactly 47 base58 characters, so the multibase segment is always 48 long.
MULTIBASE_LENGTH = 48

#: Every Ed25519 did:key begins with this fixed head.
DID_KEY_ED25519_PREFIX = f"{DID_KEY_PREFIX}{MULTIBASE_BASE58BTC}6Mk"

_DECODED_LENGTH = len(MULTICODEC_ED25519_PUB) + PUBLIC_KEY_LENGTH

_ALPHABET_INDEX = {char: index for index, char in enumerate(BASE58_ALPHABET)}


def _base58btc_encode(payload: bytes) -> str:
    """Big-integer base58 encoding.

    Valid only for payloads with no leading zero byte; see the module
    docstring. Callers in this module always pass a 0xed-prefixed payload.
    """
    number = int.from_bytes(payload, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    return encoded


def _base58btc_decode_fixed(text: str, *, length: int) -> bytes:
    """Decode base58 into exactly ``length`` bytes, or refuse."""
    number = 0
    for char in text:
        index = _ALPHABET_INDEX.get(char)
        if index is None:
            raise InvalidDidError("did contains a character outside the base58btc alphabet")
        number = number * 58 + index
    try:
        return number.to_bytes(length, "big")
    except OverflowError as exc:  # value too large for the fixed width
        raise InvalidDidError("did payload does not decode to the expected length") from exc


def public_key_from_seed(seed: bytes) -> bytes:
    """Derive the raw 32-byte Ed25519 public key from a 32-byte seed."""
    if not isinstance(seed, bytes | bytearray):
        raise InvalidSeedError("seed must be raw bytes")
    if len(seed) != SEED_LENGTH:
        raise InvalidSeedError(f"seed must be exactly {SEED_LENGTH} bytes")

    private_key = Ed25519PrivateKey.from_private_bytes(bytes(seed))
    public_key = private_key.public_key().public_bytes_raw()

    if len(public_key) != PUBLIC_KEY_LENGTH:  # pragma: no cover - library invariant
        raise InvalidPublicKeyError("derived public key has the wrong length")
    return public_key


def did_key_from_public_key(public_key: bytes) -> str:
    """Encode a raw Ed25519 public key as a ``did:key`` string."""
    if not isinstance(public_key, bytes | bytearray):
        raise InvalidPublicKeyError("public key must be raw bytes")
    if len(public_key) != PUBLIC_KEY_LENGTH:
        raise InvalidPublicKeyError(f"public key must be exactly {PUBLIC_KEY_LENGTH} bytes")

    multibase = MULTIBASE_BASE58BTC + _base58btc_encode(
        MULTICODEC_ED25519_PUB + bytes(public_key)
    )
    if len(multibase) != MULTIBASE_LENGTH:  # pragma: no cover - arithmetic invariant
        raise InvalidPublicKeyError("encoded did payload has an unexpected length")
    return DID_KEY_PREFIX + multibase


def did_key_from_seed(seed: bytes) -> str:
    """Convenience: seed -> public key -> ``did:key``."""
    return did_key_from_public_key(public_key_from_seed(seed))


def public_key_from_did_key(did: str) -> bytes:
    """Resolve a ``did:key`` string back to its raw Ed25519 public key.

    Fail-closed. A did is accepted only when every one of these holds:
    the ``did:key:`` prefix, the ``z`` multibase tag, exactly 48 multibase
    characters, an alphabet-clean body, the ``ed25519-pub`` multicodec, a
    34-byte decoding, and a **canonical** encoding - re-encoding the decoded
    bytes must reproduce the input exactly, which rejects values padded with
    leading '1' characters.
    """
    if not isinstance(did, str):
        raise InvalidDidError("did must be a string")
    if not did.startswith(DID_KEY_PREFIX):
        raise InvalidDidError("did must start with did:key:")

    multibase = did[len(DID_KEY_PREFIX) :]
    if len(multibase) != MULTIBASE_LENGTH:
        raise InvalidDidError("did payload has the wrong length")
    if not multibase.startswith(MULTIBASE_BASE58BTC):
        raise InvalidDidError("did payload must use the base58btc multibase tag")

    body = multibase[len(MULTIBASE_BASE58BTC) :]
    decoded = _base58btc_decode_fixed(body, length=_DECODED_LENGTH)

    if not decoded.startswith(MULTICODEC_ED25519_PUB):
        raise InvalidDidError("did is not an ed25519-pub key")

    public_key = decoded[len(MULTICODEC_ED25519_PUB) :]

    # Canonicality: exactly one encoding is accepted for a given key.
    if did_key_from_public_key(public_key) != did:
        raise InvalidDidError("did is not in canonical base58btc form")

    return public_key


def fingerprint_from_public_key(public_key: bytes) -> str:
    """A stable, **public** fingerprint of the identity.

    This is a Station convenience for humans comparing identities at a glance.
    It is not part of the Technocore protocol and is never used in a signature.
    Defined as the lowercase hex SHA-256 of the raw public key.
    """
    if len(public_key) != PUBLIC_KEY_LENGTH:
        raise InvalidPublicKeyError(f"public key must be exactly {PUBLIC_KEY_LENGTH} bytes")
    return hashlib.sha256(bytes(public_key)).hexdigest()


def short_fingerprint(fingerprint: str) -> str:
    """First 16 hex characters of the fingerprint, grouped for reading."""
    head = fingerprint[:16]
    return " ".join(head[index : index + 4] for index in range(0, len(head), 4))


__all__ = [
    "BASE58_ALPHABET",
    "DID_KEY_ED25519_PREFIX",
    "DID_KEY_PREFIX",
    "MULTIBASE_LENGTH",
    "MULTICODEC_ED25519_PUB",
    "PUBLIC_KEY_LENGTH",
    "SEED_LENGTH",
    "did_key_from_public_key",
    "did_key_from_seed",
    "fingerprint_from_public_key",
    "public_key_from_did_key",
    "public_key_from_seed",
    "short_fingerprint",
]
