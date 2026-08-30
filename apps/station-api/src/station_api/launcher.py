"""Process launcher.

The socket is bound before uvicorn starts so the operating system, not this
code, chooses the port. Nothing here ever binds a wildcard address: the host
is the ``LOOPBACK_HOST`` constant (INV-02, SI-01, SI-03).
"""

from __future__ import annotations

import logging
import socket
import webbrowser

import uvicorn

from station_api.app import DEFAULT_WEB_DIST, create_app
from station_api.config import LOOPBACK_HOST, Settings, load_settings
from station_api.db.migrations_runner import initialise_database
from station_api.logging_setup import configure_logging

logger = logging.getLogger("station")

LISTEN_BACKLOG = 128


def reserve_loopback_socket(settings: Settings) -> tuple[socket.socket, int]:
    """Bind a listening socket on loopback and report the chosen port.

    Port 0 asks the kernel for an ephemeral port, which is the production
    path. Development pins a port so the Vite proxy has a fixed target
    (IMP-109).
    """
    requested_port = settings.dev_port if settings.dev_mode else 0

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((LOOPBACK_HOST, requested_port))
        sock.listen(LISTEN_BACKLOG)
    except OSError:
        sock.close()
        raise

    bound_host, bound_port = sock.getsockname()
    if bound_host != LOOPBACK_HOST:
        sock.close()
        raise RuntimeError(f"refusing to serve on non-loopback address {bound_host}")

    return sock, bound_port


def bootstrap_url(*, port: int, token: str, settings: Settings) -> str:
    """Build the one-shot handoff URL.

    The return value contains a live token. It must be handed straight to the
    browser and never logged or printed.
    """
    if settings.dev_mode:
        return f"{settings.dev_origin}/session/{token}"
    return f"http://{LOOPBACK_HOST}:{port}/session/{token}"


def main() -> int:
    configure_logging()
    settings = load_settings()
    settings.ensure_data_dir()

    engine = initialise_database(settings.database_path, stage=1)
    sock, port = reserve_loopback_socket(settings)

    app = create_app(
        settings=settings,
        port=port,
        engine=engine,
        web_dist=DEFAULT_WEB_DIST,
    )

    token = app.state.bootstrap_tokens.issue()
    url = bootstrap_url(port=port, token=token, settings=settings)

    # The socket is already listening, so the browser's connection is queued
    # even though uvicorn has not started accepting yet.
    webbrowser.open(url)

    logger.info(
        "Technocore Station is listening on loopback port %d (mode=%s). "
        "A one-time session link was opened in your browser; it expires in %d seconds.",
        port,
        "development" if settings.dev_mode else "production",
        settings.bootstrap_token_ttl_seconds,
    )

    config = uvicorn.Config(
        app=app,
        host=LOOPBACK_HOST,
        port=port,
        workers=1,
        log_config=None,
        # The access log would record /session/<token>. Off at the source; the
        # redacting filter in logging_setup is the second barrier (SI-07).
        access_log=False,
    )
    uvicorn.Server(config).run(sockets=[sock])
    return 0
