"""AC-12 - no external write is permitted until every requirement is met.

The gate is a pure function, so these tests state the policy directly. The
key property is the honest one: a requirement that is not implemented yet is
never counted as satisfied.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from station_api.identity.write_gate import CheckState, WriteGateInput, evaluate

pytestmark = pytest.mark.security

#: Everything Stage 2 can deliver: identity installed, vault present,
#: recovery proven by a restore test. Conformance is deliberately left at its
#: default of False here, so the Stage 2 assertions stay about Stage 2.
_FULLY_RECOVERED = WriteGateInput(
    has_identity=True,
    identity_revoked=False,
    vault_present=True,
    recovery_verified=True,
)

#: Stage 2 plus a passing Stage 2B conformance self-test. Still not enough to
#: write: manifest-drift detection does not exist yet.
_RECOVERED_AND_CONFORMANT = WriteGateInput(
    has_identity=True,
    identity_revoked=False,
    vault_present=True,
    recovery_verified=True,
    conformance_verified=True,
)

#: Every precondition met, including a successful live check.
_FULLY_READY = WriteGateInput(
    has_identity=True,
    identity_revoked=False,
    vault_present=True,
    recovery_verified=True,
    conformance_verified=True,
    manifest_current=True,
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

    Stage 2B made conformance real and Stage 3 made manifest-drift real, so
    no check sits in ``NOT_IMPLEMENTED`` any more. The property being tested
    is unchanged and is the one that matters: whatever is in that state is
    never reported as satisfied. The state is kept precisely so a later stage
    can use it honestly rather than reaching for ``passed``.
    """
    status = evaluate(_FULLY_READY)

    unimplemented = [
        check for check in status.checks if check.state is CheckState.NOT_IMPLEMENTED
    ]
    assert unimplemented == []
    for check in status.checks:
        if check.state is CheckState.NOT_IMPLEMENTED:  # pragma: no cover
            assert check.satisfied is False


def test_manifest_blocks_until_a_live_check_succeeds() -> None:
    """Stage 3's check is real, and closed until the user runs it.

    A build can be perfectly conformant with a reference the live service has
    since moved away from. That is the case this check exists to catch, so it
    starts closed rather than optimistic.
    """
    status = evaluate(_RECOVERED_AND_CONFORMANT)

    assert status.allowed is False
    assert "manifest_current" in status.blocking_reasons

    manifest = next(check for check in status.checks if check.key == "manifest_current")
    assert manifest.state is CheckState.BLOCKED
    assert manifest.satisfied is False


def test_manifest_defaults_to_closed() -> None:
    """A caller that forgets the field gets a shut gate."""
    default = WriteGateInput(
        has_identity=True,
        identity_revoked=False,
        vault_present=True,
        recovery_verified=True,
        conformance_verified=True,
    )
    assert default.manifest_current is False
    assert "manifest_current" in evaluate(default).blocking_reasons


def test_conformance_and_manifest_stay_separate_checks() -> None:
    """They answer different questions and must not collapse into one.

    Conformance asks whether this build matches the pinned reference.
    Manifest asks whether the live service still publishes that protocol.
    Either one alone leaves the gate shut.
    """
    conformant_only = evaluate(_RECOVERED_AND_CONFORMANT)
    manifest_only = evaluate(
        WriteGateInput(
            has_identity=True,
            identity_revoked=False,
            vault_present=True,
            recovery_verified=True,
            conformance_verified=False,
            manifest_current=True,
        )
    )

    assert conformant_only.allowed is False
    assert manifest_only.allowed is False
    assert "manifest_current" in conformant_only.blocking_reasons
    assert "conformance_verified" in manifest_only.blocking_reasons


def test_every_precondition_together_opens_the_gate() -> None:
    """All six met: the gate reports allowed.

    Stage 3 completes the precondition set, and the gate says so honestly.
    That is *not* the same as a write being possible - a separate test proves
    no outbound write code exists at all.
    """
    assert evaluate(_FULLY_READY).allowed is True


def test_conformance_blocks_when_the_self_test_has_not_passed() -> None:
    """Stage 2B's check is real: a failing self-test closes the gate.

    This is the case that matters most. A build whose sweep or signature
    encoding has drifted from the pinned reference would otherwise sign
    bytes the server refuses, or worse, different bytes than it stores.
    """
    status = evaluate(_FULLY_RECOVERED)

    assert status.allowed is False
    assert "conformance_verified" in status.blocking_reasons

    conformance = next(
        check for check in status.checks if check.key == "conformance_verified"
    )
    assert conformance.state is CheckState.BLOCKED
    assert conformance.satisfied is False


def test_conformance_passes_when_the_self_test_passed() -> None:
    status = evaluate(_RECOVERED_AND_CONFORMANT)
    conformance = next(
        check for check in status.checks if check.key == "conformance_verified"
    )

    assert conformance.state is CheckState.PASSED
    assert conformance.satisfied is True
    assert "conformance_verified" not in status.blocking_reasons


def test_a_passing_self_test_alone_does_not_open_the_gate() -> None:
    """Conformance with the pinned reference is not the same claim as
    "the live server still speaks this protocol". Manifest drift is unbuilt,
    so the outward door stays shut.
    """
    assert evaluate(_RECOVERED_AND_CONFORMANT).allowed is False


def test_conformance_defaults_to_closed() -> None:
    """A caller that forgets the field gets a shut gate, never an open one."""
    default = WriteGateInput(
        has_identity=True,
        identity_revoked=False,
        vault_present=True,
        recovery_verified=True,
    )
    assert default.conformance_verified is False
    assert "conformance_verified" in evaluate(default).blocking_reasons


def test_no_check_can_be_bypassed_by_a_flag(api_source_root: Path) -> None:
    """There is no override, debug bypass or environment escape hatch.

    Checked structurally against the AST, not the raw text: a docstring that
    *describes* the absence of an override must not look like an override.
    """
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


def _non_docstring_literals(tree: ast.Module) -> list[str]:
    """Every string literal in a module except its docstrings.

    Prose *about* a forbidden path is exactly what the Stage 3 client is full
    of - it documents why those paths must never be requested - so a scan
    that matched comments and docstrings would fire on the code that is most
    careful. Only literals a program could actually use are inspected.
    """
    docstrings: set[int] = set()
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
            docstrings.add(id(first.value))

    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_no_code_path_can_reach_a_technocore_write_endpoint(repo_root: Path) -> None:
    """AC-16 groundwork: the write lanes are unreachable, not merely unused.

    Technocore performs writes over GET, so "we only send GET" proves
    nothing. What matters is that no string a program could use names a write
    path. Checked against the AST, because the read-only client's own
    docstrings quote these paths while explaining why they are forbidden.
    """
    roots = (
        repo_root / "apps" / "station-api" / "src",
        repo_root / "packages" / "technocore-conform" / "src",
    )
    write_markers = ("say-signed", "set-signed", "/say/", "/set/", "/r/events")

    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for literal in _non_docstring_literals(tree):
                for marker in write_markers:
                    if marker in literal:
                        offenders.append(f"{path.name}: {marker} in {literal[:60]!r}")

    assert offenders == [], f"a Technocore write path is reachable from code: {offenders}"


def test_the_source_registry_contains_only_read_only_documents() -> None:
    """The positive half: every reachable URL is a document, not a lane.

    The test above proves no write path appears. This one proves the paths
    that *do* appear are the six official documents and nothing else, so the
    registry cannot quietly grow a room read or a note write.
    """
    from station_api.technocore.sources import SOURCES, TECHNOCORE_ORIGIN

    paths = {source.path for source in SOURCES}
    assert paths == {
        "/.well-known/agent.json",
        "/openapi.json",
        "/config",
        "/healthz",
        "/llms.txt",
        "/skill.md",
    }

    for source in SOURCES:
        assert source.url == f"{TECHNOCORE_ORIGIN}{source.path}"
        # Not a room read, a note read, a room listing or an event stream.
        for forbidden in ("/r/", "/kv/", "/rooms", "/events"):
            assert forbidden not in source.path


def test_httpx_is_imported_only_by_the_read_only_client(api_source_root: Path) -> None:
    """Stage 3 adds exactly one outbound client, in exactly one module.

    Before Stage 3 this asserted no HTTP client existed anywhere. That was the
    honest statement while none did. Now one must, so the assertion is
    narrowed rather than dropped: any *other* module importing an HTTP client
    is a new outbound surface that nothing has reviewed.
    """
    allowed = {"client.py"}
    clients = ("httpx", "requests", "aiohttp", "urllib3", "http.client")

    offenders: list[str] = []
    for path in api_source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(name == c or name.startswith(f"{c}.") for c in clients) and (
                    path.name not in allowed
                    or path.parent.name != "technocore"
                ):
                    offenders.append(f"{path.relative_to(api_source_root)}: {name}")

    assert offenders == [], f"an HTTP client is imported outside the read-only client: {offenders}"


def test_urllib_request_is_not_used_anywhere(api_source_root: Path) -> None:
    """``urllib.request`` would be an outbound surface with no timeout by default."""
    offenders: list[str] = []
    for path in api_source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "urllib.request"
            ):
                offenders.append(path.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("urllib.request"):
                        offenders.append(path.name)
    assert offenders == []
