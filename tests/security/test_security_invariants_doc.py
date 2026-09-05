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

Two rules, and they are deliberately different in strength:

* ``file.py::name`` is **fully qualified** and must exist in exactly that
  file. Nothing weaker would catch a test that moved between files.
* ``::name`` is the table's continuation form - the file is whichever one the
  surrounding rows named, and the document is not consistent about which row
  that is. It is checked as "this name exists somewhere in ``tests/``", which
  is what the invariant claims and all this form can honestly support.

Wildcards are refused outright in both forms. A glob cannot be resolved to a
test, so a glob is not a citation; SI-243 is the proof that one rots quietly.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: A row of any of the tables: ``| SI-123 | ... |``.
_ROW = re.compile(r"^\|\s*(SI-\d+)\s*\|")

#: Everything in backticks. The Test column is prose around code spans.
_SPAN = re.compile(r"`([^`]+)`")

#: A backticked span that is a Python test reference.
_REFERENCE = re.compile(r"\A(?P<file>[\w./-]*\.py)?::(?P<name>[\w*\[\]-]+)\Z")

#: Frontend test files the table cites by bare filename.
_FRONTEND_FILE = re.compile(r"\A[\w.-]+\.test\.tsx\Z")

#: The count below the scan is vacuous. The table carried well over eight
#: hundred references when this test was written; a scan that suddenly finds a
#: handful has stopped reading the document rather than found it clean.
_MINIMUM_REFERENCES = 700


def _python_test_names(tests_root: Path) -> dict[str, frozenset[str]]:
    """Every ``test_*`` function in the suite, keyed by bare file name."""
    found: dict[str, set[str]] = {}
    for path in sorted(tests_root.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test_")
        }
        found.setdefault(path.name, set()).update(names)
    return {name: frozenset(values) for name, values in found.items()}


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


def _references(document: Path) -> list[tuple[int, str, str | None, str]]:
    """``(line, SI id, file or None, test name)`` for every citation."""
    out: list[tuple[int, str, str | None, str]] = []
    for number, invariant, cell in _rows(document):
        for span in _SPAN.findall(cell):
            match = _REFERENCE.match(span.strip())
            if match is None:
                continue
            name = match.group("name").split("[")[0]
            if not name.startswith("test"):
                continue
            out.append((number, invariant, match.group("file"), name))
    return out


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
    references = _references(document)

    assert len(rows) >= 250, len(rows)
    assert len(references) >= _MINIMUM_REFERENCES, len(references)
    assert {invariant for _, invariant, _, _ in references} >= {
        "SI-01",
        "SI-51",
        "SI-211",
        "SI-243",
        "SI-277",
    }


def test_every_test_named_in_the_table_exists(document: Path, repo_root: Path) -> None:
    """INV-06, measured. Each citation resolves to a function in the suite."""
    by_file = _python_test_names(repo_root / "tests")
    everywhere = frozenset().union(*by_file.values())

    missing: list[str] = []
    for line, invariant, file_name, name in _references(document):
        where = f"{document.name}:{line} {invariant}"
        if file_name is not None:
            if file_name not in by_file:
                missing.append(f"{where}: no test file named {file_name}")
            elif name not in by_file[file_name]:
                elsewhere = sorted(f for f, n in by_file.items() if name in n)
                missing.append(
                    f"{where}: {name} is not in {file_name}"
                    + (f" (it is in {elsewhere})" if elsewhere else " (or anywhere)")
                )
        elif name not in everywhere:
            missing.append(f"{where}: no test named {name} anywhere under tests/")

    assert not missing, "\n".join(missing)


def test_no_citation_is_a_wildcard(document: Path) -> None:
    """A glob is not a citation.

    SI-243 cited ``test_the_credential_is_absent_from_*`` and claimed seven
    surfaces. Six matched. The seventh - the data directory - is named
    ``test_no_artefact_anywhere_in_the_data_directory_carries_the_credential``
    and the glob never reached it, so the strongest-sounding row in the
    OpenCode section was quietly one surface short.
    """
    globbed = [
        f"{document.name}:{line} {invariant}: {name}"
        for line, invariant, _, name in _references(document)
        if "*" in name
    ]
    assert not globbed, "\n".join(globbed)


def test_every_frontend_test_file_the_table_names_exists(
    document: Path, repo_root: Path
) -> None:
    """The vitest half of the table is cited by bare file name, not by path."""
    web = repo_root / "apps" / "station-web"
    present = {path.name for path in web.rglob("*.test.tsx")}

    missing = sorted(
        {
            span.strip()
            for _, _, cell in _rows(document)
            for span in _SPAN.findall(cell)
            if _FRONTEND_FILE.match(span.strip())
        }
        - present
    )
    assert present, "no vitest files found; the scan is reading the wrong tree"
    assert not missing, missing


def test_the_scan_would_catch_a_planted_reference(tmp_path: Path) -> None:
    """The deny side, on a throwaway document, so the probe never ships.

    Without this, a parser that silently matched nothing would make
    :func:`test_every_test_named_in_the_table_exists` a test that cannot fail.
    """
    planted = tmp_path / "security-invariants.md"
    planted.write_text(
        "| ID | Değişmez | Beklenen | Test | Durum |\n"
        "|---|---|---|---|---|\n"
        "| SI-01 | bir | iki | `test_bind.py::test_launcher_binds_only_loopback` | A1 |\n"
        "| SI-02 | bir | iki | `test_bind.py::test_this_name_was_never_written` | A1 |\n"
        "| SI-03 | bir | iki | `test_bind.py::test_a_glob_*` | A1 |\n",
        encoding="utf-8",
    )

    references = _references(planted)
    assert [name for *_, name in references] == [
        "test_launcher_binds_only_loopback",
        "test_this_name_was_never_written",
        "test_a_glob_*",
    ]

    by_file = _python_test_names(Path(__file__).resolve().parent.parent)
    assert "test_launcher_binds_only_loopback" in by_file["test_bind.py"]
    assert "test_this_name_was_never_written" not in by_file["test_bind.py"]
    assert any("*" in name for *_, name in references)
