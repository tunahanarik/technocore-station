"""Windows DPAPI secret vault.

The seed lives here and nowhere else: not in SQLite, not in an HTTP response,
not in a log. Nothing in this package may be imported by a model adapter or
any future LLM/agent surface - the secret boundary is the package boundary.
"""

from station_api.vault.errors import (
    UNLOCK_FAILURE_MESSAGE,
    VaultAclError,
    VaultAlreadyExistsError,
    VaultCapabilityError,
    VaultError,
    VaultFormatError,
    VaultNotFoundError,
    VaultUnlockError,
    VaultUnsupportedPlatformError,
)
from station_api.vault.paths import new_identity_id, validate_identity_id
from station_api.vault.service import (
    DEFAULT_PROTECTION,
    DpapiVault,
    ProtectionMode,
    VaultCapability,
)

__all__ = [
    "DEFAULT_PROTECTION",
    "UNLOCK_FAILURE_MESSAGE",
    "DpapiVault",
    "ProtectionMode",
    "VaultAclError",
    "VaultAlreadyExistsError",
    "VaultCapability",
    "VaultCapabilityError",
    "VaultError",
    "VaultFormatError",
    "VaultNotFoundError",
    "VaultUnlockError",
    "VaultUnsupportedPlatformError",
    "new_identity_id",
    "validate_identity_id",
]
