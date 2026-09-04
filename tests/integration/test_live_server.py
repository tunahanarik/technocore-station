"""End-to-end over a real loopback socket.

This exercises the actual launcher socket, a real uvicorn server and a real
HTTP client, so the guards are verified against genuine wire behaviour rather
than only through the in-process test transport.

Nothing here contacts the network beyond loopback (INV-05).
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from station_api.app import create_app
from station_api.config import Settings
from station_api.db.migrations_runner import initialise_database
from station_api.launcher import reserve_loopback_socket

from tests.security.test_module_registry import CURRENT_SCHEMA_STAGE

pytestmark = pytest.mark.integration

STARTUP_TIMEOUT_SECONDS = 20


class LiveServer:
    def __init__(self, port: int, app: FastAPI) -> None:
        self.port = port
        self.app = app

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[LiveServer]:
    settings = Settings(dev_mode=False, data_dir=tmp_path / "data")
    settings.ensure_data_dir()
    engine = initialise_database(settings.database_path, stage=1)

    sock, port = reserve_loopback_socket(settings)
    app = create_app(settings=settings, port=port, engine=engine, web_dist=None)

    config = uvicorn.Config(app=app, log_config=None, access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start in time"

    try:
        yield LiveServer(port=port, app=app)
    finally:
        server.should_exit = True
        thread.join(timeout=STARTUP_TIMEOUT_SECONDS)
        engine.dispose()


def test_health_is_reachable_on_loopback(live_server: LiveServer) -> None:
    response = httpx.get(f"{live_server.base_url}/api/health", timeout=10)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_full_session_handoff_over_the_wire(live_server: LiveServer) -> None:
    """Token -> cookie -> CSRF -> protected read, exactly as the browser does."""
    token = live_server.app.state.bootstrap_tokens.issue()

    with httpx.Client(base_url=live_server.base_url, timeout=10) as client:
        assert client.get("/api/app/status").status_code == 401

        handoff = client.get(f"/session/{token}", follow_redirects=False)
        assert handoff.status_code == 303
        assert handoff.headers["location"] == "/"

        bootstrap = client.get("/api/session/bootstrap")
        assert bootstrap.status_code == 200
        assert bootstrap.headers["cache-control"] == "no-store"
        csrf_token = bootstrap.json()["csrf_token"]
        assert csrf_token

        status = client.get("/api/app/status")
        assert status.status_code == 200
        payload = status.json()
        # Stage 3 replaced the placeholder "not_connected" with the honest
        # four-way state. A freshly launched server has contacted nobody, so
        # the only correct opening value is never_checked - which is also the
        # proof that starting Station makes no outbound request.
        assert payload["technocore"]["state"] == "never_checked"

        # These two deliberately differ, and the gap widens with every stage
        # that is not about writing. Stage 4 is the stage that opened writes
        # and that does not move again; stage 7 is the stage this build
        # implements. Collapsing them would either backdate the later work or
        # claim writes arrived several releases later than they did.
        #
        # The stage number is read from the one place the suite pins it, so
        # this file cannot drift a release behind the entry points the way
        # ``cli/__main__.py`` once did (SI-232).
        assert payload["technocore"]["write_available_from_stage"] == 4
        assert payload["service"]["stage"] == CURRENT_SCHEMA_STAGE

        # And the composer is honest about being shut on a fresh launch: no
        # check has run, so the manifest half of the gate blocks.
        capability = client.get("/api/compose/capability")
        assert capability.status_code == 200
        assert capability.json()["can_compose"] is False
        assert "manifest_current" in capability.json()["blocking_reasons"]
        # The note lane is absent by decision, and says so rather than
        # simply not being there (ADR-0002 1).
        assert capability.json()["note_lane_available"] is False
        assert capability.json()["note_lane_detail"]

        # The token is spent.
        assert client.get(f"/session/{token}", follow_redirects=False).status_code == 404


def test_wrong_host_is_rejected_over_the_wire(live_server: LiveServer) -> None:
    response = httpx.get(
        f"{live_server.base_url}/api/health",
        headers={"Host": f"localhost:{live_server.port}"},
        timeout=10,
    )
    assert response.status_code == 421


def test_security_headers_present_over_the_wire(live_server: LiveServer) -> None:
    response = httpx.get(f"{live_server.base_url}/api/health", timeout=10)
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert not [h for h in response.headers if h.lower().startswith("access-control-")]


def test_server_does_not_answer_on_a_non_loopback_address(live_server: LiveServer) -> None:
    for address in _non_loopback_addresses():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            with pytest.raises(OSError):
                probe.connect((address, live_server.port))


def test_no_technocore_endpoint_is_reachable(live_server: LiveServer) -> None:
    """No direct write surface, over a real socket.

    Stage 1's version of this said "no outbound client and no write surface
    at all". Package D makes the second half false on purpose, so the
    assertion has been split rather than dropped.

    These paths must still not exist: a bare signing endpoint, a
    message-or-note passthrough, an invented note lane. What replaced them is
    a three-request approval chain, and the composer routes are checked
    separately below - they exist, and they refuse an unapproved caller.
    """
    with httpx.Client(base_url=live_server.base_url, timeout=10) as client:
        for path in (
            "/api/identity/create",
            "/api/recovery",
            "/api/sign",
            "/api/technocore/message",
            "/api/technocore/note",
            "/api/technocore/send",
            "/api/compose/note",
            "/api/compose/say",
        ):
            assert client.post(path).status_code in {403, 404, 405}


def test_the_composer_refuses_an_unapproved_caller_over_the_wire(
    live_server: LiveServer,
) -> None:
    """The write lane exists and is shut to anyone without an approval.

    Over a real socket, with the real middleware stack. A ``send`` with a
    made-up token must never be accepted, and a caller with no session must
    not get past the guards at all.
    """
    with httpx.Client(base_url=live_server.base_url, timeout=10) as client:
        # No session, no CSRF: refused by the middleware, not by the route.
        assert client.post(
            "/api/compose/send", json={"send_token": "TEST-ONLY-not-a-real-token"}
        ).status_code in {401, 403}
        assert client.get("/api/compose/capability").status_code == 401

        # With a session and a CSRF value, an invented approval is still
        # refused - and with 409, meaning "there is no such approval",
        # rather than anything that could be mistaken for acceptance.
        token = live_server.app.state.bootstrap_tokens.issue()
        assert (
            client.get(f"/session/{token}", follow_redirects=False).status_code == 303
        )
        csrf = client.get("/api/session/bootstrap").json()["csrf_token"]

        refused = client.post(
            "/api/compose/send",
            headers={"X-Station-CSRF": csrf},
            json={"send_token": "TEST-ONLY-not-a-real-token"},
        )
        assert refused.status_code == 409
        assert refused.headers["x-station-compose-reason"] == "approval_invalid"


def test_no_write_is_possible_without_the_composer(live_server: LiveServer) -> None:
    """GET can never write, whatever Technocore's own protocol allows.

    Technocore performs writes over GET on its own service. Station's API
    must not mirror that: a GET on the composer's own paths is not a way to
    publish anything.
    """
    with httpx.Client(base_url=live_server.base_url, timeout=10) as client:
        for path in ("/api/compose/draft", "/api/compose/sign", "/api/compose/send"):
            assert client.get(path).status_code in {401, 403, 405}


def _non_loopback_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = str(info[4][0])
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        return []
    return sorted(addresses)
