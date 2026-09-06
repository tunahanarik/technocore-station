"""The tool-call protocol adapter: how a model proposes a plan, and what is kept.

ADR-0005 1.2 and ADR-0008 2 both said the tool-call wire format was
**unpublished**, and both refused to invent one. That refusal was correct
while it held and it is the reason this module did not exist for five
packages. It no longer holds: the format was **measured**, against the
account holder's own key, on the ``chat/completions`` endpoint this build
already had in its closed registry.

What was measured, and what is therefore claimed
------------------------------------------------
``POST https://opencode.ai/zen/go/v1/chat/completions`` answered ``200`` to a
request carrying ``tools`` - a list of ``{"type": "function", "function":
{"name", "description", "parameters"}}`` objects whose ``parameters`` is JSON
Schema - together with ``tool_choice: "auto"``. The answer carried
``finish_reason: "tool_calls"`` and, on the assistant message, a ``tool_calls``
array of ``{"index", "id", "type": "function", "function": {"name",
"arguments"}}``. The model named a tool from the list and filled its declared
arguments.

Three details of that measurement are load-bearing and are written into the
code rather than into a comment:

* ``function.arguments`` is a **JSON string**, not an object. Parsing it is a
  step that can fail, and a failure is a refusal rather than an empty
  argument map;
* the assistant message carried a ``reasoning_content`` field. Nothing this
  module returns can hold it - see below;
* the body carried a ``cost`` member alongside ``usage``. Both are read as
  the provider sent them and neither is invented when absent (SI-250).

What is still not claimed: nothing about the ``responses`` or ``messages``
families' tool-call shapes, and nothing about streaming. Only the family that
was measured gets a builder here, and
:func:`station_api.opencode.registry.protocol_endpoint` still decides the
address from the compile-time table, so a model whose row says another family
cannot be used for planning at all - it is refused by name rather than sent to
an endpoint whose contract nobody has read.

``reasoning_content`` has nowhere to go, which is not the same as being deleted
-------------------------------------------------------------------------------
ADR-0008 6 and the H2 schema rule: there is **no column** in this application
that can hold a model's reasoning, and
``test_agent_boundary.py::test_no_agent_table_can_hold_a_model_reasoning_trace``
enforces that against the database rather than against a promise.

What holds it *here* is narrower than this paragraph used to claim, and the
difference matters because the claim was load-bearing. This module used to
pop the field off the decoded message and the comment beside the loop called
that the enforcement. It was not: every field below is taken out of the
mapping **by name** from an allow-list, and :class:`PlanProposal` has no
member the value could land in even if the pop were deleted - which was
measured, by turning the loop into a no-op and finding nothing red anywhere.
A deletion nothing depends on reads like a control and is not one.

So the type is the control on this path, and it is stated as the type: the
allow-list above and the shape of :class:`PlanProposal` below. The deny-list
itself moved to where it is genuinely load-bearing -
:data:`station_api.opencode.client.DISCARDED_MESSAGE_FIELDS`, applied to the
bounded excerpt of an error body. That is the path where the value could
reach a person, because a failure quotes the body back into a sentence the
surface shows, and it is the half of ADR-0012 1's "not shown" that was open.

A proposal is not a plan and is certainly not a run
----------------------------------------------------
Nothing here executes anything, validates anything against the tool registry
or touches a task. It turns bytes into a typed value. Whether a proposed call
names a registered tool, whether its arguments satisfy that tool's declared
types, and whether a person approved the result are all decided by
:mod:`station_api.planner.service` and
:mod:`station_api.agent.service`, in that order, and every one of those
answers can be "no".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from station_api.opencode.adapters import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    FAILURE_DETAIL,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    STATUS_FAILURES,
)
from station_api.opencode.client import (
    DISCARDED_MESSAGE_FIELDS as _DISCARDED_MESSAGE_FIELDS,
)
from station_api.opencode.client import RawResponse
from station_api.opencode.errors import OpenCodeResponseError
from station_api.opencode.events import (
    UNKNOWN_USAGE,
    FailureKind,
    ProviderFailure,
    TokenUsage,
)
from station_api.opencode.registry import Protocol, wire_model_id
from station_api.strict_json import StrictJsonError, canonical_json_bytes, loads_strict

#: Where the tool-call shape comes from. Stated the way
#: :data:`station_api.opencode.adapters.SHAPE_PROVENANCE` states its own, and
#: for the same reason: a reader has to be able to tell a measurement from a
#: guess, and this one is a measurement with a date and an endpoint on it.
TOOL_CALL_PROVENANCE = (
    "Arac cagrisi bicimi, hesap sahibinin kendi anahtariyla "
    "'POST /zen/go/v1/chat/completions' ucuna karsi olculdu: istek 'tools' ve "
    "'tool_choice' tasidi, yanit 'finish_reason: tool_calls' ve bir "
    "'tool_calls' dizisi dondurdu; 'function.arguments' bir JSON dizesidir. "
    "Olcum yalnizca bu protokol ailesi icindir; digerleri icin bir sey "
    "iddia edilmez."
)

#: The only family whose tool-call shape was measured. A model that speaks
#: another one is refused by name rather than sent to an unread contract.
SUPPORTED_PROTOCOL = Protocol.CHAT_COMPLETIONS

#: Sent so the non-streaming behaviour is a thing we asked for rather than a
#: default we are relying on - :func:`adapters.build_request`'s rule.
STREAM = False

#: The model may call a tool or answer in words. It is never forced to call
#: one: a forced call is a call the model did not choose, and this build wants
#: "the model proposed this" to be a true sentence.
TOOL_CHOICE = "auto"

#: Most calls one turn may propose. A turn that wanted more than this is a
#: turn whose plan a person cannot read before approving it, which is the
#: thing the approval exists for.
MAX_CALLS_PER_TURN = 8

#: Longest ``function.arguments`` string accepted before parsing.
#:
#: A **truncation guard, not a budget**. What a call may actually contain is
#: decided by the closed registry: every parameter is typed and bounded by
#: :mod:`station_api.agent.tools`, whose largest is ``MAX_TEXT_CHARS`` at
#: 20 000 characters, and those bounds are applied *after* parsing and are
#: unchanged. This number only decides whether the envelope is read at all.
#:
#: Measured, for a maximal ``write_workspace_file`` call - a 120-character
#: name and a 20 000-character body:
#:
#: * as the provider sends it, UTF-8 with no escaping: **20 144** characters.
#:   8 000 refused this outright, so a legitimate maximal call was being
#:   rejected for its envelope rather than for its content;
#: * with ``ensure_ascii`` escaping and an all-Turkish body: 120 144;
#:   all-emoji: 240 144.
#:
#: 64 000 covers the first case three times over, which is the case the
#: measured provider produces. It does **not** cover a maximal body that
#: arrives fully ``\uXXXX``-escaped, and that is a deliberate stopping point
#: rather than an oversight: the outcome there is this build's ordinary
#: bounded refusal - the whole proposal is dropped and the person is told -
#: not a crash or a truncated call, and sizing an envelope for the worst
#: imaginable encoding of the largest imaginable payload is how a guard stops
#: being one.
#:
#: No tension with the workspace ceilings: 64 000 characters is an eighth of
#: the 512 KiB per-file cap.
MAX_ARGUMENTS_CHARS = 64_000

#: Longest ``tool_call.id`` kept. It is echoed back verbatim in the following
#: turn's ``role: "tool"`` message, so it is bounded rather than trusted.
MAX_CALL_ID_CHARS = 128

#: The output ceiling one planning turn asks for.
#:
#: The same number as the single-shot lane's and deliberately not a second
#: one - both lanes talk to the same models, and the reason the number is
#: what it is (a measured truncation, not a budget) is written once, on
#: :data:`~station_api.opencode.adapters.DEFAULT_MAX_OUTPUT_TOKENS`. It is
#: re-exported here so :mod:`station_api.planner.service` can pass it
#: **explicitly** rather than inherit it as a default: that package's import
#: allow-list (``test_planner_boundary.py``) does not include the single-shot
#: adapter, and a ceiling this lane depends on should be visible in the call
#: that depends on it.
PLAN_MAX_OUTPUT_TOKENS = DEFAULT_MAX_OUTPUT_TOKENS

#: The ``finish_reason`` values this build reads, spelled the way the measured
#: endpoint spells them.
#:
#: Named rather than written as literals, because two modules now decide
#: something from them - this one decides whether the loop continues,
#: :mod:`station_api.planner.service` decides what the turn *meant* - and one
#: literal in each file is the place where the two quietly stop agreeing.
FINISH_TOOL_CALLS = "tool_calls"
FINISH_STOP = "stop"
FINISH_LENGTH = "length"
FINISH_CONTENT_FILTER = "content_filter"

#: What is recorded when the body carried no ``finish_reason`` at all, or
#: carried one that was not a string.
#:
#: Empty rather than the word ``"unknown"``, which is what it used to be: a
#: placeholder spelled like a value the provider could itself have sent makes
#: "the provider reported nothing" and "the provider reported ``unknown``"
#: into the same sentence, and the surface has to be able to tell a person
#: which one happened.
FINISH_REASON_ABSENT = ""

#: Longest ``finish_reason`` kept. It is the provider's own string, it is
#: quoted into a sentence a person reads, and it is therefore bounded on the
#: way in like every other imported value on this lane.
MAX_FINISH_REASON_CHARS = 64

#: Re-exported from :mod:`station_api.opencode.client`, where the tuple now
#: lives because that is the one place it is consulted.
#:
#: It was defined here, and the comment beside it said a deny-list nothing
#: consults is decoration. It was right and it was describing itself: the pop
#: loop that read it in :func:`parse_plan_response` could be turned into a
#: no-op with nothing going red. The tuple is kept importable from this module
#: so ``docs/security-invariants.md``'s SI-331 and its tests still have one
#: name to point at, and so the protocol layer can say which fields it means -
#: but the code that acts on it is
#: :func:`station_api.opencode.client._excerpt`.
DISCARDED_MESSAGE_FIELDS = _DISCARDED_MESSAGE_FIELDS

MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolFunction:
    """One tool, as the request declares it. Station's schema, not a provider's.

    ``parameters`` is JSON Schema and is built by
    :func:`station_api.agent.tools.json_schema` from the closed tool registry.
    This module wraps it in the envelope the measured endpoint expects and
    adds nothing: the set of tools a model may propose is exactly the set the
    registry has, and it cannot be widened from here.
    """

    name: str
    description: str
    parameters: dict[str, Any]

    def wire(self) -> dict[str, Any]:
        return {
            "function": {
                "description": self.description,
                "name": self.name,
                "parameters": self.parameters,
            },
            "type": "function",
        }


@dataclass(frozen=True, slots=True)
class ProposedCall:
    """One tool call the model proposed. Untrusted until the registry sees it.

    ``arguments_json`` is kept as the **string** the provider sent, because
    that is what it is: the measurement showed ``function.arguments`` carrying
    a JSON document inside a JSON string. Parsing it is
    :meth:`arguments`'s job and can fail, which is a refusal a person reads
    rather than an empty argument map that would look like a call with no
    arguments.
    """

    call_id: str
    name: str
    arguments_json: str

    def arguments(self) -> dict[str, str]:
        """The arguments as a flat mapping of strings, or a refusal.

        Flat and stringly typed on purpose: every parameter in the tool
        registry is a text, a bare file name or a hex digest, so a nested
        object or a list is not an argument this product has a use for. A
        number or a boolean is accepted and rendered, because a model writing
        ``{"count": 3}`` for a text parameter is being helpful rather than
        hostile; anything structured is refused.
        """
        if len(self.arguments_json) > MAX_ARGUMENTS_CHARS:
            raise OpenCodeResponseError(
                f"arac cagrisi argumanlari {MAX_ARGUMENTS_CHARS} karakter "
                "tavanini asiyor"
            )
        text = self.arguments_json.strip() or "{}"
        try:
            document = loads_strict(text.encode("utf-8"), max_bytes=MAX_ARGUMENTS_CHARS)
        except StrictJsonError as exc:
            raise OpenCodeResponseError(
                "arac cagrisi argumanlari gecerli bir JSON nesnesi degil"
            ) from exc
        flat: dict[str, str] = {}
        for key, value in document.items():
            if isinstance(value, bool):
                flat[str(key)] = "true" if value else "false"
            elif isinstance(value, str | int | float):
                flat[str(key)] = str(value)
            else:
                raise OpenCodeResponseError(
                    f"'{key}' argumani metin, sayi veya dogruluk degeri degil"
                )
        return flat


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of the conversation, in the only four roles this build sends.

    There is no ``reasoning`` field and there is nowhere to put one. An
    assistant turn carries the calls it proposed - which the endpoint requires
    before it will accept their results - and nothing else the model said
    about how it got there.
    """

    role: MessageRole
    content: str = ""
    #: Only on an ``assistant`` turn: the calls that turn proposed.
    tool_calls: tuple[ProposedCall, ...] = ()
    #: Only on a ``tool`` turn: which call this is the result of.
    tool_call_id: str = ""

    def wire(self) -> dict[str, Any]:
        document: dict[str, Any] = {"content": self.content, "role": self.role}
        if self.tool_calls:
            document["tool_calls"] = [
                {
                    "function": {
                        "arguments": call.arguments_json,
                        "name": call.name,
                    },
                    "id": call.call_id,
                    "type": "function",
                }
                for call in self.tool_calls
            ]
        if self.tool_call_id:
            document["tool_call_id"] = self.tool_call_id
        return document


@dataclass(frozen=True, slots=True)
class PlanProposal:
    """What one model turn produced. Never a reasoning trace, never a verdict.

    ``finish_reason`` is carried as the provider spelled it rather than
    normalised, because the loop's exit condition is stated in terms of it -
    "keep going while it is ``tool_calls``" - and a normalisation step is a
    place for that condition to quietly change meaning. Verbatim, but not
    unbounded: it is truncated to :data:`MAX_FINISH_REASON_CHARS` on the way
    in, since it ends up quoted inside a sentence a person reads.
    :data:`FINISH_REASON_ABSENT` is what a body that reported none produces,
    and it is distinguishable from every value a provider might send.
    """

    finish_reason: str
    calls: tuple[ProposedCall, ...] = ()
    #: What the model said in words, when it said anything. Bounded by the
    #: response cap the client already applies.
    text: str = ""
    usage: TokenUsage = UNKNOWN_USAGE
    #: The provider's own ``cost`` member, verbatim, or ``""`` when it sent
    #: none. A **string**, so a provider that answers ``"0"`` is recorded as
    #: having answered ``"0"`` and nothing is rounded, converted or summed
    #: into a currency this build cannot check (ADR-0005 9, SI-250).
    cost: str = ""
    failure: ProviderFailure | None = field(default=None)

    @property
    def wants_tools(self) -> bool:
        """Whether the loop should continue. Both halves, deliberately.

        A ``finish_reason`` of ``tool_calls`` with an empty call list is not a
        reason to go round again - it is a turn that asked for nothing - and a
        loop keyed on the reason alone would spin on it.
        """
        return self.finish_reason == FINISH_TOOL_CALLS and bool(self.calls)

    @property
    def succeeded(self) -> bool:
        return self.failure is None


def build_plan_request(
    *,
    model: str,
    messages: tuple[Message, ...],
    functions: tuple[ToolFunction, ...],
    max_output_tokens: int,
) -> bytes:
    """Canonical JSON for one non-streaming tool-call turn.

    ``tools`` is always present and always the whole registry projection the
    caller passed: a request that offered a subset would let something other
    than the compile-time registry decide what the model may propose, and
    there is nowhere in this build that such a decision could honestly be
    made.
    """
    if not functions:
        raise OpenCodeResponseError("arac listesi bos; model cagrisi yapilmaz")
    document: dict[str, Any] = {
        "max_tokens": max_output_tokens,
        "messages": [message.wire() for message in messages],
        "model": wire_model_id(model),
        "stream": STREAM,
        "tool_choice": TOOL_CHOICE,
        "tools": [function.wire() for function in functions],
    }
    payload = canonical_json_bytes(document)
    if len(payload) > MAX_REQUEST_BYTES:
        raise OpenCodeResponseError(
            f"request body exceeds the {MAX_REQUEST_BYTES}-byte cap"
        )
    return payload


def parse_plan_response(raw: RawResponse) -> PlanProposal:
    """Turn one raw response into one proposal, dropping what must not be kept.

    The order is the one :func:`station_api.opencode.adapters.parse_response`
    established and for the same reasons: an empty body is not an answer, a
    body that will not parse is not an empty answer, the status line is read
    after the body so a named failure can still quote the provider's own
    words, and a ``200`` carrying an ``error`` member is a failure.
    """
    if not raw.body.strip():
        return _failed(FailureKind.EMPTY_BODY, raw)

    try:
        document = loads_strict(raw.body, max_bytes=MAX_RESPONSE_BYTES)
    except StrictJsonError:
        return _failed(FailureKind.MALFORMED_BODY, raw)

    if raw.status_code != 200:
        kind = STATUS_FAILURES.get(raw.status_code)
        if kind is None:
            kind = (
                FailureKind.SERVER_ERROR
                if raw.status_code >= 500
                else FailureKind.PROVIDER_ERROR
            )
        return _failed(kind, raw, quote=True)

    if document.get("error") is not None and "error" in document:
        return _failed(FailureKind.PROVIDER_ERROR, raw, quote=True)

    choices = document.get("choices")
    if not isinstance(choices, list) or not choices:
        return _failed(FailureKind.MALFORMED_BODY, raw)
    first = choices[0]
    if not isinstance(first, dict):
        return _failed(FailureKind.MALFORMED_BODY, raw)
    message = first.get("message")
    if not isinstance(message, dict):
        return _failed(FailureKind.MALFORMED_BODY, raw)

    # ADR-0008 6's enforcement in this direction is the two lines below and
    # the class they build, not a deletion: every member is taken out of
    # ``message`` and ``first`` **by name**, the mapping is never copied, and
    # ``PlanProposal`` has no field a reasoning value could land in. A pop
    # loop stood here and was removed rather than kept as reassurance - it
    # was measured to be a no-op, and a control that can be deleted without
    # anything noticing is one a reader will trust when they should be
    # reading the allow-list instead. Where the deny-list does work is
    # ``client._excerpt``, on the error body this function quotes below.
    calls = _tool_calls(message.get("tool_calls"))
    if calls is None:
        return _failed(FailureKind.MALFORMED_BODY, raw)

    content = message.get("content")
    finish = first.get("finish_reason")
    return PlanProposal(
        finish_reason=(
            finish[:MAX_FINISH_REASON_CHARS]
            if isinstance(finish, str)
            else FINISH_REASON_ABSENT
        ),
        calls=calls,
        text=content if isinstance(content, str) else "",
        usage=_usage(document),
        cost=_cost(document),
    )


def _tool_calls(value: Any) -> tuple[ProposedCall, ...] | None:
    """The proposed calls, or ``None`` when the array is not one we can read.

    ``None`` rather than an empty tuple, because those are different answers:
    an absent array means the model chose to speak instead of calling
    anything, and an array we could not read means we do not know what it
    chose. Collapsing them would turn an unreadable response into a
    "the model is finished".
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        return None
    if len(value) > MAX_CALLS_PER_TURN:
        return None

    calls: list[ProposedCall] = []
    for entry in value:
        if not isinstance(entry, dict):
            return None
        function = entry.get("function")
        if not isinstance(function, dict):
            return None
        name = function.get("name")
        arguments = function.get("arguments")
        call_id = entry.get("id")
        if not isinstance(name, str) or not name:
            return None
        if not isinstance(arguments, str):
            return None
        calls.append(
            ProposedCall(
                call_id=(
                    call_id[:MAX_CALL_ID_CHARS] if isinstance(call_id, str) else ""
                ),
                name=name[:64],
                arguments_json=arguments[:MAX_ARGUMENTS_CHARS],
            )
        )
    return tuple(calls)


def _usage(document: dict[str, Any]) -> TokenUsage:
    """Token counts as the provider reported them, or unknown. Never zeroed."""
    usage = document.get("usage")
    if not isinstance(usage, dict):
        return UNKNOWN_USAGE
    return TokenUsage(
        input_tokens=_count(usage.get("prompt_tokens")),
        output_tokens=_count(usage.get("completion_tokens")),
    )


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _cost(document: dict[str, Any]) -> str:
    """The ``cost`` member exactly as it arrived, or ``""``.

    Kept as text and never parsed into a number. The measured response
    answered the string ``"0"``; a build that turned that into a float and
    displayed ``0.00`` would be presenting its own arithmetic as the
    provider's statement, which is the shape of over-claim ADR-0005 9 refuses.
    An absent member produces ``""`` rather than ``"0"`` (SI-250).
    """
    value = document.get("cost")
    if isinstance(value, str):
        return value[:64]
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int | float):
        return str(value)[:64]
    return ""


def lost(detail: str) -> PlanProposal:
    """A turn whose answer never came back. Charged or not, we do not know.

    Its own constructor rather than a generic failure, because the sentence
    matters: a lost response is the one failure where retrying would turn a
    maybe-charge into a certain one, and the caller must be able to tell it
    apart from a refusal that definitely cost nothing.
    """
    return PlanProposal(
        finish_reason="lost_response",
        failure=ProviderFailure(
            kind=FailureKind.LOST_RESPONSE,
            http_status=0,
            detail=f"{FAILURE_DETAIL[FailureKind.LOST_RESPONSE]} {detail}"[:500],
        ),
    )


def transport_failed(detail: str) -> PlanProposal:
    """A turn that never left, or that the allow-list refused to send."""
    return PlanProposal(
        finish_reason="transport_error",
        failure=ProviderFailure(
            kind=FailureKind.TRANSPORT_ERROR,
            http_status=0,
            detail=f"{FAILURE_DETAIL[FailureKind.TRANSPORT_ERROR]} {detail}"[:500],
        ),
    )


def _failed(
    kind: FailureKind, raw: RawResponse, *, quote: bool = False
) -> PlanProposal:
    detail = FAILURE_DETAIL[kind]
    if quote and raw.excerpt:
        detail = f"{detail} Saglayici yaniti: {raw.excerpt}"
    return PlanProposal(
        finish_reason="provider_error",
        failure=ProviderFailure(
            kind=kind, http_status=raw.status_code, detail=detail
        ),
    )


__all__ = [
    "DISCARDED_MESSAGE_FIELDS",
    "FINISH_CONTENT_FILTER",
    "FINISH_LENGTH",
    "FINISH_REASON_ABSENT",
    "FINISH_STOP",
    "FINISH_TOOL_CALLS",
    "MAX_ARGUMENTS_CHARS",
    "MAX_CALLS_PER_TURN",
    "MAX_FINISH_REASON_CHARS",
    "PLAN_MAX_OUTPUT_TOKENS",
    "STREAM",
    "SUPPORTED_PROTOCOL",
    "TOOL_CALL_PROVENANCE",
    "TOOL_CHOICE",
    "Message",
    "MessageRole",
    "PlanProposal",
    "ProposedCall",
    "ToolFunction",
    "build_plan_request",
    "lost",
    "parse_plan_response",
    "transport_failed",
]
