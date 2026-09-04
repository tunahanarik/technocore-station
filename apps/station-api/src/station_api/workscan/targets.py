"""The closed registry of scan targets. The fourth one, and why there is a fourth.

===============================================  ==========================
:mod:`station_api.technocore.sources`            public document read
:mod:`station_api.technocore.write_targets`      explicit signed write
:mod:`station_api.technocore.evidence_targets`   evidence read
this module                                      **work scan read**
===============================================  ==========================

Why ``/rooms`` and ``/r/{room}`` are not added to an existing registry
----------------------------------------------------------------------
``SOURCES`` is **exactly six fixed documents** and stays six: a test pins both
``len(SOURCES) == 6`` and the set equality of ``SourceId``, and those two
lines - not the ``"/r/" not in source.path`` assertion beside them, which
``/rooms`` would pass without touching - are what actually keeps the
monitoring path from addressing a room (ADR-0007 3).

``write_targets`` is the write lane. ``evidence_targets`` holds one template
whose policy is "a room we already wrote to, on the user's request, for a
capture". A discovery scan is a fourth capability with a fourth failure
policy: it reads rooms this product has never written to, it produces no
evidence record, and a failure on it is a room that contributes nothing
rather than a gate that shuts.

What is deliberately **not** here
---------------------------------
``/r/events``. The pinned ``openapi.json`` publishes it with
``parameters: null`` and describes ``since``/``format``/``wait`` only in
prose. Package B's rule - a critical field is read from the schema, never
from the prose beside it - cannot be applied to a schema that has no
parameters at all, so the discovery lane stays out of scope and ``/rooms``,
which carries a full typed schema, is the discovery surface (ADR-0007 3).

The room name goes through the write path's policy, unchanged
-------------------------------------------------------------
:func:`resolve_room_target` delegates to
:func:`station_api.technocore.write_targets.resolve_message_target`, exactly
as ``evidence_targets`` does. Two copies of a room policy are two things that
can disagree. ``DENIED_ROOMS`` therefore applies to reading as well: Station
does not read Lobby either, because a scan is still a request naming that
room (ADR-0002 4.1, ADR-0007 11, INV-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from technocore_conform import InvalidNameError, validate_name

from station_api.technocore.sources import TECHNOCORE_ORIGIN
from station_api.technocore.write_targets import (
    DENIED_ROOMS,
    UNDERSTOOD_ROOM_CLASSES,
    RoomPolicyError,
    WriteTarget,
    resolve_message_target,
)
from station_api.workscan.errors import ScanTargetError

#: Both targets are read with GET. Typed as a literal so widening it is a type
#: error at every call site rather than a runtime surprise at one of them.
#:
#: "Only GET" is **not** a safety property on this service - ``/r/{room}/say``
#: and ``/kv/{ns}/{key}/set`` are writes performed over GET - which is why the
#: registry, and not the method, is what keeps this client read-only.
SCAN_METHOD: Final[Literal["GET"]] = "GET"


class ScanTargetId(StrEnum):
    """The two addresses this build scans, and never a third."""

    #: ``GET /rooms`` - the room overview.
    ROOM_INDEX = "room_index"
    #: ``GET /r/{room}`` - one room's newest messages.
    ROOM_MESSAGES = "room_messages"


#: The room overview. No path parameter: this one is a fixed document address.
ROOM_INDEX_PATH = "/rooms"

#: One room's message lane. Formatted here and nowhere else.
ROOM_MESSAGES_TEMPLATE = "/r/{room}"


@dataclass(frozen=True, slots=True)
class ScanTarget:
    """One scan address, its cap, and why it is read at all."""

    id: ScanTargetId
    path: str
    #: Authority of the **path**, not of what comes back. The endpoint is an
    #: official one (level 1); its payload is level 3. See
    #: :mod:`station_api.workscan.authority`.
    path_authority: int
    #: What the pinned schema publishes for ``?format=json``. The client
    #: checks the response against this rather than against the status code.
    media: str
    #: Per-target ceiling on the decompressed body, in bytes.
    max_bytes: int
    rationale: str

    @property
    def method(self) -> Literal["GET"]:
        return SCAN_METHOD


#: The complete set. Adding an address means editing this tuple, which is a
#: reviewable change; nothing computes a path at runtime.
SCAN_TARGETS: tuple[ScanTarget, ...] = (
    ScanTarget(
        id=ScanTargetId.ROOM_INDEX,
        path=ROOM_INDEX_PATH,
        path_authority=1,
        media="application/json",
        max_bytes=2 * 1024 * 1024,
        rationale=(
            "The room overview. Read only when a person asks, to offer a set "
            "of rooms to choose from. Its `room` and `topic` values are "
            "caller-written strings the service re-emits, which is the whole "
            "reason the content authority level exists."
        ),
    ),
    ScanTarget(
        id=ScanTargetId.ROOM_MESSAGES,
        path=ROOM_MESSAGES_TEMPLATE,
        path_authority=1,
        media="application/json",
        max_bytes=4 * 1024 * 1024,
        rationale=(
            "One room's newest messages, for the rooms the user selected. "
            "Never the whole room universe, never on a timer."
        ),
    ),
)

_TARGETS_BY_ID: dict[ScanTargetId, ScanTarget] = {
    target.id: target for target in SCAN_TARGETS
}


def get_target(target_id: ScanTargetId) -> ScanTarget:
    """Look up a target. Raises ``KeyError`` for anything not registered."""
    return _TARGETS_BY_ID[target_id]


# ---------------------------------------------------------------------------
# Pagination, read off the pinned document rather than chosen
# ---------------------------------------------------------------------------

#: ``since`` returns only messages with a **greater** ``seq``. The pinned
#: description also records that anything which is not a non-negative integer
#: is read as no cursor at all - so this client sends the parameter only when
#: it has a non-negative integer to send, rather than sending a sentinel and
#: relying on the server's fallback.
SINCE_PARAM = "since"

LIMIT_PARAM = "limit"

FORMAT_PARAM = "format"

#: The only ``format`` value that changes anything. Any other value - a typo
#: included - is **silently ignored** and the reply stays ``text/plain`` with
#: a 200 status, which is why the client checks the Content-Type and not the
#: status (ADR-0007 3).
JSON_FORMAT = "json"

#: What the pinned schema declares as the default when ``limit`` is absent.
DEFAULT_LIMIT: Final = 50

#: The published clamp. The pinned description is explicit that a value
#: outside it is **never refused**: it is clamped, and "the count you get back
#: is the answer - read `count`, do not assume it". So this build clamps to
#: the same bounds before sending, and still reads ``count`` back.
MIN_LIMIT: Final = 1
MAX_LIMIT: Final = 200

#: Query parameters this build will not send, and the reason travels with
#: them.
#:
#: ``wait`` is the long-poll parameter. Holding a connection open for the next
#: message is polling with a different shape, and ADR-0007 4 removes polling
#: from this package altogether - there is no timer, no background task and no
#: held connection. ``n`` exists only to vary a URL past a cache, which is a
#: parameter for a client that re-polls an idle room; this one does not.
NEVER_SENT_PARAMS: frozenset[str] = frozenset({"wait", "n"})

#: The server's own declared staleness bound for the room overview, in
#: seconds, from the pinned reference's ``config.ROOMS_CACHE_SECONDS``.
#:
#: Carried as the service's **declaration**, never as a measurement of our
#: own, and never turned into a "fresh"/"stale" verdict: ADR-0007 5 refuses an
#: invented threshold, so what is shown is this number plus the moment the
#: snapshot was actually read.
ROOMS_CACHE_SECONDS_DECLARED: Final = 3

#: Where that number was read. Shown beside it, so an operator can check it.
#:
#: Written as a description rather than as a repository path: a runtime module
#: that carried the pinned oracle's path would be the first half of a runtime
#: module that reads it, and a test refuses that literal on exactly those
#: grounds.
ROOMS_CACHE_PROVENANCE = "pinli referans deposu, config.py::ROOMS_CACHE_SECONDS"


def clamp_limit(limit: int) -> int:
    """Bring a limit inside the published range. Never refuses.

    Mirrors what the service does with the value anyway. Clamping here rather
    than sending an out-of-range number and trusting the fallback means the
    URL this build produces is one it can explain, and it keeps the ``limit``
    a caller sees in a scan record equal to the one that went on the wire.
    """
    return max(MIN_LIMIT, min(MAX_LIMIT, limit))


def index_query(*, limit: int = DEFAULT_LIMIT) -> dict[str, str]:
    """The exact query for the room overview. Three keys at most, never more."""
    return {LIMIT_PARAM: str(clamp_limit(limit)), FORMAT_PARAM: JSON_FORMAT}


def messages_query(
    *, since: int | None = None, limit: int = DEFAULT_LIMIT
) -> dict[str, str]:
    """The exact query for one room's messages.

    ``since`` is omitted rather than sent as a sentinel when there is no
    cursor, and a negative cursor is refused here instead of being handed to
    the server's "not a non-negative integer means no cursor" fallback - a
    fallback that quietly returns the newest messages is exactly the shape of
    silent success this package is built to avoid.
    """
    query = {LIMIT_PARAM: str(clamp_limit(limit)), FORMAT_PARAM: JSON_FORMAT}
    if since is not None:
        if since < 0:
            raise ScanTargetError(
                "Imlec negatif olamaz; sunucu gecersiz bir imleci sessizce "
                "yok sayar ve en yeni mesajlari dondurur."
            )
        query[SINCE_PARAM] = str(since)
    return query


@dataclass(frozen=True, slots=True)
class RoomScanTarget:
    """One resolved room whose messages may be read.

    ``__post_init__`` re-applies the parts of the room policy that are
    properties of the *name*, so the sentence "a target can only be built by
    going through the write path's policy" is true of the type and not only of
    the one function that is supposed to build it.

    It was not true before. This was a plain frozen dataclass, and a review
    built ``RoomScanTarget("lobby")`` by hand and drove a request to
    ``/r/lobby`` straight through the client - the URL check passes, because
    scheme, host, port and path are all exactly what the registry produces.
    The route could not reach it, but the redundant layer that exists for
    precisely the mistake nobody catches by eye had a hole in the shape of
    INV-05's room.

    What is **not** re-checked here is the manifest markers: whether a
    successful live check has run is a fact about this process at this moment,
    not about the name, and a dataclass that read it would be a second copy of
    a decision :func:`resolve_room_target` already fails closed on.
    """

    room: str
    #: The class markers this room carries, in the order they appear.
    classes: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            name = validate_name(self.room, field="room")
        except InvalidNameError as exc:
            raise ScanTargetError(
                "Oda adi resmi ad kalibina uymuyor: kucuk harf, rakam, '-' ve "
                "'_', 1-48 karakter, harf veya rakamla baslar."
            ) from exc
        if name != self.room:
            raise ScanTargetError(
                "Oda adi normalize edilmis biciminden farkli; hedef "
                "olusturulmuyor."
            )
        if name in DENIED_ROOMS:
            raise ScanTargetError(
                f"'{name}' odasi bir bulusma noktasidir ve Station bu odayi "
                "okumak icin de adlandirmaz."
            )
        unknown = [item for item in self.classes if item not in UNDERSTOOD_ROOM_CLASSES]
        if unknown:
            raise ScanTargetError(
                "Bu oda adi bu surumun tanimadigi bir oda sinifi tasiyor: "
                f"{', '.join(unknown)}."
            )

    @property
    def method(self) -> Literal["GET"]:
        return SCAN_METHOD

    @property
    def path(self) -> str:
        return ROOM_MESSAGES_TEMPLATE.format(room=self.room)

    @property
    def url(self) -> str:
        """The full, fixed URL. Built here and nowhere else."""
        return f"{TECHNOCORE_ORIGIN}{self.path}"

    @property
    def is_ephemeral(self) -> bool:
        """Messages here expire on read, so an absent line proves even less."""
        return "e" in self.classes

    @property
    def is_unlisted(self) -> bool:
        """An unlisted room is never enumerated by the overview."""
        return "p" in self.classes


def index_url() -> str:
    """The room overview's full URL. Built here and nowhere else."""
    return f"{TECHNOCORE_ORIGIN}{ROOM_INDEX_PATH}"


def resolve_room_target(room: str, *, markers: frozenset[str]) -> RoomScanTarget:
    """Validate a room name and resolve it to the message lane.

    The whole validation is the write path's, deliberately: the published name
    pattern, ``DENIED_ROOMS``, the understood class markers, and the
    requirement that the markers came from a manifest check that actually
    succeeded. Reading is a different capability from writing; the set of
    rooms Station will *name* is one set.
    """
    try:
        target: WriteTarget = resolve_message_target(room, markers=markers)
    except RoomPolicyError as exc:
        # Re-raised in this package's hierarchy, with the message unchanged.
        # The refusal is the write path's; the *type* is this package's, so a
        # scan failure never reaches a caller as a write-path exception.
        raise ScanTargetError(str(exc)) from exc
    return RoomScanTarget(room=target.room, classes=target.classes)


__all__ = [
    "DEFAULT_LIMIT",
    "FORMAT_PARAM",
    "JSON_FORMAT",
    "LIMIT_PARAM",
    "MAX_LIMIT",
    "MIN_LIMIT",
    "NEVER_SENT_PARAMS",
    "ROOMS_CACHE_PROVENANCE",
    "ROOMS_CACHE_SECONDS_DECLARED",
    "ROOM_INDEX_PATH",
    "ROOM_MESSAGES_TEMPLATE",
    "SCAN_METHOD",
    "SCAN_TARGETS",
    "SINCE_PARAM",
    "RoomScanTarget",
    "ScanTarget",
    "ScanTargetId",
    "clamp_limit",
    "get_target",
    "index_query",
    "index_url",
    "messages_query",
    "resolve_room_target",
]
