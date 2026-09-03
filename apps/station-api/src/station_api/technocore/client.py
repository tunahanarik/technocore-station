"""The read-only Technocore client.

This is the only code in Station that makes an outbound request, and it is
written to make the dangerous things unrepresentable rather than merely
unlikely.

What the API refuses to accept
------------------------------
``fetch`` takes an ``OfficialSource`` from the closed registry. It does not
take a URL, a path, a method, headers, or any TLS setting. There is no
parameter that could carry user input to the network, so the usual questions
- "can a request body steer this?", "can a database row?" - have the same
answer by construction: no.

Why that matters more here than usual
-------------------------------------
Technocore performs **writes over GET**. ``/r/{room}/say-signed/...`` appends
to a public room; ``/kv/{ns}/{key}/set/...`` overwrites a note. A client that
accepted a caller-supplied path would therefore be one bug away from writing
to a live room with a single GET. "We only send GET" is not a safety property
on this service, so the registry is the safety property instead.

Transport rules
---------------
* TLS verification is always on. ``verify`` is never passed and never exposed;
  the only transport the test seam accepts is an ``httpx.MockTransport``, which
  negotiates no TLS at all, so there is no transport to hand in with
  verification switched off and no insecure-context escape hatch.
* Redirects are never followed. A 3xx is an error, because following one is
  precisely how a request leaves the allow-listed origin.
* Timeouts are explicit on all four phases; no phase inherits "no limit".
* The body cap is enforced on **decompressed** bytes as they stream in, so a
  small gzip that expands to gigabytes is refused rather than buffered.
* Retries are bounded and only for transport faults, 5xx and 429. A 429's
  ``Retry-After`` is honoured but clamped, so a hostile or mistaken header
  cannot park the request for hours.
* No cookies, no authorization, no DID, no fingerprint, no CSRF value and no
  user data of any kind is attached. The request carries a fixed User-Agent
  and nothing else identifying.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from station_api.technocore.errors import (
    ResponseTooLargeError,
    SourceFetchError,
    UnexpectedRedirectError,
)
from station_api.technocore.sources import (
    TECHNOCORE_HOST,
    TECHNOCORE_PORT,
    TECHNOCORE_SCHEME,
    OfficialSource,
    SourceId,
)

#: Fixed, and deliberately free of anything identifying. No version of the
#: user's OS, no machine name, no identity.
USER_AGENT = "TechnocoreStation/0.1 (+https://github.com/tunahanarik/technocore-station)"

#: Every phase is bounded. Left implicit, httpx would allow an unbounded read.
TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

#: One initial attempt plus two retries. Small on purpose: this runs when a
#: user presses a button and waits, and a read-only check that cannot answer
#: quickly should say "unavailable" rather than hang.
MAX_ATTEMPTS = 3

#: Fixed backoff per retry, in seconds.
RETRY_BACKOFF_SECONDS = 1.0

#: Ceiling on an honoured ``Retry-After``. The header is attacker-influenced
#: in the general case and mistaken in the common case.
MAX_RETRY_AFTER_SECONDS = 5.0

#: Statuses worth a second attempt: transient by definition.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

#: The only response headers kept. Everything else - including any Set-Cookie
#: - is dropped before the result leaves this module, so nothing irrelevant or
#: sensitive can reach the database or an API response.
ALLOWED_RESPONSE_HEADERS = ("content-type", "etag", "last-modified")

#: Read granularity for the streaming size check.
_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class FetchResult:
    """One successful read of one official document."""

    source_id: SourceId
    url: str
    status_code: int
    content_type: str
    etag: str
    last_modified: str
    #: The exact bytes received, after transfer decoding. The hash below is
    #: taken over precisely these bytes.
    body: bytes
    sha256: str
    byte_count: int
    fetched_at: datetime

    @property
    def short_hash(self) -> str:
        """First 12 hex characters, for display."""
        return self.sha256[:12]


def assert_allowed_url(url: str) -> None:
    """Re-check a URL against the allow-list.

    Redundant by design. The URL is built from constants, so this can only
    fail if the registry itself is wrong - which is exactly the mistake a
    reviewer is least likely to catch by eye, and the one with the worst
    consequences.
    """
    parts = urlsplit(url)

    if parts.scheme != TECHNOCORE_SCHEME:
        raise SourceFetchError(f"refusing a non-HTTPS scheme: {parts.scheme!r}")
    if parts.username is not None or parts.password is not None:
        raise SourceFetchError("refusing a URL that carries user-info")
    if parts.fragment:
        raise SourceFetchError("refusing a URL that carries a fragment")

    # `hostname` lowercases and strips brackets but keeps a trailing dot,
    # which resolves the same but is a different string - and is a classic way
    # past a naive allow-list.
    host = parts.hostname
    if host != TECHNOCORE_HOST:
        raise SourceFetchError(f"host is not on the allow-list: {host!r}")

    # An explicit port is allowed only if it is the default one.
    if parts.port is not None and parts.port != TECHNOCORE_PORT:
        raise SourceFetchError(f"refusing a non-default port: {parts.port}")

    lowered = parts.path.lower()
    if "/../" in parts.path or parts.path.endswith("/..") or "%2e%2e" in lowered:
        raise SourceFetchError("refusing a path that contains traversal")


class ReadOnlyTechnocoreClient:
    """Fetches official documents, and nothing else.

    ``transport`` and ``sleep`` exist for tests: the suite substitutes a mock
    transport so no automated test ever reaches the network. Neither is a
    security setting - a transport cannot widen the allow-list, because the
    URL is still built from the registry and re-checked before the request -
    and ``transport`` is narrowed to ``httpx.MockTransport`` so it cannot
    carry a weakened TLS posture either.
    """

    def __init__(
        self,
        *,
        transport: httpx.MockTransport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise TypeError(
                "ReadOnlyTechnocoreClient accepts only an httpx.MockTransport. "
                "The production path passes none, so httpx's verifying default "
                "stands and no transport-level TLS setting can be injected."
            )
        self._transport = transport
        self._sleep = sleep if sleep is not None else _default_sleep

    def fetch(self, source: OfficialSource) -> FetchResult:
        """Read one registered document, or raise.

        Never returns a partial or unverified result: any failure is an
        exception, which the service turns into an ``unavailable`` verdict.
        """
        url = source.url
        assert_allowed_url(url)

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._attempt(source, url)
            except _RetryableStatusError as exc:
                last_error = exc.as_fetch_error()
                if attempt == MAX_ATTEMPTS:
                    break
                self._sleep(exc.wait_seconds)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = SourceFetchError(
                    f"{source.id.value}: transport failure ({type(exc).__name__})"
                )
                if attempt == MAX_ATTEMPTS:
                    break
                self._sleep(RETRY_BACKOFF_SECONDS)

        assert last_error is not None
        raise last_error

    # --- internals ---------------------------------------------------------

    def _client(self) -> httpx.Client:
        """A client with the security posture fixed in one place.

        ``verify`` is absent on purpose: httpx verifies by default, and not
        naming the parameter means there is no line to flip to ``False``.
        """
        return httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=False,
            transport=self._transport,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                # Identity encoding would remove the decompression-bomb
                # concern entirely, but these documents are large and public;
                # the streaming cap below handles it without wasting bandwidth.
                "Accept-Encoding": "gzip, deflate",
            },
            # No cookie jar survives a fetch, so nothing can be set on one
            # request and replayed on the next.
            cookies=None,
        )

    def _attempt(self, source: OfficialSource, url: str) -> FetchResult:
        with self._client() as client, client.stream("GET", url) as response:
            if response.is_redirect:
                # The Location value is deliberately not read or logged: it is
                # attacker-influenced input we have decided not to act on.
                raise UnexpectedRedirectError(
                    f"{source.id.value}: origin answered {response.status_code} "
                    "with a redirect, which is never followed"
                )

            if response.status_code in RETRYABLE_STATUSES:
                raise _RetryableStatusError(source, response)

            if response.status_code != httpx.codes.OK:
                raise SourceFetchError(
                    f"{source.id.value}: unexpected status {response.status_code}"
                )

            body = self._read_capped(source, response)
            content_type = _header(response, "content-type")
            etag = _header(response, "etag")
            last_modified = _header(response, "last-modified")
            status_code = response.status_code

        return FetchResult(
            source_id=source.id,
            url=url,
            status_code=status_code,
            content_type=content_type,
            etag=etag,
            last_modified=last_modified,
            body=body,
            sha256=hashlib.sha256(body).hexdigest(),
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
        )

    def _read_capped(self, source: OfficialSource, response: httpx.Response) -> bytes:
        """Stream the body, refusing to buffer more than the cap allows.

        ``iter_bytes`` yields decompressed data, so the limit applies to what
        we would actually hold in memory rather than to the wire size.
        """
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes(_CHUNK_BYTES):
            total += len(chunk)
            if total > source.max_bytes:
                raise ResponseTooLargeError(
                    f"{source.id.value}: body exceeds the {source.max_bytes}-byte cap"
                )
            chunks.append(chunk)
        return b"".join(chunks)


class _RetryableStatusError(Exception):
    """Internal: a status worth one more attempt."""

    def __init__(self, source: OfficialSource, response: httpx.Response) -> None:
        super().__init__(f"{source.id.value}: status {response.status_code}")
        self.source = source
        self.status_code = response.status_code
        self.wait_seconds = _retry_delay(response)

    def as_fetch_error(self) -> SourceFetchError:
        return SourceFetchError(
            f"{self.source.id.value}: gave up after status {self.status_code}"
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
    "MAX_ATTEMPTS",
    "MAX_RETRY_AFTER_SECONDS",
    "RETRYABLE_STATUSES",
    "TIMEOUT",
    "USER_AGENT",
    "FetchResult",
    "ReadOnlyTechnocoreClient",
    "assert_allowed_url",
]
