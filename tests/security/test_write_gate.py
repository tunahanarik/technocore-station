"""AC-12 - no external write is permitted until every requirement is met.

The gate is a pure function, so these tests state the policy directly. The
key property is the honest one: a requirement that is not implemented yet is
never counted as satisfied.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from station_api.identity.write_gate import CheckState, WriteGateInput, evaluate

pytestmark = pytest.mark.security

_FULLY_RECOVERED = WriteGateInput(
    has_identity=True,
    identity_revoked=False,
    vault_present=True,
    recovery_verified=True,
)


def test_closed_when_there_is_no_identity() -> None:
    status = evaluate(
        WriteGateInput(
            has_identity=False,
            identity_revoked=False,
            vault_present=False,
            recovery_verified=False,
        )
    )
    assert status.allowed is False
    assert status.identity_ready is False
    assert "identity_present" in status.blocking_reasons


def test_closed_while_recovery_is_pending() -> None:
    status = evaluate(
        WriteGateInput(
            has_identity=True,
            identity_revoked=False,
            vault_present=True,
            recovery_verified=False,
        )
    )
    assert status.allowed is False
    assert status.identity_ready is False
    assert "recovery_verified" in status.blocking_reasons


def test_closed_when_the_vault_is_missing() -> None:
    status = evaluate(
        WriteGateInput(
            has_identity=True,
            identity_revoked=False,
            vault_present=False,
            recovery_verified=True,
        )
    )
    assert status.allowed is False
    assert "vault_present" in status.blocking_reasons


def test_closed_for_a_revoked_identity() -> None:
    status = evaluate(
        WriteGateInput(
            has_identity=True,
            identity_revoked=True,
            vault_present=False,
            recovery_verified=False,
        )
    )
    assert status.allowed is False
    assert status.identity_ready is False
    assert "identity_not_revoked" in status.blocking_reasons


def test_identity_half_passes_after_a_successful_restore_test() -> None:
    status = evaluate(_FULLY_RECOVERED)
    assert status.identity_ready is True
    for key in (
        "identity_present",
        "identity_not_revoked",
        "vault_present",
        "recovery_verified",
    ):
        assert key not in status.blocking_reasons


def test_each_check_names_the_stage_that_delivers_it() -> None:
    """Regression: conformance and manifest both reported stage 4.

    The UI renders this field as a badge next to the explanatory text, so a
    wrong value made the badge contradict the sentence beside it. Conformance
    lands in 2B and manifest-drift in 3.
    """
    stages = {check.key: check.stage for check in evaluate(_FULLY_RECOVERED).checks}

    assert stages["identity_present"] == "2"
    assert stages["identity_not_revoked"] == "2"
    assert stages["vault_present"] == "2"
    assert stages["recovery_verified"] == "2"
    assert stages["conformance_verified"] == "2B"
    assert stages["manifest_current"] == "3"

    # The badge must agree with the sentence beside it.
    for check in evaluate(_FULLY_RECOVERED).checks:
        if check.state is CheckState.NOT_IMPLEMENTED:
            assert f"Asama {check.stage}" in check.detail, (
                f"{check.key} badge says {check.stage} but detail says otherwise"
            )


def test_unimplemented_requirements_are_never_counted_as_passed() -> None:
    """The core honesty property of the gate.

    Even a fully recovered identity cannot write, because conformance and
    manifest-drift checking do not exist yet. Reporting them as passed would
    be a lie that later becomes a signature over the wrong bytes.
    """
    status = evaluate(_FULLY_RECOVERED)

    assert status.allowed is False
    assert "conformance_verified" in status.blocking_reasons
    assert "manifest_current" in status.blocking_reasons

    unimplemented = [
        check for check in status.checks if check.state is CheckState.NOT_IMPLEMENTED
    ]
    assert {check.key for check in unimplemented} == {
        "conformance_verified",
        "manifest_current",
    }
    for check in unimplemented:
        assert check.satisfied is False


def test_no_check_can_be_bypassed_by_a_flag(api_source_root: Path) -> None:
    """There is no override, debug bypass or environment escape hatch.

    Checked structurally against the AST, not the raw text: a docstring that
    *describes* the absence of an override must not look like an override.
    """
    import ast

    tree = ast.parse(
        (api_source_root / "station_api" / "identity" / "write_gate.py").read_text(
            encoding="utf-8"
        )
    )

    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr.lower())
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg.lower())
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            identifiers.add(node.name.lower())

    # Only identifiers are inspected. Prose is excluded by construction, and a
    # string-literal escape hatch would need os.getenv, which the next test
    # rules out separately.
    for smell in ("override", "bypass", "skip_gate", "station_allow_write", "getenv"):
        offenders = [name for name in identifiers if smell in name]
        assert offenders == [], f"gate exposes a {smell} affordance: {offenders}"


def test_the_gate_reads_no_environment_variable(api_source_root: Path) -> None:
    """Policy must not be reconfigurable from outside the process."""
    source = (api_source_root / "station_api" / "identity" / "write_gate.py").read_text(
        encoding="utf-8"
    )
    assert "os.environ" not in source
    assert "import os" not in source


def test_repository_contains_no_technocore_write_path(repo_root: Path) -> None:
    """Stage 2 ships no outbound client and no live write test (INV-05)."""
    roots = (
        repo_root / "apps" / "station-api" / "src",
        repo_root / "packages" / "technocore-conform" / "src",
    )
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in ("technocore.chat", "https://technocore", "say-signed", "set-signed"):
                if marker in text:
                    offenders.append(f"{path.name}: {marker}")

    assert offenders == [], f"a Technocore endpoint is referenced in code: {offenders}"


def test_no_outbound_http_client_is_imported(api_source_root: Path) -> None:
    """No production module may import an HTTP client in this stage."""
    offenders: list[str] = []
    for path in api_source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in ("import httpx", "import requests", "from httpx", "urllib.request"):
            if marker in text:
                offenders.append(f"{path.name}: {marker}")
    assert offenders == [], f"outbound HTTP client found in production code: {offenders}"
