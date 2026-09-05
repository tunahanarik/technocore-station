"""The one event model the three protocol families collapse into.

Three families, three body shapes, and - if each one were read on its own
terms - three different ways for the rest of the application to be wrong
about what happened. So the adapters do the reading and everything else sees
:class:`CompletionEvent`: one text, one finish reason, one usage record and
at most one failure.

Two rules are built into the types rather than left to a convention.

**Zero is not "unknown".** :class:`TokenUsage` holds ``None`` when the
provider reported nothing, and :attr:`TokenUsage.known` is what a caller
asks. A usage record that defaulted to ``0`` would be a fabricated cost
figure, and the one place a fabricated cost figure is guaranteed to be
believed is a spend display (ADR-0005 9).

**A 200 is not a success.** All three families can carry a provider error
inside a 200 response, so :attr:`CompletionEvent.succeeded` is derived from
the parsed body and never from the status line. A build that trusted the
status would report a refusal as an answer.

What is here, what is not, and why the answer changed for one of them
----------------------------------------------------------------------
There was no streaming event and no tool call. ADR-0005 2's reason was that
the documentation defined neither format, so writing one would have been a
guess with no way to notice it was wrong.

**Half of that is no longer true.** ADR-0012 measured the tool-call shape
against the account holder's own key on ``chat/completions`` - the request
carries ``tools`` and ``tool_choice``, the answer carries
``finish_reason: "tool_calls"`` and a ``tool_calls`` array - so the format is
no longer a guess and :data:`TOOL_CALLS_SUPPORTED` says so. The parsing lives
in :mod:`station_api.opencode.planner`, beside the provenance sentence that
records exactly what was measured and how far the measurement reaches.

**Streaming is untouched.** Nobody measured it, so
:data:`STREAMING_SUPPORTED` is still ``False`` and
:data:`DEFERRAL_SENTENCE` still names it. The two constants were always one
sentence about two formats; they are two sentences now, because the two
formats stopped having the same answer and a single sentence would have had
to be wrong about one of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from station_api.opencode.registry import Protocol

#: Deferred, not missing. Read by the status endpoint so the UI states it.
#:
#: Still ``False``, and still for the original reason: the streaming format
#: was never published and has never been measured, so this build does not
#: claim it.
STREAMING_SUPPORTED: Final[Literal[False]] = False

#: **Measured, not assumed** (ADR-0012). It was ``False`` for five packages
#: because the wire format was unpublished and ADR-0005 1.2 forbids inventing
#: an external contract. The contract was then measured against the account
#: holder's own key, so the value states the measured fact rather than an
#: assumption in either direction.
#:
#: The constant is not deleted now that it is ``True``. A reader who saw
#: ``false`` in a previous release is told the **value** changed, which is a
#: different thing from a field quietly going away.
TOOL_CALLS_SUPPORTED = True

DEFERRAL_SENTENCE = (
    "Akis (streaming) bu surumde yoktur: resmi belgede bu bicimin sozlesmesi "
    "yayimlanmamis, tahmin de edilmemistir. Arac cagrisi ise farklidir: "
    "bicimi hesap sahibinin kendi anahtariyla olculdu ve yalnizca olculen "
    "protokol ailesi icin acildi."
)


class FinishReason(StrEnum):
    """Why the model stopped, normalised across the three families."""

    COMPLETED = "completed"
    LENGTH = "length"
    REFUSED = "refused"
    PROVIDER_ERROR = "provider_error"
    #: The body did not say, or said something this build does not recognise.
    #: Deliberately distinct from ``COMPLETED``.
    UNKNOWN = "unknown"


class FailureKind(StrEnum):
    """What went wrong, in terms the user interface can act on.

    Every one of these is derived from the status line or the body. None is
    a guess about the provider's intent: ``PROVIDER_ERROR`` is the honest
    bucket for an error we can see but cannot classify.
    """

    INVALID_CREDENTIAL = "invalid_credential"
    FORBIDDEN_MODEL = "forbidden_model"
    MODEL_NOT_FOUND = "model_not_found"
    QUOTA_EXHAUSTED = "quota_exhausted"
    SERVER_ERROR = "server_error"
    MALFORMED_BODY = "malformed_body"
    EMPTY_BODY = "empty_body"
    PROVIDER_ERROR = "provider_error"
    LOST_RESPONSE = "lost_response"
    TRANSPORT_ERROR = "transport_error"


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What the provider said it counted. ``None`` means it did not say."""

    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def known(self) -> bool:
        return self.input_tokens is not None or self.output_tokens is not None

    @property
    def total_tokens(self) -> int | None:
        """The sum, or ``None`` when either half is missing.

        Not a partial sum. Adding a known half to an unknown one and
        presenting the result would be the fabricated figure this module
        exists to refuse.
        """
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


#: The usage record when nothing was reported. A named constant so the
#: "unknown" case is written once and reads the same everywhere.
UNKNOWN_USAGE = TokenUsage()


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """One failure, already neutralised for display.

    ``detail`` is our own sentence. Text quoted from upstream is data, not an
    assertion (SI-199's rule), and is never allowed to carry the credential:
    the client scrubs the response through the redaction registry before any
    excerpt reaches here.
    """

    kind: FailureKind
    http_status: int
    detail: str


@dataclass(frozen=True, slots=True)
class CompletionEvent:
    """One non-streaming answer, whichever family produced it."""

    protocol: Protocol
    model: str
    text: str
    finish: FinishReason
    usage: TokenUsage
    failure: ProviderFailure | None = None

    @property
    def succeeded(self) -> bool:
        """No failure, and a finish reason that is not an error.

        Derived, so "the status was 200" cannot be mistaken for success
        anywhere in the application.
        """
        return self.failure is None and self.finish is not FinishReason.PROVIDER_ERROR

    @property
    def cost_is_unknown(self) -> bool:
        """Whether a spend figure would have to be invented to be shown."""
        return not self.usage.known


def failed(
    protocol: Protocol,
    model: str,
    *,
    kind: FailureKind,
    http_status: int,
    detail: str,
) -> CompletionEvent:
    """A failure event with no text and no invented usage."""
    return CompletionEvent(
        protocol=protocol,
        model=model,
        text="",
        finish=FinishReason.PROVIDER_ERROR,
        usage=UNKNOWN_USAGE,
        failure=ProviderFailure(kind=kind, http_status=http_status, detail=detail),
    )


__all__ = [
    "DEFERRAL_SENTENCE",
    "STREAMING_SUPPORTED",
    "TOOL_CALLS_SUPPORTED",
    "UNKNOWN_USAGE",
    "CompletionEvent",
    "FailureKind",
    "FinishReason",
    "ProviderFailure",
    "TokenUsage",
    "failed",
]
