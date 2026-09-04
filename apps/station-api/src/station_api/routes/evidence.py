"""Evidence endpoints: read the archive, capture a line, export, verify.

    GET  /api/evidence/records   the archive plus the audit chain's verdict
    POST /api/evidence/capture   one read-only capture, on request only
    POST /api/evidence/export    JSON or Markdown, with explicit consent
    GET  /api/evidence/audit     recompute the chain and compare its head

Every state-changing route inherits the global session, CSRF, Host, Origin
and Sec-Fetch-Site guards - they are middleware, so nothing in this file can
opt out.

What is deliberately absent
---------------------------
* **No resend.** There is no route, parameter or flag that sends anything
  again. A capture is a read; ``line_not_found`` is not a reason to publish
  a second message, and this file offers no way to (ADR-0002 3, ADR-0003 4).
* **No room, URL, host or path parameter.** ``capture`` takes an evidence id
  and reads the room from the stored row, which was itself resolved through
  the closed write registry. There is no code path from a request body to an
  outbound address.
* **No export without consent.** ``acknowledged`` has no default, so a body
  that omits it never reaches a handler, and the service takes an
  ``ExportConsent`` that cannot be constructed without it. Two independent
  refusals, because this one is worth two.
* **No raw bytes in a listing.** Request and response bytes are archived and
  exported on consent; the listing returns hashes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from station_api.dependencies import require_session
from station_api.downloads import content_disposition, safe_download_filename
from station_api.evidence.export import (
    CHAIN_SENTENCE,
    ExportConsent,
    ExportRefusedError,
)
from station_api.evidence.records import EvidenceView
from station_api.evidence.service import EvidenceError, EvidenceService
from station_api.schemas import (
    AuditChainResponse,
    EvidenceCaptureRequest,
    EvidenceCaptureResponse,
    EvidenceExportRequest,
    EvidenceLevelStatus,
    EvidenceListResponse,
    EvidenceRecordResponse,
)
from station_api.security.sessions import Session

router = APIRouter(prefix="/api/evidence")

CurrentSession = Annotated[Session, Depends(require_session)]

#: Evidence is session-scoped local data; none of it belongs in a cache.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

#: The download stem. A constant; the format's suffix is appended through the
#: sanitiser, never interpolated raw (ADR-0003 9).
EXPORT_STEM = "technocore-station-kanit"

#: When the export was asked for. A header rather than a field in the
#: document, so the document itself is byte-identical between two exports of
#: an unchanged archive (``evidence/export.py``).
EXPORTED_AT_HEADER = "X-Station-Exported-At"


def _service(request: Request) -> EvidenceService:
    service: EvidenceService | None = getattr(request.app.state, "evidence", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kanit servisi kullanilabilir degil.",
            headers=_NO_STORE,
        )
    return service


def _markers(request: Request) -> frozenset[str]:
    """Room class markers from the last successful manifest check.

    Empty when no check has succeeded, which makes
    ``resolve_export_target`` refuse - the same fail-closed answer the write
    path gives, from the same data, so the two cannot disagree about which
    rooms exist.
    """
    technocore = getattr(request.app.state, "technocore", None)
    if technocore is None:
        return frozenset()
    return frozenset(technocore.status().room_class_markers)


def _json(
    model: EvidenceListResponse | EvidenceCaptureResponse | AuditChainResponse,
) -> Response:
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers=_NO_STORE,
    )


def _to_response(view: EvidenceView) -> EvidenceRecordResponse:
    return EvidenceRecordResponse(
        id=view.id,
        reservation_id=view.reservation_id,
        room=view.room,
        did=view.did,
        nonce=view.nonce,
        canonical_sha256=view.canonical_sha256,
        signature=view.signature,
        http_status=view.http_status,
        write_outcome=view.write_outcome,  # type: ignore[arg-type]
        capture_state=view.capture_state,  # type: ignore[arg-type]
        capture_detail=view.capture_detail,
        captured_at=view.captured_at,
        room_generation=view.room_generation,
        capture_generation=view.capture_generation,
        generation_changed=view.generation_changed,
        captured_line_offset=view.captured_line_offset,
        captured_line_length=view.captured_line_length,
        stream_sha256=view.stream_sha256,
        stream_bytes=view.stream_bytes,
        stream_truncated=view.stream_truncated,
        unreadable_lines=view.unreadable_lines,
        request_sha256=view.request_sha256,
        response_sha256=view.response_sha256,
        recorded_at=view.recorded_at,
        # Level 4 is null, always, and is present in the payload so a reader
        # sees the decision instead of a missing key.
        external_anchor=view.external_anchor,
        levels=[
            EvidenceLevelStatus(
                level=level.level,  # type: ignore[arg-type]
                name=level.name,
                present=level.present,
                detail=level.detail,
            )
            for level in view.levels
        ],
    )


@router.get("/records", response_model=EvidenceListResponse)
async def read_records(request: Request, session: CurrentSession) -> Response:
    """The archive, newest first, with the audit chain's verdict beside it."""
    del session
    service = _service(request)
    records = service.list_records()
    report = service.verify_chain()

    return _json(
        EvidenceListResponse(
            records=[_to_response(view) for view in records],
            record_count=len(records),
            chain_state=report.verdict.value,
            chain_detail=report.detail,
            chain_link_count=report.link_count,
        )
    )


@router.post("/capture", response_model=EvidenceCaptureResponse)
def capture_line(
    request: Request, session: CurrentSession, body: EvidenceCaptureRequest
) -> Response:
    """Read the room's export once and look for our own line.

    ``def`` rather than ``async def``, for the reason the composer's blocking
    routes are (IMP-296): this reads a stream with a 30-second read timeout
    through synchronous httpx, and on the event loop that would stall every
    other request for the whole scan.
    """
    service = _service(request)
    del session

    try:
        outcome = service.capture(
            evidence_id=body.evidence_id, markers=_markers(request)
        )
    except EvidenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc

    return _json(
        EvidenceCaptureResponse(
            evidence_id=outcome.evidence_id,
            state=outcome.state.value,
            detail=outcome.detail,
            server_observation=outcome.is_server_observation,
            room_generation=outcome.generation,
            line_offset=outcome.line_offset,
            line_length=outcome.line_length,
            stream_sha256=outcome.stream_sha256,
            scanned_bytes=outcome.scanned_bytes,
            stream_truncated=outcome.truncated,
        )
    )


@router.post("/export")
def export_records(
    request: Request, session: CurrentSession, body: EvidenceExportRequest
) -> Response:
    """Return the archive as a download. Explicit consent required.

    Delivered the way the recovery file is (ADR-0003 9): an HTTP response
    with a ``Content-Disposition``, downloaded by the browser. The server
    writes nothing to any path - not one the user chose and not a fixed
    export directory - so path traversal, symlinks, reparse points and
    overwrite prompts are absent from this feature rather than defended
    against in code nobody has reviewed.
    """
    del session
    service = _service(request)

    if body.acknowledged is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Disa aktarim acik onay ister. Onay verilmeden dosya "
                "uretilmez."
            ),
            headers=_NO_STORE,
        )

    try:
        consent = ExportConsent.granted(
            acknowledged=True, now=datetime.now(UTC)
        )
        result = service.export(export_format=body.format, consent=consent)
    except (ExportRefusedError, EvidenceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers=_NO_STORE,
        ) from exc

    filename = safe_download_filename(EXPORT_STEM, suffix=result.suffix)
    return Response(
        content=result.payload,
        media_type=result.media_type,
        headers={
            **_NO_STORE,
            "Content-Disposition": content_disposition(filename),
            # Beside the bytes, not inside them. The body is the archive and
            # is byte-identical between two exports of an unchanged archive;
            # when the copy was made is a fact about the copy, it is already
            # an audit event, and putting it in the document would have made
            # "export twice and diff" a promise with a footnote.
            EXPORTED_AT_HEADER: result.exported_at.isoformat(),
        },
    )


@router.get("/audit", response_model=AuditChainResponse)
async def read_audit(request: Request, session: CurrentSession) -> Response:
    """Recompute the chain and compare it against its separately held head.

    ``claim`` carries the only sentence permitted about what this provides.
    It is returned rather than left to the UI so the wording cannot drift
    between the two surfaces.
    """
    del session
    report = _service(request).verify_chain()

    return _json(
        AuditChainResponse(
            state=report.verdict.value,
            detail=report.detail,
            link_count=report.link_count,
            head_count=report.head_count,
            first_bad_seq=report.first_bad_seq,
            claim=CHAIN_SENTENCE,
        )
    )


__all__ = ["EXPORTED_AT_HEADER", "EXPORT_STEM", "router"]
