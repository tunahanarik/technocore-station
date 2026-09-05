"""Package H2: the agent working environment and the Activity Desk.

Seven modules, and the split is the argument:

``errors``      one refusal type per boundary, each carrying a reason.
``isolation``   the measured isolation inventory and why execution is closed.
``tools``       the closed, compile-time tool registry - the sixth in this
                product - with typed parameters and an import-time check that
                nothing in it crosses ADR-0008 7's trust boundary.
``budget``      the run ceiling: tool calls, wall-clock seconds, concurrency.
                No token, no currency, and no code path that writes it.
``workspace``   ``<data_dir>/workspace/v1/<task id>``, with the containment,
                reparse-point and ceiling defences written from nothing.
``activity``    the append-only timeline, its retention, and its one link to
                the audit chain.
``service``     planning, running, stopping and reporting.

Nothing here imports an HTTP client, a socket, the OpenCode package, the
composer or the vault's secret modules (ADR-0008 7). Nothing here imports
``subprocess`` or evaluates a string.
"""

from station_api.agent.activity import (
    ActivityAction,
    ActivityActor,
    ActivityLog,
    ActivityOutcome,
    ActivityView,
)
from station_api.agent.errors import AgentError
from station_api.agent.service import AgentService, RunPhase, RunView, StepPhase

__all__ = [
    "ActivityAction",
    "ActivityActor",
    "ActivityLog",
    "ActivityOutcome",
    "ActivityView",
    "AgentError",
    "AgentService",
    "RunPhase",
    "RunView",
    "StepPhase",
]
