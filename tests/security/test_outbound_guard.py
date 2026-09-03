"""The test suite's own outbound network guard (INV-05, ADR-0002 4.4).

Until Package D nothing stopped a test that forgot to inject an
``httpx.MockTransport`` from reaching ``technocore.chat`` for real. On the
read path that would have been a quiet dependency on a live service; on the
write path it would have published a message to a public room from a test
run.

These tests guard the guard. A control that is never itself verified tends to
stop working silently, and this one is invisible when it is working: every
test that has a mock transport behaves identically with or without it. So the
probes below assert the patch is installed, that it refuses a request that
would leave this machine, and - the load-bearing one - that a client
constructed *without* a transport now fails loudly rather than succeeding.

Two layers, and each is probed for what it actually covers. The httpx patch
closes httpx; it never saw ``socket``, ``urllib`` or a bare ``httpcore`` pool,
and the fixture's docstring used to imply that it did. The socket patch sits
under all of them. Both allow loopback, and both allow this host's own
addresses, because ``test_bind.py`` proves the loopback bind by probing them
and needing the OS - not a fixture - to refuse.
"""

from __future__ import annotations

import socket
import urllib.request

import httpx
import pytest
from station_api.technocore.client import ReadOnlyTechnocoreClient
from station_api.technocore.errors import SourceFetchError
from station_api.technocore.sources import SourceId, get_source
from station_api.technocore.write_client import SignedWriteClient, WriteOutcome
from station_api.technocore.write_targets import WriteTarget

from tests.conftest import (
    OWN_HOST_ADDRESSES,
    REAL_ASYNC_HANDLE_REQUEST,
    REAL_SOCKET_CONNECT,
    REAL_SYNC_HANDLE_REQUEST,
    OutboundNetworkBlockedError,
    is_local_address,
)

pytestmark = pytest.mark.security


def test_the_guard_is_actually_installed() -> None:
    """The patch is in place, not merely defined.

    Compared against the methods captured at import time, so this fails if
    the fixture is removed, renamed, made non-autouse or scoped away.
    """
    assert httpx.HTTPTransport.handle_request is not REAL_SYNC_HANDLE_REQUEST
    assert (
        httpx.AsyncHTTPTransport.handle_async_request is not REAL_ASYNC_HANDLE_REQUEST
    )


def test_a_real_outbound_request_raises_instead_of_leaving_the_machine() -> None:
    """The direct probe: the transport itself refuses a foreign host."""
    request = httpx.Request("GET", "https://technocore.chat/config")

    with pytest.raises(OutboundNetworkBlockedError) as caught:
        httpx.HTTPTransport().handle_request(request)

    assert "technocore.chat" in str(caught.value)
    assert "INV-05" in str(caught.value)


def test_a_read_client_with_no_mock_transport_fails_loudly() -> None:
    """The real regression this exists for.

    Without the guard this call would have gone to the live service and,
    quite likely, passed. The exception deliberately escapes the client's own
    error handling: ``fetch`` converts ``httpx.TransportError`` into a
    ``SourceFetchError`` and an ``unavailable`` verdict, which is exactly the
    plausible-looking result that would have hidden the missing mock.
    """
    client = ReadOnlyTechnocoreClient(sleep=lambda _: None)

    with pytest.raises(OutboundNetworkBlockedError):
        client.fetch(get_source(SourceId.CONFIG))


def test_the_guard_is_not_swallowed_by_the_read_clients_error_handling() -> None:
    """Stated separately because it is the property, not a side effect."""
    assert not issubclass(OutboundNetworkBlockedError, httpx.TransportError)
    assert not issubclass(OutboundNetworkBlockedError, httpx.TimeoutException)
    assert not issubclass(OutboundNetworkBlockedError, SourceFetchError)


def test_a_write_client_with_no_mock_transport_fails_loudly() -> None:
    """The same probe on the lane where a mistake would be published.

    ``send`` catches every transport failure and answers ``outcome_unknown``
    rather than raising, so an httpx-shaped block would have been reported as
    a normal three-valued result and the test would have passed. It must not
    be, and this asserts it is not.
    """
    client = SignedWriteClient()
    target = WriteTarget(room="mb-station-test-only", classes=("mb",))

    with pytest.raises(OutboundNetworkBlockedError):
        client.send(
            target,
            {"did": "did:key:zTEST", "sig": "TEST", "nonce": "1", "text": "TEST ONLY"},
        )


def test_loopback_is_still_reachable() -> None:
    """The guard blocks leaving the machine, not HTTP itself.

    ``tests/integration`` runs a real uvicorn on loopback and talks to it
    over a real socket. A guard that blocked that would either be disabled or
    worked around, and a control that gets worked around is not a control.
    """
    request = httpx.Request("GET", "http://127.0.0.1:1/nothing")

    # Connection refused is the *expected* answer here: nothing is listening
    # on port 1. What matters is which exception arrives - a transport error
    # means the guard let the attempt through.
    with pytest.raises(httpx.TransportError):
        httpx.HTTPTransport().handle_request(request)


# ---------------------------------------------------------------------------
# The second layer: below httpx, where the first one does not reach
# ---------------------------------------------------------------------------


def test_the_socket_layer_guard_is_installed() -> None:
    """Compared against the method captured at import, as above."""
    assert socket.socket.connect is not REAL_SOCKET_CONNECT


def test_a_raw_socket_to_a_foreign_host_is_refused() -> None:
    """The gap the httpx patch could never have covered.

    Nothing in the product opens a socket directly - httpx is confined to two
    reviewed modules and a test asserts it. This is about the *next* test:
    reaching for ``socket`` or a second HTTP library is how a suite quietly
    grows a live dependency, and the layer that catches all of them is this
    one.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        with pytest.raises(OutboundNetworkBlockedError) as caught:
            probe.connect(("93.184.216.34", 80))

    assert "INV-05" in str(caught.value)


def test_urllib_cannot_reach_a_foreign_host() -> None:
    """Named because the reviewer named it: ``urlopen`` bypassed the old patch.

    It never touches httpx, so it went straight out. It does end at
    ``socket.connect``, which is the point of putting the second layer there
    rather than enumerating libraries.
    """
    with pytest.raises(OutboundNetworkBlockedError):
        urllib.request.urlopen("http://93.184.216.34/nothing", timeout=1)


def test_httpcore_cannot_reach_a_foreign_host() -> None:
    """The third name on the reviewer's list, through httpx's own dependency.

    A pool used directly is not an ``httpx.HTTPTransport``, so the first layer
    never sees it.
    """
    import httpcore

    with pytest.raises(OutboundNetworkBlockedError):
        httpcore.ConnectionPool().request("GET", "http://93.184.216.34/nothing")


def test_a_loopback_socket_is_still_reachable() -> None:
    """The same allowance as the httpx layer, asserted at the socket layer.

    ``tests/integration`` connects to a real uvicorn over a real socket, so a
    refusal here would be a control that has to be switched off.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(2.0)
            probe.connect(("127.0.0.1", port))
            assert probe.getpeername()[0] == "127.0.0.1"


def test_this_machines_own_addresses_are_treated_as_local() -> None:
    """Why the allowance exists, stated where it can be checked.

    ``test_bind.py`` proves the loopback bind by *probing* this host's LAN
    addresses and requiring the OS to refuse. A guard that intercepted those
    probes would delete the evidence, and connecting to an address this host
    answers on has not left this host anyway.
    """
    for address in OWN_HOST_ADDRESSES:
        assert is_local_address(socket.AF_INET, (address, 9))


@pytest.mark.parametrize(
    "address",
    ["93.184.216.34", "8.8.8.8", "technocore.chat", "2606:4700:4700::1111"],
)
def test_a_foreign_address_is_not_treated_as_local(address: str) -> None:
    """The deny side, including a *name*, which could resolve anywhere."""
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    assert not is_local_address(family, (address, 443))


def test_the_write_outcome_enum_still_has_the_shape_the_guard_assumes() -> None:
    """A guard is only as good as the assumption behind it.

    The write probe above is meaningful because ``send`` would otherwise
    answer ``outcome_unknown``. If that ever stopped being true the probe
    would keep passing while testing nothing, so the assumption is pinned.
    """
    assert WriteOutcome.OUTCOME_UNKNOWN.value == "outcome_unknown"
