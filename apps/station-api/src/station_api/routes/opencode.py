"""OpenCode connection endpoints: configure, forget, read, refresh, choose.

    GET  /api/opencode/status           the whole connection, read-only
    POST /api/opencode/credential       store the provider key
    POST /api/opencode/credential/forget  remove it
    POST /api/opencode/check            probe the key: one metered call
    POST /api/opencode/catalog/refresh  fetch the public model catalog
    POST /api/opencode/model            choose a model, or be refused

Every state-changing route inherits the global session, CSRF, Host, Origin
and Sec-Fetch-Site guards - they are middleware, so nothing in this file can
opt out.

What is deliberately absent
---------------------------
* **No route that returns the stored key.** Not masked, not partial, not
  "for verification". The key goes in and is described by a fingerprint
  afterwards; there is no read path, so there is nothing to get wrong.
* **No URL, host, path, protocol or endpoint parameter.** ``refresh`` takes
  no body at all and ``model`` takes an identifier that is resolved through
  the compile-time table. There is no code path from a request body to an
  outbound address.
* **No badge from a read.** ``status`` contacts nobody and reports the
  *stored* verdict with the date it was earned. A verified state exists since
  ADR-0015, and ``POST /check`` is the only thing that can produce one.
* **No completion route.** Composing a task's turn is the planner package's,
  and a button for it here would have made "Station never spends money on its
  own" a claim with a footnote. ``/check`` does spend, once, on a press, from
  a body that carries nothing a caller wrote - which is the narrowest metered
  surface that can answer the question the button asks.
* **No fallback.** A model that cannot be addressed is a 400 naming the
  reason, never a quiet substitution.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from station_api.dependencies import require_session
from station_api.opencode import quota
from station_api.opencode.adapters import SHAPE_PROVENANCE
from station_api.opencode.catalog import LISTING_CAVEAT
from station_api.opencode.client import AUTH_HEADER_CAVEAT
from station_api.opencode.errors import (
    CredentialEnvelopeError,
    ModelNotSelectableError,
    OpenCodeConfigurationError,
)
from station_api.opencode.events import (
    DEFERRAL_SENTENCE,
    STREAMING_SUPPORTED,
    TOOL_CALLS_SUPPORTED,
)
from station_api.opencode.planner import TOOL_CALL_PROVENANCE
from station_api.opencode.registry import Protocol
from station_api.opencode.service import (
    CatalogView,
    ConnectionView,
    OpenCodeService,
)
from station_api.schemas import (
    OpenCodeCatalogStatus,
    OpenCodeConnectionCheckStatus,
    OpenCodeCredentialRequest,
    OpenCodeModelStatus,
    OpenCodeProtocolContext,
    OpenCodePublishedLimit,
    OpenCodeSelectModelRequest,
    OpenCodeSpendingContext,
    OpenCodeStatusResponse,
)
from station_api.security.sessions import Session

router = APIRouter(prefix="/api/opencode")

CurrentSession = Annotated[Session, Depends(require_session)]

#: Connection state is local, session-scoped and never belongs in a cache.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _service(request: Request) -> OpenCodeService:
    service: OpenCodeService | None = getattr(request.app.state, "opencode", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenCode baglantisi kullanilabilir degil.",
            headers=_NO_STORE,
        )
    return service


def _spending() -> OpenCodeSpendingContext:
    """The published figures, and where the controls actually live.

    Assembled here from constants. Nothing on this path measures, projects or
    sums anything, which is why there is no arithmetic in this function.
    """
    context = OpenCodeSpendingContext(
        limits=[
            OpenCodePublishedLimit(
                window=limit.window, amount_usd=limit.amount_usd, note=limit.note
            )
            for limit in quota.PUBLISHED_LIMITS
        ],
        limit_behaviour=quota.LIMIT_BEHAVIOUR,
        use_balance=quota.USE_BALANCE_STATEMENT,
        local_counter_caveat=quota.LOCAL_COUNTER_CAVEAT,
        unknown_cost_sentence=quota.UNKNOWN_COST_SENTENCE,
    )
    # Our own sentences, checked against our own rule: a subscription with
    # published caps is not unlimited, and this is the surface where calling
    # it that would be believed.
    for sentence in (
        context.limit_behaviour,
        context.use_balance,
        context.local_counter_caveat,
        context.unknown_cost_sentence,
    ):
        quota.assert_no_unlimited_claim(sentence)
    return context


def _catalog(view: CatalogView) -> OpenCodeCatalogStatus:
    return OpenCodeCatalogStatus(
        state=view.state.value,
        fetched_at=view.fetched_at,
        models_fetched_at=view.models_fetched_at,
        detail=view.detail,
        http_status=view.http_status,
        models=[
            OpenCodeModelStatus(
                model_id=model.model_id,
                owned_by=model.owned_by,
                selectable=model.selectable,
                protocol=model.protocol,
                protocol_verification=model.protocol_verification,  # type: ignore[arg-type]
                reason=model.reason,
                retention=model.retention,
                training_use=model.training_use,  # type: ignore[arg-type]
                requires_training_acknowledgement=(
                    model.requires_training_acknowledgement
                ),
                privacy_source=model.privacy_source,
                privacy_read_on=model.privacy_read_on,
            )
            for model in view.models
        ],
        model_count=len(view.models),
        selectable_count=view.selectable_count,
        unmapped_count=view.unmapped_count,
        listing_caveat=LISTING_CAVEAT,
        table_provenance=view.table_provenance,
        drift_notice=view.drift_notice,
    )


def _to_response(view: ConnectionView) -> OpenCodeStatusResponse:
    return OpenCodeStatusResponse(
        configured=view.configured,
        fingerprint_short=view.fingerprint_short,
        configured_at=view.configured_at,
        updated_at=view.updated_at,
        check=OpenCodeConnectionCheckStatus(
            state=view.check.state.value,
            reasons=list(view.check.reasons),
            detail=view.check.detail,
            checked_at=view.check.checked_at,
            probes_used=view.check.probes_used,
            probe_ceiling=view.check.probe_ceiling,
        ),
        selected_model=view.selected_model,
        auth_header_caveat=AUTH_HEADER_CAVEAT,
        catalog=_catalog(view.catalog),
        spending=_spending(),
        protocol_context=OpenCodeProtocolContext(
            protocols=[protocol.value for protocol in Protocol],
            # Passed explicitly from the constants rather than left to the
            # field defaults. A default here would make the wire a *second*
            # hard-coded answer with no link to the module that decides it -
            # two claims about one fact, either of which could be edited
            # alone. ``AgentExecutionStatus`` got the same repair in H2.
            streaming_supported=STREAMING_SUPPORTED,
            tool_calls_supported=TOOL_CALLS_SUPPORTED,
            deferral=DEFERRAL_SENTENCE,
            shape_provenance=SHAPE_PROVENANCE,
            tool_call_provenance=(
                TOOL_CALL_PROVENANCE if TOOL_CALLS_SUPPORTED else ""
            ),
        ),
    )


def _json(model: OpenCodeStatusResponse) -> Response:
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


@router.get("/status", response_model=OpenCodeStatusResponse)
async def read_status(request: Request, session: CurrentSession) -> Response:
    """The connection, as it is. Contacts nobody."""
    del session
    return _json(_to_response(_service(request).describe()))


@router.post("/credential", response_model=OpenCodeStatusResponse)
def store_credential(
    request: Request, session: CurrentSession, body: OpenCodeCredentialRequest
) -> Response:
    """Store the provider key.

    ``def`` rather than ``async def``: this writes a DPAPI envelope and calls
    into the Windows ACL API, and on the event loop that would stall every
    other request (IMP-296's reasoning).

    The reply is the same status document every other route returns, which is
    the point - after storing a key the user learns that it was **saved and
    not verified**, from the same fields that would have said anything else.
    """
    del session
    service = _service(request)
    try:
        view = service.store_credential(body.api_key.get_secret_value())
    except CredentialEnvelopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    except OpenCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(_to_response(view))


@router.post("/credential/forget", response_model=OpenCodeStatusResponse)
def forget_credential(request: Request, session: CurrentSession) -> Response:
    """Remove the stored key. Takes no body, so there is nothing to steer.

    ``def`` for the same reason ``store_credential`` is: this touches the
    filesystem. The ``CredentialEnvelopeError`` branch exists because
    removing the envelope can fail on Windows while another handle is open on
    it, and "the file is still there" must be reported rather than reported
    as success - the caller is a user trying to revoke a credential.
    """
    del session
    try:
        view = _service(request).forget_credential()
    except OpenCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    except CredentialEnvelopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(_to_response(view))


@router.post("/check", response_model=OpenCodeStatusResponse)
def check_connection(request: Request, session: CurrentSession) -> Response:
    """Probe the stored credential. **The only metered route on this surface.**

    ``POST`` and not ``GET``, for three reasons that all point the same way: it
    spends money, so it must be a press rather than a navigation; it changes
    stored state, so it belongs behind the CSRF, Origin and Sec-Fetch-Site
    middleware every other write here sits behind; and a ``GET`` is the thing a
    browser, a prefetcher or a reload repeats on its own.

    Blocking, and therefore ``def``: it waits on a network round trip bounded
    by the client's own 120-second read timeout.

    Takes no body. There is no prompt, no model, no address and no ceiling
    parameter: the model is the one already selected in the backend, the
    address comes from the closed endpoint registry, and the sentence sent is a
    compile-time constant. There is no path from anything a caller can type to
    what this request contains.

    A spent ceiling is **not** an error here. It comes back as a 200 carrying
    the status document, whose ``check.reasons`` already names the ceiling and
    whose ``check.probes_used`` says where the caller stands - the same call
    ``refresh_catalog`` makes about a failed fetch, and for the same reason:
    "this connection has no probes left" is a state of the connection, not a
    malformed request.
    """
    del session
    service = _service(request)
    try:
        view = service.probe_connection()
    except ModelNotSelectableError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    except OpenCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(_to_response(view))


@router.post("/catalog/refresh", response_model=OpenCodeStatusResponse)
def refresh_catalog(request: Request, session: CurrentSession) -> Response:
    """Fetch the public model catalog, on the user's request only.

    Blocking, and therefore ``def``. Takes no body: the address comes from
    the closed endpoint registry, and a failure is reported in the catalog
    fields rather than raised, because "we could not read the list" is a
    state of the connection and not an error in the request.
    """
    del session
    service = _service(request)
    try:
        service.refresh_catalog()
    except OpenCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(_to_response(service.describe()))


@router.post("/model", response_model=OpenCodeStatusResponse)
def select_model(
    request: Request, session: CurrentSession, body: OpenCodeSelectModelRequest
) -> Response:
    """Choose a model, or be told exactly why it cannot be chosen."""
    del session
    service = _service(request)
    try:
        service.select_model(
            body.model_id, training_acknowledged=body.training_acknowledged
        )
    except ModelNotSelectableError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    except OpenCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc
    return _json(_to_response(service.describe()))


__all__ = ["router"]
