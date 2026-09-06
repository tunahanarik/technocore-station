"""FastAPI application factory.

In production the built SPA is served from this same origin, which is what
makes the whole same-origin security model work: there is no second origin
for a browser to be confused about, and therefore no CORS anywhere (ADR-013).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from station_api.agent.activity import ActivityLog
from station_api.agent.service import AgentService
from station_api.compose.nonce import NonceReserver
from station_api.compose.service import ComposeService
from station_api.compose.signer import MessageSigner, VaultMessageSigner
from station_api.config import LOOPBACK_HOST, Settings
from station_api.conformance import ConformanceService, default_conformance_service
from station_api.evidence.audit import AuditChain
from station_api.evidence.audit_envelope import AuditEnvelope, AuditEnvelopeError
from station_api.evidence.service import EvidenceService
from station_api.identity.service import IdentityService
from station_api.opencode.service import OpenCodeService
from station_api.planner.service import ModelPlannerService
from station_api.proof.service import ProofService
from station_api.resources import PackagedLayoutError, is_frozen, shipped_web_dist
from station_api.routes import agent as agent_routes
from station_api.routes import api as api_routes
from station_api.routes import compose as compose_routes
from station_api.routes import conformance as conformance_routes
from station_api.routes import evidence as evidence_routes
from station_api.routes import identity as identity_routes
from station_api.routes import opencode as opencode_routes
from station_api.routes import planner as planner_routes
from station_api.routes import proof as proof_routes
from station_api.routes import session as session_routes
from station_api.routes import technocore as technocore_routes
from station_api.routes import workscan as workscan_routes
from station_api.security.middleware import (
    CsrfMiddleware,
    FetchMetadataMiddleware,
    HostGuardMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    SessionMiddleware,
    unhandled_exception_shield,
    validation_error_shield,
)
from station_api.security.sessions import SessionStore
from station_api.security.tokens import BootstrapTokenStore
from station_api.tasks.reconciliation import (
    ReconciliationReport,
    scan_unfinished_writes,
)
from station_api.tasks.service import TaskService
from station_api.technocore.service import TechnocoreService
from station_api.technocore.write_client import SignedWriteClient
from station_api.vault import DpapiVault
from station_api.vault.errors import VaultError
from station_api.workscan.service import WorkScanService

_log = logging.getLogger(__name__)

#: Sentinel default for ``create_app``'s ``web_dist``: "serve whatever SPA
#: this build actually ships with", resolved by
#: :func:`station_api.resources.shipped_web_dist` at call time.
#:
#: A sentinel rather than a module constant because the answer depends on how
#: the process was started, and a module constant is computed at import. The
#: old ``DEFAULT_WEB_DIST`` was exactly that constant, and it was wrong
#: everywhere except an editable install (ADR-0010 1). ``None`` still means
#: "mount no SPA at all", which is what most tests pass, so a third value was
#: needed rather than a second.
SHIPPED_WEB_DIST: Path = Path("<shipped-spa>")

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
    """Serve the built SPA from this origin.

    The frozen check here is the second half of ADR-0010 1's requirement and
    it is deliberately not the same check as
    :func:`~station_api.resources.shipped_web_dist`'s. That one refuses to
    *resolve* a missing bundle; this one refuses to *mount* a directory that
    has no ``index.html``, whoever chose it - so a packaged build cannot reach
    the 503 page even by being handed an explicit ``web_dist``. Two
    independent refusals, because one of them is the one somebody edits.
    """
    index_html = web_dist / "index.html"
    assets_dir = web_dist / "assets"

    if is_frozen() and not index_html.is_file():
        raise PackagedLayoutError(
            "Bu paket derlenmis arayuzu tasimiyor. Paket eksik uretilmis; "
            "yeniden paketlenmesi gerekir."
        )

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


def _build_evidence(
    *,
    engine: Engine,
    chain: AuditChain,
    evidence: EvidenceService | None,
) -> EvidenceService | None:
    """Wire the evidence archive, or report that it could not be wired.

    The chain's MAC material lives in a DPAPI envelope, and DPAPI is a
    Windows facility that a self-test can find missing. Failing to build the
    archive must not fail the application: the composer treats a missing
    evidence layer as "not archived" and keeps working, which is the honest
    degradation. Swallowing the error silently would not be - so the shape of
    the failure is one narrow exception type, not a bare ``except``.
    """
    if evidence is not None:
        return evidence
    service = EvidenceService(engine=engine, chain=chain)
    try:
        service.start()
    except (AuditEnvelopeError, VaultError, OSError):
        return None
    return service


def _scan_unfinished(engine: Engine | None) -> ReconciliationReport:
    """Run the startup scan and say what it found, once, in the log.

    Wrapped so a database that cannot be read does not stop the application
    from starting. The scan is a report about the ledger; failing to produce
    it is worth a log line, not a refusal to launch - and swallowing the
    failure silently is not the alternative, which is why the shape of the
    exception is narrow rather than a bare ``except``.
    """
    try:
        report = scan_unfinished_writes(engine)
    except SQLAlchemyError as exc:  # pragma: no cover - storage-dependent
        _log.warning("task reconciliation scan failed: %s", type(exc).__name__)
        return ReconciliationReport(
            scanned_at=datetime.now(UTC),
            unfinished=(),
            detail="Yarim kalmis gonderim taramasi yapilamadi.",
        )
    if report.unfinished:
        _log.info(
            "task reconciliation: %d unfinished send(s) listed; nothing resumed",
            report.unfinished_count,
        )
    return report


def create_app(
    *,
    settings: Settings,
    port: int,
    engine: Engine | None = None,
    web_dist: Path | None = SHIPPED_WEB_DIST,
    token_store: BootstrapTokenStore | None = None,
    conformance: ConformanceService | None = None,
    technocore: TechnocoreService | None = None,
    write_client: SignedWriteClient | None = None,
    signer: MessageSigner | None = None,
    evidence: EvidenceService | None = None,
    opencode: OpenCodeService | None = None,
    workscan: WorkScanService | None = None,
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

    # The evidence archive and its audit chain. Both need a database, and the
    # chain additionally needs DPAPI for the envelope that holds its MAC
    # material. Neither is a precondition for sending: a machine where the
    # chain cannot be created still composes and sends, and reports that a
    # send was not archived rather than refusing to send. Refusing would trade
    # a missing record for a missing message, which is the worse of the two.
    # The audit chain object is built once and shared by the evidence archive
    # and the Activity Desk. Two chains over one table would be two things
    # that can disagree about where the head is - the duplication ADR-0004 2
    # rules out, applied to the one component both packages append to.
    chain = (
        AuditChain(engine, AuditEnvelope(settings.data_dir))
        if engine is not None
        else None
    )
    app.state.evidence = (
        _build_evidence(engine=engine, chain=chain, evidence=evidence)
        if engine is not None and chain is not None
        else None
    )

    # The composer. It needs a database (for the nonce counter) and an
    # identity service (for the gate and the vault handle); without either it
    # is absent and its routes answer 503 rather than pretending.
    #
    # ``write_client`` and ``signer`` are test seams in the same sense as the
    # read client's transport: neither can widen anything, because the URL is
    # still built from the closed write registry and re-checked against the
    # origin allow-list, and the signer still receives only a canonical
    # payload. Nothing reads either from the environment.
    app.state.compose = (
        ComposeService(
            identity=app.state.identity_service,
            technocore=app.state.technocore,
            reserver=NonceReserver(engine),
            signer=(
                signer
                if signer is not None
                else VaultMessageSigner(DpapiVault(settings.data_dir))
            ),
            write_client=(
                write_client if write_client is not None else SignedWriteClient()
            ),
            evidence=app.state.evidence,
        )
        if engine is not None and app.state.identity_service is not None
        else None
    )

    # The task layer. It needs a database and nothing else: no client, no
    # signer, no vault (ADR-0004 2). It has no routes in this release - the
    # tasks section stays closed (ADR-0004 9) - so it is reachable only from
    # here and from tests, which is what a foundation package should look
    # like.
    app.state.tasks = TaskService(engine=engine) if engine is not None else None

    # The agent runtime (ADR-0008). Built when there is a database and a task
    # service, because it owns neither: it plans runs, calls tools from a
    # compile-time registry and moves the task through
    # ``TaskService.transition``, which is still the only function in this
    # product that writes a task state.
    #
    # Building it starts nothing. There is no scheduler, no background task
    # and no resume-on-launch: a run interrupted by a restart is *listed* by
    # ``interrupted_runs`` and continues only when a person asks (SI-224).
    #
    # The activity log is handed the chain only when the evidence archive
    # started, which is this application's way of saying the chain is
    # actually openable on this machine. Where it is not, the timeline still
    # records and simply does not claim a decision reached a chain it could
    # not reach.
    app.state.agent = (
        AgentService(
            engine=engine,
            data_dir=settings.data_dir,
            tasks=app.state.tasks,
            activity=ActivityLog(
                engine=engine,
                chain=chain if app.state.evidence is not None else None,
            ),
        )
        if engine is not None and app.state.tasks is not None
        else None
    )

    # The proof workspace (ADR-0009). Built when the task service and the
    # agent runtime are both there, because it owns neither and reads both: a
    # bundle is assembled out of rows those two services already own, and this
    # package adds no table, no file root and no outbound client.
    #
    # The evidence archive is passed when it started, and is optional for the
    # same reason it is optional elsewhere: on a machine where the audit
    # envelope cannot be opened, the proof workspace still assembles and
    # simply refuses the one operation that needs the archive - marking the
    # fourth field from an archived send.
    #
    # Building it starts nothing and contacts nobody. There is no scheduler,
    # no background task and no request at launch; the single-use share
    # approvals it mints live in process memory, stop being valid on their own
    # after ``SHARE_TOKEN_TTL_SECONDS`` and are *removed* on the next mint.
    #
    # The second half of that sentence is newer than the first. There is no
    # sweeper here and there never will be - a scheduler is exactly what this
    # process refuses to grow - so the store purges and caps itself inside
    # ``issue``, the way the composer's draft store always has. Before that,
    # "expire on their own" was true of validity and false of memory: fifty
    # abandoned approvals stayed fifty entries for the life of the process.
    app.state.proof = (
        ProofService(
            tasks=app.state.tasks,
            agent=app.state.agent,
            # The same root the agent writes under. The proof service reads
            # artifact bodies through ``agent.workspace``'s own containment and
            # reparse-point checks; this is the root those checks are applied
            # under, not a second file lane.
            data_dir=settings.data_dir,
            evidence=app.state.evidence,
        )
        if app.state.tasks is not None and app.state.agent is not None
        else None
    )

    # The read-only reconciliation scan (ADR-0004 6). ``in_flight`` has been
    # written since Package D and never read back; this reads it. One SELECT,
    # no outbound request, no row changed and no send continued. Whether to
    # continue is the user's decision, and continuing re-runs every check.
    app.state.task_reconciliation = _scan_unfinished(engine)

    # The OpenCode connection. Built unconditionally, because building it
    # contacts nobody: it reads the database when there is one and reports
    # "not configured" when there is not. Nothing here fetches the catalog,
    # verifies a credential or sends a metered request at startup - a launch
    # that could cost the user money would be the worst possible default, and
    # a test counts the outbound attempts rather than taking this comment's
    # word for it.
    app.state.opencode = opencode or OpenCodeService(
        engine=engine, data_dir=settings.data_dir
    )

    # The work scan (ADR-0007). Built unconditionally, because building it
    # contacts nobody: the constructor stores a client and a task service and
    # makes no request. Nothing here reads a room, fetches the room overview
    # or starts a timer at launch - there is no timer in the package at all -
    # and a test counts the outbound attempts during ``create_app`` rather
    # than taking this comment's word for it.
    # ``data_dir`` is the agent's own workspace root, not a second file lane.
    # A suggestion writes the request's full text into the new task's
    # workspace so a model can read it through the tool that already exists;
    # every guard on that surface - the name allow-list, containment, the
    # reparse walk and the three ceilings - applies unchanged, and the secret
    # scans that walk this root already cover the file.
    app.state.workscan = workscan or WorkScanService(
        tasks=app.state.tasks, data_dir=settings.data_dir
    )

    # The model planning lane (Package H4). Built when the agent runtime, the
    # task service and the OpenCode connection are all there, because it owns
    # none of them: it asks the model for a turn, looks every proposed call up
    # in the agent's own compile-time registry, and records the result through
    # the same ``plan_run`` a person's typed plan goes through.
    #
    # Building it contacts nobody. There is no request at launch, no timer and
    # no background task: a turn happens inside the request that asked for it,
    # and the ceiling on how many turns one task may spend is the compile-time
    # one in ``agent/budget.py``.
    #
    # The sessions it keeps live in process memory and are lost on restart,
    # which is deliberate rather than unfinished: a stored conversation is the
    # thing somebody would resume, and SI-224 says a restart resumes nothing.
    app.state.model_planner = (
        ModelPlannerService(
            agent=app.state.agent,
            tasks=app.state.tasks,
            opencode=app.state.opencode,
        )
        if app.state.agent is not None and app.state.tasks is not None
        else None
    )

    app.include_router(session_routes.router)
    app.include_router(api_routes.router)
    app.include_router(identity_routes.router)
    app.include_router(identity_routes.gate_router)
    app.include_router(conformance_routes.router)
    app.include_router(technocore_routes.router)
    app.include_router(compose_routes.router)
    app.include_router(evidence_routes.router)
    app.include_router(opencode_routes.router)
    app.include_router(workscan_routes.router)
    app.include_router(agent_routes.router)
    app.include_router(proof_routes.router)
    app.include_router(planner_routes.router)

    # Registered last so it cannot shadow /api or /session.
    resolved_dist = shipped_web_dist() if web_dist is SHIPPED_WEB_DIST else web_dist
    if resolved_dist is not None:
        _mount_spa(app, resolved_dist)

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

    # The 422's twin. FastAPI's default validation handler answers with
    # Pydantic's error list, and every entry of it carries ``input`` - the
    # value that was submitted. On the credential route that value is the
    # provider key, and a *type* error is raised before ``SecretStr`` ever
    # wraps it, so the default handler quoted the raw key straight back
    # (SI-243). This one keeps the location, the message and the type, and
    # drops every key that carries a submitted value.
    app.add_exception_handler(RequestValidationError, validation_error_shield)

    return app
