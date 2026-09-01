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
EXPECTED_FILES = (
    "LICENSE",
    "NOTICE",
    "pyproject.toml",
    "scripts/sign.py",
    "src/config.py",
    "src/didkey.py",
    "src/manifest.py",
    "src/store.py",
)


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
    """The package must stay importable without FastAPI, SQLAlchemy or Windows.

    Stage 2 added exactly one runtime dependency, ``cryptography``, for
    Ed25519. Anything that would drag in the application or the platform is
    still forbidden, which is what keeps this package portable and cheap to
    differential-test.
    """
    manifest = (repo_root / "packages" / "technocore-conform" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    dependencies = manifest.split("dependencies = [", 1)[1].split("]", 1)[0]

    for forbidden in ("fastapi", "sqlalchemy", "alembic", "uvicorn", "pywin32", "station-api"):
        assert forbidden not in dependencies.lower(), (
            f"technocore-conform must not depend on {forbidden}"
        )
    assert "cryptography" in dependencies


def test_conform_package_does_not_import_the_application(repo_root: Path) -> None:
    """The dependency arrow points one way: station-api -> technocore-conform."""
    package = repo_root / "packages" / "technocore-conform" / "src"
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("import station_api", "from station_api", "import fastapi", "import sqlalchemy"):
            if forbidden in text:
                offenders.append(f"{path.name}: {forbidden}")
    assert offenders == [], f"conform package reaches into the application: {offenders}"


def test_conform_package_exposes_the_stage_2b_surface() -> None:
    """Stage 2B delivers the protocol surface this package existed to hold.

    Until Stage 2B this asserted the *absence* of sweep, sign and verify,
    which was the honest statement while they did not exist. Implementing
    them is what this stage is; the assertion is inverted rather than
    dropped, so the surface stays pinned by a test.
    """
    import technocore_conform

    assert technocore_conform.IMPLEMENTED_IN_STAGE == "2B"
    assert technocore_conform.CANONICAL_SEPARATOR == "|"

    for expected in (
        "sweep",
        "sweep_message",
        "sweep_note_value",
        "canonical_message",
        "canonical_note",
        "sign_payload",
        "verify_payload",
        "did_key_from_seed",
        "run_self_test",
    ):
        assert hasattr(technocore_conform, expected), f"{expected} is missing"
        assert expected in technocore_conform.__all__, f"{expected} is not exported"


def test_conform_package_exposes_no_arbitrary_signing_shortcut() -> None:
    """Signing takes a payload, never a bare string.

    A convenience like ``sign_arbitrary_string`` would let a caller sign raw
    text, which the server refuses and which cannot be re-verified against
    the bytes on disk.
    """
    import technocore_conform

    for forbidden in (
        "sign_arbitrary_string",
        "sign_string",
        "sign_raw",
        "sign_text",
        "sign_message",
    ):
        assert not hasattr(technocore_conform, forbidden), (
            f"{forbidden} would allow signing text that was never swept"
        )


def test_conform_package_holds_no_nonce_state() -> None:
    """Nonce allocation and replay defence are Stage 4, not this package."""
    import technocore_conform

    for forbidden in ("next_nonce", "allocate_nonce", "reserve_nonce", "NonceCounter"):
        assert not hasattr(technocore_conform, forbidden), (
            f"{forbidden} is Stage 4 scope; this package keeps no state"
        )
