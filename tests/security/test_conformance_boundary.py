"""Stage 2B security regressions: the conformance surface leaks nothing.

The conformance package now holds signing code and ships a vector bundle
containing TEST-ONLY seeds. Two boundaries therefore need guarding:

* Nothing key-shaped may reach an HTTP response, and the new status endpoint
  must sit behind exactly the same session and same-origin guards as every
  other route.
* The package must stay portable and side-effect free - no application
  import, no Windows module, no network, no disk access at import time.

The write gate's fail-closed behaviour is exercised here too, through the
real service rather than the pure function, because that is the path a
request actually takes.
"""

from __future__ import annotations

import ast
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.conformance import ConformanceService
from station_api.config import Settings
from station_api.identity.service import IdentityService
from technocore_conform import SelfTestResult
from technocore_conform.selftest import EXPECTED_BUNDLE_DIGEST

from tests.conftest import TEST_PORT
from tests.security.conftest import establish_session

pytestmark = pytest.mark.security

#: Anything shaped like an Ed25519 seed or key in hex.
_HEX_64 = re.compile(r"\b[0-9a-fA-F]{64}\b")

_CONFORMANCE_PATH = "/api/conformance/status"


def _failing_self_test() -> SelfTestResult:
    """A verdict from a build whose conformance has drifted."""
    return SelfTestResult(
        passed=False,
        checks=(),
        failures=("sweep: vector ascii-plain swept differently",),
        bundle_digest="",
        bundle_vectors=0,
        upstream_commit="",
        package_version="",
        python_version="",
        unicode_version="",
        bundle_unicode_version="",
    )


# --- the endpoint is behind the usual guards --------------------------------


def test_conformance_status_requires_a_session(client: TestClient) -> None:
    assert client.get(_CONFORMANCE_PATH).status_code == 401


def test_conformance_status_is_readable_with_a_session(
    client: TestClient, csrf_token: str
) -> None:
    assert csrf_token
    response = client.get(_CONFORMANCE_PATH)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


def test_conformance_status_rejects_a_foreign_host(
    client: TestClient, csrf_token: str
) -> None:
    assert csrf_token
    response = client.get(_CONFORMANCE_PATH, headers={"Host": "evil.example"})
    assert response.status_code == 421


def test_conformance_status_rejects_a_cross_site_request(
    client: TestClient, csrf_token: str
) -> None:
    assert csrf_token
    response = client.get(_CONFORMANCE_PATH, headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_conformance_status_is_read_only(client: TestClient, csrf_token: str) -> None:
    """No write verb exists on this path."""
    for method in (client.post, client.put, client.patch, client.delete):
        response = method(_CONFORMANCE_PATH, headers={"X-Station-CSRF": csrf_token})
        assert response.status_code in {404, 405}


# --- the response carries public metadata only ------------------------------


def test_conformance_status_exposes_no_key_material(
    client: TestClient, csrf_token: str
) -> None:
    """The vector bundle holds TEST-ONLY seeds; none may be served.

    A seed and a SHA-256 are both 64 hex characters, so the one legitimate
    64-hex field - the vector bundle digest - is removed first and then
    checked against its own pinned value. Everything else must be free of
    key-shaped material.
    """
    assert csrf_token
    payload = client.get(_CONFORMANCE_PATH).json()

    # The one expected hash, verified to be exactly that and nothing else.
    assert payload.pop("bundle_digest") == EXPECTED_BUNDLE_DIGEST
    payload.pop("bundle_digest_short")

    remaining = json.dumps(payload)
    match = _HEX_64.search(remaining)
    assert match is None, f"an unexpected 64-hex value reached the response: {match}"

    for forbidden in ("seed", "private", "passphrase", "mnemonic", "secret"):
        assert forbidden not in remaining.lower()


def test_conformance_status_returns_no_vector_content(
    client: TestClient, csrf_token: str
) -> None:
    """Counts and digests, never the vectors themselves."""
    assert csrf_token
    payload = client.get(_CONFORMANCE_PATH).json()

    assert set(payload) == {
        "passed",
        "checks",
        "failures",
        "capabilities",
        "bundle_digest",
        "bundle_digest_short",
        "bundle_vectors",
        "upstream_commit",
        "upstream_commit_short",
        "package_version",
        "python_version",
        "unicode_version",
        "bundle_unicode_version",
        "unicode_version_matches",
    }
    for check in payload["checks"]:
        assert set(check) == {"name", "passed", "vectors", "detail"}


def test_conformance_status_reports_the_pinned_reference(
    client: TestClient, csrf_token: str
) -> None:
    assert csrf_token
    payload = client.get(_CONFORMANCE_PATH).json()

    assert payload["passed"] is True
    assert payload["upstream_commit"] == "7707cb63ebf638e8ef0cf59d1364818b9fef7d24"
    assert payload["upstream_commit_short"] == "7707cb6"
    assert len(payload["bundle_digest_short"]) == 12
    assert payload["bundle_digest"].startswith(payload["bundle_digest_short"])
    assert payload["unicode_version_matches"] is True


def test_conformance_status_leaks_no_filesystem_path(
    client: TestClient, csrf_token: str
) -> None:
    assert csrf_token
    body = client.get(_CONFORMANCE_PATH).text

    for marker in ("C:\\", "/home/", "AppData", "LOCALAPPDATA", "site-packages"):
        assert marker not in body


# --- the gate really closes -------------------------------------------------


def test_a_failing_self_test_closes_the_write_gate(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """End to end: a drifted build cannot write, whatever else is in place."""
    app = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        conformance=ConformanceService(runner=_failing_self_test),
    )
    with TestClient(app, base_url=base_url) as client:
        assert establish_session(client, app)
        gate = client.get("/api/write-gate").json()

        assert gate["allowed"] is False
        assert "conformance_verified" in gate["blocking_reasons"]

        status = client.get(_CONFORMANCE_PATH).json()
        assert status["passed"] is False
        assert status["failures"]


def test_a_passing_self_test_still_does_not_open_the_gate(
    client: TestClient, csrf_token: str
) -> None:
    """Manifest drift is unbuilt, so no outward write path exists yet."""
    assert csrf_token
    gate = client.get("/api/write-gate").json()

    assert gate["allowed"] is False
    assert "manifest_current" in gate["blocking_reasons"]
    assert "conformance_verified" not in gate["blocking_reasons"]


def test_a_crashing_self_test_is_not_a_pass(settings: Settings, engine: Engine) -> None:
    """An exception must become a closed gate, not an unhandled error."""

    def explode() -> SelfTestResult:
        raise RuntimeError("simulated conformance crash")

    service = ConformanceService(runner=explode)
    assert service.passed is False

    identity = IdentityService(
        engine=engine, data_dir=settings.data_dir, conformance=service
    )
    gate = identity.describe().gate
    assert gate.allowed is False
    assert "conformance_verified" in gate.blocking_reasons


def test_a_crashed_verdict_does_not_claim_a_matching_unicode_database(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """Regression: a crash must not advertise a Unicode match it never checked.

    Leaving both Unicode fields empty made ``unicode_version_matches``
    compare "" with "" and report True, so ``/api/conformance/status`` said
    the Unicode database matched on a run that never got far enough to read
    the vectors.
    """

    def explode() -> SelfTestResult:
        raise RuntimeError("simulated conformance crash")

    app = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        conformance=ConformanceService(runner=explode),
    )
    with TestClient(app, base_url=base_url) as client:
        assert establish_session(client, app)
        payload = client.get(_CONFORMANCE_PATH).json()

    assert payload["passed"] is False
    assert payload["unicode_version_matches"] is False
    # The runtime half is knowable and reported; the bundle half is not.
    assert payload["unicode_version"]
    assert payload["bundle_unicode_version"] == ""


def test_no_technocore_write_endpoint_was_added(app: FastAPI) -> None:
    """Stage 2B adds a read-only status route and nothing outbound."""
    paths = {getattr(route, "path", "") for route in app.routes}

    for path in paths:
        assert "say-signed" not in path
        assert "set-signed" not in path


# --- the package boundary holds ---------------------------------------------


def test_the_conformance_package_imports_nothing_heavy(repo_root: Path) -> None:
    """Portable, plain Python: no application, platform or network imports."""
    package = repo_root / "packages" / "technocore-conform" / "src"
    forbidden = {
        "station_api",
        "fastapi",
        "sqlalchemy",
        "alembic",
        "uvicorn",
        "sqlite3",
        "ctypes",
        "winreg",
        "socket",
        "http",
        "urllib",
        "httpx",
        "requests",
        "nacl",
    }

    offenders: list[str] = []
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in forbidden:
                    offenders.append(f"{path.name}: {name}")

    assert offenders == [], f"technocore-conform imports a forbidden module: {offenders}"


def test_the_conformance_package_makes_no_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proved by removing the ability, not by reading the source."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the conformance package attempted a network call")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    from technocore_conform import (
        canonical_message,
        did_key_from_seed,
        run_self_test,
        sign_payload,
        verify_payload,
    )

    seed = bytes.fromhex("00" * 31 + "01")
    payload = canonical_message(room="r", nonce="1", text="x")
    signature = sign_payload(payload, seed=seed)
    verify_payload(payload, did=did_key_from_seed(seed), signature=signature)
    assert run_self_test().passed is True


def test_pynacl_is_absent_from_the_production_import_graph() -> None:
    """The independent verifier is a test tool, not a shipped dependency.

    Checked by importing the application in a clean interpreter and looking
    at what actually landed in ``sys.modules`` - a source scan would miss a
    transitive pull-in.
    """
    script = (
        "import sys;"
        "import station_api.app, station_api.launcher, technocore_conform;"
        "tops = {name.split('.')[0] for name in sys.modules};"
        # httpx is deliberately absent from this set: Stage 3 added it as
        # the read-only client's transport. That it is confined to one
        # module is asserted in test_write_gate.py instead.
        "print(','.join(sorted(tops & {'nacl', 'requests', 'urllib3', 'aiohttp'})))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        f"a test-only or unreviewed network library reached production: {result.stdout.strip()}"
    )


def test_the_conformance_cli_offers_no_seed_input(repo_root: Path) -> None:
    """A seed must never be an argv value, a file option or an env variable."""
    source = (
        repo_root
        / "packages"
        / "technocore-conform"
        / "src"
        / "technocore_conform"
        / "cli.py"
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)
    added_options: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr == "add_argument":
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    added_options.append(argument.value.lower())

    assert added_options, "no CLI options were found; the scan would be vacuous"
    for option in added_options:
        for forbidden in ("seed", "passphrase", "password", "private", "secret"):
            assert forbidden not in option, f"the CLI declares {option}"

    # And no environment escape hatch.
    assert "os.environ" not in source
    assert "getenv" not in source


def test_the_conformance_package_reads_nothing_at_import_time(repo_root: Path) -> None:
    """Import must not touch the disk: the bundle is read when asked for.

    Checked structurally - a module-level call would make every import slow
    and would hide the self-test verdict from the caller.
    """
    package = repo_root / "packages" / "technocore-conform" / "src"

    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                pytest.fail(f"{path.name} calls something at import time")


def test_the_shipped_vectors_do_not_contain_the_leak_canary(repo_root: Path) -> None:
    """Keeps the canary in ``test_seed_leakage.py`` meaningful."""
    from tests.conftest import TEST_ONLY_SEED_HEX

    bundle = (
        repo_root
        / "packages"
        / "technocore-conform"
        / "src"
        / "technocore_conform"
        / "vectors"
        / "conformance-v1.json"
    ).read_text(encoding="ascii")

    assert TEST_ONLY_SEED_HEX not in bundle
    # The bundle is TEST-ONLY material and says so.
    assert "TEST-ONLY" in json.loads(bundle)["description"]
