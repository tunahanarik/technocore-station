"""Request guards for the loopback core.

There is deliberately **no CORS middleware anywhere in this project** (INV-03).
The frontend and the backend share one origin; development uses a Vite proxy.
Adding permissive cross-origin headers would defeat every guard below.

Outermost to innermost the chain is:

    SecurityHeaders -> HostGuard -> FetchMetadata -> Session -> Csrf

SecurityHeaders sits outermost so that the 421 and 403 responses produced by
the guards below it still carry the hardening headers (SI-33).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from secrets import compare_digest

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from station_api.config import CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from station_api.security.sessions import SessionStore

#: Methods that cannot change server state and therefore need no CSRF proof.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Paths whose responses must never be cached.
NO_STORE_PREFIXES = ("/api/", "/session/")

# React Aria (which HeroUI v3 is built on) injects exactly one inline
# stylesheet at runtime:
#
#     @layer { [data-react-aria-pressable] { touch-action: pan-x pan-y pinch-zoom; } }
#
# It fixes touch behaviour on pressable elements. Allowing it by hash keeps
# 'unsafe-inline' out of style-src: only this exact stylesheet is permitted.
#
# On a HeroUI/React Aria upgrade this hash may change. The failure mode is
# safe and loud - the stylesheet is blocked and the browser console names the
# expected hash, which is then updated here. Verify with tests/security and a
# real browser after any upgrade.
REACT_ARIA_PRESSABLE_STYLE_HASH = "'sha256-38RhXrc7EdReTKsOm23ZPOCUgniTUUcjky8QOOrQx6o='"

_CSP = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self'",
        # Inline <style> elements are blocked except the single hashed one
        # above; the style *attribute* is allowed separately, because React
        # Aria positions overlays and sets colour-scheme that way.
        f"style-src 'self' {REACT_ARIA_PRESSABLE_STYLE_HASH}",
        "style-src-attr 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "manifest-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
        "object-src 'none'",
    )
)

# Browser capabilities this application has no use for. clipboard-write is
# intentionally absent from the deny list: copying a public DID is a planned
# Stage 2 affordance.
_PERMISSIONS_POLICY = ", ".join(
    f"{feature}=()"
    for feature in (
        "accelerometer",
        "autoplay",
        "camera",
        "display-capture",
        "encrypted-media",
        "fullscreen",
        "geolocation",
        "gyroscope",
        "hid",
        "idle-detection",
        "magnetometer",
        "microphone",
        "midi",
        "payment",
        "publickey-credentials-get",
        "screen-wake-lock",
        "serial",
        "usb",
        "xr-spatial-tracking",
    )
)

_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": _PERMISSIONS_POLICY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

CallNext = Callable[[Request], Awaitable[Response]]


def _denied(code: str, status_code: int) -> JSONResponse:
    """A guard rejection.

    The body carries a stable machine-readable code and no request detail, so
    a rejection can never echo back a header value an attacker supplied.
    """
    return JSONResponse({"detail": code}, status_code=status_code)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response, including error responses."""

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        if request.url.path.startswith(NO_STORE_PREFIXES):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response


class HostGuardMiddleware(BaseHTTPMiddleware):
    """Require an exact ``127.0.0.1:<port>`` Host header.

    This is the DNS-rebinding defence: a hostile page that resolves its own
    domain to the loopback address still sends its own name in Host, so it
    never matches. ``localhost`` is rejected too, because it is a name and not
    the literal address this process bound to (SI-11, SI-12, SI-13).
    """

    def __init__(self, app: ASGIApp, *, allowed_hosts: frozenset[str]) -> None:
        super().__init__(app)
        self._allowed_hosts = allowed_hosts

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        host = request.headers.get("host", "")
        if host not in self._allowed_hosts:
            return _denied("host_not_allowed", status_code=421)
        return await call_next(request)


class FetchMetadataMiddleware(BaseHTTPMiddleware):
    """Reject anything that did not originate from this application.

    ``Origin`` is checked when present. ``Sec-Fetch-Site`` must be
    ``same-origin``; ``none`` is accepted only for a safe navigation, which is
    how the launcher's own ``/session/<token>`` tab arrives (IMP-104).
    """

    def __init__(self, app: ASGIApp, *, allowed_origins: frozenset[str]) -> None:
        super().__init__(app)
        self._allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and origin not in self._allowed_origins:
            return _denied("origin_not_allowed", status_code=403)

        site = request.headers.get("sec-fetch-site")
        if site is not None and site != "same-origin":
            is_safe_navigation = site == "none" and request.method in SAFE_METHODS
            if not is_safe_navigation:
                return _denied("cross_origin_request_blocked", status_code=403)

        return await call_next(request)


class SessionMiddleware(BaseHTTPMiddleware):
    """Resolve the session cookie into ``request.state.session``.

    This middleware only *loads* the session; it never rejects. Enforcement is
    the job of the ``require_session`` dependency (401) and of CsrfMiddleware
    (403), so that a missing cookie on a read is distinguishable from a failed
    CSRF proof on a write.
    """

    def __init__(self, app: ASGIApp, *, store: SessionStore) -> None:
        super().__init__(app)
        self._store = store

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        cookie = request.cookies.get(SESSION_COOKIE_NAME)
        request.state.session = self._store.get(cookie)
        return await call_next(request)


class CsrfMiddleware(BaseHTTPMiddleware):
    """Require a matching ``X-Station-CSRF`` header on state-changing requests.

    The value is compared with ``compare_digest`` so a wrong header cannot be
    discovered by timing (SI-22). It is never echoed back or logged.
    """

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        if request.method in SAFE_METHODS:
            return await call_next(request)

        session = getattr(request.state, "session", None)
        if session is None:
            return _denied("csrf_session_required", status_code=403)

        provided = request.headers.get(CSRF_HEADER_NAME)
        if provided is None or not compare_digest(provided, session.csrf_token):
            return _denied("csrf_token_invalid", status_code=403)

        return await call_next(request)
