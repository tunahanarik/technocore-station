"""The shipped vectors really came from the pinned reference.

The runtime self-test replays a bundle that lives inside the package, on a
machine that may have no ``vendor/`` directory. That is only trustworthy if
the bundle is *derived from* the official reference rather than written by
hand - otherwise the self-test would confirm that this project agrees with
itself, which is worth nothing.

This module closes that gap: it rebuilds the bundle from the live oracle and
asserts the result is byte-identical to the shipped file. So "these vectors
came from the reference" is checked on every run, not asserted in a comment.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from technocore_conform.selftest import (
    EXPECTED_BUNDLE_DIGEST,
    EXPECTED_BUNDLE_FORMAT,
    EXPECTED_BUNDLE_VERSION,
    VECTOR_FILENAME,
)

from tests.conformance.vector_builder import build_bundle, digest, serialise

pytestmark = pytest.mark.conformance


@pytest.fixture(scope="module")
def shipped_bundle_path(repo_root: Path) -> Path:
    return (
        repo_root
        / "packages"
        / "technocore-conform"
        / "src"
        / "technocore_conform"
        / "vectors"
        / VECTOR_FILENAME
    )


def test_the_shipped_bundle_exists(shipped_bundle_path: Path) -> None:
    assert shipped_bundle_path.is_file()


def test_the_shipped_bundle_matches_its_pinned_digest(shipped_bundle_path: Path) -> None:
    """The digest in ``selftest`` is what makes the vectors un-editable."""
    assert digest(shipped_bundle_path.read_bytes()) == EXPECTED_BUNDLE_DIGEST


def test_the_shipped_bundle_is_reproducible_from_the_oracle(
    shipped_bundle_path: Path, vendor_root: Path
) -> None:
    """Provenance for AC-02, AC-04 and AC-05: rebuild it and compare bytes.

    If this fails, either the vectors were edited by hand or the pinned
    reference changed. Both must be a loud failure, never a silent drift.
    """
    rebuilt = serialise(build_bundle(vendor_root))
    assert rebuilt == shipped_bundle_path.read_bytes(), (
        "the shipped vectors are not what the pinned reference produces"
    )


def test_the_bundle_declares_its_format_and_provenance(shipped_bundle_path: Path) -> None:
    bundle = json.loads(shipped_bundle_path.read_text(encoding="ascii"))

    assert bundle["format"] == EXPECTED_BUNDLE_FORMAT
    assert bundle["version"] == EXPECTED_BUNDLE_VERSION
    assert bundle["upstream_commit"] == "7707cb63ebf638e8ef0cf59d1364818b9fef7d24"
    assert bundle["upstream_repo"].endswith("flop-labs/technocore-chat")
    assert bundle["unicode_version"]
    assert "TEST-ONLY" in bundle["description"]


def test_the_bundle_keys_do_not_collide(shipped_bundle_path: Path) -> None:
    """Regression: the provenance text was once keyed "note", like the vectors.

    JSON keeps the last duplicate, so the note vectors silently replaced the
    description and the section would have gone unchecked.
    """
    bundle = json.loads(shipped_bundle_path.read_text(encoding="ascii"))

    assert isinstance(bundle["description"], str)
    assert isinstance(bundle["note"], list)
    assert all(isinstance(vector, dict) for vector in bundle["note"])


def test_the_bundle_covers_every_contract_area(shipped_bundle_path: Path) -> None:
    """A bundle missing a section would let that area pass unchecked."""
    bundle = json.loads(shipped_bundle_path.read_text(encoding="ascii"))

    assert len(bundle["sweep"]) >= 20
    assert len(bundle["did"]) >= 4
    assert len(bundle["message"]) >= 8
    assert len(bundle["note"]) >= 4
    assert len(bundle["tamper"]) >= 6

    # Both outcomes must be represented, or "everything is refused" would pass.
    outcomes = {vector["outcome"] for vector in bundle["sweep"]}
    assert outcomes == {"swept", "refused"}


def test_the_bundle_is_pure_ascii(shipped_bundle_path: Path) -> None:
    """``ensure_ascii`` is what lets a lone surrogate survive the round-trip."""
    shipped_bundle_path.read_bytes().decode("ascii")


def test_the_bundle_seeds_are_not_the_leak_canary(shipped_bundle_path: Path) -> None:
    """The canary must not be in a shipped file, or the leak search is void.

    ``tests/security/test_seed_leakage.py`` proves a specific seed never
    escapes the vault by searching for its bytes. If that same seed were
    shipped inside the package, the search would find it everywhere and mean
    nothing.
    """
    from tests.conftest import TEST_ONLY_SEED_HEX

    text = shipped_bundle_path.read_text(encoding="ascii")
    assert TEST_ONLY_SEED_HEX not in text
    assert TEST_ONLY_SEED_HEX.upper() not in text
