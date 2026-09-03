"""Shared fixtures.

No test in this suite contacts the real Technocore. Since Stage 3 the product
carries an outbound read client, and since Stage 4 it carries an outbound
*write* client as well, so this is no longer true by absence: it holds
because INV-05 forbids a test from reaching the network, and the tests drive
both clients through ``httpx.MockTransport`` instead.

Until Package D, nothing enforced that. A new test that forgot to inject a
mock transport would have gone to ``technocore.chat`` silently, and on the
write lane it would have published a message to a live public room. The
autouse fixture below removes that possibility (ADR-0002 4.4): the real
outbound transports are replaced for the whole session, so a forgotten mock
fails loudly instead of succeeding quietly.

Loopback is deliberately still allowed. ``tests/integration`` runs a real
uvicorn on ``127.0.0.1`` and talks to it over a real socket, which is the
point of those tests; the guard is about leaving this machine, not about
using HTTP.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine
from station_api.config import Settings
from station_api.db.migrations_runner import initialise_database

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# The outbound network guard (INV-05, ADR-0002 4.4)
# ---------------------------------------------------------------------------

#: Hosts a test may genuinely reach. Everything else is off this machine.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

#: The unpatched methods, captured at import time. Kept so the guard's own
#: test can prove the patch is installed rather than assuming it.
REAL_SYNC_HANDLE_REQUEST = httpx.HTTPTransport.handle_request
REAL_ASYNC_HANDLE_REQUEST = httpx.AsyncHTTPTransport.handle_async_request


class OutboundNetworkBlockedError(AssertionError):
    """A test tried to make a real request off this machine.

    An ``AssertionError`` on purpose. The read-only client catches
    ``httpx.TimeoutException`` and ``httpx.TransportError`` and turns them
    into an ``unavailable`` verdict, and the write client turns them into
    ``outcome_unknown`` - so an httpx-shaped exception here would be
    swallowed into a plausible-looking result and the missing mock would
    never be noticed. This class is outside both hierarchies, so it escapes
    every one of those handlers and fails the test.
    """


def _refuse(request: httpx.Request) -> OutboundNetworkBlockedError:
    return OutboundNetworkBlockedError(
        f"a test attempted a real {request.method} to {request.url.host!r}. "
        "No automated test may contact Technocore or any other host "
        "(AGENTS.md INV-05). Inject an httpx.MockTransport instead."
    )


def _is_loopback(request: httpx.Request) -> bool:
    return (request.url.host or "") in LOOPBACK_HOSTS


@pytest.fixture(scope="session", autouse=True)
def block_real_outbound_requests() -> Iterator[None]:
    """Replace httpx's real transports for the whole session.

    Patched at the transport layer rather than at the client layer because
    that is the single point every code path funnels through: a client built
    with no explicit transport gets an ``HTTPTransport``, and there is no way
    to reach the network past it.
    """

    def guarded_handle_request(
        self: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        if _is_loopback(request):
            return REAL_SYNC_HANDLE_REQUEST(self, request)
        raise _refuse(request)

    async def guarded_handle_async_request(
        self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        if _is_loopback(request):
            return await REAL_ASYNC_HANDLE_REQUEST(self, request)
        raise _refuse(request)

    httpx.HTTPTransport.handle_request = guarded_handle_request  # type: ignore[method-assign]
    httpx.AsyncHTTPTransport.handle_async_request = guarded_handle_async_request  # type: ignore[method-assign]
    try:
        yield
    finally:
        httpx.HTTPTransport.handle_request = REAL_SYNC_HANDLE_REQUEST  # type: ignore[method-assign]
        httpx.AsyncHTTPTransport.handle_async_request = REAL_ASYNC_HANDLE_REQUEST  # type: ignore[method-assign]

#: A fixed, plausible ephemeral port. The app only ever compares it against
#: the Host header; nothing binds it during these tests.
TEST_PORT = 49731


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def api_source_root(repo_root: Path) -> Path:
    return repo_root / "apps" / "station-api" / "src"


@pytest.fixture(scope="session")
def web_source_root(repo_root: Path) -> Path:
    return repo_root / "apps" / "station-web" / "src"


@pytest.fixture(scope="session")
def web_dist_root(repo_root: Path) -> Path:
    return repo_root / "apps" / "station-web" / "dist"


# ---------------------------------------------------------------------------
# TEST-ONLY key material.
#
# Every value below is a fixture, published in this repository, and must never
# be used for anything real. The leak-detection marker seed is deliberately
# unusual so a substring search for it is meaningful.
# ---------------------------------------------------------------------------

#: TEST-ONLY. NOT A REAL SEED.
TEST_ONLY_SEED_HEX = "4c7a1e9b3d5f8027a6c4e91b2d8f0356749ace1b2d4f6081a3c5e7092b4d6f81"

#: TEST-ONLY. A second fixture seed, for differential coverage.
TEST_ONLY_SEED_HEX_ALT = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"

#: TEST-ONLY passphrases. NOT REAL.
TEST_ONLY_VAULT_PASSPHRASE = "TEST-ONLY-vault-passphrase-0001"
TEST_ONLY_RECOVERY_PASSPHRASE = "TEST-ONLY-recovery-passphrase-01"
TEST_ONLY_WRONG_PASSPHRASE = "TEST-ONLY-wrong-passphrase-9999"


@pytest.fixture(scope="session")
def test_only_seed() -> bytes:
    return bytes.fromhex(TEST_ONLY_SEED_HEX)


# ---------------------------------------------------------------------------
# Application fixtures, shared by the security and integration packages.
# ---------------------------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "station-data"


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    """Production settings. Development mode is off, as it is by default."""
    return Settings(dev_mode=False, data_dir=data_dir)


@pytest.fixture
def dev_settings(data_dir: Path) -> Settings:
    return Settings(dev_mode=True, data_dir=data_dir)


@pytest.fixture
def engine(settings: Settings) -> Engine:
    return initialise_database(settings.database_path, stage=4)


@pytest.fixture
def base_url() -> str:
    return f"http://127.0.0.1:{TEST_PORT}"


@pytest.fixture
def fast_kdf_policy():  # type: ignore[no-untyped-def]
    """A cheap Argon2id policy so unit tests are not dominated by the KDF.

    Injected into the *library*; production endpoints always construct
    ``PRODUCTION_KDF_POLICY`` and its accept-bounds refuse these parameters,
    which is asserted in tests/security/test_identity_vault.py.
    """
    from station_api.vault.passphrase import KdfPolicy

    return KdfPolicy(
        time_cost=1,
        memory_cost_kib=8,
        parallelism=1,
        min_time_cost=1,
        max_time_cost=10,
        min_memory_cost_kib=8,
        max_memory_cost_kib=262144,
    )
