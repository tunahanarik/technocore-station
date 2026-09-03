"""Request guards for the loopback core.

There is deliberately **no CORS middleware anywhere in this project** (INV-03).
The frontend and the backend share one origin; development uses a Vite proxy.
Adding permissive cross-origin headers would defeat every guard below.

Outermost to innermost the chain is:

    SecurityHeaders -> RequestId -> HostGuard -> FetchMetadata -> Session -> Csrf

SecurityHeaders sits outermost so that the 421 and 403 responses produced by
the guards below it still carry the hardening headers (SI-33). RequestId sits
directly inside it so that every one of those rejections - and every ordinary
response - also carries the correlation id (SI-125).

One response class is built outside this chain entirely: Starlette runs the
``Exception`` handler in ServerErrorMiddleware, which wraps even
SecurityHeaders, so ``unhandled_exception_shield`` below applies the hardening
headers and the request id itself (SI-126, IMP-260).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from secrets import compare_digest
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from station_api.config import (
    CSRF_HEADER_NAME,
    REQUEST_ID_HEADER_NAME,
    SESSION_COOKIE_NAME,
)
from station_api.security.sessions import SessionStore

_logger = logging.getLogger(__name__)

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


def apply_security_headers(response: Response, path: str) -> None:
    """Attach the hardening headers to one response.

    The single source of truth for both places a response can be born: the
    middleware chain below, and the unhandled-exception shield that Starlette
    runs outside it. Neither copy can drift from the other because there is
    no copy.
    """
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    if path.startswith(NO_STORE_PREFIXES):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response, including error responses."""

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        response = await call_next(request)
        apply_security_headers(response, request.url.path)
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Stamp every response with a fresh correlation id (SI-125).

    ``uuid4().hex`` is random and carries no request content, so the id can
    never leak anything and never collides with the redaction layer in
    ``logging_setup``: it is not a secret, is never registered as one, and
    does not match the ``/session/<token>`` scrub pattern.

    The id is also stored on ``request.state`` so the unhandled-exception
    shield can put the same value in the 500 body's header and in the server
    log line that carries the traceback.
    """

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        request_id = uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER_NAME] = request_id
        return response


async def unhandled_exception_shield(request: Request, exc: Exception) -> Response:
    """Last line of defence: an unhandled exception never reaches the client.

    Registered for ``Exception`` on the application. Starlette places that
    handler in ServerErrorMiddleware - *outside* the whole middleware chain -
    so this response would bypass SecurityHeaders and RequestId; the shield
    therefore applies both itself, through the same helper and the same
    stored id (SI-126).

    The body is a constant. The traceback, the exception type and every path
    go to the server log only, keyed by the request id so a user-visible id
    can be matched to the full story. The URL path is deliberately not logged
    here: ``/session/<token>`` would put a live token one formatting layer
    away from disk (SI-07).
    """
    request_id = getattr(request.state, "request_id", None) or uuid4().hex
    _logger.exception(
        "Unhandled exception while serving a request; request_id=%s",
        request_id,
        exc_info=exc,
    )
    response = _denied("internal_error", status_code=500)
    response.headers[REQUEST_ID_HEADER_NAME] = request_id
    apply_security_headers(response, request.url.path)
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
