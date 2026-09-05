"""The security-invariant table has to name tests that exist.

``AGENTS.md`` INV-06 says every line of ``docs/security-invariants.md``
matches a test. Nothing measured that, and the document drifted three times
before anybody noticed: SI-211 and SI-277 named functions that had been
renamed out from under them, and SI-243's ``test_the_credential_is_absent_from_*``
wildcard silently stopped covering its seventh surface when that surface was
given a name the glob does not match
(``test_no_artefact_anywhere_in_the_data_directory_carries_the_credential``).

A wrong test name is worse than no test name. It reads as evidence, it
survives review, and the invariant it claims to defend can be deleted without
anything turning red. So the table is parsed here and every name in it is
resolved against the suite (ADR-0011 2).

Three rules, and they are deliberately different in strength:

* ``file.py::name`` is **fully qualified** and must exist in exactly that
  file. Nothing weaker would catch a test that moved between files.
* ``::name`` is the table's continuation form - the file is whichever one the
  surrounding rows named, and the document is not consistent about which row
  that is. It is checked as "this name exists somewhere in ``tests/``", which
  is what the invariant claims and all this form can honestly support.
* **Every row must produce at least one of those**, or a vitest file name.
  The first version of this file resolved the citations it found and never
  asked whether a row carried one, so a row whose Test column said
  ``Aşama 2`` - which is literally what SI-38 said before Paket J - was as
  green as a row naming a real function. Rows that legitimately hold no
  pytest function are listed one by one in
  :data:`_ROWS_WITHOUT_A_PYTHON_TEST` with the reason; the list is checked
  for growth **and** for staleness, so it cannot quietly become a bucket.

Patterns are refused, and refused loudly. The first version only looked for
``*``; ``?``, a character class and a regex were parsed to nothing and
**dropped in silence**, which cost the row its whole Test column without a
word. Now any backticked span containing ``::`` that this scan cannot
resolve is a failure. A pytest parameter id is the single bracketed
exception, and it is only accepted when the function it names really carries
a ``parametrize`` decorator - otherwise ``name[abc]`` is a glob wearing a
test id.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: A row of any of the tables: ``| SI-123 | ... |``.
_ROW = re.compile(r"^\|\s*(SI-\d+)\s*\|")

#: Everything in backticks. The Test column is prose around code spans.
_SPAN = re.compile(r"`([^`]+)`")

#: A Python test citation: an optional ``.py`` file, ``::``, a name that
#: starts with ``test``, and at most one trailing pytest parameter id.
_PY_TEST = re.compile(
    r"\A(?P<file>[\w./-]*\.py)?::(?P<name>test\w*)(?:\[(?P<param>[\w.-]+)\])?\Z"
)

#: A citation of a *source* member rather than a test; SI-266 points at two
#: docstrings. The file half is mandatory here - a bare ``::member`` would be
#: indistinguishable from a misspelt test name and must stay an error.
_PY_MEMBER = re.compile(
    r"\A(?P<file>[\w./-]*\.py)::(?P<member>[A-Za-z_]\w*(?:\.\w+)*)\Z"
)

#: A case-name citation into a browser suite (``file.spec.ts::case name``,
#: ``file.test.tsx::case name``, or the bare ``::case name`` continuation).
#: Playwright and vitest case names carry spaces, and that is exactly what
#: separates them from a Python identifier that failed to parse.
_CASE = re.compile(
    r"\A(?P<file>[\w./-]*\.(?:spec\.ts|test\.tsx))?::(?P<case>\S+(?: +\S+)+)\Z"
)

#: Frontend test files the table cites by bare filename.
_FRONTEND_FILE = re.compile(r"\A[\w.-]+\.test\.tsx\Z")

#: What makes a span a pattern instead of a citation. ``[`` and ``]`` are
#: absent on purpose: a pytest parameter id needs them, and they are admitted
#: only by the narrow bracketed tail of :data:`_PY_TEST` - after which the
#: parameter id is checked against a real ``parametrize`` decorator.
_WILDCARD = re.compile(r"[*?()|+^$\\{}]")

#: A scan with no floor is vacuous. The table carried 329 rows and 940
#: resolvable citations when this was last measured; a scan that suddenly
#: finds far fewer has stopped reading the document rather than found it
#: clean. The bounds sit just under that measurement on purpose - the first
#: version allowed 250/700, which is 79 rows and 240 citations of silent
#: room. (These are counts of table rows, not of tests; ADR-0011 1 keeps
#: test counts in the verification report and nowhere else.)
_MINIMUM_ROWS = 325
_MINIMUM_REFERENCES = 930

#: Rows that hold no pytest function, one by one, with the reason. This is a
#: **counted list, not a pattern**: a new row that cites nothing lands here
#: only by somebody writing it down, and a row that gains a test and is left
#: here is reported as stale. Both directions are failures.
_ROWS_WITHOUT_A_PYTHON_TEST: dict[str, str] = {
    "SI-261": (
        "Playwright. What holds it is apps/station-web/e2e (global-setup and "
        "two specs); pytest has nothing to name. The spec files it cites are "
        "checked for existence like any other citation."
    ),
    "SI-266": (
        "Accepted limitation, not a closed one. What holds it is two source "
        "docstrings, cited as file.py::member; there is no test to name and "
        "writing one would be writing a test for a paragraph."
    ),
    "SI-270": (
        "Accepted limitation. What holds it is a module docstring saying what "
        "is deliberately absent; an absence of scrubbing has no test."
    ),
}


@dataclass(frozen=True)
class _Citation:
    """One backticked span from a Test column that contains ``::``."""

    line: int
    invariant: str
    span: str
    #: ``test``, ``member``, ``case`` or ``broken``.
    kind: str
    file: str | None
    name: str
    param: str | None


def _is_parametrized(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Does this function carry a ``parametrize`` decorator?"""
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "parametrize":
            return True
    return False


def _python_tests(tests_root: Path) -> dict[str, dict[str, bool]]:
    """``{file name: {test name: is parametrized}}`` for the whole suite."""
    found: dict[str, dict[str, bool]] = {}
    for path in sorted(tests_root.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        into = found.setdefault(path.name, {})
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test"):
                continue
            into[node.name] = into.get(node.name, False) or _is_parametrized(node)
    return found


def _source_modules(repo_root: Path) -> frozenset[str]:
    """Every shipped ``.py`` path, relative to its source root."""
    roots = [repo_root / "apps" / "station-api" / "src"]
    roots.extend(sorted((repo_root / "packages").glob("*/src")))
    return frozenset(
        path.relative_to(root).as_posix()
        for root in roots
        if root.is_dir()
        for path in root.rglob("*.py")
    )


def _vitest_files(repo_root: Path) -> frozenset[str]:
    web = repo_root / "apps" / "station-web" / "src"
    return frozenset(path.name for path in web.rglob("*.test.tsx"))


def _playwright_specs(repo_root: Path) -> frozenset[str]:
    e2e = repo_root / "apps" / "station-web" / "e2e"
    return frozenset(path.name for path in e2e.rglob("*.spec.ts"))


def _rows(document: Path) -> list[tuple[int, str, str]]:
    """``(line number, SI id, Test column)`` for every table row."""
    rows: list[tuple[int, str, str]] = []
    for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
        match = _ROW.match(line)
        if match is None:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:  # a row without a Test column is a different table
            continue
        rows.append((number, match.group(1), cells[-2]))
    return rows


def _classify(line: int, invariant: str, span: str) -> _Citation:
    """Sort one ``::`` span into a kind. Unsortable is ``broken``, never skipped."""
    if _WILDCARD.search(span):
        return _Citation(line, invariant, span, "broken", None, "", None)
    test = _PY_TEST.match(span)
    if test is not None:
        return _Citation(
            line, invariant, span, "test", test["file"], test["name"], test["param"]
        )
    member = _PY_MEMBER.match(span)
    if member is not None:
        return _Citation(
            line, invariant, span, "member", member["file"], member["member"], None
        )
    case = _CASE.match(span)
    if case is not None:
        return _Citation(line, invariant, span, "case", case["file"], case["case"], None)
    return _Citation(line, invariant, span, "broken", None, "", None)


def _citations(document: Path) -> list[_Citation]:
    """Every backticked span carrying ``::``, classified rather than filtered."""
    out: list[_Citation] = []
    for number, invariant, cell in _rows(document):
        for raw in _SPAN.findall(cell):
            span = raw.strip()
            if "::" not in span:
                continue
            out.append(_classify(number, invariant, span))
    return out


def _test_citations(document: Path) -> list[_Citation]:
    return [cite for cite in _citations(document) if cite.kind == "test"]


def _cited_frontend_files(document: Path) -> dict[str, set[str]]:
    """``{vitest file name: SI ids that name it}``, bare or before ``::``."""
    named: dict[str, set[str]] = {}
    for _, invariant, cell in _rows(document):
        for raw in _SPAN.findall(cell):
            span = raw.strip()
            head = span.split("::", 1)[0] if "::" in span else span
            name = head.rsplit("/", 1)[-1]
            if _FRONTEND_FILE.match(name):
                named.setdefault(name, set()).add(invariant)
    return named


def _assert_every_citation_resolves(document: Path, repo_root: Path) -> None:
    """INV-06, measured. The body of the real test, callable on a planted document.

    It lives here rather than inside the test so the deny-side probe can drive
    **this** code instead of a second implementation of it. The probe used to
    re-implement the parser and the lookup, which meant the branch that
    resolves a qualified citation could be neutralised and the probe stayed
    green - it was guarding a copy of the code, not the code.
    """
    by_file = _python_tests(repo_root / "tests")
    everywhere: dict[str, bool] = {}
    for names in by_file.values():
        for name, parametrized in names.items():
            everywhere[name] = everywhere.get(name, False) or parametrized
    sources = _source_modules(repo_root)
    vitest = _vitest_files(repo_root)
    specs = _playwright_specs(repo_root)

    assert by_file, "no pytest files found; the scan is reading the wrong tree"
    assert sources, "no source modules found; the scan is reading the wrong tree"
    assert vitest, "no vitest files found; the scan is reading the wrong tree"
    assert specs, "no playwright specs found; the scan is reading the wrong tree"

    missing: list[str] = []
    for cite in _citations(document):
        where = f"{document.name}:{cite.line} {cite.invariant}"
        if cite.kind == "broken":
            missing.append(
                f"{where}: {cite.span!r} contains :: but is not a citation this scan "
                "can resolve; a pattern is not a citation"
            )
            continue
        if cite.kind == "member":
            assert cite.file is not None
            if not any(
                path == cite.file or path.endswith("/" + cite.file) for path in sources
            ):
                missing.append(f"{where}: no source module named {cite.file}")
            continue
        if cite.kind == "case":
            if cite.file is None:
                continue
            name = cite.file.rsplit("/", 1)[-1]
            present = specs if name.endswith(".spec.ts") else vitest
            if name not in present:
                missing.append(f"{where}: no browser suite file named {name}")
            continue

        if cite.file is not None:
            names = by_file.get(cite.file)
            if names is None:
                missing.append(f"{where}: no test file named {cite.file}")
                continue
            if cite.name not in names:
                elsewhere = sorted(f for f, n in by_file.items() if cite.name in n)
                missing.append(
                    f"{where}: {cite.name} is not in {cite.file}"
                    + (f" (it is in {elsewhere})" if elsewhere else " (or anywhere)")
                )
                continue
            parametrized = names[cite.name]
        else:
            if cite.name not in everywhere:
                missing.append(
                    f"{where}: no test named {cite.name} anywhere under tests/"
                )
                continue
            parametrized = everywhere[cite.name]
        if cite.param is not None and not parametrized:
            missing.append(
                f"{where}: {cite.name} is cited with the parameter id "
                f"[{cite.param}] but carries no parametrize decorator; that "
                "bracket is a glob wearing a test id"
            )

    assert not missing, "\n".join(missing)


def _assert_every_row_cites_a_test(
    document: Path, exempt: dict[str, str] | None = None
) -> None:
    """Every row resolves to at least one test, or is a written-down exception."""
    if exempt is None:
        exempt = _ROWS_WITHOUT_A_PYTHON_TEST

    cited = {cite.invariant for cite in _test_citations(document)}
    for invariants in _cited_frontend_files(document).values():
        cited |= invariants

    rows = _rows(document)
    assert rows, "no rows parsed; the scan is reading the wrong document"

    silent = {invariant for _, invariant, _ in rows} - cited
    by_id = {invariant: (line, cell) for line, invariant, cell in rows}

    unexplained = sorted(silent - set(exempt))
    assert not unexplained, "\n".join(
        f"{document.name}:{by_id[invariant][0]} {invariant}: the Test column "
        f"names nothing this scan can resolve ({by_id[invariant][1]!r}). "
        "Cite a test, or add the row to _ROWS_WITHOUT_A_PYTHON_TEST with the "
        "reason it holds without one."
        for invariant in unexplained
    )

    stale = sorted(set(exempt) - silent)
    assert not stale, (
        "these rows are listed as holding no pytest function but now cite one; "
        f"drop them from _ROWS_WITHOUT_A_PYTHON_TEST: {stale}"
    )


def _planted_document(cell: str) -> str:
    """A one-row throwaway table, so probes never ship inside the real one."""
    return (
        "| ID | Değişmez | Beklenen | Test | Durum |\n"
        "|---|---|---|---|---|\n"
        f"| SI-01 | bir | iki | {cell} | A1 |\n"
    )


@pytest.fixture(name="document")
def _document(repo_root: Path) -> Path:
    return repo_root / "docs" / "security-invariants.md"


def test_the_document_is_where_the_contract_says_it_is(document: Path) -> None:
    """Guards the guard: a missing file would make every scan below vacuous."""
    assert document.is_file(), document


def test_the_scan_actually_reads_the_table(document: Path) -> None:
    """Guards the guard, again, and this one has teeth.

    Every other assertion in this file is a loop over what the parser found.
    A parser that found nothing - a changed row prefix, a renamed column -
    would pass all of them and report a clean document forever. That failure
    mode is the reason SI-243 went unnoticed, so it is asserted rather than
    assumed.
    """
    rows = _rows(document)
    references = _test_citations(document)

    assert len(rows) >= _MINIMUM_ROWS, len(rows)
    assert len(references) >= _MINIMUM_REFERENCES, len(references)
    assert {cite.invariant for cite in references} >= {
        "SI-01",
        "SI-51",
        "SI-211",
        "SI-243",
        "SI-277",
    }


def test_every_test_named_in_the_table_exists(document: Path, repo_root: Path) -> None:
    """INV-06, measured. Each citation resolves to a function in the suite."""
    _assert_every_citation_resolves(document, repo_root)


def test_every_row_names_a_test_that_resolves(document: Path) -> None:
    """A row with no resolvable citation is the failure the table was built to stop.

    SI-38's Test column said ``Aşama 2``, and SI-49/50/51/52/55 sat in the
    list with nothing at all, for as long as the only rule was "resolve what
    you find". Resolving what you find says nothing about a row that offers
    nothing to resolve.
    """
    _assert_every_row_cites_a_test(document)


def test_no_citation_is_a_wildcard(
    document: Path, repo_root: Path, tmp_path: Path
) -> None:
    """A glob is not a citation, and neither is a ``?``, a class or a regex.

    SI-243 cited ``test_the_credential_is_absent_from_*`` and claimed seven
    surfaces. Six matched. The seventh - the data directory - is named
    ``test_no_artefact_anywhere_in_the_data_directory_carries_the_credential``
    and the glob never reached it, so the strongest-sounding row in the
    OpenCode section was quietly one surface short.

    Only ``*`` was ever refused. ``?`` and ``[abc]`` and a regex went in
    through a different door: they failed the reference pattern, and a span
    that failed the pattern was **skipped without a word**, so the row lost
    its entire Test column and stayed green. All four forms are driven here.
    """
    unresolvable = [
        f"{document.name}:{cite.line} {cite.invariant}: {cite.span}"
        for cite in _citations(document)
        if cite.kind == "broken"
    ]
    assert not unresolvable, "\n".join(unresolvable)

    forms = (
        "::test_the_credential_is_absent_from_*",
        "::test_the_credential_is_absent_from_?",
        "::test_the_credential_is_absent_from_.*",
        # A real, existing, *unparametrized* test wearing a character class.
        # This is the form that used to be truncated into a valid name.
        "::test_launcher_binds_only_loopback[abc]",
    )
    for index, form in enumerate(forms):
        planted = tmp_path / f"wildcard-{index}.md"
        planted.write_text(_planted_document(f"`{form}`"), encoding="utf-8")
        with pytest.raises(AssertionError):
            _assert_every_citation_resolves(planted, repo_root)


def test_every_frontend_test_file_the_table_names_exists(
    document: Path, repo_root: Path
) -> None:
    """The vitest half of the table is cited by bare file name, not by path."""
    present = _vitest_files(repo_root)
    missing = sorted(set(_cited_frontend_files(document)) - present)

    assert present, "no vitest files found; the scan is reading the wrong tree"
    assert not missing, missing


def test_the_scan_would_catch_a_planted_reference(
    repo_root: Path, tmp_path: Path
) -> None:
    """The deny side, on throwaway documents, so the probe never ships.

    It calls the same helpers the real tests call. The first version of this
    probe re-implemented the parser and the lookup, so the branch that
    resolves a qualified citation could be turned off entirely and the probe
    stayed green.
    """
    real = "test_bind.py::test_launcher_binds_only_loopback"

    control = tmp_path / "control.md"
    control.write_text(_planted_document(f"`{real}`"), encoding="utf-8")
    _assert_every_citation_resolves(control, repo_root)
    _assert_every_row_cites_a_test(control, exempt={})

    planted: dict[str, str] = {
        "a name nobody wrote": "test_bind.py::test_this_name_was_never_written",
        "a real name in the wrong file": (
            "test_session.py::test_launcher_binds_only_loopback"
        ),
        "a bare name nobody wrote": "::test_this_name_was_never_written",
        "a source module that is not there": "vault/no_such_module.py::_atomic_write",
        "a spec file that is not there": "no-such.spec.ts::a case that is not there",
    }
    for label, citation in planted.items():
        document = tmp_path / f"{label.replace(' ', '-')}.md"
        document.write_text(_planted_document(f"`{citation}`"), encoding="utf-8")
        with pytest.raises(AssertionError):
            _assert_every_citation_resolves(document, repo_root)

    # And the row-level rule: a Test column that offers nothing to resolve.
    for label, cell in {
        "a stage name": "Aşama 2",
        "an empty column": "",
        "prose in backticks": "`Stage B: schema boundaries`",
    }.items():
        document = tmp_path / f"silent-{label.replace(' ', '-')}.md"
        document.write_text(_planted_document(cell), encoding="utf-8")
        with pytest.raises(AssertionError):
            _assert_every_row_cites_a_test(document, exempt={})
