"""End-to-end identity and recovery over HTTP.

Covers AC-10 (a recovery file restores the same DID on a clean profile) and
AC-11 (a wrong passphrase and a tampered file are refused identically) through
the real API, with the real session, CSRF, Host and Sec-Fetch-Site guards in
force.

Nothing here contacts Technocore; there is no outbound client to contact it
with (INV-05).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import Settings
from station_api.db.migrations_runner import initialise_database
from station_api.schemas import CREATE_IDENTITY_CONFIRMATION
from station_api.strict_json import canonical_json_bytes

from tests.conftest import (
    TEST_ONLY_RECOVERY_PASSPHRASE,
    TEST_ONLY_VAULT_PASSPHRASE,
    TEST_ONLY_WRONG_PASSPHRASE,
)
from tests.security.conftest import TEST_PORT, establish_session

pytestmark = pytest.mark.integration

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI vault is required to create an identity"
)


@pytest.fixture
def api(
    settings: Settings, engine: Engine, base_url: str
) -> Iterator[tuple[TestClient, str, FastAPI]]:
    app = create_app(settings=settings, port=TEST_PORT, engine=engine, web_dist=None)
    with TestClient(app, base_url=base_url) as client:
        csrf = establish_session(client, app)
        if not app.state.identity_service.describe().capability.usable:
            pytest.skip("vault capability unavailable on this platform")
        yield client, csrf, app


def _create(client: TestClient, csrf: str) -> dict:
    response = client.post(
        "/api/identity",
        headers={"X-Station-CSRF": csrf},
        json={
            "protection": "dpapi+passphrase",
            "passphrase": TEST_ONLY_VAULT_PASSPHRASE,
            "passphrase_confirm": TEST_ONLY_VAULT_PASSPHRASE,
            "label": "TEST-ONLY",
            "confirmation": CREATE_IDENTITY_CONFIRMATION,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _export(client: TestClient, csrf: str) -> bytes:
    response = client.post(
        "/api/identity/recovery/export",
        headers={"X-Station-CSRF": csrf},
        json={
            "recovery_passphrase": TEST_ONLY_RECOVERY_PASSPHRASE,
            "recovery_passphrase_confirm": TEST_ONLY_RECOVERY_PASSPHRASE,
            "vault_passphrase": TEST_ONLY_VAULT_PASSPHRASE,
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert ".tcrec" in response.headers["content-disposition"]
    return response.content


@windows_only
def test_identity_lifecycle_over_http(api: tuple[TestClient, str, FastAPI]) -> None:
    client, csrf, _ = api

    before = client.get("/api/identity").json()
    assert before["state"] == "no_identity"
    assert before["gate"]["allowed"] is False

    created = _create(client, csrf)
    assert created["state"] == "recovery_pending"
    assert created["identity"]["did"].startswith("did:key:z6Mk")
    assert created["gate"]["identity_ready"] is False

    payload = _export(client, csrf)

    response = client.post(
        "/api/identity/recovery/verify",
        headers={"X-Station-CSRF": csrf},
        files={"recovery_file": ("backup.tcrec", payload, "application/octet-stream")},
        data={"recovery_passphrase": TEST_ONLY_RECOVERY_PASSPHRASE},
    )
    assert response.status_code == 200, response.text
    verified = response.json()
    assert verified["state"] == "ready"
    assert verified["recovery"]["verified_at"] is not None
    assert verified["gate"]["identity_ready"] is True

    # AC-12: identity is ready, but writing is still closed and honest about why.
    assert verified["gate"]["allowed"] is False
    assert "conformance_verified" in verified["gate"]["blocking_reasons"]


@windows_only
def test_wrong_passphrase_and_tamper_share_one_response(
    api: tuple[TestClient, str, FastAPI],
) -> None:
    """AC-11 - the two failures are indistinguishable from outside."""
    client, csrf, _ = api
    _create(client, csrf)
    payload = _export(client, csrf)

    wrong = client.post(
        "/api/identity/recovery/verify",
        headers={"X-Station-CSRF": csrf},
        files={"recovery_file": ("backup.tcrec", payload, "application/octet-stream")},
        data={"recovery_passphrase": TEST_ONLY_WRONG_PASSPHRASE},
    )

    header = json.loads(payload)
    header["ciphertext"] = header["ciphertext"][:-4] + "AAAA"
    tampered = client.post(
        "/api/identity/recovery/verify",
        headers={"X-Station-CSRF": csrf},
        files={
            "recovery_file": (
                "backup.tcrec",
                canonical_json_bytes(header),
                "application/octet-stream",
            )
        },
        data={"recovery_passphrase": TEST_ONLY_RECOVERY_PASSPHRASE},
    )

    assert wrong.status_code == tampered.status_code == 400
    assert wrong.json()["detail"] == tampered.json()["detail"]

    after = client.get("/api/identity").json()
    assert after["state"] == "recovery_pending"
    assert after["recovery"]["verified_at"] is None


@windows_only
def test_clean_profile_recovers_the_same_did(
    api: tuple[TestClient, str, FastAPI], tmp_path: Path, base_url: str
) -> None:
    """AC-10 - a second, empty application root restores the identity.

    Scope note: this uses an independent data root inside the *same* Windows
    account. It proves the recovery file carries everything needed and depends
    on no DPAPI blob from the first profile. It is NOT a second-Windows-account
    test; see PROJECT_STATUS.md for that honest limitation.
    """
    client, csrf, _ = api
    created = _create(client, csrf)
    original_did = created["identity"]["did"]
    payload = _export(client, csrf)

    clean_root = tmp_path / "clean-profile"
    clean_settings = Settings(dev_mode=False, data_dir=clean_root)
    clean_settings.ensure_data_dir()
    clean_engine = initialise_database(clean_settings.database_path, stage=2)
    clean_app = create_app(
        settings=clean_settings, port=TEST_PORT, engine=clean_engine, web_dist=None
    )

    with TestClient(clean_app, base_url=base_url) as clean_client:
        clean_csrf = establish_session(clean_client, clean_app)

        assert clean_client.get("/api/identity").json()["state"] == "no_identity"

        inspect = clean_client.post(
            "/api/identity/recovery/inspect",
            headers={"X-Station-CSRF": clean_csrf},
            files={"recovery_file": ("backup.tcrec", payload, "application/octet-stream")},
            data={"recovery_passphrase": TEST_ONLY_RECOVERY_PASSPHRASE},
        )
        assert inspect.status_code == 200, inspect.text
        assert inspect.json()["did"] == original_did

        adopt = clean_client.post(
            "/api/identity/recovery/adopt",
            headers={"X-Station-CSRF": clean_csrf},
            files={"recovery_file": ("backup.tcrec", payload, "application/octet-stream")},
            data={
                "recovery_passphrase": TEST_ONLY_RECOVERY_PASSPHRASE,
                "protection": "dpapi+passphrase",
                "vault_passphrase": TEST_ONLY_VAULT_PASSPHRASE,
                "confirm_did": original_did,
            },
        )
        assert adopt.status_code == 201, adopt.text
        restored = adopt.json()

        assert restored["identity"]["did"] == original_did
        assert restored["state"] == "ready"
        assert restored["gate"]["identity_ready"] is True

    clean_engine.dispose()


@windows_only
def test_revoke_requires_the_exact_did_and_closes_the_gate(
    api: tuple[TestClient, str, FastAPI],
) -> None:
    client, csrf, _ = api
    created = _create(client, csrf)
    did = created["identity"]["did"]

    refused = client.post(
        "/api/identity/revoke",
        headers={"X-Station-CSRF": csrf},
        json={"confirm_did": "did:key:zWRONG"},
    )
    assert refused.status_code == 409
    assert client.get("/api/identity").json()["state"] == "recovery_pending"

    accepted = client.post(
        "/api/identity/revoke", headers={"X-Station-CSRF": csrf}, json={"confirm_did": did}
    )
    assert accepted.status_code == 200
    revoked = accepted.json()
    assert revoked["state"] == "revoked"
    assert revoked["gate"]["identity_ready"] is False
    assert "identity_not_revoked" in revoked["gate"]["blocking_reasons"]


@windows_only
def test_create_requires_the_exact_confirmation_text(
    api: tuple[TestClient, str, FastAPI],
) -> None:
    client, csrf, _ = api
    response = client.post(
        "/api/identity",
        headers={"X-Station-CSRF": csrf},
        json={
            "protection": "dpapi+passphrase",
            "passphrase": TEST_ONLY_VAULT_PASSPHRASE,
            "passphrase_confirm": TEST_ONLY_VAULT_PASSPHRASE,
            "confirmation": "kimlik olustur",  # wrong case
        },
    )
    assert response.status_code == 400
    assert client.get("/api/identity").json()["state"] == "no_identity"


@windows_only
def test_dpapi_only_requires_an_explicit_risk_acknowledgement(
    api: tuple[TestClient, str, FastAPI],
) -> None:
    client, csrf, _ = api
    response = client.post(
        "/api/identity",
        headers={"X-Station-CSRF": csrf},
        json={"protection": "dpapi", "confirmation": CREATE_IDENTITY_CONFIRMATION},
    )
    assert response.status_code == 400
    assert client.get("/api/identity").json()["state"] == "no_identity"


def test_identity_writes_require_csrf_and_a_session(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """The Stage 1 guards still cover every new endpoint."""
    app = create_app(settings=settings, port=TEST_PORT, engine=engine, web_dist=None)
    with TestClient(app, base_url=base_url) as client:
        assert client.get("/api/identity").status_code == 401
        assert client.post("/api/identity", json={"protection": "dpapi"}).status_code == 403

        establish_session(client, app)
        assert client.post("/api/identity", json={"protection": "dpapi"}).status_code == 403
        assert (
            client.post("/api/identity/revoke", json={"confirm_did": "x"}).status_code == 403
        )


@windows_only
def test_oversized_recovery_upload_is_refused(api: tuple[TestClient, str, FastAPI]) -> None:
    client, csrf, _ = api
    response = client.post(
        "/api/identity/recovery/verify",
        headers={"X-Station-CSRF": csrf},
        files={
            "recovery_file": (
                "big.tcrec",
                b"A" * (64 * 1024 + 10),
                "application/octet-stream",
            )
        },
        data={"recovery_passphrase": TEST_ONLY_RECOVERY_PASSPHRASE},
    )
    assert response.status_code == 413


def test_identity_service_is_unavailable_without_a_database(
    settings: Settings, base_url: str
) -> None:
    """No database means 503, not a pretend-success."""
    app = create_app(settings=settings, port=TEST_PORT, engine=None, web_dist=None)
    with TestClient(app, base_url=base_url) as client:
        establish_session(client, app)
        assert client.get("/api/identity").status_code == 503
