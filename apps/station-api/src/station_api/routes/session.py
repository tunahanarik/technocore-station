"""Browser handoff.

The launcher opens ``/session/<token>`` once. Redeeming the token revokes it,
mints a session, sets the cookie and redirects to a clean ``/`` so the token
never lingers in the address bar, in history or in a Referer header.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from station_api.config import SESSION_COOKIE_NAME

router = APIRouter()


@router.get("/session/{token}", include_in_schema=False)
async def redeem_bootstrap_token(token: str, request: Request) -> RedirectResponse:
    if not request.app.state.bootstrap_tokens.consume(token):
        # One message for unknown, expired and already-used tokens alike, so
        # the response cannot be used to probe which case applies.
        raise HTTPException(status_code=404, detail="invalid_bootstrap_token")

    session = request.app.state.sessions.create()

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_id,
        httponly=True,
        samesite="strict",
        path="/",
        # No Secure flag: this is loopback HTTP and browsers do not handle
        # Secure cookies consistently there. Documented in SECURITY.md 3.
    )
    return response
