"""Stage 1 conformance: the pinned vendor oracle is intact and isolated.

The sweep, canonical, did:key and signature differential tests belong to
Stage 2B. What is verifiable today is that the pinned Apache-2.0 reference
has not drifted and that no runtime module imports it.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.conformance

PINNED_COMMIT = "7707cb63ebf638e8ef0cf59d1364818b9fef7d24"
EXPECTED_FILES = ("LICENSE", "NOTICE", "scripts/sign.py", "src/store.py")


@pytest.fixture(scope="module")
def vendor_root(repo_root: Path) -> Path:
    return repo_root / "vendor" / "technocore-reference"


def test_pinned_files_are_present(vendor_root: Path) -> None:
    for relative in EXPECTED_FILES:
        assert (vendor_root / relative).is_file(), f"missing vendor file: {relative}"


def test_vendor_files_match_their_recorded_hashes(vendor_root: Path) -> None:
    """Detects any local edit to the reference, which must stay verbatim."""
    checksums = (vendor_root / "SHA256SUMS").read_text(encoding="utf-8").strip().splitlines()
    assert checksums, "SHA256SUMS is empty"

    for line in checksums:
        expected_digest, relative = line.split(maxsplit=1)
        path = vendor_root / relative.strip()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected_digest, f"vendor file modified: {relative}"


def test_provenance_records_the_pinned_commit(vendor_root: Path) -> None:
    provenance = (vendor_root / "PROVENANCE.md").read_text(encoding="utf-8")
    assert PINNED_COMMIT in provenance
    assert "https://github.com/flop-labs/technocore-chat" in provenance
    assert "Apache" in provenance


def test_upstream_license_and_notice_are_preserved(vendor_root: Path) -> None:
    license_text = (vendor_root / "LICENSE").read_text(encoding="utf-8")
    notice_text = (vendor_root / "NOTICE").read_text(encoding="utf-8")

    assert "Apache License" in license_text
    assert "Version 2.0" in license_text
    assert "FLOP Labs" in notice_text


def test_root_notice_declares_the_vendor_licence(repo_root: Path) -> None:
    notice = (repo_root / "NOTICE").read_text(encoding="utf-8")
    assert "vendor/technocore-reference" in notice
    assert "Apache-2.0" in notice
    assert PINNED_COMMIT in notice


def test_root_license_is_mit(repo_root: Path) -> None:
    assert "MIT License" in (repo_root / "LICENSE").read_text(encoding="utf-8")


def _docstring_constant_ids(tree: ast.Module) -> set[int]:
    """Identify the string constants that are docstrings.

    Prose *about* the boundary is expected and must not be mistaken for code
    that crosses it.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
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


def test_no_runtime_module_imports_the_vendor_reference(repo_root: Path) -> None:
    """The oracle is a test fixture, never part of the shipped application.

    Checked structurally: imports are read from the AST, and only non-docstring
    string constants are inspected, so a comment describing the rule cannot
    trip the rule.
    """
    offenders: list[str] = []
    runtime_roots = (
        repo_root / "apps" / "station-api" / "src",
        repo_root / "packages" / "technocore-conform" / "src",
    )

    for root in runtime_roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            docstrings = _docstring_constant_ids(tree)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "technocore_reference" in alias.name:
                            offenders.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and "technocore_reference" in node.module:
                        offenders.append(f"{path}: from {node.module}")
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if id(node) in docstrings:
                        continue
                    if "vendor/technocore-reference" in node.value:
                        offenders.append(f"{path}: path literal")

    assert offenders == [], f"runtime code references the vendor oracle: {offenders}"


def test_conform_package_has_no_heavy_dependencies(repo_root: Path) -> None:
    """The package must stay importable without FastAPI, SQLAlchemy or Windows."""
    manifest = (repo_root / "packages" / "technocore-conform" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "dependencies = []" in manifest


def test_conform_package_is_a_placeholder_in_this_stage() -> None:
    """Stage 1 ships the boundary only; no protocol code yet."""
    import technocore_conform

    assert technocore_conform.IMPLEMENTED_IN_STAGE == "2B"
    assert technocore_conform.CANONICAL_SEPARATOR == "|"

    for forbidden in ("sweep", "sign", "verify", "did_key", "canonical_message"):
        assert not hasattr(technocore_conform, forbidden), (
            f"{forbidden} implemented early; it belongs to Stage 2B"
        )
