"""Route dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request

from station_api.security.sessions import Session


def require_session(request: Request) -> Session:
    """Reject a request that carries no valid session cookie.

    401 rather than 403: the caller is unauthenticated, not forbidden. CSRF
    failures on state-changing requests are the 403 case and are handled by
    CsrfMiddleware before a route is ever reached (SI-10, SI-19).
    """
    # request.state is dynamically typed; annotate so the contract is explicit.
    session: Session | None = getattr(request.state, "session", None)
    if session is None:
        raise HTTPException(status_code=401, detail="session_required")
    return session
