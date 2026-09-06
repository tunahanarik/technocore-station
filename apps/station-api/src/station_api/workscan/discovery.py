"""The discovery log: new public rooms, in the order the service announced them.

``GET /r/events`` is the service's own append-ordered log - one line per new
public room. It is **server-written**: a client write there answers 403, and
this build never attempts one, which is a property of the source rather than a
promise (see :data:`WRITE_REFUSAL` and the test that reads the syntax tree).

Why this lane needs no new address
-----------------------------------
ADR-0007 3 left it out of scope for a precise reason: the pinned
``openapi.json`` published ``/r/events`` with ``parameters: null`` and
described ``since``/``format`` only in the prose beside it, and Package B's
rule is that a critical field is read from a schema and never from prose.

The measured contract removes that reason without weakening the rule. The lane
behaves like an ordinary room - ``since``, ``format`` and the ring's retention
all apply - so it is not a new address family at all: it is ``/r/{room}`` with
a **compile-time** room name. The registry therefore stays at two targets, the
same resolver and the same room policy apply to it unchanged, the same parser
reads its body, and ``OUTBOUND_CLIENT_MODULES`` stays at five. Nothing here
opens a socket; it hands :class:`~station_api.workscan.client.RoomScanClient`
a target the resolver built.

The line format is not published, so this build does not invent one
--------------------------------------------------------------------
The description says "one line per new public room" and stops. It does not say
whether the line is the bare name, a sentence containing it, or a name with a
timestamp. A parser written to a guess would silently produce **room names
this build made up** the first time the format differed - and a made-up name
that happens to validate is a one-click scan target for a room nobody
announced.

So :func:`announced_name` accepts exactly one shape: a line that, trimmed, is
already a valid room name. Every other line is kept **verbatim** with the
reason it could not be read, which shows a person the real format instead of
our guess at it. The rule is deliberately easy to widen later, from evidence,
and impossible to widen by accident.

Four kinds of line are refused rather than offered
---------------------------------------------------
* **not a name.** The format is unpublished; the line is shown as it arrived.
* **a denied room.** ``DENIED_ROOMS`` applies here as it does everywhere else,
  and the refusal drops the line's *text* as well as the name: repeating it is
  how ``lobby`` would reach a screen through the very check that exists to
  keep it off one (INV-05, ADR-0007 11).
* **an unlisted room.** The service states that unlisted (``p-``) rooms are
  never announced here. A line announcing one contradicts the published
  contract, and turning a contradiction into a button would launder it. The
  name is shown, the conflict is named, and it is not selectable.
* **a name the reply normalised differently.** Same rule the write path uses.

Nothing here is automatic
--------------------------
There is no timer, no background task and no long poll (SI-272, SI-224). The
log is read inside the request a person made, once, and ``since`` is a cursor
that caller supplies rather than one this module remembers - a remembered
cursor is the first half of a loop somebody schedules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from technocore_conform import InvalidNameError, validate_name

from station_api.technocore.projection import safe_display
from station_api.technocore.write_targets import DENIED_ROOMS, classes_of
from station_api.workscan.authority import (
    CONTENT_AUTHORITY,
    ROOM_NAME_CAVEAT,
    UNLISTED_NEVER_LISTED,
    AuthorityLevel,
)
from station_api.workscan.snapshot import (
    RingDropNotice,
    RoomMessagesSnapshot,
    StalenessNote,
)
from station_api.workscan.targets import RoomScanTarget, resolve_room_target

#: The discovery log's room name. Compile-time, and the only reason this
#: module can exist without a new registry entry: it is a room, so the room
#: lane addresses it.
DISCOVERY_ROOM: Final = "events"

#: Longest announcement line kept, in characters. An announcement is a room
#: name in the shape this build understands, and a name is at most 48
#: characters; anything longer is a line we could not read anyway, and it is
#: kept only so a person can see the format.
MAX_LINE_CHARS = 200

#: Most lines kept from one read. The message parser already caps at the
#: published ``limit`` ceiling; this is the same bound restated where the
#: entries are built, so a change to one is visible against the other.
MAX_ENTRIES = 200

#: Why this build never writes to the discovery log. Carried on the surface
#: rather than left in this docstring, so "we do not write here" is a claim a
#: client can read back.
WRITE_REFUSAL = (
    "Kesif gunlugu sunucu tarafindan yazilir. Bir istemcinin buraya yazma "
    "denemesi 403 ile reddedilir; Station denemez. Bu paketin hicbir kod "
    "yolunda yazma adresi yoktur ve bir test kaynak agacini tarayarak bunu "
    "dogrular."
)

#: The reason attached to a line that announces an unlisted room.
UNLISTED_NEVER_ANNOUNCED = (
    "Bu satir listelenmeyen (p-) bir odayi duyuruyor; oysa servis boyle bir "
    "odanin kesif gunlugunde hicbir zaman duyurulmadigini soyluyor. Celiskiyi "
    "aciklayamadigimiz icin bu oda tek tikla secilebilir yapilmadi; adini "
    "zaten biliyorsaniz elle yazabilirsiniz."
)

#: The reason attached to a line this build cannot read as a name.
FORMAT_NOT_PUBLISHED = (
    "Bu satirin bicimi yayimlanmis semada yok. Station bir ayristirici "
    "uydurmaz: yalnizca tamami gecerli bir oda adi olan satirlari secilebilir "
    "yapar, digerlerini geldigi gibi gosterir."
)

#: The reason attached to a line that is exactly a room this build refuses to
#: name. The line's own text is dropped with it.
DENIED_ROOM_LINE = (
    "Bu satir, Station'in hicbir yetenek icin adlandirmadigi bir odayi "
    "duyuruyor. Satirin metni de gosterilmiyor: adi tekrar etmek, onu "
    "ekrandan uzak tutmak icin var olan denetimin kendisiyle ekrana "
    "getirmek olurdu."
)

#: The reason attached to an empty line.
EMPTY_LINE = "Bu satirda metin yok; duyurdugu bir oda adi okunamadi."


@dataclass(frozen=True, slots=True)
class AnnouncedRoom:
    """One line of the discovery log.

    A line, not an endorsement. There is deliberately no ``recommended``,
    ``score``, ``rank`` or ``trusted`` field here: the log records that a room
    was opened, and the room's name is still a string the person who opened it
    chose (:data:`~station_api.workscan.authority.ROOM_NAME_CAVEAT`).
    """

    seq: int
    ts: str
    #: The room this line announces, when this build could read one. Empty
    #: otherwise - never a placeholder, because a placeholder is a room name
    #: this build made up.
    name: str
    #: The line as it arrived, swept and bounded. Empty when repeating it
    #: would print a name this product does not name.
    line: str
    #: Why no name was read, or "" when one was.
    unusable_reason: str

    @property
    def selectable(self) -> bool:
        """Whether this line may be offered as a one-click scan choice."""
        return bool(self.name)

    @property
    def authority(self) -> AuthorityLevel:
        return CONTENT_AUTHORITY


@dataclass(frozen=True, slots=True)
class DiscoveryLog:
    """One read of the discovery log, at one moment."""

    #: The room this build asked for - the compile-time constant, never the
    #: name the reply echoed. The message parser already refuses a reply that
    #: names another room; this field carries the requested one for the same
    #: reason that one does.
    room: str
    entries: tuple[AnnouncedRoom, ...]
    #: The cursor this read was made with, or ``None``.
    since: int | None
    #: The service's ``last_seq``, read and never assumed. This is what a
    #: caller passes back as ``since`` next time - and it is passed back by a
    #: **caller**, because a cursor this module remembered would be the first
    #: half of a loop.
    last_seq: int
    first_seq: int | None
    staleness: StalenessNote
    ring_drop: RingDropNotice | None
    sha256: str

    @property
    def lines_read(self) -> int:
        return len(self.entries)

    @property
    def selectable(self) -> tuple[str, ...]:
        """The rooms a person may pick from this log, in announcement order."""
        return tuple(entry.name for entry in self.entries if entry.selectable)

    @property
    def unusable_count(self) -> int:
        return sum(1 for entry in self.entries if not entry.selectable)

    @property
    def room_name_caveat(self) -> str:
        return ROOM_NAME_CAVEAT

    @property
    def unlisted_note(self) -> str:
        return UNLISTED_NEVER_LISTED

    @property
    def write_refusal(self) -> str:
        return WRITE_REFUSAL


def discovery_target(*, markers: frozenset[str]) -> RoomScanTarget:
    """Resolve the log through the same policy every other room goes through.

    Not a private constant address. ``markers`` comes from the live manifest
    check exactly as it does for a room a person typed, so an empty set is a
    refusal here too: a lane that resolved without a verified convention would
    be the one address in this package that skipped the check.
    """
    return resolve_room_target(DISCOVERY_ROOM, markers=markers)


def announced_name(text: str, *, markers: frozenset[str]) -> tuple[str, str]:
    """Read a room name off one line, or say why there is none.

    Returns ``(name, reason)`` with exactly one of the two filled. The whole
    extraction rule is here and it is one rule: a line that, swept, is already
    a valid room name. Splitting on whitespace and hoping one token validates
    would be a parser for a format nobody published.

    The sweep comes **first**, and that ordering is the guard rather than
    tidiness. ``safe_display`` turns invisible characters into spaces, so a
    line reading ``lobby`` with a zero-width space glued to it becomes
    ``lobby`` here and is refused **by name** below. Comparing the raw text
    instead would have reported the same line as merely unreadable, which is
    the wrong sentence about the one room this product never addresses.

    There is deliberately no "the name differs from its normalised form"
    branch. There was one, and it was unreachable:
    :func:`technocore_conform.validate_name` **returns its input unchanged**
    (``names.py``) - it is a pattern check, not a normaliser - so after a
    successful call the two strings are the same object's value by
    construction. A check that cannot fire is a check nobody can test, and it
    reads as protection that is not there. The normalising this lane actually
    does is the sweep above, and that one is driven by a test.
    """
    candidate = safe_display(text).strip()
    if not candidate:
        return "", EMPTY_LINE

    try:
        name = validate_name(candidate, field="room")
    except InvalidNameError:
        return "", FORMAT_NOT_PUBLISHED

    if name in DENIED_ROOMS:
        return "", DENIED_ROOM_LINE
    if "p" in classes_of(name, markers):
        return "", UNLISTED_NEVER_ANNOUNCED
    return name, ""


def parse_discovery(
    snapshot: RoomMessagesSnapshot, *, markers: frozenset[str]
) -> DiscoveryLog:
    """Turn one read of the log into announcements, refusing what it cannot read.

    Takes an already-parsed :class:`~station_api.workscan.snapshot.RoomMessagesSnapshot`
    rather than raw bytes: the log is a room, the room parser already refuses
    a reply that names a different one, and a second parser for the same body
    would be a second thing that can disagree about what arrived.
    """
    entries: list[AnnouncedRoom] = []
    for item in snapshot.messages[:MAX_ENTRIES]:
        name, reason = announced_name(item.text, markers=markers)
        # A denied room's line is dropped along with its name. Every other
        # unreadable line survives verbatim, because the line is the only
        # evidence a person has of what the real format is.
        line = "" if reason == DENIED_ROOM_LINE else safe_display(item.text)[:MAX_LINE_CHARS]
        entries.append(
            AnnouncedRoom(
                seq=item.seq,
                ts=item.ts,
                name=name,
                line=line,
                unusable_reason=reason,
            )
        )

    return DiscoveryLog(
        room=snapshot.room,
        entries=tuple(entries),
        since=snapshot.since,
        last_seq=snapshot.last_seq,
        first_seq=snapshot.first_seq,
        staleness=snapshot.staleness,
        ring_drop=snapshot.ring_drop,
        sha256=snapshot.sha256,
    )


__all__ = [
    "DENIED_ROOM_LINE",
    "DISCOVERY_ROOM",
    "EMPTY_LINE",
    "FORMAT_NOT_PUBLISHED",
    "MAX_ENTRIES",
    "MAX_LINE_CHARS",
    "UNLISTED_NEVER_ANNOUNCED",
    "WRITE_REFUSAL",
    "AnnouncedRoom",
    "DiscoveryLog",
    "announced_name",
    "discovery_target",
    "parse_discovery",
]
