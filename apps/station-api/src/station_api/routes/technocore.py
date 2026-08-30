"""Read-only Technocore monitoring endpoints.

Two routes, and the split between them is the point:

``GET  /api/technocore/status``   reads the current verdict. Never touches the
                                  network, so opening the dashboard contacts
                                  nobody.
``POST /api/technocore/refresh``  runs the check. Session **and** CSRF
                                  protected, because it is the one action here
                                  that reaches the public internet, and it must
                                  only ever happen because a user asked.

The refresh route takes **no request body**. There is no URL, no path, no
host and no method to supply: it runs the fixed source registry and nothing
else. That is deliberate - Technocore performs writes over GET, so an
endpoint that accepted any caller-influenced address would be one bug away
from writing to a live public room.

Nothing here returns a document body. The UI receives allow-listed metadata,
a short hash and per-field verdicts; the bounded raw excerpt stays in the
database for human review.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from station_api.dependencies import require_session
from station_api.schemas import (
    OfficialSourceStatus,
    ProtocolFieldStatus,
    TechnocoreStatusResponse,
)
from station_api.security.sessions import Session
from station_api.technocore.service import TechnocoreService, TechnocoreStatus
from station_api.technocore.sources import TECHNOCORE_ORIGIN

router = APIRouter(prefix="/api/technocore")

CurrentSession = Annotated[Session, Depends(require_session)]

_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _service(request: Request) -> TechnocoreService:
    service: TechnocoreService | None = getattr(request.app.state, "technocore", None)
    if service is None:  # pragma: no cover - always wired by create_app
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Technocore izleme servisi kullanilabilir degil.",
        )
    return service


def to_response(state: TechnocoreStatus) -> TechnocoreStatusResponse:
    """Project the in-process verdict onto the public response model."""
    projection = state.projection
    fields = (
        [
            ProtocolFieldStatus(
                key=item.field.key,
                label=item.field.label,
                source_id=item.field.source_id.value,
                json_path=item.field.json_path,
                severity=item.field.severity.value,
                expected=item.field.expected,
                observed=item.observed,
                matches=item.matches,
                rationale=item.field.rationale,
            )
            for item in projection.observations
        ]
        if projection is not None
        else []
    )

    return TechnocoreStatusResponse(
        state=state.state.value,
        manifest_current=state.manifest_current,
        checked_at=state.checked_at,
        last_attempt_at=state.last_attempt_at,
        last_success_at=state.last_success_at,
        reasons=list(state.reasons),
        sources=[
            OfficialSourceStatus(
                source_id=source.source_id,
                url=source.url,
                authority=source.authority,
                outcome=source.outcome,
                http_status=source.http_status,
                content_type=source.content_type,
                etag=source.etag,
                last_modified=source.last_modified,
                short_hash=source.short_hash,
                byte_count=source.byte_count,
                detail=source.detail,
                rationale=source.rationale,
            )
            for source in state.sources
        ],
        fields=fields,
        critical_mismatch_count=(
            len(projection.critical_mismatches) if projection is not None else 0
        ),
        warning_count=len(projection.warnings) if projection is not None else 0,
        origin=TECHNOCORE_ORIGIN,
    )


def _json(model: TechnocoreStatusResponse) -> Response:
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


@router.get("/status", response_model=TechnocoreStatusResponse)
async def read_status(request: Request, session: CurrentSession) -> Response:
    """The current verdict. Read-only, and offline."""
    del session
    return _json(to_response(_service(request).status()))


@router.post("/refresh", response_model=TechnocoreStatusResponse)
async def refresh(request: Request, session: CurrentSession) -> Response:
    """Run the read-only check against the fixed source registry.

    Takes no body on purpose: there is nothing for a caller to steer.
    """
    del session
    return _json(to_response(_service(request).refresh()))
