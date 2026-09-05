"""The ``/api`` surface for Stage 1.

Three endpoints, nothing more: a public health probe, the session bootstrap
that hands the SPA its CSRF value, and a protected status read.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Engine

from station_api.config import CSRF_HEADER_NAME
from station_api.db.migrations_runner import current_revision
from station_api.dependencies import require_session
from station_api.schemas import (
    AppStatusResponse,
    DatabaseStatus,
    HealthResponse,
    ServiceStatus,
    SessionBootstrapResponse,
    SessionSecurityStatus,
    TechnocoreStatus,
)
from station_api.security.sessions import Session
from station_api.technocore.projection import DriftState
from station_api.technocore.service import TechnocoreService

router = APIRouter(prefix="/api")

CurrentSession = Annotated[Session, Depends(require_session)]

_TECHNOCORE_DETAIL = {
    "never_checked": (
        "Resmi kaynaklar bu oturumda henuz denetlenmedi. Station kendiliginden "
        "istek gondermez; denetimi Evidence & Sources sekmesinden siz baslatirsiniz."
    ),
    "current": (
        "Resmi kaynaklar salt okunur denetlendi ve kritik protokol sozlesmesi "
        "beklenenle ayni. Yazma yolu yalnizca sizin ayri ayri onayladiginiz "
        "bir imza ve gonderim ile calisir; Station kendiliginden yazmaz."
    ),
    "drifted": (
        "Kritik protokol alani degismis. Dis yazma kapisi kapali kalir."
    ),
    "unavailable": (
        "Resmi kaynaklara ulasilamadi veya belge okunamadi. Kapi fail-closed."
    ),
}


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Public probe. Reveals liveness and nothing else."""
    return HealthResponse()


@router.get("/session/bootstrap", response_model=SessionBootstrapResponse)
async def session_bootstrap(session: CurrentSession) -> SessionBootstrapResponse:
    """Return the per-session CSRF value.

    A pure read, so it needs no CSRF proof of its own and no exemption from
    the CSRF middleware (IMP-105). The response is sent with
    ``Cache-Control: no-store`` by SecurityHeadersMiddleware.
    """
    return SessionBootstrapResponse(
        csrf_token=session.csrf_token,
        csrf_header=CSRF_HEADER_NAME,
    )


def _read_database_status(engine: Engine | None) -> DatabaseStatus:
    if engine is None:
        return DatabaseStatus(
            state="unavailable",
            journal_mode="unknown",
            foreign_keys=False,
            schema_revision="unknown",
        )
    with engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    return DatabaseStatus(
        state="ready",
        journal_mode=str(journal_mode).lower(),
        foreign_keys=bool(foreign_keys),
        schema_revision=current_revision(engine) or "unknown",
    )


def _technocore_status(request: Request) -> TechnocoreStatus:
    """The header card, driven by the same verdict the write gate reads.

    Reading this never triggers a fetch: it reports what the last
    user-initiated check found, or that none has run yet.
    """
    service: TechnocoreService | None = getattr(request.app.state, "technocore", None)
    state: DriftState = (
        DriftState.NEVER_CHECKED if service is None else service.status().state
    )
    return TechnocoreStatus(state=state.value, detail=_TECHNOCORE_DETAIL[state.value])


@router.get("/app/status", response_model=AppStatusResponse)
async def app_status(request: Request, session: CurrentSession) -> AppStatusResponse:
    """Protected status read.

    Note what is absent: the database file path, the data directory and the
    listening port are never returned (SI-36).
    """
    settings = request.app.state.settings
    return AppStatusResponse(
        service=ServiceStatus(
            stage=8,
            mode="development" if settings.dev_mode else "production",
        ),
        database=_read_database_status(request.app.state.engine),
        session_security=SessionSecurityStatus(
            cookie_http_only=True,
            cookie_same_site="strict",
            cookie_secure=False,
            csrf_required=True,
        ),
        technocore=_technocore_status(request),
    )
