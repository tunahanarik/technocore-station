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
* writing is atomic - create empty, ACL, write, fsync, ``os.replace``, ACL
  again, and **fail-closed on either side of the rename**.

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

The fingerprint is the *only* handle a user has on "which key is stored", so
a fingerprint that disagreed with the file would break the whole pattern's
promise while looking healthy. This module therefore never leaves a file in a
state it did not fully write: a failure before the rename leaves the previous
envelope untouched, and a failure *after* the rename removes the new file
too, so the outcome is always either "the write happened" or "there is no
envelope" - never "an envelope nobody can name". ``OpenCodeService`` closes
the other half by dropping the metadata row *before* it writes and inserting
it again only once the file on disk is the one the row describes (SI-263).

What is deliberately **not** here
---------------------------------
There is no memory scrubbing. Everywhere else in this codebase a secret is
carried as a ``bytearray`` and zeroed in a ``finally`` - identity, vault,
signer, recovery and the CLI all do it - and this module does not, because a
provider key is a ``str`` from the moment Pydantic parses the request body
and a ``str`` cannot be overwritten in place. Converting only this layer to
``bytes`` would zero one copy while three live frames above it still held the
same immutable object, which is theatre rather than protection. So the honest
statement is the narrow one: the protections here are the DPAPI envelope, the
restrictive ACL and the redaction registry, and a crash dump or a swapped
page taken while a key is in flight is **not** covered by any of them. The
vault states the same limit for the seed it *does* scrub; this module has
strictly less to offer and says so rather than letting the neighbouring
docstrings imply otherwise.
"""

from __future__ import annotations

import hmac
import os
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from station_api.logging_setup import forget_secret, register_secret
from station_api.opencode.errors import (
    CredentialEnvelopeError,
    OpenCodeConfigurationError,
)
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
from station_api.vault.errors import (
    VaultAclError,
    VaultCapabilityError,
    VaultError,
    VaultUnsupportedPlatformError,
)

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

#: Serialises this process's own readers and writers of the single envelope
#: file. Windows refuses ``os.replace`` while another handle is open on the
#: target, so two threads storing and reading at once produced a
#: ``PermissionError`` - an ``OSError``, outside this package's hierarchy -
#: rather than a refusal in the connection's own vocabulary. The lock is
#: module level and not per instance on purpose: two ``ApiKeyEnvelope``
#: objects built for the same data directory are two writers of the same
#: file, and a per-instance lock would not know it.
_STORE_LOCK = threading.RLock()

#: ``O_BINARY`` exists only on Windows; elsewhere the flag is a no-op and the
#: DPAPI call refuses long before any file is opened.
_BINARY_FLAG: int = getattr(os, "O_BINARY", 0)

#: A read can still lose a race with a writer in another process, for the
#: length of one rename. Four attempts over ~60 ms is far longer than a
#: rename and far shorter than a user notices.
_READ_ATTEMPTS = 4
_READ_BACKOFF_SECONDS = 0.02


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


@contextmanager
def _vault_failures_named() -> Iterator[None]:
    """Keep every failure of this module inside the OpenCode hierarchy.

    The two most likely real faults here - DPAPI unavailable, and an ACL that
    could not be applied - are raised by :mod:`station_api.vault` as
    ``VaultError`` subclasses, which are **not** ``OpenCodeError`` subclasses
    and which no route catches. The unhandled-exception shield turned them
    into an opaque 500 carrying no key, so nothing leaked, but the package's
    own contract ("every failure here is fail-closed",
    :mod:`station_api.opencode.errors`) was false and the user was told
    nothing. Translating at this boundary is what makes the contract true: a
    machine that cannot hold the key at all is a *configuration* failure
    (503, and the message says DPAPI), and an envelope that cannot be read is
    a *credential* failure (400).

    The original is always attached with ``from``, so the traceback still
    names the vault error - it simply no longer escapes as one.
    """
    try:
        yield
    except (VaultCapabilityError, VaultUnsupportedPlatformError) as exc:
        raise OpenCodeConfigurationError(
            "Windows gizli deposu (DPAPI) bu makinede kullanilabilir degil; "
            "saglayici anahtari guvenle saklanamaz."
        ) from exc
    except VaultAclError as exc:
        raise OpenCodeConfigurationError(
            "Anahtar dosyasinin erisim izinleri uygulanamadi. Kisitlanmamis "
            "bir dosya birakmamak icin islem tamamlanmadi."
        ) from exc
    except VaultError as exc:
        raise CredentialEnvelopeError(
            "Saklanan anahtar zarfi acilamadi. Dosya degistirilmis olabilir "
            "veya baska bir Windows kullanicisi tarafindan yazilmis olabilir."
        ) from exc
    except OSError as exc:
        raise CredentialEnvelopeError(
            "Anahtar zarfi dosyasina erisilemedi."
        ) from exc


def _read_with_retry(target: Path) -> bytes:
    """Read the envelope, tolerating a rename in flight.

    In-process writers are serialised by :data:`_STORE_LOCK`; this covers the
    remaining case, a writer in another process, whose ``os.replace`` makes
    the target briefly unopenable on Windows. Bounded and short: a read that
    still fails after four attempts is reported, never retried forever and
    never answered with a stale value.
    """
    last: OSError | None = None
    for attempt in range(_READ_ATTEMPTS):
        try:
            return target.read_bytes()
        except OSError as exc:
            last = exc
            if attempt + 1 < _READ_ATTEMPTS:
                time.sleep(_READ_BACKOFF_SECONDS)
    raise CredentialEnvelopeError(
        "Anahtar zarfi su anda okunamiyor; dosya baska bir islem tarafindan "
        "kullaniliyor olabilir."
    ) from last


def _create_exclusive(directory: Path) -> tuple[int, Path]:
    """Create a fresh, empty, exclusively-owned temporary file.

    ``mkstemp`` would do, but it returns a file this module then writes to
    *before* it can name it for the ACL call. Creating the name ourselves
    with ``O_EXCL`` keeps the same collision safety and lets the ACL land
    while the file is still empty.
    """
    while True:
        candidate = directory / f"credential-{uuid.uuid4().hex}.tmp"
        try:
            handle = os.open(
                candidate,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | _BINARY_FLAG,
                0o600,
            )
        except FileExistsError:  # pragma: no cover - a 128-bit collision
            continue
        return handle, candidate


def _atomic_write(target: Path, payload: bytes) -> None:
    """Write via a temp file in the same directory, then rename.

    Two things here used to be claimed and not done. Both are now done rather
    than re-worded.

    **The ACL really does precede the bytes.** The old shape was
    ``mkstemp -> write -> fsync -> ACL``, and a traced run showed 537 bytes
    of envelope already on disk under an inherited DACL while the ACL call
    was still pending. The file is now created empty with
    ``O_CREAT | O_EXCL``, restricted while it is still zero bytes, and only
    then written. The window is closed instead of being described as closed.
    (Those bytes were DPAPI ciphertext throughout, so the impact was low; a
    docstring that was measurably false was the actual defect.)

    **A failure after the rename is fail-closed.** ``os.replace`` destroys
    the previous envelope. If the ACL that follows it fails, the old key is
    already gone, the new one is live and not known to be protected, and the
    caller sees an exception - the worst of the three possible outcomes. So
    the target is removed on that path: what remains is "no envelope", which
    ``describe()`` reports as *not configured* and a user can act on, rather
    than a stored credential nobody accounted for.

    The directory is restricted too. The file's own DACL is protected and
    therefore sufficient, so this is completeness rather than a trust
    boundary; the vault's equivalent gap is recorded as an accepted
    limitation instead of being pretended away (SI-266).

    The shape is ``DpapiVault._atomic_write``'s and
    ``AuditEnvelope._atomic_write``'s; the code is not shared because each
    resolves its own directory and must not write into another's.
    """
    directory = target.parent
    directory.mkdir(parents=True, exist_ok=True)
    windows_acl.restrict_to_current_user(directory)

    handle, temp_path = _create_exclusive(directory)
    replaced = False
    try:
        with os.fdopen(handle, "wb") as stream:
            # The file exists and is empty, so no byte of the envelope has
            # ever existed under the directory's inherited permissions.
            windows_acl.restrict_to_current_user(temp_path)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
        replaced = True
        windows_acl.restrict_to_current_user(target)
    except BaseException:
        if replaced:
            target.unlink(missing_ok=True)
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

        Either the file on disk is the key this returned a fingerprint for,
        or this raised. There is no third outcome; see :func:`_atomic_write`.
        """
        assert_storable(key)
        with _STORE_LOCK, _vault_failures_named():
            _atomic_write(self.file, _wrap(key.encode("utf-8")))
        return fingerprint(key)

    def load(self) -> str:
        """Open the envelope and return the key. Registers **nothing**.

        Prefer :meth:`opened`. This is the raw accessor: it does not put the
        value in the redaction registry, and a caller that forgets to is a
        caller holding a provider key that nothing would scrub from a log
        line. The previous wording here claimed ``OpenCodeService`` did the
        registering "around every use", which was not true of any code path -
        the service never called this method at all - and would have read as
        reassurance to whoever wired up the first real caller.
        """
        target = self.file
        if not target.is_file():
            raise CredentialEnvelopeError("no OpenCode credential is stored")
        with _STORE_LOCK, _vault_failures_named():
            plaintext = _unwrap(_read_with_retry(target))
        try:
            key = plaintext.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CredentialEnvelopeError(
                "stored OpenCode credential is not valid UTF-8"
            ) from exc
        if not MIN_KEY_LENGTH <= len(key) <= MAX_KEY_LENGTH:
            raise CredentialEnvelopeError(
                "stored OpenCode credential has an unexpected length"
            )
        return key

    @contextmanager
    def opened(self) -> Iterator[str]:
        """Yield the key with its redaction registration held for the block.

        ``register_secret`` and ``forget_secret`` are a pair a caller can get
        wrong in one direction that matters - forget to register - and this
        takes the choice away rather than documenting it. The length floor in
        :func:`assert_storable` and the re-check in :meth:`load` are what make
        the registration real: ``register_secret`` ignores anything under
        sixteen characters in silence, so a value this yields is always one
        the registry actually holds (ADR-0005 8).
        """
        key = self.load()
        register_secret(key)
        try:
            yield key
        finally:
            forget_secret(key)

    def delete(self) -> bool:
        """Remove the envelope. ``True`` when a file was actually removed."""
        with _STORE_LOCK, _vault_failures_named():
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
