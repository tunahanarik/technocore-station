"""The forbidden-phrase audit, extended to cover H3's own text.

Package E built this control for the evidence layer, H1 extended it to the
work scan and H2 to the agent runtime. Each scan is scoped to its own
directory, so a new package's wording is covered by nothing at all until it
brings its own - and a rule that does not cover the text being written is not
a rule (ADR-0007 10, ADR-0008 9, ADR-0009 5).

Three halves, as in the three files before this one:

* the **runtime** guard, on the sentences this package writes;
* the **static** scan, over every string literal in the package *and* in the
  route file in front of it;
* the **mutation** control: with the guard neutered, at least one test here
  has to go red. A guard nobody has watched fail is a guard nobody has tested.

Why this package needed its own seven
--------------------------------------
The subject of H3 is a word - *proof* - that a reader is entitled to misread
as *proven*, and ADR-0009 11 requires the difference to be written down rather
than left to inference. Every phrase H3 adds is a sentence somebody would
reasonably write on a proof screen and that this build cannot support: there
is no independent check (the model lane is closed), a digest does not verify
content, no check ran and there is no exit code, and handing a file to a
browser is neither a publication nor a verification.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from station_api.agent.language import FORBIDDEN_PHRASES as AGENT_FORBIDDEN_PHRASES
from station_api.evidence.language import (
    FORBIDDEN_PHRASES as EVIDENCE_FORBIDDEN_PHRASES,
)
from station_api.proof import bundle as bundle_module
from station_api.proof import service as service_module
from station_api.proof.language import (
    BUNDLE_SCOPE_SENTENCE,
    FORBIDDEN_PHRASES,
    HASH_SCOPE_SENTENCE,
    NEUTRALISED_MARK,
    PERMITTED_ALTERNATIVES,
    PROOF_FORBIDDEN_PHRASES,
    ForbiddenClaimError,
    assert_no_forbidden_claim,
    find_forbidden_phrases,
    neutralise,
)
from station_api.workscan.language import (
    FORBIDDEN_PHRASES as SCAN_FORBIDDEN_PHRASES,
)

pytestmark = pytest.mark.security

#: Files the static scan skips, and why. ``language.py`` is the registry
#: itself, which writes the phrases out in full; nothing else is exempt.
_EXEMPT = frozenset({"language.py"})

TEST_ONLY_CONTENT = b"TEST-ONLY proof task content."

#: U+200B ZERO WIDTH SPACE. Written as an escape rather than as the character,
#: because a bare zero-width space in source is invisible to a reviewer - and a
#: test whose input a reviewer cannot see is a test nobody can check.
ZERO_WIDTH_SPACE = "​"


def _package(api_source_root: Path) -> Path:
    return api_source_root / "station_api" / "proof"


def _scanned(api_source_root: Path) -> list[Path]:
    files = [
        path
        for path in sorted(_package(api_source_root).rglob("*.py"))
        if path.name not in _EXEMPT
    ]
    files.append(api_source_root / "station_api" / "routes" / "proof.py")
    return files


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


def test_the_registry_inherits_all_three_earlier_layers_rather_than_copying() -> None:
    """A phrase added in E, H1 or H2 is refused here on the same commit."""
    for phrase in EVIDENCE_FORBIDDEN_PHRASES:
        assert phrase in FORBIDDEN_PHRASES
    for phrase in SCAN_FORBIDDEN_PHRASES:
        assert phrase in FORBIDDEN_PHRASES
    for phrase in AGENT_FORBIDDEN_PHRASES:
        assert phrase in FORBIDDEN_PHRASES

    assert len(FORBIDDEN_PHRASES) == len(AGENT_FORBIDDEN_PHRASES) + len(
        PROOF_FORBIDDEN_PHRASES
    )
    assert len(PROOF_FORBIDDEN_PHRASES) == len(PERMITTED_ALTERNATIVES)


def test_every_phrase_the_adr_names_is_in_the_registry() -> None:
    """The claims ADR-0009 6, 7 and 11 forbid, in the wording they would appear in."""
    for phrase in (
        "bagimsiz olarak dogrulandi",
        "ucuncu taraf onayi",
        "ozet icerigi dogrular",
        "denetim basariyla kosuldu",
        "cikis kodu 0",
    ):
        assert phrase in PROOF_FORBIDDEN_PHRASES


@pytest.mark.parametrize("phrase", PROOF_FORBIDDEN_PHRASES)
def test_a_phrase_is_caught_in_every_spelling(phrase: str) -> None:
    """Folded matching, so the Turkish and ASCII spellings are one claim.

    The dotless ``i`` is the case IMP-384 records: ``casefold`` does not map it
    onto ``i``, so a guard written in ASCII is blind to the language this
    product is written in. The spellings are generated rather than typed, so
    the test cannot share a blind spot with the rule.
    """
    for spelling in (phrase, phrase.upper(), phrase.replace("i", "ı")):
        assert find_forbidden_phrases(f"once {spelling} sonra") != ()


def test_the_permitted_wording_passes_its_own_guard() -> None:
    """ADR-0009 11's sentence, and the rule it has to survive.

    A guard whose own permitted wording tripped it would be a guard somebody
    edits the guard for. This is the sentence the product actually prints
    about what a digest establishes, and it has to say the honest thing
    *without* putting a forbidden phrase in its own mouth.
    """
    assert find_forbidden_phrases(HASH_SCOPE_SENTENCE) == ()
    assert find_forbidden_phrases(BUNDLE_SCOPE_SENTENCE) == ()

    # And it says the thing ADR-0009 11 asks for rather than merely passing.
    assert "bayt bakimindan ayni kaldigini tanimlar" in HASH_SCOPE_SENTENCE
    assert "yararli" in HASH_SCOPE_SENTENCE
    assert "kanit" in HASH_SCOPE_SENTENCE
    assert "hicbir yola yazilmaz" in BUNDLE_SCOPE_SENTENCE
    for sentence in (HASH_SCOPE_SENTENCE, BUNDLE_SCOPE_SENTENCE):
        assert not set(sentence) & set("çğıöşüÇĞİÖŞÜ")


def test_an_innocent_sentence_passes() -> None:
    assert find_forbidden_phrases("bu gorev icin bir paket hazirlandi") == ()


# ---------------------------------------------------------------------------
# The runtime half
# ---------------------------------------------------------------------------


def test_our_own_over_claim_fails_closed() -> None:
    with pytest.raises(ForbiddenClaimError):
        assert_no_forbidden_claim(
            "Bu cikti bagimsiz olarak dogrulandi.", where="test_only"
        )


def test_user_text_carrying_a_forbidden_phrase_is_neutralised_not_refused() -> None:
    """Package E's split, applied here.

    A person who types the banned words into a task title or a note must not
    be able to make this product refuse to show them their own proof.
    """
    hostile = "merhaba, bu cikti bagimsiz olarak dogrulandi ve ucuncu taraf onayi var"
    cleaned = neutralise(hostile)

    assert find_forbidden_phrases(cleaned) == ()
    assert NEUTRALISED_MARK in cleaned
    assert "merhaba" in cleaned


def test_neutralising_leaves_clean_text_untouched() -> None:
    assert neutralise("sade bir cumle") == "sade bir cumle"


def test_the_earlier_layers_phrases_are_neutralised_here_too() -> None:
    for hostile in (
        "bu bir sunucu kanitidir",
        "bu is hala acik",
        "burada kod calistirildi",
    ):
        assert find_forbidden_phrases(neutralise(hostile)) == ()


# ---------------------------------------------------------------------------
# The static half
# ---------------------------------------------------------------------------


def test_no_string_literal_in_the_proof_package_carries_a_forbidden_phrase(
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

    assert len(scanned) >= 5, scanned
    assert {"bundle.py", "service.py", "approvals.py", "proof.py"} <= {
        path.name for path in scanned
    }
    literals = 0
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        literals += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    assert literals > 150, literals


def test_the_route_layer_is_scanned_too(api_source_root: Path) -> None:
    """The wording a user reads is assembled partly in the route.

    Scanning only the package would leave the layer closest to the screen
    outside the rule - the exact gap ADR-0007 10 was written about.
    """
    path = api_source_root / "station_api" / "routes" / "proof.py"
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
        'LABEL = "Bu ozet icerigi dogrular ve denetim basariyla kosuldu."\n',
        encoding="utf-8",
    )

    tree = ast.parse(planted.read_text(encoding="utf-8"))
    found = [
        find_forbidden_phrases(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]

    assert any(found), "the scan cannot see a phrase it was pointed at"


def test_the_language_module_is_the_only_exempt_file(api_source_root: Path) -> None:
    """The exemption list is one file, and it is the registry itself.

    An exemption that grew would be the quietest way to take a package's
    wording back out of the rule.
    """
    all_files = {path.name for path in _package(api_source_root).rglob("*.py")}

    assert {"language.py"} == _EXEMPT
    assert all_files >= _EXEMPT
    assert len(all_files - _EXEMPT) >= 4


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

    for phrase in PROOF_FORBIDDEN_PHRASES:
        assert phrase in registry_literals, phrase


# ---------------------------------------------------------------------------
# The mutation control
# ---------------------------------------------------------------------------


def test_turning_the_guard_into_a_no_op_lets_a_bundle_carry_an_over_claim(
    proof, task, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    """The control ADR-0008 9 asks for, run inside the suite, for H3's own text.

    Unmutated, a bundle whose fixed hash sentence carries a forbidden claim is
    refused before a single byte is produced. Mutated, the same string is
    written into the document and would be handed to the browser - which is
    exactly the regression the guard exists to prevent, and what makes "the
    guard is load-bearing" a measured statement rather than a hopeful one.

    Both the sentence and :data:`PRODUCT_SENTENCES` are patched, because the
    tuple is built at import from the sentence: patching one without the other
    would mutate the *document* without mutating what the guard reads, and the
    test would appear to work for the wrong reason.
    """
    over_claim = "Bu ozet icerigi dogrular."
    monkeypatch.setattr(bundle_module, "HASH_SCOPE_SENTENCE", over_claim)
    monkeypatch.setattr(
        bundle_module,
        "PRODUCT_SENTENCES",
        (over_claim, *bundle_module.PRODUCT_SENTENCES[1:]),
    )

    with pytest.raises(ForbiddenClaimError):
        proof.build(task.id)

    monkeypatch.setattr(
        bundle_module, "assert_no_forbidden_claim", lambda text, *, where: None
    )
    bundle = proof.build(task.id)

    assert find_forbidden_phrases(bundle.document["notes"]["hash_scope"]) != ()


def test_turning_the_neutraliser_off_lets_a_users_words_refuse_the_product(
    proof, task, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    """IMP-420's shape, driven on H3's own surface.

    A note the user types is quoted back inside the sentence this product
    writes. Unmutated it is neutralised first, so a person who types the
    banned words gets their acceptance recorded with the phrase removed.
    Mutated - the neutralising step gone - their own words reach our sentence,
    the guard correctly refuses it, and a request a person can act on becomes
    an unhandled error.

    That is the direction that matters: the neutraliser is not there to make
    the guard quieter, it is there so a keyboard cannot decide whether this
    product may speak.
    """
    hostile = "bence bu cikti bagimsiz olarak dogrulandi"
    bundle = proof.build(task.id)

    recorded = proof.record_acceptance(
        task.id, bundle_sha256=bundle.sha256, detail=hostile
    )
    stored = next(
        ref.detail for ref in recorded.refs if ref.field.value == "user_acceptance"
    )
    assert find_forbidden_phrases(stored) == ()
    assert NEUTRALISED_MARK in stored

    monkeypatch.setattr(bundle_module, "neutralise", lambda text: text)

    with pytest.raises(ForbiddenClaimError):
        proof.record_acceptance(
            task.id, bundle_sha256=proof.build(task.id).sha256, detail=hostile
        )


def test_a_zero_width_character_cannot_smuggle_a_phrase_into_our_sentence(
    proof, task  # type: ignore[no-untyped-def]
) -> None:
    """``safe_text`` sweeps **before** it neutralises, driven on a real note.

    The order inside ``safe_text`` was not pinned by anything until an
    adversarial review swapped the two calls and measured zero failures. The
    mutant is not equivalent, and the reason is that the two functions
    disagree about invisible characters by design: ``fold`` - which
    ``neutralise`` compares through - **deletes** them, so ``w<ZWSP>allet`` is
    one word to a matcher, while ``sweep_untrusted`` **replaces** them with a
    space, so nothing can hide behind one in a scanned sentence.

    Put a zero-width space between two words of a forbidden phrase and the two
    behaviours pull apart. Folded, the phrase reads ``bagimsizolarak
    dogrulandi`` and matches no entry in the registry; swept, it is the
    registry entry, character for character. Sweeping first therefore hands
    ``neutralise`` the string it has to see. Sweeping second hands
    ``assert_no_forbidden_claim`` a live forbidden phrase, and
    ``routes/proof.py`` catches only ``(ProofError, TaskError)`` - so a note a
    person typed would come back as an unhandled 500 on their own acceptance,
    which is IMP-420's failure exactly: a keyboard deciding what this product
    may say.
    """
    hostile = f"bence bu cikti bagimsiz{ZERO_WIDTH_SPACE}olarak dogrulandi"
    # The premise, asserted rather than assumed: neutralising the raw text
    # alone does nothing, so the sweep is doing the work being measured.
    assert neutralise(hostile) == hostile

    bundle = proof.build(task.id)
    recorded = proof.record_acceptance(
        task.id, bundle_sha256=bundle.sha256, detail=hostile
    )
    stored = next(
        ref.detail for ref in recorded.refs if ref.field.value == "user_acceptance"
    )

    assert find_forbidden_phrases(stored) == ()
    assert NEUTRALISED_MARK in stored
    assert ZERO_WIDTH_SPACE not in stored


def test_the_sweep_happens_inside_the_neutralise_call_and_not_around_it(
    api_source_root: Path,
) -> None:
    """The same order, read off the syntax tree as well as driven.

    The behavioural test above can only see the one path it drives, and
    ``safe_text`` is called from four places. This pins the shape itself:
    ``neutralise``'s argument must *be* a ``sweep_untrusted`` call, so the two
    cannot be swapped, and the sweep cannot be lifted out to a later step
    where it would re-expose what the neutraliser had removed.
    """
    path = _package(api_source_root) / "bundle.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    launderer = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "safe_text"
    )
    neutralise_calls = [
        node
        for node in ast.walk(launderer)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "neutralise"
    ]

    assert len(neutralise_calls) == 1
    inner = neutralise_calls[0].args[0]
    assert isinstance(inner, ast.Call)
    assert isinstance(inner.func, ast.Name)
    assert inner.func.id == "sweep_untrusted"


def test_the_guard_is_wired_into_the_package_and_not_only_defined(
    api_source_root: Path,
) -> None:
    """The assumption the mutations rest on, pinned where it can rot.

    A mutation is only meaningful because the code calls the guard. If those
    call sites were deleted the mutations would still "pass" while testing
    nothing, so the call sites are read off the syntax tree.
    """
    counted = 0
    for name in ("bundle.py", "service.py"):
        path = _package(api_source_root) / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        counted += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "assert_no_forbidden_claim"
        )

    assert counted >= 3, "the proof package stopped checking its own wording"


def test_the_neutralising_step_runs_before_the_guard_and_not_after(
    api_source_root: Path,
) -> None:
    """Where ``neutralise`` is called, read off the syntax tree.

    ADR-0008's split has one rule with a direction: user text is neutralised
    **before** it joins our sentence, and our sentence is then checked. H2's
    first attempt neutralised inside the same helper that ran the guard, which
    made the guard a no-op on exactly the text it existed for (IMP-420).

    So ``safe_text`` - the helper that launders a user's words - must call
    ``neutralise`` and must **not** call the guard; the guard is called by the
    functions that assemble a finished sentence.
    """
    path = _package(api_source_root) / "bundle.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    launderers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "safe_text"
    ]

    assert len(launderers) == 1, "exactly one helper may launder user text"
    calls = [
        node.func.id
        for node in ast.walk(launderers[0])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]

    assert "neutralise" in calls
    assert "assert_no_forbidden_claim" not in calls


def test_the_service_neutralises_a_users_note_before_quoting_it(
    api_source_root: Path,
) -> None:
    """And the service's own sentences go through the laundered value.

    Read structurally as well as behaviourally, because the behavioural test
    above can only see the paths it drives: both sentence builders must reach
    ``safe_text`` and both must then call the guard.
    """
    path = _package(api_source_root) / "service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for name in ("_acceptance_sentence", "_share_sentence"):
        builder = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        calls = [
            node.func.id
            for node in ast.walk(builder)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert "safe_text" in calls, name
        assert "assert_no_forbidden_claim" in calls, name

    assert service_module.ACCEPTED_WRITE_OUTCOME == "accepted"
