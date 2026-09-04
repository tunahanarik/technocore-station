"""The closed registry of evidence-read targets.

The third registry, and the reason there are three rather than two is the
same reason there were two rather than one (SI-152): a capability gets its
own closed list, and a bug in one cannot produce an address belonging to
another.

===========================================  ==========================
:mod:`station_api.technocore.sources`        public document read
:mod:`station_api.technocore.write_targets`  explicit signed write
this module                                  **evidence read**
===========================================  ==========================

Why ``/r/{room}/export`` is not simply a seventh entry in ``SOURCES``
--------------------------------------------------------------------
``SOURCES`` enumerates six *fixed documents*. Every one of its entries is a
constant path with no parameter, and a test asserts both the set equality and
that no entry's path contains ``/r/`` - which is what makes "the read
monitoring path cannot address a room" a structural fact rather than a
convention. Adding a room-parameterised template there would have deleted
that property to gain nothing: the shape is different (a template, not a
document), the failure policy is different, and the caller is different.

So the set stays six, and this registry holds exactly one template
(ADR-0003 1). Adding a second entry here is the change a reviewer must see.

Room names go through the write path's policy, unchanged
--------------------------------------------------------
:func:`resolve_export_target` delegates to
:func:`station_api.technocore.write_targets.resolve_message_target` rather
than re-deriving the rules. Two copies of a room policy are two things that
can disagree, and the one that would drift is the one nobody is looking at.
``DENIED_ROOMS`` therefore applies here too: Station does not read Lobby's
export either, because a capture attempt is still a request naming that room
(ADR-0002 4.1, INV-05).

Nothing here is a write. The template is a GET on a public read surface, and
the pinned reference publishes it with "No query parameters" - so there is no
parameter for a caller to steer even if one wanted to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from station_api.technocore.sources import TECHNOCORE_ORIGIN
from station_api.technocore.write_targets import WriteTarget, resolve_message_target

#: The evidence read is a GET. Unlike the six documents, it carries a room
#: name - which is exactly why it lives in its own registry.
EXPORT_METHOD: Final[Literal["GET"]] = "GET"

#: The one evidence path template. Formatted here and nowhere else.
EXPORT_LANE_TEMPLATE = "/r/{room}/export"

#: The response header the pinned reference publishes alongside the body. The
#: room's conversation epoch; a record captured under one generation cannot be
#: compared against a capture taken under another.
GENERATION_HEADER = "X-Room-Generation"

#: The media type the pinned reference publishes for this lane.
EXPORT_MEDIA_TYPE = "application/x-ndjson"


@dataclass(frozen=True, slots=True)
class EvidenceTarget:
    """One resolved room whose export may be read."""

    room: str
    #: The class markers this room carries, in the order they appear.
    classes: tuple[str, ...]

    @property
    def method(self) -> Literal["GET"]:
        return EXPORT_METHOD

    @property
    def path(self) -> str:
        return EXPORT_LANE_TEMPLATE.format(room=self.room)

    @property
    def url(self) -> str:
        """The full, fixed URL. Built here and nowhere else."""
        return f"{TECHNOCORE_ORIGIN}{self.path}"

    @property
    def is_ephemeral(self) -> bool:
        """Records here expire on read, so an absent line proves even less."""
        return "e" in self.classes


def resolve_export_target(room: str, *, markers: frozenset[str]) -> EvidenceTarget:
    """Validate a room name and resolve it to the export lane.

    The whole validation is the write path's, deliberately: name pattern,
    ``DENIED_ROOMS``, understood class markers, and the requirement that the
    markers came from a manifest check that actually succeeded. A capture is a
    read, but it is a read *about a room we wrote to*, and the set of rooms
    Station will name is one set.
    """
    target: WriteTarget = resolve_message_target(room, markers=markers)
    return EvidenceTarget(room=target.room, classes=target.classes)


__all__ = [
    "EXPORT_LANE_TEMPLATE",
    "EXPORT_MEDIA_TYPE",
    "EXPORT_METHOD",
    "GENERATION_HEADER",
    "EvidenceTarget",
    "resolve_export_target",
]
