"""The forbidden-phrase rule covers the whole tree, not six remembered names.

The twelfth - and, per the sweep recorded in ``PROJECT_STATUS.md``, the last -
instance of this repository's signature defect: *a guard that looks like it
checks something but reads the same list as the thing it guards, so it can
never see a gap*.

What the gap was
----------------
``FORBIDDEN_PHRASES`` is enforced by a static scan written once per package,
and the scan's scope was six package names spread across five test files:
``evidence``, ``workscan``, ``agent`` and ``proof`` (their ``*_language.py``
tests), ``planner`` (``test_planner_boundary.py``), and four of the thirteen
files in ``routes``. Nothing walked the tree to ask whether those six were
all the packages that speak to a user. The three later ``*_language.py``
modules even *stated* the gap in prose - "each scan is scoped to its own
directory, so a new package's wording is covered by nothing at all until it
brings its own" - with no test behind the sentence, which is the tenth
instance's exact shape: the defect written into a comment instead of a guard.

It was measured rather than argued, twice:

* the plant ``PLANTED_OVERCLAIM = "Testler gecti ve kod calistirildi;
  otomatik onaylandi."`` - three forbidden phrases at once - appended in
  place to ``opencode/service.py``: **2269 passed**, byte-identical to the
  clean baseline;
* the same plant appended to one tracked file in each of the twelve
  uncovered packages *and* to ``routes/opencode.py``, thirteen files at once:
  **2269 passed** again.

Two sentences, one package red and its neighbour invisible. What decided the
scope was not the subject of the rule but whether somebody had written a
separate test file for that package.

What replaces it
----------------
The scan unit is no longer the package somebody remembered. It is **every
``.py`` file under ``station_api``** - eighteen packages and fourteen loose
modules - discovered by walking, applying the **union** registry (all
twenty-seven phrases, the one ``proof.language`` composes) rather than the
narrower per-package one. The per-package tests are untouched and still run;
this is a floor under them, not a replacement.

Nothing is exempt from being *scanned*, because opening a literal costs
nothing and an exemption is the hole. The only files outside are the four
registries themselves (:data:`REGISTRY_MODULES_OUTSIDE_THE_SCAN`), which
write the phrases out in full and are pinned as registries so a file cannot
keep the exemption after it stops being one.

What "user-visible Turkish" is, and why the question is load-bearing
--------------------------------------------------------------------
A scan that covers everything is trivially green in a package that says
nothing, and "green" would then mean two different things in the same run.
So each scan unit is separately classified, by walking, into one that emits
user-visible Turkish and one written down in
:data:`UNITS_WITHOUT_USER_VISIBLE_TURKISH` with the reason. Both directions
fail: a unit that speaks and is listed is a stale reason, a unit that is
silent and unlisted is somebody's unrecorded judgement.

The detector is deliberately one rule with two measured proofs rather than a
pile of heuristics with exclusions bolted on - exclusions added to quiet a
scan are how this defect is born. A literal is Turkish prose when its folded
form carries, **as a whole word**, one of :data:`TURKISH_MARKERS`.

*It is not too loose*: every marker is a Turkish word that is not an English
word, and that is checked against a corpus this file does not own -
``packages/technocore-conform/src``, 608 literals and 4755 word tokens of
English, in which the lexicon scores **zero**
(:func:`test_no_turkish_marker_is_an_english_word`).

*It is not too tight*: it has to see every sentence this product certifies as
its own wording - the honesty sentences the four language modules export -
and it does, with room to spare. The longest exported constant it does *not*
see is seven word tokens (``NEUTRALISED_ALL``, a bracketed mark rather than a
sentence); the shortest it does see is twenty-five
(:func:`test_the_detector_sees_every_sentence_this_product_certifies`). It was
sixteen until ADR-0014 rewrote ``DERIVATION_HONESTY_SENTENCE``, and the gap
around the threshold only got wider.

And the discovery walks. :func:`test_the_scan_reaches_a_package_no_list_here_names`
and :func:`test_the_derivation_sees_a_package_no_list_here_names` build a
package this file has never heard of and require both halves to find it -
which a version reading :data:`LANGUAGE_SCAN_PACKAGES` cannot do. That is not
a hypothesis: it is the mutation this guard was tested with, and it goes
green with the violation still planted.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from station_api.agent.language import FORBIDDEN_PHRASES as AGENT_FORBIDDEN_PHRASES
from station_api.downloads import DEFAULT_STEM
from station_api.evidence.language import (
    FORBIDDEN_PHRASES as EVIDENCE_FORBIDDEN_PHRASES,
)
from station_api.evidence.language import fold
from station_api.proof.language import (
    FORBIDDEN_PHRASES as ALL_FORBIDDEN_PHRASES,
)
from station_api.proof.language import find_forbidden_phrases
from station_api.workscan.language import (
    FORBIDDEN_PHRASES as WORK_SCAN_FORBIDDEN_PHRASES,
)

pytestmark = pytest.mark.security

#: Every package under ``station_api``, written out.
#:
#: Written out rather than globbed for the reason ``test_task_states.py``
#: gives about its own tuples: a list built from ``glob`` agrees with whatever
#: it finds, so it can never report a newcomer.
#: :func:`test_every_package_is_scanned_and_every_scanned_package_exists`
#: walks the tree and compares it against this, and the parametrised plant
#: tests below enumerate it, which is why it has to be a module constant
#: rather than a fixture.
#:
#: Nothing in this file *scopes* the scan by this tuple. The scan walks; this
#: is what the walk is checked against.
LANGUAGE_SCAN_PACKAGES: tuple[str, ...] = (
    "agent",
    "cli",
    "compose",
    "conformance",
    "db",
    "evidence",
    "identity",
    "modules",
    "opencode",
    "planner",
    "proof",
    "recovery",
    "routes",
    "security",
    "tasks",
    "technocore",
    "vault",
    "workreader",
    "workscan",
)

#: Every loose module sitting directly under ``station_api``, written out.
#:
#: The same list ``test_task_states.py`` and ``test_task_evidence.py`` keep,
#: for the same reason and closing the same shape one level down: the eleventh
#: instance of this defect was a rule whose scan unit was the *package*, so a
#: ``.py`` file beside ``app.py`` was outside it altogether. ``schemas.py``
#: alone carries 324 string literals.
LANGUAGE_SCAN_MODULES: tuple[str, ...] = (
    "__init__.py",
    "__main__.py",
    "app.py",
    "config.py",
    "dependencies.py",
    "digests.py",
    "downloads.py",
    "launcher.py",
    "logging_setup.py",
    "resources.py",
    "schemas.py",
    "seed_import.py",
    "single_instance.py",
    "strict_json.py",
)

#: The only files the scan does not open, by exact relative path, with the
#: reason. A **counted list, not a pattern**: ``language.py`` as a *name*
#: would exempt any file anywhere that somebody chose to call that, which is
#: an exemption that widens itself.
#:
#: Each entry is pinned against what it claims to be by
#: :func:`test_the_registry_exemption_is_exactly_four_files_that_are_registries`:
#: a file keeps the exemption only while it still defines ``FORBIDDEN_PHRASES``
#: **and** still spells at least one registered phrase out. A registry that is
#: emptied or renamed loses the exemption in the same commit rather than
#: keeping a hole open behind a familiar filename.
REGISTRY_MODULES_OUTSIDE_THE_SCAN: dict[str, str] = {
    "evidence/language.py": (
        "Package E's registry. It writes the six charter phrases out as data "
        "so they can be compared against; a scan of its literals would be a "
        "scan of the rule itself."
    ),
    "workscan/language.py": (
        "H1's registry. Inherits Package E's six and adds seven, each spelled "
        "out beside the permitted alternative it replaces."
    ),
    "agent/language.py": (
        "H2's registry. Inherits the thirteen above and adds seven, and its "
        "module docstring quotes each addition while explaining why the "
        "runtime cannot support it."
    ),
    "proof/language.py": (
        "H3's registry, and the one this scan applies: it composes all "
        "twenty-seven phrases. Adds seven of its own, spelled out."
    ),
}

#: Every scan unit that emits **no** user-visible Turkish, one by one, with
#: the reason - what the unit does, not that the rule does not apply to it.
#:
#: These are not exemptions. Every one of them is still scanned; opening a
#: literal costs nothing and an exemption is the hole this file exists to
#: close. What the entry records is why the scan is *trivially* green there,
#: so that "green" carries one meaning across the whole tree and a unit that
#: starts speaking to a user is reported rather than absorbed
#: (:func:`test_every_scan_unit_either_speaks_turkish_or_is_a_written_down_silence`).
#:
#: Three of the reasons make a specific factual claim about specific code, and
#: those three are pinned against a measurement rather than left to be read as
#: though they still described the tree - the ``agent.budget``-at-exactly-three
#: -importers and ``compose``-at-``nonce.py:_settle_once`` pattern.
UNITS_WITHOUT_USER_VISIBLE_TURKISH: dict[str, str] = {
    "conformance": (
        "A thin adapter over technocore_conform.run_self_test. It produces a "
        "verdict object, not a sentence: the wording a person reads about "
        "conformance is written in routes/conformance.py, which is inside "
        "this scan and does speak Turkish. Pinned by "
        "test_the_conformance_wording_lives_in_the_route_that_is_scanned."
    ),
    "security": (
        "Request guards. What it puts on the wire is header values, CSP "
        "directives and machine-readable refusal codes - host_not_allowed, "
        "origin_not_allowed, cross_origin_request_blocked, "
        "csrf_session_required, csrf_token_invalid, internal_error - which "
        "exist precisely so a refusal carries no request detail. The Turkish "
        "a user reads for a refusal is written in routes/. Pinned by "
        "test_the_security_package_answers_with_codes_rather_than_sentences."
    ),
    "__init__.py": (
        "The package docstring and nothing executable. It declares the local "
        "FastAPI core and defines no function that could address a user."
    ),
    "__main__.py": (
        "The `python -m station_api` entry point: a docstring and the "
        "'__main__' guard. It hands straight to launcher.py."
    ),
    "config.py": (
        "Runtime settings. Its literals are environment variable names, "
        "header names, the data directory and the dev origin - identifiers "
        "the operating system reads, not text a person reads."
    ),
    "dependencies.py": (
        "One route dependency, which refuses an unauthenticated request with "
        "a status code and no body text."
    ),
    "digests.py": (
        "Domain-separated SHA-256 helpers. Its literals are the domain "
        "labels and encodings that go into a hash."
    ),
    "downloads.py": (
        "Builds a Content-Disposition header that cannot say more than a "
        "name. Its one Turkish token is the default filename stem "
        "DEFAULT_STEM = 'indirme', a single word; the shortest registered "
        "phrase is two words, so a stem cannot carry one. Pinned by "
        "test_the_download_stem_is_one_word_and_no_phrase_is."
    ),
    "launcher.py": (
        "Binds the loopback socket and starts uvicorn. Its two console lines "
        "are English operator messages on stdout, addressed to whoever "
        "started the process rather than to the person using the product."
    ),
    "logging_setup.py": (
        "Mandatory log redaction. Its literals are logger names, the "
        "'<redacted>' placeholder and a record format string; nothing here "
        "reaches a screen."
    ),
    "strict_json.py": (
        "JSON parsing with the duplicate-key and depth rules applied. It "
        "raises typed errors that the route layer turns into sentences."
    ),
}

#: The refusal codes ``security`` answers with, so the reason above is a
#: measurement rather than a recollection. Each has to be a bare
#: machine-readable token - lowercase, underscores, no space - because "this
#: package answers with codes, not sentences" is exactly the claim that would
#: rot quietly if somebody put a Turkish sentence in one of these ``detail``
#: values.
SECURITY_REFUSAL_CODES: tuple[str, ...] = (
    "cross_origin_request_blocked",
    "csrf_session_required",
    "csrf_token_invalid",
    "host_not_allowed",
    "internal_error",
    "origin_not_allowed",
)

#: The predicate: Turkish words that are **not** English words.
#:
#: A predicate constant, in the sense the sweep behind the eleventh instance
#: drew - *what* a rule looks for, as opposed to *where* it looks. Written out
#: is the right shape for one of those (``FORBIDDEN_PHRASES`` is one); it is
#: the scope constants that have to be walked instead.
#:
#: Chosen as closed-class and near-closed-class vocabulary - articles,
#: conjunctions, postpositions, copulas - because those are what separate a
#: sentence from a label, and they appear in Turkish prose of any subject. A
#: content-word lexicon would have to grow with the product; this does not.
#:
#: Three obvious candidates are deliberately absent, and they are the reason
#: this list is checked rather than trusted: ``her``, ``once`` and ``var`` are
#: all common Turkish words **and** English ones, so each would fire on an
#: English log line. :func:`test_no_turkish_marker_is_an_english_word` is what
#: keeps a fourth of them from being added by accident.
TURKISH_MARKERS: frozenset[str] = frozenset(
    {
        "ancak",
        "artik",
        "bir",
        "bu",
        "bunu",
        "bunun",
        "cok",
        "cunku",
        "daha",
        "degil",
        "degildir",
        "fakat",
        "gerekir",
        "gerekli",
        "gibi",
        "hala",
        "hem",
        "hicbir",
        "icin",
        "ile",
        "kadar",
        "kendi",
        "kullanilabilir",
        "olabilir",
        "olan",
        "olarak",
        "oldu",
        "olmali",
        "olmalidir",
        "olur",
        "sadece",
        "sonra",
        "tum",
        "tumu",
        "uzerinde",
        "ve",
        "veya",
        "yalniz",
        "yalnizca",
        "yeniden",
        "yok",
        "yoktur",
        "zaten",
    }
)

#: The English corpus the lexicon is checked against, and it is deliberately
#: **not** a corpus this file curates: it is the sibling distribution, whose
#: prose nobody wrote with this test in mind. Measured at 608 literals and
#: 4755 word tokens; the floor sits under that so a corpus that vanished -
#: renamed directory, moved package - would be reported rather than silently
#: proving the lexicon clean against nothing.
ENGLISH_PROSE_TREE = Path("packages") / "technocore-conform" / "src"
MINIMUM_ENGLISH_CORPUS_TOKENS = 4000

#: What counts as a *sentence* when the detector is checked for tightness.
#:
#: Measured, not chosen: of the constants the four language modules export,
#: the longest one the detector does not classify as Turkish is
#: ``NEUTRALISED_ALL`` at seven word tokens - a bracketed mark, not a
#: sentence - and the shortest one it does is
#: ``DERIVATION_HONESTY_SENTENCE`` at twenty-five - sixteen before ADR-0014
#: rewrote it. Eight sits in the gap rather than against either edge.
SENTENCE_WORD_TOKENS = 8

#: Floors, so "the scan found nothing" cannot read as "the tree is clean".
#: Measured at 136 files and 6857 literals with the four registries excluded;
#: the six-package rule this replaces opened 45 files.
MINIMUM_SCANNED_FILES = 120
MINIMUM_SCANNED_LITERALS = 6000

#: The plant. Three registered phrases in one sentence, from three different
#: registries - H2's ``testler gecti`` and ``kod calistirildi``, and its
#: ``otomatik onaylandi`` - so a scan applying a narrower registry than the
#: union is visible as a partial catch rather than as a pass.
PLANTED_SENTENCE = "Testler gecti ve kod calistirildi; otomatik onaylandi."

_WORD = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------------------
# Walking the tree
# ---------------------------------------------------------------------------


def _station_api(api_source_root: Path) -> Path:
    return api_source_root / "station_api"


def _packages(api_source_root: Path) -> set[str]:
    """Every package directory under ``station_api``.

    Read off the tree rather than listed, for the reason every walk in
    ``tests/security`` is: a guard built out of the list cannot see what the
    list omits.
    """
    return {
        entry.name
        for entry in _station_api(api_source_root).iterdir()
        if entry.is_dir() and entry.name != "__pycache__"
    }


def _loose_modules(api_source_root: Path) -> set[str]:
    """Every ``.py`` file directly under ``station_api``."""
    return {
        entry.name
        for entry in _station_api(api_source_root).glob("*.py")
        if entry.is_file()
    }


def _scan_files(api_source_root: Path) -> list[Path]:
    """Every file the forbidden-phrase scan opens.

    The whole tree minus the four registries, discovered by walking. There is
    no scope tuple in this function on purpose: reading
    :data:`LANGUAGE_SCAN_PACKAGES` here is precisely the mutation that turns
    this guard back into the defect, and
    :func:`test_the_scan_reaches_a_package_no_list_here_names` is what
    detects it.
    """
    root = _station_api(api_source_root)
    exempt = {root / Path(name) for name in REGISTRY_MODULES_OUTSIDE_THE_SCAN}
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path not in exempt
    )


def _unit_of(api_source_root: Path, path: Path) -> str:
    """The scan unit a file belongs to: a package name, or a module file name.

    ``station_api/tasks/service.py`` is ``tasks``; ``station_api/schemas.py``
    is ``schemas.py``. One helper for both, exactly as ``test_task_states.py``
    writes it, because a unit is looked up the same way whichever kind it is.
    """
    return path.relative_to(_station_api(api_source_root)).parts[0]


def _literals(path: Path) -> list[tuple[int, str]]:
    """``(lineno, value)`` for every string literal in one file.

    Docstrings are included. They are developer prose and not user-visible,
    so including them can only widen the scan - and narrowing an existing
    rule to make a newly covered package quiet is the move this whole file
    exists to refuse.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _forbidden_offenders(api_source_root: Path) -> list[str]:
    """``<relative path>:<line> <phrases>`` for every offending literal."""
    root = _station_api(api_source_root)
    offenders: list[str] = []
    for path in _scan_files(api_source_root):
        for lineno, value in _literals(path):
            found = find_forbidden_phrases(value)
            if found:
                relative = path.relative_to(root).as_posix()
                offenders.append(f"{relative}:{lineno} {found}")
    return offenders


# ---------------------------------------------------------------------------
# The detector
# ---------------------------------------------------------------------------


def _word_tokens(text: str) -> list[str]:
    """The folded word tokens of ``text``.

    Folded with the product's own :func:`fold`, so the detector reads a
    string the same way the registry does - dotless ``i`` mapped, diacritics
    stripped, lookalike letters folded onto Latin. A second normalisation
    would be a second thing to get wrong in the same way.
    """
    return _WORD.findall(fold(text))


def _is_turkish_prose(text: str) -> bool:
    """Whether ``text`` is a sentence this product wrote in Turkish."""
    return bool(set(_word_tokens(text)) & TURKISH_MARKERS)


def _turkish_literals(path: Path) -> list[tuple[int, str]]:
    return [(lineno, value) for lineno, value in _literals(path) if _is_turkish_prose(value)]


def _units(api_source_root: Path) -> dict[str, list[Path]]:
    """Every scan unit, with the files it owns - by walking, never by list."""
    root = _station_api(api_source_root)
    units: dict[str, list[Path]] = {}
    for path in _scan_files(api_source_root):
        units.setdefault(_unit_of(api_source_root, path), []).append(path)
    # A package whose every file is a registry still exists as a unit, and a
    # unit with no files would otherwise disappear from both directions of
    # the silence check at once.
    for entry in root.iterdir():
        if entry.is_dir() and entry.name != "__pycache__":
            units.setdefault(entry.name, [])
    return units


def _turkish_speaking_units(api_source_root: Path) -> set[str]:
    """Which scan units emit user-visible Turkish, derived by walking."""
    return {
        unit
        for unit, paths in _units(api_source_root).items()
        if any(_turkish_literals(path) for path in paths)
    }


# ---------------------------------------------------------------------------
# Throwaway trees
# ---------------------------------------------------------------------------


def _throwaway_tree(tmp_path: Path) -> Path:
    """A source root with every real scan unit present but empty.

    Every package and loose module is created, because an empty result has to
    mean "the planted file was opened and nothing else offended" rather than
    "the walk found a tree with nothing in it".
    """
    root = tmp_path / "station_api"
    root.mkdir(parents=True, exist_ok=True)
    for name in LANGUAGE_SCAN_PACKAGES:
        (root / name).mkdir(exist_ok=True)
        (root / name / "__init__.py").write_text("", encoding="utf-8")
    for name in LANGUAGE_SCAN_MODULES:
        path = root / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# The scope: what the walk finds, against what is written down
# ---------------------------------------------------------------------------


def test_every_package_is_scanned_and_every_scanned_package_exists(
    api_source_root: Path,
) -> None:
    """Both directions, against the tree rather than against the tuple.

    The growth case is a package added next year whose author never hears of
    this rule; the staleness case is a name here with nothing behind it,
    which would leave the parametrised plant tests below silently
    enumerating a package that is not there.
    """
    packages = _packages(api_source_root)
    listed = set(LANGUAGE_SCAN_PACKAGES)

    unlisted = sorted(packages - listed)
    assert not unlisted, (
        "these packages exist under station_api and are not written down in "
        f"LANGUAGE_SCAN_PACKAGES: {unlisted}. The scan already opens them - "
        "it walks - but they also have to be classified: either they emit "
        "user-visible Turkish, or they belong in "
        "UNITS_WITHOUT_USER_VISIBLE_TURKISH with the reason."
    )

    gone = sorted(listed - packages)
    assert not gone, f"LANGUAGE_SCAN_PACKAGES names packages that no longer exist: {gone}"


def test_every_loose_module_is_scanned_and_every_scanned_module_exists(
    api_source_root: Path,
) -> None:
    """The same, one level down - where the eleventh instance lived.

    A rule whose unit is the package treats a ``.py`` file sitting directly
    in ``station_api`` as outside it altogether. ``schemas.py`` alone carries
    324 string literals and is the wire shape of every response.
    """
    modules = _loose_modules(api_source_root)
    listed = set(LANGUAGE_SCAN_MODULES)

    unlisted = sorted(modules - listed)
    assert not unlisted, (
        "these loose modules sit directly under station_api and are not "
        f"written down in LANGUAGE_SCAN_MODULES: {unlisted}"
    )

    gone = sorted(listed - modules)
    assert not gone, f"LANGUAGE_SCAN_MODULES names modules that no longer exist: {gone}"


def test_the_scan_opens_the_whole_tree_rather_than_six_packages(
    api_source_root: Path,
) -> None:
    """Guards the guard: a scan that opened nothing would pass forever.

    The floors are measured (136 files, 6857 literals) and set below the
    measurement, not at it, so ordinary growth does not touch them and a
    collapse does. The rule this replaces opened 45 files.
    """
    files = _scan_files(api_source_root)
    assert len(files) >= MINIMUM_SCANNED_FILES, len(files)

    literals = sum(len(_literals(path)) for path in files)
    assert literals >= MINIMUM_SCANNED_LITERALS, literals

    opened = {_unit_of(api_source_root, path) for path in files}
    missing = sorted(set(LANGUAGE_SCAN_MODULES) - opened)
    assert not missing, f"the scan opens no file for these loose modules: {missing}"


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------


def test_no_string_literal_under_station_api_carries_a_forbidden_claim(
    api_source_root: Path,
) -> None:
    """Every literal in the tree, against the union of all four registries.

    The five per-package tests still run and still assert what they always
    did. This is the floor under them: it is what the twelve uncovered
    packages, the fourteen loose modules and the nine unscanned route files
    had nothing of.
    """
    offenders = _forbidden_offenders(api_source_root)
    assert offenders == [], f"forbidden phrases in source strings: {offenders}"


@pytest.mark.parametrize("package", LANGUAGE_SCAN_PACKAGES)
def test_a_planted_forbidden_claim_is_reported_from_every_scanned_package(
    package: str, tmp_path: Path
) -> None:
    """The scan, driven once per package it claims to cover.

    This is the test that would have failed on the day the twelfth instance
    was written into a commit message instead of fixed: eighteen packages,
    twelve of which were invisible to every existing spelling of this rule.
    """
    root = _throwaway_tree(tmp_path)
    planted = root / "station_api" / package / "planted.py"
    planted.write_text(f'LABEL = "{PLANTED_SENTENCE}"\n', encoding="utf-8")

    offenders = _forbidden_offenders(root)

    assert len(offenders) == 1, offenders
    assert offenders[0].startswith(f"{package}/planted.py:1"), offenders
    assert "testler gecti" in offenders[0]
    assert "kod calistirildi" in offenders[0]
    assert "otomatik onaylandi" in offenders[0]


@pytest.mark.parametrize("module", LANGUAGE_SCAN_MODULES)
def test_a_planted_forbidden_claim_is_reported_from_every_scanned_loose_module(
    module: str, tmp_path: Path
) -> None:
    """The same drive for the fourteen files a package-shaped rule cannot see.

    In place, on a file that already exists, because that is the plant with
    nothing else to notice it: no new file, no changed file list, nothing for
    ``test_tracked_sources.py`` to react to.
    """
    root = _throwaway_tree(tmp_path)
    planted = root / "station_api" / module
    planted.write_text(f'LABEL = "{PLANTED_SENTENCE}"\n', encoding="utf-8")

    offenders = _forbidden_offenders(root)

    assert len(offenders) == 1, offenders
    assert offenders[0].startswith(f"{module}:1"), offenders


def test_the_scan_reaches_a_package_no_list_here_names(tmp_path: Path) -> None:
    """The anti-fake half: the scan walks, so it finds what no list mentions.

    A package called ``newcomer`` appears in no constant in this file and in
    no ``*_language.py`` test. A scan scoped by a tuple - the defect being
    closed - reports nothing here; this one reports the plant.
    """
    root = _throwaway_tree(tmp_path)
    assert "newcomer" not in LANGUAGE_SCAN_PACKAGES

    package = root / "station_api" / "newcomer"
    package.mkdir()
    (package / "service.py").write_text(
        f'DETAIL = "{PLANTED_SENTENCE}"\n', encoding="utf-8"
    )

    offenders = _forbidden_offenders(root)
    assert len(offenders) == 1, offenders
    assert offenders[0].startswith("newcomer/service.py:1"), offenders


def test_the_scan_applies_the_union_of_every_registry() -> None:
    """Twenty-seven phrases, not the six or thirteen a package knows about.

    The scan a package wrote for itself applies that package's registry. The
    tree-wide one has no package, so it applies the widest - and that has to
    be checked rather than assumed, because ``proof.language`` composing the
    other three is a property of that module, not a guarantee.
    """
    for registry in (
        EVIDENCE_FORBIDDEN_PHRASES,
        WORK_SCAN_FORBIDDEN_PHRASES,
        AGENT_FORBIDDEN_PHRASES,
    ):
        assert set(registry) <= set(ALL_FORBIDDEN_PHRASES)

    assert len(ALL_FORBIDDEN_PHRASES) == len(set(ALL_FORBIDDEN_PHRASES))
    assert len(ALL_FORBIDDEN_PHRASES) == 27

    # And the plant really does exercise three registries at once, so a scan
    # that quietly narrowed to one of them is a partial catch rather than a
    # pass.
    assert len(find_forbidden_phrases(PLANTED_SENTENCE)) == 3


def test_the_registry_exemption_is_exactly_four_files_that_are_registries(
    api_source_root: Path,
) -> None:
    """The one exemption, pinned against what it claims about each file.

    A file keeps this exemption only while it is still a registry: it has to
    exist, define ``FORBIDDEN_PHRASES``, and actually spell a registered
    phrase out. A module renamed, emptied, or turned into something else
    would otherwise keep a hole open behind a familiar filename - which is
    the failure mode this repository has closed eleven times.
    """
    root = _station_api(api_source_root)
    assert len(REGISTRY_MODULES_OUTSIDE_THE_SCAN) == 4

    for name, reason in sorted(REGISTRY_MODULES_OUTSIDE_THE_SCAN.items()):
        path = root / Path(name)
        assert path.is_file(), f"{name}: exempted but no such file"
        assert reason.strip(), f"{name}: exempted with no reason"

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        defines = any(
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "FORBIDDEN_PHRASES"
            for node in ast.walk(tree)
        )
        assert defines, f"{name}: exempted as a registry but defines no FORBIDDEN_PHRASES"

        spelled = [value for _, value in _literals(path) if find_forbidden_phrases(value)]
        assert spelled, f"{name}: exempted as a registry but spells no registered phrase"

    scanned = {path.relative_to(root).as_posix() for path in _scan_files(api_source_root)}
    assert not scanned & set(REGISTRY_MODULES_OUTSIDE_THE_SCAN)


# ---------------------------------------------------------------------------
# Which units speak, derived by walking
# ---------------------------------------------------------------------------


def test_every_scan_unit_either_speaks_turkish_or_is_a_written_down_silence(
    api_source_root: Path,
) -> None:
    """The derivation, both directions, against the tree.

    A scan that covers everything is trivially green wherever nothing is
    said, so "green" would mean two different things in one run unless each
    unit is classified. The classification is walked, not read: a unit that
    starts addressing a user is reported the same week rather than the year
    somebody notices.

    The staleness direction is the sharper one. A reason saying what a
    package does is exactly the sentence that goes on reading as though it
    still described the package after the package changed.
    """
    speaking = _turkish_speaking_units(api_source_root)
    silent = set(UNITS_WITHOUT_USER_VISIBLE_TURKISH)
    every = set(_units(api_source_root))

    unclassified = sorted(every - speaking - silent)
    assert not unclassified, (
        "these scan units emit no user-visible Turkish and nobody has said "
        f"why: {unclassified}. Write the reason - what the unit does - in "
        "UNITS_WITHOUT_USER_VISIBLE_TURKISH. 'Not applicable' is not a reason."
    )

    stale = sorted(speaking & silent)
    assert not stale, (
        "these units are written down as emitting no user-visible Turkish "
        f"and now do: {stale}. The reason beside each one is describing a "
        "unit that no longer exists; rewrite it or remove the entry."
    )

    assert speaking, "the derivation classified nothing as speaking Turkish"


def test_every_written_down_silence_names_a_unit_that_exists_with_a_reason(
    api_source_root: Path,
) -> None:
    """A silence recorded for a unit the tree does not have says nothing."""
    every = set(_units(api_source_root))
    for unit, reason in sorted(UNITS_WITHOUT_USER_VISIBLE_TURKISH.items()):
        assert unit in every, f"{unit}: written down as silent but is not a scan unit"
        assert reason.strip(), f"{unit}: written down as silent with no reason"
        assert len(reason.split()) >= 8, f"{unit}: the reason says nothing: {reason!r}"


def test_the_derivation_sees_a_package_no_list_here_names(tmp_path: Path) -> None:
    """The anti-fake half for the derivation, matching the one for the scan.

    Same mutation, other half: a derivation that read
    :data:`LANGUAGE_SCAN_PACKAGES` - or worse, the silence table - would
    classify this package as neither speaking nor silent and report nothing,
    which is how a guard that reads the list it guards passes forever.
    """
    root = _throwaway_tree(tmp_path)
    assert "newcomer" not in LANGUAGE_SCAN_PACKAGES
    assert "newcomer" not in UNITS_WITHOUT_USER_VISIBLE_TURKISH

    package = root / "station_api" / "newcomer"
    package.mkdir()
    (package / "views.py").write_text(
        'DETAIL = "Bu gorev icin bir kayit uretildi."\n', encoding="utf-8"
    )

    assert "newcomer" in _turkish_speaking_units(root)


def test_a_package_that_says_nothing_is_not_reported_as_speaking(
    tmp_path: Path,
) -> None:
    """The other side of the same throwaway tree, so the detector can say no.

    A detector that classified every unit as speaking would make the silence
    table unreachable and the whole classification decorative.
    """
    root = _throwaway_tree(tmp_path)
    package = root / "station_api" / "newcomer"
    package.mkdir()
    (package / "codes.py").write_text(
        'CODE = "host_not_allowed"\nHEADER = "X-Station-Request-Id"\n',
        encoding="utf-8",
    )

    assert "newcomer" not in _turkish_speaking_units(root)


# ---------------------------------------------------------------------------
# The detector, proved in both directions
# ---------------------------------------------------------------------------


def test_no_turkish_marker_is_an_english_word(repo_root: Path) -> None:
    """Not too loose, against a corpus this file does not own.

    ``packages/technocore-conform`` is the sibling distribution: English
    docstrings and English error text, written years of commits before this
    guard and by nobody thinking about it. If a marker were also an English
    word it would score there, and ``her``, ``once`` and ``var`` - all
    genuine Turkish words - are absent from the lexicon for exactly that
    reason.

    The corpus size is asserted first. A lexicon proves nothing against an
    empty tree, and a renamed directory would otherwise turn this test green
    by deleting its own evidence.
    """
    corpus = repo_root / ENGLISH_PROSE_TREE
    assert corpus.is_dir(), corpus

    tokens = 0
    offenders: list[str] = []
    for path in sorted(corpus.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for lineno, value in _literals(path):
            words = _word_tokens(value)
            tokens += len(words)
            hits = sorted(set(words) & TURKISH_MARKERS)
            if hits:
                offenders.append(f"{path.name}:{lineno} {hits}")

    assert tokens >= MINIMUM_ENGLISH_CORPUS_TOKENS, tokens
    assert offenders == [], (
        "these markers fired on English prose, so they are not Turkish-only "
        f"and would classify an English log line as a user-visible sentence: {offenders}"
    )


def test_the_detector_sees_every_sentence_this_product_certifies() -> None:
    """Not too tight, against this product's own certified wording.

    A detector that reported clean forever is worse than no detector, so it
    is measured against the sentences the four language modules publish as
    the wording this product is allowed to use. Every one of them at
    :data:`SENTENCE_WORD_TOKENS` or longer has to be seen.

    The corpus is read off the modules rather than typed here, so a sentence
    added to any of them joins this test on the same commit.
    """
    import importlib

    sentences: list[tuple[str, str]] = []
    for package in ("evidence", "workscan", "agent", "proof"):
        module = importlib.import_module(f"station_api.{package}.language")
        for name in module.__all__:
            value = getattr(module, name)
            if isinstance(value, str):
                sentences.append((f"{package}.{name}", value))

    assert sentences, "the language modules exported no string constants"

    checked = [
        (name, text)
        for name, text in sentences
        if len(_word_tokens(text)) >= SENTENCE_WORD_TOKENS
    ]
    assert len(checked) >= 8, checked

    missed = [name for name, text in checked if not _is_turkish_prose(text)]
    assert missed == [], (
        "the detector cannot see this product's own user-visible sentences, "
        f"so it would report a package clean while it speaks: {missed}"
    )

    # And the gap the threshold sits in is real rather than assumed: nothing
    # between seven and twenty-five tokens is exported at all, so eight is not
    # a number tuned against an edge. The upper number was sixteen until
    # ADR-0014 replaced the shortest of these sentences with a longer one; the
    # gap the threshold sits in only widened, which is the property this pair
    # of assertions is about rather than either figure on its own.
    lengths = sorted(len(_word_tokens(text)) for _, text in sentences)
    assert max(n for n in lengths if n < SENTENCE_WORD_TOKENS) == 7
    assert min(n for n in lengths if n >= SENTENCE_WORD_TOKENS) == 25


def test_the_detector_sees_the_planted_sentence_and_not_a_machine_code() -> None:
    """The narrow drive, both ways, on strings this file owns."""
    assert _is_turkish_prose(PLANTED_SENTENCE)
    assert _is_turkish_prose("Bu kayit yerel arsivde tutulur.")

    for machine in (
        "host_not_allowed",
        "X-Station-CSRF",
        "application/json",
        "UPDATE evidence_record SET capture_generation = room_generation",
        "Unhandled exception while serving a request; request_id=%s",
    ):
        assert not _is_turkish_prose(machine), machine


def test_the_detector_reads_a_string_the_way_the_registry_does() -> None:
    """One normalisation, not two.

    The registry folds - dotless ``i`` mapped, diacritics stripped, invisible
    characters dropped, lookalikes folded onto Latin. A detector that
    lowercased instead would miss the spelling this product's documents are
    written in, which is IMP-384's mistake with a different subject.
    """
    tail = "u kayit yerel arsivde tutulur."
    for spelling in (
        "Bu kayıt yerel arşivde tutulur.",
        "BU KAYIT YEREL ARSIVDE TUTULUR.",
        # U+0432 CYRILLIC SMALL LETTER VE, drawn as ``b``, standing in for the
        # ``b`` of ``bu``, and U+200C ZERO WIDTH NON-JOINER inside the same
        # word. Built with ``chr`` rather than written into the literal, for
        # the reason ``evidence/language.py`` gives about its own dotless i:
        # the linter's confusables rule is right to be suspicious of a bare
        # lookalike in source, and an invisible character in source is worse.
        chr(0x0432) + tail,
        "b" + chr(0x200C) + tail,
    ):
        assert _is_turkish_prose(spelling), spelling


# ---------------------------------------------------------------------------
# The three silences that make a specific claim, pinned
# ---------------------------------------------------------------------------


def test_the_conformance_wording_lives_in_the_route_that_is_scanned(
    api_source_root: Path,
) -> None:
    """``conformance``'s reason names a file; the file is checked.

    The entry says the wording a person reads about conformance is written in
    ``routes/conformance.py`` and that this scan covers it. Both halves are
    claims about the tree, and a claim about the tree that nothing measures
    is how an exemption reason decays into a name.
    """
    route = _station_api(api_source_root) / "routes" / "conformance.py"
    assert route.is_file()
    assert route in _scan_files(api_source_root)
    assert _turkish_literals(route), (
        "conformance's silence is justified by its route carrying the "
        "wording; that route now carries no Turkish, so the reason is stale"
    )


def test_the_security_package_answers_with_codes_rather_than_sentences(
    api_source_root: Path,
) -> None:
    """``security``'s reason names six codes; the six are checked.

    "It answers with machine codes, not sentences" is the kind of sentence
    that keeps reading true after somebody puts a Turkish detail in one of
    these refusals. So each code has to still be spelled in the package, and
    each has to still be a bare token.
    """
    package = _station_api(api_source_root) / "security"
    spelled = {value for path in package.rglob("*.py") for _, value in _literals(path)}

    for code in SECURITY_REFUSAL_CODES:
        assert code in spelled, f"{code} is no longer written in the security package"
        assert code == code.lower()
        assert " " not in code
        assert not _is_turkish_prose(code)


def test_the_download_stem_is_one_word_and_no_registered_phrase_is(
    api_source_root: Path,
) -> None:
    """``downloads.py``'s reason turns on a count; the count is measured.

    The module does emit one Turkish token - the default filename stem - and
    the reason it is still a silence is arithmetic rather than judgement: a
    stem is one word and the shortest registered phrase is two, so no stem
    can carry one. If either half stopped being true the entry would be
    wrong, and this is what says so.
    """
    assert DEFAULT_STEM == "indirme"
    assert len(_word_tokens(DEFAULT_STEM)) == 1

    shortest = min(len(_word_tokens(phrase)) for phrase in ALL_FORBIDDEN_PHRASES)
    assert shortest >= 2, "a one-word forbidden phrase would make the stem reachable"

    module = _station_api(api_source_root) / "downloads.py"
    assert _turkish_literals(module) == []
