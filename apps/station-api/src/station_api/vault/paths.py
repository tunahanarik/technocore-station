"""Vault filesystem layout.

The vault lives under the application data directory, in a **versioned**
subdirectory so a future envelope format can migrate without ambiguity:

    <data_dir>/vault/v1/<identity_id>.vault.json

Two rules matter here:

* The path is never derived from HTTP input or from a frontend value. It is
  built from the application data directory plus an application-generated
  identity id.
* The identity id is validated as a 32-character lowercase hex UUID before it
  is placed in a path, so it cannot carry a separator or a traversal segment.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from station_api.vault.errors import VaultFormatError

VAULT_DIRNAME = "vault"
VAULT_FORMAT_DIRNAME = "v1"
VAULT_SUFFIX = ".vault.json"

_IDENTITY_ID_RE = re.compile(r"\A[0-9a-f]{32}\Z")


def new_identity_id() -> str:
    """Generate an application-owned identity id (32 lowercase hex chars)."""
    return uuid.uuid4().hex


def validate_identity_id(identity_id: str) -> str:
    """Refuse anything that is not a bare 32-char lowercase hex id."""
    if not isinstance(identity_id, str) or not _IDENTITY_ID_RE.match(identity_id):
        raise VaultFormatError("identity id is not a valid application identifier")
    return identity_id


def vault_dir(data_dir: Path) -> Path:
    return data_dir / VAULT_DIRNAME / VAULT_FORMAT_DIRNAME


def vault_file(data_dir: Path, identity_id: str) -> Path:
    return vault_dir(data_dir) / f"{validate_identity_id(identity_id)}{VAULT_SUFFIX}"


__all__ = [
    "VAULT_DIRNAME",
    "VAULT_FORMAT_DIRNAME",
    "VAULT_SUFFIX",
    "new_identity_id",
    "validate_identity_id",
    "vault_dir",
    "vault_file",
]
