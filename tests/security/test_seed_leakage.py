"""AC-06 - a seed must not appear anywhere outside the vault.

The method is a marked canary. A distinctive TEST-ONLY seed is installed, then
every surface that could carry it is searched for its bytes, its lowercase hex
and its uppercase hex: HTTP bodies and headers, the OpenAPI document, the
SQLite file, log output, exception text and the frontend bundle.

A plain substring search is the point. It does not care how a leak happened.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.agent.workspace import ensure_workspace, write_text
from station_api.config import Settings
from station_api.identity.service import IdentityService, IdentityServiceError
from station_api.logging_setup import configure_logging
from station_api.vault import ProtectionMode
from station_api.vault.errors import VaultUnlockError

from tests.conftest import (
    TEST_ONLY_SEED_HEX,
    TEST_ONLY_VAULT_PASSPHRASE,
    TEST_ONLY_WRONG_PASSPHRASE,
)

pytestmark = pytest.mark.security

TEST_ONLY_SEED = bytes.fromhex(TEST_ONLY_SEED_HEX)

#: Every spelling of the canary a leak could plausibly take.
_NEEDLES = (
    TEST_ONLY_SEED,
    TEST_ONLY_SEED_HEX.encode(),
    TEST_ONLY_SEED_HEX.upper().encode(),
)


def _assert_clean(blob: bytes, where: str) -> None:
    for needle in _NEEDLES:
        assert needle not in blob, f"seed material leaked into {where}"


@pytest.fixture
def installed_identity(engine: Engine, settings: Settings, app: FastAPI) -> IdentityService:
    """Install the canary seed, or skip cleanly where DPAPI is unavailable."""
    service = IdentityService(engine=engine, data_dir=settings.data_dir)
    if not service.describe().capability.usable:
        pytest.skip("vault capability unavailable on this platform")
    service.import_seed(
        seed=TEST_ONLY_SEED,
        protection=ProtectionMode.DPAPI_PASSPHRASE,
        passphrase=TEST_ONLY_VAULT_PASSPHRASE,
        label="TEST-ONLY",
    )
    app.state.identity_service = service
    return service


def test_seed_is_absent_from_every_http_response(
    installed_identity: IdentityService, client: TestClient, csrf_token: str
) -> None:
    assert installed_identity is not None
    assert csrf_token

    for path in (
        "/api/identity",
        "/api/write-gate",
        "/api/app/status",
        "/api/health",
        # Stage 2B. The conformance vectors hold TEST-ONLY seeds, so this
        # response is worth searching even though the canary is not among them.
        "/api/conformance/status",
    ):
        response = client.get(path)
        _assert_clean(response.content, f"{path} body")
        headers = " ".join(f"{key}: {value}" for key, value in response.headers.items())
        _assert_clean(headers.encode(), f"{path} headers")


def test_seed_is_absent_from_the_openapi_document(
    installed_identity: IdentityService, app: FastAPI
) -> None:
    assert installed_identity is not None
    _assert_clean(json.dumps(app.openapi()).encode(), "the OpenAPI document")


def test_seed_is_absent_from_the_sqlite_database(
    installed_identity: IdentityService, settings: Settings
) -> None:
    assert installed_identity is not None
    found = False
    for path in settings.data_dir.rglob("*.sqlite3*"):
        found = True
        _assert_clean(path.read_bytes(), f"the database file {path.name}")
    assert found, "expected a database file to inspect"


def test_seed_is_absent_from_the_vault_file(
    installed_identity: IdentityService, settings: Settings
) -> None:
    assert installed_identity is not None
    vault_files = list((settings.data_dir / "vault").rglob("*.vault.json"))
    assert vault_files, "expected a vault envelope to inspect"
    for path in vault_files:
        _assert_clean(path.read_bytes(), f"the vault envelope {path.name}")


#: A workspace this test writes so that the scan below has one to read.
TEST_ONLY_WORKSPACE_TASK_ID = "0123456789abcdef0123456789abcdef"


def test_no_plaintext_artefact_is_left_in_the_data_directory(
    installed_identity: IdentityService, settings: Settings
) -> None:
    """Nothing anywhere under the data root may carry the seed.

    A real agent workspace file is written first, and the scan is required to
    have read it. That step is not decoration. ``agent/workspace.py`` claimed
    workspace files entered this scan "automatically rather than by somebody
    remembering to add a path", and an independent review measured that they
    never had: this test's fixtures create an identity and a database and
    nothing that calls ``ensure_workspace``, so the walk had only ever seen a
    data directory with no workspace in it. Living under the data root makes
    a file *reachable*; only writing one makes it covered.
    """
    assert installed_identity is not None
    produced = write_text(
        ensure_workspace(settings.data_dir, TEST_ONLY_WORKSPACE_TASK_ID),
        "rapor.md",
        "TEST-ONLY agent ciktisi",
        replace_existing=False,
    )

    inspected: list[str] = []
    for path in settings.data_dir.rglob("*"):
        if not path.is_file():
            continue
        inspected.append(path.name)
        _assert_clean(path.read_bytes(), f"the file {path.name}")

    assert inspected
    assert produced.name in inspected, inspected


def test_seed_is_absent_from_logs_and_exceptions(
    installed_identity: IdentityService, capsys: pytest.CaptureFixture[str]
) -> None:
    """Even a forced failure path must not spill the seed."""
    service = installed_identity

    root = logging.getLogger()
    previous = root.handlers[:]
    try:
        configure_logging()
        logging.getLogger("station.test").error("identity installed")

        try:
            service.export_recovery(
                recovery_passphrase=TEST_ONLY_WRONG_PASSPHRASE,
                vault_passphrase=TEST_ONLY_WRONG_PASSPHRASE,
            )
        except (VaultUnlockError, IdentityServiceError) as exc:
            _assert_clean(repr(exc).encode(), "an exception repr")
            _assert_clean(str(exc).encode(), "an exception message")

        captured = capsys.readouterr()
        _assert_clean(captured.err.encode(), "stderr logging")
        _assert_clean(captured.out.encode(), "stdout logging")
    finally:
        root.handlers[:] = previous


def test_seed_is_absent_from_the_frontend_bundle(web_dist_root: Path) -> None:
    """The canary cannot reach a build, but the check documents the surface."""
    if not (web_dist_root / "index.html").is_file():
        pytest.fail("production build missing. Run: npm --prefix apps/station-web run build")
    for path in web_dist_root.rglob("*"):
        if path.is_file() and path.suffix in {".js", ".css", ".html"}:
            _assert_clean(path.read_bytes(), f"the bundle file {path.name}")


def test_passphrases_never_reach_the_database(
    installed_identity: IdentityService, settings: Settings
) -> None:
    assert installed_identity is not None
    for path in settings.data_dir.rglob("*"):
        if not path.is_file():
            continue
        assert TEST_ONLY_VAULT_PASSPHRASE.encode() not in path.read_bytes(), (
            f"a passphrase leaked into {path.name}"
        )


def test_identity_response_exposes_only_public_material(
    installed_identity: IdentityService, client: TestClient, csrf_token: str
) -> None:
    assert installed_identity is not None
    assert csrf_token

    payload = client.get("/api/identity").json()
    identity = payload["identity"]

    assert set(identity) == {
        "did",
        "public_key",
        "fingerprint",
        "fingerprint_short",
        "label",
        "status",
        "protection",
        "created_at",
        "revoked_at",
    }
    # The public key is public by definition; the seed is not derivable from it.
    assert identity["public_key"] != TEST_ONLY_SEED_HEX
    body = json.dumps(payload).lower()
    for forbidden in ("seed", "private_key", "mnemonic", "vault_path"):
        assert forbidden not in body
