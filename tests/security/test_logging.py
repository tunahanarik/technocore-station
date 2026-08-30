"""SI-07, SI-23 - the bootstrap token and CSRF value never reach a log."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from station_api.config import Settings
from station_api.launcher import bootstrap_url
from station_api.logging_setup import configure_logging, redact, register_secret

pytestmark = pytest.mark.security


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Undo the global handler swap that configure_logging performs."""
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    yield
    root.handlers[:] = previous_handlers
    root.setLevel(previous_level)


def test_bootstrap_token_never_appears_in_logs(
    capsys: pytest.CaptureFixture[str], app: FastAPI
) -> None:
    configure_logging()
    token = app.state.bootstrap_tokens.issue()

    logging.getLogger("station.test").warning(
        "handoff opened at http://127.0.0.1:49731/session/%s", token
    )

    captured = capsys.readouterr()
    assert token not in captured.err
    assert token not in captured.out
    assert "<redacted>" in captured.err


def test_csrf_token_never_appears_in_logs(
    capsys: pytest.CaptureFixture[str], csrf_token: str
) -> None:
    configure_logging()

    logging.getLogger("station.test").error("csrf mismatch, expected %s", csrf_token)

    captured = capsys.readouterr()
    assert csrf_token not in captured.err
    assert "<redacted>" in captured.err


def test_session_url_shape_is_redacted_even_for_unknown_tokens() -> None:
    """The path pattern is scrubbed regardless of the registry."""
    line = "GET /session/AbCdEf0123456789_-XyZ HTTP/1.1"
    scrubbed = redact(line)
    assert "AbCdEf0123456789" not in scrubbed
    assert "/session/<redacted>" in scrubbed


def test_registered_secret_is_scrubbed_anywhere_in_a_line() -> None:
    secret = "TEST-ONLY-not-a-real-secret-value-0123456789"
    register_secret(secret)
    assert secret not in redact(f"prefix {secret} suffix")


def test_short_values_are_not_registered() -> None:
    """Scrubbing a short common string would corrupt unrelated log lines."""
    register_secret("abc")
    assert redact("abc def") == "abc def"


def test_bootstrap_url_is_never_passed_to_a_logger(api_source_root: Path) -> None:
    """The launcher hands the URL to the browser and nothing else."""
    launcher = (api_source_root / "station_api" / "launcher.py").read_text(encoding="utf-8")

    for line in launcher.splitlines():
        stripped = line.strip()
        if stripped.startswith(("logger.", "print(")):
            assert "url" not in stripped, f"launcher logs the handoff URL: {stripped}"


def test_uvicorn_access_log_is_disabled(api_source_root: Path) -> None:
    """The access log would record /session/<token> on every launch."""
    launcher = (api_source_root / "station_api" / "launcher.py").read_text(encoding="utf-8")
    assert "access_log=False" in launcher


def test_bootstrap_url_contains_the_token_and_is_therefore_sensitive(
    settings: Settings,
) -> None:
    """Documents why the URL must be treated as a secret."""
    token = "TEST-ONLY-token-value-0123456789abcdef"
    url = bootstrap_url(port=49731, token=token, settings=settings)
    assert url == f"http://127.0.0.1:49731/session/{token}"
    assert token not in redact(url)


def test_request_logging_does_not_leak_the_cookie(
    capsys: pytest.CaptureFixture[str], client: TestClient, app: FastAPI
) -> None:
    configure_logging()
    token = app.state.bootstrap_tokens.issue()
    client.get(f"/session/{token}", follow_redirects=False)
    client.get("/api/app/status")

    captured = capsys.readouterr()
    assert token not in captured.err
    assert token not in captured.out
