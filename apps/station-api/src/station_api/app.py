"""FastAPI application factory.

In production the built SPA is served from this same origin, which is what
makes the whole same-origin security model work: there is no second origin
for a browser to be confused about, and therefore no CORS anywhere (ADR-013).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from station_api.config import LOOPBACK_HOST, Settings
from station_api.conformance import ConformanceService, default_conformance_service
from station_api.identity.service import IdentityService
from station_api.routes import api as api_routes
from station_api.routes import conformance as conformance_routes
from station_api.routes import identity as identity_routes
from station_api.routes import session as session_routes
from station_api.routes import technocore as technocore_routes
from station_api.security.middleware import (
    CsrfMiddleware,
    FetchMetadataMiddleware,
    HostGuardMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    SessionMiddleware,
    unhandled_exception_shield,
)
from station_api.security.sessions import SessionStore
from station_api.security.tokens import BootstrapTokenStore
from station_api.technocore.service import TechnocoreService

#: apps/station-api/src/station_api/app.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_WEB_DIST = REPO_ROOT / "apps" / "station-web" / "dist"

_NO_BUILD_PAGE = (
    '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
    "<title>Technocore Station</title></head><body>"
    "<h1>Arayuz derlenmemis</h1>"
    "<p>Once <code>npm --prefix apps/station-web run build</code> calistirin.</p>"
    "</body></html>"
)


def _allowed_hosts(port: int, settings: Settings) -> frozenset[str]:
    """Exactly the loopback authority this process listens on.

    ``localhost`` is intentionally absent: it is a name, and accepting names
    is what makes DNS rebinding possible (SI-12).
    """
    hosts = {f"{LOOPBACK_HOST}:{port}"}
    if settings.dev_mode:
        # The Vite proxy rewrites Host to the backend authority, but the dev
        # server's own authority is added so a direct hit still works.
        hosts.add(f"{LOOPBACK_HOST}:{settings.dev_port}")
        hosts.add(settings.dev_origin.removeprefix("http://"))
    return frozenset(hosts)


def _allowed_origins(port: int, settings: Settings) -> frozenset[str]:
    """Origins accepted in the ``Origin`` header.

    In production this is a single value. The Vite origin is added only when
    development mode is explicitly enabled, so a production build can never
    accept it (SI-17).
    """
    origins = {f"http://{LOOPBACK_HOST}:{port}"}
    if settings.dev_mode:
        origins.add(settings.dev_origin)
    return frozenset(origins)


def _mount_spa(app: FastAPI, web_dist: Path) -> None:
    """Serve the built SPA from this origin."""
    index_html = web_dist / "index.html"
    assets_dir = web_dist / "assets"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        if not index_html.is_file():
            return HTMLResponse(_NO_BUILD_PAGE, status_code=503)

        if full_path:
            candidate = (web_dist / full_path).resolve()
            # Containment check: a traversal attempt resolves outside dist and
            # falls through to index.html instead of reading an arbitrary file.
            if candidate.is_file() and candidate.is_relative_to(web_dist.resolve()):
                return FileResponse(candidate)

        return FileResponse(index_html)


def create_app(
    *,
    settings: Settings,
    port: int,
    engine: Engine | None = None,
    web_dist: Path | None = DEFAULT_WEB_DIST,
    token_store: BootstrapTokenStore | None = None,
    conformance: ConformanceService | None = None,
    technocore: TechnocoreService | None = None,
) -> FastAPI:
    """Build the application.

    ``openapi_url`` is None so the schema is never served over HTTP; tests
    still inspect it by calling ``app.openapi()`` in-process.
    """
    app = FastAPI(
        title="Technocore Station API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.state.settings = settings
    app.state.port = port
    app.state.engine = engine
    app.state.sessions = SessionStore()
    app.state.bootstrap_tokens = token_store or BootstrapTokenStore(
        ttl_seconds=settings.bootstrap_token_ttl_seconds
    )
    app.state.allowed_hosts = _allowed_hosts(port, settings)
    app.state.allowed_origins = _allowed_origins(port, settings)

    # One conformance verdict, shared by the status route and the write gate,
    # so the two can never disagree about whether this build is conformant.
    app.state.conformance = conformance or default_conformance_service()

    # The live-check verdict. Starts at never_checked and stays there
    # until the user asks for a check: creating the app contacts nobody.
    # One instance, shared by the status route and the write gate, so the
    # two surfaces cannot disagree about whether the protocol is current.
    app.state.technocore = technocore or TechnocoreService(engine=engine)

    # The identity service needs a database. Without one the identity routes
    # answer 503 rather than pretending to work.
    app.state.identity_service = (
        IdentityService(
            engine=engine,
            data_dir=settings.data_dir,
            conformance=app.state.conformance,
            technocore=app.state.technocore,
        )
        if engine is not None
        else None
    )

    app.include_router(session_routes.router)
    app.include_router(api_routes.router)
    app.include_router(identity_routes.router)
    app.include_router(identity_routes.gate_router)
    app.include_router(conformance_routes.router)
    app.include_router(technocore_routes.router)

    # Registered last so it cannot shadow /api or /session.
    if web_dist is not None:
        _mount_spa(app, web_dist)

    # Starlette wraps the LAST added middleware outermost, so this block reads
    # innermost-first. Effective order: SecurityHeaders -> RequestId ->
    # HostGuard -> FetchMetadata -> Session -> Csrf. SecurityHeaders stays
    # outermost so every guard rejection carries the hardening headers (SI-33);
    # RequestId sits directly inside it so those same rejections also carry
    # the correlation id (SI-125). There is no CORS middleware (INV-03).
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(SessionMiddleware, store=app.state.sessions)
    app.add_middleware(FetchMetadataMiddleware, allowed_origins=app.state.allowed_origins)
    app.add_middleware(HostGuardMiddleware, allowed_hosts=app.state.allowed_hosts)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # Starlette runs the Exception handler in ServerErrorMiddleware, outside
    # even SecurityHeaders, which is why the shield sets the hardening headers
    # and the request id itself (SI-126). The body is a constant
    # {"detail": "internal_error"}; the traceback goes to the server log only.
    app.add_exception_handler(Exception, unhandled_exception_shield)

    return app
