"""Work-scan endpoints: read the surface, list rooms, scan a chosen set, suggest.

    GET  /api/workscan/status            the whole surface, read-only, contacts nobody
    POST /api/workscan/rooms/refresh     read the room overview, once, on request
    POST /api/workscan/discovery/refresh read the new-room log, once, on request
    POST /api/workscan/scan              read the rooms in the body, once each
    POST /api/workscan/suggest           open one candidate as a local suggested task

Every state-changing route inherits the global session, CSRF, Host, Origin
and Sec-Fetch-Site guards - they are middleware, so nothing in this file can
opt out.

What is deliberately absent
---------------------------
* **No scan-everything route.** ``scan`` takes the rooms in the body and the
  body is bounded, and the bound did not move when the rooms became pickable
  off a list instead of typed - a list to choose from is not a licence to scan
  the list. There is no endpoint that walks the room universe, and neither the
  overview nor the discovery log feeds a scan on its own (ADR-0007 4).
* **No write, and no route that could become one.** The discovery log is
  server-written; a client write there answers 403 and this build attempts
  none. Opening a room is a write to ``/r/{room}`` and needs the write gate's
  six preconditions, which is a different capability on a different surface -
  nothing in this file addresses it.
* **No polling parameter and no timer.** ``wait`` reaches no query this
  package builds, ``status`` makes no request, and nothing here schedules a
  follow-up. A client that wants newer data presses the button again.
* **No URL, host, path or room-template parameter.** A room *name* is
  accepted and it goes through the write path's policy, ``DENIED_ROOMS``
  included; nothing else about the address comes from the request.
* **No approval.** ``suggest`` opens a task in ``suggested``. Moving it to
  ``awaiting_approval`` is a separate act by the user, on the task surface.
* **No third-party score.** Nothing here reads, fetches or returns a
  ``score`` or ``rank`` from any external service (ADR-0007 1).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from station_api.dependencies import require_session
from station_api.identity.service import IdentityService
from station_api.schemas import (
    WorkScanAdapter,
    WorkScanAdapterFact,
    WorkScanAnnouncedRoom,
    WorkScanCandidate,
    WorkScanCapability,
    WorkScanDiscovery,
    WorkScanDiscoveryRequest,
    WorkScanEffort,
    WorkScanMeasuredField,
    WorkScanOpenState,
    WorkScanQuote,
    WorkScanRefreshRequest,
    WorkScanRefusal,
    WorkScanResult,
    WorkScanRingDrop,
    WorkScanRoom,
    WorkScanRoomFailure,
    WorkScanRoomIndex,
    WorkScanRoomNote,
    WorkScanRoomResult,
    WorkScanScanRequest,
    WorkScanStaleness,
    WorkScanStatusResponse,
    WorkScanSuggestRequest,
    WorkScanSuggestResponse,
    WorkScanUntrusted,
)
from station_api.security.sessions import Session
from station_api.technocore.service import TechnocoreService
from station_api.workscan.candidates import (
    CandidateCapability,
    DerivationResult,
    WorkCandidate,
)
from station_api.workscan.discovery import DiscoveryLog
from station_api.workscan.errors import CandidateError, ScanTargetError, WorkScanError
from station_api.workscan.kibble import AdapterRecord
from station_api.workscan.language import PROHIBITION_HONESTY_SENTENCE
from station_api.workscan.service import (
    RoomNote,
    ScanResult,
    WorkScanService,
    WorkScanView,
)
from station_api.workscan.snapshot import (
    RingDropNotice,
    RoomIndexSnapshot,
    StalenessNote,
    UntrustedDeclaration,
)
from station_api.workscan.targets import NEVER_SENT_PARAMS

router = APIRouter(prefix="/api/workscan")

CurrentSession = Annotated[Session, Depends(require_session)]

#: Scan state is local, momentary and never belongs in a cache.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

#: Stated in the payload rather than only in this docstring, so "there is no
#: polling" is a claim a client can check instead of a promise it must trust.
POLLING_STATEMENT = (
    "Bu yuzeyde zamanlayici, arka plan gorevi ve uzun bekleme (long-poll) "
    "yoktur. Her giden istek, bir kullanici eyleminin icinde ve bir kez "
    "yapilir; yenilemek icin islemi yeniden baslatmaniz gerekir."
)


def _service(request: Request) -> WorkScanService:
    service: WorkScanService | None = getattr(request.app.state, "workscan", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Is tarama yuzeyi kullanilabilir degil.",
            headers=_NO_STORE,
        )
    return service


def _write_gate_open(request: Request) -> bool:
    """The composer's gate, read from the service that owns it.

    Not re-derived here. A second gate is the duplication ADR-0004 2 rules out
    by name, and two gates are two things that can disagree about whether this
    machine may write.
    """
    identity: IdentityService | None = getattr(
        request.app.state, "identity_service", None
    )
    if identity is None:
        return False
    return bool(identity.write_gate_status().allowed)


def _markers(request: Request) -> frozenset[str]:
    """The room-class convention, from the last live manifest check.

    Empty when no successful check has run, which makes every room name a
    refusal rather than a name resolved against a convention nothing verified.
    """
    service: TechnocoreService | None = getattr(request.app.state, "technocore", None)
    if service is None:
        return frozenset()
    return frozenset(service.status().room_class_markers)


def _capability(value: CandidateCapability) -> WorkScanCapability:
    return WorkScanCapability(
        module_id=value.module_id,
        module_state=value.module_state,
        module_available=value.module_available,
        write_gate_open=value.write_gate_open,
        ready=value.ready,
        detail=value.detail,
    )


def _candidate(value: WorkCandidate) -> WorkScanCandidate:
    return WorkScanCandidate(
        id=value.id,
        signal=value.signal.value,
        source=WorkScanQuote(
            room=value.source.room,
            seq=value.source.seq,
            ts=value.source.ts,
            author=value.source.author,
            author_is_did_key=value.source.author_is_did_key,
            author_detail=value.source.author_detail,
            quote=value.source.quote,
            reference=value.source.reference,
        ),
        benefit=value.benefit,
        deliverable=value.deliverable,
        success_condition=value.success_condition,
        test_method=value.test_method,
        capability=_capability(value.capability),
        effort=WorkScanEffort(band=value.effort.band, basis=value.effort.basis),
        budget_detail=value.budget_detail,
        permissions=list(value.permissions),
        risks=list(value.risks),
        open_state=WorkScanOpenState(
            read_at=value.open_state.read_at, detail=value.open_state.detail
        ),
        derivation=value.derivation,
    )


def _room_result(value: DerivationResult) -> WorkScanRoomResult:
    return WorkScanRoomResult(
        room=value.room,
        candidates=[_candidate(item) for item in value.candidates],
        refusals=[
            WorkScanRefusal(
                room=item.room,
                seq=item.seq,
                # The reason, which for a prohibited work shape *is* that
                # shape's value. A line refused for a repeated sequence number
                # or a missing source coordinate carries its own reason
                # instead of being reported as prohibited work.
                shape=item.reason,
                detail=item.detail,
            )
            for item in value.refusals
        ],
        lines_read=value.lines_read,
    )


def _staleness(value: StalenessNote) -> WorkScanStaleness:
    return WorkScanStaleness(
        read_at=value.read_at,
        declared_cache_seconds=value.declared_cache_seconds,
        declared_by=value.declared_by,
        detail=value.detail,
    )


def _ring_drop(value: RingDropNotice) -> WorkScanRingDrop:
    return WorkScanRingDrop(
        since=value.since,
        expected_first=value.expected_first,
        first_seq=value.first_seq,
        detail=value.detail,
    )


def _untrusted(value: UntrustedDeclaration) -> WorkScanUntrusted:
    """The reply's own claim about its caller-written fields, carried whole.

    Both lists go on the wire and so do the two disagreements. Sending only
    the union would hide which side widened it, and sending only our own list
    would make the response silent about a reply that tried to narrow it.
    """
    return WorkScanUntrusted(
        present=value.present,
        fields=list(value.fields),
        note=value.note,
        build_fields=list(value.build_fields),
        extra_fields=list(value.extra_fields),
        missing_fields=list(value.missing_fields),
        detail=value.detail,
    )


def _room_index(value: RoomIndexSnapshot) -> WorkScanRoomIndex:
    """One listing, with the two halves of every entry kept apart.

    ``name``/``topic`` and ``measured`` are separate fields rather than one
    object with a caveat beside it, because the service's own warning is that
    the first two are strings a stranger chose and everything else is its own
    measurement. The caveats are read off the snapshot rather than imported
    here: one copy of a sentence is one thing that can be wrong.
    """
    return WorkScanRoomIndex(
        rooms=[
            WorkScanRoom(
                name=room.name,
                topic=room.topic,
                measured=[
                    WorkScanMeasuredField(key=field.key, value=field.value)
                    for field in room.measured
                ],
                measured_truncated=room.measured_truncated,
            )
            for room in value.rooms
        ],
        total=value.total,
        kept_count=value.kept_count,
        truncated=value.truncated,
        staleness=_staleness(value.staleness),
        sha256=value.sha256,
        room_name_caveat=value.room_name_caveat,
        topic_caveat=value.topic_caveat,
        measured_caveat=value.measured_caveat,
        unlisted_note=value.unlisted_note,
        untrusted=_untrusted(value.untrusted),
    )


def _discovery(value: DiscoveryLog) -> WorkScanDiscovery:
    """One read of the discovery log.

    ``selectable`` is computed on the record, not here: whether a line may
    become a one-click scan target is a property of how the line parsed, and a
    route that decided it a second time would be a second thing that can
    disagree with the parser about a room name.
    """
    return WorkScanDiscovery(
        room=value.room,
        entries=[
            WorkScanAnnouncedRoom(
                seq=entry.seq,
                ts=entry.ts,
                name=entry.name,
                line=entry.line,
                unusable_reason=entry.unusable_reason,
                selectable=entry.selectable,
            )
            for entry in value.entries
        ],
        since=value.since,
        last_seq=value.last_seq,
        first_seq=value.first_seq,
        lines_read=value.lines_read,
        selectable=list(value.selectable),
        unusable_count=value.unusable_count,
        ring_drop=(
            _ring_drop(value.ring_drop) if value.ring_drop is not None else None
        ),
        staleness=_staleness(value.staleness),
        sha256=value.sha256,
        room_name_caveat=value.room_name_caveat,
        unlisted_note=value.unlisted_note,
        write_refusal=value.write_refusal,
    )


def _room_note(value: RoomNote) -> WorkScanRoomNote:
    """A fact about a scanned room's class. Narrowed to the two kinds there are.

    ``kind`` is a ``Literal`` on the wire, so a record that grew a third kind
    fails validation here rather than reaching a client as a string nothing
    knows how to render.
    """
    if value.kind not in ("unlisted", "ephemeral"):  # pragma: no cover - constant
        raise RuntimeError(f"unknown room note kind: {value.kind}")
    kind: Literal["unlisted", "ephemeral"] = (
        "unlisted" if value.kind == "unlisted" else "ephemeral"
    )
    return WorkScanRoomNote(room=value.room, kind=kind, detail=value.detail)


def _scan(value: ScanResult) -> WorkScanResult:
    return WorkScanResult(
        started_at=value.started_at,
        completed_at=value.completed_at,
        rooms=list(value.rooms),
        results=[_room_result(item) for item in value.results],
        failures=[
            WorkScanRoomFailure(
                room=item.room, reason=item.reason, detail=item.detail
            )
            for item in value.failures
        ],
        notes=[_room_note(item) for item in value.notes],
        candidate_count=len(value.candidates),
        refusal_count=len(value.refusals),
    )


def _never_true(value: bool, *, field: str) -> Literal[False]:
    """Carry a "this is always false" property onto a ``Literal[False]`` field.

    The narrowing is the point. ``Literal[False]`` is what makes the wire
    value structural, and a plain ``bool`` would have widened it back; this
    reads the record's own answer, refuses to serialise a true one, and hands
    the type system the literal it needs. A record that grew a way to say
    "yes" therefore fails here, loudly, instead of being replaced by a schema
    default nobody sees.
    """
    if value:
        raise RuntimeError(
            f"an adapter record claims {field} is true; this build writes no "
            "adapter and contacts no third-party service"
        )
    return False


def _adapter(value: AdapterRecord) -> WorkScanAdapter:
    """One adapter record, with the two "never" flags **read off the record**.

    They used to be left to the schema's ``Literal[False]`` default, which
    made the response's ``adapter_written is False`` a restatement of a
    constant in ``schemas.py``. Two mutations proved it: flipping either
    property on ``AdapterRecord`` to ``True`` turned no test red, because no
    test and no code path ever looked at them. The wire invariant was real -
    ``Literal[False]`` cannot serialise anything else - and the *derivation*
    half of SI-281 was untested.

    Passing them here makes the two halves one: the properties are on the
    wire, so a record that started claiming it had been written to would fail
    validation at this line rather than be quietly overwritten by a default.
    """
    return WorkScanAdapter(
        id=value.id,
        name=value.name,
        support=value.support.value,
        declared_origin=value.declared_origin,
        adapter_written=_never_true(value.adapter_written, field="adapter_written"),
        contacted=_never_true(value.contacted, field="contacted"),
        self_description_source=value.self_description_source,
        score_self_description=value.score_self_description,
        verified=[
            WorkScanAdapterFact(
                key=fact.key, detail=fact.detail, state=fact.state.value
            )
            for fact in value.verified
        ],
        unverified=[
            WorkScanAdapterFact(
                key=fact.key, detail=fact.detail, state=fact.state.value
            )
            for fact in value.unverified
        ],
        self_description=value.self_description,
        score_caveat=value.score_caveat,
        provenance=value.provenance,
    )


def _to_response(view: WorkScanView) -> WorkScanStatusResponse:
    return WorkScanStatusResponse(
        honesty=view.honesty,
        capability=_capability(view.capability),
        adapters=[_adapter(item) for item in view.adapters],
        room_index=(
            _room_index(view.room_index) if view.room_index is not None else None
        ),
        discovery=(
            _discovery(view.discovery) if view.discovery is not None else None
        ),
        last_scan=_scan(view.last_scan) if view.last_scan is not None else None,
        never_sent_params=sorted(NEVER_SENT_PARAMS),
        polling_statement=POLLING_STATEMENT,
        prohibition_statement=PROHIBITION_HONESTY_SENTENCE,
    )


def _json(model: WorkScanStatusResponse) -> Response:
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


@router.get("/status", response_model=WorkScanStatusResponse)
async def read_status(request: Request, session: CurrentSession) -> Response:
    """The scan surface, as it is. Contacts nobody."""
    del session
    service = _service(request)
    return _json(_to_response(service.describe(write_gate_open=_write_gate_open(request))))


@router.post("/rooms/refresh", response_model=WorkScanStatusResponse)
def refresh_rooms(
    request: Request, session: CurrentSession, body: WorkScanRefreshRequest
) -> Response:
    """Read the room overview once, because the user asked.

    Blocking, and therefore ``def``: an outbound read on the event loop would
    stall every other request. A failure is a refusal with the reason, never a
    partial list - an overview this build could not read is not an overview
    with fewer rooms in it.
    """
    del session
    service = _service(request)
    try:
        service.refresh_room_index(limit=body.limit)
    except WorkScanError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(_to_response(service.describe(write_gate_open=_write_gate_open(request))))


@router.post("/discovery/refresh", response_model=WorkScanStatusResponse)
def refresh_discovery(
    request: Request, session: CurrentSession, body: WorkScanDiscoveryRequest
) -> Response:
    """Read the discovery log once, because the user asked.

    ``GET /r/events`` is the service's own append-ordered log of new public
    rooms. It is read through the *room* lane with a compile-time room name,
    so this route adds no address family and no client: the registry stays at
    two targets and ``OUTBOUND_CLIENT_MODULES`` stays at five.

    Blocking, and therefore ``def``, for the same reason ``rooms/refresh`` is.
    ``since`` comes from the body - the previous read's ``last_seq`` - because
    a cursor the service remembered would be the first half of a loop, and
    there is no timer, no background task and no held connection anywhere
    under this route.

    **Nothing is written here.** The log is server-written and a client write
    answers 403; this build has no code path that could attempt one, which is
    why the refusal travels as a sentence on the payload rather than as a
    promise in this docstring.
    """
    del session
    service = _service(request)
    markers = _markers(request)
    if not markers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Oda sinifi konvansiyonu resmi manifest'ten okunamadi; kesif "
                "gunlugu de bir odadir ve dogrulanmamis bir konvansiyonla "
                "adlandirilmaz. Once resmi kaynak denetimini calistirin."
            ),
            headers=_NO_STORE,
        )
    try:
        service.refresh_discovery(markers=markers, since=body.since, limit=body.limit)
    except ScanTargetError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    except WorkScanError as exc:
        # A refusal with the reason, never a partial log. An empty discovery
        # log means "no new rooms were announced", and a log this build could
        # not read must never be able to say that.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(_to_response(service.describe(write_gate_open=_write_gate_open(request))))


@router.post("/scan", response_model=WorkScanStatusResponse)
def scan_rooms(
    request: Request, session: CurrentSession, body: WorkScanScanRequest
) -> Response:
    """Read the rooms in the body, once each, and derive candidates.

    The scope is the body's list. A room that cannot be read is reported by
    name in ``failures`` rather than dropped, so an empty candidate list never
    stands in for a room nobody could reach.
    """
    del session
    service = _service(request)
    markers = _markers(request)
    if not markers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Oda sinifi konvansiyonu resmi manifest'ten okunamadi; hedef "
                "dogrulanamadigi icin tarama yapilmaz. Once resmi kaynak "
                "denetimini calistirin."
            ),
            headers=_NO_STORE,
        )
    # ``scan`` reports a failed room by name and does not raise for one. This
    # guard is for the case that is not one room: a failure of the scan as a
    # whole. It exists because it did not, and an unusable line reached the
    # ASGI layer as an unhandled exception and came back as a generic 500 -
    # the one answer that tells a user nothing about which rooms were read.
    try:
        service.scan(
            body.rooms,
            markers=markers,
            write_gate_open=_write_gate_open(request),
            limit=body.limit,
        )
    except WorkScanError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(_to_response(service.describe(write_gate_open=_write_gate_open(request))))


@router.post("/suggest", response_model=WorkScanSuggestResponse)
def suggest_candidate(
    request: Request, session: CurrentSession, body: WorkScanSuggestRequest
) -> Response:
    """Open one candidate as a local task in ``suggested``. Sends nothing."""
    del session
    service = _service(request)
    try:
        result = service.suggest(body.candidate_id)
    except (CandidateError, ScanTargetError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    except WorkScanError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc

    view = result.task
    payload = WorkScanSuggestResponse(
        task_id=view.id,
        module_id=view.module_id,
        source_id=view.source_id,
        source_version_id=view.source_version_id,
        detail=view.state_detail,
        # Carried rather than folded into ``detail``. ``detail`` is the task's
        # own state sentence; whether a model can read this request is a
        # different question with a different answer, and one string holding
        # both would be a reader's problem to take apart.
        request_file=result.request_file,
        request_file_detail=result.request_file_detail,
    )
    return Response(
        content=payload.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


__all__ = ["POLLING_STATEMENT", "router"]
