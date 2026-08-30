"""The runtime self-test, including the ways it must fail.

A self-test that only ever passes is decoration. These tests exercise the
failure paths deliberately, because the write gate's honesty depends on them:
a self-test that cannot run must report failure, never absence of failure.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest
from technocore_conform import run_self_test
from technocore_conform import selftest as selftest_module

pytestmark = pytest.mark.conformance


def test_the_self_test_passes_on_this_build() -> None:
    result = run_self_test()
    assert result.passed, f"conformance self-test failed: {result.failures}"
    assert result.failures == ()


def test_it_reports_everything_needed_to_interpret_the_verdict() -> None:
    """A verdict with no provenance cannot be audited later."""
    result = run_self_test()

    assert result.bundle_digest == selftest_module.EXPECTED_BUNDLE_DIGEST
    assert result.upstream_commit == "7707cb63ebf638e8ef0cf59d1364818b9fef7d24"
    assert result.package_version
    assert result.python_version.startswith("3.12")
    assert result.unicode_version
    assert result.bundle_unicode_version == result.unicode_version
    assert result.unicode_version_matches is True
    assert result.bundle_vectors > 0


def test_every_contract_area_is_covered() -> None:
    """The named checks are the contract; a missing one is a silent gap."""
    result = run_self_test()
    names = {check.name for check in result.checks}

    assert names == {
        "sweep",
        "did",
        "canonical",
        "signing",
        "verification",
        "encoding",
        "tamper",
        "unicode_database",
    }
    assert set(result.capabilities) == names


def test_the_vector_backed_checks_actually_have_vectors() -> None:
    """A check reporting zero vectors would be passing vacuously."""
    result = run_self_test()
    for check in result.checks:
        if check.name == "unicode_database":
            continue  # a version comparison, not a vector replay
        assert check.vectors > 0, f"{check.name} replayed no vectors"


# --- fail-closed -----------------------------------------------------------


def test_a_tampered_bundle_digest_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Editing the vectors to force a pass must break the digest instead.

    This simulates the digest no longer matching, which is what a hand-edited
    vector file would produce.
    """
    monkeypatch.setattr(selftest_module, "EXPECTED_BUNDLE_DIGEST", "0" * 64)
    result = run_self_test()

    assert result.passed is False
    assert result.checks == ()
    assert any("digest mismatch" in failure for failure in result.failures)


def test_a_missing_bundle_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selftest_module, "VECTOR_FILENAME", "does-not-exist.json")
    result = run_self_test()

    assert result.passed is False
    assert any("missing" in failure for failure in result.failures)


def test_an_unexpected_bundle_format_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selftest_module, "EXPECTED_BUNDLE_FORMAT", "something-else")
    result = run_self_test()

    assert result.passed is False
    assert any("format" in failure for failure in result.failures)


def test_a_unicode_database_mismatch_is_reported_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A different Unicode database is not silently treated as conformant.

    The sweep is defined over Unicode categories, so a database we have no
    vectors for is an absence of evidence, not evidence of conformance.
    """
    monkeypatch.setattr(selftest_module.unicodedata, "unidata_version", "99.0.0")
    result = run_self_test()

    assert result.passed is False
    assert result.unicode_version_matches is False
    assert any("unicode_database" in failure for failure in result.failures)
    # And the vector checks still ran, so the failure is specific.
    assert any(check.name == "sweep" and check.passed for check in result.checks)


def test_the_self_test_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash must become a failed verdict, never an exception to swallow."""

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated failure inside a check")

    monkeypatch.setattr(selftest_module, "_check_sweep", explode)
    result = run_self_test()

    assert result.passed is False
    assert any("raised" in failure for failure in result.failures)


# --- environment independence ----------------------------------------------


def test_the_self_test_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """No network, checked by making sockets impossible."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the conformance self-test attempted a network call")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    assert run_self_test().passed is True


def test_the_self_test_runs_without_the_vendor_directory(
    tmp_path: Path, repo_root: Path
) -> None:
    """It must work on an end user's machine, which has no vendor/ at all.

    Run from a temporary working directory with only the installed package
    importable, so nothing can reach the repository by relative path.
    """
    assert (repo_root / "vendor").is_dir()  # present here, and irrelevant

    script = "from technocore_conform import run_self_test; r=run_self_test(); print(r.passed)"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_importing_the_package_runs_no_self_test(tmp_path: Path) -> None:
    """Import must be free of side effects: no disk read, no verification.

    A package that self-tested on import would make every import slow and
    would hide the verdict from the caller.
    """
    script = (
        "import sys; import technocore_conform; "
        "print('technocore_conform.vectors' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
