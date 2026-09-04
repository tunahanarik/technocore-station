"""Work-scan errors.

Fail-closed, like the three error hierarchies before it. A scan either
produced bytes this build parsed into a snapshot, or there is no snapshot and
nothing pretends otherwise: an unread room contributes no candidates rather
than contributing an empty list that reads like "nothing to do here".

Messages never carry user data, a file path or an identity. They may name the
target id, the HTTP status, a byte count and a room name the user typed,
because those are properties of a request this product made to a public read
surface.
"""

from __future__ import annotations


class WorkScanError(Exception):
    """Base class for every work-scan failure."""


class ScanTargetError(WorkScanError):
    """A room was refused as a scan target.

    Raised by the room policy, which is the *write* path's policy applied to a
    read (ADR-0007 3). Safe to show: it names the rule, never the internals.
    """


class ScanFetchError(WorkScanError):
    """The public read surface could not be reached, or answered unusably.

    Covers DNS, TLS, timeout, connection reset and a status this build refuses
    to read as success. One class on purpose: from a caller's point of view
    they mean the same thing, which is that this build does not know what the
    room currently holds.
    """


class UnexpectedRedirectError(ScanFetchError):
    """The origin answered with a redirect.

    Never followed. Following one is how a request leaves the allow-listed
    origin, and this client's allow-list is the only thing standing between a
    scan and an arbitrary host.
    """


class ResponseTooLargeError(ScanFetchError):
    """The body exceeded the per-target cap, measured on decompressed bytes."""


class WrongMediaTypeError(ScanFetchError):
    """The reply was not JSON.

    Its own class because the pinned contract makes this the *expected*
    failure rather than an exotic one: ``format=json`` is advisory, any other
    value is ignored silently, and the reply then stays ``text/plain`` with a
    200 status. A client that read the status would call that a success
    (ADR-0007 3).
    """


class SnapshotParseError(WorkScanError):
    """The document arrived and is not usable.

    Malformed JSON, an unexpected top-level type, or a field whose type is not
    what the pinned schema publishes. A document this build cannot parse
    produces no candidates; it never produces guessed ones.
    """


class CandidateError(WorkScanError):
    """A candidate could not be produced, or could not be turned into a task.

    Raised where one of the eight mandatory elements is missing or where a
    prohibited work shape was recognised. Both are refusals with a reason, not
    silently dropped rows.
    """


__all__ = [
    "CandidateError",
    "ResponseTooLargeError",
    "ScanFetchError",
    "ScanTargetError",
    "SnapshotParseError",
    "UnexpectedRedirectError",
    "WorkScanError",
    "WrongMediaTypeError",
]
