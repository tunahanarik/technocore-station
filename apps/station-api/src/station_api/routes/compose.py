"""Composer endpoints: the only outbound write surface in Station.

Four routes. Three of them are the approval chain and each one is a separate
request on purpose (ADR-0002 2); the fourth is a read that lets the UI
explain a closed gate.

    GET  /api/compose/capability   what is possible, and what blocks it
    POST /api/compose/draft        sweep and bind; signs nothing
    POST /api/compose/sign         reserve a nonce, sign, mint one approval
    POST /api/compose/send         spend the approval, POST once

Every state-changing route here inherits the global session, CSRF, Host,
Origin and Sec-Fetch-Site guards - they are middleware, so nothing in this
file can opt out - and every one of the three re-runs the whole write gate
inside the service. A disabled button in the browser is not a control.

What is deliberately absent
---------------------------
* **No note lane.** ADR-0002 1: the pinned protocol accepts a signed note
  only in the ``room-owners`` and ``room-allow`` namespaces, and the profile
  note the charter asks for lives on the unsigned lane. A send button for it
  would present an unsigned write as signed evidence.
* **No URL, host, path or method parameter anywhere.** The room name is
  validated against the official pattern and resolved through the closed
  write registry; nothing else about the request is caller-influenced.
* **No route that signs and sends in one call.** That is the whole design.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from technocore_conform import MAX_MESSAGE_CHARS

from station_api.compose.approvals import DRAFT_TTL_SECONDS, SEND_TOKEN_TTL_SECONDS
from station_api.compose.service import ComposeError, ComposeService
from station_api.dependencies import require_session
from station_api.schemas import (
    ComposeCapabilityResponse,
    ComposeDraftRequest,
    ComposeDraftResponse,
    ComposeSendRequest,
    ComposeSendResponse,
    ComposeSignRequest,
    ComposeSignResponse,
)
from station_api.security.sessions import Session
from station_api.technocore.write_targets import (
    DENIED_ROOMS,
    MESSAGE_LANE_TEMPLATE,
    WRITE_METHOD,
)

router = APIRouter(prefix="/api/compose")

CurrentSession = Annotated[Session, Depends(require_session)]

#: Every response here is session-scoped or carries a capability token.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

#: Why there is no note send path. Shown to the user rather than left as a
#: missing button, so the absence reads as a decision instead of a gap.
NOTE_LANE_DETAIL = (
    "Imzali note gonderimi bu surumde yoktur. Pinlenmis protokol imzali note "
    "yazmasini yalniz room-owners ve room-allow namespace'lerinde kabul "
    "ediyor; kunyenin istedigi DID profil notu ise imzasiz lane'de yayimlanir "
    "ve imza kaniti uretmez. Imzasiz bir yazmayi 'gonderildi' rozetiyle "
    "sunmak kanit seviyelerini karistirmak olurdu."
)


def _service(request: Request) -> ComposeService:
    service: ComposeService | None = getattr(request.app.state, "compose", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Composer servisi kullanilabilir degil.",
        )
    return service


def _refused(error: ComposeError) -> HTTPException:
    """Map a refusal onto HTTP without losing why it happened.

    The reason code travels in a header rather than in the body so the error
    contract (SI-126) stays exactly ``{"detail": ...}``.
    """
    return HTTPException(
        status_code=error.status_code,
        detail=str(error),
        headers={**_NO_STORE, "X-Station-Compose-Reason": error.reason},
    )


def _json(
    model: ComposeCapabilityResponse
    | ComposeDraftResponse
    | ComposeSignResponse
    | ComposeSendResponse,
) -> Response:
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


@router.get("/capability", response_model=ComposeCapabilityResponse)
async def read_capability(request: Request, session: CurrentSession) -> Response:
    """What the composer can do right now, and what is blocking it."""
    del session
    identity_service = getattr(request.app.state, "identity_service", None)
    technocore = getattr(request.app.state, "technocore", None)

    if identity_service is None or technocore is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Composer servisi kullanilabilir degil.",
        )

    gate = identity_service.describe().gate
    live = technocore.status()
    projection = live.projection
    limits = (
        projection.effective_payload_limits["text"] if projection is not None else None
    )

    return _json(
        ComposeCapabilityResponse(
            can_compose=gate.allowed,
            blocking_reasons=list(gate.blocking_reasons),
            write_method=WRITE_METHOD,
            write_path_template=MESSAGE_LANE_TEMPLATE,
            denied_rooms=sorted(DENIED_ROOMS),
            room_class_markers=list(live.room_class_markers),
            # Without a completed check there are no live limits to report,
            # so the charter ceiling stands in - and the gate is shut anyway.
            min_chars=1 if limits is None else limits.minimum,
            max_chars=MAX_MESSAGE_CHARS if limits is None else limits.maximum,
            draft_ttl_seconds=DRAFT_TTL_SECONDS,
            approval_ttl_seconds=SEND_TOKEN_TTL_SECONDS,
            note_lane_detail=NOTE_LANE_DETAIL,
        )
    )


@router.post("/draft", response_model=ComposeDraftResponse)
async def create_draft(
    request: Request, session: CurrentSession, body: ComposeDraftRequest
) -> Response:
    """Step 1. Sweeps, measures and binds a digest. Signs nothing."""
    try:
        result = _service(request).draft(
            session_id=session.session_id, room=body.room, text=body.text
        )
    except ComposeError as exc:
        raise _refused(exc) from exc

    return _json(
        ComposeDraftResponse(
            draft_id=result.draft_id,
            room=result.room,
            room_classes=list(result.room_classes),
            raw_text=result.raw_text,
            swept_text=result.swept_text,
            changed_by_sweep=result.changed_by_sweep,
            raw_chars=result.raw_chars,
            swept_chars=result.swept_chars,
            draft_digest=result.draft_digest,
            min_chars=result.min_chars,
            max_chars=result.max_chars,
            expires_in_seconds=result.expires_in_seconds,
            target_notes=list(result.target_notes),
        )
    )


@router.post("/sign", response_model=ComposeSignResponse)
def sign_draft(
    request: Request, session: CurrentSession, body: ComposeSignRequest
) -> Response:
    """Step 2. The explicit signing approval.

    Reserves the nonce inside a transaction *before* signing, because the
    nonce is part of the bytes being signed.

    ``def`` rather than ``async def`` on purpose: FastAPI runs a sync path
    operation in a worker thread. The body of this one unlocks a
    passphrase-protected vault, which means an Argon2id derivation sized to
    take real time, and it holds a database transaction while it does. On the
    event loop that would stall *every* other request for the whole
    derivation, including the session and gate reads the same page is making.
    """
    passphrase = (
        body.vault_passphrase.get_secret_value() if body.vault_passphrase else None
    )
    try:
        result = _service(request).sign(
            session_id=session.session_id,
            draft_id=body.draft_id,
            confirmed_digest=body.draft_digest,
            vault_passphrase=passphrase,
        )
    except ComposeError as exc:
        raise _refused(exc) from exc

    return _json(
        ComposeSignResponse(
            draft_id=result.draft_id,
            room=result.room,
            did=result.did,
            nonce=result.nonce,
            canonical=result.canonical,
            canonical_digest=result.canonical_digest,
            signature=result.signature,
            changed_by_sweep=result.changed_by_sweep,
            send_token=result.send_token,
            expires_in_seconds=result.expires_in_seconds,
        )
    )


@router.post("/send", response_model=ComposeSendResponse)
def send_message(
    request: Request, session: CurrentSession, body: ComposeSendRequest
) -> Response:
    """Step 3. Spend the approval and POST once. No retry, ever.

    ``def`` for the same reason as ``sign``, and here the number is concrete:
    the write client is synchronous ``httpx`` with a 15-second read timeout,
    so an ``async def`` would hand the event loop a call that can hold it for
    fifteen seconds. Nothing else would be served in that window - not the
    countdown the composer is polling, not another tab.

    Exactly-once is unaffected: the approval token is consumed under a lock in
    the service, before anything is sent, so two threads racing on the same
    token still produce one request and one refusal.
    """
    try:
        result = _service(request).send(
            session_id=session.session_id, send_token=body.send_token
        )
    except ComposeError as exc:
        raise _refused(exc) from exc

    return _json(
        ComposeSendResponse(
            # ``WriteOutcome`` is a StrEnum whose members are exactly the
            # three Literal values, so this needs no cast - and mypy says so.
            outcome=result.outcome.value,
            room=result.room,
            did=result.did,
            nonce=result.nonce,
            canonical_digest=result.canonical_digest,
            signature=result.signature,
            http_status=result.http_status,
            detail=result.detail,
            response_excerpt=result.response_excerpt,
            reconciliation_required=result.reconciliation_required,
        )
    )


__all__ = ["NOTE_LANE_DETAIL", "router"]
