"""Turning scan bytes into snapshots, and saying what a snapshot cannot tell you.

Two documents are parsed here and both are parsed **strictly**: duplicate
keys, non-finite numbers and non-object payloads are refused rather than
normalised, because a document that means two things to two readers is
exactly what an anonymous, world-writable surface can produce.

Three things are read from the reply and never assumed (ADR-0007 5)
--------------------------------------------------------------------
``count``, ``last_seq`` and ``first_seq``. The pinned description says it in
so many words - *"the count you get back is the answer - read `count`, do not
assume it"* - because ``limit`` is advisory: an out-of-range value is clamped
to 1..200 and **never refused**, so the number of messages returned need not
be the number requested. This module therefore records both the server's
``count`` and the length of the array it actually received, and reports the
disagreement instead of picking a winner.

Staleness: a measurement, never an invented threshold
------------------------------------------------------
No "fresh"/"stale" verdict is computed here and no cut-off is chosen. What is
carried is the pair of facts that exist: the moment this process finished
reading the body, and the bound the **service publishes about itself**
(``ROOMS_CACHE_SECONDS = 3`` in the pinned reference's own config). Both are
always present - a staleness note that only appeared when something looked
wrong would be a note nobody ever sees.

The room is the one *we* asked for, never the one the reply claims
-------------------------------------------------------------------
``/r/{room}`` echoes a ``room`` field, and that field is a value on an
anonymous, world-writable surface: it is whatever the answering process chose
to put there. Nothing downstream may take it as the scan's scope. Two things
would break if it did, and both are load-bearing:

* the scope this product reports would be the reply's rather than the user's,
  and a reply claiming ``lobby`` would make the product print the name of the
  one room INV-05 says it never addresses (ADR-0007 11);
* a candidate's identity is ``(room, seq)``, so two genuinely different rooms
  answering with the same ``room`` and ``seq`` would collapse into one
  candidate and one of the two lines would vanish.

So :func:`parse_room_messages` takes the **resolved**
:class:`~station_api.workscan.targets.RoomScanTarget`'s room name as a
required argument, refuses a reply that names a different one, and puts the
requested name - never the echoed one - on the snapshot. The refusal is
fail-closed rather than a relabel: a reply that names another room may well
be *that other room's* content, and filing it under the requested name would
be a worse lie than filing it under the claimed one. The claimed name is not
repeated in the refusal either, because repeating it is how ``lobby`` would
get printed by the very check that exists to keep it off the screen.

The ring drop is the server's signal, not our inference
--------------------------------------------------------
The published schema says of ``first_seq``: *"Greater than your `since` + 1
means the ring dropped messages you never read."* That is a machine-readable
statement by the service about its own retention, so it gets its **own**
notice, separate from the staleness note. Conflating the two would present a
concrete "you have unread messages that are gone" as a general caveat about
freshness.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from station_api.strict_json import StrictJsonError, loads_strict
from station_api.technocore.projection import safe_display
from station_api.workscan.authority import (
    CALLER_WRITTEN_ROOM_FIELDS,
    CONTENT_AUTHORITY,
    MEASURED_CAVEAT,
    ROOM_NAME_CAVEAT,
    TOPIC_CAVEAT,
    UNLISTED_NEVER_LISTED,
    AuthorDescription,
    AuthorityLevel,
    describe_author,
)
from station_api.workscan.client import ScanFetchResult
from station_api.workscan.errors import SnapshotParseError
from station_api.workscan.targets import (
    ROOMS_CACHE_PROVENANCE,
    ROOMS_CACHE_SECONDS_DECLARED,
)

#: Most rooms one parsed overview keeps. A bound on what this build will hold
#: in memory from an anonymous document; the reply's own ``total`` is reported
#: separately, so truncating here never becomes a claim that the service has
#: fewer rooms than it said.
MAX_ROOMS = 200

#: Most messages one parsed room keeps. The published ceiling on ``limit`` is
#: 200 and this matches it, so a reply that carried more than the service
#: itself will return is bounded rather than trusted.
MAX_MESSAGES = 200

#: Longest message body kept, in characters. The published message ceiling is
#: 4096; this is the same number, so nothing is truncated that the service
#: would have accepted, and anything longer is a reply that outran its own
#: contract.
MAX_TEXT_CHARS = 4096

#: Most service-measured fields kept from one listing entry.
#:
#: The published ``rooms[]`` item schema is a bare object naming no
#: properties, so this build cannot enumerate the aggregates by name without
#: inventing names nobody published. It reads them **structurally** instead -
#: every key that is not caller-written - and a structural reader on an
#: anonymous document needs a ceiling, because the document decides how many
#: keys there are.
MAX_MEASURED_FIELDS = 16

#: Longest measured key or rendered value kept, in characters.
MAX_MEASURED_CHARS = 200

#: Most field names kept from a reply's own ``untrusted.fields`` array. The
#: array is content like everything else on this surface.
MAX_UNTRUSTED_FIELDS = 16


@dataclass(frozen=True, slots=True)
class StalenessNote:
    """When this snapshot was read, and what the service says about its cache.

    Deliberately not a verdict. There is no ``is_stale`` here, because there
    is no threshold this build is entitled to choose (ADR-0007 5).
    """

    #: The moment this process finished reading the body.
    read_at: datetime
    #: The bound the service declares for its own room overview, in seconds.
    declared_cache_seconds: int
    #: Where that number was read from, so it can be checked.
    declared_by: str
    #: One Turkish sentence carrying both measured values.
    detail: str


def staleness_note(read_at: datetime) -> StalenessNote:
    """Build the note. Always built; never conditional on anything."""
    return StalenessNote(
        read_at=read_at,
        declared_cache_seconds=ROOMS_CACHE_SECONDS_DECLARED,
        declared_by=ROOMS_CACHE_PROVENANCE,
        detail=(
            f"Anlik goruntu {read_at.isoformat()} aninda okundu. Servis kendi "
            f"yapilandirmasinda bu listeyi en cok "
            f"{ROOMS_CACHE_SECONDS_DECLARED} saniye bayat verebilecegini "
            "bildiriyor; bu deger bizim olcumumuz degil, servisin kendi "
            "beyanidir."
        ),
    )


@dataclass(frozen=True, slots=True)
class RingDropNotice:
    """The service's own signal that unread messages were dropped.

    Present only when the service actually signalled it. ``expected_first``
    and ``first_seq`` are both carried so the reader can see the arithmetic
    rather than take the sentence's word for it.
    """

    since: int
    expected_first: int
    first_seq: int
    detail: str


def ring_drop_notice(*, since: int | None, first_seq: int | None) -> RingDropNotice | None:
    """Apply the published rule, and only the published rule.

    ``first_seq > since + 1`` is the schema's own sentence. With no cursor
    there is nothing to compare against - the reply is simply the newest
    messages - so the answer is ``None`` rather than a guess about how much
    history was missed.
    """
    if since is None or first_seq is None:
        return None
    expected_first = since + 1
    if first_seq <= expected_first:
        return None
    missing = first_seq - expected_first
    return RingDropNotice(
        since=since,
        expected_first=expected_first,
        first_seq=first_seq,
        detail=(
            f"Okunmamis mesajlar halkadan dustu: {since} imlecinden sonra "
            f"{expected_first} numarali siradan devam edilmesi beklenirdi, "
            f"yanit {first_seq} numaradan basliyor. Aradaki {missing} kayit "
            "artik sunucuda yok. Bu, sunucunun kendi yayimladigi sinyaldir."
        ),
    )


@dataclass(frozen=True, slots=True)
class MeasuredField:
    """One thing the **service** says it measured about a room.

    Kept apart from :attr:`RoomEntry.name` and :attr:`RoomEntry.topic` on
    purpose. Those two are strings a stranger typed; these are the service's
    own aggregates over its own window, and merging the two into one object
    would make every reader responsible for remembering which is which.

    The key is echoed, never chosen here. The published ``rooms[]`` item
    schema names no properties at all, so a build that listed the aggregate
    names would be listing names nobody published - the same mistake as
    reading a field out of the prose beside a schema.
    """

    key: str
    #: The value rendered as one bounded, swept string. Objects and arrays are
    #: rendered rather than walked: a recursive reader on an anonymous
    #: document is an unbounded reader, and nothing downstream indexes into
    #: this value anyway.
    value: str


@dataclass(frozen=True, slots=True)
class UntrustedDeclaration:
    """What the reply itself said about which of its fields are caller-written.

    Carried, and never relied on. The declaration is content on the same
    anonymous surface as everything else here, so a reply that named *fewer*
    fields would otherwise widen what this build treats as a measurement -
    the exact inversion of the guard. The rule is therefore a **union**: a
    reply may add to :data:`~station_api.workscan.authority.CALLER_WRITTEN_ROOM_FIELDS`
    and can never subtract from it.

    Both lists travel so the disagreement is visible rather than resolved
    silently in favour of one of them.
    """

    #: Whether the reply carried the object at all.
    present: bool
    #: The field names the reply declared, swept and bounded.
    fields: tuple[str, ...]
    #: The reply's own note, swept. Data, like the rest of the document.
    note: str
    #: This build's compile-time list.
    build_fields: tuple[str, ...]
    #: Declared by the reply and not by this build. Honoured: treated as
    #: caller-written from here on.
    extra_fields: tuple[str, ...]
    #: Named by this build and **not** by the reply. Not honoured, and this is
    #: the direction that matters.
    missing_fields: tuple[str, ...]
    detail: str


@dataclass(frozen=True, slots=True)
class RoomEntry:
    """One room as the overview listed it.

    ``room`` and ``topic`` are caller-written strings the service re-emits.
    Everything else on the entry is the service's own measurement and it now
    travels in :attr:`measured`, separately - it used to be dropped on the
    floor, which made the listing a name and a stranger's note with nothing to
    tell one room from another.
    """

    name: str
    topic: str
    #: The service's own aggregates for this room, by the names it used.
    measured: tuple[MeasuredField, ...] = ()
    #: Whether the entry carried more measurements than this build keeps.
    measured_truncated: bool = False

    @property
    def authority(self) -> AuthorityLevel:
        """The level of :attr:`name` and :attr:`topic`.

        Deliberately the level of the caller-written half. The measured half
        is the service reporting on itself and carries
        :data:`~station_api.workscan.authority.MEASURED_CAVEAT` instead; one
        number for two different kinds of fact would be the merge this type
        exists to avoid.
        """
        return CONTENT_AUTHORITY


@dataclass(frozen=True, slots=True)
class RoomIndexSnapshot:
    """The room overview, as read once, at one moment."""

    rooms: tuple[RoomEntry, ...]
    #: The service's own count of every listed room. Reported as it arrived;
    #: it is not ``len(rooms)`` and the two are allowed to differ, because
    #: this build bounds what it keeps.
    total: int
    staleness: StalenessNote
    #: The digest of the exact bytes this snapshot was built from.
    sha256: str
    #: What the reply claimed about its own caller-written fields.
    untrusted: UntrustedDeclaration

    @property
    def kept_count(self) -> int:
        return len(self.rooms)

    @property
    def truncated(self) -> bool:
        """Whether this build kept fewer rooms than the service reported."""
        return self.total > self.kept_count

    @property
    def room_name_caveat(self) -> str:
        return ROOM_NAME_CAVEAT

    @property
    def topic_caveat(self) -> str:
        return TOPIC_CAVEAT

    @property
    def measured_caveat(self) -> str:
        return MEASURED_CAVEAT

    @property
    def unlisted_note(self) -> str:
        """Always present, whether or not anything looks missing.

        An unlisted room is never enumerated here, so the listing's silence
        about one is not evidence. Shown on every snapshot rather than only
        when something seems wrong, because a note nobody ever sees is a note
        that is not there.
        """
        return UNLISTED_NEVER_LISTED


@dataclass(frozen=True, slots=True)
class RoomMessage:
    """One stored message, as it arrived, swept for display."""

    seq: int
    ts: str
    author: AuthorDescription
    text: str

    @property
    def authority(self) -> AuthorityLevel:
        return CONTENT_AUTHORITY


@dataclass(frozen=True, slots=True)
class RoomMessagesSnapshot:
    """One room's newest messages, as read once, at one moment."""

    #: The room this build **asked for**, after the write path's policy. Every
    #: identity, reference and sentence downstream is built from this value
    #: and never from what the reply claimed.
    room: str
    #: What the reply's own ``room`` field said. Equal to :attr:`room` by
    #: construction - a disagreement refuses the document - and kept as a
    #: separate, separately-named value so that the equality is a fact on the
    #: object rather than an assumption in a reader's head.
    reported_room: str
    messages: tuple[RoomMessage, ...]
    #: The service's ``count``. Read, never assumed.
    reported_count: int
    #: The service's ``last_seq``. Read, never assumed.
    last_seq: int
    #: The service's ``first_seq``. May be ``null`` on an empty room.
    first_seq: int | None
    #: The cursor this read was made with, or ``None``.
    since: int | None
    staleness: StalenessNote
    ring_drop: RingDropNotice | None
    sha256: str

    @property
    def received_count(self) -> int:
        """How many messages actually arrived, counted here."""
        return len(self.messages)

    @property
    def count_disagreement(self) -> str:
        """Empty when the two counts agree; a sentence when they do not.

        Not resolved into one number on purpose. ``count`` is the service's
        answer and the array length is ours; when they differ, the honest
        report is that they differ.
        """
        if self.reported_count == self.received_count:
            return ""
        return (
            f"Sunucu 'count' alaninda {self.reported_count} diyor, gelen dizide "
            f"{self.received_count} kayit var. Iki sayi ayri ayri "
            "gosteriliyor; hangisinin dogru oldugu buradan bilinemez."
        )


def _object(payload: bytes, *, max_bytes: int) -> dict[str, Any]:
    try:
        return loads_strict(payload, max_bytes=max_bytes)
    except StrictJsonError as exc:
        raise SnapshotParseError(f"belge ayristirilamadi: {exc}") from exc


def _int_or_refuse(document: dict[str, Any], key: str) -> int:
    """Read an integer, refusing a ``bool``.

    ``isinstance(True, int)`` is true in Python, so a document carrying
    ``"count": true`` would otherwise become the number 1 and be reported as a
    message count. Refused by type rather than coerced.
    """
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SnapshotParseError(
            f"'{key}' alani tam sayi olarak gelmedi; belge kullanilmiyor."
        )
    return value


def _optional_int_or_refuse(document: dict[str, Any], key: str) -> int | None:
    """The same, for a field the schema publishes as ``integer`` or ``null``."""
    if document.get(key) is None:
        return None
    return _int_or_refuse(document, key)


def _str_or_empty(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    return safe_display(value) if isinstance(value, str) else ""


def _untrusted_declaration(document: dict[str, Any]) -> UntrustedDeclaration:
    """Read the reply's own ``untrusted`` object, and say what it disagrees on.

    Absent is a real answer and gets recorded as one. It is not the same as a
    reply that carried the object and left this build's two fields out of it:
    the first says nothing, the second says something this build refuses to
    believe, and only the second produces a ``missing_fields`` entry.
    """
    build_fields = tuple(sorted(CALLER_WRITTEN_ROOM_FIELDS))
    raw = document.get("untrusted")
    if not isinstance(raw, dict):
        return UntrustedDeclaration(
            present=False,
            fields=(),
            note="",
            build_fields=build_fields,
            extra_fields=(),
            missing_fields=(),
            detail=(
                "Yanit kendi 'untrusted' bildirimini tasimadi. Cagiran "
                "tarafindan yazilan alanlar bu yapinin kendi listesinden "
                f"okundu: {', '.join(build_fields)}."
            ),
        )

    listed = raw.get("fields")
    names: list[str] = []
    if isinstance(listed, list):
        for item in listed:
            if not isinstance(item, str):
                continue
            shown = safe_display(item)[:MAX_MEASURED_CHARS]
            if shown and shown not in names:
                names.append(shown)
            if len(names) >= MAX_UNTRUSTED_FIELDS:
                break

    declared = tuple(names)
    extra = tuple(
        sorted(name for name in declared if name not in CALLER_WRITTEN_ROOM_FIELDS)
    )
    missing = tuple(sorted(CALLER_WRITTEN_ROOM_FIELDS - set(declared)))

    parts = [
        "Yanit, su alanlarin cagiran tarafindan yazildigini bildirdi: "
        f"{', '.join(declared) or 'hicbiri'}. Bu bildirim de ayni anonim "
        "yuzeyden gelen bir icerik oldugu icin tek basina esas alinmaz; "
        "guvenilmez kabul edilen alan kumesi, bu yapinin kendi listesiyle "
        f"({', '.join(build_fields)}) birlesimidir."
    ]
    if missing:
        parts.append(
            f"Yanit su alanlari bildirmedi: {', '.join(missing)}. Bu alanlar "
            "yine de cagiran tarafindan yazilmis sayilir; bir yanit "
            "guvenilmezler listesini daraltamaz."
        )
    if extra:
        parts.append(
            f"Yanit su alanlari da ekledi: {', '.join(extra)}. Bunlar servis "
            "olcumu olarak degil, cagiran metni olarak islenir."
        )

    return UntrustedDeclaration(
        present=True,
        fields=declared,
        note=_str_or_empty(raw, "note"),
        build_fields=build_fields,
        extra_fields=extra,
        missing_fields=missing,
        detail=" ".join(parts),
    )


def _measured_fields(
    entry: dict[str, Any], *, caller_written: frozenset[str]
) -> tuple[tuple[MeasuredField, ...], bool]:
    """Split the service's own numbers out of one listing entry.

    Structural rather than by name: the published item schema names no
    properties, so the only honest rule is "everything that is not
    caller-written". Bounded, because the document decides how many keys it
    has, and rendered rather than walked, because a recursive reader on an
    anonymous document is an unbounded one.
    """
    kept: list[MeasuredField] = []
    truncated = False
    for key, value in entry.items():
        if not isinstance(key, str) or key in caller_written:
            continue
        if len(kept) >= MAX_MEASURED_FIELDS:
            truncated = True
            break
        kept.append(
            MeasuredField(
                key=safe_display(key)[:MAX_MEASURED_CHARS],
                value=safe_display(value)[:MAX_MEASURED_CHARS],
            )
        )
    return tuple(kept), truncated


def parse_room_index(result: ScanFetchResult) -> RoomIndexSnapshot:
    """Parse the room overview.

    ``rooms`` entries are published as bare objects - the schema declares
    ``items: {"type": "object"}`` and names no properties. Nothing here reads
    an aggregate **by name**; the two fields the prose does name are read by
    name because the prose names them as the caller-written ones, and the rest
    of the entry is split off structurally into
    :attr:`RoomEntry.measured` with the keys the reply used.

    That split is the whole content of this function. Before it existed the
    entry's other fields were dropped, which left a listing that could say
    what a room is called and what a stranger wrote about it and nothing at
    all about whether anybody had been there.
    """
    document = _object(result.body, max_bytes=len(result.body))

    listed = document.get("rooms")
    if not isinstance(listed, list):
        raise SnapshotParseError("'rooms' alani dizi olarak gelmedi.")

    untrusted = _untrusted_declaration(document)
    # The union, and it runs one way. ``extra_fields`` widens what counts as
    # caller-written; nothing narrows it.
    caller_written = CALLER_WRITTEN_ROOM_FIELDS | set(untrusted.fields)

    entries: list[RoomEntry] = []
    for item in listed[:MAX_ROOMS]:
        if not isinstance(item, dict):
            raise SnapshotParseError("Oda kaydi nesne olarak gelmedi.")
        name = _str_or_empty(item, "room")
        if not name:
            # A listing entry with no name addresses nothing. Skipped rather
            # than kept with a placeholder, which would be a room this build
            # invented.
            continue
        measured, measured_truncated = _measured_fields(
            item, caller_written=frozenset(caller_written)
        )
        entries.append(
            RoomEntry(
                name=name,
                topic=_str_or_empty(item, "topic"),
                measured=measured,
                measured_truncated=measured_truncated,
            )
        )

    return RoomIndexSnapshot(
        rooms=tuple(entries),
        total=_int_or_refuse(document, "total"),
        staleness=staleness_note(result.read_at),
        sha256=result.sha256,
        untrusted=untrusted,
    )


def parse_room_messages(
    result: ScanFetchResult,
    *,
    requested_room: str,
    since: int | None = None,
) -> RoomMessagesSnapshot:
    """Parse one room's messages, for the room that was actually requested.

    ``room``, ``count``, ``last_seq`` and ``messages`` are the schema's
    required fields and all four are read. ``first_seq`` is optional in the
    schema and optional here, which is what makes the ring-drop notice
    absent rather than wrong on an empty room.

    ``requested_room`` is **required** and it is the resolved, policy-checked
    name from :class:`~station_api.workscan.targets.RoomScanTarget`. It is not
    a default with a fallback to the reply's own field: a default is a way of
    forgetting, and forgetting here hands the scan's scope to the document.
    See the module docstring for why a mismatch is refused rather than
    relabelled.
    """
    if not requested_room:
        raise SnapshotParseError(
            "Anlik goruntu, istenen oda adi olmadan ayristirilamaz."
        )

    document = _object(result.body, max_bytes=len(result.body))

    room = document.get("room")
    if not isinstance(room, str) or not room:
        raise SnapshotParseError("'room' alani metin olarak gelmedi.")

    if room != requested_room:
        # Deliberately does not echo the claimed name: the whole point of the
        # check is that a reply must not get to put a room name on our screen.
        raise SnapshotParseError(
            f"Yanit, istenen '{requested_room}' odasindan baska bir odayi "
            "adlandiriyor; belge kullanilmiyor. Okunan icerigin hangi odaya "
            "ait oldugu bilinemez."
        )

    listed = document.get("messages")
    if not isinstance(listed, list):
        raise SnapshotParseError("'messages' alani dizi olarak gelmedi.")

    messages: list[RoomMessage] = []
    for item in listed[:MAX_MESSAGES]:
        if not isinstance(item, dict):
            raise SnapshotParseError("Mesaj kaydi nesne olarak gelmedi.")
        seq = _int_or_refuse(item, "seq")
        text = _str_or_empty(item, "text")[:MAX_TEXT_CHARS]
        messages.append(
            RoomMessage(
                seq=seq,
                ts=_str_or_empty(item, "ts"),
                author=describe_author(
                    item["from"] if isinstance(item.get("from"), str) else ""
                ),
                text=text,
            )
        )

    first_seq = _optional_int_or_refuse(document, "first_seq")

    return RoomMessagesSnapshot(
        # The requested name, not ``safe_display(room)``: it has already been
        # through the write path's policy and its own published pattern, so it
        # carries nothing to sweep and nothing a reply chose.
        room=requested_room,
        reported_room=requested_room,
        messages=tuple(messages),
        reported_count=_int_or_refuse(document, "count"),
        last_seq=_int_or_refuse(document, "last_seq"),
        first_seq=first_seq,
        since=since,
        staleness=staleness_note(result.read_at),
        ring_drop=ring_drop_notice(since=since, first_seq=first_seq),
        sha256=result.sha256,
    )


__all__ = [
    "MAX_MEASURED_CHARS",
    "MAX_MEASURED_FIELDS",
    "MAX_MESSAGES",
    "MAX_ROOMS",
    "MAX_TEXT_CHARS",
    "MAX_UNTRUSTED_FIELDS",
    "MeasuredField",
    "RingDropNotice",
    "RoomEntry",
    "RoomIndexSnapshot",
    "RoomMessage",
    "RoomMessagesSnapshot",
    "StalenessNote",
    "UntrustedDeclaration",
    "parse_room_index",
    "parse_room_messages",
    "ring_drop_notice",
    "staleness_note",
]
