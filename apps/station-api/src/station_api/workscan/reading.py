"""What a model may say about a room's lines, and what it may never carry.

ADR-0014 opened the reading lane and this module is the seam it was opened
through. It holds the **types** that cross it and nothing that could make a
request: no client, no service, no prompt and no import of
:mod:`station_api.opencode`. The scan package keeps the property
``test_the_package_calls_no_model_and_imports_no_completion_path`` states -
it parses, sweeps, refuses and builds candidates, and somebody else spends the
money.

The seam is a Protocol, not a class
------------------------------------
:class:`LineReader` is structural. :class:`~station_api.workscan.service.
WorkScanService` names only this protocol, so the scan package cannot reach
the reader's module even by accident, and a build with no provider configured
simply has no reader - which is a state the scan is *told* about rather than
one that produces an empty candidate list.

What crosses, in each direction
--------------------------------
**Towards the model:** :class:`ReadableLine`, and it carries exactly two
fields - a sequence number and the message text. There is deliberately no
room name, no author, no timestamp and no task on it. A reader that wanted to
tell a provider which room these lines came from would have to invent the
value, because it is not given one (ADR-0014 5).

**Back:** :class:`LineVerdict`, and it carries a sequence number and one of
the four :class:`~station_api.workscan.candidates.SignalId` members. There is
no free-text field anywhere on the return path. The model chooses among four
shapes whose wording this product wrote; it does not write wording of its own
(ADR-0014 1).

A refusal is per line, and every declined line gets one
--------------------------------------------------------
:class:`ReadingRefusal` exists so that "the model read this line and found no
work" and "this line was never read" are different answers on the screen. The
scan surface already refuses to let those two collapse for a *room*
(``RoomFailure`` versus an empty result); a lane that spends a bounded number
of turns has the same problem one level down, because the ceiling stops the
reading in the middle of a room.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Protocol

from station_api.workscan.signals import SignalId

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from station_api.agent.model_calls import ScanModelCallCounter


#: Most lines one reading turn carries.
#:
#: Part of the seam rather than of the reader, because two packages need the
#: number for two different reasons: the reader batches by it, and the scan
#: surface has to tell a person what one turn covers **before** the turn is
#: spent (ADR-0014 6). One definition, so the sentence on the screen and the
#: batch in the request cannot drift apart.
#:
#: It is also the whole of "a room with many lines cannot cost many turns":
#: the batch grows to this and then the scan's ceiling - not the room - decides
#: whether there is another turn at all.
MAX_LINES_PER_TURN: Final = 60


class ReadingRefusalReason(StrEnum):
    """Why a line was not read, or why its turn's answer was not used.

    Four, and each one is a different sentence to a person. They are *not*
    prohibited work shapes and are deliberately not filed as ones: nobody
    asked for prohibited work here, the reading simply did not happen or did
    not come back usable.
    """

    #: This build has no reader at all - no provider connection, or no model
    #: selected. The lines were never sent anywhere.
    MODEL_UNAVAILABLE = "model_unavailable"
    #: The scan reached its model-call ceiling before these lines' turn. They
    #: were not sent, and nothing was spent on them.
    READING_CEILING = "reading_ceiling"
    #: The provider refused, failed, or never answered. The turn is counted
    #: only if an answer came back and was parsed - see the reader.
    MODEL_FAILED = "model_failed"
    #: An answer came back and this build would not use it: a tool name that
    #: is not in the closed registry, an argument that did not satisfy its
    #: declared type, or a line number that was not in the turn's own batch.
    #: The **whole turn** is dropped, never trimmed to the calls that happened
    #: to parse (``planner/service.py``'s rule).
    MODEL_REFUSED = "model_refused"


@dataclass(frozen=True, slots=True)
class ReadableLine:
    """One line as the reading lane may see it. Two fields, and that is all.

    The narrowness is the control. ADR-0014 5 says the provider must not
    become an oracle about the user, and the cheapest way to keep a value out
    of a request is not to hand it to the code that builds the request.
    """

    seq: int
    text: str


@dataclass(frozen=True, slots=True)
class LineVerdict:
    """One line the model said carries work, and which of the four shapes.

    ``signal`` is a :class:`SignalId`, so a verdict cannot name a fifth shape:
    the enum is closed and the reader resolves the model's answer through a
    compile-time registry before one of these is built.
    """

    seq: int
    signal: SignalId


@dataclass(frozen=True, slots=True)
class ReadingRefusal:
    """One line that was not read, or whose turn was not used, and why."""

    seq: int
    reason: ReadingRefusalReason
    detail: str


@dataclass(frozen=True, slots=True)
class RoomReading:
    """What the reading lane produced for one room's readable lines.

    ``model_calls_used`` is carried so the scan can report the spend beside
    the result. It is the reader's count for *this room*; the ceiling is the
    scan's, and it lives on the counter both sides share.
    """

    verdicts: tuple[LineVerdict, ...] = ()
    refusals: tuple[ReadingRefusal, ...] = ()
    model_calls_used: int = 0

    @property
    def by_sequence(self) -> dict[int, SignalId]:
        """The verdicts as a lookup. The first answer for a ``seq`` wins.

        First rather than last, and it matters: a turn that named the same
        line under two shapes has said two things, and taking the later one
        would silently prefer whichever the provider happened to serialise
        second.
        """
        found: dict[int, SignalId] = {}
        for verdict in self.verdicts:
            found.setdefault(verdict.seq, verdict.signal)
        return found


class LineReader(Protocol):
    """The one thing the scan asks of the reading lane.

    Structural rather than nominal so that
    :mod:`station_api.workscan.service` never imports the implementation.
    ``counter`` is the scan's own spend meter and is shared across the rooms
    of one scan, which is what makes the ceiling a bound on the *scan* rather
    than on each room separately.
    """

    def classify(
        self, lines: Sequence[ReadableLine], *, counter: ScanModelCallCounter
    ) -> RoomReading:  # pragma: no cover - protocol declaration
        ...


#: What is said about every line when this build has no reader.
#:
#: Named here rather than in the reader, because the reader is precisely what
#: does not exist in this state. A scan with no provider connection still
#: runs, still reads the rooms, still applies the prohibitions and still
#: reports every line - it simply proposes nothing, and says why.
MODEL_UNAVAILABLE_DETAIL = (
    "Bu satir bir modele okutulmadi: bu yapida bir saglayici baglantisi veya "
    "secili bir model yok. Satir okundu ve gosteriliyor; aday uretilmedi. "
    "Baglantiyi kurup modeli sectikten sonra taramayi tekrar calistirin."
)

__all__ = [
    "MAX_LINES_PER_TURN",
    "MODEL_UNAVAILABLE_DETAIL",
    "LineReader",
    "LineVerdict",
    "ReadableLine",
    "ReadingRefusal",
    "ReadingRefusalReason",
    "RoomReading",
]
