"""Identity lifecycle: create, protect, export recovery, restore-test, revoke.

This package owns the only code path that ever holds a seed in memory, and it
holds one for as short a time as possible. See docs/identity-lifecycle.md.
"""

from station_api.identity.service import (
    IdentityService,
    IdentityServiceError,
    IdentityState,
    IdentityView,
)
from station_api.identity.write_gate import (
    CheckState,
    GateCheck,
    WriteGateInput,
    WriteGateStatus,
    evaluate,
)

__all__ = [
    "CheckState",
    "GateCheck",
    "IdentityService",
    "IdentityServiceError",
    "IdentityState",
    "IdentityView",
    "WriteGateInput",
    "WriteGateStatus",
    "evaluate",
]
