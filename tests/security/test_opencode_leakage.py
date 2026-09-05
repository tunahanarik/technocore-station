"""The credential canary: the seed-leakage test's twin, for the second secret.

``test_seed_leakage.py`` installs a distinctive TEST-ONLY seed and then
searches every surface that could carry it. This file does the same for the
provider credential, and for the same reason: a plain substring search does
not care *how* a value escaped, so it catches the leak nobody predicted.

Two surfaces are here that the seed's twin does not need, because they only
exist for a credential:

* **an outbound request's own headers.** The seed never leaves the process;
  the credential does, in an ``Authorization`` header, and everything *else*
  in that request is checked for it too.
* **a reflected key.** An upstream error body can echo back what was sent.
  The client registers the credential for the duration of a request and
  computes the response excerpt inside that window, so a reflected key is
  ``<redacted>`` before anything can display it - and this file proves it
  rather than trusting the ordering.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.agent.workspace import ensure_workspace, write_text
from station_api.app import create_app
from station_api.config import Settings
from station_api.logging_setup import (
    _MIN_REGISTERABLE_LENGTH,
    configure_logging,
    register_secret,
)
from station_api.opencode.adapters import parse_response
from station_api.opencode.client import OpenCodeClient
from station_api.opencode.credential_store import credential_path
from station_api.opencode.registry import Protocol
from station_api.opencode.service import OpenCodeService

from tests.conftest import TEST_ONLY_OPENCODE_CREDENTIAL, TEST_PORT
from tests.security.conftest import establish_session
from tests.security.opencode_fixtures import catalog_transport, recording_transport

pytestmark = pytest.mark.security

IS_WINDOWS = sys.platform == "win32"

windows_only = pytest.mark.skipif(
    not IS_WINDOWS, reason="storing a credential needs DPAPI, a Windows API"
)

#: Every spelling a leak could plausibly take.
_NEEDLES = (
    TEST_ONLY_OPENCODE_CREDENTIAL.encode(),
    TEST_ONLY_OPENCODE_CREDENTIAL.upper().encode(),
    TEST_ONLY_OPENCODE_CREDENTIAL.lower().encode(),
)


def _assert_clean(blob: bytes, where: str) -> None:
    for needle in _NEEDLES:
        assert needle not in blob, f"the provider credential leaked into {where}"


# ---------------------------------------------------------------------------
# The canary is a canary
# ---------------------------------------------------------------------------


def test_the_canary_is_long_enough_for_the_redaction_registry_to_hold_it() -> None:
    """The trap ADR-0005 8 names, checked on the marker itself.

    ``register_secret`` ignores a short value **in silence**. A canary under
    that threshold would sail through every test below while proving that
    redaction does not work.
    """
    assert len(TEST_ONLY_OPENCODE_CREDENTIAL) >= _MIN_REGISTERABLE_LENGTH


def test_the_canary_appears_nowhere_else_in_the_repository(repo_root: Path) -> None:
    """Keeps the searches below meaningful.

    A marker that occurs in ordinary source would make every "not present"
    assertion below either vacuous or a false alarm.
    """
    permitted = {
        (repo_root / "tests" / "conftest.py").resolve(),
        Path(__file__).resolve(),
    }
    needle = TEST_ONLY_OPENCODE_CREDENTIAL.encode()

    offenders: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.resolve() in permitted:
            continue
        parts = set(path.parts)
        if parts & {".git", "node_modules", ".venv", "__pycache__", ".mypy_cache"}:
            continue
        try:
            blob = path.read_bytes()
        except OSError:  # pragma: no cover - transient lock
            continue
        if needle in blob:
            offenders.append(str(path.relative_to(repo_root)))

    assert offenders == [], f"the canary is not unique: {offenders}"


# ---------------------------------------------------------------------------
# Stored, then searched
# ---------------------------------------------------------------------------


@pytest.fixture
def configured(engine: Engine, settings: Settings) -> OpenCodeService:
    """Install the canary as the stored credential, or skip cleanly."""
    if not IS_WINDOWS:
        pytest.skip("DPAPI is unavailable on this platform")
    transport, _ = catalog_transport()
    service = OpenCodeService(
        engine=engine,
        data_dir=settings.data_dir,
        client=OpenCodeClient(transport=transport, sleep=lambda _: None),
    )
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)
    service.refresh_catalog()
    return service


@windows_only
def test_the_credential_is_absent_from_the_envelope_file(
    configured: OpenCodeService, data_dir: Path
) -> None:
    assert configured is not None
    path = credential_path(data_dir)
    assert path.is_file()
    _assert_clean(path.read_bytes(), "the credential envelope")


@windows_only
def test_the_credential_is_absent_from_the_sqlite_database(
    configured: OpenCodeService, settings: Settings
) -> None:
    assert configured is not None
    found = False
    for path in settings.data_dir.rglob("*.sqlite3*"):
        found = True
        _assert_clean(path.read_bytes(), f"the database file {path.name}")
    assert found, "expected a database file to inspect"


#: A workspace this test writes so that the scan below has one to read.
TEST_ONLY_WORKSPACE_TASK_ID = "0123456789abcdef0123456789abcdef"


@windows_only
def test_no_artefact_anywhere_in_the_data_directory_carries_the_credential(
    configured: OpenCodeService, settings: Settings
) -> None:
    """The seed scan's twin, and it had the same hole.

    An agent workspace file is written first and the scan is required to have
    read it. Without that step this walk only ever saw the credential
    envelope and the database: nothing in these fixtures creates a workspace,
    so the surface ``agent/workspace.py`` claimed was covered "automatically"
    was not being read at all.
    """
    assert configured is not None
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


@windows_only
def test_the_credential_is_absent_from_every_http_response_and_its_headers(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    transport, _ = catalog_transport()
    app = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        opencode=OpenCodeService(
            engine=engine,
            data_dir=settings.data_dir,
            client=OpenCodeClient(transport=transport, sleep=lambda _: None),
        ),
    )
    with TestClient(app, base_url=base_url) as client:
        csrf = establish_session(client, app)
        headers = {"X-Station-CSRF": csrf}
        client.post(
            "/api/opencode/credential",
            json={"api_key": TEST_ONLY_OPENCODE_CREDENTIAL},
            headers=headers,
        )
        client.post("/api/opencode/catalog/refresh", headers=headers)

        for path in (
            "/api/opencode/status",
            "/api/app/status",
            "/api/identity",
            "/api/write-gate",
            "/api/health",
        ):
            response = client.get(path)
            _assert_clean(response.content, f"{path} body")
            rendered = " ".join(
                f"{key}: {value}" for key, value in response.headers.items()
            )
            _assert_clean(rendered.encode(), f"{path} headers")


@windows_only
def test_the_credential_is_absent_from_the_openapi_document(
    configured: OpenCodeService, app: FastAPI
) -> None:
    assert configured is not None
    _assert_clean(json.dumps(app.openapi()).encode(), "the OpenAPI document")


@windows_only
def test_the_credential_is_absent_from_logs_and_exceptions(
    configured: OpenCodeService, capsys: pytest.CaptureFixture[str]
) -> None:
    """Even a forced failure path must not spill it."""
    root = logging.getLogger()
    previous = root.handlers[:]
    try:
        configure_logging()
        register_secret(TEST_ONLY_OPENCODE_CREDENTIAL)
        logging.getLogger("station.test").error(
            "connection configured with %s", TEST_ONLY_OPENCODE_CREDENTIAL
        )

        try:
            raise RuntimeError(f"upstream said: {TEST_ONLY_OPENCODE_CREDENTIAL}")
        except RuntimeError:
            logging.getLogger("station.test").exception("simulated failure")

        captured = capsys.readouterr()
        _assert_clean(captured.err.encode(), "stderr logging")
        _assert_clean(captured.out.encode(), "stdout logging")
    finally:
        root.handlers[:] = previous


def test_the_credential_is_absent_from_the_frontend_bundle(web_dist_root: Path) -> None:
    """The canary cannot reach a build, but the check documents the surface."""
    if not (web_dist_root / "index.html").is_file():
        pytest.fail(
            "production build missing. Run: npm --prefix apps/station-web run build"
        )
    for path in web_dist_root.rglob("*"):
        if path.is_file() and path.suffix in {".js", ".css", ".html"}:
            _assert_clean(path.read_bytes(), f"the bundle file {path.name}")


# ---------------------------------------------------------------------------
# The outbound request, and a reflected key
# ---------------------------------------------------------------------------


def test_the_outbound_request_carries_the_credential_in_one_header_and_nowhere_else() -> None:
    """It has to go somewhere. It goes in exactly one place."""
    transport, recorder = recording_transport(
        lambda _: httpx.Response(200, content=b"{}")
    )
    client = OpenCodeClient(transport=transport, sleep=lambda _: None)
    client.post_completion(
        Protocol.CHAT_COMPLETIONS,
        b'{"model": "TEST-ONLY"}',
        api_key=TEST_ONLY_OPENCODE_CREDENTIAL,
    )

    request = recorder.last
    _assert_clean(str(request.url).encode(), "the request URL")
    _assert_clean(request.content, "the request body")

    carrying = [
        name
        for name, value in request.headers.items()
        if TEST_ONLY_OPENCODE_CREDENTIAL in value
    ]
    assert carrying == ["authorization"]


def test_an_upstream_body_that_echoes_the_credential_never_reaches_the_user() -> None:
    """The reflected-key case, end to end (ADR-0005 8).

    The provider is under no obligation to be careful with what it quotes
    back. Our own display is, so the excerpt is computed while the credential
    is still registered for redaction - and the failure detail that reaches
    the UI carries ``<redacted>`` instead.
    """
    reflected = json.dumps(
        {
            "error": {
                "message": f"invalid key: {TEST_ONLY_OPENCODE_CREDENTIAL}",
                "type": "authentication_error",
            }
        }
    ).encode()
    transport, _ = recording_transport(
        lambda _: httpx.Response(401, content=reflected)
    )
    client = OpenCodeClient(transport=transport, sleep=lambda _: None)

    raw = client.post_completion(
        Protocol.CHAT_COMPLETIONS, b"{}", api_key=TEST_ONLY_OPENCODE_CREDENTIAL
    )
    _assert_clean(raw.excerpt.encode(), "the response excerpt")
    assert "<redacted>" in raw.excerpt

    event = parse_response(Protocol.CHAT_COMPLETIONS, raw, model="TEST-ONLY")
    assert event.failure is not None
    _assert_clean(event.failure.detail.encode(), "the failure detail")


def test_the_credential_is_dropped_from_the_registry_when_the_request_ends() -> None:
    """Registered for exactly as long as it is in use, and no longer.

    A registry that only grows is a registry that eventually scrubs ordinary
    log lines, which is how a redaction control gets switched off.
    """
    from station_api.logging_setup import contains_registered_secret

    transport, _ = recording_transport(lambda _: httpx.Response(200, content=b"{}"))
    client = OpenCodeClient(transport=transport, sleep=lambda _: None)
    client.post_completion(
        Protocol.MESSAGES, b"{}", api_key=TEST_ONLY_OPENCODE_CREDENTIAL
    )

    assert not contains_registered_secret(TEST_ONLY_OPENCODE_CREDENTIAL)


def test_the_credential_is_dropped_even_when_the_request_fails() -> None:
    from station_api.logging_setup import contains_registered_secret
    from station_api.opencode.errors import OpenCodeLostResponseError

    def explode(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated")

    client = OpenCodeClient(
        transport=httpx.MockTransport(explode), sleep=lambda _: None
    )
    with pytest.raises(OpenCodeLostResponseError):
        client.post_completion(
            Protocol.RESPONSES, b"{}", api_key=TEST_ONLY_OPENCODE_CREDENTIAL
        )

    assert not contains_registered_secret(TEST_ONLY_OPENCODE_CREDENTIAL)


# ---------------------------------------------------------------------------
# The error path, which the surfaces above did not cover
# ---------------------------------------------------------------------------
#
# Everything before this point inspects a **successful** store and the reads
# that follow it. That left the rejection path unmeasured, and the rejection
# path was where the credential actually escaped: ``api_key`` is a
# ``SecretStr``, but a *type* error is raised before the value is ever
# wrapped in one, so FastAPI's default validation handler answered 422 with
# Pydantic's error list - and every entry of that list carries ``input``, the
# submitted value, verbatim.
#
# These do not need DPAPI: nothing is stored, which is the whole point.


def _rejecting_client(
    settings: Settings, engine: Engine, base_url: str
) -> tuple[TestClient, FastAPI]:
    app = create_app(settings=settings, port=TEST_PORT, engine=engine, web_dist=None)
    return TestClient(app, base_url=base_url), app


def test_a_rejected_credential_body_is_not_quoted_back_in_the_422(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """The canary, sent in a shape the schema refuses (SI-243).

    A list where a string is expected fails at the type level, which is
    exactly the case ``SecretStr`` cannot help with. The answer must name the
    field and the rule and nothing else.
    """
    client, app = _rejecting_client(settings, engine, base_url)
    with client:
        csrf = establish_session(client, app)
        response = client.post(
            "/api/opencode/credential",
            json={"api_key": [TEST_ONLY_OPENCODE_CREDENTIAL]},
            headers={"X-Station-CSRF": csrf},
        )

    assert response.status_code == 422
    _assert_clean(response.content, "the 422 body")
    rendered = " ".join(f"{key}: {value}" for key, value in response.headers.items())
    _assert_clean(rendered.encode(), "the 422 headers")

    # The half that has to survive: a caller still learns what was wrong.
    entries = response.json()["detail"]
    assert entries, "the rejection must still say what it refused"
    assert entries[0]["loc"] == ["body", "api_key"]
    assert entries[0]["type"] == "string_type"
    assert "input" not in entries[0]
    assert "ctx" not in entries[0]


def test_a_rejected_body_carries_no_submitted_value_on_any_route(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """The rule is global, not a patch on one route.

    ``/api/opencode/model`` has no secret field, and that is the point: the
    shield is registered for the application, so a body rejected anywhere
    describes the rule rather than repeating what was sent.
    """
    client, app = _rejecting_client(settings, engine, base_url)
    marker = "SUBMITTEDVALUEMARKER0123456789"
    with client:
        csrf = establish_session(client, app)
        response = client.post(
            "/api/opencode/model",
            json={"model_id": {"nested": marker}, "training_acknowledged": False},
            headers={"X-Station-CSRF": csrf},
        )

    assert response.status_code == 422
    assert marker not in response.text
    for entry in response.json()["detail"]:
        assert "input" not in entry
        assert "ctx" not in entry


def test_the_422_carries_the_hardening_headers_and_is_never_cached(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """An exception handler's response is born outside the middleware chain.

    The 500 shield learned this once (SI-126). The 422 is built the same way
    and would have shipped bare without the same treatment.
    """
    client, app = _rejecting_client(settings, engine, base_url)
    with client:
        csrf = establish_session(client, app)
        response = client.post(
            "/api/opencode/credential",
            json={"api_key": 12345},
            headers={"X-Station-CSRF": csrf},
        )

    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Station-Request-Id"]


def test_the_stripper_drops_every_value_bearing_key_and_keeps_the_rest() -> None:
    """The rule itself, away from HTTP.

    Stated separately so a future edit that renames a key has one obvious
    place to fail, and so the shape check (a non-list, a non-dict entry) is
    pinned rather than assumed.
    """
    from station_api.security.middleware import (
        VALUE_BEARING_ERROR_KEYS,
        strip_submitted_values,
    )

    assert {"input", "ctx"} == VALUE_BEARING_ERROR_KEYS

    cleaned = strip_submitted_values(
        [
            {
                "type": "string_type",
                "loc": ["body", "api_key"],
                "msg": "Input should be a valid string",
                "input": [TEST_ONLY_OPENCODE_CREDENTIAL],
                "ctx": {"given": TEST_ONLY_OPENCODE_CREDENTIAL},
            }
        ]
    )
    assert cleaned == [
        {
            "type": "string_type",
            "loc": ["body", "api_key"],
            "msg": "Input should be a valid string",
        }
    ]
    _assert_clean(json.dumps(cleaned).encode(), "the stripped error list")

    # Anything unrecognised is dropped, never passed through.
    assert strip_submitted_values("not a list") == []
    assert strip_submitted_values([TEST_ONLY_OPENCODE_CREDENTIAL]) == []
