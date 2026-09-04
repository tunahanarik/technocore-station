"""Shared fixtures for the OpenCode connection tests.

Everything here is synthetic. **No test in this package makes a real call to
any provider, and no test uses a real API key**: the autouse guard in
``tests/conftest.py`` blocks the network at two layers, and every client
below is driven through an ``httpx.MockTransport`` (SI-174's rule).

The catalog fixture is shaped after the document ADR-0005 1 recorded from the
live service - ``{id, object, created, owned_by}`` and nothing else - because
the *poverty* of that document is the thing several tests are about.

The five identifiers below are chosen so one fetched document exercises every
state a catalog row can land in:

* :data:`OBSERVED_MODEL_ID` and :data:`SECOND_OBSERVED_MODEL_ID` are real ids
  from the published "Endpoints" table, on two *different* protocol families,
  and neither is a training model - so both are selectable outright;
* :data:`TRAINING_MODEL_ID` is a real id the published "Privacy" table marks
  as used for training - documented, therefore selectable, but only after an
  explicit acknowledgement;
* :data:`SURPLUS_MODEL_ID` stands for the seven ids the live catalog returned
  that the Endpoints table does not list. It is the reason ``UNVERIFIED``
  exists: listed, and not addressable;
* :data:`TRAINING_FAMILY_MODEL_ID` is likewise absent from the table *and*
  falls inside a family the privacy table names, so it proves the family
  check raises the bar for an id we know nothing else about.

The last two carry ``TEST-ONLY`` in their own names, so nobody mistakes a
fixture for a model this build claims exists.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

#: A model identifier the ADR recorded from the live catalog, and a row of
#: the published Endpoints table: ``chat/completions``, retention "0 days",
#: not used for training. The plain selectable case.
OBSERVED_MODEL_ID = "glm-5.3"

#: A second one, likewise recorded and likewise documented - but on the
#: ``responses`` family and with a 30-day retention term. Selectable, and on a
#: *different* address, which is what makes "the protocol comes from the
#: table, not from the id" testable with one document.
#:
#: This is also the row that carried the transcription error the table was
#: corrected for: an earlier revision filed it under ``chat/completions``.
SECOND_OBSERVED_MODEL_ID = "grok-4.6"

#: Real, documented, and the Privacy table says its data trains the model and
#: that it is outside zero-data-retention. Selectable *and* gated behind an
#: acknowledgement - the two are separate properties, which is the point.
TRAINING_MODEL_ID = "muse-spark-1.3-contributor"

#: Synthetic, and named so it cannot be read as a real model. Stands for the
#: catalog surplus: an id the provider lists and the Endpoints table does not,
#: whose protocol family is therefore unknown and not guessed.
SURPLUS_MODEL_ID = "surplus-model-TEST-ONLY"

#: Synthetic, and named so it cannot be read as a real model. Absent from the
#: table like :data:`SURPLUS_MODEL_ID`, but inside the family the privacy
#: table names as used for training - so the family check has to raise the
#: bar on it even though there is no row to read a term from.
TRAINING_FAMILY_MODEL_ID = "muse-spark-TEST-ONLY"

CATALOG_DOCUMENT: dict[str, Any] = {
    "object": "list",
    "data": [
        {
            "id": OBSERVED_MODEL_ID,
            "object": "model",
            "created": 1756857600,
            "owned_by": "opencode",
        },
        {
            "id": SECOND_OBSERVED_MODEL_ID,
            "object": "model",
            "created": 1756857600,
            "owned_by": "opencode",
        },
        {
            "id": TRAINING_MODEL_ID,
            "object": "model",
            "created": 1756857600,
            "owned_by": "opencode",
        },
        {
            "id": SURPLUS_MODEL_ID,
            "object": "model",
            "created": 1756857600,
            "owned_by": "opencode",
        },
        {
            "id": TRAINING_FAMILY_MODEL_ID,
            "object": "model",
            "created": 1756857600,
            "owned_by": "opencode",
        },
    ],
}

#: How many rows of :data:`CATALOG_DOCUMENT` this build can actually address.
#: Three of the five: the two plain documented rows and the training row,
#: which is selectable but gated. Written out rather than computed, so a
#: change to either the fixture or the closed table has to be acknowledged
#: here.
SELECTABLE_IN_CATALOG = 3


def catalog_bytes(document: dict[str, Any] | None = None) -> bytes:
    return json.dumps(document if document is not None else CATALOG_DOCUMENT).encode()


# ---------------------------------------------------------------------------
# Protocol body fixtures
#
# Non-streaming only. ADR-0005 2: the streaming and tool-call formats are not
# published, so there is nothing to write a fixture against and this package
# deliberately has none.
# ---------------------------------------------------------------------------

RESPONSES_BODY: dict[str, Any] = {
    "id": "resp_TEST_ONLY",
    "object": "response",
    "model": OBSERVED_MODEL_ID,
    "status": "completed",
    "output": [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "merhaba"}],
        }
    ],
    "usage": {"input_tokens": 11, "output_tokens": 4},
}

MESSAGES_BODY: dict[str, Any] = {
    "id": "msg_TEST_ONLY",
    "type": "message",
    "role": "assistant",
    "model": OBSERVED_MODEL_ID,
    "content": [{"type": "text", "text": "merhaba"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 11, "output_tokens": 4},
}

CHAT_COMPLETIONS_BODY: dict[str, Any] = {
    "id": "chatcmpl_TEST_ONLY",
    "object": "chat.completion",
    "model": OBSERVED_MODEL_ID,
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "merhaba"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 4},
}


def body_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(document).encode()


# ---------------------------------------------------------------------------
# Recording transports
# ---------------------------------------------------------------------------


@dataclass
class TransportRecorder:
    """Every request a client actually attempted, and what it carried.

    Counting rather than asserting is the point on the startup tests: "no
    metered call happens at launch" is a claim about a number, and reading
    the number back is the only way to know rather than to believe.
    """

    requests: list[httpx.Request] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.requests)

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "no request was attempted"
        return self.requests[-1]

    def urls(self) -> list[str]:
        return [str(request.url) for request in self.requests]


def recording_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[httpx.MockTransport, TransportRecorder]:
    """A mock transport that answers with ``handler`` and remembers the call."""
    recorder = TransportRecorder()

    def record(request: httpx.Request) -> httpx.Response:
        # ``read()`` so the body is available after the handler returns; a
        # streamed request would otherwise be consumed by the time a test
        # looks at it.
        request.read()
        recorder.requests.append(request)
        return handler(request)

    return httpx.MockTransport(record), recorder


def constant_transport(
    response: httpx.Response,
) -> tuple[httpx.MockTransport, TransportRecorder]:
    """Answer every request with the same response."""
    return recording_transport(lambda _: response)


def status_transport(
    status_code: int, *, body: bytes = b"{}", headers: dict[str, str] | None = None
) -> tuple[httpx.MockTransport, TransportRecorder]:
    return recording_transport(
        lambda _: httpx.Response(status_code, content=body, headers=headers)
    )


def refusing_transport(
    exception: Exception,
) -> tuple[httpx.MockTransport, TransportRecorder]:
    """A transport that fails the way a network does."""

    def raise_it(_: httpx.Request) -> httpx.Response:
        raise exception

    return recording_transport(raise_it)


def catalog_transport(
    document: dict[str, Any] | None = None,
) -> tuple[httpx.MockTransport, TransportRecorder]:
    return recording_transport(
        lambda _: httpx.Response(
            200,
            content=catalog_bytes(document),
            headers={"content-type": "application/json"},
        )
    )


def never_called_transport() -> tuple[httpx.MockTransport, TransportRecorder]:
    """A transport that fails loudly if anything reaches it.

    Used where the claim is "nothing outbound happens here". The recorder is
    still returned so a test can assert the count is zero as well, which
    distinguishes "nothing was attempted" from "the assertion never ran".
    """

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            f"an outbound request was attempted: {request.method} {request.url}"
        )

    return recording_transport(refuse)


__all__ = [
    "CATALOG_DOCUMENT",
    "CHAT_COMPLETIONS_BODY",
    "MESSAGES_BODY",
    "OBSERVED_MODEL_ID",
    "RESPONSES_BODY",
    "SECOND_OBSERVED_MODEL_ID",
    "SELECTABLE_IN_CATALOG",
    "SURPLUS_MODEL_ID",
    "TRAINING_FAMILY_MODEL_ID",
    "TRAINING_MODEL_ID",
    "TransportRecorder",
    "body_bytes",
    "catalog_bytes",
    "catalog_transport",
    "constant_transport",
    "never_called_transport",
    "recording_transport",
    "refusing_transport",
    "status_transport",
]
