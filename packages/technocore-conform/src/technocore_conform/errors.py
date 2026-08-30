"""Conformance errors.

Every failure here is fail-closed: a value is either provably conformant or it
is rejected. Nothing is coerced, repaired or guessed.

Error messages never contain key material. They may name the *kind* of defect
(wrong length, bad prefix) because that is derived from public structure, but
they never echo a seed or a private key.
"""

from __future__ import annotations


class ConformanceError(Exception):
    """Base class for every conformance failure."""


class InvalidSeedError(ConformanceError):
    """The seed is not exactly 32 bytes."""


class InvalidPublicKeyError(ConformanceError):
    """The public key is not exactly 32 bytes."""


class InvalidDidError(ConformanceError):
    """The did:key string is malformed, non-canonical or not Ed25519."""


__all__ = [
    "ConformanceError",
    "InvalidDidError",
    "InvalidPublicKeyError",
    "InvalidSeedError",
]
