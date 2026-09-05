"""Process launcher.

The socket is bound before uvicorn starts so the operating system, not this
code, chooses the port. Nothing here ever binds a wildcard address: the host
is the ``LOOPBACK_HOST`` constant (INV-02, SI-01, SI-03).
"""

from __future__ import annotations

import contextlib
import logging
import signal
import socket
import sys
import threading
import webbrowser
from collections.abc import Iterator
from types import FrameType
from typing import Final

import uvicorn

from station_api import single_instance
from station_api.app import create_app
from station_api.config import LOOPBACK_HOST, Settings, load_settings
from station_api.db.migrations_runner import SchemaAheadError, initialise_database
from station_api.logging_setup import configure_logging

logger = logging.getLogger("station")

LISTEN_BACKLOG = 128

#: The signals uvicorn shuts down on - and, having shut down, re-raises.
#:
#: ``uvicorn.Server.capture_signals`` installs its own handler for each of
#: these, records the one that arrived, restores whatever handler was there
#: before, and then calls ``signal.raise_signal`` on the recorded signal so
#: "the expected behaviour" happens after the graceful stop. Whatever that
#: restored handler does is therefore what the user sees *after* a perfectly
#: clean shutdown, and by default it is one of two bad endings:
#:
#: * ``SIGINT`` restores to ``signal.default_int_handler``, which raises
#:   ``KeyboardInterrupt`` out of ``Server.run``. ``main`` never reaches its
#:   ``return 0``, the process exits **1**, and a frozen build prints
#:   ``Failed to execute script ... due to unhandled exception!``.
#: * ``SIGBREAK`` restores to ``SIG_DFL``, and the Windows CRT's default for
#:   it ends the process immediately - exit code **3**, with no unwinding, so
#:   the ``finally`` that releases the single-instance lock never runs and
#:   the next launch is refused by a lock file nobody is holding.
#:
#: Both were measured on the real artefact and written down in
#: ``docs/verification/paket-i.md`` 13.3. ADR-0010 7 kept the console visible
#: on the grounds that it "is both the shutdown mechanism and the diagnostic
#: surface"; a shutdown mechanism that prints a crash and strands a lock file
#: falsifies that sentence, which is why this is fixed rather than noted.
SHUTDOWN_SIGNALS: Final[tuple[signal.Signals, ...]] = tuple(
    candidate
    for candidate in (
        signal.SIGINT,  # Ctrl+C, the documented way to stop Station.
        signal.SIGTERM,  # ``kill``; not delivered by Windows, harmless here.
        getattr(signal, "SIGBREAK", None),  # Ctrl+Break, Windows only.
    )
    if candidate is not None
)


def absorb_shutdown_signal(signum: int, frame: FrameType | None) -> None:
    """Swallow the signal uvicorn re-raises once it has already stopped.

    Doing nothing is the whole point and is not a swallowed error: by the
    time this runs the server has finished its graceful shutdown, so the
    signal has already had its effect. What is being suppressed is only the
    *second* effect - a traceback or an abort - that would land on top of a
    successful stop.
    """
    return None


@contextlib.contextmanager
def absorbing_shutdown_signals() -> Iterator[None]:
    """Make this process's shutdown signals no-ops for the duration.

    Installed **around** ``uvicorn.Server.run`` rather than inside it, so
    that the handler uvicorn saves and restores is this one. The window is
    kept as narrow as the server run itself: outside it a Ctrl+C still does
    what Python does by default, because absorbing a signal during start-up
    would mean a user could not interrupt a slow migration.

    ``signal.signal`` only works on the main thread, and a test or an
    embedder may call the launcher from another one; there the context
    manager is a no-op and the ``except KeyboardInterrupt`` in :func:`main`
    is what keeps the exit code honest.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous = {sig: signal.signal(sig, absorb_shutdown_signal) for sig in SHUTDOWN_SIGNALS}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


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

    # ADR-0010 8. Claimed before the database is opened, because the thing
    # being protected is the database and the audit chain head - claiming it
    # afterwards would leave the window this exists to close. The refusal is
    # a message and exit code 4, not a traceback: a user who double-clicked
    # the icon twice has done nothing wrong.
    try:
        lock = single_instance.acquire(settings.data_dir)
    except single_instance.AlreadyRunningError as exc:
        print(exc, file=sys.stderr)
        return 4

    # Everything from here on runs inside the lock's ``finally``, and the
    # span is the point. It used to start at ``uvicorn.Server.run``, which
    # left every start-up step outside it: a migration interrupted with
    # Ctrl+C, a port that could not be reserved, a bundle with no SPA - all
    # of them exited with ``station.lock`` still on disk, so the *next*
    # launch was refused by a lock nobody was holding.
    #
    # The last of those is the worst, and it is this package's own subject:
    # ``PackagedLayoutError`` is the refusal ADR-0010 1 added for a bundle
    # built wrong, and a user who met it once then met "Station is already
    # running" - a second, false diagnosis on top of the true one. Measured
    # and driven in
    # ``tests/security/test_packaging_boundary.py::
    # test_a_failure_during_start_up_does_not_strand_the_lock``.
    #
    # ``finally`` rather than ``atexit``: the lock is released on a clean
    # stop, on Ctrl-C, on Ctrl+Break and on an exception alike. A process
    # killed outright still leaves the file behind, which is why the refusal
    # above names it.
    try:
        # ADR-0010 6. An older build opening a newer database says so and
        # stops, rather than reaching Alembic's own "Can't locate revision"
        # from inside an upgrade. No explicit release here any more: the
        # ``finally`` below covers this return like every other exit.
        try:
            engine = initialise_database(settings.database_path, stage=10)
        except SchemaAheadError as exc:
            print(exc, file=sys.stderr)
            return 5

        sock, port = reserve_loopback_socket(settings)

        # ``web_dist`` is deliberately not passed: the default sentinel asks
        # ``station_api.resources`` which SPA *this* build ships, which is the
        # question ADR-0010 1 is about. A frozen build with no SPA beside it
        # raises here rather than serving the "not built yet" page.
        app = create_app(settings=settings, port=port, engine=engine)

        token = app.state.bootstrap_tokens.issue()
        url = bootstrap_url(port=port, token=token, settings=settings)

        # The socket is already listening, so the browser's connection is
        # queued even though uvicorn has not started accepting yet.
        webbrowser.open(url)

        logger.info(
            "Technocore Station is listening on loopback port %d (mode=%s). "
            "A one-time session link was opened in your browser; it expires "
            "in %d seconds.",
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
            # The access log would record /session/<token>. Off at the source;
            # the redacting filter in logging_setup is the second barrier
            # (SI-07).
            access_log=False,
        )
        # The ``with`` is what makes "on Ctrl+Break" true: see
        # :data:`SHUTDOWN_SIGNALS`. The ``except`` is the second barrier for
        # the case where the context manager could not install anything - it
        # catches ``KeyboardInterrupt``, which is a ``BaseException`` and
        # would otherwise sail past. It is scoped to the server run and not
        # to the whole body on purpose: an interrupt during a slow migration
        # must still end the process, because
        # ``absorbing_shutdown_signals`` deliberately does not cover
        # start-up. Neither of them touches an ordinary exception: a server
        # that actually crashes still propagates, still prints, and still
        # exits non-zero, because a crash must not be dressed up as a clean
        # stop.
        try:
            with absorbing_shutdown_signals():
                uvicorn.Server(config).run(sockets=[sock])
        except KeyboardInterrupt:
            logger.info("Technocore Station stopped on an interrupt.")
        return 0
    finally:
        lock.release()
