"""The claims ADR-0012 made false, and the guard that has to keep finding them.

A live read of the Gorevler screen found two sentences contradicting each
other three paragraphs apart: the card description said *there is no model
call*, the run sentence said *the test result stays 'not implemented'*, and
the block between them correctly said the model **proposes** a plan and the
test result is derived from the plan's own acceptance conditions. Both of the
first two were true when they were written and both were false when they were
read, because ADR-0012 opened the model lane and
:mod:`station_api.agent.acceptance` gave a plan a criterion a machine can
decide.

Why this file exists rather than two edits
-------------------------------------------
The two sentences were not the defect; they were two instances of it. This
repository has now found the same shape eight times - a claim that outlived
the fact it rested on - and in three of those the *comment above the sentence*
had already been corrected while the sentence itself had not
(``modules/registry.py`` says, in English, that the detail below it "is no
longer accurate", and the detail below it still says the old thing). A guard
that checked the two known sentences would have caught neither of those.

So the set of strings checked here is **discovered by walking the product
trees**, not read from a list of paths:

* Python is read through :mod:`ast`, because the sentences are written as
  implicitly concatenated literals and a text scan would look for
  ``"hicbir kod yolu"`` in a file that spells it ``hicbir "`` newline
  ``"kod yolu``;
* TypeScript and TSX are read as text, because the worst offender was **JSX
  text** - not a string literal at all - wrapped across two source lines by
  the formatter.

Two controls keep the walk honest, and both of them have to be able to fail:

* :func:`test_a_claim_planted_in_a_file_no_list_names_is_seen` writes a probe
  file into each real tree, in a directory this module never names, and
  asserts the walk finds it. A guard that reads a list of paths passes every
  other test here and fails this one.
* :func:`test_every_pattern_can_match_something` asserts each pattern matches
  a sentence written out by hand. A pattern with a typo in it matches nothing
  and reports a clean tree forever.

The claims are the product's, so the patterns are Turkish
----------------------------------------------------------
AGENTS.md 3 splits the languages: what a user reads is Turkish, and comments
and identifiers are English. The patterns below are therefore Turkish, which
is exactly the surface a user can be misled by. English prose carrying the
same stale premise - a docstring saying "the model lane is closed" - is
outside this guard on purpose: it is a note to the next developer, not a
sentence the product says, and writing English patterns would have meant
either exempting the two places that legitimately *quote* the old wording or
accepting a false positive that somebody would eventually silence.

What stays true, and is not what this file is about
-----------------------------------------------------
Arbitrary code and shell execution are still closed (ADR-0008 1, restated by
ADR-0012 7). The model only proposes; nothing it returns runs without the
four approvals. A plan that writes no acceptance condition still earns
``not_implemented``. Sentences saying those things are correct and must stay -
which is why the patterns are written narrowly enough to leave them alone, and
why :func:`test_the_sentences_that_are_still_earned_are_not_flagged` pins
that.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from station_api.agent.acceptance import (
    AcceptanceState,
    bind_condition,
    evaluate,
)
from station_api.agent.language import (
    RUN_HONESTY_SENTENCE,
    find_forbidden_phrases,
)
from station_api.evidence.language import fold

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# The claims. Written out, in the language the product speaks them in.
# ---------------------------------------------------------------------------

#: Each entry is a name and a folded-Turkish pattern for one stale claim.
#:
#: They are deliberately not derived from any registry the product also reads:
#: a guard sharing its input with the thing it guards can only ever agree with
#: it. They are also deliberately narrow. ``"model cagrisi yapilmaz"`` is a
#: **conditional** refusal this build makes for good reasons - no provider key,
#: an empty tool list, the model-call ceiling reached - and a pattern that
#: swallowed those would be turned off within a week.
STALE_CLAIMS: tuple[tuple[str, str], ...] = (
    # "the model lane is closed", in any of its inflections.
    ("model_lane_closed", r"model yolu kapal"),
    # "there is no model call" as a property of the build, rather than as the
    # outcome of a named condition.
    ("no_model_call", r"model cagrisi[^.!?]{0,120}\byoktur\b"),
    ("no_model_call_at_all", r"hicbir model cagrisi"),
    # "the test result stays 'not implemented'" - true of a plan with no
    # acceptance conditions, false as an absolute since ADR-0012.
    ("test_result_stays_unimplemented", r"test sonucu[^.!?]{0,80}uygulanmadi[^.!?]{0,40}kalir"),
    ("no_code_path_can_produce_it", r"hicbir kod yolu bu kaniti uretemez[^.!?]{0,160}uygulanmadi"),
    # "the execution that would run it is closed", given as *the* reason a
    # test result is missing. Acceptance conditions are decided by reading
    # bytes; no executor is involved either way.
    ("test_needs_the_closed_executor", r"kosacak yurutme kapalidir"),
)

_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern)) for name, pattern in STALE_CLAIMS
)

#: One sentence per pattern, so a pattern that can never match is a failure
#: here rather than a clean report forever. Written by hand and on purpose in
#: the shape the product used to write them.
PATTERN_EXAMPLES: dict[str, str] = {
    "model_lane_closed": "Bu surumde model yolu kapalidir.",
    "no_model_call": "Arac zinciri deterministiktir: model cagrisi ve kabuk komutu yoktur.",
    "no_model_call_at_all": "Hicbir model cagrisi yapilmaz.",
    "test_result_stays_unimplemented": (
        "Test sonucu 'uygulanmadi' kalir ve gorev yayima hazir sayilamaz."
    ),
    "no_code_path_can_produce_it": (
        "Yurutme kapali oldugu icin hicbir kod yolu bu kaniti uretemez: sonuc "
        "'uygulanmadi' olarak raporlanir."
    ),
    "test_needs_the_closed_executor": (
        "Test sonucu bu surumde uygulanmadi; onu kosacak yurutme kapalidir."
    ),
}

#: Sentences this build has still earned. They sit close enough to the
#: patterns that a wider rule would take them out, and taking them out is how
#: a guard becomes a thing somebody deletes.
STILL_EARNED: tuple[str, ...] = (
    "Keyfi kod ve kabuk yurutmesi kapalidir; bir metni komut olarak kosacak yol yoktur.",
    "Saglayici anahtari kaydedilmedi; model cagrisi yapilamaz.",
    "Model cagrisi tavanina ulasildi; bu gorev icin yeni bir model cagrisi yapilmaz.",
    "Tavan: en cok 8 model cagrisi, en cok 120 saniye, eszamanlilik 1.",
    "Model plan onerir, calistirmaz.",
    (
        "Test sonucu uygulanmadi: bu plan makinece degerlendirilebilir bir kabul "
        "kosulu yazmadi."
    ),
    "Note lane bu surumde yoktur; hicbir kod yolu bu kaniti uretemez.",
    "Gercek bir cikis kodu uretilmedi; kosacak bir denetim yoktur.",
)


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------

#: The trees a user's sentences can come out of, named as directories rather
#: than as files. Everything inside them is read; nothing inside them is
#: exempt, including the test fixtures - a fixture holding a stale copy of a
#: product sentence is how the stale sentence stays green after the product
#: has moved on, which is exactly what happened to ``TasksPanel.test.tsx``.
PRODUCT_TREES: tuple[tuple[tuple[str, ...], frozenset[str]], ...] = (
    (("apps", "station-api", "src", "station_api"), frozenset({".py"})),
    (("apps", "station-web", "src"), frozenset({".ts", ".tsx"})),
    (("apps", "station-web", "e2e"), frozenset({".ts"})),
)

#: Directories a tree walk finds and nobody wants read.
_SKIPPED_DIRECTORIES = frozenset({"node_modules", "__pycache__", ".venv", "dist"})


@dataclass(frozen=True, slots=True)
class Span:
    """One piece of product text, and where a reader would find it."""

    path: Path
    line: int
    text: str


def product_files(repo_root: Path) -> tuple[Path, ...]:
    """Every source file in the product trees, found by walking them."""
    found: list[Path] = []
    for parts, suffixes in PRODUCT_TREES:
        root = repo_root.joinpath(*parts)
        assert root.is_dir(), f"product tree missing: {root}"
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            if _SKIPPED_DIRECTORIES & set(path.parts):
                continue
            found.append(path)
    return tuple(found)


def _python_spans(path: Path) -> Iterator[Span]:
    """Every string literal, read off the syntax tree.

    Docstrings are included rather than filtered. They are English, so the
    Turkish patterns cannot fire on them, and excluding them would mean
    writing a rule about which literals count - the kind of rule that is
    quietly widened later.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield Span(path=path, line=node.lineno, text=node.value)


def _text_spans(path: Path) -> Iterator[Span]:
    """The whole file, folded line by line and rejoined, with the lines kept.

    A single span rather than one per literal, because the sentence that
    started this was **JSX text**: it has no quotes around it and the
    formatter had broken it over two lines. Anything narrower than the file
    would have had a window size in it, and a window size is a number somebody
    picks and nobody revisits.
    """
    folded_lines: list[str] = []
    starts: list[tuple[int, int]] = []
    offset = 0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        folded = fold(line).strip()
        if not folded:
            continue
        starts.append((offset, number))
        folded_lines.append(folded)
        offset += len(folded) + 1
    yield Span(path=path, line=starts[0][1] if starts else 1, text=" ".join(folded_lines))


def _line_for(span: Span, index: int) -> int:
    """The source line a match at ``index`` inside a text span came from."""
    if span.path.suffix == ".py":
        return span.line
    offset = 0
    line = span.line
    for number, raw in enumerate(span.path.read_text(encoding="utf-8").splitlines(), 1):
        folded = fold(raw).strip()
        if not folded:
            continue
        if offset <= index < offset + len(folded) + 1:
            return number
        offset += len(folded) + 1
        line = number
    return line


def spans_of(path: Path) -> Iterator[Span]:
    return _python_spans(path) if path.suffix == ".py" else _text_spans(path)


def stale_claims_in(repo_root: Path) -> tuple[str, ...]:
    """Every stale claim in the product trees, as ``path:line [name] text``."""
    offenders: list[str] = []
    for path in product_files(repo_root):
        for span in spans_of(path):
            haystack = fold(span.text)
            for name, pattern in _COMPILED:
                # Every match of every pattern, not the first one found. A
                # TypeScript span is the whole file, so stopping at the first
                # hit would report one claim per file and hide the rest until
                # somebody fixed the one that was showing.
                for match in pattern.finditer(haystack):
                    line = _line_for(span, match.start())
                    quoted = match.group(0)[:100]
                    offenders.append(
                        f"{path.relative_to(repo_root).as_posix()}:{line} "
                        f"[{name}] {quoted}"
                    )
    return tuple(dict.fromkeys(offenders))


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_no_product_string_claims_the_model_lane_is_closed(repo_root: Path) -> None:
    """The whole point: nothing a user can read says the closed thing is closed.

    ADR-0012 opened the model lane and measured the contract before opening
    it. A sentence that still says the lane is closed is not a cautious
    sentence; it is a wrong one, and it is wrong in the direction that makes
    the product look safer than it is.
    """
    offenders = stale_claims_in(repo_root)

    assert offenders == (), "stale model-lane / test-result claims:\n" + "\n".join(
        offenders
    )


def test_the_walk_reaches_all_three_trees_and_reads_real_text(
    repo_root: Path,
) -> None:
    """Guards the guard: a walk that found nothing would pass forever."""
    files = product_files(repo_root)

    suffixes = {path.suffix for path in files}
    assert suffixes == {".py", ".ts", ".tsx"}, suffixes
    assert len(files) >= 150, len(files)

    characters = sum(len(span.text) for path in files for span in spans_of(path))
    assert characters > 500_000, characters


@pytest.mark.parametrize("name,pattern", STALE_CLAIMS)
def test_every_pattern_can_match_something(name: str, pattern: str) -> None:
    """A pattern that matches nothing is a clean report and no guard at all."""
    example = PATTERN_EXAMPLES[name]

    assert re.compile(pattern).search(fold(example)), f"{name} matches nothing"


@pytest.mark.parametrize("sentence", STILL_EARNED)
def test_the_sentences_that_are_still_earned_are_not_flagged(sentence: str) -> None:
    """The other half of a usable rule: it leaves the true sentences alone.

    Every one of these is a claim this build has earned - execution is closed,
    a named condition refuses a call, a conditionless plan is not implemented -
    and a guard that failed them would be a guard somebody widens an exemption
    list for.
    """
    haystack = fold(sentence)
    hit = [name for name, pattern in _COMPILED if pattern.search(haystack)]

    assert hit == [], f"a true sentence is flagged by {hit}: {sentence}"


def test_a_claim_planted_in_a_file_no_list_names_is_seen(repo_root: Path) -> None:
    """The mutation control, and the one test a list-reading guard fails.

    Two probes, one per language, in directories this module names nowhere.
    They exist for the length of one assertion and are removed in ``finally``
    whether it passes or not.
    """
    probes = {
        repo_root
        / "apps"
        / "station-api"
        / "src"
        / "station_api"
        / "technocore"
        / "_planted_probe.py": (
            'PLANTED = "Bu surumde model yolu kapalidir; olculecek bir sey yok."\n'
        ),
        repo_root
        / "apps"
        / "station-web"
        / "src"
        / "components"
        / "identity"
        / "_planted_probe.tsx": (
            "export const PLANTED = (\n"
            "  <p>\n"
            "    Araclar deterministiktir; hicbir kabuk komutu ve hicbir model\n"
            "    cagrisi yoktur.\n"
            "  </p>\n"
            ");\n"
        ),
    }
    for path, body in probes.items():
        assert path.parent.is_dir(), path.parent
        assert not path.exists(), path
    try:
        for path, body in probes.items():
            path.write_text(body, encoding="utf-8")
        seen = stale_claims_in(repo_root)
    finally:
        for path in probes:
            path.unlink(missing_ok=True)

    for path in probes:
        stem = path.relative_to(repo_root).as_posix()
        assert any(
            line.startswith(stem) for line in seen
        ), f"the walk cannot see a claim planted in {stem}: {seen}"


# ---------------------------------------------------------------------------
# The run sentence, pinned against the code that made it false
# ---------------------------------------------------------------------------


def test_the_acceptance_registry_really_can_produce_a_pass(tmp_path: Path) -> None:
    """The fact the pin below rests on, measured rather than asserted.

    Pinning "the run sentence must not say the test result is always
    ``not_implemented``" is only meaningful while a pass is reachable. If
    :mod:`station_api.agent.acceptance` were ever reduced to the state it
    replaced, this fails first and says so, instead of leaving the next
    reader with a sentence that is too weak for a build that got weaker.
    """
    (tmp_path / "rapor.json").write_text('{"ad": "TEST-ONLY"}', encoding="utf-8")
    condition = bind_condition(
        "artifact_has_json_keys", {"name": "rapor.json", "keys": "ad"}
    )

    outcome = evaluate([condition], tmp_path)

    assert outcome.state is AcceptanceState.PASSED
    assert evaluate([], tmp_path).state is AcceptanceState.NOT_IMPLEMENTED


def test_the_run_sentence_no_longer_claims_the_result_is_always_unimplemented() -> None:
    """The two sentences the browser read, pinned as meanings rather than text.

    The old sentence made two absolute claims - no model call, and the test
    result stays ``not_implemented`` - and the code under it stopped
    supporting either one on the same commit. What has to survive is
    everything it was still right about: the tool chain is deterministic,
    arbitrary execution is closed, a plan without acceptance conditions is not
    published.
    """
    folded = fold(RUN_HONESTY_SENTENCE)

    flagged = [name for name, pattern in _COMPILED if pattern.search(folded)]
    assert flagged == [], f"the run sentence still makes a stale claim: {flagged}"

    # What it must still say, because those are still true.
    assert "deterministik" in folded
    assert "uygulanmadi" in folded
    assert "yayima hazir sayilamaz" in folded
    assert "kabul kosul" in folded, "the sentence has to say what decides the result"
    assert "onerir" in folded or "onerebilir" in folded

    # And it stays under its own package's forbidden-phrase registry.
    assert find_forbidden_phrases(RUN_HONESTY_SENTENCE) == ()
    assert not set(RUN_HONESTY_SENTENCE) & set("çğıöşüÇĞİÖŞÜ")
