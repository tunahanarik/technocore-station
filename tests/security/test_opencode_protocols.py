"""Three protocol families, one event model, and the sentences it will not say.

Each family gets at least one fixture and is proved against it, because a
shape nobody exercised is a shape nobody has checked. Beyond that, the tests
here are mostly about **refusals** - the four things
:mod:`station_api.opencode.adapters` must not do - since those are the
behaviours that would be invisible if they broke:

* a 200 carrying a provider error is not a success;
* a body with no token counts does not become a cost figure of zero;
* an unfamiliar shape is not an empty answer;
* a body read under the wrong family does not quietly parse.

No test in this file makes a real call. Everything is a
``httpx.MockTransport`` and a fixture document (SI-174).
"""

from __future__ import annotations

import json

import httpx
import pytest
from station_api.opencode.adapters import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    SHAPE_PROVENANCE,
    build_request,
    parse_response,
)
from station_api.opencode.client import OpenCodeClient, RawResponse
from station_api.opencode.events import (
    DEFERRAL_SENTENCE,
    STREAMING_SUPPORTED,
    TOOL_CALLS_SUPPORTED,
    FailureKind,
    FinishReason,
    TokenUsage,
)
from station_api.opencode.registry import (
    DOC_LAST_UPDATED,
    ENDPOINTS_TABLE_SOURCE,
    MODEL_MAPPINGS,
    PRIVACY_TABLE_READ_ON,
    PROVIDER_PREFIX,
    RETENTION_NOT_ZDR,
    RETENTION_THIRTY,
    RETENTION_ZERO_FOOTNOTED,
    EndpointId,
    MappingVerification,
    Protocol,
    TrainingUse,
    find_mapping,
    protocol_endpoint,
    selectable_model_ids,
    wire_model_id,
)

from tests.security.opencode_fixtures import (
    CHAT_COMPLETIONS_BODY,
    MESSAGES_BODY,
    OBSERVED_MODEL_ID,
    RESPONSES_BODY,
    body_bytes,
    recording_transport,
    status_transport,
)

pytestmark = pytest.mark.security

TEST_ONLY_CREDENTIAL = "TEST-ONLY-protocol-credential-01"

#: One fixture per family. Parametrising over this is what makes "every
#: protocol family has at least one fixture" a fact rather than an intention.
FAMILY_FIXTURES = (
    (Protocol.RESPONSES, RESPONSES_BODY),
    (Protocol.MESSAGES, MESSAGES_BODY),
    (Protocol.CHAT_COMPLETIONS, CHAT_COMPLETIONS_BODY),
)


def _raw(status_code: int, body: bytes, protocol: Protocol) -> RawResponse:
    """One response, produced through the real client and a mock transport.

    Built through the client rather than constructed directly so the parsing
    tests exercise the same object the production path produces - including
    the cap, the allow-list and the redacting excerpt.
    """
    transport, _ = status_transport(status_code, body=body)
    client = OpenCodeClient(transport=transport, sleep=lambda _: None)
    return client.post_completion(protocol, b"{}", api_key=TEST_ONLY_CREDENTIAL)


# ---------------------------------------------------------------------------
# The happy shape, once per family
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("protocol", "document"), FAMILY_FIXTURES)
def test_each_family_collapses_into_the_same_event(
    protocol: Protocol, document: dict[str, object]
) -> None:
    event = parse_response(
        protocol, _raw(200, body_bytes(document), protocol), model=OBSERVED_MODEL_ID
    )

    assert event.succeeded is True
    assert event.failure is None
    assert event.text == "merhaba"
    assert event.finish is FinishReason.COMPLETED
    assert event.protocol is protocol
    assert event.model == OBSERVED_MODEL_ID


@pytest.mark.parametrize(("protocol", "document"), FAMILY_FIXTURES)
def test_each_family_reports_the_usage_the_provider_actually_sent(
    protocol: Protocol, document: dict[str, object]
) -> None:
    """Three different key names, one normalised record."""
    event = parse_response(
        protocol, _raw(200, body_bytes(document), protocol), model=OBSERVED_MODEL_ID
    )

    assert event.usage == TokenUsage(input_tokens=11, output_tokens=4)
    assert event.usage.known is True
    assert event.usage.total_tokens == 15
    assert event.cost_is_unknown is False


# ---------------------------------------------------------------------------
# The four refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("protocol", list(Protocol))
def test_a_two_hundred_carrying_a_provider_error_is_not_a_success(
    protocol: Protocol,
) -> None:
    """The case a status-only reader gets wrong.

    All three families can answer 200 with an error member. Reporting that as
    an answer would show the user an empty reply and a green state at the
    same time.
    """
    body = json.dumps(
        {"error": {"type": "invalid_request_error", "message": "TEST ONLY"}}
    ).encode()

    event = parse_response(protocol, _raw(200, body, protocol), model=OBSERVED_MODEL_ID)

    assert event.succeeded is False
    assert event.failure is not None
    assert event.failure.kind is FailureKind.PROVIDER_ERROR
    assert event.failure.http_status == 200
    assert event.finish is FinishReason.PROVIDER_ERROR


@pytest.mark.parametrize("protocol", list(Protocol))
def test_a_body_with_no_usage_is_unknown_and_never_zero(protocol: Protocol) -> None:
    """A fabricated zero is the one figure a spend display always believes."""
    document = {
        Protocol.RESPONSES: {"status": "completed", "output_text": "merhaba"},
        Protocol.MESSAGES: {
            "content": [{"type": "text", "text": "merhaba"}],
            "stop_reason": "end_turn",
        },
        Protocol.CHAT_COMPLETIONS: {
            "choices": [
                {"message": {"role": "assistant", "content": "merhaba"},
                 "finish_reason": "stop"}
            ]
        },
    }[protocol]

    event = parse_response(
        protocol, _raw(200, json.dumps(document).encode(), protocol),
        model=OBSERVED_MODEL_ID,
    )

    assert event.succeeded is True
    assert event.usage.known is False
    assert event.usage.input_tokens is None
    assert event.usage.output_tokens is None
    assert event.usage.total_tokens is None
    assert event.cost_is_unknown is True


def test_a_boolean_is_not_accepted_as_a_token_count() -> None:
    """``bool`` is an ``int`` in Python, and ``True`` is not one token."""
    document = dict(CHAT_COMPLETIONS_BODY)
    document["usage"] = {"prompt_tokens": True, "completion_tokens": -3}

    event = parse_response(
        Protocol.CHAT_COMPLETIONS,
        _raw(200, json.dumps(document).encode(), Protocol.CHAT_COMPLETIONS),
        model=OBSERVED_MODEL_ID,
    )

    assert event.usage.input_tokens is None
    assert event.usage.output_tokens is None


@pytest.mark.parametrize("protocol", list(Protocol))
def test_an_unrecognised_shape_is_malformed_and_not_an_empty_answer(
    protocol: Protocol,
) -> None:
    """"We could not read it" and "it said nothing" are different sentences."""
    event = parse_response(
        protocol, _raw(200, b'{"unexpected": true}', protocol), model=OBSERVED_MODEL_ID
    )

    assert event.succeeded is False
    assert event.failure is not None
    assert event.failure.kind is FailureKind.MALFORMED_BODY
    assert event.text == ""


@pytest.mark.parametrize("protocol", list(Protocol))
def test_an_empty_body_is_named_as_empty(protocol: Protocol) -> None:
    event = parse_response(protocol, _raw(200, b"   ", protocol), model=OBSERVED_MODEL_ID)

    assert event.failure is not None
    assert event.failure.kind is FailureKind.EMPTY_BODY


@pytest.mark.parametrize("protocol", list(Protocol))
def test_a_body_that_is_not_json_is_malformed(protocol: Protocol) -> None:
    event = parse_response(
        protocol, _raw(200, b"<html>gateway</html>", protocol), model=OBSERVED_MODEL_ID
    )

    assert event.failure is not None
    assert event.failure.kind is FailureKind.MALFORMED_BODY


def test_a_body_read_under_the_wrong_family_does_not_quietly_parse() -> None:
    """Choosing the wrong protocol is a visible failure, not a wrong answer.

    This is the failure mode a guessed model-to-protocol mapping would have
    produced, which is exactly why ADR-0005 5 refuses to guess one: the
    request goes to the wrong family and comes back looking like the user's
    problem.
    """
    for protocol, document in FAMILY_FIXTURES:
        for other, _ in FAMILY_FIXTURES:
            if other is protocol:
                continue
            event = parse_response(
                other, _raw(200, body_bytes(document), other), model=OBSERVED_MODEL_ID
            )
            if event.succeeded:
                # The two OpenAI-shaped families are genuinely distinct in the
                # fields they carry; a fixture that parsed under both would
                # mean this test proves nothing, so it fails loudly.
                pytest.fail(
                    f"{protocol.value} fixture parsed as {other.value}"
                )


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status_code", "kind"),
    [
        (401, FailureKind.INVALID_CREDENTIAL),
        (403, FailureKind.FORBIDDEN_MODEL),
        (404, FailureKind.MODEL_NOT_FOUND),
        (429, FailureKind.QUOTA_EXHAUSTED),
        (500, FailureKind.SERVER_ERROR),
        (503, FailureKind.SERVER_ERROR),
        (418, FailureKind.PROVIDER_ERROR),
    ],
)
def test_every_named_status_maps_to_the_failure_it_actually_means(
    status_code: int, kind: FailureKind
) -> None:
    body = json.dumps({"error": {"message": "TEST ONLY"}}).encode()
    event = parse_response(
        Protocol.CHAT_COMPLETIONS,
        _raw(status_code, body, Protocol.CHAT_COMPLETIONS),
        model=OBSERVED_MODEL_ID,
    )

    assert event.failure is not None
    assert event.failure.kind is kind
    assert event.failure.http_status == status_code
    assert event.succeeded is False


def test_a_failure_carries_the_providers_words_as_a_quotation_not_as_our_claim() -> None:
    """Imported text is data (SI-199's rule), attributed and bounded."""
    body = json.dumps({"error": {"message": "TEST ONLY upstream sentence"}}).encode()
    event = parse_response(
        Protocol.MESSAGES, _raw(403, body, Protocol.MESSAGES), model=OBSERVED_MODEL_ID
    )

    assert event.failure is not None
    assert "Saglayici yaniti:" in event.failure.detail
    assert "TEST ONLY upstream sentence" in event.failure.detail


# ---------------------------------------------------------------------------
# Finish reasons
# ---------------------------------------------------------------------------


def test_an_unrecognised_finish_reason_stays_unknown_rather_than_completed() -> None:
    """Silence about why a model stopped is not a completed answer."""
    document = dict(CHAT_COMPLETIONS_BODY)
    document["choices"] = [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "merhaba"},
            "finish_reason": "something_new",
        }
    ]

    event = parse_response(
        Protocol.CHAT_COMPLETIONS,
        _raw(200, json.dumps(document).encode(), Protocol.CHAT_COMPLETIONS),
        model=OBSERVED_MODEL_ID,
    )

    assert event.finish is FinishReason.UNKNOWN
    # Unknown is still not a failure: the text arrived.
    assert event.succeeded is True


def test_a_truncated_answer_is_reported_as_a_length_stop() -> None:
    for protocol, document, mutation in (
        (
            Protocol.RESPONSES,
            RESPONSES_BODY,
            {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
        ),
        (Protocol.MESSAGES, MESSAGES_BODY, {"stop_reason": "max_tokens"}),
        (
            Protocol.CHAT_COMPLETIONS,
            CHAT_COMPLETIONS_BODY,
            {
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "merhaba"},
                        "finish_reason": "length",
                    }
                ]
            },
        ),
    ):
        mutated = {**document, **mutation}
        event = parse_response(
            protocol,
            _raw(200, json.dumps(mutated).encode(), protocol),
            model=OBSERVED_MODEL_ID,
        )
        assert event.finish is FinishReason.LENGTH, protocol


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("protocol", list(Protocol))
def test_a_request_asks_for_non_streaming_explicitly(protocol: Protocol) -> None:
    """Not relying on a default we did not verify."""
    document = json.loads(
        build_request(protocol, model=OBSERVED_MODEL_ID, prompt="merhaba")
    )

    assert document["stream"] is False
    assert document["model"] == OBSERVED_MODEL_ID


@pytest.mark.parametrize("protocol", list(Protocol))
def test_the_provider_prefix_is_stripped_before_the_wire(protocol: Protocol) -> None:
    """``opencode-go/<id>`` is a configuration prefix, not a wire identifier.

    Sending the prefixed form would be a request for a model that does not
    exist, and the 404 would read like the catalog was wrong (ADR-0005 1).
    """
    prefixed = f"{PROVIDER_PREFIX}{OBSERVED_MODEL_ID}"
    assert wire_model_id(prefixed) == OBSERVED_MODEL_ID

    document = json.loads(build_request(protocol, model=prefixed, prompt="merhaba"))
    assert document["model"] == OBSERVED_MODEL_ID
    assert PROVIDER_PREFIX not in json.dumps(document)


@pytest.mark.parametrize("protocol", list(Protocol))
def test_a_request_carries_a_bounded_output_ceiling(protocol: Protocol) -> None:
    document = json.loads(
        build_request(protocol, model=OBSERVED_MODEL_ID, prompt="merhaba")
    )
    bound = document.get("max_output_tokens", document.get("max_tokens"))
    assert bound == DEFAULT_MAX_OUTPUT_TOKENS


@pytest.mark.parametrize("protocol", list(Protocol))
def test_each_protocol_goes_to_its_own_registered_address(protocol: Protocol) -> None:
    """The address comes from the closed registry, never from a body."""
    transport, recorder = recording_transport(
        lambda _: httpx.Response(200, content=b"{}")
    )
    client = OpenCodeClient(transport=transport, sleep=lambda _: None)
    client.post_completion(protocol, b"{}", api_key=TEST_ONLY_CREDENTIAL)

    assert str(recorder.last.url) == protocol_endpoint(protocol).url
    assert recorder.last.method == "POST"


def test_the_three_protocol_addresses_are_distinct_and_registered() -> None:
    urls = {protocol_endpoint(protocol).url for protocol in Protocol}
    assert len(urls) == 3
    assert protocol_endpoint(Protocol.CHAT_COMPLETIONS).id is EndpointId.CHAT_COMPLETIONS


# ---------------------------------------------------------------------------
# What is deliberately not built
# ---------------------------------------------------------------------------


def test_streaming_is_absent_and_says_so_and_tool_calls_were_measured() -> None:
    """One format deferred, one measured, and the sentence says which is which.

    This test said "both are absent" and asserted two ``False``s. The claim
    was true when it was written and half of it stopped being true when
    ADR-0012 measured the tool-call contract against the account holder's own
    key. It is rewritten rather than relaxed, and the half that did **not**
    change is asserted harder than before: streaming is still ``False``,
    still named in the deferral sentence, and nothing measured it.

    The measured half now has to carry its provenance. A ``True`` with no
    sentence saying what was measured and how far the measurement reaches
    would be exactly the unsourced claim ADR-0005 1.2 refuses - which is what
    the old ``False`` was protecting against in the first place.
    """
    from station_api.opencode.planner import TOOL_CALL_PROVENANCE

    assert STREAMING_SUPPORTED is False
    assert "streaming" in DEFERRAL_SENTENCE.lower()

    assert TOOL_CALLS_SUPPORTED is True
    assert "arac cagrisi" in DEFERRAL_SENTENCE.lower()
    assert "olculdu" in DEFERRAL_SENTENCE.lower()
    # The provenance names the endpoint and the observable that was read.
    assert "chat/completions" in TOOL_CALL_PROVENANCE
    assert "tool_calls" in TOOL_CALL_PROVENANCE
    assert not set(TOOL_CALL_PROVENANCE) & set("çğıöşüÇĞİÖŞÜ")


def test_the_shape_provenance_is_stated_rather_than_implied() -> None:
    """The bodies are the upstream families', not a published OpenCode contract."""
    assert "yayimlanmis" in SHAPE_PROVENANCE
    assert "fixture" in SHAPE_PROVENANCE


# ---------------------------------------------------------------------------
# The closed table, checked against the page it was transcribed from
#
# An earlier revision of the registry asserted that the documentation
# "never says which family a given model belongs to", and the test that stood
# here pinned that claim by requiring every row to be unselectable. The claim
# was false: the "Endpoints" table prints ``Model | Model ID | Endpoint |
# AI SDK Package`` and gives an endpoint on all 27 rows.
#
# The failure is worth naming, because a test can pin a falsehood as firmly as
# a truth and this one read like caution while it disabled the feature: with
# no row documented, ``selectable_model_ids()`` was empty and no model could
# be chosen at all. So the tests below are deliberately *specific* - counts
# per family, and named rows - rather than a shape check any table would
# satisfy.
# ---------------------------------------------------------------------------

#: The published table, family by family, as a reviewer can diff it against
#: the page. Written out here and in the registry independently on purpose: a
#: transcription checked against itself checks nothing.
DOCUMENTED_ROWS: dict[Protocol, frozenset[str]] = {
    Protocol.RESPONSES: frozenset(
        {
            "grok-4.6",
            "gpt-5.6-luna",
            "muse-spark-1.3-contributor",
            "muse-spark-1.2-contributor",
        }
    ),
    Protocol.MESSAGES: frozenset(
        {
            "minimax-m3",
            "minimax-m2.7",
            "minimax-m2.5",
            "qwen3.8-max",
            "qwen3.8-flash",
            "qwen3.7-max",
            "qwen3.7-plus",
            "qwen3.6-plus",
        }
    ),
    Protocol.CHAT_COMPLETIONS: frozenset(
        {
            "glm-5.3-flash",
            "glm-5.3",
            "glm-5.2",
            "glm-5.1",
            "kimi-k3",
            "kimi-k2.7-code",
            "kimi-k2.6",
            "longcat-2.0",
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-v4-flash-vision-exp",
            "mimo-v2.5",
            "mimo-v2.5-pro",
            "hy4-preview",
            "hy3",
        }
    ),
}


def test_the_closed_table_transcribes_all_twenty_seven_published_rows() -> None:
    """Every row, on the family the page prints for it - and no extra row.

    Compared as whole sets rather than by count, so a swapped pair of ids
    fails here and not in production against a provider error that would read
    like the user's mistake.
    """
    transcribed: dict[Protocol, set[str]] = {protocol: set() for protocol in Protocol}
    for mapping in MODEL_MAPPINGS:
        transcribed[mapping.protocol].add(mapping.wire_id)

    assert {p: frozenset(ids) for p, ids in transcribed.items()} == DOCUMENTED_ROWS
    assert len(MODEL_MAPPINGS) == 27


def test_every_transcribed_row_is_marked_documented_and_selectable() -> None:
    """A transcription is documented by construction; nothing here is a guess."""
    assert MODEL_MAPPINGS
    for mapping in MODEL_MAPPINGS:
        assert mapping.protocol_verification is MappingVerification.DOCUMENTED
        assert mapping.selectable is True


def test_the_table_has_no_duplicate_identifiers() -> None:
    """Two rows for one id would make the resolved protocol order-dependent."""
    ids = [mapping.wire_id for mapping in MODEL_MAPPINGS]
    assert len(ids) == len(set(ids))


def test_this_build_can_actually_address_a_model() -> None:
    """The regression that mattered.

    ``selectable_model_ids()`` returning the empty set is what turned this
    connection into a box that stores a key and can never use it. Asserted as
    the exact set, so "non-empty" cannot be satisfied by one accidental row.
    """
    selectable = selectable_model_ids()

    assert selectable == frozenset().union(*DOCUMENTED_ROWS.values())
    assert len(selectable) == 27


def test_grok_is_filed_under_responses_and_not_chat_completions() -> None:
    """The specific row the correction turned up, pinned by name.

    The earlier table had ``grok-4.6`` on ``chat/completions``; the page says
    ``responses``. A wrong family is worse than a missing one - it produces a
    provider error at call time that looks like a bad request from the user.
    """
    mapping = find_mapping("grok-4.6")

    assert mapping is not None
    assert mapping.protocol is Protocol.RESPONSES
    assert protocol_endpoint(mapping.protocol).id is EndpointId.RESPONSES


def test_every_row_carries_its_own_privacy_term_with_a_source_and_a_date() -> None:
    """Per row, not one blanket sentence.

    The Privacy table gives a term per model and five of them are not the
    common case, so a single sentence covering the table would have been
    wrong for those five. The provenance rides along so a stale claim is
    visibly stale rather than silently authoritative.
    """
    for mapping in MODEL_MAPPINGS:
        assert mapping.retention
        assert mapping.retention != "unknown"
        assert mapping.privacy_source
        assert mapping.privacy_read_on == PRIVACY_TABLE_READ_ON
        assert mapping.note


def test_the_two_thirty_day_rows_are_not_described_as_zero_retention() -> None:
    for wire_id in ("grok-4.6", "gpt-5.6-luna"):
        mapping = find_mapping(wire_id)
        assert mapping is not None
        assert mapping.retention == RETENTION_THIRTY
        assert mapping.training_use is TrainingUse.NO


def test_the_muse_spark_rows_are_training_models_and_need_acknowledgement() -> None:
    """Documented, therefore selectable - and still not selectable by default.

    Two separate properties. Collapsing them would either hide a training
    model behind "unverified" - a lie about why - or let it be chosen with no
    acknowledgement at all.
    """
    for wire_id in ("muse-spark-1.3-contributor", "muse-spark-1.2-contributor"):
        mapping = find_mapping(wire_id)
        assert mapping is not None
        assert mapping.training_use is TrainingUse.YES
        assert mapping.retention == RETENTION_NOT_ZDR
        assert mapping.selectable is True
        assert mapping.requires_training_acknowledgement is True


def test_no_other_documented_row_asks_for_a_training_acknowledgement() -> None:
    """The gate is exactly the two rows the table names, not a mood."""
    gated = {
        mapping.wire_id
        for mapping in MODEL_MAPPINGS
        if mapping.requires_training_acknowledgement
    }
    assert gated == {"muse-spark-1.3-contributor", "muse-spark-1.2-contributor"}


def test_the_deepseek_footnote_marker_survives_transcription() -> None:
    """``0 days*`` is not ``0 days``.

    The asterisk points at a footnote that was not read. Dropping it would
    turn a qualified term into an unqualified one, which is the exact
    over-claim this table exists to avoid.
    """
    for wire_id in (
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
    ):
        mapping = find_mapping(wire_id)
        assert mapping is not None
        assert mapping.retention == RETENTION_ZERO_FOOTNOTED
        assert mapping.retention.endswith("*")


def test_the_table_says_where_it_was_read_and_when_the_page_was_updated() -> None:
    """Two dates, because they answer different questions.

    A page read today can be a page that stopped being updated a year ago,
    and only one of the two dates would say so.
    """
    assert "Endpoints" in ENDPOINTS_TABLE_SOURCE
    assert "opencode.ai/docs/go" in ENDPOINTS_TABLE_SOURCE
    assert PRIVACY_TABLE_READ_ON == "2026-09-04"
    assert DOC_LAST_UPDATED == "2026-09-03"


def test_every_documented_protocol_resolves_to_a_registered_address() -> None:
    """The closed loop: table -> protocol -> one of four fixed URLs."""
    for mapping in MODEL_MAPPINGS:
        endpoint = protocol_endpoint(mapping.protocol)
        assert endpoint.url.startswith("https://opencode.ai/zen/go/v1/")
        assert endpoint.requires_key is True


def test_an_identifier_outside_the_table_resolves_to_nothing() -> None:
    """No fallback family. A miss is a miss, not a default."""
    assert find_mapping("a-model-that-does-not-exist") is None
    assert find_mapping("") is None


def test_the_authentication_header_is_still_not_verified() -> None:
    """Correcting the protocol table did not verify the auth header.

    Two different absences, and only one of them was resolved. ADR-0005 3
    has not moved: the header name was never published, so the caveat in the
    module's own docstring stays and this test is what keeps it there.
    """
    from station_api.opencode import registry

    doc = registry.__doc__ or ""
    assert "the name of the authentication header" in doc
    assert "ADR-0005 3" in doc
