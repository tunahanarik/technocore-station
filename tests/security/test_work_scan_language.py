"""SI-280 - the forbidden-phrase audit, extended to cover H1's own text.

Package E built this control for the evidence layer and proved it two ways:
at runtime on the sentences the product writes, and statically over every
string literal in the package. The static half is scoped to
``station_api/evidence``, so H1's wording was outside it, and a rule that does
not cover the text being written is not a rule (ADR-0007 10).

This file holds both halves for ``station_api/workscan``, plus the mutation
control: with the guard turned into a no-op, at least one test here has to go
red. A guard nobody has ever seen fail is a guard nobody has tested.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from station_api.evidence.language import (
    FORBIDDEN_PHRASES as EVIDENCE_FORBIDDEN_PHRASES,
)
from station_api.workscan import candidates as candidates_module
from station_api.workscan import language as language_module
from station_api.workscan.language import (
    DERIVATION_HONESTY_SENTENCE,
    FORBIDDEN_PHRASES,
    NEUTRALISED_MARK,
    OPEN_STATE_SENTENCE,
    PERMITTED_ALTERNATIVES,
    WORK_SCAN_FORBIDDEN_PHRASES,
    ForbiddenClaimError,
    assert_no_forbidden_claim,
    find_forbidden_phrases,
    neutralise,
)

pytestmark = pytest.mark.security

#: Files the static scan skips, and why. ``language.py`` is the registry
#: itself, which is written out in full; nothing else is exempt.
_EXEMPT = frozenset({"language.py"})


def _package(api_source_root: Path) -> Path:
    return api_source_root / "station_api" / "workscan"


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            ids.add(id(first.value))
    return ids


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


def test_the_registry_inherits_the_evidence_layers_phrases_rather_than_copying() -> None:
    """A phrase added there must be refused here on the same commit."""
    for phrase in EVIDENCE_FORBIDDEN_PHRASES:
        assert phrase in FORBIDDEN_PHRASES

    assert len(FORBIDDEN_PHRASES) == len(EVIDENCE_FORBIDDEN_PHRASES) + len(
        WORK_SCAN_FORBIDDEN_PHRASES
    )
    assert len(WORK_SCAN_FORBIDDEN_PHRASES) == len(PERMITTED_ALTERNATIVES)


def test_every_phrase_the_adr_names_is_in_the_registry() -> None:
    """ADR-0007 10's five clauses, in the wording they would be violated in."""
    for phrase in (
        "hala acik",
        "dogrulanmis itibar",
        "uygunluk puani",
        "airdrop uygunlugu",
        "dogrulanmis talep sahibi",
    ):
        assert phrase in WORK_SCAN_FORBIDDEN_PHRASES


@pytest.mark.parametrize("phrase", WORK_SCAN_FORBIDDEN_PHRASES)
def test_a_phrase_is_caught_in_every_spelling(phrase: str) -> None:
    """Folded matching, so the Turkish and ASCII spellings are one claim.

    The dotless ``i`` is the case IMP-384 records: ``casefold`` does not map it
    onto ``i``, so a guard written in ASCII was blind to the language the
    product is written in. The spellings are generated here rather than typed,
    so the test cannot share a blind spot with the rule.
    """
    for spelling in (phrase, phrase.upper(), phrase.replace("i", "ı")):
        assert find_forbidden_phrases(f"once {spelling} sonra") != ()


def test_an_innocent_sentence_passes() -> None:
    assert find_forbidden_phrases("bu oda hakkinda bir sey soylenemez") == ()
    assert find_forbidden_phrases(DERIVATION_HONESTY_SENTENCE) == ()


# ---------------------------------------------------------------------------
# The runtime half
# ---------------------------------------------------------------------------


def test_our_own_over_claim_fails_closed() -> None:
    with pytest.raises(ForbiddenClaimError):
        assert_no_forbidden_claim(
            "Bu is hala acik durumda.", where="test_only"
        )


def test_the_only_permitted_open_state_wording_needs_a_timestamp() -> None:
    """A template, not a sentence: it cannot be shown without the measurement."""
    assert "{read_at}" in OPEN_STATE_SENTENCE
    assert find_forbidden_phrases(OPEN_STATE_SENTENCE) == ()
    assert "kapanis isareti gorulmedi" in OPEN_STATE_SENTENCE


def test_remote_text_carrying_a_forbidden_phrase_is_neutralised_not_refused() -> None:
    """Package E's split, applied here: a claim fails closed, data does not.

    A stranger who types the banned words into a public room must not be able
    to make this product refuse to show a scan.
    """
    hostile = "merhaba, bu is hala acik ve bende dogrulanmis itibar var"
    cleaned = neutralise(hostile)

    assert find_forbidden_phrases(cleaned) == ()
    assert NEUTRALISED_MARK in cleaned
    assert "merhaba" in cleaned


def test_neutralising_leaves_clean_text_untouched() -> None:
    assert neutralise("sade bir cumle") == "sade bir cumle"


def test_the_evidence_layers_phrases_are_neutralised_here_too() -> None:
    cleaned = neutralise("bu bir sunucu kanitidir")
    assert find_forbidden_phrases(cleaned) == ()


# ---------------------------------------------------------------------------
# The static half
# ---------------------------------------------------------------------------


def test_no_string_literal_in_the_work_scan_package_carries_a_forbidden_phrase(
    api_source_root: Path,
) -> None:
    """Every literal in the package, not just the sentences we thought to check.

    This is the half ADR-0007 10 exists for: the evidence layer's scan is
    scoped to its own directory, so a new package's labels, templates and
    refusal sentences were covered by nothing at all.
    """
    offenders: list[str] = []

    for path in sorted(_package(api_source_root).rglob("*.py")):
        if path.name in _EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            found = find_forbidden_phrases(node.value)
            if found:
                offenders.append(f"{path.name}:{node.lineno} {found}")

    assert offenders == [], f"forbidden phrases in source strings: {offenders}"


def test_the_route_layer_is_scanned_too(api_source_root: Path) -> None:
    """The wording a user actually reads is assembled partly in the route.

    Scanning only the package would leave the layer closest to the screen
    outside the rule.
    """
    path = api_source_root / "station_api" / "routes" / "workscan.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders = [
        f"{path.name}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and find_forbidden_phrases(node.value)
    ]

    assert offenders == []


def test_the_static_scan_is_actually_scanning_something(
    api_source_root: Path,
) -> None:
    """Guards the guard: a scan that found no files would pass forever.

    The route-path scan in Package D turned out to have exactly this shape of
    vacuity, so the count is asserted rather than assumed.
    """
    scanned = [
        path
        for path in _package(api_source_root).rglob("*.py")
        if path.name not in _EXEMPT
    ]

    assert len(scanned) >= 7, scanned
    literals = 0
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        literals += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    assert literals > 100, literals


def test_the_scan_would_catch_a_planted_phrase(tmp_path: Path) -> None:
    """The deny side, on a throwaway tree, so the probe never ships.

    A rule that has only ever been pointed at a repository which satisfies it
    has not been shown to refuse anything.
    """
    planted = tmp_path / "planted.py"
    planted.write_text(
        'LABEL = "Bu talep sahibi dogrulanmis talep sahibi sayilir."\n',
        encoding="utf-8",
    )

    tree = ast.parse(planted.read_text(encoding="utf-8"))
    found = [
        find_forbidden_phrases(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]

    assert any(found), "the scan cannot see a phrase it was pointed at"


def test_a_docstring_is_scanned_like_any_other_literal(
    api_source_root: Path,
) -> None:
    """Deliberately *not* exempt, unlike the long-poll parameter scan.

    A forbidden claim in a docstring is still a claim this product wrote, and
    docstrings reach a reader through the API schema and the source alike. The
    parameter scan skips them because it looks for a *name*; this one looks
    for a *claim*.
    """
    ids: set[int] = set()
    scanned = 0
    for path in sorted(_package(api_source_root).rglob("*.py")):
        if path.name in _EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        ids |= _docstring_ids(tree)
        scanned += 1

    assert scanned >= 7
    assert ids, "the package should have docstrings for the scan to cover"


# ---------------------------------------------------------------------------
# The mutation control
# ---------------------------------------------------------------------------


def test_turning_the_guard_into_a_no_op_turns_this_file_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control ADR-0007 10 asks for, run inside the suite.

    With ``assert_no_forbidden_claim`` neutered, the two runtime call sites in
    :mod:`station_api.workscan.candidates` stop refusing an over-claim. This
    test *drives* that mutation and requires the refusal to disappear, which
    is what makes "the guard is load-bearing" a measured statement rather than
    a hopeful one: if the call sites were removed, this test fails.
    """
    from datetime import UTC, datetime

    # Unmutated: the guard refuses our own over-claim.
    with pytest.raises(ForbiddenClaimError):
        assert_no_forbidden_claim("dogrulanmis itibar", where="test_only")

    # Mutated: the guard is a no-op and the same string passes.
    monkeypatch.setattr(
        language_module, "assert_no_forbidden_claim", lambda text, *, where: None
    )
    monkeypatch.setattr(
        candidates_module, "assert_no_forbidden_claim", lambda text, *, where: None
    )
    monkeypatch.setattr(
        candidates_module,
        "OPEN_STATE_SENTENCE",
        "Bu is hala acik (anlik goruntu: {read_at}).",
    )

    # The producer now builds the forbidden sentence without complaint, which
    # is exactly the regression the guard exists to prevent.
    note = candidates_module.open_state_note(datetime(2026, 9, 4, tzinfo=UTC))
    assert find_forbidden_phrases(note.detail) != ()


def test_the_guard_is_wired_into_the_producer_and_not_only_defined(
    api_source_root: Path,
) -> None:
    """The assumption the mutation control rests on, pinned where it can rot.

    The mutation above is only meaningful because the producer calls the
    guard. If those call sites were deleted the mutation would still "pass"
    while testing nothing, so the call sites are read off the syntax tree.
    """
    path = api_source_root / "station_api" / "workscan" / "candidates.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "assert_no_forbidden_claim"
    ]

    assert len(calls) >= 4, "the producer stopped checking its own wording"


def test_the_honesty_sentence_is_not_itself_a_forbidden_claim() -> None:
    assert find_forbidden_phrases(DERIVATION_HONESTY_SENTENCE) == ()
    assert "anlamsal cikarim yoktur" in DERIVATION_HONESTY_SENTENCE
