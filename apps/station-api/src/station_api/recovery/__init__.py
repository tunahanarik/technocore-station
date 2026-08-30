"""Portable ``.tcrec`` recovery files.

Independent of DPAPI by design: a recovery file must open on a clean profile
or a different Windows account, given only the recovery passphrase.
"""

from station_api.recovery.format import (
    MAX_RECOVERY_BYTES,
    RECOVERY_FAILURE_MESSAGE,
    RECOVERY_FORMAT,
    RECOVERY_SUFFIX,
    RECOVERY_VERSION,
    OpenedRecovery,
    RecoveryKdfMetadata,
    aad_for_header,
    create_recovery,
    file_fingerprint,
    open_recovery,
)

__all__ = [
    "MAX_RECOVERY_BYTES",
    "RECOVERY_FAILURE_MESSAGE",
    "RECOVERY_FORMAT",
    "RECOVERY_SUFFIX",
    "RECOVERY_VERSION",
    "OpenedRecovery",
    "RecoveryKdfMetadata",
    "aad_for_header",
    "create_recovery",
    "file_fingerprint",
    "open_recovery",
]
