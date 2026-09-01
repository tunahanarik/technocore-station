"""The official documents the Stage 3 tests run against.

These are **not** hand-written, and they are not a transcription of the live
service. They are the bytes produced by executing the pinned official
generator, stored in ``technocore_reference/`` and byte-compared against a
fresh run by :mod:`tests.conformance.test_manifest_oracle`.

The distinction matters because the previous version of this file *was*
hand-written from a reading of the live document, and the reading was wrong:
it put the ``sig``/``nonce`` constraints directly under ``schema.properties``,
where the reference publishes only a description. Every test then agreed with
the projection because both carried the same mistake, and the real service
looked like it had changed the signature format.

They exist as files rather than as live fetches so the suite is deterministic
and offline: no automated test may contact Technocore (INV-05), and asserting
on a 429 or a redirect requires a transport we control anyway.

Provenance - upstream commit, generation command, file SHA-256 and the JSON
paths the projection reads - is recorded in
``technocore_reference/PROVENANCE.md``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

#: Where the generated documents live.
REFERENCE_ROOT = Path(__file__).resolve().parent / "technocore_reference"

#: These are the *pinned* version's documents, not the live service's. The
#: live service may be newer, and on the last observation it was; see
#: ``docs/read-only-technocore.md``.
PINNED_COMMIT = "7707cb63ebf638e8ef0cf59d1364818b9fef7d24"


def _load(name: str) -> Any:
    return json.loads((REFERENCE_ROOT / name).read_text(encoding="utf-8"))


#: Loaded once; every caller gets a deep copy so a mutating test cannot leak
#: into the next one.
_OPENAPI: Any = _load("openapi.json")
_AGENT: Any = _load("agent.json")

#: The supplementary documents carry no contract the projection reads, so a
#: short plausible body is enough; nothing asserts on their content beyond the
#: fact that a fetch happened.
_CONFIG: dict[str, Any] = {
    "service": "technocore-chat",
    "version": "0.10.0",
    "env_prefix": "CHAT_",
    "settings": {"rate_read": 120, "rate_write": 30},
    "withheld": {"CHAT_ROOT": "A filesystem path on the host."},
}
_HEALTH = "ok"
_MANUAL = "# technocore-chat manual\nRead a room with GET.\n"
_SKILL = "# skill\nUse the documented endpoints.\n"


def build_documents(*, parsed: bool = False) -> dict[str, Any]:
    """The six documents.

    ``parsed=False`` returns them keyed by request path, ready for a mock
    transport. ``parsed=True`` returns the two JSON documents keyed by a short
    name, ready to hand to the projection.
    """
    if parsed:
        return {
            "openapi": copy.deepcopy(_OPENAPI),
            "agent": copy.deepcopy(_AGENT),
            "config": copy.deepcopy(_CONFIG),
        }

    return {
        "/.well-known/agent.json": copy.deepcopy(_AGENT),
        "/openapi.json": copy.deepcopy(_OPENAPI),
        "/config": copy.deepcopy(_CONFIG),
        "/healthz": _HEALTH,
        "/llms.txt": _MANUAL,
        "/skill.md": _SKILL,
    }


def document_bytes(path: str) -> bytes:
    """The exact bytes a mock transport should return for ``path``."""
    body = build_documents()[path]
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body).encode("utf-8")


def message_body_schema(openapi: dict[str, Any]) -> dict[str, Any]:
    """The message POST request-body schema, for tests that mutate it."""
    schema = openapi["paths"]["/r/{room}"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert isinstance(schema, dict)
    return schema


def note_body_schema(openapi: dict[str, Any]) -> dict[str, Any]:
    """The note POST request-body schema, for tests that mutate it."""
    schema = openapi["paths"]["/kv/{ns}/{key}"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert isinstance(schema, dict)
    return schema


def signed_lane(schema: dict[str, Any]) -> dict[str, Any]:
    """The ``dependentSchemas.did`` node - where the credentials really live."""
    lane = schema["dependentSchemas"]["did"]
    assert isinstance(lane, dict)
    return lane


__all__ = [
    "PINNED_COMMIT",
    "REFERENCE_ROOT",
    "build_documents",
    "document_bytes",
    "message_body_schema",
    "note_body_schema",
    "signed_lane",
]
