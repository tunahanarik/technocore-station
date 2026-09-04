"""The work-scan client: the fifth outbound surface, and the first that paginates.

Four clients already exist and each got its own module for the same reason
this one does (ADR-0003 1, ADR-0005 6, ADR-0007 3): a different capability, a
different registry and a different failure policy. What is new here is a
**query string**. The three Technocore clients address fixed paths with no
parameters at all; this one carries ``since``, ``limit`` and ``format``,
which is precisely why the parameters are built by
:mod:`station_api.workscan.targets` from typed values and never accepted as
text.

What this API refuses to accept
-------------------------------
:meth:`RoomScanClient.fetch_room_index` takes an integer.
:meth:`RoomScanClient.fetch_room_messages` takes a
:class:`~station_api.workscan.targets.RoomScanTarget` - a room name that has
already been through the write path's policy - plus two integers. Neither
takes a URL, a path, a method, a header or any TLS setting, so a request body
or a database row has no route to an outbound address.

The signatures are deliberately **not** ``fetch(self, source)``. The read
client's signature is pinned by a test and stays exactly as it is; borrowing
it here would have invited a future caller to treat the two as
interchangeable, and they are not - one reads six fixed documents and this one
reads anonymous, world-writable room content.

Why the status code is not the success signal
---------------------------------------------
``format=json`` is **advisory** on this service. Any other value, a typo
included, is ignored and the reply stays ``text/plain`` **with a 200**. A
client that checked ``response.status_code == 200`` and then called
``json.loads`` would report a parse error for what is really a contract
mismatch, and a client that checked nothing would hand plain text to a
parser. So the Content-Type is checked, and a non-JSON body raises
:class:`~station_api.workscan.errors.WrongMediaTypeError` by name
(ADR-0007 3).

What does not happen here
-------------------------
No ``wait``. No timer, no thread, no background task, no scheduled refresh
and no automatic follow-up request. Every method on this class runs exactly
one HTTP exchange per attempt, when a caller on a request thread calls it
(ADR-0007 4). ``NEVER_SENT_PARAMS`` names the parameters that are refused,
and a test asserts they appear in no URL this client produces.

Transport rules, unchanged from the reviewed clients
----------------------------------------------------
* TLS verification is always on. ``verify`` is never passed and never
  exposed; the only transport the test seam accepts is an
  ``httpx.MockTransport``, which negotiates no TLS at all.
* Redirects are never followed. A 3xx is an error.
* Timeouts are explicit on all four phases.
* The body cap is enforced on **decompressed** bytes as they stream in.
* No cookies, no authorization, no DID, no CSRF value, no session cookie, no
  file path and no user data of any kind is attached. The request carries a
  fixed User-Agent and nothing else identifying. Reading a public room needs
  no credential and this client has none to leak.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from station_api.technocore.sources import (
    TECHNOCORE_HOST,
    TECHNOCORE_PORT,
    TECHNOCORE_SCHEME,
)
from station_api.technocore.write_targets import DENIED_ROOMS
from station_api.workscan.errors import (
    ResponseTooLargeError,
    ScanFetchError,
    UnexpectedRedirectError,
    WrongMediaTypeError,
)
from station_api.workscan.targets import (
    DEFAULT_LIMIT,
    NEVER_SENT_PARAMS,
    ROOM_MESSAGES_TEMPLATE,
    RoomScanTarget,
    ScanTarget,
    ScanTargetId,
    get_target,
    index_query,
    index_url,
    messages_query,
)

#: Fixed, and deliberately free of anything identifying. The same string the
#: other clients send: this product does not present itself as two things.
USER_AGENT = "TechnocoreStation/0.1 (+https://github.com/tunahanarik/technocore-station)"

#: Every phase is bounded. Left implicit, httpx would allow an unbounded read.
TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

#: One initial attempt plus one retry. Smaller than the document client's
#: three: a scan reads several rooms in one user action, and a room that
#: cannot answer quickly should drop out of *this* scan rather than make the
#: person wait through three attempts per room. A room that contributed
#: nothing is reported as such; it is never reported as empty.
MAX_ATTEMPTS = 2

#: Fixed backoff per retry, in seconds.
RETRY_BACKOFF_SECONDS = 1.0

#: Ceiling on an honoured ``Retry-After``. The header is attacker-influenced
#: in the general case and mistaken in the common case.
MAX_RETRY_AFTER_SECONDS = 5.0

#: Statuses worth a second attempt: transient by definition. 429 is in the
#: list because this service publishes a read bucket and states the delay in
#: the body; the clamp above bounds what we will honour from it.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

#: The only response headers kept. Everything else - including any Set-Cookie
#: - is dropped before the result leaves this module.
ALLOWED_RESPONSE_HEADERS = ("content-type", "retry-after")

#: Read granularity for the streaming size check.
_CHUNK_BYTES = 64 * 1024

#: Everything before the room name in the message lane's path. Derived from
#: the registry's own template, so the two cannot drift apart.
_ROOM_PATH_PREFIX = ROOM_MESSAGES_TEMPLATE.split("{", 1)[0]


@dataclass(frozen=True, slots=True)
class ScanFetchResult:
    """One successful read of one scan target.

    Carries the exact bytes and their hash, not a parsed document: parsing is
    :mod:`station_api.workscan.snapshot`'s job, and keeping the two apart is
    what lets a snapshot record the digest of what it was actually built from.
    """

    target_id: ScanTargetId
    url: str
    status_code: int
    content_type: str
    #: The exact bytes received, after transfer decoding.
    body: bytes
    sha256: str
    byte_count: int
    #: When this process finished reading the body. The only timestamp this
    #: build owns; the server's own clock is never treated as ours.
    read_at: datetime
    #: The query that actually went on the wire, for the record.
    query: Mapping[str, str]

    @property
    def short_hash(self) -> str:
        """First 12 hex characters, for display."""
        return self.sha256[:12]


def assert_allowed_url(url: str) -> None:
    """Re-check a URL against the allow-list.

    Redundant by design, exactly as it is in the other clients: the URL is
    built from constants, so this can only fail if the registry itself is
    wrong - the mistake a reviewer is least likely to catch by eye.

    A **query string is refused here** even though this client sends one. The
    query is passed to httpx separately, as typed parameters, so a query that
    has already been baked into the address means something built a URL by
    string concatenation - which is the step this whole design removes.
    """
    parts = urlsplit(url)

    if parts.scheme != TECHNOCORE_SCHEME:
        raise ScanFetchError(f"refusing a non-HTTPS scheme: {parts.scheme!r}")
    if parts.username is not None or parts.password is not None:
        raise ScanFetchError("refusing a URL that carries user-info")
    if parts.fragment:
        raise ScanFetchError("refusing a URL that carries a fragment")
    if parts.query:
        raise ScanFetchError("refusing a URL that already carries a query string")

    # `hostname` lowercases and strips brackets but keeps a trailing dot,
    # which resolves the same but is a different string.
    host = parts.hostname
    if host != TECHNOCORE_HOST:
        raise ScanFetchError(f"host is not on the allow-list: {host!r}")

    if parts.port is not None and parts.port != TECHNOCORE_PORT:
        raise ScanFetchError(f"refusing a non-default port: {parts.port}")

    lowered = parts.path.lower()
    if "/../" in parts.path or parts.path.endswith("/..") or "%2e%2e" in lowered:
        raise ScanFetchError("refusing a path that contains traversal")

    _assert_room_path_allowed(parts.path)


def _assert_room_path_allowed(path: str) -> None:
    """Apply the room policy to the address, not only to the target object.

    Scheme, host, port and path shape were all this check knew, and a request
    to ``/r/lobby`` satisfies every one of them: it is exactly the address the
    registry produces, for exactly the room INV-05 says this product never
    names. The room policy lived one layer up, on
    :func:`~station_api.workscan.targets.resolve_room_target`, so the layer
    whose own docstring calls itself the catch for "the mistake a reviewer is
    least likely to catch by eye" had a hole in the shape of the single room
    the charter is most specific about.

    Checked on the URL because that is the last thing before the wire. It is
    the third place the same rule is applied - the resolver, the target's
    ``__post_init__``, and here - and that is the intent (ADR-0002 4.1,
    ADR-0007 11, INV-05).
    """
    if not path.startswith(_ROOM_PATH_PREFIX):
        return
    room = path[len(_ROOM_PATH_PREFIX) :]
    if room.casefold() in DENIED_ROOMS:
        raise ScanFetchError(
            "refusing a room the policy denies, on the outbound path"
        )


def assert_allowed_query(query: Mapping[str, str]) -> None:
    """Refuse a parameter this package has decided not to send.

    Named separately from the URL check because it guards a different
    mistake. ``wait`` is a *valid* parameter on this service; sending it is
    not a security failure, it is a policy failure - it is long-polling, and
    ADR-0007 4 removed polling from this package. A rule that lives only in a
    docstring is a rule that comes back in the next revision.

    The comparison is case-folded. It was not, and ``{"WAIT": "30"}`` went
    through a check that is named as the structural half of the polling ban -
    a ban that a service reading its parameters case-insensitively would have
    honoured the upper-case spelling of.
    """
    offenders = sorted(
        name for name in query if name.casefold() in NEVER_SENT_PARAMS
    )
    if offenders:
        raise ScanFetchError(
            "refusing a query parameter this package does not send: "
            f"{', '.join(offenders)}"
        )


class RoomScanClient:
    """Reads the public room surface, and nothing else.

    ``transport`` and ``sleep`` exist for tests, in the same sense they do on
    the other clients: neither is a security setting. A transport cannot widen
    the allow-list, because the URL is still built from the registry and
    re-checked before the request, and ``transport`` is narrowed to
    ``httpx.MockTransport`` so it cannot carry a weakened TLS posture either.
    """

    def __init__(
        self,
        *,
        transport: httpx.MockTransport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise TypeError(
                "RoomScanClient accepts only an httpx.MockTransport. The "
                "production path passes none, so httpx's verifying default "
                "stands and no transport-level TLS setting can be injected."
            )
        self._transport = transport
        self._sleep = sleep if sleep is not None else _default_sleep

    def fetch_room_index(self, *, limit: int = DEFAULT_LIMIT) -> ScanFetchResult:
        """Read the room overview once, on a caller's explicit request.

        Not ``fetch(self, source)``: this client's surface is its own, and the
        read client's signature is pinned where it lives.
        """
        target = get_target(ScanTargetId.ROOM_INDEX)
        return self._run(target, index_url(), index_query(limit=limit))

    def fetch_room_messages(
        self,
        target: RoomScanTarget,
        *,
        since: int | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> ScanFetchResult:
        """Read one already-resolved room's newest messages, once.

        ``target`` is a resolved room rather than a string, so the room policy
        cannot be skipped by calling this directly: there is no way to build a
        :class:`RoomScanTarget` except through
        :func:`~station_api.workscan.targets.resolve_room_target`'s validation
        or by writing one out in a test, and the URL is derived from the
        target's own property.
        """
        registered = get_target(ScanTargetId.ROOM_MESSAGES)
        return self._run(
            registered, target.url, messages_query(since=since, limit=limit)
        )

    # --- internals ---------------------------------------------------------

    def _run(
        self, target: ScanTarget, url: str, query: dict[str, str]
    ) -> ScanFetchResult:
        assert_allowed_url(url)
        assert_allowed_query(query)

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._attempt(target, url, query)
            except _RetryableStatusError as exc:
                last_error = exc.as_fetch_error()
                if attempt == MAX_ATTEMPTS:
                    break
                self._sleep(exc.wait_seconds)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = ScanFetchError(
                    f"{target.id.value}: transport failure ({type(exc).__name__})"
                )
                if attempt == MAX_ATTEMPTS:
                    break
                self._sleep(RETRY_BACKOFF_SECONDS)

        assert last_error is not None
        raise last_error

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
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            cookies=None,
        )

    def _attempt(
        self, target: ScanTarget, url: str, query: dict[str, str]
    ) -> ScanFetchResult:
        with self._client() as client, client.stream("GET", url, params=query) as reply:
            if reply.is_redirect:
                # The Location value is deliberately not read or logged: it is
                # attacker-influenced input we have decided not to act on.
                raise UnexpectedRedirectError(
                    f"{target.id.value}: origin answered {reply.status_code} "
                    "with a redirect, which is never followed"
                )

            if reply.status_code in RETRYABLE_STATUSES:
                raise _RetryableStatusError(target, reply)

            if reply.status_code != httpx.codes.OK:
                raise ScanFetchError(
                    f"{target.id.value}: unexpected status {reply.status_code}"
                )

            content_type = _header(reply, "content-type")
            _assert_json(target, content_type)

            body = self._read_capped(target, reply)
            status_code = reply.status_code

        return ScanFetchResult(
            target_id=target.id,
            url=url,
            status_code=status_code,
            content_type=content_type,
            body=body,
            sha256=hashlib.sha256(body).hexdigest(),
            byte_count=len(body),
            read_at=datetime.now(UTC),
            query=dict(query),
        )

    def _read_capped(self, target: ScanTarget, response: httpx.Response) -> bytes:
        """Stream the body, refusing to buffer more than the cap allows.

        ``iter_bytes`` yields decompressed data, so the limit applies to what
        we would actually hold in memory rather than to the wire size.
        """
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes(_CHUNK_BYTES):
            total += len(chunk)
            if total > target.max_bytes:
                raise ResponseTooLargeError(
                    f"{target.id.value}: body exceeds the {target.max_bytes}-byte cap"
                )
            chunks.append(chunk)
        return b"".join(chunks)


def _assert_json(target: ScanTarget, content_type: str) -> None:
    """The contract check the status code cannot make.

    ``format=json`` is advisory: an ignored value leaves a 200 carrying
    ``text/plain``. Comparing the media type before the parameters - a charset
    is normal and irrelevant - is what turns that into a named refusal instead
    of a confusing parse error two layers up.
    """
    media = content_type.split(";", 1)[0].strip().lower()
    if media != target.media:
        raise WrongMediaTypeError(
            f"{target.id.value}: yanit '{target.media}' degil '{media or 'bos'}' "
            "olarak geldi. 'format=json' bu serviste tavsiye niteligindedir ve "
            "yok sayilabilir; durum kodu 200 olsa da govde JSON degildir."
        )


class _RetryableStatusError(Exception):
    """Internal: a status worth one more attempt."""

    def __init__(self, target: ScanTarget, response: httpx.Response) -> None:
        super().__init__(f"{target.id.value}: status {response.status_code}")
        self.target = target
        self.status_code = response.status_code
        self.wait_seconds = _retry_delay(response)

    def as_fetch_error(self) -> ScanFetchError:
        return ScanFetchError(
            f"{self.target.id.value}: gave up after status {self.status_code}"
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
    "RoomScanClient",
    "ScanFetchResult",
    "assert_allowed_query",
    "assert_allowed_url",
]
