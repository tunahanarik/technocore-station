"""SI-34 .. SI-36 - no secret-shaped field may exist in the API surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from station_api import schemas

pytestmark = pytest.mark.security

#: A field whose name contains any of these may never leave the process.
FORBIDDEN_FRAGMENTS = (
    "seed",
    "private",
    "secret",
    "mnemonic",
    "passphrase",
    "password",
    "privkey",
)


def _collect_property_names(node: Any, found: set[str]) -> None:
    """Walk an OpenAPI document collecting every declared property name."""
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            found.update(str(key) for key in properties)
        for value in node.values():
            _collect_property_names(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_property_names(item, found)


def test_openapi_schema_has_no_secret_field_names(app: FastAPI) -> None:
    names: set[str] = set()
    _collect_property_names(app.openapi(), names)

    assert names, "the schema should declare at least one property"

    offenders = [
        name
        for name in names
        if any(fragment in name.lower() for fragment in FORBIDDEN_FRAGMENTS)
    ]
    assert offenders == [], f"secret-shaped fields in OpenAPI: {offenders}"


def test_response_models_have_no_secret_fields() -> None:
    """Checked on the models themselves, not only on what routes expose today."""
    offenders: list[str] = []

    for attribute in vars(schemas).values():
        if not isinstance(attribute, type) or not issubclass(attribute, BaseModel):
            continue
        for field_name in attribute.model_fields:
            if any(fragment in field_name.lower() for fragment in FORBIDDEN_FRAGMENTS):
                offenders.append(f"{attribute.__name__}.{field_name}")

    assert offenders == [], f"secret-shaped model fields: {offenders}"


def test_response_models_forbid_extra_fields() -> None:
    """extra='forbid' stops a stray value being attached at runtime."""
    for attribute in vars(schemas).values():
        if not isinstance(attribute, type) or not issubclass(attribute, BaseModel):
            continue
        if attribute is schemas.StrictModel or attribute is BaseModel:
            continue
        assert attribute.model_config.get("extra") == "forbid", attribute.__name__


def test_openapi_is_not_served_over_http(client: TestClient) -> None:
    """The schema is inspectable in-process but is not an HTTP surface."""
    for path in ("/openapi.json", "/api/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code != 200


def test_database_path_is_not_exposed(
    client: TestClient, data_dir: Path, csrf_token: str
) -> None:
    assert csrf_token
    body = client.get("/api/app/status").text

    assert str(data_dir) not in body
    assert data_dir.as_posix() not in body
    assert "sqlite" not in body.lower()
    assert "station.sqlite3" not in body


def test_status_response_exposes_no_filesystem_path(
    client: TestClient, csrf_token: str
) -> None:
    assert csrf_token
    payload = client.get("/api/app/status").json()

    flattened = repr(payload)
    for marker in ("C:\\", "/home/", "AppData", "LOCALAPPDATA", "Temp"):
        assert marker not in flattened


def test_health_response_leaks_no_environment_detail(client: TestClient) -> None:
    payload = client.get("/api/health").json()
    assert set(payload) == {"status", "service"}
