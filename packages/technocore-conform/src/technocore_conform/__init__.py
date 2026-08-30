"""Technocore conformance package.

Stage 2 implements the identity half of the contract: seed -> public key ->
``did:key``, and the reverse resolution. Sweep, canonicalization, signing and
verification remain **unimplemented** and arrive in Stage 2B (PROJECT_STATUS.md).

Boundary rules, enforced by review and by the absence of imports below:

* This package imports **nothing** from ``station_api``, FastAPI, SQLAlchemy,
  SQLite or any Windows-specific module. It is plain, portable Python.
* It implements the specification in ``docs/protocol-contract.md``. It does
  **not** copy implementation lines out of ``vendor/technocore-reference/``,
  which is Apache-2.0; this package is MIT.
* ``vendor/technocore-reference/`` is a differential test *oracle* only, used
  from ``tests/conformance/``. It is never imported from here.

The contract this package will implement:

    message:  <room>|<nonce>|<swept_text>
    note:     <namespace>|<key>|<nonce>|<swept_value>

where the sweep replaces every character in Unicode category Cc, Cf, Cs, Co,
Zl or Zp with a single space and then trims the ends.
"""

from __future__ import annotations

from technocore_conform.did import (
    BASE58_ALPHABET,
    DID_KEY_ED25519_PREFIX,
    DID_KEY_PREFIX,
    MULTIBASE_LENGTH,
    MULTICODEC_ED25519_PUB,
    PUBLIC_KEY_LENGTH,
    SEED_LENGTH,
    did_key_from_public_key,
    did_key_from_seed,
    fingerprint_from_public_key,
    public_key_from_did_key,
    public_key_from_seed,
    short_fingerprint,
)
from technocore_conform.errors import (
    ConformanceError,
    InvalidDidError,
    InvalidPublicKeyError,
    InvalidSeedError,
)

__version__ = "0.2.0"

#: Roadmap stage that will implement the signing half of this package.
IMPLEMENTED_IN_STAGE = "2B"

#: Field separator in every canonical string.
CANONICAL_SEPARATOR = "|"

__all__ = [
    "BASE58_ALPHABET",
    "CANONICAL_SEPARATOR",
    "DID_KEY_ED25519_PREFIX",
    "DID_KEY_PREFIX",
    "IMPLEMENTED_IN_STAGE",
    "MULTIBASE_LENGTH",
    "MULTICODEC_ED25519_PUB",
    "PUBLIC_KEY_LENGTH",
    "SEED_LENGTH",
    "ConformanceError",
    "InvalidDidError",
    "InvalidPublicKeyError",
    "InvalidSeedError",
    "__version__",
    "did_key_from_public_key",
    "did_key_from_seed",
    "fingerprint_from_public_key",
    "public_key_from_did_key",
    "public_key_from_seed",
    "short_fingerprint",
]
