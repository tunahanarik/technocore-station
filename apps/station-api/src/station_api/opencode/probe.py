"""The connection probe: one metered turn, and what its answer is allowed to mean.

ADR-0015. "Baglantiyi denetle" used to produce a fixed sentence, and the
reasoning written above it was sound while it held: *a probe that cost money
would need the user's explicit request; a probe that did not cost money would
not prove anything.* The button **is** the explicit request, and nothing was
behind it.

Why the catalog cannot be the probe
------------------------------------
:meth:`station_api.opencode.client.OpenCodeClient.fetch_catalog` attaches no
credential - it calls ``_with_bounded_retry(..., api_key=None)`` - and the
endpoint answers ``200`` without one. A request that succeeds without the
credential proves the *network* works and says nothing at all about the key.
The same is true of every other free address in the registry. So the only
request that can prove a stored key authenticates is one the provider would
refuse without it, and on this provider that means the **metered**
``chat/completions`` endpoint, which ADR-0012 measured accepting
``Authorization: Bearer``.

What the probe therefore is, and what it costs
-----------------------------------------------
One ``POST /zen/go/v1/chat/completions`` - the only body shape that was
measured - carrying the stored credential, the model the user selected, a
four-character prompt and :data:`PROBE_MAX_OUTPUT_TOKENS` of output headroom.
No ``tools`` array: the tool registry is what a *plan* offers a model, and a
connection check has no business offering it.

It costs **one model call**. The turn ADR-0012 measured was strictly larger -
the whole tool registry plus a real brief, 184 prompt tokens and 46 completion
tokens - and reported ``cost: "0"``; this one sends a fraction of that prompt
and caps generation at sixteen tokens. "Cheap" is not "free", which is why the
call is counted against :data:`station_api.agent.budget.MAX_CONNECTION_PROBES`
before it is made and recorded after.

Why the verdict is read off the status line and not off the text
-----------------------------------------------------------------
:func:`station_api.opencode.adapters.parse_response` requires readable
assistant text before it will call a ``200`` a success, and that is right for
the lane it serves: a completion with no text is a completion that failed.
It is wrong here. The probe asks exactly one question - *did this credential
authenticate* - and the answer to that arrived with the status line. A
reasoning model that spends all sixteen tokens before writing a word answers
``200`` with ``finish_reason: "length"`` and an empty ``content``, and reading
that as "unverified" would turn a proven credential into an unproven one
because the model was terse.

So this module reads the status code, plus the one thing a status code is
known to lie about: a ``200`` carrying an ``error`` member, which all three
protocol families can send and which
:func:`station_api.opencode.adapters._carries_error` already recognises.

Three outcomes, and the third is named for what it holds
---------------------------------------------------------
:class:`ProbeOutcome` has ``VERIFIED``, ``REFUSED`` and ``FAILED``. The third
is the "we do not know" bucket: no answer came back, or one came back that
settles nothing - a 429, a 5xx, a body that will not parse, a ``200`` carrying
an error. It is **not** called ``unreachable``, because a 429 is an answer from
a host that was plainly reached, and naming it after the network would be a
claim about the network that nothing here measured. The distinction a person
actually needs is carried by ``detail``, which is the provider's own sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from station_api.opencode.adapters import (
    FAILURE_DETAIL,
    MAX_RESPONSE_BYTES,
    STATUS_FAILURES,
    build_request,
)
from station_api.opencode.client import RawResponse
from station_api.opencode.events import FailureKind
from station_api.opencode.registry import Protocol
from station_api.strict_json import StrictJsonError, loads_strict

#: The family whose request and response shapes were measured (ADR-0012). A
#: model filed under any other family is refused by name rather than probed
#: against a contract nobody has read - the same rule
#: :func:`station_api.opencode.service.OpenCodeService.propose_plan` applies.
PROBE_PROTOCOL = Protocol.CHAT_COMPLETIONS

#: What the probe says. Four characters, no instruction, nothing about the
#: user, the machine, the identity or any task: the provider is being asked
#: whether it will accept the credential, not to do anything.
PROBE_PROMPT = "ping"

#: Output headroom for one probe.
#:
#: Deliberately tiny, and deliberately **not**
#: :data:`~station_api.opencode.adapters.DEFAULT_MAX_OUTPUT_TOKENS`. That
#: number is a truncation guard for a lane whose answer has to be complete;
#: here the answer is the status line and the generated text is discarded, so
#: the smallest ceiling that still lets the provider answer is the cheapest
#: honest request. A ``finish_reason`` of ``length`` is a **successful** probe.
PROBE_MAX_OUTPUT_TOKENS = 16

#: The statuses that mean the provider looked at the credential and said no.
#:
#: ``401`` is the credential being rejected. ``403`` is the account being told
#: it may not have this model - which is a refusal of the request, not proof
#: that the key is wrong, and the sentence carried with it
#: (``FAILURE_DETAIL[FailureKind.FORBIDDEN_MODEL]``) says exactly that rather
#: than being rewritten into a verdict about the key.
REFUSING_FAILURES: frozenset[FailureKind] = frozenset(
    {FailureKind.INVALID_CREDENTIAL, FailureKind.FORBIDDEN_MODEL}
)

#: What is said when the provider answered the metered request.
#:
#: The claim is bounded on purpose and in two directions: it is about **this
#: call**, and it is about **authentication**. It does not say the key will
#: work later, that the quota is intact, or that any other model is reachable.
VERIFIED_DETAIL = (
    "Anahtar dogrulandi: saglayici, kaydedilen anahtarla gonderilen olculu "
    "istege yanit verdi. Bu, denetim anindaki tek bir cagri icin gecerlidir; "
    "anahtar sonradan iptal edilebilir, kota dolabilir veya model degisebilir."
)


class ProbeOutcome(StrEnum):
    """What one probe established. Three answers, never two."""

    #: The provider answered the metered request. Only a credential it accepts
    #: can produce this.
    VERIFIED = "verified"
    #: The provider answered and refused: it rejected the credential (401) or
    #: refused this account this model (403).
    REFUSED = "provider_refused"
    #: No answer, or an answer that settles nothing. See the module docstring
    #: for why this is not called "unreachable".
    FAILED = "probe_failed"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """One probe's verdict, its status line, and the sentence a person reads."""

    outcome: ProbeOutcome
    #: 0 when the request never produced a status line.
    http_status: int
    detail: str


def build_probe_request(*, model: str) -> bytes:
    """Canonical JSON for the one request a connection check sends.

    Built through :func:`station_api.opencode.adapters.build_request` rather
    than assembled here, so the probe cannot drift into a second spelling of
    the body shape that was measured. The only thing this adds is the two
    numbers that make it a probe: a four-character prompt and a sixteen-token
    ceiling.
    """
    return build_request(
        PROBE_PROTOCOL,
        model=model,
        prompt=PROBE_PROMPT,
        max_output_tokens=PROBE_MAX_OUTPUT_TOKENS,
    )


def classify(raw: RawResponse) -> ProbeResult:
    """Turn one raw response into one verdict about the credential.

    Order matters and matches :func:`adapters.parse_response`'s for the same
    reasons: an empty body is not an answer, a body that will not parse is not
    an empty answer, and a ``200`` carrying an ``error`` member is a failure
    whatever the status line says.
    """
    if not raw.body.strip():
        return _failed(FailureKind.EMPTY_BODY, raw)

    document = _load(raw)
    if document is None:
        return _failed(FailureKind.MALFORMED_BODY, raw)

    if raw.status_code != 200:
        kind = STATUS_FAILURES.get(raw.status_code)
        if kind is None:
            kind = (
                FailureKind.SERVER_ERROR
                if raw.status_code >= 500
                else FailureKind.PROVIDER_ERROR
            )
        outcome = (
            ProbeOutcome.REFUSED if kind in REFUSING_FAILURES else ProbeOutcome.FAILED
        )
        return ProbeResult(
            outcome=outcome,
            http_status=raw.status_code,
            detail=_with_excerpt(FAILURE_DETAIL[kind], raw),
        )

    if document.get("error") is not None and "error" in document:
        return _failed(FailureKind.PROVIDER_ERROR, raw)

    return ProbeResult(
        outcome=ProbeOutcome.VERIFIED,
        http_status=raw.status_code,
        detail=VERIFIED_DETAIL,
    )


def lost(detail: str) -> ProbeResult:
    """A probe whose answer never came back. Charged or not, we do not know."""
    return ProbeResult(
        outcome=ProbeOutcome.FAILED,
        http_status=0,
        detail=f"{FAILURE_DETAIL[FailureKind.LOST_RESPONSE]} {detail}"[:500],
    )


def transport_failed(detail: str) -> ProbeResult:
    """A probe that never left, or that the allow-list refused to send."""
    return ProbeResult(
        outcome=ProbeOutcome.FAILED,
        http_status=0,
        detail=f"{FAILURE_DETAIL[FailureKind.TRANSPORT_ERROR]} {detail}"[:500],
    )


def _failed(kind: FailureKind, raw: RawResponse) -> ProbeResult:
    return ProbeResult(
        outcome=ProbeOutcome.FAILED,
        http_status=raw.status_code,
        detail=_with_excerpt(FAILURE_DETAIL[kind], raw),
    )


def _with_excerpt(sentence: str, raw: RawResponse) -> str:
    """The sentence, plus the provider's own bounded words when there are any.

    ``raw.excerpt`` is computed inside the client's redaction window, so a
    body that echoed the credential back is already ``<redacted>`` here, and a
    body carrying a reasoning field has already lost it
    (:data:`station_api.opencode.client.DISCARDED_MESSAGE_FIELDS`).
    """
    if not raw.excerpt:
        return sentence
    return f"{sentence} Saglayici yaniti: {raw.excerpt}"


def _load(raw: RawResponse) -> dict[str, Any] | None:
    try:
        return loads_strict(raw.body, max_bytes=MAX_RESPONSE_BYTES)
    except StrictJsonError:
        return None


__all__ = [
    "PROBE_MAX_OUTPUT_TOKENS",
    "PROBE_PROMPT",
    "PROBE_PROTOCOL",
    "REFUSING_FAILURES",
    "VERIFIED_DETAIL",
    "ProbeOutcome",
    "ProbeResult",
    "build_probe_request",
    "classify",
    "lost",
    "transport_failed",
]
