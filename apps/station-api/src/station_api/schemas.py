"""Pydantic response models.

Every field that can ever leave this process is declared here. No model in
this module, or any module that follows it, may carry a field whose name
contains ``seed``, ``private``, ``secret`` or ``mnemonic`` (INV-01, SI-34).
The database path is likewise never returned (SI-36).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(StrictModel):
    """Public liveness probe. Deliberately carries no environment detail."""

    status: Literal["ok"] = "ok"
    service: Literal["station-api"] = "station-api"


class SessionBootstrapResponse(StrictModel):
    """Hands the SPA its per-session CSRF value.

    The client keeps this in memory only. It is never written to
    localStorage, sessionStorage or IndexedDB (SI-24).
    """

    csrf_token: str = Field(description="Send as the X-Station-CSRF header.")
    csrf_header: str = Field(description="Name of the header to send it in.")


class ServiceStatus(StrictModel):
    state: Literal["running"] = "running"
    stage: int = Field(description="Implemented roadmap stage.")
    mode: Literal["production", "development"]


class DatabaseStatus(StrictModel):
    state: Literal["ready", "unavailable"]
    journal_mode: str = Field(description="Expected to be wal.")
    foreign_keys: bool
    schema_revision: str


class SessionSecurityStatus(StrictModel):
    state: Literal["active"] = "active"
    cookie_http_only: bool
    cookie_same_site: Literal["strict"]
    # Loopback HTTP: the Secure flag is deliberately not set, because browsers
    # do not honour it consistently over plain HTTP. Reported so the UI can
    # state the real posture instead of implying a guarantee.
    cookie_secure: bool
    csrf_required: bool
    transport: Literal["loopback-http"] = "loopback-http"


class TechnocoreStatus(StrictModel):
    """The read-only connection state shown on the dashboard header.

    Stage 3 made this real. ``never_checked`` is where every launch
    starts: Station sends no request until the user asks for one, so
    "not yet checked" is the honest opening state rather than a
    placeholder. There is still no write path of any kind.
    """

    state: Literal["never_checked", "current", "drifted", "unavailable"]
    #: The stage that opens outbound *writes*. Reading is Stage 3;
    #: composing and sending is Stage 4.
    write_available_from_stage: int = 4
    detail: str


class AppStatusResponse(StrictModel):
    service: ServiceStatus
    database: DatabaseStatus
    session_security: SessionSecurityStatus
    technocore: TechnocoreStatus


# ---------------------------------------------------------------------------
# Identity and recovery (Stage 2)
#
# Response models are an explicit allow-list. Only public material appears
# here: DID, public key, fingerprint, label, status, protection mode and
# recovery timestamps. There is deliberately no seed, private key, mnemonic,
# passphrase or vault path anywhere in this section, and a security test walks
# every model in this module to prove it.
# ---------------------------------------------------------------------------

#: The user must type this exactly to create an identity.
CREATE_IDENTITY_CONFIRMATION = "KİMLİK OLUŞTUR"


class IdentityPublic(StrictModel):
    """Everything about an identity that is safe to show or copy."""

    did: str
    public_key: str = Field(description="Raw Ed25519 public key, lowercase hex.")
    fingerprint: str
    fingerprint_short: str
    label: str
    status: str
    protection: str | None
    created_at: datetime
    revoked_at: datetime | None


class RecoveryStatus(StrictModel):
    exported_at: datetime | None
    verified_at: datetime | None
    file_fingerprint: str | None = Field(
        default=None, description="SHA-256 of the exported .tcrec. Not a secret."
    )
    kdf: str | None
    kdf_time_cost: int | None
    kdf_memory_kib: int | None
    kdf_parallelism: int | None


class VaultCapabilityStatus(StrictModel):
    platform_supported: bool
    dpapi_available: bool
    aead_available: bool
    usable: bool
    detail: str


class GateCheckStatus(StrictModel):
    key: str
    state: Literal["passed", "blocked", "not_implemented"]
    detail: str
    #: Roadmap stage that delivers this requirement: "2", "2B", "3", ...
    #: A string because the roadmap has a "2B" stage.
    stage: str


class WriteGateResponse(StrictModel):
    """Why an external write may or may not proceed.

    ``allowed`` stays False while any check is ``not_implemented``: an
    unbuilt requirement is never counted as satisfied.
    """

    allowed: bool
    identity_ready: bool
    blocking_reasons: list[str]
    checks: list[GateCheckStatus]


class IdentityStatusResponse(StrictModel):
    state: Literal[
        "no_identity",
        "creating",
        "recovery_pending",
        "ready",
        "revoked",
        "capability_error",
    ]
    identity: IdentityPublic | None
    recovery: RecoveryStatus
    capability: VaultCapabilityStatus
    gate: WriteGateResponse
    default_protection: str
    min_passphrase_chars: int
    create_confirmation_text: str


class CreateIdentityRequest(StrictModel):
    """Request body for creating an identity.

    Passphrases use ``SecretStr`` so an accidental repr, log line or traceback
    prints ``**********`` instead of the value.
    """

    protection: Literal["dpapi", "dpapi+passphrase"]
    passphrase: SecretStr | None = None
    passphrase_confirm: SecretStr | None = None
    label: str = Field(default="", max_length=128)
    confirmation: str = Field(description="Must equal the create confirmation text.")
    accept_dpapi_only_risk: bool = Field(
        default=False,
        description="Required when choosing dpapi without a passphrase.",
    )


class ExportRecoveryRequest(StrictModel):
    recovery_passphrase: SecretStr
    recovery_passphrase_confirm: SecretStr
    vault_passphrase: SecretStr | None = None


class RevokeIdentityRequest(StrictModel):
    confirm_did: str


class RecoveryInspectResponse(StrictModel):
    """Public DID read from a recovery file, shown before adoption."""

    did: str
    fingerprint: str
    fingerprint_short: str


# ---------------------------------------------------------------------------
# Conformance (Stage 2B)
#
# Everything here is public metadata about *this build*: which contract areas
# were checked, how many vectors, and which pinned reference, Python and
# Unicode database produced the verdict. The vectors themselves - and the
# TEST-ONLY seeds inside them - are never serialised.
# ---------------------------------------------------------------------------


class ConformanceCheckStatus(StrictModel):
    """One area of the write contract, and how much evidence backs it."""

    name: str
    passed: bool
    vectors: int
    detail: str


class ConformanceStatusResponse(StrictModel):
    """The runtime self-test verdict.

    ``passed`` means this build reproduces the **pinned reference commit's**
    behaviour. It is deliberately not a claim that the live Technocore server
    still speaks that protocol; that is manifest drift, and it is a separate
    check that stays closed until Stage 3.
    """

    passed: bool
    checks: list[ConformanceCheckStatus]
    failures: list[str]
    capabilities: list[str]
    bundle_digest: str
    bundle_digest_short: str
    bundle_vectors: int
    upstream_commit: str
    upstream_commit_short: str
    package_version: str
    python_version: str
    unicode_version: str
    bundle_unicode_version: str
    unicode_version_matches: bool


# ---------------------------------------------------------------------------
# Read-only Technocore monitoring (Stage 3)
#
# Everything here is metadata about documents Station fetched from a public
# origin: which source, which fixed URL, the hash of the exact bytes, and
# which protocol fields matched. The raw bodies are **never** returned - they
# stay in the bounded database excerpt for human review. Remote strings are
# swept and truncated before they reach these models.
# ---------------------------------------------------------------------------


class OfficialSourceStatus(StrictModel):
    """One official document, as far as the UI is allowed to know."""

    source_id: str
    url: str
    authority: int
    outcome: Literal["ok", "fetch_error", "parse_error"]
    http_status: int
    content_type: str
    etag: str
    last_modified: str
    #: First 12 hex characters of the SHA-256 over the exact response bytes.
    short_hash: str
    byte_count: int
    detail: str
    rationale: str


class ProtocolFieldStatus(StrictModel):
    """One field of the critical protocol projection, and its verdict."""

    key: str
    label: str
    source_id: str
    json_path: str
    severity: Literal["critical", "warning"]
    expected: str
    observed: str
    matches: bool
    #: Why a change to this field matters, in plain language.
    rationale: str


class TechnocoreStatusResponse(StrictModel):
    """The read-only monitoring verdict.

    ``state`` is the honest four-way answer. ``never_checked`` is the state
    every launch starts in: Station contacts nobody until the user asks it
    to, and a check recorded in an earlier session never restores an open
    gate.
    """

    state: Literal["never_checked", "current", "drifted", "unavailable"]
    manifest_current: bool
    checked_at: datetime | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    reasons: list[str]
    sources: list[OfficialSourceStatus]
    fields: list[ProtocolFieldStatus]
    critical_mismatch_count: int
    warning_count: int
    origin: str
