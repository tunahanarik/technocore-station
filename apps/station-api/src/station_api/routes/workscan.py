"""Work-scan endpoints: read the surface, list rooms, scan a chosen set, suggest.

    GET  /api/workscan/status        the whole surface, read-only, contacts nobody
    POST /api/workscan/rooms/refresh read the room overview, once, on request
    POST /api/workscan/scan          read the rooms in the body, once each
    POST /api/workscan/suggest       open one candidate as a local suggested task

Every state-changing route inherits the global session, CSRF, Host, Origin
and Sec-Fetch-Site guards - they are middleware, so nothing in this file can
opt out.

What is deliberately absent
---------------------------
* **No scan-everything route.** ``scan`` takes the rooms in the body and the
  body is bounded. There is no endpoint that walks the room universe, and the
  overview read exists to give a person a list to choose from rather than to
  feed a loop (ADR-0007 4).
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

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from station_api.dependencies import require_session
from station_api.identity.service import IdentityService
from station_api.schemas import (
    WorkScanAdapter,
    WorkScanAdapterFact,
    WorkScanCandidate,
    WorkScanCapability,
    WorkScanEffort,
    WorkScanOpenState,
    WorkScanQuote,
    WorkScanRefreshRequest,
    WorkScanRefusal,
    WorkScanResult,
    WorkScanRoom,
    WorkScanRoomFailure,
    WorkScanRoomIndex,
    WorkScanRoomResult,
    WorkScanScanRequest,
    WorkScanStaleness,
    WorkScanStatusResponse,
    WorkScanSuggestRequest,
    WorkScanSuggestResponse,
)
from station_api.security.sessions import Session
from station_api.technocore.service import TechnocoreService
from station_api.workscan.authority import ROOM_NAME_CAVEAT, TOPIC_CAVEAT
from station_api.workscan.candidates import (
    CandidateCapability,
    DerivationResult,
    WorkCandidate,
)
from station_api.workscan.errors import CandidateError, ScanTargetError, WorkScanError
from station_api.workscan.kibble import AdapterRecord
from station_api.workscan.service import ScanResult, WorkScanService, WorkScanView
from station_api.workscan.snapshot import RoomIndexSnapshot, StalenessNote
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
                shape=item.shape.value,
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


def _room_index(value: RoomIndexSnapshot) -> WorkScanRoomIndex:
    return WorkScanRoomIndex(
        rooms=[WorkScanRoom(name=room.name, topic=room.topic) for room in value.rooms],
        total=value.total,
        kept_count=value.kept_count,
        truncated=value.truncated,
        staleness=_staleness(value.staleness),
        sha256=value.sha256,
        room_name_caveat=ROOM_NAME_CAVEAT,
        topic_caveat=TOPIC_CAVEAT,
    )


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
        candidate_count=len(value.candidates),
        refusal_count=len(value.refusals),
    )


def _adapter(value: AdapterRecord) -> WorkScanAdapter:
    return WorkScanAdapter(
        id=value.id,
        name=value.name,
        support=value.support.value,
        declared_origin=value.declared_origin,
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
        last_scan=_scan(view.last_scan) if view.last_scan is not None else None,
        never_sent_params=sorted(NEVER_SENT_PARAMS),
        polling_statement=POLLING_STATEMENT,
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
    service.scan(
        body.rooms,
        markers=markers,
        write_gate_open=_write_gate_open(request),
        limit=body.limit,
    )
    return _json(_to_response(service.describe(write_gate_open=_write_gate_open(request))))


@router.post("/suggest", response_model=WorkScanSuggestResponse)
def suggest_candidate(
    request: Request, session: CurrentSession, body: WorkScanSuggestRequest
) -> Response:
    """Open one candidate as a local task in ``suggested``. Sends nothing."""
    del session
    service = _service(request)
    try:
        view = service.suggest(body.candidate_id)
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

    payload = WorkScanSuggestResponse(
        task_id=view.id,
        module_id=view.module_id,
        source_id=view.source_id,
        source_version_id=view.source_version_id,
        detail=view.state_detail,
    )
    return Response(
        content=payload.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


__all__ = ["POLLING_STATEMENT", "router"]
