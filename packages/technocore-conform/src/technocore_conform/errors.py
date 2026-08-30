"""Conformance errors.

Every failure here is fail-closed: a value is either provably conformant or it
is rejected. Nothing is coerced, repaired or guessed.

Error messages never contain key material, and they never echo the user's text
back. They may name the *kind* of defect and a measurement derived from it
(wrong length, character count, bad prefix) because that is public structure,
not content. A message that quoted the offending text would put user content
into every log line and traceback that touches it.

The hierarchy exists so a caller can distinguish causes that need different
responses:

* ``SweepError`` - the text cannot be stored as written.
* ``InvalidNameError`` / ``InvalidNonceError`` - a structural field is not in
  the protocol's allow-list.
* ``MalformedSignatureError`` vs ``SignatureMismatchError`` - "this is not a
  signature" is a different fact from "this signature does not verify", and
  conflating them hides tampering behind a parse error.
"""

from __future__ import annotations


class ConformanceError(Exception):
    """Base class for every conformance failure."""


# --- identity --------------------------------------------------------------


class InvalidSeedError(ConformanceError):
    """The seed is not exactly 32 bytes."""


class InvalidPublicKeyError(ConformanceError):
    """The public key is not exactly 32 bytes."""


class InvalidDidError(ConformanceError):
    """The did:key string is malformed, non-canonical or not Ed25519."""


# --- sweep -----------------------------------------------------------------


class SweepError(ConformanceError):
    """The text cannot pass the single-line sweep."""


class InvalidTextError(SweepError):
    """The value handed to the sweep is not a string."""


class EmptyTextError(SweepError):
    """Nothing visible survives the sweep.

    Deliberately distinct from ``TextTooLongError``: a caller whose text was
    entirely zero-width or bidi characters would otherwise resend the same
    bytes and get the same refusal.
    """


class TextTooLongError(SweepError):
    """The swept text is longer than the policy allows."""


# --- structural fields -----------------------------------------------------


class InvalidNameError(ConformanceError):
    """A room, namespace or key is outside the protocol allow-list."""


class InvalidNonceError(ConformanceError):
    """A nonce is not 1-19 ASCII digits."""


# --- signatures ------------------------------------------------------------


class SignatureError(ConformanceError):
    """Base class for signature failures."""


class MalformedSignatureError(SignatureError):
    """The signature is not canonical unpadded base64url of 64 bytes.

    Raised before any cryptography runs. Padding, whitespace, standard-base64
    ``+``/``/``, the wrong length and non-canonical slack bits all land here.
    """


class SignatureMismatchError(SignatureError):
    """The signature is well-formed but does not verify over this payload.

    This is the tamper signal: the DID, a structural field or the swept text
    is not what was signed.
    """


# --- self-test -------------------------------------------------------------


class SelfTestError(ConformanceError):
    """The runtime conformance self-test could not be completed.

    Raised when the vector bundle is missing or its digest does not match the
    pinned value. A self-test that cannot run is never a self-test that passed.
    """


__all__ = [
    "ConformanceError",
    "EmptyTextError",
    "InvalidDidError",
    "InvalidNameError",
    "InvalidNonceError",
    "InvalidPublicKeyError",
    "InvalidSeedError",
    "InvalidTextError",
    "MalformedSignatureError",
    "SelfTestError",
    "SignatureError",
    "SignatureMismatchError",
    "SweepError",
    "TextTooLongError",
]
