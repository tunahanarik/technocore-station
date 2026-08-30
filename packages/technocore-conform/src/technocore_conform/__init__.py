"""Technocore conformance package.

The whole protocol surface Station needs in order to write to Technocore
correctly, and nothing else:

    message:  <room>|<nonce>|<swept_text>
    note:     <namespace>|<key>|<nonce>|<swept_value>

signed with Ed25519 and encoded as 86 characters of unpadded base64url.

Boundary rules, enforced by tests as well as by the absence of imports below:

* This package imports **nothing** from ``station_api``, FastAPI, SQLAlchemy,
  SQLite or any Windows-specific module. It is plain, portable Python with a
  single runtime dependency, ``cryptography``.
* It implements the specification in ``docs/protocol-contract.md``. It does
  **not** copy implementation lines out of ``vendor/technocore-reference/``,
  which is Apache-2.0; this package is MIT.
* ``vendor/technocore-reference/`` is a differential test *oracle* only, used
  from ``tests/conformance/``. It is never imported from here, and the
  runtime self-test does not need it.

Importing this module has no side effects: nothing is read from disk, no
network call is made, and no self-test runs until ``run_self_test`` is called.

What this package deliberately does not do
------------------------------------------
It holds no state, so it allocates no nonces and enforces no monotonicity -
that is Stage 4, where a counter is reserved inside a transaction. It has no
HTTP client. And there is no public function that signs an arbitrary string:
signing takes a ``CanonicalPayload``, which can only be built through the
sweep.
"""

from __future__ import annotations

from technocore_conform._version import __version__
from technocore_conform.canonical import (
    MESSAGE_SEPARATORS,
    NOTE_SEPARATORS,
    SEPARATOR,
    CanonicalPayload,
    PayloadKind,
    canonical_message,
    canonical_message_from_swept,
    canonical_note,
    canonical_note_from_swept,
)
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
    EmptyTextError,
    InvalidDidError,
    InvalidNameError,
    InvalidNonceError,
    InvalidPublicKeyError,
    InvalidSeedError,
    InvalidTextError,
    MalformedSignatureError,
    SelfTestError,
    SignatureError,
    SignatureMismatchError,
    SweepError,
    TextTooLongError,
)
from technocore_conform.names import (
    MAX_NAME_LENGTH,
    MIN_NAME_LENGTH,
    NAME_PATTERN,
    is_valid_name,
    validate_name,
)
from technocore_conform.nonce import (
    MAX_NONCE_DIGITS,
    MIN_NONCE_DIGITS,
    NONCE_PATTERN,
    is_valid_nonce,
    validate_nonce,
)
from technocore_conform.selftest import (
    EXPECTED_BUNDLE_DIGEST,
    CheckResult,
    SelfTestResult,
    run_self_test,
)
from technocore_conform.signature import (
    SIGNATURE_BYTES,
    SIGNATURE_CHARS,
    SIGNATURE_PATTERN,
    decode_signature,
    encode_signature,
    is_canonical_signature,
    sign_payload,
    verify_payload,
)
from technocore_conform.sweep import (
    INVISIBLE_CATEGORIES,
    MAX_MESSAGE_CHARS,
    MAX_NOTE_VALUE_CHARS,
    MESSAGE_POLICY,
    NOTE_VALUE_POLICY,
    SweepPolicy,
    contains_invisible,
    is_swept,
    sweep,
    sweep_message,
    sweep_note_value,
)

#: Roadmap stage in which this package's protocol surface was implemented.
IMPLEMENTED_IN_STAGE = "2B"

#: Field separator in every canonical string. Kept as an alias of
#: ``canonical.SEPARATOR`` because Stage 1 published this name.
CANONICAL_SEPARATOR = SEPARATOR

__all__ = [
    "BASE58_ALPHABET",
    "CANONICAL_SEPARATOR",
    "DID_KEY_ED25519_PREFIX",
    "DID_KEY_PREFIX",
    "EXPECTED_BUNDLE_DIGEST",
    "IMPLEMENTED_IN_STAGE",
    "INVISIBLE_CATEGORIES",
    "MAX_MESSAGE_CHARS",
    "MAX_NAME_LENGTH",
    "MAX_NONCE_DIGITS",
    "MAX_NOTE_VALUE_CHARS",
    "MESSAGE_POLICY",
    "MESSAGE_SEPARATORS",
    "MIN_NAME_LENGTH",
    "MIN_NONCE_DIGITS",
    "MULTIBASE_LENGTH",
    "MULTICODEC_ED25519_PUB",
    "NAME_PATTERN",
    "NONCE_PATTERN",
    "NOTE_SEPARATORS",
    "NOTE_VALUE_POLICY",
    "PUBLIC_KEY_LENGTH",
    "SEED_LENGTH",
    "SEPARATOR",
    "SIGNATURE_BYTES",
    "SIGNATURE_CHARS",
    "SIGNATURE_PATTERN",
    "CanonicalPayload",
    "CheckResult",
    "ConformanceError",
    "EmptyTextError",
    "InvalidDidError",
    "InvalidNameError",
    "InvalidNonceError",
    "InvalidPublicKeyError",
    "InvalidSeedError",
    "InvalidTextError",
    "MalformedSignatureError",
    "PayloadKind",
    "SelfTestError",
    "SelfTestResult",
    "SignatureError",
    "SignatureMismatchError",
    "SweepError",
    "SweepPolicy",
    "TextTooLongError",
    "__version__",
    "canonical_message",
    "canonical_message_from_swept",
    "canonical_note",
    "canonical_note_from_swept",
    "contains_invisible",
    "decode_signature",
    "did_key_from_public_key",
    "did_key_from_seed",
    "encode_signature",
    "fingerprint_from_public_key",
    "is_canonical_signature",
    "is_swept",
    "is_valid_name",
    "is_valid_nonce",
    "public_key_from_did_key",
    "public_key_from_seed",
    "run_self_test",
    "short_fingerprint",
    "sign_payload",
    "sweep",
    "sweep_message",
    "sweep_note_value",
    "validate_name",
    "validate_nonce",
    "verify_payload",
]
