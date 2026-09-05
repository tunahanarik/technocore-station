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
from pathlib import Path

from station_api.agent import workspace
from station_api.agent.errors import WorkspaceError
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
from station_api.workscan.discovery import (
    DiscoveryLog,
    discovery_target,
    parse_discovery,
)
from station_api.workscan.errors import (
    CandidateError,
    ScanTargetError,
    WorkScanError,
)
from station_api.workscan.kibble import ADAPTERS, AdapterRecord
from station_api.workscan.language import DERIVATION_HONESTY_SENTENCE
from station_api.workscan.request_file import (
    REQUEST_FILE_NAME,
    render_request_file,
)
from station_api.workscan.snapshot import (
    RoomIndexSnapshot,
    RoomMessagesSnapshot,
    StalenessNote,
    parse_room_index,
    parse_room_messages,
)
from station_api.workscan.targets import (
    DEFAULT_LIMIT,
    RoomScanTarget,
    resolve_room_target,
)

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


#: Said when the request file was written. Carries the name, because the name
#: is what a person needs in order to open the file themselves and see exactly
#: what the model was given.
REQUEST_FILE_WRITTEN = (
    "Istegin tam metni gorevin calisma alanina '{name}' adiyla yazildi "
    "({byte_count} bayt, ozet {sha256}). Model bu dosyayi mevcut okuma "
    "araciyla okur; dosyanin icinde metnin bir yabanci tarafindan yazildigi "
    "ve veri oldugu yazilidir."
)

#: Said when this build has no workspace root to write into at all.
#:
#: Reachable: :class:`WorkScanService` is built unconditionally at startup,
#: and a data directory is not part of what "unconditionally" needs. A
#: suggestion opened in that state is a real task with a real content digest
#: and no readable text behind it, which is a fact worth one sentence rather
#: than an empty workspace a reader has to interpret.
REQUEST_FILE_UNAVAILABLE = (
    "Istegin tam metni yazilamadi: bu yapida gorev calisma alani kokune "
    "erisim yok. Gorev acildi ve icerik ozeti dogrudur, fakat modelin "
    "okuyabilecegi bir istek dosyasi yoktur. Metni odayi yeniden tarayarak "
    "gorebilirsiniz."
)

#: Said when the workspace refused the write, with the workspace's own reason.
#:
#: The reason code travels because it is the difference between problems with
#: different answers: ``workspace_reparse_point`` is somebody's junction on
#: this machine, ``workspace_file_too_large`` is a ceiling, and a reader who
#: is only told "it failed" cannot tell those apart.
REQUEST_FILE_REFUSED = (
    "Istegin tam metni yazilamadi (neden: {reason}). Gorev acildi ve icerik "
    "ozeti dogrudur, fakat modelin okuyabilecegi bir istek dosyasi yoktur. "
    "Calisma alaninin kendi aciklamasi: {detail}"
)


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    """One suggestion: the task that was opened, and what reached the model.

    Two fields rather than one, and neither is a boolean. The task is a row
    that exists; the request file is a write that may not have happened, and
    the difference between "a model can read this request" and "a model can
    read this request's title" is the difference this whole change is about.
    A caller that only rendered :attr:`task` would be showing the state of the
    row and saying nothing about what is behind it - which is exactly the
    silence the defect lived in.
    """

    task: TaskView
    #: The file's name, or ``""`` when nothing was written. Never a name that
    #: is not on disk: it is taken from the workspace's own return value.
    request_file: str
    #: One sentence, always present, whichever way the write went.
    request_file_detail: str


@dataclass(frozen=True, slots=True)
class RoomFailure:
    """One room that could not be read, named, with its reason."""

    room: str
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class RoomNote:
    """A fact about a room that changes what reading it means.

    Not a failure and not a refusal: the room was read. It is a sentence the
    scan owes a person about *which* room they chose, and it exists because
    the read path used to owe it and never said it. ``RoomScanTarget`` has
    carried :attr:`~station_api.workscan.targets.RoomScanTarget.is_unlisted`
    and ``is_ephemeral`` since Package H1 and **no caller read either one** -
    the write path warns about both on every send, and the read path dropped
    them on the floor.
    """

    room: str
    #: ``unlisted`` or ``ephemeral``. A closed set, from the room's class
    #: markers, never from anything a reply said.
    kind: str
    detail: str


#: What is said about a room whose name is not in any listing. Not a refusal:
#: a name somebody already knows is theirs to read. What was missing is that
#: the product never said which kind of room the person was pointing at.
UNLISTED_ROOM_NOTE = (
    "Bu oda listelenmez: oda listesinde ve kesif gunlugunde hicbir zaman "
    "gorunmez, yani bu adi baska bir yerden ogrendiniz. Adi bilen herkes "
    "okuyabilir; ad bir sirdir, erisim denetimi degildir."
)

#: What is said about an ephemeral room.
EPHEMERAL_ROOM_NOTE = (
    "Bu oda gecicidir: mesajlar okuma aninda suresi dolmus sayilabilir. "
    "Burada bir satirin gorunmemesi, o satirin hic yazilmadigi anlamina "
    "gelmez."
)


def room_notes(target: RoomScanTarget) -> tuple[RoomNote, ...]:
    """The facts a room's own class markers carry, as sentences.

    Built from the resolved target, so the markers came from the live
    manifest check and not from a prefix somebody eyeballed.
    """
    notes: list[RoomNote] = []
    if target.is_unlisted:
        notes.append(
            RoomNote(room=target.room, kind="unlisted", detail=UNLISTED_ROOM_NOTE)
        )
    if target.is_ephemeral:
        notes.append(
            RoomNote(room=target.room, kind="ephemeral", detail=EPHEMERAL_ROOM_NOTE)
        )
    return tuple(notes)


@dataclass(frozen=True, slots=True)
class ScanResult:
    """One scan of one user-chosen room set."""

    started_at: datetime
    completed_at: datetime
    #: The rooms the caller asked for, after the room policy.
    rooms: tuple[str, ...]
    results: tuple[DerivationResult, ...]
    failures: tuple[RoomFailure, ...]
    #: What each scanned room's class markers mean for what was read.
    notes: tuple[RoomNote, ...] = ()
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
    #: The last discovery-log read, if a person asked for one this process.
    #: ``None`` until then: reading the surface contacts nobody, and a log
    #: that appeared without a request would be an automatic scan.
    discovery: DiscoveryLog | None
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
        data_dir: Path | None = None,
    ) -> None:
        self._client = client if client is not None else RoomScanClient()
        self._tasks = tasks
        # The same root the agent writes under, passed the way
        # ``ProofService`` takes it and for the same reason: this is not a
        # second file lane, it is the root that
        # :mod:`station_api.agent.workspace`'s containment, reparse walk and
        # ceilings are applied under. ``None`` means this build has no
        # workspace to write into, which is a state a caller is *told* about
        # rather than one that produces an empty directory.
        self._data_dir = data_dir
        self._room_index: RoomIndexSnapshot | None = None
        self._discovery: DiscoveryLog | None = None
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
            discovery=self._discovery,
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

    def refresh_discovery(
        self,
        *,
        markers: frozenset[str],
        since: int | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> DiscoveryLog:
        """Read the discovery log once, because a person asked.

        One request, inside the request that asked for it. ``since`` is a
        cursor the **caller** supplies from the previous read's ``last_seq``:
        this class deliberately does not remember one, because a remembered
        cursor turns "read the rest" into a loop somebody schedules, and there
        is no scheduler in this package (SI-272, ADR-0007 4).

        A failure raises rather than returning an empty log. An empty
        discovery log means "no new rooms were announced", and a log this
        build could not read must never be able to say that.
        """
        target = discovery_target(markers=markers)
        result = self._client.fetch_room_messages(target, since=since, limit=limit)
        log = parse_discovery(
            parse_room_messages(result, requested_room=target.room, since=since),
            markers=markers,
        )
        self._discovery = log
        return log

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
        notes: list[RoomNote] = []

        for name in wanted:
            try:
                target, snapshot = self._read_room(name, markers=markers, limit=limit)
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
            # Said about a room that *was* read, and only after it was. A note
            # attached before the read would describe a room this scan never
            # reached.
            notes.extend(room_notes(target))

        result = ScanResult(
            started_at=started_at,
            completed_at=datetime.now(UTC),
            rooms=tuple(scanned),
            results=tuple(results),
            failures=tuple(failures),
            notes=tuple(notes),
        )
        self._last_scan = result
        # Replaced, not merged. A candidate that is no longer in the newest
        # reading of a room must not remain selectable from an older one.
        self._candidates = {
            candidate.id: candidate for candidate in result.candidates
        }
        return result

    # --- the one write, and it is local ------------------------------------

    def suggest(self, candidate_id: str) -> SuggestionResult:
        """Turn one candidate into a local task in ``suggested``.

        Two writes now, and both are local: a row in this machine's own
        database, and one file in that task's own workspace. It still sends
        nothing, approves nothing and does not move the task forward - the
        walk from ``suggested`` to ``awaiting_approval`` is the user's,
        through the task service's own transition (ADR-0007 7, 8).

        The file is the repair for a measured defect: the row records
        ``content_sha256`` and drops the bytes, so a model was being asked to
        help with a request it could only see the title of. It goes into the
        workspace rather than into a new column because the workspace is the
        surface whose name allow-list, containment, reparse walk, ceilings and
        secret coverage already exist - see
        :mod:`station_api.workscan.request_file`.

        **The task still opens when the file cannot be written.** The row and
        its first state transition are written before the file - the workspace
        is addressed by the task id, so there is no id to write under until
        the row exists - and this product has no way to un-write them: a task
        is a state machine with an audit trail and there is no delete. Raising
        here would leave a real task in ``suggested`` while telling the caller
        the suggestion failed, which is worse than the honest answer. So the
        refusal travels on :class:`SuggestionResult` instead, in a field of
        its own, and the caller shows it. ``content_sha256`` and
        ``source_version_id`` are untouched by any of this: what a failed
        write costs is readability, not identity.
        """
        if self._tasks is None:
            raise WorkScanError(
                "Gorev katmani kullanilabilir degil; oneri kaydedilemez."
            )
        candidate = self.candidate(candidate_id)
        try:
            view = self._tasks.suggest_task(
                module_id=SCAN_MODULE_ID,
                source=SCAN_SOURCE_ID,
                content=candidate_content(candidate),
                title=candidate.source.quote[:MAX_TITLE_CHARS],
            )
        except TaskError as exc:
            raise CandidateError(str(exc)) from exc

        name, detail = self._write_request_file(view.id, candidate)
        return SuggestionResult(
            task=view, request_file=name, request_file_detail=detail
        )

    def _write_request_file(
        self, task_id: str, candidate: WorkCandidate
    ) -> tuple[str, str]:
        """Write the request into the task's workspace, or say why not.

        Returns ``("", <sentence>)`` on every failure and never re-raises: see
        :meth:`suggest` for why a failure here cannot be allowed to discard a
        task that already exists.

        ``OSError`` is caught beside :class:`WorkspaceError` because the two
        cover different halves of the same event. ``WorkspaceError`` is this
        product's own refusal - a name, a link, a ceiling - and ``OSError`` is
        the machine's: a full disk, a denied ACL, a path the filesystem would
        not take. Only ``strerror`` is carried out of it, never ``filename``,
        so the sentence says what went wrong without printing a path into a
        response body.
        """
        if self._data_dir is None:
            return "", REQUEST_FILE_UNAVAILABLE
        try:
            directory = workspace.ensure_workspace(self._data_dir, task_id)
            written = workspace.write_text(
                directory,
                REQUEST_FILE_NAME,
                render_request_file(candidate),
                replace_existing=False,
            )
        except WorkspaceError as exc:
            return "", REQUEST_FILE_REFUSED.format(
                reason=exc.reason, detail=str(exc)
            )
        except OSError as exc:
            return "", REQUEST_FILE_REFUSED.format(
                reason=type(exc).__name__,
                detail=exc.strerror or "isletim sistemi bir aciklama vermedi.",
            )
        return written.name, REQUEST_FILE_WRITTEN.format(
            name=written.name,
            byte_count=written.byte_count,
            sha256=written.sha256[:12],
        )

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
    ) -> tuple[RoomScanTarget, RoomMessagesSnapshot]:
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
        #
        # The target travels back with the snapshot because its class markers
        # are a fact about the room a person chose, and they were being thrown
        # away here.
        return target, parse_room_messages(result, requested_room=target.room)


__all__ = [
    "EPHEMERAL_ROOM_NOTE",
    "MAX_ROOMS_PER_SCAN",
    "MAX_TITLE_CHARS",
    "REQUEST_FILE_REFUSED",
    "REQUEST_FILE_UNAVAILABLE",
    "REQUEST_FILE_WRITTEN",
    "SCAN_MODULE_ID",
    "SCAN_SOURCE_ID",
    "UNLISTED_ROOM_NOTE",
    "RoomFailure",
    "RoomNote",
    "ScanResult",
    "SuggestionResult",
    "WorkScanService",
    "WorkScanView",
    "room_notes",
]
