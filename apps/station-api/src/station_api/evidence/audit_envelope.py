"""The audit chain's DPAPI envelopes: MAC material, and the chain head.

Why :class:`~station_api.vault.service.DpapiVault` could not be reused
---------------------------------------------------------------------
It is identity-bound in five places, and every one of them is load-bearing
for the thing it was written for and wrong for this one (ADR-0003 6):

* it demands a 32-hex ``identity_id`` and refuses anything else;
* the filename *is* that identity id;
* the envelope carries the identity id and re-checks it on load;
* the inner AAD binds the ciphertext to that identity;
* ``store()`` never overwrites, which is deliberate protection against
  destroying a seed and is the exact opposite of what a chain head needs -
  the head is rewritten on every append.

The audit chain belongs to the installation, not to an identity, and it
outlives any single identity: revoking a key must not orphan the record of
what that key did. So this module writes its own envelopes and reuses only
the pieces that are genuinely generic - :mod:`station_api.vault.dpapi`'s
``protect``/``unprotect``, :func:`~station_api.vault.windows_acl.
restrict_to_current_user`, :mod:`station_api.strict_json`, and the
*shape* of ``DpapiVault._atomic_write`` (temp file, fsync, ACL, ``os.replace``,
ACL again).

What is not here
----------------
No passphrase layer. The chain's MAC material protects against an offline
change made by someone who does not have it; an attacker running as this
Windows user has DPAPI and would have the passphrase prompt too, so a second
layer would buy a sentence rather than a property (SECURITY.md 7). The vault
that holds a *seed* has one, because the seed is worth an attacker's time in
a way a detection MAC is not.

The material itself enters no table. ``audit_chain_metadata`` holds the
relative path, the creation time and a fingerprint - an HMAC of a fixed,
public label under the material, so it names the material without revealing
it (the ``secret_metadata`` pattern).
"""

from __future__ import annotations

import hmac
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

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

AUDIT_DIRNAME = "audit"
AUDIT_FORMAT_DIRNAME = "v1"

#: The MAC material's envelope. Named for what the chain does, not for what
#: it holds, so a directory listing does not advertise a target.
MATERIAL_FILENAME = "chain-material.json"

#: The chain head: the last MAC and how many links there are.
HEAD_FILENAME = "chain-head.json"

ENVELOPE_FORMAT = "technocore-station.audit"
ENVELOPE_VERSION = 1

#: An envelope is tiny; anything larger is not ours.
MAX_ENVELOPE_BYTES = 64 * 1024

#: 32 bytes, the SHA-256 block-size-appropriate length for an HMAC-SHA256 MAC.
MATERIAL_LENGTH = 32

#: A fixed, public label. Hashing it under the material yields a value that
#: identifies the material without revealing it.
FINGERPRINT_LABEL = b"technocore-station/audit/v1/fingerprint"

#: The single row in ``audit_chain_metadata``.
CHAIN_ID = "audit-chain-v1"

_ENVELOPE_KEYS = frozenset({"format", "version", "kind", "created_at", "dpapi_blob"})
_HEAD_KEYS = frozenset({"count", "last_mac", "updated_at"})


class AuditEnvelopeError(Exception):
    """An audit envelope could not be written or read."""


@dataclass(frozen=True, slots=True)
class ChainHead:
    """What the chain looked like the last time an append committed."""

    count: int
    last_mac: str
    updated_at: str


def audit_dir(data_dir: Path) -> Path:
    return data_dir / AUDIT_DIRNAME / AUDIT_FORMAT_DIRNAME


def material_path(data_dir: Path) -> Path:
    return audit_dir(data_dir) / MATERIAL_FILENAME


def head_path(data_dir: Path) -> Path:
    return audit_dir(data_dir) / HEAD_FILENAME


def relative_path(data_dir: Path, target: Path) -> str:
    """The path recorded in the database: relative, never absolute (SI-36)."""
    try:
        return target.relative_to(data_dir).as_posix()
    except ValueError:  # pragma: no cover - both are built from data_dir
        return target.name


def fingerprint(material: bytes) -> str:
    """A public identifier for the MAC material."""
    return hmac.new(material, FINGERPRINT_LABEL, sha256).hexdigest()


def _atomic_write(target: Path, payload: bytes) -> None:
    """Write via a temp file in the same directory, then rename.

    The ACL is applied to the temporary file before the *rename* and again
    afterwards, because a rename can carry a different security descriptor
    depending on the volume.

    Stated precisely, because the neighbouring copy of this sentence was
    measurably wrong: the order is write, fsync, ACL, rename, ACL, so the
    payload does exist on disk under the directory's inherited permissions
    for the moment between the write and the ACL call. What is protected in
    that moment is the DPAPI ciphertext, not the material.
    :func:`station_api.opencode.credential_store._atomic_write` closes the
    window by creating the file empty and restricting it first; this one is
    left as it is because the audit material's envelope is never rewritten
    and changing its write path would touch the one file the chain's
    verification depends on. The gap is recorded rather than described away
    (SI-265).

    The shape is ``DpapiVault._atomic_write``'s; the code is not shared
    because that method resolves the vault's own directory and this one must
    not write there.
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


def _wrap(kind: str, payload: bytes) -> bytes:
    return canonical_json_bytes(
        {
            "format": ENVELOPE_FORMAT,
            "version": ENVELOPE_VERSION,
            "kind": kind,
            "created_at": datetime.now(UTC).isoformat(),
            "dpapi_blob": b64u_encode(dpapi.protect(payload)),
        }
    )


def _unwrap(raw: bytes, *, kind: str) -> bytes:
    try:
        envelope: dict[str, Any] = loads_strict(raw, max_bytes=MAX_ENVELOPE_BYTES)
        require_exact_keys(envelope, _ENVELOPE_KEYS)
        if require_str(envelope, "format") != ENVELOPE_FORMAT:
            raise AuditEnvelopeError("unexpected audit envelope format")
        if require_int(envelope, "version") != ENVELOPE_VERSION:
            raise AuditEnvelopeError("unsupported audit envelope version")
        if require_str(envelope, "kind") != kind:
            raise AuditEnvelopeError("audit envelope is of the wrong kind")
        require_str(envelope, "created_at")
        blob = b64u_decode(require_str(envelope, "dpapi_blob"))
    except StrictJsonError as exc:
        raise AuditEnvelopeError("audit envelope is malformed") from exc
    return dpapi.unprotect(blob)


class AuditEnvelope:
    """Owns the two files the audit chain depends on.

    Versioned by construction: the envelope carries ``version`` and ``kind``,
    and both are checked on read, so a future format cannot be mistaken for
    this one and this one cannot be mistaken for a head when it is material.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    # --- MAC material ------------------------------------------------------

    @property
    def material_file(self) -> Path:
        return material_path(self._data_dir)

    @property
    def head_file(self) -> Path:
        return head_path(self._data_dir)

    def material_relpath(self) -> str:
        return relative_path(self._data_dir, self.material_file)

    def exists(self) -> bool:
        return self.material_file.is_file()

    def create_material(self) -> bytes:
        """Generate and store new MAC material. Never overwrites.

        Overwriting would silently invalidate every MAC already written,
        which reads afterwards as "the whole chain is broken" - the loudest
        possible way to lose the ability to say anything at all.
        """
        if self.exists():
            raise AuditEnvelopeError("audit chain material already exists")
        material = secrets.token_bytes(MATERIAL_LENGTH)
        _atomic_write(self.material_file, _wrap("material", material))
        return material

    def load_material(self) -> bytes:
        """Open the envelope and return the MAC material."""
        target = self.material_file
        if not target.is_file():
            raise AuditEnvelopeError("no audit chain material exists")
        material = _unwrap(target.read_bytes(), kind="material")
        if len(material) != MATERIAL_LENGTH:
            raise AuditEnvelopeError("audit chain material has an unexpected length")
        return material

    def ensure_material(self) -> bytes:
        """Load the material, creating it on first use."""
        if self.exists():
            return self.load_material()
        return self.create_material()

    # --- chain head --------------------------------------------------------

    def read_head(self) -> ChainHead | None:
        """The last committed head, or ``None`` when there is none yet."""
        target = self.head_file
        if not target.is_file():
            return None
        payload = _unwrap(target.read_bytes(), kind="head")
        try:
            document: dict[str, Any] = loads_strict(
                payload, max_bytes=MAX_ENVELOPE_BYTES
            )
            require_exact_keys(document, _HEAD_KEYS)
            head = ChainHead(
                count=require_int(document, "count"),
                last_mac=require_str(document, "last_mac"),
                updated_at=require_str(document, "updated_at"),
            )
        except StrictJsonError as exc:
            raise AuditEnvelopeError("audit chain head is malformed") from exc
        return head

    def write_head(self, head: ChainHead) -> None:
        """Replace the head.

        Called inside the same transaction block as the append it describes.
        That is a *boundary*, not a two-phase commit - a file and a SQLite
        transaction cannot commit atomically - and the honest consequence is
        written down: a crash in the window leaves the head one link behind
        or one link ahead, and :meth:`AuditChain.verify` reports which,
        separately from a broken link. Calling either of those "tampering"
        would be the kind of false alarm that gets a check switched off.
        """
        payload = canonical_json_bytes(
            {
                "count": head.count,
                "last_mac": head.last_mac,
                "updated_at": head.updated_at,
            }
        )
        _atomic_write(self.head_file, _wrap("head", payload))


__all__ = [
    "AUDIT_DIRNAME",
    "AUDIT_FORMAT_DIRNAME",
    "CHAIN_ID",
    "ENVELOPE_FORMAT",
    "ENVELOPE_VERSION",
    "FINGERPRINT_LABEL",
    "HEAD_FILENAME",
    "MATERIAL_FILENAME",
    "MATERIAL_LENGTH",
    "MAX_ENVELOPE_BYTES",
    "AuditEnvelope",
    "AuditEnvelopeError",
    "ChainHead",
    "audit_dir",
    "fingerprint",
    "head_path",
    "material_path",
    "relative_path",
]
