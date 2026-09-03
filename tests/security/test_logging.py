"""SI-07, SI-23, SI-127 - no secret reaches a log, on any record surface."""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from station_api.config import Settings
from station_api.launcher import bootstrap_url
from station_api.logging_setup import (
    FILTERED_LOGGER_NAMES,
    RedactingFilter,
    configure_logging,
    redact,
    register_secret,
)

pytestmark = pytest.mark.security

#: TEST-ONLY. Never a real token; long enough that register_secret accepts it.
TEST_ONLY_REGISTERED_SECRET = "TEST-ONLY-registered-secret-0123456789abcdef"

#: TEST-ONLY. Matches the ``/session/<token>`` scrub pattern.
TEST_ONLY_SESSION_PATH = "/session/AbCdEf0123456789_-XyZ"


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Undo every global mutation configure_logging performs.

    Both the root handler swap and the filters bound to the uvicorn loggers,
    which live on for the whole process otherwise.
    """
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    previous_filters = {
        name: logging.getLogger(name).filters[:] for name in FILTERED_LOGGER_NAMES
    }
    yield
    root.handlers[:] = previous_handlers
    root.setLevel(previous_level)
    for name, filters in previous_filters.items():
        logging.getLogger(name).filters[:] = filters


class SecretBearingPayload:
    """An object whose ``repr`` embeds secrets.

    Nothing ever hands these strings to a logger. They exist only inside the
    exception, which is precisely how a real failure leaks: FastAPI's
    ``ResponseValidationError`` puts the whole offending response into its own
    message, and that message is rendered by the *formatter*, long after every
    filter has run.
    """

    def __repr__(self) -> str:
        return (
            f"SecretBearingPayload(token={TEST_ONLY_REGISTERED_SECRET!r}, "
            f"url={TEST_ONLY_SESSION_PATH!r})"
        )


def _assert_scrubbed(output: str) -> None:
    """Neither secret shape survives, and the redaction marker proves it ran."""
    assert TEST_ONLY_REGISTERED_SECRET not in output, "a registered secret reached the log"
    assert "AbCdEf0123456789" not in output, "a /session/<token> path reached the log"
    assert "<redacted>" in output, "nothing was redacted at all"


@pytest.fixture
def shipped_log_sink() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    """A real handler carrying the **shipped** formatter and filter.

    Not a replica: ``configure_logging`` installs the production handler on
    root, and this fixture reuses that handler's own formatter and filters on
    a StringIO sink. Assertions therefore run on the text the product would
    write *after* ``Formatter.format``, which is the only moment a traceback
    or a stack dump exists at all.
    """
    configure_logging()
    shipped = logging.getLogger().handlers[0]

    stream = io.StringIO()
    sink = logging.StreamHandler(stream)
    sink.setFormatter(shipped.formatter)
    for existing in shipped.filters:
        sink.addFilter(existing)

    logger = logging.getLogger("station.test.sink")
    logger.handlers = [sink]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield logger, stream
    logger.handlers = []
    logger.propagate = True


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


# ---------------------------------------------------------------------------
# SI-127 - the traceback and the stack dump are redacted too
#
# These assert on **formatted handler output**, never on ``record.exc_info``.
# A record's exc_info is the raw exception object by definition, so a test
# that inspects it cannot fail no matter how badly the filter leaks; the
# traceback only becomes text inside ``Formatter.format``.
# ---------------------------------------------------------------------------


def test_a_traceback_is_redacted_in_the_formatted_log_output(
    shipped_log_sink: tuple[logging.Logger, io.StringIO],
) -> None:
    """The exception carries the secret; no argument to the logger does."""
    logger, stream = shipped_log_sink
    register_secret(TEST_ONLY_REGISTERED_SECRET)

    try:
        raise RuntimeError(SecretBearingPayload())
    except RuntimeError:
        logger.exception("Unhandled exception while serving a request; request_id=%s", "0" * 32)

    output = stream.getvalue()
    assert "Traceback (most recent call last)" in output, "the traceback must still be logged"
    _assert_scrubbed(output)


def test_a_chained_cause_in_a_traceback_is_redacted(
    shipped_log_sink: tuple[logging.Logger, io.StringIO],
) -> None:
    """``raise ... from ...`` renders the cause too, and the cause leaks alike."""
    logger, stream = shipped_log_sink
    register_secret(TEST_ONLY_REGISTERED_SECRET)

    try:
        try:
            raise ValueError(SecretBearingPayload())
        except ValueError as cause:
            raise RuntimeError("wrapped") from cause
    except RuntimeError:
        logger.exception("Unhandled exception while serving a request")

    output = stream.getvalue()
    assert "direct cause" in output, "the chained cause must still be logged"
    _assert_scrubbed(output)


def test_a_stack_dump_is_redacted_in_the_formatted_log_output(
    shipped_log_sink: tuple[logging.Logger, io.StringIO],
) -> None:
    """``stack_info`` is appended verbatim by the formatter, so the filter -
    not the formatter - is the only place it can be scrubbed."""
    logger, stream = shipped_log_sink
    register_secret(TEST_ONLY_REGISTERED_SECRET)

    record = logger.makeRecord(
        logger.name, logging.ERROR, __file__, 0, "stack dump follows", None, None
    )
    record.stack_info = (
        'Stack (most recent call last):\n  File "handoff.py", line 1, in open_session\n'
        f"    open({TEST_ONLY_SESSION_PATH!r}, token={TEST_ONLY_REGISTERED_SECRET!r})\n"
    )
    logger.handle(record)

    output = stream.getvalue()
    assert "Stack (most recent call last)" in output, "the stack dump must still be logged"
    _assert_scrubbed(output)


def test_an_already_rendered_exc_text_is_redacted(
    shipped_log_sink: tuple[logging.Logger, io.StringIO],
) -> None:
    """A formatter earlier in the chain may have cached the raw traceback;
    the cached value must never be the one that reaches a sink."""
    logger, stream = shipped_log_sink
    register_secret(TEST_ONLY_REGISTERED_SECRET)

    record = logger.makeRecord(
        logger.name, logging.ERROR, __file__, 0, "traceback follows", None, None
    )
    record.exc_text = (
        "Traceback (most recent call last):\n"
        f"RuntimeError: rejected {TEST_ONLY_REGISTERED_SECRET} at {TEST_ONLY_SESSION_PATH}\n"
    )
    logger.handle(record)

    _assert_scrubbed(stream.getvalue())


def test_the_uvicorn_loggers_carry_the_filter_themselves(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Starlette's ServerErrorMiddleware re-raises after the shield has run,
    so uvicorn logs the *same* traceback a second time through
    ``uvicorn.error``. That second copy must be scrubbed as well."""
    configure_logging()
    assert "uvicorn.error" in FILTERED_LOGGER_NAMES
    for name in FILTERED_LOGGER_NAMES:
        attached = logging.getLogger(name).filters
        assert any(isinstance(item, RedactingFilter) for item in attached), name

    register_secret(TEST_ONLY_REGISTERED_SECRET)
    try:
        raise RuntimeError(SecretBearingPayload())
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")

    _assert_scrubbed(capsys.readouterr().err)


def test_configuring_logging_twice_does_not_stack_filters() -> None:
    """``configure_logging`` is called by the launcher and by tests; the
    filter list must not grow without bound."""
    configure_logging()
    configure_logging()
    for name in FILTERED_LOGGER_NAMES:
        attached = logging.getLogger(name).filters
        assert sum(isinstance(item, RedactingFilter) for item in attached) == 1, name


def test_the_shielded_500_traceback_is_redacted_end_to_end(
    capsys: pytest.CaptureFixture[str], app: FastAPI, base_url: str
) -> None:
    """The whole product path at once: an unhandled exception whose payload
    carries live secrets, through the shield, the application logger, the
    shipped root handler and its formatter, onto the real stream."""
    register_secret(TEST_ONLY_REGISTERED_SECRET)

    @app.get("/api/probe/secret-boom", include_in_schema=False)
    async def probe_secret_boom() -> dict[str, str]:
        raise RuntimeError(SecretBearingPayload())

    configure_logging()
    with TestClient(app, base_url=base_url, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/probe/secret-boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "internal_error"}

    captured = capsys.readouterr()
    assert "Traceback (most recent call last)" in captured.err, "the traceback must be logged"
    _assert_scrubbed(captured.err)
    assert TEST_ONLY_REGISTERED_SECRET not in captured.out
