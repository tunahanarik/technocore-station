"""The signed-write client. POST only, one attempt, three outcomes.

This is the second - and last - module in Station that makes an outbound
request. It is separate from the read-only client because the two have
opposite failure policies, and collapsing them would inherit the wrong one.

Three outcomes, not two
-----------------------
The pinned manual states the problem in one line: *"A fetch failure is
therefore not evidence that a write failed."* So the result of a write is
three-valued (ADR-0002 3):

``accepted``          2xx. The server took it.
``refused``           400, 403, 413, 422. Responses that prove nothing was
                      written: a rejected body, a forbidden room, an
                      oversized payload, a duplicate filter.
``outcome_unknown``   everything else - timeout, connection failure,
                      malformed response, a redirect, 429, any 5xx. The
                      server may have written. Presenting this as either
                      "sent" or "failed" would be a claim the evidence does
                      not support, so it is presented as itself.

No retry, ever
--------------
The read-only client retries transport faults, 5xx and 429 up to three
times, because re-reading a document is free. That policy is deliberately
**not** inherited here: a retried write is how one approved message becomes
two published ones. There is no attempt loop in this module, no backoff, and
no ``Retry-After`` handling. Recovery from ``outcome_unknown`` is a
read-side reconciliation and a fresh human decision, with a fresh nonce.

Transport rules, same as the read client
----------------------------------------
* TLS verification is always on. ``verify`` is never named in this module, so
  there is no line to flip to ``False``; and the only transport this client
  accepts through its test seam is an ``httpx.MockTransport``, which speaks no
  TLS at all. A real transport carrying ``verify=False`` is therefore not
  merely absent - it cannot be handed in.
* Redirects are never followed. A 3xx is ``outcome_unknown``, because the
  request may have been acted on before the hop and following one leaves the
  allow-listed origin.
* Timeouts are explicit on all four phases.
* The response body is **streamed** under a cap, so what is buffered is
  bounded by ``MAX_RESPONSE_BYTES`` rather than by whatever the server chose
  to send. ``response.content`` would have buffered the whole body and sliced
  it afterwards, which is not a cap. Only a bounded, swept excerpt survives.
* A body that arrives with a ``Content-Encoding`` we did not ask for is not
  decompressed at all. ``Accept-Encoding: identity`` is a request and a server
  may ignore it; refusing the encoding on the way back is what makes the
  decompression-bomb question actually absent here rather than merely bounded.
* Nothing identifying is attached: no cookie, no authorization header, no
  fingerprint. The DID and signature travel in the body because the protocol
  puts them there, and nowhere else.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import httpx

from station_api.technocore.client import USER_AGENT, assert_allowed_url
from station_api.technocore.projection import safe_display
from station_api.technocore.write_targets import WRITE_METHOD, WriteTarget

#: Every phase bounded, as on the read path. Slightly more generous on read
#: because a write does more work server-side before it answers; still short
#: enough that a person waiting on a button gets an answer.
WRITE_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)

#: Statuses that prove the server did not store anything (ADR-0002 3).
REFUSED_STATUSES = frozenset({400, 403, 413, 422})

#: Cap on the response body we will read back. A write answers with a small
#: JSON receipt; anything larger is not something we need. Enforced while
#: streaming, on decompressed bytes.
MAX_RESPONSE_BYTES = 64 * 1024

#: Read granularity for the streaming cap, mirroring the read client. The
#: transient overshoot is bounded by this value and trimmed immediately.
_CHUNK_BYTES = 8 * 1024

#: Longest excerpt kept from that body.
MAX_EXCERPT_CHARS = 1024

#: Content codings that mean "no decoding happens". Anything else was not
#: asked for and is not unpacked.
IDENTITY_ENCODINGS = frozenset({"", "identity"})

#: Stands in for a body we deliberately did not read. Our own bytes, so it
#: carries nothing the server chose.
UNREAD_BODY_NOTE = (
    b"[govde okunmadi: sunucu istenmeyen bir Content-Encoding ile yanitladi]"
)


class WriteOutcome(StrEnum):
    """The three-valued result of one attempted write."""

    ACCEPTED = "accepted"
    REFUSED = "refused"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True, slots=True)
class WriteResult:
    """What is known after one attempt, and nothing more."""

    outcome: WriteOutcome
    #: 0 when no response line was ever received.
    http_status: int
    #: One sentence in Turkish, safe to show. Never a raw response body.
    detail: str
    #: A bounded, swept excerpt of the response, for the record.
    response_excerpt: str
    attempted_at: datetime
    url: str

    @property
    def is_accepted(self) -> bool:
        return self.outcome is WriteOutcome.ACCEPTED


class SignedWriteClient:
    """POSTs one approved body to one resolved room. Once.

    ``transport`` exists so tests can substitute ``httpx.MockTransport``, and
    that is the *only* thing it accepts. Documenting it as "not a security
    setting" was not enough: an ``httpx.HTTPTransport`` built with
    ``verify=False`` has the shape of a test seam and the effect of a disabled
    TLS check, and nothing refused it. Narrowing the accepted type makes the
    difference structural - a mock transport terminates the request in the
    process and negotiates no TLS at all, so there is no verification to
    disable - without taking the seam away from the tests that need it.

    There is still no ``url``, ``method``, ``headers`` or ``verify``
    parameter, so a caller cannot steer the request anywhere.
    """

    def __init__(self, *, transport: httpx.MockTransport | None = None) -> None:
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise TypeError(
                "SignedWriteClient accepts only an httpx.MockTransport. The "
                "production path passes none, so httpx's verifying default "
                "stands and no transport-level TLS setting can be injected."
            )
        self._transport = transport

    def send(self, target: WriteTarget, body: Mapping[str, str]) -> WriteResult:
        """Send one message. Never raises for a network condition.

        Every failure becomes a result, because an exception escaping here
        would be caught somewhere as "it did not work" - which is exactly the
        claim this module exists to refuse to make.
        """
        url = target.url
        assert_allowed_url(url)
        attempted_at = datetime.now(UTC)

        try:
            with (
                self._client() as client,
                client.stream(WRITE_METHOD, url, json=dict(body)) as response,
            ):
                status_code = response.status_code
                excerpt = _excerpt(_read_capped(response))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return WriteResult(
                outcome=WriteOutcome.OUTCOME_UNKNOWN,
                http_status=0,
                detail=(
                    "Yanit alinamadi "
                    f"({type(exc).__name__}). Sunucu mesaji yazmis olabilir; "
                    "sonuc bilinmiyor."
                ),
                response_excerpt="",
                attempted_at=attempted_at,
                url=url,
            )

        return _classify(
            status_code=status_code,
            excerpt=excerpt,
            attempted_at=attempted_at,
            url=url,
        )

    def _client(self) -> httpx.Client:
        """A client with the security posture fixed in one place.

        ``verify`` is absent on purpose: httpx verifies by default, and not
        naming the parameter means there is no line to flip to ``False``.
        """
        return httpx.Client(
            timeout=WRITE_TIMEOUT,
            follow_redirects=False,
            transport=self._transport,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                # Identity encoding: a write receipt is small, so there is no
                # bandwidth to save by accepting compression. This is only a
                # *request*, though, so ``_read_capped`` enforces the same rule
                # on the answer rather than trusting the server to honour it.
                "Accept-Encoding": "identity",
            },
            cookies=None,
        )


def _classify(
    *, status_code: int, excerpt: str, attempted_at: datetime, url: str
) -> WriteResult:
    """Map a received status onto the three-valued outcome."""
    if 200 <= status_code < 300:
        return WriteResult(
            outcome=WriteOutcome.ACCEPTED,
            http_status=status_code,
            detail="Sunucu mesaji kabul etti.",
            response_excerpt=excerpt,
            attempted_at=attempted_at,
            url=url,
        )

    if status_code in REFUSED_STATUSES:
        return WriteResult(
            outcome=WriteOutcome.REFUSED,
            http_status=status_code,
            detail=_refusal_detail(status_code),
            response_excerpt=excerpt,
            attempted_at=attempted_at,
            url=url,
        )

    # Everything else, including 3xx. A redirect is not a refusal: the origin
    # may have acted before answering, and we do not follow it to find out.
    return WriteResult(
        outcome=WriteOutcome.OUTCOME_UNKNOWN,
        http_status=status_code,
        detail=(
            f"Sunucu {status_code} dondu. Bu yanit yazmadigini kanitlamaz; "
            "sonuc bilinmiyor."
        ),
        response_excerpt=excerpt,
        attempted_at=attempted_at,
        url=url,
    )


def _refusal_detail(status_code: int) -> str:
    """Why a refusal happened, in the terms the protocol uses.

    422 gets its own sentence because it is the one refusal a user will be
    tempted to retry, and retrying it sends the same bytes to the same filter
    for the same answer.
    """
    if status_code == 422:
        return (
            "Sunucu ayni metnin yakin zamanda yazildigini bildirdi (tekrar "
            "filtresi). Ayni baytlari yeniden gondermek yine reddedilir."
        )
    if status_code == 403:
        return "Sunucu bu odaya yazmayi reddetti (yetki)."
    if status_code == 413:
        return "Govde sunucunun kabul ettiginden buyuk."
    return "Sunucu istegi reddetti; hicbir sey yazilmadi."


def _read_capped(response: httpx.Response) -> bytes:
    """Buffer at most ``MAX_RESPONSE_BYTES`` of a body we do not trust.

    The read client's pattern, applied here for the same reason: ``iter_bytes``
    yields **decompressed** data, so the limit applies to what would actually
    be held in memory rather than to the wire size. ``response.content`` would
    buffer the whole body first and slice afterwards, which is not a cap at
    all - a 64 MiB expansion of a 65 KB gzip would be fully materialised before
    the slice ever ran.

    A body carrying a ``Content-Encoding`` we did not ask for is not read at
    all. ``Accept-Encoding: identity`` is a request, not a guarantee; a server
    that ignores it could answer a 65 KB gzip that expands to 64 MiB, and
    decoding *any* of it to find out is the part worth not doing. Nothing is
    decompressed, so nothing can expand.

    Reaching the cap stops the read; it is not an error. The receipt is
    already longer than anything worth keeping, and refusing to classify a
    write because its receipt was oversized would turn an ``accepted`` into an
    ``outcome_unknown`` - the one conversion this module exists to avoid. The
    same holds for a refused encoding: the status still classifies the write.
    """
    encoding = response.headers.get("content-encoding", "").strip().lower()
    if encoding not in IDENTITY_ENCODINGS:
        return UNREAD_BODY_NOTE

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes(_CHUNK_BYTES):
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_RESPONSE_BYTES:
            break
    return b"".join(chunks)[:MAX_RESPONSE_BYTES]


def _excerpt(body: bytes) -> str:
    """A bounded, swept excerpt of a response we do not trust."""
    if not body:
        return ""
    text = body.decode("utf-8", errors="replace")
    return safe_display(text[: MAX_EXCERPT_CHARS * 2])[:MAX_EXCERPT_CHARS]


__all__ = [
    "IDENTITY_ENCODINGS",
    "MAX_EXCERPT_CHARS",
    "MAX_RESPONSE_BYTES",
    "REFUSED_STATUSES",
    "UNREAD_BODY_NOTE",
    "WRITE_TIMEOUT",
    "SignedWriteClient",
    "WriteOutcome",
    "WriteResult",
]
