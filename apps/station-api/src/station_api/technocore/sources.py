"""The closed registry of official read-only sources.

This module is the entire external surface of Station. A URL that is not
built from an entry here cannot be requested, because the client takes a
``SourceId`` and never a URL: there is no code path from user input, a
request body or a database row to an outbound address.

Why a registry rather than a base URL plus a path argument
----------------------------------------------------------
Technocore performs **writes over GET**. ``/r/{room}/say-signed/...`` and
``/kv/{ns}/{key}/set/...`` are both GET requests that append to a room or
overwrite a note. So "only GET" is not a safety property here, and any API
that accepted a caller-supplied path would be one bug away from writing to a
live public room. Enumerating the six documents we actually read removes that
category of mistake rather than guarding against it.

Every entry below was verified against the live service and against
``/openapi.json``; none is guessed.

Authority levels follow the specification (§21.1): level 1 is a machine
readable manifest or config that runtime behaviour may depend on, level 2 is
official prose documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: The one origin this application may contact. Scheme, host and the implicit
#: default port 443 are all fixed. There is no setting that changes it.
TECHNOCORE_ORIGIN = "https://technocore.chat"

#: Exact host expected in the origin. Compared literally, so a sub-domain, a
#: trailing dot, an IP address or user-info cannot match.
TECHNOCORE_HOST = "technocore.chat"

#: Only the default HTTPS port is acceptable.
TECHNOCORE_PORT = 443

TECHNOCORE_SCHEME = "https"


class SourceId(StrEnum):
    """Stable identifiers for the documents Station reads."""

    AGENT_MANIFEST = "agent_manifest"
    OPENAPI = "openapi"
    CONFIG = "config"
    HEALTH = "health"
    MANUAL = "manual"
    SKILL = "skill"


@dataclass(frozen=True, slots=True)
class OfficialSource:
    """One document, its fixed path, and how it is treated."""

    id: SourceId
    path: str
    authority: int
    media: str
    #: Whether the protocol verdict depends on this document. A required
    #: source that cannot be fetched or parsed makes the verdict
    #: ``unavailable`` and keeps the gate shut. A supplementary source is
    #: recorded and surfaced, but its failure does not by itself decide
    #: whether the live protocol matches ours - it carries no protocol
    #: contract to compare.
    required_for_verdict: bool
    #: Per-source ceiling on the decompressed body, in bytes.
    max_bytes: int
    #: Why this document is read at all.
    rationale: str

    @property
    def url(self) -> str:
        """The full, fixed URL. Built here and nowhere else."""
        return f"{TECHNOCORE_ORIGIN}{self.path}"


#: The complete set. Adding a path means editing this tuple, which is a
#: reviewable change; nothing computes a path at runtime.
SOURCES: tuple[OfficialSource, ...] = (
    OfficialSource(
        id=SourceId.AGENT_MANIFEST,
        path="/.well-known/agent.json",
        authority=1,
        media="application/json",
        required_for_verdict=True,
        max_bytes=256 * 1024,
        rationale=(
            "The machine-readable manifest registries read. Carries the "
            "signature payload shapes, the signature encoding, the nonce rule "
            "and the name pattern - the contract a signature must match."
        ),
    ),
    OfficialSource(
        id=SourceId.OPENAPI,
        path="/openapi.json",
        authority=1,
        media="application/json",
        required_for_verdict=True,
        max_bytes=2 * 1024 * 1024,
        rationale=(
            "The authoritative API description. Carries the signed lanes, "
            "their methods and paths, and the did/sig/nonce patterns and "
            "lengths the server actually enforces."
        ),
    ),
    OfficialSource(
        id=SourceId.CONFIG,
        path="/config",
        authority=1,
        media="application/json",
        required_for_verdict=False,
        max_bytes=256 * 1024,
        rationale=(
            "The effective deployment settings. Capacity and rate figures "
            "only; it carries no signature contract, so it informs warnings "
            "rather than the protocol verdict."
        ),
    ),
    OfficialSource(
        id=SourceId.HEALTH,
        path="/healthz",
        authority=1,
        media="text/plain",
        required_for_verdict=False,
        max_bytes=8 * 1024,
        rationale=(
            "Liveness. Reported honestly but deliberately not part of the "
            "verdict: this endpoint has been observed answering 503 "
            "intermittently, and an infrastructure hiccup on an endpoint that "
            "carries no protocol contract must not flap the write gate."
        ),
    ),
    OfficialSource(
        id=SourceId.MANUAL,
        path="/llms.txt",
        authority=2,
        media="text/plain",
        required_for_verdict=False,
        max_bytes=1024 * 1024,
        rationale=(
            "The prose manual. Snapshotted for evidence and change detection; "
            "prose drift is a warning, never a protocol verdict."
        ),
    ),
    OfficialSource(
        id=SourceId.SKILL,
        path="/skill.md",
        authority=2,
        media="text/plain",
        required_for_verdict=False,
        max_bytes=1024 * 1024,
        rationale=(
            "The agent skill document. Same treatment as the manual: evidence "
            "and warnings, not protocol truth."
        ),
    ),
)

_BY_ID: dict[SourceId, OfficialSource] = {source.id: source for source in SOURCES}


def get_source(source_id: SourceId) -> OfficialSource:
    """Look up a source. Raises ``KeyError`` for anything not registered."""
    return _BY_ID[source_id]


def required_sources() -> tuple[OfficialSource, ...]:
    """The sources whose failure makes the protocol verdict unavailable."""
    return tuple(source for source in SOURCES if source.required_for_verdict)


__all__ = [
    "SOURCES",
    "TECHNOCORE_HOST",
    "TECHNOCORE_ORIGIN",
    "TECHNOCORE_PORT",
    "TECHNOCORE_SCHEME",
    "OfficialSource",
    "SourceId",
    "get_source",
    "required_sources",
]
