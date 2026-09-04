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
    CONTENT_AUTHORITY,
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
class RoomEntry:
    """One room as the overview listed it.

    ``room`` and ``topic`` are caller-written strings the service re-emits;
    every other field on the wire is the service's own measurement. Only these
    two are kept, because they are the only two this build has a use for and
    keeping a measurement would invite a sentence that leans on it.
    """

    name: str
    topic: str

    @property
    def authority(self) -> AuthorityLevel:
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

    @property
    def kept_count(self) -> int:
        return len(self.rooms)

    @property
    def truncated(self) -> bool:
        """Whether this build kept fewer rooms than the service reported."""
        return self.total > self.kept_count


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

    room: str
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


def parse_room_index(result: ScanFetchResult) -> RoomIndexSnapshot:
    """Parse the room overview.

    ``rooms`` entries are published as bare objects - the schema declares
    ``items: {"type": "object"}`` and names no properties - so nothing here
    reads a field the prose did not name. The two the prose does name are the
    two caller-written ones, and those are the two kept.
    """
    document = _object(result.body, max_bytes=len(result.body))

    listed = document.get("rooms")
    if not isinstance(listed, list):
        raise SnapshotParseError("'rooms' alani dizi olarak gelmedi.")

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
        entries.append(RoomEntry(name=name, topic=_str_or_empty(item, "topic")))

    return RoomIndexSnapshot(
        rooms=tuple(entries),
        total=_int_or_refuse(document, "total"),
        staleness=staleness_note(result.read_at),
        sha256=result.sha256,
    )


def parse_room_messages(
    result: ScanFetchResult, *, since: int | None = None
) -> RoomMessagesSnapshot:
    """Parse one room's messages.

    ``room``, ``count``, ``last_seq`` and ``messages`` are the schema's
    required fields and all four are read. ``first_seq`` is optional in the
    schema and optional here, which is what makes the ring-drop notice
    absent rather than wrong on an empty room.
    """
    document = _object(result.body, max_bytes=len(result.body))

    room = document.get("room")
    if not isinstance(room, str) or not room:
        raise SnapshotParseError("'room' alani metin olarak gelmedi.")

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
        room=safe_display(room),
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
    "MAX_MESSAGES",
    "MAX_ROOMS",
    "MAX_TEXT_CHARS",
    "RingDropNotice",
    "RoomEntry",
    "RoomIndexSnapshot",
    "RoomMessage",
    "RoomMessagesSnapshot",
    "StalenessNote",
    "parse_room_index",
    "parse_room_messages",
    "ring_drop_notice",
    "staleness_note",
]
