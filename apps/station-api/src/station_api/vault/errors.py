"""Vault errors.

Two rules hold across this module:

1. No message ever contains seed bytes, a passphrase, or a vault path.
2. Wrong passphrase and tampered ciphertext raise the *same* error type with
   the *same* message. The caller cannot distinguish them, so neither can an
   attacker reading the HTTP response.

We do not claim constant-time behaviour: AEAD verification and Argon2id both
have data-dependent timing we do not control. The guarantee here is a single
external error contract, not timing equality.
"""

from __future__ import annotations


class VaultError(Exception):
    """Base class for vault failures."""


class VaultUnsupportedPlatformError(VaultError):
    """The platform has no supported secret store (non-Windows)."""


class VaultCapabilityError(VaultError):
    """DPAPI or the AEAD self-test is unavailable on this machine."""


class VaultNotFoundError(VaultError):
    """No vault envelope exists for the requested identity."""


class VaultAlreadyExistsError(VaultError):
    """An envelope already exists; refusing to overwrite."""


class VaultFormatError(VaultError):
    """The envelope is malformed, of an unknown version, or not strict."""


class VaultAclError(VaultError):
    """The restrictive ACL could not be applied or verified.

    This is fatal by design: a vault written with inherited permissions is
    not the vault we promised, so we never silently continue.
    """


class VaultUnlockError(VaultError):
    """The seed could not be recovered.

    Deliberately covers a wrong passphrase, a tampered inner ciphertext and a
    failed DPAPI unprotect alike.
    """


#: The single user-facing message for every unlock failure.
UNLOCK_FAILURE_MESSAGE = (
    "Secret acilamadi. Parola yanlis olabilir veya kasa dosyasi degistirilmis olabilir."
)

__all__ = [
    "UNLOCK_FAILURE_MESSAGE",
    "VaultAclError",
    "VaultAlreadyExistsError",
    "VaultCapabilityError",
    "VaultError",
    "VaultFormatError",
    "VaultNotFoundError",
    "VaultUnlockError",
    "VaultUnsupportedPlatformError",
]
