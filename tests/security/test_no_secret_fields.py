"""SI-34 .. SI-36 - no secret-shaped field may exist in the API surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretBytes, SecretStr
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


#: Types that can actually carry a secret value. A field named
#: ``min_passphrase_chars`` is an int policy constant, not a leak; the rule is
#: about values that could hold key material or a passphrase.
_SECRET_CARRYING_TYPES = (str, bytes, bytearray, SecretStr, SecretBytes)


def _ref_name(node: Any) -> str | None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            return ref.rsplit("/", 1)[-1]
    return None


def _collect_refs(node: Any, found: set[str]) -> None:
    name = _ref_name(node)
    if name is not None:
        found.add(name)
    if isinstance(node, dict):
        for value in node.values():
            _collect_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, found)


def _response_schema_names(document: dict[str, Any]) -> set[str]:
    """Component schemas reachable from any operation's *responses*.

    Request bodies are excluded on purpose: a passphrase has to be accepted
    as input somewhere. The rule under test is that it may never come back.
    """
    roots: set[str] = set()
    for operations in document.get("paths", {}).values():
        for operation in operations.values():
            if isinstance(operation, dict):
                _collect_refs(operation.get("responses", {}), roots)

    components = document.get("components", {}).get("schemas", {})
    # Follow nested references so a leak cannot hide one level down.
    seen: set[str] = set()
    queue = list(roots)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        nested: set[str] = set()
        _collect_refs(components.get(name, {}), nested)
        queue.extend(nested - seen)
    return seen


def test_openapi_schema_has_no_secret_field_names(app: FastAPI) -> None:
    """No response schema, at any nesting depth, may declare a secret field."""
    document = app.openapi()
    components = document.get("components", {}).get("schemas", {})
    reachable = _response_schema_names(document)

    assert reachable, "at least one response schema should be reachable"

    offenders: list[str] = []
    for name in sorted(reachable):
        for field_name in components.get(name, {}).get("properties", {}):
            if any(fragment in field_name.lower() for fragment in FORBIDDEN_FRAGMENTS):
                offenders.append(f"{name}.{field_name}")

    # min_passphrase_chars is an int policy constant, not key material.
    offenders = [entry for entry in offenders if not entry.endswith(".min_passphrase_chars")]
    assert offenders == [], f"secret-shaped fields in OpenAPI responses: {offenders}"


def _is_request_model(model: type[BaseModel]) -> bool:
    return model.__name__.endswith("Request")


def test_response_models_have_no_secret_fields() -> None:
    """Checked on the models themselves, not only on what routes expose today."""
    offenders: list[str] = []

    for attribute in vars(schemas).values():
        if not isinstance(attribute, type) or not issubclass(attribute, BaseModel):
            continue
        if _is_request_model(attribute):
            continue
        for field_name, field in attribute.model_fields.items():
            if not any(fragment in field_name.lower() for fragment in FORBIDDEN_FRAGMENTS):
                continue
            if _carries_secret(field.annotation):
                offenders.append(f"{attribute.__name__}.{field_name}")

    assert offenders == [], f"secret-shaped model fields: {offenders}"


def _carries_secret(annotation: Any) -> bool:
    """Whether a field annotation could hold a string or bytes value."""
    if annotation in _SECRET_CARRYING_TYPES:
        return True
    return any(arg in _SECRET_CARRYING_TYPES for arg in get_args(annotation))


def test_request_models_wrap_passphrases_in_secret_str() -> None:
    """Inputs may carry a passphrase, but only as a redacted type.

    ``SecretStr`` prints ``**********`` in a repr, a log line or a traceback,
    so an accidental exception never spills the value.
    """
    checked = 0
    for attribute in vars(schemas).values():
        if not isinstance(attribute, type) or not issubclass(attribute, BaseModel):
            continue
        if not _is_request_model(attribute):
            continue
        for field_name, field in attribute.model_fields.items():
            if "passphrase" not in field_name.lower():
                continue
            annotation = field.annotation
            args = get_args(annotation)
            assert annotation is SecretStr or SecretStr in args, (
                f"{attribute.__name__}.{field_name} must be SecretStr"
            )
            checked += 1

    assert checked >= 4, "expected several passphrase inputs to exist"


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
