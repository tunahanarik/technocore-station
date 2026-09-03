"""Fixtures for the composer tests.

Two seams, and both are the ones the product already offers for the same
reason ``IdentityService`` offers a vault seam: so the behaviour under test
can be exercised without a DPAPI vault, on a machine that may not have one.

* :class:`StubIdentity` stands in for the identity service. The composer
  depends on ``ComposeIdentity`` - two methods, "is the gate open" and "which
  key signs" - so the stub is exactly that and nothing more. What is being
  tested is that the composer *asks*, at every step, and refuses when the
  answer is no; a real vault would not make that a stronger assertion.

* :class:`TestOnlySigner` signs with a published TEST-ONLY seed. It is the
  same ``sign_payload`` the product calls, given the same canonical payload;
  what it skips is the vault unlock, which ``test_identity_vault.py`` covers
  on its own and which the Windows-only integration test exercises end to
  end.

Every seed, DID and passphrase here is a TEST-ONLY fixture published in this
repository. None of them is real, and none of them is ever used against a
real service: the write client is always driven through a mock transport,
and the lobby is never a target (INV-05).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import httpx
from sqlalchemy import Engine
from station_api.compose.nonce import NonceReserver
from station_api.compose.service import ComposeService
from station_api.identity.service import SigningIdentity
from station_api.identity.write_gate import WriteGateInput, WriteGateStatus, evaluate
from station_api.technocore.service import TechnocoreService
from station_api.technocore.write_client import SignedWriteClient
from technocore_conform import CanonicalPayload, did_key_from_seed, sign_payload

from tests.conftest import TEST_ONLY_SEED_HEX
from tests.security.technocore_fixtures import build_documents

#: TEST-ONLY. NOT A REAL SEED. Published in this repository.
TEST_ONLY_SEED = bytes.fromhex(TEST_ONLY_SEED_HEX)

#: The did:key that seed derives to. Computed rather than pasted, so it can
#: never drift away from the seed it belongs to.
TEST_ONLY_DID = did_key_from_seed(TEST_ONLY_SEED)

#: TEST-ONLY vault handle. Names nothing on disk in these tests.
TEST_ONLY_IDENTITY_ID = "0" * 32

#: TEST-ONLY rooms. Never the lobby, never a real room (INV-05).
TEST_ROOM = "mb-station-test-only"
TEST_ROOM_ALT = "e-station-test-only"

#: Every precondition met. The composer's starting point.
OPEN_GATE = WriteGateInput(
    has_identity=True,
    identity_revoked=False,
    vault_present=True,
    recovery_verified=True,
    conformance_verified=True,
    manifest_current=True,
)


class StubIdentity:
    """A controllable ``ComposeIdentity``.

    ``gate_input`` is mutable on purpose: the tests need the gate to change
    *between* two composer steps, which is the whole point of re-running it
    at each one.
    """

    def __init__(
        self,
        *,
        gate_input: WriteGateInput = OPEN_GATE,
        identity_id: str = TEST_ONLY_IDENTITY_ID,
        did: str = TEST_ONLY_DID,
    ) -> None:
        self.gate_input = gate_input
        self.identity_id = identity_id
        self.did = did
        #: Counts how many times the composer asked. A step that skipped the
        #: gate would show up here as a missing increment.
        self.gate_calls = 0

    def write_gate_status(self) -> WriteGateStatus:
        self.gate_calls += 1
        return evaluate(self.gate_input)

    def active_signing_identity(self) -> SigningIdentity:
        return SigningIdentity(identity_id=self.identity_id, did=self.did)

    def close_gate(self, **changes: bool) -> None:
        """Flip one precondition off, as it would flip in real use."""
        self.gate_input = replace(self.gate_input, **changes)


class TestOnlySigner:
    """Signs with the published TEST-ONLY seed. Never touches a vault."""

    def __init__(self, seed: bytes = TEST_ONLY_SEED) -> None:
        self._seed = seed
        #: Every payload this signer was asked to sign, so a test can assert
        #: on what was signed rather than only on what came back.
        self.signed: list[CanonicalPayload] = []

    def sign(
        self, payload: CanonicalPayload, *, identity_id: str, passphrase: str | None
    ) -> str:
        del identity_id, passphrase
        self.signed.append(payload)
        return sign_payload(payload, seed=self._seed)


class CountingWriteClient:
    """Wraps the real write client and counts what left the process."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        self.client = SignedWriteClient(transport=httpx.MockTransport(recording))

    @property
    def send_count(self) -> int:
        return len(self.requests)


def answering(status: int, *, body: str = "{}") -> Callable[
    [httpx.Request], httpx.Response
]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body)

    return handler


def raising(error: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


def official_documents_transport() -> httpx.MockTransport:
    """Serves the pinned official documents, so the check verdict is real."""
    docs = build_documents()

    def respond(request: httpx.Request) -> httpx.Response:
        body = docs.get(request.url.path)
        if body is None:
            return httpx.Response(404, text="not found")
        if isinstance(body, dict):
            return httpx.Response(200, json=body)
        return httpx.Response(200, text=body, headers={"Content-Type": "text/plain"})

    return httpx.MockTransport(respond)


def checked_technocore(engine: Engine) -> TechnocoreService:
    """A technocore service that has run one successful, offline check.

    Real projection, real verdict, real room-class markers read from the
    pinned manifest - and no network, because the transport is a mock.
    """
    from station_api.technocore.client import ReadOnlyTechnocoreClient

    service = TechnocoreService(
        engine=engine,
        client=ReadOnlyTechnocoreClient(
            transport=official_documents_transport(), sleep=lambda _: None
        ),
    )
    service.refresh()
    return service


@dataclass
class ComposeHarness:
    """Everything a composer test needs, wired together."""

    service: ComposeService
    identity: StubIdentity
    signer: TestOnlySigner
    writes: CountingWriteClient
    technocore: TechnocoreService
    reserver: NonceReserver
    session_id: str = "TEST-ONLY-session"


def build_harness(
    engine: Engine,
    *,
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
    identity: StubIdentity | None = None,
    technocore: TechnocoreService | None = None,
    reserver: NonceReserver | None = None,
) -> ComposeHarness:
    stub = identity if identity is not None else StubIdentity()
    live = technocore if technocore is not None else checked_technocore(engine)
    signer = TestOnlySigner()
    writes = CountingWriteClient(handler if handler is not None else answering(200))
    counter = reserver if reserver is not None else NonceReserver(engine)

    return ComposeHarness(
        service=ComposeService(
            identity=stub,
            technocore=live,
            reserver=counter,
            signer=signer,
            write_client=writes.client,
        ),
        identity=stub,
        signer=signer,
        writes=writes,
        technocore=live,
        reserver=counter,
    )


__all__ = [
    "OPEN_GATE",
    "TEST_ONLY_DID",
    "TEST_ONLY_IDENTITY_ID",
    "TEST_ONLY_SEED",
    "TEST_ROOM",
    "TEST_ROOM_ALT",
    "ComposeHarness",
    "CountingWriteClient",
    "StubIdentity",
    "TestOnlySigner",
    "answering",
    "build_harness",
    "checked_technocore",
    "official_documents_transport",
    "raising",
]
