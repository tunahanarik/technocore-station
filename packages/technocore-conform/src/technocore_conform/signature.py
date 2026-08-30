"""Ed25519 signing and verification over canonical payloads.

Encoding contract, from the pinned reference:

* Raw signature: **64 bytes**.
* Wire form: **unpadded base64url**, exactly **86 characters**.
* The 86th character is always one of ``A``, ``Q``, ``g`` or ``w``.

That last rule is not arbitrary. 86 base64 characters carry 516 bits, but a
signature is only 512, so the final character's low four bits are slack and
must be zero. Exactly four alphabet characters have that property. A decoder
that ignores those bits would accept 16 different spellings of the same
signature; this module accepts one.

Seed handling
-------------
``sign_payload`` takes the seed, uses it, and returns. No object in this
module stores a seed, caches a private key, or puts either in a ``repr``. The
seed belongs to the caller - in Station's case, to the DPAPI vault, which
holds it for the duration of one operation.

There is deliberately no public function that signs an arbitrary string. The
only way in is a ``CanonicalPayload``, which can only be built through the
sweep. Signing raw text is a 403 from the server and a silent correctness bug
here; making it unreachable is cheaper than testing for it everywhere.
"""

from __future__ import annotations

import base64
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from technocore_conform.canonical import CanonicalPayload
from technocore_conform.did import SEED_LENGTH, public_key_from_did_key
from technocore_conform.errors import (
    InvalidSeedError,
    MalformedSignatureError,
    SignatureMismatchError,
)

#: Raw Ed25519 signature length in bytes.
SIGNATURE_BYTES = 64

#: Length of the unpadded base64url encoding of 64 bytes.
SIGNATURE_CHARS = 86

#: Canonical wire form. The final class is the four characters whose low four
#: bits are zero, which is what makes the encoding of 64 bytes unique.
SIGNATURE_PATTERN = r"[A-Za-z0-9_-]{85}[AQgw]"

_SIGNATURE_RE = re.compile(SIGNATURE_PATTERN)

#: Padding that turns 86 base64url characters back into a decodable block.
_DECODE_PADDING = "=="


def encode_signature(raw: bytes) -> str:
    """Encode a 64-byte signature as canonical unpadded base64url."""
    if not isinstance(raw, bytes | bytearray):
        raise MalformedSignatureError("signature must be raw bytes")
    if len(raw) != SIGNATURE_BYTES:
        raise MalformedSignatureError(
            f"signature must be exactly {SIGNATURE_BYTES} bytes, got {len(raw)}"
        )
    return base64.urlsafe_b64encode(bytes(raw)).decode("ascii").rstrip("=")


def is_canonical_signature(signature: object) -> bool:
    """Whether ``signature`` is in the one accepted wire form."""
    return (
        isinstance(signature, str)
        and len(signature) == SIGNATURE_CHARS
        and _SIGNATURE_RE.fullmatch(signature) is not None
    )


def decode_signature(signature: str) -> bytes:
    """Decode a canonical signature, or refuse.

    Refuses padding, whitespace, standard-base64 ``+``/``/``, the wrong
    length, and non-canonical slack bits. The re-encode check at the end is
    redundant against the pattern above and kept anyway: it is the property
    that actually matters (exactly one spelling per signature), stated
    directly rather than inferred from a regex.
    """
    if not isinstance(signature, str):
        raise MalformedSignatureError("signature must be a string")
    if len(signature) != SIGNATURE_CHARS:
        raise MalformedSignatureError(
            f"signature must be exactly {SIGNATURE_CHARS} characters, got {len(signature)}"
        )
    if _SIGNATURE_RE.fullmatch(signature) is None:
        raise MalformedSignatureError(
            "signature must be unpadded base64url and end with a canonical character"
        )

    raw = base64.urlsafe_b64decode(signature + _DECODE_PADDING)
    if len(raw) != SIGNATURE_BYTES:  # pragma: no cover - length is fixed above
        raise MalformedSignatureError("signature does not decode to 64 bytes")
    if encode_signature(raw) != signature:  # pragma: no cover - pattern covers this
        raise MalformedSignatureError("signature is not in canonical base64url form")
    return raw


def _validate_seed(seed: bytes) -> bytes:
    """Exactly 32 raw bytes. No string seeds, no passphrase derivation."""
    if not isinstance(seed, bytes | bytearray):
        raise InvalidSeedError("seed must be raw bytes")
    if len(seed) != SEED_LENGTH:
        raise InvalidSeedError(f"seed must be exactly {SEED_LENGTH} bytes")
    return bytes(seed)


def sign_payload(payload: CanonicalPayload, *, seed: bytes) -> str:
    """Sign a canonical payload, returning the 86-character wire signature.

    The private key is constructed, used and dropped within this call.
    """
    if not isinstance(payload, CanonicalPayload):
        raise TypeError("sign_payload requires a CanonicalPayload")

    private_key = Ed25519PrivateKey.from_private_bytes(_validate_seed(seed))
    return encode_signature(private_key.sign(payload.canonical_bytes))


def verify_payload(payload: CanonicalPayload, *, did: str, signature: str) -> None:
    """Verify a signature over a payload. Returns None, or raises.

    Three failure modes stay distinguishable, because they mean different
    things: ``InvalidDidError`` (the DID is not a canonical Ed25519 did:key),
    ``MalformedSignatureError`` (that is not a signature), and
    ``SignatureMismatchError`` (well-formed, but not over these bytes - the
    tamper signal).
    """
    if not isinstance(payload, CanonicalPayload):
        raise TypeError("verify_payload requires a CanonicalPayload")

    public_key = Ed25519PublicKey.from_public_bytes(public_key_from_did_key(did))
    raw_signature = decode_signature(signature)

    try:
        public_key.verify(raw_signature, payload.canonical_bytes)
    except InvalidSignature as exc:
        raise SignatureMismatchError(
            "signature does not verify over this canonical payload"
        ) from exc


__all__ = [
    "SIGNATURE_BYTES",
    "SIGNATURE_CHARS",
    "SIGNATURE_PATTERN",
    "decode_signature",
    "encode_signature",
    "is_canonical_signature",
    "sign_payload",
    "verify_payload",
]
