"""Conformance status endpoint.

One read-only route, behind the same session, Host, Origin and Sec-Fetch-Site
guards as everything else - they are global middleware, so this file cannot
opt out of them.

The response is public metadata about this build: which parts of the write
contract were checked, how many vectors backed each one, and the pinned
reference, package, Python and Unicode versions that produced the verdict.
The vector bundle itself is never returned. It contains TEST-ONLY seeds, and
while those are published fixtures, an endpoint that serves key-shaped bytes
is a habit worth not forming.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from technocore_conform import SelfTestResult

from station_api.conformance import ConformanceService
from station_api.dependencies import require_session
from station_api.schemas import ConformanceCheckStatus, ConformanceStatusResponse
from station_api.security.sessions import Session

router = APIRouter(prefix="/api/conformance")

CurrentSession = Annotated[Session, Depends(require_session)]

#: Short forms shown in the UI. Long enough to identify, short enough to read.
_SHORT_DIGEST_CHARS = 12
_SHORT_COMMIT_CHARS = 7


def _service(request: Request) -> ConformanceService:
    service: ConformanceService | None = getattr(request.app.state, "conformance", None)
    if service is None:  # pragma: no cover - always wired by create_app
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Uygunluk servisi kullanilabilir degil.",
        )
    return service


def to_response(result: SelfTestResult) -> ConformanceStatusResponse:
    """Project a self-test verdict onto the public response model."""
    return ConformanceStatusResponse(
        passed=result.passed,
        checks=[
            ConformanceCheckStatus(
                name=check.name,
                passed=check.passed,
                vectors=check.vectors,
                detail=check.detail,
            )
            for check in result.checks
        ],
        failures=list(result.failures),
        capabilities=list(result.capabilities),
        bundle_digest=result.bundle_digest,
        bundle_digest_short=result.bundle_digest[:_SHORT_DIGEST_CHARS],
        bundle_vectors=result.bundle_vectors,
        upstream_commit=result.upstream_commit,
        upstream_commit_short=result.upstream_commit[:_SHORT_COMMIT_CHARS],
        package_version=result.package_version,
        python_version=result.python_version,
        unicode_version=result.unicode_version,
        bundle_unicode_version=result.bundle_unicode_version,
        unicode_version_matches=result.unicode_version_matches,
    )


@router.get("/status", response_model=ConformanceStatusResponse)
async def read_conformance_status(request: Request, session: CurrentSession) -> Response:
    del session
    model = to_response(_service(request).result())
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
