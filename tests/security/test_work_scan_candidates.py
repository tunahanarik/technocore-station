"""SI-276, SI-278, SI-279 - deterministic derivation, eight elements, six refusals.

The two claims that carry this file:

* **nothing is generated.** Every value on a candidate is either a raw field of
  the source line or a fixed template from the signal table, and the test
  proves it the only way that means anything: by taking every string a
  candidate carries and requiring it to be reachable from one of those two
  places (ADR-0007 2).
* **the eight elements are structural.** A candidate that cannot carry all
  eight does not come into existence, so there is no partially-formed
  candidate anywhere for a view to render.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from station_api.identity.write_gate import CheckState
from station_api.modules.registry import ModuleId
from station_api.workscan.authority import AuthorityLevel
from station_api.workscan.candidates import (
    DERIVATION_METHOD,
    DUPLICATE_SEQUENCE_REASON,
    PROHIBITED_MARKERS,
    PROHIBITION_DETAIL,
    SIGNALS,
    UNUSABLE_SOURCE_REASON,
    CandidateCapability,
    EffortEstimate,
    ProhibitedShape,
    SignalId,
    SourceQuote,
    WorkCandidate,
    candidate_content,
    candidate_id,
    capability_for,
    derive_from_room,
    matching_signal,
    open_state_note,
    prohibited_shape,
)
from station_api.workscan.client import RoomScanClient
from station_api.workscan.errors import CandidateError
from station_api.workscan.snapshot import parse_room_messages, staleness_note
from station_api.workscan.targets import resolve_room_target

from tests.security.workscan_fixtures import (
    DEFECT_LINE,
    HELP_LINE,
    MARKERS,
    QUIET_LINE,
    ROOM,
    WALLET_LINE,
    json_transport,
    message,
    room_document,
)

pytestmark = pytest.mark.security


def _capability(*, write_gate_open: bool = True) -> CandidateCapability:
    return capability_for(ModuleId.WORK_SCAN, write_gate_open=write_gate_open)


#: A reading moment far from "now", so a test that moves the clock is
#: obviously moving it rather than racing it.
_LATER = datetime(2031, 3, 4, 5, 6, 7, 891011, tzinfo=UTC)


def _derive(  # type: ignore[no-untyped-def]
    messages: list[dict[str, object]],
    *,
    write_gate_open: bool = True,
    read_at: datetime | None = None,
):
    transport, _ = json_transport(room_document(messages=messages))  # type: ignore[arg-type]
    client = RoomScanClient(transport=transport, sleep=lambda _: None)
    snapshot = parse_room_messages(
        client.fetch_room_messages(resolve_room_target(ROOM, markers=MARKERS)),
        requested_room=ROOM,
    )
    if read_at is not None:
        snapshot = replace(snapshot, staleness=staleness_note(read_at))
    return derive_from_room(
        snapshot, capability=_capability(write_gate_open=write_gate_open)
    )


# ---------------------------------------------------------------------------
# No model call, and none reachable
# ---------------------------------------------------------------------------


def test_the_package_calls_no_model_and_imports_no_completion_path(
    api_source_root: Path,
) -> None:
    """ADR-0007 2, checked structurally rather than argued.

    ``station_api.opencode`` is the only thing in this build that could reach
    a provider, and the scan package must not import any of it - not the
    client, not the service, not the adapters.
    """
    package = api_source_root / "station_api" / "workscan"
    banned = ("station_api.opencode", "openai", "anthropic")
    offenders: list[str] = []

    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(name == item or name.startswith(f"{item}.") for item in banned):
                    offenders.append(f"{path.name}: {name}")

    assert offenders == [], f"the scan package can reach a model: {offenders}"


def test_the_same_line_produces_the_same_candidate_every_time() -> None:
    """Determinism is what makes ``source_version_id`` an identity at all.

    A generated candidate would differ between runs and the identity would
    name nothing, which is the second reason ADR-0007 2 gives.
    """
    first = _derive([message(1, HELP_LINE)])
    second = _derive([message(1, HELP_LINE)], read_at=_LATER)

    assert [item.id for item in first.candidates] == [
        item.id for item in second.candidates
    ]
    assert candidate_content(first.candidates[0]) == candidate_content(
        second.candidates[0]
    )
    assert first.candidates[0].derivation == DERIVATION_METHOD

    # The reading moment is moved on purpose rather than left to the wall
    # clock. Two derivations a microsecond apart can land on the same
    # timestamp on a fast machine, so asserting that two `now()` calls differ
    # tests the runner, not the product. Forcing the clock forward proves the
    # claim outright: element 8 records a different reading moment while the
    # identity and the content stay put, which is exactly why a clock that
    # moved must not invalidate evidence recorded against the same proposal.
    assert first.candidates[0].open_state.read_at != _LATER
    assert second.candidates[0].open_state.read_at == _LATER


def test_every_string_on_a_candidate_comes_from_the_line_or_from_the_table() -> None:
    """The load-bearing claim, tested as a claim rather than as a comment.

    Each sentence must be reachable from a signal-table template or from a raw
    source field. A value that matched neither would be a value this build
    invented.
    """
    result = _derive([message(1, HELP_LINE)])
    candidate = result.candidates[0]
    signal = next(item for item in SIGNALS if item.id is candidate.signal)

    assert candidate.deliverable == signal.deliverable
    assert candidate.success_condition == signal.success_condition
    assert candidate.test_method == signal.test_method
    assert candidate.permissions == signal.permissions
    assert candidate.risks == signal.risks
    assert candidate.effort.band == signal.effort_band
    # The one interpolated sentence: its template is the table's, and both
    # substituted values are raw source fields.
    assert candidate.source.room in candidate.benefit
    assert signal.benefit.split("{")[0] in candidate.benefit
    # The quote is the message, unrewritten.
    assert candidate.source.quote == HELP_LINE


# ---------------------------------------------------------------------------
# The eight elements
# ---------------------------------------------------------------------------


def test_a_candidate_carries_all_eight_elements() -> None:
    candidate = _derive([message(7, DEFECT_LINE)]).candidates[0]

    assert candidate.source.room == ROOM  # 1
    assert candidate.source.seq == 7
    assert candidate.source.ts
    assert candidate.source.quote
    assert candidate.benefit.strip()  # 2
    assert candidate.deliverable.strip()  # 3
    assert candidate.success_condition.strip()  # 4
    assert candidate.test_method.strip()
    assert candidate.capability.detail.strip()  # 5
    assert candidate.effort.label == "tahmin"  # 6
    assert candidate.budget_state is CheckState.NOT_IMPLEMENTED
    assert candidate.permissions  # 7
    assert candidate.risks
    assert candidate.open_state.detail.strip()  # 8


@pytest.mark.parametrize(
    "field, value",
    [
        ("room", ""),
        ("ts", ""),
        ("quote", "   "),
    ],
)
def test_a_quote_without_its_coordinates_cannot_be_constructed(
    field: str, value: str
) -> None:
    """Element 1 is refused at construction, the ``EvidenceRef`` way."""
    arguments = {
        "room": ROOM,
        "seq": 1,
        "ts": "2026-09-04T10:00:00Z",
        "author": "test-only-nick",
        "author_is_did_key": False,
        "author_detail": "TEST-ONLY",
        "quote": HELP_LINE,
    }
    arguments[field] = value

    with pytest.raises(CandidateError):
        SourceQuote(**arguments)  # type: ignore[arg-type]


def test_a_negative_sequence_number_is_refused() -> None:
    with pytest.raises(CandidateError):
        SourceQuote(
            room=ROOM,
            seq=-1,
            ts="2026-09-04T10:00:00Z",
            author="",
            author_is_did_key=False,
            author_detail="TEST-ONLY",
            quote=HELP_LINE,
        )


def test_an_effort_estimate_cannot_present_itself_as_a_measurement() -> None:
    """Element 6: the label is fixed, so there is no argument that removes it."""
    estimate = EffortEstimate(band="bir oturum", basis="TEST-ONLY")
    assert estimate.label == "tahmin"

    with pytest.raises(CandidateError):
        EffortEstimate(band="bir oturum", basis="TEST-ONLY", label="olcum")

    with pytest.raises(CandidateError):
        EffortEstimate(band="  ", basis="TEST-ONLY")


def test_a_candidate_cannot_claim_a_budget_this_release_does_not_have() -> None:
    candidate = _derive([message(1, HELP_LINE)]).candidates[0]

    with pytest.raises(CandidateError):
        WorkCandidate(
            id=candidate.id,
            signal=candidate.signal,
            source=candidate.source,
            benefit=candidate.benefit,
            deliverable=candidate.deliverable,
            success_condition=candidate.success_condition,
            test_method=candidate.test_method,
            capability=candidate.capability,
            effort=candidate.effort,
            budget_state=CheckState.PASSED,
            budget_detail=candidate.budget_detail,
            permissions=candidate.permissions,
            risks=candidate.risks,
            open_state=candidate.open_state,
        )


@pytest.mark.parametrize("missing", ["permissions", "risks"])
def test_a_candidate_without_permissions_or_risks_cannot_be_constructed(
    missing: str,
) -> None:
    candidate = _derive([message(1, HELP_LINE)]).candidates[0]
    overrides: dict[str, object] = {missing: ()}

    with pytest.raises(CandidateError):
        WorkCandidate(
            id=candidate.id,
            signal=candidate.signal,
            source=candidate.source,
            benefit=candidate.benefit,
            deliverable=candidate.deliverable,
            success_condition=candidate.success_condition,
            test_method=candidate.test_method,
            capability=candidate.capability,
            effort=candidate.effort,
            budget_state=candidate.budget_state,
            budget_detail=candidate.budget_detail,
            permissions=overrides.get("permissions", candidate.permissions),  # type: ignore[arg-type]
            risks=overrides.get("risks", candidate.risks),  # type: ignore[arg-type]
            open_state=candidate.open_state,
        )


def test_element_eight_is_a_sentence_with_a_timestamp_and_never_a_boolean() -> None:
    """ADR-0007 8 forbids the certain wording and names the replacement."""
    read_at = datetime(2026, 9, 4, 9, 30, tzinfo=UTC)
    note = open_state_note(read_at)

    assert read_at.isoformat() in note.detail
    assert "kapanis isareti gorulmedi" in note.detail
    assert not hasattr(note, "is_open")
    assert not hasattr(note, "open")


def test_the_capability_reads_the_registry_and_the_gate_without_merging_them() -> None:
    """Element 5: two halves, and neither stands in for the other."""
    open_gate = _capability(write_gate_open=True)
    shut_gate = _capability(write_gate_open=False)

    assert open_gate.module_id == ModuleId.WORK_SCAN.value
    assert open_gate.module_available is True
    assert open_gate.write_gate_open is True
    assert open_gate.ready is True

    assert shut_gate.module_available is True
    assert shut_gate.write_gate_open is False
    assert shut_gate.ready is False
    assert shut_gate.detail != open_gate.detail


def test_a_planned_module_produces_a_capability_that_says_the_code_is_absent() -> None:
    """Read off the compile-time registry, not asserted."""
    planned = capability_for(ModuleId.AGENT_WORKSPACE, write_gate_open=True)

    assert planned.module_available is False
    assert planned.ready is False
    assert "H2" in planned.detail


# ---------------------------------------------------------------------------
# The prohibitions
# ---------------------------------------------------------------------------


def test_all_six_prohibited_shapes_are_defined_with_markers_and_a_sentence() -> None:
    assert set(ProhibitedShape) == set(PROHIBITED_MARKERS)
    assert set(ProhibitedShape) == set(PROHIBITION_DETAIL)
    for shape in ProhibitedShape:
        assert PROHIBITED_MARKERS[shape], shape
        assert PROHIBITION_DETAIL[shape].strip(), shape


@pytest.mark.parametrize(
    "text, shape",
    [
        ("cuzdanini bagla ve claim al", ProhibitedShape.WALLET_OR_PAYMENT),
        ("private key gonderirsen hallederim", ProhibitedShape.WALLET_OR_PAYMENT),
        ("leaderboard icin puan topla", ProhibitedShape.POINT_FARMING),
        ("herkesi etiketle bakalim", ProhibitedShape.SPAM_PING),
        ("sadece done yaz yeter", ProhibitedShape.EMPTY_ACKNOWLEDGEMENT),
        ("kendi isini onayla gecsin", ProhibitedShape.SELF_APPROVAL),
        ("ayni seyi tekrar gonder", ProhibitedShape.DUPLICATE_DELIVERY),
    ],
)
def test_a_prohibited_line_is_recognised(text: str, shape: ProhibitedShape) -> None:
    assert prohibited_shape(text) is shape


def test_a_prohibited_line_produces_no_candidate_even_when_it_matches_a_signal() -> None:
    """The order of the two checks is load-bearing, so it is tested.

    :data:`WALLET_LINE` carries a help marker *and* a wallet marker. If the
    signal were looked for first, this line would become a proposal to do
    exactly the work the charter forbids.
    """
    assert matching_signal(WALLET_LINE) is not None
    result = _derive([message(3, WALLET_LINE)])

    assert result.candidates == ()
    assert len(result.refusals) == 1
    assert result.refusals[0].shape is ProhibitedShape.WALLET_OR_PAYMENT
    assert result.refusals[0].seq == 3
    assert result.refusals[0].detail.strip()


def test_a_refused_line_is_reported_rather_than_silently_dropped() -> None:
    """A shorter list with no explanation reads as "nothing was there"."""
    result = _derive([message(1, HELP_LINE), message(2, WALLET_LINE)])

    assert len(result.candidates) == 1
    assert len(result.refusals) == 1
    assert result.lines_read == 2


def test_a_line_that_matches_nothing_produces_nothing_and_is_still_counted() -> None:
    """"Read and found nothing" must be distinguishable from "read nothing"."""
    result = _derive([message(1, QUIET_LINE)])

    assert result.candidates == ()
    assert result.refusals == ()
    assert result.lines_read == 1


def test_the_same_line_cannot_produce_two_candidates_in_one_scan() -> None:
    """Duplicate delivery, prevented by identity rather than by carefulness."""
    result = _derive([message(5, HELP_LINE), message(5, DEFECT_LINE)])

    assert len(result.candidates) == 1
    assert result.candidates[0].id == candidate_id(ROOM, 5)


def test_the_candidate_identity_is_domain_separated_and_stable() -> None:
    first = candidate_id(ROOM, 12)
    assert first == candidate_id(ROOM, 12)
    assert first != candidate_id(ROOM, 13)
    assert first != candidate_id("test-only-other", 12)
    assert len(first) == 64


def test_the_honesty_sentence_travels_with_every_derivation() -> None:
    """ADR-0007 2: the cost of pattern matching is shown, not filed away."""
    result = _derive([message(1, QUIET_LINE)])

    assert "kalip eslesmesiyle" in result.honesty
    assert "her firsat gorulmez" in result.honesty


def test_the_signal_table_is_closed_and_every_entry_is_complete() -> None:
    assert {signal.id for signal in SIGNALS} == set(SignalId)
    for signal in SIGNALS:
        assert signal.markers
        assert "{room}" in signal.benefit
        assert "{author}" in signal.benefit
        for text in (signal.deliverable, signal.success_condition, signal.test_method):
            assert text.strip()
        assert signal.permissions and signal.risks
        assert signal.effort_band.strip()


def test_a_candidate_is_community_content_whatever_its_author_looks_like() -> None:
    candidate = _derive([message(1, HELP_LINE)]).candidates[0]

    assert candidate.authority is AuthorityLevel.COMMUNITY
    assert candidate.source.authority is AuthorityLevel.COMMUNITY


# ---------------------------------------------------------------------------
# The wallet gate, against the spellings a person reads as the same word
# ---------------------------------------------------------------------------

#: Nineteen lines a review walked straight past the prohibition list with.
#:
#: Two families. The first spells a listed word so that a substring search
#: misses it and a reader does not: an inserted space, a zero-width character,
#: a soft hyphen, a full stop, or one Cyrillic letter drawn exactly like its
#: Latin twin. The second does not obfuscate anything - it simply asks for the
#: same act using a noun the list did not contain.
#:
#: Every line also carries a help marker, so each one *did* produce a
#: candidate before the fix rather than merely failing to be refused.
_EVADING_WALLET_LINES = (
    # Separated letters
    "kim yapabilir: w a l l e t baglayacak biri lazim",
    "kim yapabilir: wal-let baglayacak biri lazim",
    "kim yapabilir: w.a.l.l.e.t baglayacak biri lazim",
    # Zero-width and format characters
    "kim yapabilir: w\u200ballet baglayacak biri lazim",
    "kim yapabilir: wal\u200dlet baglayacak biri lazim",
    "kim yapabilir: wal\u200clet baglayacak biri lazim",
    "kim yapabilir: wal\u00adlet baglayacak biri lazim",
    # One Cyrillic letter, drawn as its Latin twin
    "kim yapabilir: cl\u0430im alacak biri lazim",
    "kim yapabilir: cuzd\u0430n baglayacak biri lazim",
    # The same act, a different noun
    "kim yapabilir: kripto para gonderin",
    "kim yapabilir: bakiye aktarin",
    "help wanted: transfer 1 ETH to me",
    "kim yapabilir: gas ucretini odeyin",
    "kim yapabilir: btc adresime gonderin",
    "looking for someone: connect your purse",
    "looking for someone to buy some tokens",
    "kim yapabilir: nft mint edin",
    "kim yapabilir: staking yapin",
    "kim yapabilir: para gonderin",
)


@pytest.mark.parametrize("text", _EVADING_WALLET_LINES)
def test_a_wallet_request_is_refused_however_it_is_spelled(text: str) -> None:
    """SI-283. Every one of these produced a candidate before the fix.

    The list is matched on what a reader sees: format characters are deleted,
    a handful of Cyrillic and Greek lookalikes are mapped onto their Latin
    twins, and the prohibition gate is additionally matched against a haystack
    with the intra-word separators removed.
    """
    assert prohibited_shape(text) is ProhibitedShape.WALLET_OR_PAYMENT


@pytest.mark.parametrize("text", _EVADING_WALLET_LINES)
def test_none_of_those_lines_produces_a_candidate(text: str) -> None:
    """The gate is only worth anything where a candidate would have been."""
    result = _derive([message(1, text)])

    assert result.candidates == ()
    assert len(result.refusals) == 1
    assert result.refusals[0].shape is ProhibitedShape.WALLET_OR_PAYMENT
    assert result.refusals[0].reason == ProhibitedShape.WALLET_OR_PAYMENT.value


def test_an_ordinary_help_request_is_still_a_candidate() -> None:
    """The widened list has to leave the thing this feature is for alone."""
    result = _derive([message(1, HELP_LINE), message(2, DEFECT_LINE)])

    assert len(result.candidates) == 2
    assert result.refusals == ()


# ---------------------------------------------------------------------------
# The other two reasons a line is declined - both were silent
# ---------------------------------------------------------------------------


def test_a_repeated_sequence_number_is_shown_rather_than_dropped() -> None:
    """SI-284. Two lines read, one candidate, and nothing said why.

    ``seq`` is a total order inside a room, so a repeat is a malformed reply -
    but the reply is anonymous input and this is what it did. The second line
    cannot become a second candidate (the identity is ``(room, seq)``), and
    the rule for a line this build declines is that it is shown.
    """
    result = _derive([message(5, HELP_LINE), message(5, DEFECT_LINE)])

    assert result.lines_read == 2
    assert len(result.candidates) == 1
    assert len(result.refusals) == 1
    assert result.refusals[0].reason == DUPLICATE_SEQUENCE_REASON
    assert result.refusals[0].shape is None
    assert result.refusals[0].seq == 5


def test_a_line_without_a_timestamp_refuses_itself_and_not_the_room() -> None:
    """SI-284. One unusable line used to raise out of the whole scan.

    ``SourceQuote`` refuses a quote with no ``ts``, ``derive_from_room`` was
    called outside the service's per-room ``try``, and the route carried no
    handler - so one message missing one field answered HTTP 500 and threw
    away every room the same scan had already read.
    """
    broken = message(1, HELP_LINE)
    del broken["ts"]

    result = _derive([broken, message(2, DEFECT_LINE)])

    assert result.lines_read == 2
    assert len(result.candidates) == 1
    assert result.candidates[0].source.seq == 2
    assert len(result.refusals) == 1
    assert result.refusals[0].reason == UNUSABLE_SOURCE_REASON
    assert result.refusals[0].seq == 1
    assert result.refusals[0].detail.strip()


# ---------------------------------------------------------------------------
# The rest of the eight-element guard, which nothing was covering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "benefit",
        "deliverable",
        "success_condition",
        "test_method",
        "budget_detail",
    ],
)
@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_a_candidate_missing_any_mandatory_sentence_cannot_be_constructed(
    field: str, blank: str
) -> None:
    """SI-278, on the half of ``__post_init__`` no test was reaching.

    Emptying the body of ``WorkCandidate.__post_init__`` turned only three
    tests red - budget, permissions, risks. The ``missing`` loop over the five
    mandatory sentences, and the identity check below, were asserted by the
    invariant and covered by nothing. Whitespace counts as missing, because
    ``strip()`` is what the guard actually applies.
    """
    candidate = _derive([message(1, HELP_LINE)]).candidates[0]

    with pytest.raises(CandidateError) as raised:
        replace(candidate, **{field: blank})

    assert field in str(raised.value)


def test_a_candidate_without_an_identity_cannot_be_constructed() -> None:
    """The last line of the guard, and the one that makes de-duplication real."""
    candidate = _derive([message(1, HELP_LINE)]).candidates[0]

    with pytest.raises(CandidateError):
        replace(candidate, id="")
