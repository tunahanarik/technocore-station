"""The work-scan service: user-driven, one request at a time, no timers.

What this class deliberately does not have
------------------------------------------
No ``start()``, no ``schedule()``, no thread, no ``asyncio`` task, no interval
and no ``wait`` parameter anywhere beneath it. Every outbound request happens
inside a method a route called because a person pressed something, and the
method returns when that request returns (ADR-0007 4). Building the service
contacts nobody; reading its state contacts nobody. A test counts the
attempts rather than trusting this paragraph, which is Package F's rule for
exactly this claim.

The scope is the room set the user chose
-----------------------------------------
:meth:`WorkScanService.scan` takes the rooms as an argument. There is no
"scan everything" call, and the room overview is a *separate*, also explicit,
read whose only purpose is to give a person a list to choose from. The whole
room universe is never walked: the charter left a full room explorer to a
later stage, and a scan that quietly enumerated every public room would be
that explorer with no UI.

Every room name goes through the write path's policy
-----------------------------------------------------
Including ``DENIED_ROOMS``. Station does not read Lobby either: a scan is
still a request naming that room, and the room INV-05 names is not a target
for any capability (ADR-0007 3, 11).

Failures are per room, and a failed room is never an empty room
----------------------------------------------------------------
One room that times out does not fail the scan; it is reported by name with
its reason. The distinction matters more here than anywhere else in this
product: "we read this room and found nothing" and "we could not read this
room" look identical in a candidate list, and only one of them means there is
nothing to do.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from station_api.modules.registry import ModuleId
from station_api.tasks.service import TaskError, TaskService, TaskView
from station_api.tasks.sources import TaskSourceId
from station_api.workscan.candidates import (
    CandidateCapability,
    DerivationResult,
    RefusedLine,
    WorkCandidate,
    candidate_content,
    capability_for,
    derive_from_room,
)
from station_api.workscan.client import RoomScanClient
from station_api.workscan.errors import (
    CandidateError,
    ScanTargetError,
    WorkScanError,
)
from station_api.workscan.kibble import ADAPTERS, AdapterRecord
from station_api.workscan.language import DERIVATION_HONESTY_SENTENCE
from station_api.workscan.snapshot import (
    RoomIndexSnapshot,
    RoomMessagesSnapshot,
    StalenessNote,
    parse_room_index,
    parse_room_messages,
)
from station_api.workscan.targets import DEFAULT_LIMIT, resolve_room_target

#: Most rooms one scan will read, whatever the caller asked for. A bound on a
#: single user action: a scan is several sequential HTTP reads against a rate
#: limited service, and a request naming two hundred rooms would be a
#: crawl wearing a button.
MAX_ROOMS_PER_SCAN = 10

#: Longest title carried onto a suggested task. Bounded here as well as in the
#: task service, because the value is remote content either way.
MAX_TITLE_CHARS = 120

#: The module a scanned candidate is filed under. Compile-time, never derived
#: from what a room said.
SCAN_MODULE_ID = ModuleId.WORK_SCAN

#: The task source every suggestion carries. Also compile-time.
SCAN_SOURCE_ID = TaskSourceId.PUBLIC_ROOM_SCAN


@dataclass(frozen=True, slots=True)
class RoomFailure:
    """One room that could not be read, named, with its reason."""

    room: str
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    """One scan of one user-chosen room set."""

    started_at: datetime
    completed_at: datetime
    #: The rooms the caller asked for, after the room policy.
    rooms: tuple[str, ...]
    results: tuple[DerivationResult, ...]
    failures: tuple[RoomFailure, ...]
    honesty: str = DERIVATION_HONESTY_SENTENCE

    @property
    def candidates(self) -> tuple[WorkCandidate, ...]:
        return tuple(
            candidate for result in self.results for candidate in result.candidates
        )

    @property
    def refusals(self) -> tuple[RefusedLine, ...]:
        return tuple(refusal for result in self.results for refusal in result.refusals)


@dataclass(frozen=True, slots=True)
class WorkScanView:
    """The scan surface as it stands. Built without contacting anybody."""

    #: Never ``None`` in a useful sense: the sentence is shown on every read,
    #: not only beside a result.
    honesty: str
    adapters: tuple[AdapterRecord, ...]
    #: The last room overview, if a person asked for one this process.
    room_index: RoomIndexSnapshot | None
    #: The last scan, if a person ran one this process.
    last_scan: ScanResult | None
    #: The compile-time capability reading, so a user can see before scanning
    #: whether anything could be acted on afterwards.
    capability: CandidateCapability

    @property
    def staleness(self) -> StalenessNote | None:
        return self.room_index.staleness if self.room_index is not None else None


class WorkScanService:
    """Reads public rooms when asked to, and derives candidates from what it read.

    ``client`` and ``tasks`` arrive through the constructor - the
    ``ComposeService`` pattern - and this class creates neither. It holds the
    last overview and the last scan **in memory** on purpose: a scan is a
    momentary reading of a ring buffer that drops history, and persisting one
    would create a stored list of "open work" that goes quietly wrong the
    moment the rooms move on. What is persisted is only what a person
    explicitly turned into a task.
    """

    def __init__(
        self,
        *,
        client: RoomScanClient | None = None,
        tasks: TaskService | None = None,
    ) -> None:
        self._client = client if client is not None else RoomScanClient()
        self._tasks = tasks
        self._room_index: RoomIndexSnapshot | None = None
        self._last_scan: ScanResult | None = None
        self._candidates: dict[str, WorkCandidate] = {}

    # --- reads that contact nobody -----------------------------------------

    def describe(self, *, write_gate_open: bool = False) -> WorkScanView:
        """The whole surface, read-only. Makes no outbound request.

        ``write_gate_open`` is passed in rather than read here: the gate
        belongs to the identity service and this class does not own a second
        copy of it (ADR-0004 2). Its default is the closed answer, so a caller
        that forgot to supply it gets the conservative reading.
        """
        return WorkScanView(
            honesty=DERIVATION_HONESTY_SENTENCE,
            adapters=ADAPTERS,
            room_index=self._room_index,
            last_scan=self._last_scan,
            capability=capability_for(
                SCAN_MODULE_ID, write_gate_open=write_gate_open
            ),
        )

    def candidate(self, candidate_id: str) -> WorkCandidate:
        """One candidate from the last scan, or a refusal.

        Looked up by identity rather than by index, so a stale identifier from
        a previous scan is a refusal instead of a different candidate.
        """
        found = self._candidates.get(candidate_id)
        if found is None:
            raise CandidateError(
                "Bu aday son taramada yok. Adaylar saklanmaz; odayi yeniden "
                "taramaniz gerekir."
            )
        return found

    # --- reads that a person asked for -------------------------------------

    def refresh_room_index(self, *, limit: int = DEFAULT_LIMIT) -> RoomIndexSnapshot:
        """Read the room overview once, because a person asked.

        Kept separate from :meth:`scan` so that "show me what is out there"
        and "read these rooms" are two decisions a user makes, rather than one
        button that does both and therefore always reads everything.
        """
        result = self._client.fetch_room_index(limit=limit)
        snapshot = parse_room_index(result)
        self._room_index = snapshot
        return snapshot

    def scan(
        self,
        rooms: Sequence[str],
        *,
        markers: frozenset[str],
        write_gate_open: bool = False,
        limit: int = DEFAULT_LIMIT,
    ) -> ScanResult:
        """Read the rooms the user chose, once each, and derive candidates.

        ``markers`` comes from the live manifest check, exactly as the
        composer's does, and an empty set means no successful check has run -
        in which case every room is refused rather than resolved against a
        convention nothing verified.
        """
        started_at = datetime.now(UTC)
        capability = capability_for(SCAN_MODULE_ID, write_gate_open=write_gate_open)

        wanted, dropped = self._bounded(rooms)
        results: list[DerivationResult] = []
        failures: list[RoomFailure] = [
            RoomFailure(
                room=name,
                reason="scan_bound",
                detail=(
                    f"Tek bir taramada en cok {MAX_ROOMS_PER_SCAN} oda "
                    "okunur. Bu oda okunmadi; kalan odalari ayri bir "
                    "taramayla secebilirsiniz."
                ),
            )
            for name in dropped
        ]
        scanned: list[str] = []

        for name in wanted:
            try:
                snapshot = self._read_room(name, markers=markers, limit=limit)
            except ScanTargetError as exc:
                failures.append(
                    RoomFailure(room=name, reason="room_refused", detail=str(exc))
                )
                continue
            except WorkScanError as exc:
                failures.append(
                    RoomFailure(room=name, reason="room_unreadable", detail=str(exc))
                )
                continue

            # Derivation is inside the per-room guard as well, and not only
            # the read. A single unusable line - one with no ``ts``, say -
            # raises ``CandidateError``, and outside this ``try`` that one
            # line would have thrown away every room already read in the same
            # scan and left the route with an unhandled exception. Per-line
            # refusals are handled inside ``derive_from_room``; this is the
            # backstop for anything it does not anticipate, so that "failures
            # are per room" holds on the derivation half too.
            try:
                derived = derive_from_room(snapshot, capability=capability)
            except CandidateError as exc:
                failures.append(
                    RoomFailure(
                        room=name, reason="room_underivable", detail=str(exc)
                    )
                )
                continue

            scanned.append(snapshot.room)
            results.append(derived)

        result = ScanResult(
            started_at=started_at,
            completed_at=datetime.now(UTC),
            rooms=tuple(scanned),
            results=tuple(results),
            failures=tuple(failures),
        )
        self._last_scan = result
        # Replaced, not merged. A candidate that is no longer in the newest
        # reading of a room must not remain selectable from an older one.
        self._candidates = {
            candidate.id: candidate for candidate in result.candidates
        }
        return result

    # --- the one write, and it is local ------------------------------------

    def suggest(self, candidate_id: str) -> TaskView:
        """Turn one candidate into a local task in ``suggested``.

        This is the only thing in the package that writes anything, and what
        it writes is a row in this machine's own database. It sends nothing,
        approves nothing and does not move the task forward: the walk from
        ``suggested`` to ``awaiting_approval`` is the user's, through the task
        service's own transition (ADR-0007 7, 8).
        """
        if self._tasks is None:
            raise WorkScanError(
                "Gorev katmani kullanilabilir degil; oneri kaydedilemez."
            )
        candidate = self.candidate(candidate_id)
        try:
            return self._tasks.suggest_task(
                module_id=SCAN_MODULE_ID,
                source=SCAN_SOURCE_ID,
                content=candidate_content(candidate),
                title=candidate.source.quote[:MAX_TITLE_CHARS],
            )
        except TaskError as exc:
            raise CandidateError(str(exc)) from exc

    # --- internals ---------------------------------------------------------

    def _bounded(self, rooms: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """De-duplicate, keep the caller's order, and cap the count.

        Returns what will be read **and what was dropped**, because the drop
        is reported rather than silent: a scan that quietly read the first ten
        of twelve rooms would show a candidate list that looks like the answer
        for twelve.

        De-duplication is not tidiness either: reading the same room twice in
        one action would produce the same candidate identities twice and spend
        two requests from a per-IP read bucket to learn nothing.
        """
        seen: dict[str, None] = {}
        for name in rooms:
            if name not in seen:
                seen[name] = None
        ordered = tuple(seen)
        return ordered[:MAX_ROOMS_PER_SCAN], ordered[MAX_ROOMS_PER_SCAN:]

    def _read_room(
        self, room: str, *, markers: frozenset[str], limit: int
    ) -> RoomMessagesSnapshot:
        """Resolve, read once, parse. No cursor, and therefore no follow-up.

        ``since`` is deliberately not carried between scans. A cursor is the
        first half of polling: the moment this class remembered where it got
        to, "read the rest" becomes a loop somebody schedules. Each scan is a
        fresh bounded slice, and the ring-drop notice is what tells a user
        that history moved underneath them (ADR-0007 4, 5).
        """
        target = resolve_room_target(room, markers=markers)
        result = self._client.fetch_room_messages(target, limit=limit)
        # The resolved room, not the one the reply names. A snapshot's scope
        # is a decision this process made; see ``snapshot`` for what happens
        # when the document disagrees.
        return parse_room_messages(result, requested_room=target.room)


__all__ = [
    "MAX_ROOMS_PER_SCAN",
    "MAX_TITLE_CHARS",
    "SCAN_MODULE_ID",
    "SCAN_SOURCE_ID",
    "RoomFailure",
    "ScanResult",
    "WorkScanService",
    "WorkScanView",
]
