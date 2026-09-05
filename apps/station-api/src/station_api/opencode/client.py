"""The OpenCode Go client: the fourth outbound surface, and the first with a credential.

Three clients already exist and each got its own module for the same reason
this one does (ADR-0003 1, ADR-0005 6): a different capability, a different
registry and a different failure policy. This one adds two more differences
neither of the others has - a **different origin** and a **different
authentication model**. No Technocore client carries a credential; this one
carries the only one in the application.

That single difference reshapes several rules
---------------------------------------------
*Retries.* The read client retries transport faults, 5xx and 429, because a
public document costs nothing to ask for twice. Here a request that left the
process may already have been billed even if the answer never came back, so
the **metered** endpoints are attempted exactly once and a lost response is
reported as :class:`~station_api.opencode.errors.OpenCodeLostResponseError`
rather than retried. The catalog is free and unauthenticated, so it gets one
bounded retry and no more.

*Headers.* :func:`credential_headers` is the only place in this repository
that writes an ``Authorization`` header, and it says in one line that the
scheme is **not published**. When the contract appears, one line changes.

*Response text.* An upstream error body can echo back what was sent. The
credential is registered for redaction by the service before any call, and
:func:`station_api.logging_setup.redact` is applied to every excerpt this
module produces, so a reflected key cannot reach a log line, an exception or
the UI.

Transport rules, unchanged from the reviewed clients
----------------------------------------------------
* TLS verification is always on. ``verify`` is never passed and never
  exposed; the only transport the test seam accepts is an
  ``httpx.MockTransport``, which negotiates no TLS at all.
* Redirects are never followed. Following one is how a request carrying a
  credential leaves the allow-listed origin.
* Timeouts are explicit on all four phases.
* The body cap is enforced on **decompressed** bytes as they stream in.
* No cookies, no DID, no CSRF value, no session cookie, no file path and no
  user data of any kind is attached. The outbound request carries the
  provider credential, a random per-process session id, our own User-Agent
  and nothing else.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from station_api.logging_setup import forget_secret, redact, register_secret
from station_api.opencode.errors import (
    OpenCodeLostResponseError,
    OpenCodeRequestError,
    ResponseTooLargeError,
    UnexpectedRedirectError,
)
from station_api.opencode.registry import (
    OPENCODE_HOST,
    OPENCODE_PORT,
    OPENCODE_SCHEME,
    EndpointId,
    OpenCodeEndpoint,
    Protocol,
    get_endpoint,
    protocol_endpoint,
)

#: Our own, and deliberately free of anything identifying. The documentation
#: asks clients not to use a broad user agent; it does not ask us to pretend
#: to be another client, and we do not (ADR-0005 3, 11).
USER_AGENT = "TechnocoreStation/0.1 (+https://github.com/tunahanarik/technocore-station)"

# ---------------------------------------------------------------------------
# The authentication header: declared, and declared unverified
# ---------------------------------------------------------------------------

#: STILL NOT PUBLISHED IN THE OFFICIAL DOCUMENTATION - BUT NOW MEASURED.
#:
#: ADR-0005 3 recorded that none of ``opencode.ai/docs/go``, ``/docs/zen``,
#: ``/docs/providers`` or ``/docs/config`` names an authentication header,
#: so ``Authorization: Bearer`` was written here as a labelled assumption.
#: **That half is now measured** (ADR-0012): a metered
#: ``POST /zen/go/v1/chat/completions`` carrying this header answered 200,
#: which no unauthenticated request can. The header is therefore correct.
#:
#: What did **not** change: the documentation still does not publish it, so
#: the provider is free to alter it without a contract we could point at.
#: That is why the label survives rather than being deleted - it is now a
#: statement about the *source*, not about our confidence. It stays written
#: **once**, here, and the label still reaches the user in the status
#: endpoint rather than living only in this comment.
AUTH_HEADER_NAME = "Authorization"
AUTH_SCHEME = "Bearer"

#: The documentation **does** ask for this one. The value is random per
#: process, is derived from nothing about the user or the identity, and is
#: never persisted (SI-71's spirit, ADR-0005 3).
SESSION_HEADER_NAME = "x-opencode-session"

#: The sentence carried to the UI beside the connection state. Turkish and
#: diacritic-free, like every other user-visible string here.
AUTH_HEADER_CAVEAT = (
    "Kimlik dogrulama basligi resmi belgede hala yayimlanmamistir. Station "
    "'Authorization: Bearer' gonderir ve bunun calistigi canli olcumle "
    "dogrulandi; belge yayimlamadigi icin saglayici onu bir sozlesmeye "
    "dayanmadan degistirebilir."
)

#: Every phase is bounded. Left implicit, httpx would allow an unbounded read.
#:
#: ``read`` was 30 s while this client only fetched a catalogue and the shape
#: of a completion was unknown. **Measured against the live provider (ADR-0012
#: and the round that opened the model lane): a reasoning model exceeds it.**
#: Two of roughly six live proposals ended in ``ReadTimeout`` at 30 s, and the
#: cost of that is not a slow screen - the endpoint is metered, so a lost
#: response is one the user may have paid for and will never see. The product
#: refuses to retry it automatically and says so, which is right, but the
#: refusal was firing on latency the provider considers ordinary.
#:
#: 120 s is this product's own existing answer to "how long may one thing
#: take" (``agent/budget.py``'s wall-clock ceiling), so the model call is
#: bounded by a number the codebase already had to defend rather than a new
#: one invented here. It is a **ceiling, not a target**: the successful calls
#: measured in that round returned in a few seconds.
#:
#: What is **not** measured: the provider's latency distribution. 120 s is
#: chosen to sit above the observed failures, not because anybody counted how
#: often 120 s is itself exceeded.
TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)

#: The free, unauthenticated catalog: one initial attempt plus one retry.
MAX_CATALOG_ATTEMPTS = 2

#: A metered call: **exactly one attempt**, ever. See the module docstring.
MAX_METERED_ATTEMPTS = 1

#: Fixed backoff between catalog attempts, in seconds.
RETRY_BACKOFF_SECONDS = 1.0

#: Ceiling on an honoured ``Retry-After``.
MAX_RETRY_AFTER_SECONDS = 5.0

#: Statuses worth a second attempt on the free endpoint only.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

#: The only response headers kept. Everything else - including any Set-Cookie
#: - is dropped before the result leaves this module.
ALLOWED_RESPONSE_HEADERS = ("content-type", "retry-after")

#: Read granularity for the streaming size check.
_CHUNK_BYTES = 64 * 1024

#: How much of an error body may be quoted back to the user. Bounded, swept
#: and redacted; it is data, never an assertion.
MAX_EXCERPT_CHARS = 240


@dataclass(frozen=True, slots=True)
class RawResponse:
    """One response, read and capped, before any protocol adapter sees it."""

    endpoint_id: EndpointId
    status_code: int
    content_type: str
    body: bytes
    byte_count: int
    sha256: str
    received_at: datetime
    #: A bounded, redacted, control-character-free quotation of the body, for
    #: the ``detail`` on a failure.
    #:
    #: **Computed at read time, not on demand.** An upstream error body can
    #: echo the credential back, and the only moment redaction is guaranteed
    #: to work is while the credential is still in the registry - which is
    #: for the duration of the request and not a line longer. A lazy
    #: ``excerpt()`` would have been evaluated by a caller after the
    #: ``finally`` had already dropped it, and would have quoted the key.
    excerpt: str = ""


def _excerpt(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    swept = "".join(" " if character < " " else character for character in text)
    return redact(swept.strip())[:MAX_EXCERPT_CHARS]


def new_session_id() -> str:
    """A fresh value for ``x-opencode-session``.

    Random, unlinkable and process-scoped. It identifies a run of this
    program to the provider and nothing else: it is not derived from the DID,
    the Windows user, the machine, the data directory or the session cookie,
    and it is never written to disk.
    """
    return secrets.token_hex(16)


def credential_headers(api_key: str) -> dict[str, str]:
    """The credential header. **The only place one is written.**

    Kept as a function rather than inlined so the "not verified" note above
    has exactly one thing to be attached to, and so a test can assert that no
    other module in the tree spells ``Authorization``.
    """
    return {AUTH_HEADER_NAME: f"{AUTH_SCHEME} {api_key}"}


def assert_allowed_url(url: str) -> None:
    """Re-check a URL against the allow-list.

    Redundant by design, exactly as it is on the Technocore client: the URL
    is built from constants, so this can only fail if the registry itself is
    wrong - the mistake a reviewer is least likely to catch by eye, and here
    the one that would send a credential somewhere else.
    """
    parts = urlsplit(url)

    if parts.scheme != OPENCODE_SCHEME:
        raise OpenCodeRequestError(f"refusing a non-HTTPS scheme: {parts.scheme!r}")
    if parts.username is not None or parts.password is not None:
        raise OpenCodeRequestError("refusing a URL that carries user-info")
    if parts.fragment:
        raise OpenCodeRequestError("refusing a URL that carries a fragment")
    if parts.query:
        raise OpenCodeRequestError("refusing a URL that carries a query string")

    host = parts.hostname
    if host != OPENCODE_HOST:
        raise OpenCodeRequestError(f"host is not on the allow-list: {host!r}")

    if parts.port is not None and parts.port != OPENCODE_PORT:
        raise OpenCodeRequestError(f"refusing a non-default port: {parts.port}")

    lowered = parts.path.lower()
    if "/../" in parts.path or parts.path.endswith("/..") or "%2e%2e" in lowered:
        raise OpenCodeRequestError("refusing a path that contains traversal")


class OpenCodeClient:
    """Talks to the four registered addresses, and nothing else.

    ``transport`` and ``sleep`` exist for tests, in exactly the sense the
    other three clients' do: the suite substitutes a mock transport so no
    automated test reaches the network (SI-174's rule). Neither is a security
    setting - a transport cannot widen the allow-list, because the URL is
    still built from the registry and re-checked before the request - and
    ``transport`` is narrowed to ``httpx.MockTransport`` so it cannot carry a
    weakened TLS posture either.

    There is no ``url``, ``method``, ``headers``, ``verify`` or ``retries``
    parameter, here or on any method.
    """

    def __init__(
        self,
        *,
        transport: httpx.MockTransport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise TypeError(
                "OpenCodeClient accepts only an httpx.MockTransport. The "
                "production path passes none, so httpx's verifying default "
                "stands and no transport-level TLS setting can be injected."
            )
        self._transport = transport
        self._sleep = sleep if sleep is not None else _default_sleep
        #: One value per client instance, so a restart is a new session and
        #: nothing links two runs together.
        self._session_id = new_session_id()

    @property
    def session_id(self) -> str:
        return self._session_id

    # --- the two capabilities ----------------------------------------------

    def fetch_catalog(self) -> RawResponse:
        """Read the model catalog. Free, unauthenticated, user-initiated.

        No credential is attached, because none is needed - which is the
        whole reason a successful fetch cannot be reported as a verified key
        (ADR-0005 4).
        """
        endpoint = get_endpoint(EndpointId.MODELS)
        return self._with_bounded_retry(endpoint, body=None, api_key=None)

    def post_completion(
        self, protocol: Protocol, body: bytes, *, api_key: str
    ) -> RawResponse:
        """Send one non-streaming request on one protocol family.

        Exactly one attempt. A timeout or a dropped connection here becomes
        :class:`~station_api.opencode.errors.OpenCodeLostResponseError`,
        because the honest statement is "we do not know whether that was
        charged", and a retry would turn a maybe-charge into a certain one.
        """
        endpoint = protocol_endpoint(protocol)
        # Registered for the whole request, including the excerpt taken from
        # the response, and dropped in a ``finally``. An upstream 401 body
        # that echoes the credential back is the case this exists for: the
        # excerpt is computed inside this window, so a reflected key is
        # already ``<redacted>`` by the time anything can display it.
        register_secret(api_key)
        try:
            return self._attempt(endpoint, body=body, api_key=api_key)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise OpenCodeLostResponseError(
                f"{endpoint.id.value}: yanit alinamadi "
                f"({type(exc).__name__}). Istek surecten cikmis olabilir; "
                "otomatik olarak tekrarlanmaz."
            ) from exc
        finally:
            forget_secret(api_key)

    # --- internals ---------------------------------------------------------

    def _with_bounded_retry(
        self,
        endpoint: OpenCodeEndpoint,
        *,
        body: bytes | None,
        api_key: str | None,
    ) -> RawResponse:
        """The free endpoint's policy. Never used for a metered one."""
        if endpoint.metered:  # pragma: no cover - guarded by construction
            raise AssertionError("a metered endpoint is never retried")

        last_error: Exception | None = None
        for attempt in range(1, MAX_CATALOG_ATTEMPTS + 1):
            try:
                return self._attempt(endpoint, body=body, api_key=api_key)
            except _RetryableStatusError as exc:
                last_error = exc.as_request_error()
                if attempt == MAX_CATALOG_ATTEMPTS:
                    break
                self._sleep(exc.wait_seconds)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = OpenCodeRequestError(
                    f"{endpoint.id.value}: transport failure ({type(exc).__name__})"
                )
                if attempt == MAX_CATALOG_ATTEMPTS:
                    break
                self._sleep(RETRY_BACKOFF_SECONDS)

        assert last_error is not None
        raise last_error

    def _client(self, *, api_key: str | None) -> httpx.Client:
        """A client with the security posture fixed in one place.

        ``verify`` is absent on purpose: httpx verifies by default, and not
        naming the parameter means there is no line to flip to ``False``.
        """
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            # Identity encoding, so there is no decompression step at all on
            # a lane that carries a credential. The bodies here are small.
            "Accept-Encoding": "identity",
            SESSION_HEADER_NAME: self._session_id,
        }
        if api_key is not None:
            headers.update(credential_headers(api_key))

        return httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=False,
            transport=self._transport,
            headers=headers,
            # No cookie jar survives a request, so nothing can be set on one
            # and replayed on the next.
            cookies=None,
        )

    def _attempt(
        self,
        endpoint: OpenCodeEndpoint,
        *,
        body: bytes | None,
        api_key: str | None,
    ) -> RawResponse:
        url = endpoint.url
        assert_allowed_url(url)

        request_headers = (
            {"Content-Type": "application/json"} if body is not None else None
        )

        with self._client(api_key=api_key) as client, client.stream(
            endpoint.method, url, content=body, headers=request_headers
        ) as response:
            if response.is_redirect:
                # The Location value is deliberately not read or logged: it is
                # attacker-influenced input we have decided not to act on, and
                # acting on it would forward a credential.
                raise UnexpectedRedirectError(
                    f"{endpoint.id.value}: origin answered "
                    f"{response.status_code} with a redirect, which is never "
                    "followed"
                )

            if not endpoint.metered and response.status_code in RETRYABLE_STATUSES:
                raise _RetryableStatusError(endpoint, response)

            payload = self._read_capped(endpoint, response)
            content_type = _header(response, "content-type")
            status_code = response.status_code

        return RawResponse(
            endpoint_id=endpoint.id,
            status_code=status_code,
            content_type=content_type,
            body=payload,
            byte_count=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            received_at=datetime.now(UTC),
            excerpt=_excerpt(payload),
        )

    def _read_capped(
        self, endpoint: OpenCodeEndpoint, response: httpx.Response
    ) -> bytes:
        """Stream the body, refusing to buffer more than the cap allows.

        ``iter_bytes`` yields decompressed data, so the limit applies to what
        we would actually hold in memory rather than to the wire size. The
        pattern is ``ReadOnlyTechnocoreClient._read_capped``'s.
        """
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes(_CHUNK_BYTES):
            total += len(chunk)
            if total > endpoint.max_bytes:
                raise ResponseTooLargeError(
                    f"{endpoint.id.value}: body exceeds the "
                    f"{endpoint.max_bytes}-byte cap"
                )
            chunks.append(chunk)
        return b"".join(chunks)


class _RetryableStatusError(Exception):
    """Internal: a status worth one more attempt on a free endpoint."""

    def __init__(self, endpoint: OpenCodeEndpoint, response: httpx.Response) -> None:
        super().__init__(f"{endpoint.id.value}: status {response.status_code}")
        self.endpoint = endpoint
        self.status_code = response.status_code
        self.wait_seconds = _retry_delay(response)

    def as_request_error(self) -> OpenCodeRequestError:
        return OpenCodeRequestError(
            f"{self.endpoint.id.value}: gave up after status {self.status_code}"
        )


def _retry_delay(response: httpx.Response) -> float:
    """Honour ``Retry-After``, clamped.

    Only the delay-seconds form is read. The HTTP-date form is ignored rather
    than parsed: it would need a clock comparison against a header we do not
    trust, to buy nothing the fixed backoff does not already provide.
    """
    raw = response.headers.get("retry-after", "").strip()
    if raw.isdigit():
        return min(float(raw), MAX_RETRY_AFTER_SECONDS)
    return RETRY_BACKOFF_SECONDS


def _header(response: httpx.Response, name: str) -> str:
    if name not in ALLOWED_RESPONSE_HEADERS:  # pragma: no cover - constant callers
        raise AssertionError(f"{name} is not an allow-listed response header")
    value: str = response.headers.get(name, "")
    return value


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


__all__ = [
    "ALLOWED_RESPONSE_HEADERS",
    "AUTH_HEADER_CAVEAT",
    "AUTH_HEADER_NAME",
    "AUTH_SCHEME",
    "MAX_CATALOG_ATTEMPTS",
    "MAX_EXCERPT_CHARS",
    "MAX_METERED_ATTEMPTS",
    "MAX_RETRY_AFTER_SECONDS",
    "RETRYABLE_STATUSES",
    "SESSION_HEADER_NAME",
    "TIMEOUT",
    "USER_AGENT",
    "OpenCodeClient",
    "RawResponse",
    "assert_allowed_url",
    "credential_headers",
    "new_session_id",
]
