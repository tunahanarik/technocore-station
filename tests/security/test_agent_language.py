"""The forbidden-phrase audit, extended to cover H2's own text.

Package E built this control for the evidence layer and H1 extended it to the
work scan. Each scan is scoped to its own directory, so a new package's
wording is covered by nothing at all until it brings its own - and a rule that
does not cover the text being written is not a rule (ADR-0007 10, ADR-0008 9).

Three halves, as in the two files before this one:

* the **runtime** guard, on the sentences this package writes;
* the **static** scan, over every string literal in the package *and* in the
  route file in front of it;
* the **mutation** control: with the guard neutered, at least one test here
  has to go red. A guard nobody has watched fail is a guard nobody has tested.

What H2 adds to the registry
-----------------------------
Seven phrases, and each one names a thing this build cannot do. There is no
isolated environment and no virtual machine (ADR-0008 1); no code and no
command is executed; no test passed, because running one is the closed
capability; and nothing is approved automatically, because approval is a
person's act.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from station_api.agent import activity as activity_module
from station_api.agent import service as service_module
from station_api.agent.activity import ActivityAction, ActivityActor, ActivityOutcome
from station_api.agent.errors import ToolArgumentError
from station_api.agent.language import (
    AGENT_FORBIDDEN_PHRASES,
    FORBIDDEN_PHRASES,
    NEUTRALISED_MARK,
    PERMITTED_ALTERNATIVES,
    RUN_HONESTY_SENTENCE,
    STOP_HONESTY_SENTENCE,
    ForbiddenClaimError,
    assert_no_forbidden_claim,
    find_forbidden_phrases,
    neutralise,
)
from station_api.evidence.language import (
    FORBIDDEN_PHRASES as EVIDENCE_FORBIDDEN_PHRASES,
)
from station_api.workscan.language import (
    FORBIDDEN_PHRASES as SCAN_FORBIDDEN_PHRASES,
)

pytestmark = pytest.mark.security

#: Files the static scan skips, and why. ``language.py`` is the registry
#: itself, which writes the phrases out in full; nothing else is exempt.
_EXEMPT = frozenset({"language.py"})


def _package(api_source_root: Path) -> Path:
    return api_source_root / "station_api" / "agent"


def _scanned(api_source_root: Path) -> list[Path]:
    files = [
        path
        for path in sorted(_package(api_source_root).rglob("*.py"))
        if path.name not in _EXEMPT
    ]
    files.append(api_source_root / "station_api" / "routes" / "agent.py")
    return files


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


def test_the_registry_inherits_both_earlier_layers_rather_than_copying() -> None:
    """A phrase added in E or H1 is refused here on the same commit."""
    for phrase in EVIDENCE_FORBIDDEN_PHRASES:
        assert phrase in FORBIDDEN_PHRASES
    for phrase in SCAN_FORBIDDEN_PHRASES:
        assert phrase in FORBIDDEN_PHRASES

    assert len(FORBIDDEN_PHRASES) == len(SCAN_FORBIDDEN_PHRASES) + len(
        AGENT_FORBIDDEN_PHRASES
    )
    assert len(AGENT_FORBIDDEN_PHRASES) == len(PERMITTED_ALTERNATIVES)


def test_every_phrase_the_adr_names_is_in_the_registry() -> None:
    """The claims ADR-0008 1, 3 and 7 forbid, in the wording they would appear in."""
    for phrase in (
        "izole calisma ortami",
        "guvenli sanal makine",
        "kod calistirildi",
        "test gecti",
        "otomatik onaylandi",
    ):
        assert phrase in AGENT_FORBIDDEN_PHRASES


@pytest.mark.parametrize("phrase", AGENT_FORBIDDEN_PHRASES)
def test_a_phrase_is_caught_in_every_spelling(phrase: str) -> None:
    """Folded matching, so the Turkish and ASCII spellings are one claim.

    The dotless ``i`` is the case IMP-384 records: ``casefold`` does not map it
    onto ``i``, so a guard written in ASCII is blind to the language this
    product is written in. The spellings are generated rather than typed, so
    the test cannot share a blind spot with the rule.
    """
    for spelling in (phrase, phrase.upper(), phrase.replace("i", "ı")):
        assert find_forbidden_phrases(f"once {spelling} sonra") != ()


def test_an_innocent_sentence_passes() -> None:
    assert find_forbidden_phrases("bu calisma alaninda bir rapor uretildi") == ()
    assert find_forbidden_phrases(RUN_HONESTY_SENTENCE) == ()
    assert find_forbidden_phrases(STOP_HONESTY_SENTENCE) == ()


# ---------------------------------------------------------------------------
# The runtime half
# ---------------------------------------------------------------------------


def test_our_own_over_claim_fails_closed() -> None:
    with pytest.raises(ForbiddenClaimError):
        assert_no_forbidden_claim("Bu adimda kod calistirildi.", where="test_only")


def test_the_honesty_sentences_say_what_is_actually_true() -> None:
    """The permitted wording, pinned so a later edit cannot soften it."""
    assert "deterministik" in RUN_HONESTY_SENTENCE
    assert "uygulanmadi" in RUN_HONESTY_SENTENCE
    assert "yayima hazir sayilamaz" in RUN_HONESTY_SENTENCE
    assert "sonraki arac cagrisini engeller" in STOP_HONESTY_SENTENCE
    for sentence in (RUN_HONESTY_SENTENCE, STOP_HONESTY_SENTENCE):
        assert not set(sentence) & set("çğıöşüÇĞİÖŞÜ")


def test_user_text_carrying_a_forbidden_phrase_is_neutralised_not_refused() -> None:
    """Package E's split, applied here.

    A person who types the banned words into a file name or a plan must not be
    able to make this product refuse to show them their own run.
    """
    hostile = "merhaba, burada kod calistirildi ve test gecti"
    cleaned = neutralise(hostile)

    assert find_forbidden_phrases(cleaned) == ()
    assert NEUTRALISED_MARK in cleaned
    assert "merhaba" in cleaned


def test_neutralising_leaves_clean_text_untouched() -> None:
    assert neutralise("sade bir cumle") == "sade bir cumle"


def test_the_earlier_layers_phrases_are_neutralised_here_too() -> None:
    for hostile in ("bu bir sunucu kanitidir", "bu is hala acik"):
        assert find_forbidden_phrases(neutralise(hostile)) == ()


# ---------------------------------------------------------------------------
# The static half
# ---------------------------------------------------------------------------


def test_no_string_literal_in_the_agent_package_carries_a_forbidden_phrase(
    api_source_root: Path,
) -> None:
    """Every literal, not just the sentences we thought to check."""
    offenders: list[str] = []

    for path in _scanned(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            found = find_forbidden_phrases(node.value)
            if found:
                offenders.append(f"{path.name}:{node.lineno} {found}")

    assert offenders == [], f"forbidden phrases in source strings: {offenders}"


def test_the_static_scan_is_actually_scanning_something(
    api_source_root: Path,
) -> None:
    """Guards the guard: a scan that found no files would pass forever."""
    scanned = _scanned(api_source_root)

    assert len(scanned) >= 8, scanned
    literals = 0
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        literals += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    assert literals > 200, literals


def test_the_route_layer_is_scanned_too(api_source_root: Path) -> None:
    """The wording a user reads is assembled partly in the route.

    Scanning only the package would leave the layer closest to the screen
    outside the rule - the exact gap ADR-0007 10 was written about.
    """
    path = api_source_root / "station_api" / "routes" / "agent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders = [
        f"{path.name}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and find_forbidden_phrases(node.value)
    ]

    assert offenders == []


def test_the_scan_would_catch_a_planted_phrase(tmp_path: Path) -> None:
    """The deny side, on a throwaway tree, so the probe never ships."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        'LABEL = "Bu calisma izole calisma ortami icinde kosuldu."\n',
        encoding="utf-8",
    )

    tree = ast.parse(planted.read_text(encoding="utf-8"))
    found = [
        find_forbidden_phrases(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]

    assert any(found), "the scan cannot see a phrase it was pointed at"


# ---------------------------------------------------------------------------
# IMP-420, from the other side: the guard must not be reachable by a user
# ---------------------------------------------------------------------------


def test_a_forbidden_phrase_a_user_typed_cannot_drive_the_product_into_a_500(
    agent, task, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    """IMP-420's fix, driven - and it had no test until an independent review said so.

    The fix moved ``neutralise`` out of ``ActivityLog._clean`` (where it made
    the guard beside it a no-op) and into ``AgentService._clean``, where a
    user's text joins one of our sentences. Removing that call left the whole
    suite green, so the most important repair in the package was resting on
    nothing.

    Here is what it is load-bearing for. A plan step's **argument key** is
    user text and it is quoted back inside the refusal this product writes.
    Typing a forbidden phrase into one must produce the shown refusal the
    argument actually deserves - an unknown parameter - and never a
    ``ForbiddenClaimError`` escaping as a 500, which is the product refusing
    to speak because the user chose the wrong words.
    """
    step = ("read_run_status", {"kod calistirildi": "TEST-ONLY"})

    with pytest.raises(ToolArgumentError) as caught:
        agent.plan_run(
            task.id,
            steps=[step],
            expected_artifacts=[],
            test_condition="TEST-ONLY olcut",
        )

    assert caught.value.reason == "argument_unknown"

    # The mutation, in the same test so the first half cannot rot into
    # proving nothing: with the neutralising step gone, the user's own words
    # reach our sentence and the guard - correctly - refuses it, turning a
    # 400 the user can read into an unhandled error.
    monkeypatch.setattr(service_module, "neutralise", lambda text: text)

    with pytest.raises(ForbiddenClaimError):
        agent.plan_run(
            task.id,
            steps=[step],
            expected_artifacts=[],
            test_condition="TEST-ONLY olcut",
        )


def test_the_neutralising_step_is_on_the_services_side_of_the_boundary(
    api_source_root: Path,
) -> None:
    """Where ``neutralise`` is called, read off the syntax tree.

    ADR-0008's split has one rule with a direction: user text is neutralised
    **before** it joins our sentence, and our sentence is then checked. So
    ``service.py`` must call ``neutralise`` and ``activity.py`` must not -
    a call there would put the laundering after the guard again, which is the
    exact shape of IMP-420.
    """

    def _calls(name: str) -> int:
        path = api_source_root / "station_api" / "agent" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        return sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "neutralise"
        )

    assert _calls("service.py") >= 1, "user text stopped being neutralised"
    assert _calls("activity.py") == 0, "the laundering moved back before the guard"


# ---------------------------------------------------------------------------
# The mutation control
# ---------------------------------------------------------------------------


def test_turning_the_guard_into_a_no_op_lets_an_over_claim_be_stored(
    activity_log, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    """The control ADR-0008 9 asks for, run inside the suite.

    Unmutated, an activity row carrying one of our own forbidden sentences is
    refused before it is written. Mutated, the same string is stored - which
    is exactly the regression the guard exists to prevent, and which is what
    makes "the guard is load-bearing" a measured statement rather than a
    hopeful one.

    If the call site in ``ActivityLog.record`` were ever deleted, the first
    half of this test would fail rather than the mutation silently proving
    nothing.
    """
    over_claim = "Bu adimda kod calistirildi ve test gecti."

    with pytest.raises(ForbiddenClaimError):
        activity_log.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            detail=over_claim,
        )

    monkeypatch.setattr(
        activity_module, "assert_no_forbidden_claim", lambda text, *, where: None
    )
    stored = activity_log.record(
        action=ActivityAction.TOOL_CALLED,
        actor=ActivityActor.STATION_RUNNER,
        outcome=ActivityOutcome.OK,
        detail=over_claim,
    )

    assert find_forbidden_phrases(stored.detail) != ()


def test_turning_the_guard_into_a_no_op_lets_a_run_report_an_over_claim(
    agent, tasks, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    """The second mutation, on the runner's own wording rather than a row.

    The sentence a run reports when it starts is built by
    ``AgentService.start_run`` and checked there. With that sentence replaced
    by a forbidden one, the guard refuses the run; with the guard neutered,
    the same run reports it.

    Two **separate tasks** are used, one per half, because the refusal happens
    after the task has already moved into ``running`` - so replaying the same
    run would hit the phase check rather than the guard, and the mutation
    would appear to work for the wrong reason.
    """
    from station_api.modules.registry import ModuleId
    from station_api.tasks.sources import TaskSourceId

    def _fresh(label: bytes):  # type: ignore[no-untyped-def]
        return tasks.open_task(
            module_id=ModuleId.AGENT_WORKSPACE,
            source=TaskSourceId.OPERATOR_REQUEST,
            content=label,
            title="TEST-ONLY mutasyon",
        )

    def _plan(task_id: str) -> str:
        return agent.plan_run(
            task_id,
            steps=[("read_run_status", {})],
            expected_artifacts=[],
            test_condition="TEST-ONLY olcut",
        ).id

    monkeypatch.setattr(
        service_module,
        "RUN_HONESTY_SENTENCE",
        "Bu calisma izole calisma ortami icinde kosuldu.",
    )

    guarded = _plan(_fresh(b"TEST-ONLY-guarded").id)
    with pytest.raises(ForbiddenClaimError):
        agent.start_run(guarded)

    monkeypatch.setattr(
        service_module, "assert_no_forbidden_claim", lambda text, *, where: None
    )
    monkeypatch.setattr(
        activity_module, "assert_no_forbidden_claim", lambda text, *, where: None
    )
    mutated = _plan(_fresh(b"TEST-ONLY-mutated").id)
    agent.start_run(mutated)

    reported = [
        view.detail
        for view in agent.activity.list_events(run_id=mutated)
        if view.action is ActivityAction.RUN_STARTED
    ]

    assert reported
    assert any(find_forbidden_phrases(detail) != () for detail in reported)


def test_the_guard_is_wired_into_the_runner_and_not_only_defined(
    api_source_root: Path,
) -> None:
    """The assumption the mutations rest on, pinned where it can rot.

    A mutation is only meaningful because the code calls the guard. If those
    call sites were deleted the mutation would still "pass" while testing
    nothing, so the call sites are read off the syntax tree.
    """
    counted = 0
    for name in ("service.py", "activity.py"):
        path = api_source_root / "station_api" / "agent" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        counted += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "assert_no_forbidden_claim"
        )

    assert counted >= 5, "the agent stopped checking its own wording"


def test_the_language_module_is_the_only_exempt_file(api_source_root: Path) -> None:
    """The exemption list is one file, and it is the registry itself.

    An exemption that grew would be the quietest way to take a package's
    wording back out of the rule.
    """
    all_files = {path.name for path in _package(api_source_root).rglob("*.py")}

    assert {"language.py"} == _EXEMPT
    assert all_files >= _EXEMPT
    assert len(all_files - _EXEMPT) >= 7


def test_the_registry_file_itself_is_the_only_place_the_phrases_appear(
    api_source_root: Path,
) -> None:
    """And it is checked by hand rather than skipped silently.

    The exempt file is exempt because it *writes the phrases out*. This
    asserts that is the only reason: every forbidden phrase in it appears
    inside the registry tuple or the alternatives tuple, not in a sentence the
    product would show.
    """
    path = _package(api_source_root) / "language.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    registry_literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AnnAssign):
            for element in ast.walk(node):
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    registry_literals.add(element.value)

    for phrase in AGENT_FORBIDDEN_PHRASES:
        assert phrase in registry_literals, phrase
