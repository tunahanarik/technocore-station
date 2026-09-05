"""Proof workspace endpoints: read the proof, prepare it, take it, accept it.

    GET  /api/proof/{task_id}               artifacts, digests, gaps, claims
    POST /api/proof/{task_id}/prepare       mint one single-use share approval
    POST /api/proof/{task_id}/share         spend it and download the bundle
    POST /api/proof/{task_id}/acceptance    a person accepts what they read
    POST /api/proof/{task_id}/public-share  point field four at an archived send

Every state-changing route inherits the global session, CSRF, Host, Origin and
Sec-Fetch-Site guards - they are middleware, so nothing in this file can opt
out - and every read answers ``no-store``.

What is deliberately absent
---------------------------
* **No route that writes the bundle to a path.** ``share`` returns an HTTP
  response with a ``Content-Disposition``; the browser decides where it goes.
  There is no directory parameter, no filename parameter and no fixed export
  root, so path traversal, symlinks, reparse points and overwrite prompts are
  absent from this feature rather than defended against (ADR-0003 9,
  ADR-0009 3).
* **No archive.** Two formats, both plain text. Nothing is packed and nothing
  is ever unpacked.
* **No route that sends anything anywhere.** External publication goes through
  the composer's three-step chain and its reviewed write client;
  ``OUTBOUND_CLIENT_MODULES`` stays at five (ADR-0009 11). ``public-share``
  *records* that a send happened, by pointing at the archived evidence of one;
  it cannot cause a send.
* **No route that sets an evidence field to a value the caller chose.**
  ``acceptance`` writes ``user_acceptance`` and nothing else, and only after
  the bundle the person read is confirmed unchanged. ``public-share`` writes
  ``public_share`` and takes its ``verified`` from the archived send's own
  outcome, never from the request.
* **No transition.** Accepting does not move the task. ``ready_to_publish``
  is derived from three separately verified fields and is not something a
  route hands out as a side effect (SI-222, ADR-0009 8).
* **No second consent shape.** ``share`` spends a single-use approval bound to
  the bundle digest, and *also* requires ``acknowledged`` in the body - two
  independent refusals, because a file leaving this machine is worth two.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel

from station_api.dependencies import require_session
from station_api.downloads import content_disposition, safe_download_filename
from station_api.modules.registry import ModuleId, ModuleRegistryError, get_module
from station_api.proof.bundle import (
    BUNDLE_FORMATS,
    BUNDLE_STEM,
    ProofBundle,
)
from station_api.proof.language import BUNDLE_SCOPE_SENTENCE, HASH_SCOPE_SENTENCE
from station_api.proof.service import ProofError, ProofService
from station_api.schemas import (
    ProjectModuleStatus,
    ProofAcceptanceRequest,
    ProofArtifactStatus,
    ProofClaimStatus,
    ProofMissingStatus,
    ProofPrepareResponse,
    ProofPublicShareRequest,
    ProofShareRequest,
    ProofWorkspaceResponse,
)
from station_api.security.sessions import Session
from station_api.tasks.service import TaskError, TaskService
from station_api.tasks.views import to_module_status, to_task_status

router = APIRouter(prefix="/api/proof")

CurrentSession = Annotated[Session, Depends(require_session)]

#: A proof is local, momentary and never belongs in a cache.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

#: When the copy was made. Beside the bytes rather than inside them, so two
#: downloads of an unchanged bundle are byte-identical - the decision
#: ``evidence/export.py`` records at length.
DELIVERED_AT_HEADER = "X-Station-Delivered-At"

#: Which refusal reason gets which status code. A closed mapping rather than a
#: guess per raise site, so two refusals of the same kind cannot answer
#: differently depending on which function raised them.
_CONFLICT_REASONS = frozenset(
    {
        "bundle_changed",
        "content_version_changed",
        "approval_invalid",
        "approval_foreign_session",
        "approval_foreign_task",
        "evidence_unavailable",
    }
)

_MISSING_REASONS = frozenset({"task_missing", "evidence_record_missing"})


def _refuse(exc: ProofError | TaskError) -> HTTPException:
    """One refusal, one status code, one sentence the user can read."""
    if exc.reason in _MISSING_REASONS:
        code = status.HTTP_404_NOT_FOUND
    elif exc.reason in _CONFLICT_REASONS:
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=str(exc), headers=_NO_STORE)


def _proof(request: Request) -> ProofService:
    service: ProofService | None = getattr(request.app.state, "proof", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kanit calisma alani kullanilabilir degil.",
            headers=_NO_STORE,
        )
    return service


def _tasks(request: Request) -> TaskService:
    service: TaskService | None = getattr(request.app.state, "tasks", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gorev yuzeyi kullanilabilir degil.",
            headers=_NO_STORE,
        )
    return service


def _json(model: BaseModel) -> Response:
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


def _module_status(tasks: TaskService, task_id: str) -> ProjectModuleStatus:
    view = tasks.get(task_id)
    try:
        record = get_module(ModuleId(view.module_id))
    except (ValueError, ModuleRegistryError) as exc:
        raise TaskError(
            "Bu gorev kayitli olmayan bir modul kimligi tasiyor.",
            reason="module_unknown",
        ) from exc
    return to_module_status(record, tasks.module_completion(task_id))


def _workspace(
    proof: ProofService, tasks: TaskService, task_id: str, bundle: ProofBundle
) -> ProofWorkspaceResponse:
    """Project one built bundle onto the wire. Decides nothing.

    The document is the single source: the artifacts, the digests, the named
    gaps and the two unproduced claims are read out of it rather than
    recomputed here, so the file a person downloads and the screen they read
    cannot disagree about what is missing.
    """
    document = bundle.document
    artifacts = document["artifacts"]
    claims = document["claims"]

    return ProofWorkspaceResponse(
        task=to_task_status(tasks.get(task_id), tasks.gate(task_id)),
        module=_module_status(tasks, task_id),
        artifacts=[
            ProofArtifactStatus(
                name=str(item["name"]),
                byte_count=int(item["byte_count"]),
                sha256=str(item["sha256"]),
            )
            for item in artifacts["files"]
        ],
        file_count=int(artifacts["file_count"]),
        total_bytes=int(artifacts["total_bytes"]),
        artifact_set_sha256=str(artifacts["set_sha256"]),
        bundle_sha256=bundle.sha256,
        missing=[
            ProofMissingStatus(
                key=str(entry["key"]),
                state=str(entry["state"]),
                detail=str(entry["detail"]),
            )
            for entry in document["missing"]
        ],
        claims=[
            ProofClaimStatus(
                key=key,
                state=str(value["state"]),  # type: ignore[arg-type]
                detail=str(value["detail"]),
            )
            for key, value in claims.items()
        ],
        formats=list(BUNDLE_FORMATS),
        hash_scope=HASH_SCOPE_SENTENCE,
        bundle_scope=BUNDLE_SCOPE_SENTENCE,
        reproduction=str(document["notes"]["reproduction"]),
        approval_ttl_seconds=proof.approval_ttl_seconds,
    )


@router.get("/{task_id}", response_model=ProofWorkspaceResponse)
def read_proof(request: Request, session: CurrentSession, task_id: str) -> Response:
    """One task's proof, as it stands. Reads the filesystem; writes nothing.

    ``def`` rather than ``async def``, for the reason the run listing is:
    reading and digesting a directory on the event loop would stall every
    other request.
    """
    del session
    proof = _proof(request)
    tasks = _tasks(request)
    try:
        return _json(_workspace(proof, tasks, task_id, proof.build(task_id)))
    except (ProofError, TaskError) as exc:
        raise _refuse(exc) from exc


@router.post("/{task_id}/prepare", response_model=ProofPrepareResponse)
def prepare_share(
    request: Request, session: CurrentSession, task_id: str
) -> Response:
    """Show what would leave, and mint one approval bound to exactly that.

    Preparing sends nothing and writes nothing. It returns the bundle's digest
    beside a single-use token, so the second request can be checked against
    the first: if an artifact changes in between, the digest changes and the
    approval no longer matches (ADR-0009 4).
    """
    proof = _proof(request)
    tasks = _tasks(request)
    try:
        token, bundle = proof.prepare_share(
            task_id, session_id=session.session_id
        )
        return _json(
            ProofPrepareResponse(
                workspace=_workspace(proof, tasks, task_id, bundle),
                share_token=token,
                expires_in_seconds=proof.approval_ttl_seconds,
            )
        )
    except (ProofError, TaskError) as exc:
        raise _refuse(exc) from exc


@router.post("/{task_id}/share")
def take_bundle(
    request: Request,
    session: CurrentSession,
    task_id: str,
    body: ProofShareRequest,
) -> Response:
    """Spend the approval and hand the file to the browser. Writes no path.

    ``acknowledged`` is checked here as well as being ``Literal[True]`` on the
    model. Redundant on purpose: the model refuses a body that omits it, and
    this refuses a caller that reached the handler some other way - the same
    doubling the evidence export uses, for a file that leaves this machine.
    """
    proof = _proof(request)
    if body.acknowledged is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Dis paylasim acik onay ister. Onay verilmeden paket "
                "uretilmez."
            ),
            headers=_NO_STORE,
        )
    try:
        result = proof.deliver_share(
            task_id,
            session_id=session.session_id,
            share_token=body.share_token,
            bundle_format=body.format,
        )
    except (ProofError, TaskError) as exc:
        raise _refuse(exc) from exc

    filename = safe_download_filename(BUNDLE_STEM, suffix=result.suffix)
    return Response(
        content=result.payload,
        media_type=result.media_type,
        headers={
            **_NO_STORE,
            "Content-Disposition": content_disposition(filename),
            DELIVERED_AT_HEADER: result.delivered_at.isoformat(),
        },
    )


@router.post("/{task_id}/acceptance", response_model=ProofWorkspaceResponse)
def record_acceptance(
    request: Request,
    session: CurrentSession,
    task_id: str,
    body: ProofAcceptanceRequest,
) -> Response:
    """Record that a person accepted this exact bundle. Moves no state.

    This is the only route in the product that writes ``user_acceptance``, and
    it exists because there was no surface at all before Package H3 - the
    field was defined, reported and unfillable, which is precisely the state
    ``agent_workspace``'s seventh requirement was waiting out (ADR-0009 8).

    It does not transition the task. Acceptance is the input to a publication
    decision; a route that also moved the task would make
    ``ready_to_publish`` something a request produces rather than something
    three verified fields derive (SI-222).
    """
    del session
    proof = _proof(request)
    tasks = _tasks(request)
    try:
        proof.record_acceptance(
            task_id, bundle_sha256=body.bundle_sha256, detail=body.detail
        )
        return _json(_workspace(proof, tasks, task_id, proof.build(task_id)))
    except (ProofError, TaskError) as exc:
        raise _refuse(exc) from exc


@router.post("/{task_id}/public-share", response_model=ProofWorkspaceResponse)
def record_public_share(
    request: Request,
    session: CurrentSession,
    task_id: str,
    body: ProofPublicShareRequest,
) -> Response:
    """Point the fourth field at an archived send. Causes no send.

    The body carries an evidence-record identity and nothing else. There is no
    room parameter, no address and no text: this route cannot reach an
    outbound client, and what it records is that a send *already* in the
    archive belongs to this task. ``verified`` comes from that record's own
    write outcome, never from the request (ADR-0009 1).
    """
    del session
    proof = _proof(request)
    tasks = _tasks(request)
    try:
        proof.record_public_share(
            task_id, evidence_id=body.evidence_id, detail=body.detail
        )
        return _json(_workspace(proof, tasks, task_id, proof.build(task_id)))
    except (ProofError, TaskError) as exc:
        raise _refuse(exc) from exc


__all__ = ["DELIVERED_AT_HEADER", "router"]
