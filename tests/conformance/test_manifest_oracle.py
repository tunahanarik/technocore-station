"""The stored reference documents really are the pinned generator's output.

Stage 3's fixture was hand-written and wrong, so the fixture and the code
under test carried the same mistake and agreed with each other. The fix is
structural rather than a better transcription: the documents are generated,
and this module regenerates them and compares **bytes**. Editing the stored
copy to make a test pass breaks this test instead.
"""

from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from station_api.technocore.projection import (
    EXPECTED_SIGNATURE_PATTERN,
    MESSAGE_BODY_POINTER,
    NOTE_BODY_POINTER,
    read_pointer,
)

from tests.conformance.manifest_oracle import (
    PINNED_COMMIT,
    generate_documents,
    pinned_version,
    serialise,
)

pytestmark = pytest.mark.conformance

STORED = ("openapi.json", "agent.json")


@pytest.fixture(scope="module")
def vendor_root(repo_root: Path) -> Path:
    return repo_root / "vendor" / "technocore-reference"


@pytest.fixture(scope="module")
def reference_root(repo_root: Path) -> Path:
    return repo_root / "tests" / "security" / "technocore_reference"


@pytest.fixture(scope="module")
def generated(vendor_root: Path) -> dict[str, Any]:
    return generate_documents(vendor_root)


def test_the_stored_documents_are_byte_identical_to_a_fresh_run(
    generated: dict[str, Any], reference_root: Path
) -> None:
    """The whole point: no hand-written protocol reference survives here."""
    for name, key in zip(STORED, ("openapi", "agent"), strict=True):
        expected = serialise(generated[key])
        actual = (reference_root / name).read_bytes()
        assert actual == expected, (
            f"{name} differs from a fresh run of the pinned generator. "
            "Regenerate it rather than editing it by hand."
        )


def test_the_recorded_hashes_match_the_stored_bytes(reference_root: Path) -> None:
    """PROVENANCE.md records a digest; it must be the real one."""
    provenance = (reference_root / "PROVENANCE.md").read_text(encoding="utf-8")
    for name in STORED:
        digest = hashlib.sha256((reference_root / name).read_bytes()).hexdigest()
        assert digest in provenance, f"PROVENANCE.md does not record {name}'s digest"


def test_provenance_names_the_pin_and_the_generator(reference_root: Path) -> None:
    provenance = (reference_root / "PROVENANCE.md").read_text(encoding="utf-8")
    assert PINNED_COMMIT in provenance
    assert "manifest.py" in provenance
    # The old fixture claimed to be a transcription of the live service. The
    # replacement must say what it actually is.
    assert "elle yazılmamıştır" in provenance


def test_the_stored_documents_carry_no_windows_line_endings(
    reference_root: Path,
) -> None:
    """A CRLF rewrite on checkout would break the byte comparison above.

    ``.gitattributes`` marks these paths ``-text``; this is the assertion that
    notices if that ever stops being true, which is exactly how Stage 2B's
    vector bundle died on a fresh clone.
    """
    for name in STORED:
        assert b"\r\n" not in (reference_root / name).read_bytes(), (
            f"{name} has CRLF line endings; check .gitattributes"
        )


def test_the_stored_documents_parse_as_json(reference_root: Path) -> None:
    for name in STORED:
        assert isinstance(
            json.loads((reference_root / name).read_text(encoding="utf-8")), dict
        )


# ---------------------------------------------------------------------------
# What the generated documents actually say - the finding, as an assertion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pointer", [MESSAGE_BODY_POINTER, NOTE_BODY_POINTER])
def test_the_credentials_are_conditional_not_unconditional_properties(
    generated: dict[str, Any], pointer: tuple[str, ...]
) -> None:
    """The finding this whole stage exists for, stated against real bytes.

    ``properties.sig`` carries a description and nothing else. The pattern,
    the lengths and the requiredness all live under ``dependentSchemas.did``.
    """
    schema = read_pointer(generated["openapi"], pointer)
    assert isinstance(schema, dict)

    for name in ("sig", "nonce"):
        published = schema["properties"][name]
        assert set(published) == {"description"}, (
            f"properties.{name} unexpectedly carries {sorted(published)}; "
            "the projection's pointers assume it carries only a description"
        )

    assert "sig" not in schema["required"]
    assert "nonce" not in schema["required"]

    lane = schema["dependentSchemas"]["did"]
    assert sorted(lane["required"]) == ["nonce", "sig"]
    assert lane["properties"]["sig"]["pattern"] == EXPECTED_SIGNATURE_PATTERN


@pytest.mark.parametrize("pointer", [MESSAGE_BODY_POINTER, NOTE_BODY_POINTER])
def test_the_length_bounds_are_numbers_not_strings(
    generated: dict[str, Any], pointer: tuple[str, ...]
) -> None:
    """``86`` is an integer here, which is why the comparison is typed."""
    schema = read_pointer(generated["openapi"], pointer)
    assert isinstance(schema, dict)
    sig = schema["dependentSchemas"]["did"]["properties"]["sig"]
    for bound in ("minLength", "maxLength"):
        assert isinstance(sig[bound], int)
        assert not isinstance(sig[bound], bool)
    assert isinstance(schema["properties"]["did"]["maxLength"], int)


def test_the_official_signature_pattern_is_the_canonical_one(
    generated: dict[str, Any],
) -> None:
    """Not the wide 86-character class Stage 3 expected.

    The reference generates this from ``didkey.SIG_PATTERN``; the last
    character carries four slack bits that a 64-byte signature always leaves
    zero, so only four characters can end one.
    """
    schema = read_pointer(generated["openapi"], MESSAGE_BODY_POINTER)
    assert isinstance(schema, dict)
    pattern = schema["dependentSchemas"]["did"]["properties"]["sig"]["pattern"]

    assert pattern == r"^[A-Za-z0-9_-]{85}[AQgw]$"
    assert pattern != r"^[A-Za-z0-9_-]{86}$"


def test_the_generated_version_comes_from_the_pinned_project_file(
    generated: dict[str, Any], vendor_root: Path
) -> None:
    """No hand-entered version sits in the provenance chain."""
    assert generated["version"] == pinned_version(vendor_root)
    assert generated["agent"]["version"] == generated["version"]


def test_generation_leaves_no_upstream_module_imported(
    generated: dict[str, Any],
) -> None:
    """The oracle borrows four very generic module names; it gives them back."""
    del generated
    for name in ("config", "didkey", "store", "manifest"):
        assert name not in sys.modules, f"{name} leaked into sys.modules"


def test_generation_leaves_no_import_shim_behind(vendor_root: Path) -> None:
    """A shim that outlives generation would silently weaken later tests.

    ``orjson`` is not a dependency of this project and POSIX ``fcntl`` does not
    exist on Windows. A leftover fake makes a later ``import orjson`` succeed
    with a two-function stub instead of failing honestly, and makes an
    assertion that ``fcntl`` is unavailable stop testing anything.
    """
    for name in ("fcntl", "orjson"):
        sys.modules.pop(name, None)

    generate_documents(vendor_root)

    for name in ("fcntl", "orjson"):
        assert name not in sys.modules, f"{name} shim outlived generation"


def test_a_pre_existing_module_is_not_removed(vendor_root: Path) -> None:
    """Only what this oracle installed is taken away again.

    On a platform where ``fcntl`` is real, generation must hand it back rather
    than unloading someone else's module.
    """
    sentinel = types.ModuleType("fcntl")
    sentinel.LOCK_EX = 2  # type: ignore[attr-defined]
    sentinel.LOCK_UN = 8  # type: ignore[attr-defined]
    sentinel.flock = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    sys.modules["fcntl"] = sentinel
    try:
        generate_documents(vendor_root)
        assert sys.modules.get("fcntl") is sentinel
    finally:
        sys.modules.pop("fcntl", None)
