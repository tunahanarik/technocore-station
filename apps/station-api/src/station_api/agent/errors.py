"""Refusals this package raises, each carrying a reason a surface can show.

The shape is :class:`station_api.tasks.service.TaskError`'s: one exception
type per boundary, every one of them carrying a machine-readable ``reason``
beside a Turkish sentence that is safe to put on a screen. A refusal that
arrives as a bare ``KeyError`` becomes an armoured 500 and tells the user
nothing, which is the failure ADR-0004 2 named and F-11 fixed once already.
"""

from __future__ import annotations


class AgentError(Exception):
    """An agent operation was refused. The message is safe to show a user."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class ToolRegistryError(AgentError):
    """An identifier that is not in the compile-time tool registry.

    Raised as a *shown* refusal rather than a lookup failure, because the
    thing being refused is a request for a capability this build does not
    have. ADR-0008 2: the agent cannot add a tool to itself, and asking for
    an unregistered one gets an answer rather than silence.
    """


class ToolArgumentError(AgentError):
    """An argument did not match the tool's typed parameter."""


class WorkspaceError(AgentError):
    """A workspace path, name or ceiling was refused."""


class RunError(AgentError):
    """A run operation was refused: wrong phase, missing plan, stopped."""


class ActivityError(AgentError):
    """An activity operation was refused, deletion of a linked row included."""


__all__ = [
    "ActivityError",
    "AgentError",
    "RunError",
    "ToolArgumentError",
    "ToolRegistryError",
    "WorkspaceError",
]
