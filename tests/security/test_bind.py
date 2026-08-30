"""SI-01, SI-02, SI-03 - the application listens on loopback, on an OS-chosen port."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from station_api.config import LOOPBACK_HOST, Settings
from station_api.launcher import reserve_loopback_socket

pytestmark = pytest.mark.security

# Safe to name directly: the scans below cover apps/ only, never tests/, so
# this file can hold the literal it forbids elsewhere.
WILDCARD_IPV4 = "0.0.0.0"


def test_loopback_host_constant_is_the_literal_loopback_address() -> None:
    assert LOOPBACK_HOST == "127.0.0.1"


def test_launcher_binds_only_loopback(tmp_path: Path) -> None:
    settings = Settings(dev_mode=False, data_dir=tmp_path)
    sock, port = reserve_loopback_socket(settings)
    try:
        bound_host, bound_port = sock.getsockname()
        assert bound_host == "127.0.0.1"
        assert bound_port == port
    finally:
        sock.close()


def test_port_is_ephemeral(tmp_path: Path) -> None:
    """The operating system chooses the port, not the application.

    Three sockets are held open at once, so the ports are necessarily
    distinct. A hardcoded port would collide and could not produce three
    different values.
    """
    settings = Settings(dev_mode=False, data_dir=tmp_path)
    sockets: list[socket.socket] = []
    ports: list[int] = []
    try:
        for _ in range(3):
            sock, port = reserve_loopback_socket(settings)
            sockets.append(sock)
            ports.append(port)
    finally:
        for sock in sockets:
            sock.close()

    assert len(set(ports)) == 3
    for port in ports:
        assert 1024 < port < 65536


def test_bound_port_is_not_reachable_on_a_non_loopback_address(tmp_path: Path) -> None:
    """A wildcard bind would also answer on a LAN address. This one must not."""
    settings = Settings(dev_mode=False, data_dir=tmp_path)
    sock, port = reserve_loopback_socket(settings)
    try:
        for address in _non_loopback_addresses():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                with pytest.raises(OSError):
                    probe.connect((address, port))
    finally:
        sock.close()


def test_no_wildcard_bind_in_source(api_source_root: Path) -> None:
    offenders: list[str] = []
    for path in api_source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if WILDCARD_IPV4 in text or "INADDR_ANY" in text:
            offenders.append(str(path))
    assert offenders == [], f"wildcard bind found in: {offenders}"


def test_vite_dev_server_is_loopback_only(repo_root: Path) -> None:
    config = (repo_root / "apps" / "station-web" / "vite.config.ts").read_text(
        encoding="utf-8"
    )
    assert 'host: "127.0.0.1"' in config
    assert WILDCARD_IPV4 not in config
    assert "host: true" not in config


def _non_loopback_addresses() -> list[str]:
    """Best-effort list of this machine's non-loopback IPv4 addresses.

    An empty list is fine: the getsockname assertion above already proves the
    bind address, and this check is an additional, opportunistic probe.
    """
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = str(info[4][0])
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        return []
    return sorted(addresses)
