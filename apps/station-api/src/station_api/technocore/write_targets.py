"""The closed registry of write targets.

Separate from :mod:`station_api.technocore.sources` on purpose, and the
separation is a security boundary rather than tidiness. The read registry
enumerates six public documents and is what the monitoring check may touch;
this one enumerates the single lane a user-approved message may be POSTed to.
Neither can grow into the other by accident, and a bug in the read path
cannot produce a write address (uctan uca prompt 8: "public read ve explicit
write kabiliyetleri ayri kapali registry/policy tasisin").

One lane, and only one
----------------------
``POST /r/{room}``. The note lane is deliberately absent: the pinned protocol
accepts a signed note only in the ``room-owners`` and ``room-allow``
namespaces, and the DID profile note the charter asks for is published on the
*unsigned* lane, which produces no signature evidence. Shipping a send button
for it would mean presenting an unsigned write as signed. See ADR-0002 1.

Room names are checked against the live convention
--------------------------------------------------
The reference builds room semantics out of leading ``<class>-`` markers, and
which markers exist is published by the manifest under
``conventions.room_classes``. This module reads them from there rather than
guessing: the markers are data, the *parsing rule* (a chain of leading
segments, stopping at the first segment that is not a marker) is the
reference's own algorithm, and a class the pinned reference did not define is
refused rather than treated as ordinary text - we would not know what a write
to it means.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from technocore_conform import InvalidNameError, validate_name

from station_api.technocore.sources import TECHNOCORE_ORIGIN

#: Production writes are POST. GET is not a fallback, hidden or otherwise:
#: Technocore's GET write lanes put the text in a URL, where it lands in
#: proxy logs and history, and the charter makes POST the default (ADR-011).
#:
#: Typed as a literal rather than a bare ``str`` so that widening it is a
#: type error at every call site, not a runtime surprise on one of them.
WRITE_METHOD: Final[Literal["POST"]] = "POST"

#: The one write path template. Formatted here and nowhere else.
MESSAGE_LANE_TEMPLATE = "/r/{room}"

#: The room classes the pinned reference defines (``store.ROOM_CLASSES``).
#: A live manifest that publishes a marker outside this set is publishing
#: semantics this build has never seen, so a room carrying it is refused.
UNDERSTOOD_ROOM_CLASSES = frozenset({"p", "mb", "d", "e"})

#: Rooms Station will never write to.
#:
#: The pinned reference calls these "the rendezvous points every agent is
#: told about" and hardcodes them as unownable (``store.UNOWNABLE_ROOMS``).
#: ADR-0002 4.1 requires ``lobby`` to be refused outright - it is the one
#: room INV-05 names, and the one where a mistaken write is most public.
#: ``meta`` is the same kind of front door and is refused with it.
DENIED_ROOMS = frozenset({"lobby", "meta"})


class RoomPolicyError(Exception):
    """A room is not a target Station will write to. Safe to show a user."""


@dataclass(frozen=True, slots=True)
class WriteTarget:
    """One resolved destination for one approved message."""

    room: str
    #: The class markers this room carries, in the order they appear.
    classes: tuple[str, ...]

    @property
    def method(self) -> Literal["POST"]:
        return WRITE_METHOD

    @property
    def path(self) -> str:
        return MESSAGE_LANE_TEMPLATE.format(room=self.room)

    @property
    def url(self) -> str:
        """The full, fixed URL. Built here and nowhere else."""
        return f"{TECHNOCORE_ORIGIN}{self.path}"

    @property
    def is_ephemeral(self) -> bool:
        """Messages here expire on read, so evidence of them is temporary."""
        return "e" in self.classes

    @property
    def is_mailbox(self) -> bool:
        """Signed writes only - which is the only kind Station sends."""
        return "mb" in self.classes

    @property
    def is_unlisted(self) -> bool:
        """The name is the only secret; it leaks wherever the name leaks."""
        return "p" in self.classes

    @property
    def is_ownable(self) -> bool:
        """An owner claim may gate writes, so a refusal here is expected."""
        return "d" in self.classes


def published_markers(conventions: Mapping[str, object] | None) -> frozenset[str]:
    """The class markers the live manifest publishes, as bare letters.

    The manifest spells them with the hyphen (``"mb-"``) because that is how
    they appear in a name. The trailing hyphen is stripped here so the
    parsing rule below compares segments, and anything that is not a
    ``"<letters>-"`` key is ignored rather than guessed at.
    """
    if not isinstance(conventions, Mapping):
        return frozenset()
    published = conventions.get("room_classes")
    if not isinstance(published, Mapping):
        return frozenset()
    return frozenset(
        key[:-1]
        for key in published
        if isinstance(key, str) and key.endswith("-") and key[:-1].isalpha()
    )


def classes_of(room: str, markers: frozenset[str]) -> tuple[str, ...]:
    """The leading class markers on a name, using the reference's rule.

    ``p-x`` -> ``("p",)``; ``mb-p-x`` -> ``("mb", "p")``; ``pastel`` -> ``()``.
    The final segment is always the body, never a class, so ``p-`` alone is
    still an unlisted room and a bare ``d`` is not an ownable one.
    """
    found: list[str] = []
    for segment in room.split("-")[:-1]:
        if segment not in markers:
            break
        found.append(segment)
    return tuple(found)


def resolve_message_target(room: str, *, markers: frozenset[str]) -> WriteTarget:
    """Validate a room name and resolve it to the message lane.

    Fail-closed at every step. ``markers`` comes from the live manifest and
    is empty when no successful check has run - in which case the write gate
    is already shut, and refusing here as well means the two cannot disagree.
    """
    if not markers:
        raise RoomPolicyError(
            "Oda sinifi konvansiyonu resmi manifest'ten okunamadi; hedef "
            "dogrulanamadigi icin gonderim yapilmaz."
        )

    try:
        name = validate_name(room, field="room")
    except InvalidNameError as exc:
        raise RoomPolicyError(
            "Oda adi resmi ad kalibina uymuyor: kucuk harf, rakam, '-' ve "
            "'_', 1-48 karakter, harf veya rakamla baslar."
        ) from exc

    if name in DENIED_ROOMS:
        raise RoomPolicyError(
            f"'{name}' odasi bir bulusma noktasidir ve Station bu odaya yazmaz."
        )

    classes = classes_of(name, markers)
    unknown = [item for item in classes if item not in UNDERSTOOD_ROOM_CLASSES]
    if unknown:
        raise RoomPolicyError(
            "Bu oda adi bu surumun tanimadigi bir oda sinifi tasiyor: "
            f"{', '.join(unknown)}. Yazmanin ne anlama geldigi bilinmiyor."
        )

    return WriteTarget(room=name, classes=classes)


__all__ = [
    "DENIED_ROOMS",
    "MESSAGE_LANE_TEMPLATE",
    "UNDERSTOOD_ROOM_CLASSES",
    "WRITE_METHOD",
    "RoomPolicyError",
    "WriteTarget",
    "classes_of",
    "published_markers",
    "resolve_message_target",
]
