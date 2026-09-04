"""Task records, their nine states and the four fields a result is kept in.

New code only (ADR-0004 1). Nothing was moved into this package and nothing
existing imports from it except ``app.py``, which builds the service from the
instances it already owns.

The package has **no outbound surface**: no HTTP client, no socket, no
outbound registry, no signer and no vault. A security test walks its syntax
tree to keep it that way.
"""

from __future__ import annotations

from station_api.tasks.gate import (
    TaskCheck,
    TaskGateInput,
    TaskGateStatus,
    evaluate,
)
from station_api.tasks.reconciliation import (
    ReconciliationReport,
    UnfinishedWrite,
    scan_unfinished_writes,
)
from station_api.tasks.service import (
    TaskError,
    TaskService,
    TaskView,
    TransitionView,
)
from station_api.tasks.sources import (
    TaskSourceError,
    TaskSourceId,
    content_sha256,
    source_version_id,
)
from station_api.tasks.states import (
    ALLOWED_TRANSITIONS,
    INITIAL_STATE,
    PRODUCIBLE_STATES,
    STATE_DETAIL,
    UNPRODUCIBLE_STATES,
    TaskState,
    TransitionVerdict,
    validate_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "INITIAL_STATE",
    "PRODUCIBLE_STATES",
    "STATE_DETAIL",
    "UNPRODUCIBLE_STATES",
    "ReconciliationReport",
    "TaskCheck",
    "TaskError",
    "TaskGateInput",
    "TaskGateStatus",
    "TaskService",
    "TaskSourceError",
    "TaskSourceId",
    "TaskState",
    "TaskView",
    "TransitionVerdict",
    "TransitionView",
    "UnfinishedWrite",
    "content_sha256",
    "evaluate",
    "scan_unfinished_writes",
    "source_version_id",
    "validate_transition",
]
