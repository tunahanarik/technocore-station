"""The signer boundary.

This module is the only place in Station where a seed and a payload meet. It
is deliberately thin: it opens the vault, hands the bytes to
``technocore_conform.sign_payload``, and scrubs. There is no policy here, no
gate check, no nonce allocation and no network - those live in
:mod:`station_api.compose.service`, which cannot reach a seed.

Two properties are structural rather than tested-for at each call site:

* **Only a canonical payload can be signed.** ``sign_payload`` takes a
  ``CanonicalPayload``, and a ``CanonicalPayload`` can only be built through
  the sweep. There is no public way to sign a free-form string, so signing
  raw text - a 403 from the server and a record that can never be
  re-verified against the stored bytes - is unrepresentable (IMP-211).
* **The key never leaves this call.** The seed is copied into a
  ``bytearray``, used, and zeroed in a ``finally``, following the same
  pattern as ``identity/service.py``. What is returned is an 86-character
  public signature and nothing else.

Honest limit: the scrub is best-effort. CPython may have copied the bytes
during allocation or garbage collection, and there is no portable way to
guarantee erasure. Stated here rather than implied away, exactly as
``vault/service.py`` states it.

The seam and why it exists
--------------------------
:class:`VaultMessageSigner` is what the application constructs. The
:class:`MessageSigner` protocol exists so the composer can be exercised on a
machine without DPAPI, in the same way ``IdentityService`` accepts a vault -
it is a test seam, not a configuration switch: nothing reads it from the
environment, and a security test asserts the application wires the vault
implementation.
"""

from __future__ import annotations

from typing import Protocol

from technocore_conform import CanonicalPayload, sign_payload

from station_api.vault import DpapiVault


class MessageSigner(Protocol):
    """Produce the wire signature for one canonical payload."""

    def sign(
        self, payload: CanonicalPayload, *, identity_id: str, passphrase: str | None
    ) -> str:
        """Return the 86-character unpadded base64url signature."""
        ...  # pragma: no cover - protocol declaration


class VaultMessageSigner:
    """Signs with a seed unlocked from the DPAPI vault for one call."""

    def __init__(self, vault: DpapiVault) -> None:
        self._vault = vault

    def sign(
        self, payload: CanonicalPayload, *, identity_id: str, passphrase: str | None
    ) -> str:
        seed = bytearray(self._vault.load(identity_id=identity_id, passphrase=passphrase))
        try:
            return sign_payload(payload, seed=bytes(seed))
        finally:
            for index in range(len(seed)):
                seed[index] = 0


__all__ = ["MessageSigner", "VaultMessageSigner"]
