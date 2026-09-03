"""Fixtures for the evidence and audit tests.

Two things are deliberately **not** faked here.

The audit chain runs against the real DPAPI envelope, on the real filesystem,
in a temporary data directory. There is no in-memory chain and no injectable
MAC material: the property under test is that the material is protected by
DPAPI and that the head is a separate file, and a fake would test neither.
This follows ``test_identity_vault.py``'s discipline - the real thing, or an
assertion about the fail-closed path, never a silent substitute.

The export reads run against ``httpx.MockTransport``, which is the only
transport the evidence client accepts. No test contacts Technocore, and the
lobby is never a target (INV-05, ADR-0002 4.1).

Every seed, DID, room and passphrase referenced here is a TEST-ONLY fixture
published in this repository.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx
from sqlalchemy import Engine
from station_api.evidence.audit import AuditChain
from station_api.evidence.audit_envelope import AuditEnvelope
from station_api.evidence.service import EvidenceService
from station_api.technocore.evidence_client import EvidenceClient
from station_api.technocore.evidence_targets import GENERATION_HEADER

from tests.security.compose_fixtures import TEST_ONLY_DID, TEST_ROOM

#: A generation value that is plainly a fixture rather than a real epoch.
TEST_ONLY_GENERATION = "7"

#: A second one, for the "the room was recreated" case.
TEST_ONLY_GENERATION_NEXT = "8"


def record_line(
    *,
    seq: int,
    did: str = TEST_ONLY_DID,
    text: str = "TEST-ONLY mesaj",
    nonce: int = 1,
    signature: str = "A" * 85 + "A",
    timestamp: str = "2026-09-04T00:00:00.000000Z",
) -> bytes:
    """One NDJSON record in the shape the pinned reference writes.

    ``orjson.dumps(rec) + b"\\n"``: ``seq``, ``ts``, ``from``, ``text``, and
    on the signed lane ``nonce`` and ``sig``. Built here so a test can put a
    *specific* byte sequence in the stream and then assert that exactly those
    bytes came back - which is the whole point of a byte-exact export.
    """
    record = {
        "seq": seq,
        "ts": timestamp,
        "from": did,
        "text": text,
        "nonce": nonce,
        "sig": signature,
    }
    return json.dumps(record, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def ndjson(lines: Iterable[bytes]) -> bytes:
    """Join records the way the reference stores them: one per line."""
    return b"".join(line + b"\n" for line in lines)


def export_handler(
    body: bytes,
    *,
    status: int = 200,
    generation: str = TEST_ONLY_GENERATION,
    room: str = TEST_ROOM,
    headers: dict[str, str] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer one room's export, and 404 for anything else.

    The path is checked rather than ignored: a client that asked for a
    different room would otherwise be served the right answer to the wrong
    question, and the test would pass on a bug.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path != f"/r/{room}/export":
            return httpx.Response(404, text="not found")
        merged = {GENERATION_HEADER: generation, "Content-Type": "application/x-ndjson"}
        merged.update(headers or {})
        return httpx.Response(status, content=body, headers=merged)

    return respond


def export_transport(
    body: bytes,
    *,
    status: int = 200,
    generation: str = TEST_ONLY_GENERATION,
    room: str = TEST_ROOM,
    headers: dict[str, str] | None = None,
) -> httpx.MockTransport:
    """The same handler, wrapped in the only transport the client accepts."""
    return httpx.MockTransport(
        export_handler(
            body, status=status, generation=generation, room=room, headers=headers
        )
    )


def recording_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    sink: list[httpx.Request],
) -> httpx.MockTransport:
    """Wrap a handler and record every request that reached it."""

    def respond(request: httpx.Request) -> httpx.Response:
        sink.append(request)
        return handler(request)

    return httpx.MockTransport(respond)


def build_evidence(
    engine: Engine,
    data_dir: Path,
    *,
    transport: httpx.MockTransport | None = None,
) -> EvidenceService:
    """A fully wired evidence service: real chain, real envelope, mock reads."""
    service = EvidenceService(
        engine=engine,
        chain=AuditChain(engine, AuditEnvelope(data_dir)),
        client=EvidenceClient(transport=transport),
    )
    service.start()
    return service


__all__ = [
    "TEST_ONLY_GENERATION",
    "TEST_ONLY_GENERATION_NEXT",
    "build_evidence",
    "export_handler",
    "export_transport",
    "ndjson",
    "record_line",
    "recording_transport",
]
