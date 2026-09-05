"""Run the real Station backend for the browser tests. Test harness only.

This file is deliberately **not** part of ``station_api``. It imports the
shipping application and changes nothing about it: same
:func:`~station_api.launcher.reserve_loopback_socket`, same
:func:`~station_api.app.create_app`, same middleware chain, same built SPA,
same security headers. Two things differ from
:func:`station_api.launcher.main`, and only two:

* ``webbrowser.open`` is not called - a test run must not hijack the
  developer's browser;
* bootstrap tokens are minted on demand through a directory watcher, because
  each Playwright worker needs its own one-shot session and the tokens live
  for thirty seconds (:data:`station_api.config.BOOTSTRAP_TOKEN_TTL_SECONDS`),
  so they cannot be handed out in advance.

The token channel is a directory, not a socket. Opening a second listening
port in a process whose whole security story is "one loopback port, one
ephemeral number" would have been the wrong thing to add for the convenience
of a test: a request is an empty file in ``tokens/req/``, the answer is a file
in ``tokens/out/``, and both live inside the throwaway data directory that the
test run deletes afterwards.

``STATION_DATA_DIR`` must be set by the caller and must be a temporary
directory. This refuses to run against the real ``%LOCALAPPDATA%`` tree
(INV: browser QA never touches the user's identity data - ADR-0006 2/3).
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from station_api.app import create_app
from station_api.config import LOOPBACK_HOST, load_settings
from station_api.db.migrations_runner import initialise_database
from station_api.launcher import reserve_loopback_socket
from station_api.logging_setup import configure_logging
from station_api.resources import shipped_web_dist

#: How often the token watcher looks for a request. Small enough that a test
#: never notices, large enough not to spin a core.
POLL_SECONDS = 0.02


def _refuse_production_data_dir(data_dir: Path) -> None:
    """Fail closed if this run would touch the user's real Station data.

    The check is on the *resolved* path, so a junction or a relative path
    cannot sneak past it.
    """
    raw = os.environ.get("STATION_DATA_DIR")
    if not raw:
        raise SystemExit("STATION_DATA_DIR must be set to a temporary directory")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        production = (Path(local_app_data) / "TechnocoreStation").resolve()
        resolved = data_dir.resolve()
        if resolved == production or production in resolved.parents:
            raise SystemExit(
                f"refusing to run browser tests against the production data directory {production}"
            )


def _serve_tokens(app: FastAPI, token_dir: Path, stop: threading.Event) -> None:
    """Answer one-shot token requests until the server shuts down.

    A request file named ``<id>`` in ``req/`` produces ``out/<id>`` holding a
    freshly issued token. The request file is removed first, so a crash here
    cannot make the same request answer twice.
    """
    requests = token_dir / "req"
    answers = token_dir / "out"
    requests.mkdir(parents=True, exist_ok=True)
    answers.mkdir(parents=True, exist_ok=True)

    while not stop.is_set():
        for request_file in sorted(requests.iterdir()):
            if not request_file.is_file():
                continue
            try:
                request_file.unlink()
            except OSError:  # pragma: no cover - raced with another sweep
                continue
            token: str = app.state.bootstrap_tokens.issue()
            answer = answers / request_file.name
            # Write then rename: the reader must never see a half-written
            # token and treat the truncated value as the real one.
            temporary = answer.with_suffix(".part")
            temporary.write_text(token, encoding="utf-8")
            temporary.replace(answer)
        stop.wait(POLL_SECONDS)


def main() -> int:
    configure_logging()
    settings = load_settings()
    _refuse_production_data_dir(settings.data_dir)
    settings.ensure_data_dir()

    if settings.dev_mode:
        raise SystemExit("browser tests run the production path; STATION_DEV must be off")

    engine = initialise_database(settings.database_path, stage=11)
    sock, port = reserve_loopback_socket(settings)

    # The same resolution the launcher uses, asked for once so the handshake
    # can report the directory the browser suite is actually being served
    # (ADR-0010 1: the SPA location is derived, never an environment value).
    web_dist = shipped_web_dist()
    if web_dist is None:  # pragma: no cover - the harness always runs in a checkout
        raise SystemExit("this build ships no SPA; run: npm --prefix apps/station-web run build")

    app = create_app(settings=settings, port=port, engine=engine, web_dist=web_dist)

    token_dir = Path(os.environ["STATION_E2E_TOKEN_DIR"])
    stop = threading.Event()
    watcher = threading.Thread(
        target=_serve_tokens, args=(app, token_dir, stop), daemon=True, name="e2e-token-watcher"
    )
    watcher.start()

    handshake = Path(os.environ["STATION_E2E_HANDSHAKE"])
    payload = {
        "origin": f"http://{LOOPBACK_HOST}:{port}",
        "host": LOOPBACK_HOST,
        "port": port,
        "data_dir": str(settings.data_dir.resolve()),
        "database_path": str(settings.database_path.resolve()),
        "web_dist": str(web_dist.resolve()),
        "pid": os.getpid(),
    }
    # Same write-then-rename discipline: the Node side polls for this file and
    # must never parse a partial one.
    temporary = handshake.with_suffix(".part")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(handshake)

    config = uvicorn.Config(
        app=app,
        host=LOOPBACK_HOST,
        port=port,
        workers=1,
        log_config=None,
        access_log=False,
    )
    try:
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
