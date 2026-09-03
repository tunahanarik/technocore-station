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
* TLS verification is always on: ``verify`` is never passed, never exposed
  and never configurable.
* Redirects are never followed. A 3xx is ``outcome_unknown``, because the
  request may have been acted on before the hop and following one leaves the
  allow-listed origin.
* Timeouts are explicit on all four phases.
* The response body is read under a hard cap and kept only as a bounded,
  swept excerpt.
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
#: JSON receipt; anything larger is not something we need.
MAX_RESPONSE_BYTES = 64 * 1024

#: Longest excerpt kept from that body.
MAX_EXCERPT_CHARS = 1024


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

    ``transport`` exists so tests can substitute ``httpx.MockTransport``; it
    is not a security setting, because the URL is still built from the write
    registry and re-checked against the origin allow-list before the request.
    There is no ``url``, ``method``, ``headers`` or ``verify`` parameter, so
    a caller cannot steer the request anywhere.
    """

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
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
            with self._client() as client:
                response = client.request(WRITE_METHOD, url, json=dict(body))
                status_code = response.status_code
                excerpt = _excerpt(response.content[:MAX_RESPONSE_BYTES])
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
                # Identity encoding: a write receipt is small, and refusing
                # compression removes the decompression-bomb question here
                # entirely rather than bounding it.
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


def _excerpt(body: bytes) -> str:
    """A bounded, swept excerpt of a response we do not trust."""
    if not body:
        return ""
    text = body.decode("utf-8", errors="replace")
    return safe_display(text[: MAX_EXCERPT_CHARS * 2])[:MAX_EXCERPT_CHARS]


__all__ = [
    "MAX_EXCERPT_CHARS",
    "MAX_RESPONSE_BYTES",
    "REFUSED_STATUSES",
    "WRITE_TIMEOUT",
    "SignedWriteClient",
    "WriteOutcome",
    "WriteResult",
]
