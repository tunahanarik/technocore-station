"""Three protocol adapters, one event model.

The service publishes three endpoints and distinguishes them in its own
documentation only by an "AI SDK Package" column; it never publishes their
request or response bodies (ADR-0005 1). So the shapes below are the shapes
of the **upstream protocol families the endpoint names identify** - the
Responses API, the Messages API and Chat Completions - and that provenance is
recorded on each adapter rather than presented as OpenCode's contract.

The practical consequence is written into :data:`SHAPE_PROVENANCE` and shown
to the user: this build proves the three shapes against fixtures, and a real
account test belongs to the person who owns the account. No automated test in
this repository makes a metered call.

What every adapter refuses to do
--------------------------------
* **Treat a 200 as success.** All three families can carry an error member in
  a 200 body. :func:`parse_response` looks for one before it looks for text,
  and a hit becomes a failure event.
* **Invent usage.** A body that reports no token counts produces
  :data:`~station_api.opencode.events.UNKNOWN_USAGE`, never zeroes.
* **Guess at an unfamiliar shape.** A 200 whose body carries neither an error
  nor recognisable text is ``MALFORMED_BODY``, not an empty answer. An empty
  answer would look like the model declined; a malformed body means we could
  not read what it said, and those are different sentences.
* **Substitute a model.** The model id in the request is the one the caller
  resolved through the closed table, and nothing here rewrites it.

Streaming and tool calls are absent by decision, not by omission - see
:mod:`station_api.opencode.events`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from station_api.opencode.client import RawResponse
from station_api.opencode.errors import OpenCodeResponseError
from station_api.opencode.events import (
    UNKNOWN_USAGE,
    CompletionEvent,
    FailureKind,
    FinishReason,
    TokenUsage,
    failed,
)
from station_api.opencode.registry import Protocol, wire_model_id
from station_api.strict_json import StrictJsonError, canonical_json_bytes, loads_strict

#: Where the three body shapes come from, stated so nobody reads them as a
#: verified OpenCode contract.
SHAPE_PROVENANCE = (
    "Uc protokol ailesinin govde bicimi OpenCode belgelerinde yayimlanmis "
    "degildir. Station, endpoint adlarinin isaret ettigi ust protokol "
    "ailelerinin bilinen non-streaming bicimini kullanir ve bunu sahte "
    "tasiyici ile fixture'a karsi dogrular. Gercek hesapla dogrulama "
    "hesabin sahibine aittir."
)

#: Cap on a request body. Small on purpose: this lane carries a credential
#: and a metered call, and neither benefits from an unbounded body.
MAX_REQUEST_BYTES = 256 * 1024

#: Cap on a parsed response document.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

#: Default output ceiling for the family that requires one. Named rather than
#: inlined so a reader sees that a bound exists at all.
DEFAULT_MAX_OUTPUT_TOKENS = 1024

#: Status codes we can name. Anything else is ``PROVIDER_ERROR``: an error we
#: can see and will not pretend to have classified.
_STATUS_FAILURES: dict[int, FailureKind] = {
    401: FailureKind.INVALID_CREDENTIAL,
    403: FailureKind.FORBIDDEN_MODEL,
    404: FailureKind.MODEL_NOT_FOUND,
    429: FailureKind.QUOTA_EXHAUSTED,
}

#: The sentence shown for each failure kind. Turkish, diacritic-free, and
#: careful about what it claims: an invalid credential is what the status
#: says, not proof that the key is wrong in some other sense.
FAILURE_DETAIL: dict[FailureKind, str] = {
    FailureKind.INVALID_CREDENTIAL: (
        "Saglayici anahtari reddetti (401). Kaydedilen anahtar bu istekte "
        "kabul edilmedi."
    ),
    FailureKind.FORBIDDEN_MODEL: (
        "Saglayici bu modele erisimi reddetti (403). Modelin listelenmesi bu "
        "hesabin onu cagirabildigi anlamina gelmez."
    ),
    FailureKind.MODEL_NOT_FOUND: (
        "Saglayici bu modeli bulamadi (404). Model kaldirilmis veya kimligi "
        "degismis olabilir; Station baska bir modele gecmez."
    ),
    FailureKind.QUOTA_EXHAUSTED: (
        "Saglayici kota siniri bildirdi (429). Station otomatik olarak "
        "tekrar denemez."
    ),
    FailureKind.SERVER_ERROR: (
        "Saglayici tarafinda sunucu hatasi. Istek surecten cikti; sonucu "
        "bilinmiyor."
    ),
    FailureKind.MALFORMED_BODY: (
        "Yanit govdesi okunamadi. Bu bir cevap degildir ve bos cevap olarak "
        "sayilmaz."
    ),
    FailureKind.EMPTY_BODY: "Saglayici bos govde dondurdu. Cevap yok.",
    FailureKind.PROVIDER_ERROR: (
        "Saglayici bir hata bildirdi. Ayrinti asagida oldugu gibi "
        "aktarilmistir; Station bunu kendi cumlesi olarak sunmaz."
    ),
    FailureKind.LOST_RESPONSE: (
        "Yanit alinamadi. Istek surecten cikmis olabilir ve ucretlenmis "
        "olabilir; otomatik olarak tekrarlanmaz."
    ),
    FailureKind.TRANSPORT_ERROR: "Baglanti kurulamadi.",
}


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


def build_request(
    protocol: Protocol,
    *,
    model: str,
    prompt: str,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> bytes:
    """Canonical JSON for one non-streaming request.

    ``stream`` is present and ``false`` in all three, because leaving it out
    would make the non-streaming behaviour a default we are relying on rather
    than a thing we asked for.
    """
    wire_id = wire_model_id(model)
    if protocol is Protocol.RESPONSES:
        document: dict[str, Any] = {
            "model": wire_id,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            "stream": False,
        }
    elif protocol is Protocol.MESSAGES:
        document = {
            "model": wire_id,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
    else:
        document = {
            "model": wire_id,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }

    payload = canonical_json_bytes(document)
    if len(payload) > MAX_REQUEST_BYTES:
        raise OpenCodeResponseError(
            f"request body exceeds the {MAX_REQUEST_BYTES}-byte cap"
        )
    return payload


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def parse_response(
    protocol: Protocol, raw: RawResponse, *, model: str
) -> CompletionEvent:
    """Turn one raw response into one event, whichever family produced it."""
    wire_id = wire_model_id(model)

    if not raw.body.strip():
        return failed(
            protocol,
            wire_id,
            kind=FailureKind.EMPTY_BODY,
            http_status=raw.status_code,
            detail=FAILURE_DETAIL[FailureKind.EMPTY_BODY],
        )

    document = _load(raw)
    if document is None:
        return failed(
            protocol,
            wire_id,
            kind=FailureKind.MALFORMED_BODY,
            http_status=raw.status_code,
            detail=FAILURE_DETAIL[FailureKind.MALFORMED_BODY],
        )

    # The status line first, but the body still parsed above so a named
    # failure can carry the provider's own words as data.
    if raw.status_code != 200:
        kind = _STATUS_FAILURES.get(raw.status_code)
        if kind is None:
            kind = (
                FailureKind.SERVER_ERROR
                if raw.status_code >= 500
                else FailureKind.PROVIDER_ERROR
            )
        return failed(
            protocol,
            wire_id,
            kind=kind,
            http_status=raw.status_code,
            detail=_with_excerpt(FAILURE_DETAIL[kind], raw),
        )

    # A 200 that carries an error member. This is the case a status-only
    # reader gets wrong, and it is the one the brief names.
    if _carries_error(document):
        return failed(
            protocol,
            wire_id,
            kind=FailureKind.PROVIDER_ERROR,
            http_status=raw.status_code,
            detail=_with_excerpt(FAILURE_DETAIL[FailureKind.PROVIDER_ERROR], raw),
        )

    parsed = _PARSERS[protocol](document, wire_id)
    if parsed is None:
        return failed(
            protocol,
            wire_id,
            kind=FailureKind.MALFORMED_BODY,
            http_status=raw.status_code,
            detail=FAILURE_DETAIL[FailureKind.MALFORMED_BODY],
        )
    return parsed


def _load(raw: RawResponse) -> dict[str, Any] | None:
    try:
        return loads_strict(raw.body, max_bytes=MAX_RESPONSE_BYTES)
    except StrictJsonError:
        return None


def _carries_error(document: dict[str, Any]) -> bool:
    """Whether a body reports a failure regardless of the status line.

    ``error`` present and not ``null`` is a failure in all three families.
    ``"type": "error"`` is the Messages family's spelling of the same thing.
    """
    if document.get("error") is not None and "error" in document:
        return True
    return document.get("type") == "error"


def _with_excerpt(sentence: str, raw: RawResponse) -> str:
    excerpt = raw.excerpt
    if not excerpt:
        return sentence
    return f"{sentence} Saglayici yaniti: {excerpt}"


# --- family: Responses ------------------------------------------------------


def _parse_responses(document: dict[str, Any], model: str) -> CompletionEvent | None:
    text = _responses_text(document)
    if text is None:
        return None

    usage = _usage(document, input_key="input_tokens", output_key="output_tokens")
    status = document.get("status")
    incomplete = document.get("incomplete_details")
    reason = FinishReason.UNKNOWN
    if status == "completed":
        reason = FinishReason.COMPLETED
    elif status == "incomplete":
        reason = FinishReason.LENGTH if _is_length_stop(incomplete) else FinishReason.REFUSED
    return CompletionEvent(
        protocol=Protocol.RESPONSES,
        model=model,
        text=text,
        finish=reason,
        usage=usage,
    )


def _responses_text(document: dict[str, Any]) -> str | None:
    """``output_text`` when present, otherwise the ``output`` item list."""
    direct = document.get("output_text")
    if isinstance(direct, str):
        return direct

    output = document.get("output")
    if not isinstance(output, list):
        return None

    pieces: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            return None
        content = item.get("content")
        if content is None:
            continue
        if not isinstance(content, list):
            return None
        for part in content:
            if not isinstance(part, dict):
                return None
            value = part.get("text")
            if isinstance(value, str):
                pieces.append(value)
    return "".join(pieces) if pieces else None


def _is_length_stop(incomplete: Any) -> bool:
    return (
        isinstance(incomplete, dict)
        and incomplete.get("reason") == "max_output_tokens"
    )


# --- family: Messages -------------------------------------------------------

_MESSAGES_STOP: dict[str, FinishReason] = {
    "end_turn": FinishReason.COMPLETED,
    "stop_sequence": FinishReason.COMPLETED,
    "max_tokens": FinishReason.LENGTH,
    "refusal": FinishReason.REFUSED,
}


def _parse_messages(document: dict[str, Any], model: str) -> CompletionEvent | None:
    content = document.get("content")
    if not isinstance(content, list):
        return None

    pieces: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            return None
        value = part.get("text")
        if isinstance(value, str):
            pieces.append(value)
    if not pieces:
        return None

    stop = document.get("stop_reason")
    reason = (
        _MESSAGES_STOP.get(stop, FinishReason.UNKNOWN)
        if isinstance(stop, str)
        else FinishReason.UNKNOWN
    )
    return CompletionEvent(
        protocol=Protocol.MESSAGES,
        model=model,
        text="".join(pieces),
        finish=reason,
        usage=_usage(document, input_key="input_tokens", output_key="output_tokens"),
    )


# --- family: Chat Completions -----------------------------------------------

_CHAT_FINISH: dict[str, FinishReason] = {
    "stop": FinishReason.COMPLETED,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.REFUSED,
}


def _parse_chat_completions(
    document: dict[str, Any], model: str
) -> CompletionEvent | None:
    choices = document.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    text = message.get("content")
    if not isinstance(text, str):
        return None

    finish = first.get("finish_reason")
    reason = (
        _CHAT_FINISH.get(finish, FinishReason.UNKNOWN)
        if isinstance(finish, str)
        else FinishReason.UNKNOWN
    )
    return CompletionEvent(
        protocol=Protocol.CHAT_COMPLETIONS,
        model=model,
        text=text,
        finish=reason,
        usage=_usage(
            document, input_key="prompt_tokens", output_key="completion_tokens"
        ),
    )


# --- shared -----------------------------------------------------------------


def _usage(document: dict[str, Any], *, input_key: str, output_key: str) -> TokenUsage:
    """Token counts, or ``UNKNOWN_USAGE``. Never zero-filled."""
    usage = document.get("usage")
    if not isinstance(usage, dict):
        return UNKNOWN_USAGE
    return TokenUsage(
        input_tokens=_count(usage.get(input_key)),
        output_tokens=_count(usage.get(output_key)),
    )


def _count(value: Any) -> int | None:
    """A non-negative integer, or ``None``.

    ``bool`` is rejected explicitly: it is an ``int`` subclass in Python, and
    ``True`` silently becoming a token count of 1 is exactly the kind of
    fabricated figure this module refuses.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


_PARSERS: dict[Protocol, Callable[[dict[str, Any], str], CompletionEvent | None]] = {
    Protocol.RESPONSES: _parse_responses,
    Protocol.MESSAGES: _parse_messages,
    Protocol.CHAT_COMPLETIONS: _parse_chat_completions,
}


__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "FAILURE_DETAIL",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "SHAPE_PROVENANCE",
    "build_request",
    "parse_response",
]
