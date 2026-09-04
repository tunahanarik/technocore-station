"""The provider key's DPAPI envelope.

Why neither existing store could be reused
------------------------------------------
:class:`~station_api.vault.service.DpapiVault` is identity-bound in five
places - a 32-hex identity id, the filename, the envelope field, the inner
AAD and a never-overwrite rule - and a provider key belongs to the
installation, not to a DID. :class:`~station_api.evidence.audit_envelope.
AuditEnvelope` is the right *shape* and the wrong *rule*, which is the whole
point of this module's docstring.

So this file copies the shape and states the difference (ADR-0005 7):

* the envelope is ``{format, version, kind, created_at, dpapi_blob}``, read
  back through :func:`~station_api.strict_json.require_exact_keys`;
* writing is atomic - mkstemp, fsync, ACL, ``os.replace``, ACL again.

**And the one deliberate inversion.** The audit chain's material is *never*
overwritten, because overwriting it silently invalidates every MAC already
written. A provider key is the opposite: a user must be able to replace a
rotated or mistyped key, and refusing would leave them with a broken
connection and no way out but deleting a file they cannot see. So
:meth:`ApiKeyEnvelope.store` **replaces**, on purpose, and a test pins that
it does. Anyone copying the audit envelope's shape a third time should copy
this sentence too, not the rule above it.

Domain separation
-----------------
:func:`station_api.vault.dpapi.protect` takes no entropy parameter - it uses
one fixed application constant - so a blob written by the vault and a blob
written here are interchangeable as far as DPAPI is concerned. The separation
is therefore in-band: the plaintext is prefixed with
:data:`DOMAIN_SEPARATION_LABEL` and the prefix is required on load, so an
audit-material blob dropped into this file is rejected rather than read as a
key. It is a fixed, public constant and not a secret.

What reaches the database
-------------------------
Nothing but the relative path, two timestamps and a fingerprint - an HMAC of
a fixed public label under the key, which names the key without revealing it
(the ``secret_metadata`` pattern). There is no endpoint anywhere that returns
or copies the stored key.
"""

from __future__ import annotations

import hmac
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from station_api.opencode.errors import CredentialEnvelopeError
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
from station_api.vault import dpapi, windows_acl

CREDENTIAL_DIRNAME = "opencode"
CREDENTIAL_FORMAT_DIRNAME = "v1"

#: Named for what the connection does, not for what it holds, so a directory
#: listing does not advertise a target.
CREDENTIAL_FILENAME = "provider-credential.json"

ENVELOPE_FORMAT = "technocore-station.opencode"
ENVELOPE_VERSION = 1
ENVELOPE_KIND = "provider-credential"

#: An envelope is tiny; anything larger is not ours.
MAX_ENVELOPE_BYTES = 64 * 1024

#: Fixed, public domain-separation prefix. NOT a secret: it only stops a blob
#: written for another purpose being unwrapped as a provider key.
DOMAIN_SEPARATION_LABEL = b"technocore-station/opencode/v1/credential\x00"

#: A fixed, public label. Hashing it under the key yields a value that
#: identifies the key without revealing it.
FINGERPRINT_LABEL = b"technocore-station/opencode/v1/fingerprint"

#: The single row in ``opencode_credential_metadata``.
CREDENTIAL_ID = "opencode-go-v1"

#: Bounds on an accepted key. The **lower** bound is load-bearing twice over:
#: it keeps an obviously-empty paste from being stored, and it is the length
#: at which :func:`station_api.logging_setup.register_secret` starts working
#: at all - that function silently ignores anything shorter than 16
#: characters, so a shorter key would be stored *and never redacted*
#: (ADR-0005 8). Refusing it is the only way to keep the redaction promise
#: true for everything we hold.
MIN_KEY_LENGTH = 20
MAX_KEY_LENGTH = 512

_ENVELOPE_KEYS = frozenset({"format", "version", "kind", "created_at", "dpapi_blob"})


@dataclass(frozen=True, slots=True)
class StoredCredential:
    """What the *metadata* knows. Never the key."""

    fingerprint: str
    envelope_relpath: str
    created_at: datetime


def credential_dir(data_dir: Path) -> Path:
    return data_dir / CREDENTIAL_DIRNAME / CREDENTIAL_FORMAT_DIRNAME


def credential_path(data_dir: Path) -> Path:
    return credential_dir(data_dir) / CREDENTIAL_FILENAME


def relative_path(data_dir: Path, target: Path) -> str:
    """The path recorded in the database: relative, never absolute (SI-36)."""
    try:
        return target.relative_to(data_dir).as_posix()
    except ValueError:  # pragma: no cover - both are built from data_dir
        return target.name


def fingerprint(key: str) -> str:
    """A public identifier for a key."""
    return hmac.new(key.encode("utf-8"), FINGERPRINT_LABEL, sha256).hexdigest()


def assert_storable(key: str) -> None:
    """Refuse a key we could not hold safely.

    The length floor is a redaction precondition, not a format check: nothing
    here validates the *shape* of a provider key, because a shape check that
    passed would look like a verification and this build cannot verify a key
    at all (ADR-0005 4).
    """
    if len(key) < MIN_KEY_LENGTH:
        raise CredentialEnvelopeError(
            "Anahtar cok kisa. En az "
            f"{MIN_KEY_LENGTH} karakter olmali; daha kisa bir deger log "
            "redaksiyonuna kaydedilemez."
        )
    if len(key) > MAX_KEY_LENGTH:
        raise CredentialEnvelopeError(
            f"Anahtar cok uzun. En fazla {MAX_KEY_LENGTH} karakter kabul edilir."
        )
    if key.strip() != key or not key.strip():
        raise CredentialEnvelopeError(
            "Anahtarin basinda veya sonunda bosluk var. Kirpilmis hali "
            "kaydedilmez; dogru degeri yapistirin."
        )


def _atomic_write(target: Path, payload: bytes) -> None:
    """Write via a temp file in the same directory, then rename.

    The ACL is applied to the temporary file *before* the rename, so the
    envelope is never briefly readable under inherited permissions, and again
    afterwards because a rename can carry a different security descriptor
    depending on the volume. The shape is ``DpapiVault._atomic_write``'s and
    ``AuditEnvelope._atomic_write``'s; the code is not shared because each
    resolves its own directory and must not write into another's.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        windows_acl.restrict_to_current_user(temp_path)
        os.replace(temp_path, target)
        windows_acl.restrict_to_current_user(target)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _wrap(payload: bytes) -> bytes:
    return canonical_json_bytes(
        {
            "format": ENVELOPE_FORMAT,
            "version": ENVELOPE_VERSION,
            "kind": ENVELOPE_KIND,
            "created_at": datetime.now(UTC).isoformat(),
            "dpapi_blob": b64u_encode(
                dpapi.protect(DOMAIN_SEPARATION_LABEL + payload)
            ),
        }
    )


def _unwrap(raw: bytes) -> bytes:
    try:
        envelope: dict[str, Any] = loads_strict(raw, max_bytes=MAX_ENVELOPE_BYTES)
        require_exact_keys(envelope, _ENVELOPE_KEYS)
        if require_str(envelope, "format") != ENVELOPE_FORMAT:
            raise CredentialEnvelopeError("unexpected credential envelope format")
        if require_int(envelope, "version") != ENVELOPE_VERSION:
            raise CredentialEnvelopeError("unsupported credential envelope version")
        if require_str(envelope, "kind") != ENVELOPE_KIND:
            raise CredentialEnvelopeError("credential envelope is of the wrong kind")
        require_str(envelope, "created_at")
        blob = b64u_decode(require_str(envelope, "dpapi_blob"))
    except StrictJsonError as exc:
        raise CredentialEnvelopeError("credential envelope is malformed") from exc

    plaintext = dpapi.unprotect(blob)
    if not plaintext.startswith(DOMAIN_SEPARATION_LABEL):
        # A blob that unprotects but is not ours - an audit material file
        # copied over this one, say. Reading it as a key would leak whatever
        # it is into an outbound Authorization header.
        raise CredentialEnvelopeError(
            "credential envelope does not carry the OpenCode domain label"
        )
    return plaintext[len(DOMAIN_SEPARATION_LABEL) :]


class ApiKeyEnvelope:
    """Owns the one file the OpenCode connection depends on.

    Versioned by construction: the envelope carries ``version`` and ``kind``
    and both are checked on read, so a future format cannot be mistaken for
    this one.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    @property
    def file(self) -> Path:
        return credential_path(self._data_dir)

    def relpath(self) -> str:
        return relative_path(self._data_dir, self.file)

    def exists(self) -> bool:
        return self.file.is_file()

    def store(self, key: str) -> str:
        """Write the key, **replacing** any existing one. Returns a fingerprint.

        The replacement is the deliberate difference from
        :meth:`~station_api.evidence.audit_envelope.AuditEnvelope.
        create_material`, which refuses precisely this. See the module
        docstring: a user rotating a key must not have to delete a file they
        cannot see.
        """
        assert_storable(key)
        _atomic_write(self.file, _wrap(key.encode("utf-8")))
        return fingerprint(key)

    def load(self) -> str:
        """Open the envelope and return the key.

        The caller is responsible for registering it for redaction and
        forgetting it afterwards; :class:`~station_api.opencode.service.
        OpenCodeService` does both around every use.
        """
        target = self.file
        if not target.is_file():
            raise CredentialEnvelopeError("no OpenCode credential is stored")
        key = _unwrap(target.read_bytes()).decode("utf-8")
        if not MIN_KEY_LENGTH <= len(key) <= MAX_KEY_LENGTH:
            raise CredentialEnvelopeError(
                "stored OpenCode credential has an unexpected length"
            )
        return key

    def delete(self) -> bool:
        """Remove the envelope. ``True`` when a file was actually removed."""
        target = self.file
        if not target.is_file():
            return False
        target.unlink()
        return True


__all__ = [
    "CREDENTIAL_DIRNAME",
    "CREDENTIAL_FILENAME",
    "CREDENTIAL_FORMAT_DIRNAME",
    "CREDENTIAL_ID",
    "DOMAIN_SEPARATION_LABEL",
    "ENVELOPE_FORMAT",
    "ENVELOPE_KIND",
    "ENVELOPE_VERSION",
    "FINGERPRINT_LABEL",
    "MAX_ENVELOPE_BYTES",
    "MAX_KEY_LENGTH",
    "MIN_KEY_LENGTH",
    "ApiKeyEnvelope",
    "StoredCredential",
    "assert_storable",
    "credential_dir",
    "credential_path",
    "fingerprint",
    "relative_path",
]
