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
    placeholder.

    Stage 4 opened the write path, and only in the narrow sense the field
    below names: a message is written when the user has separately approved
    its signature and its publication, with the whole gate re-checked at each
    step. Nothing is written automatically, and there is still no note lane.
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
    #: Distinguishes a value that is present and different from one that
    #: could not be read at all. A UI that shows both as "changed" would be
    #: claiming the server did something the evidence does not support.
    outcome: Literal["matched", "mismatch", "missing", "unsupported"]
    #: Why a change to this field matters, in plain language.
    rationale: str
    #: Set when ``outcome`` is ``unsupported``: what could not be read.
    detail: str = ""


class ComposeDraftRequest(StrictModel):
    """Step 1. Nothing is signed and no nonce is reserved by this call."""

    room: str = Field(max_length=48)
    #: Bounded here as a first line of defence only. The real limit is the
    #: effective one read from the live manifest and applied to the *swept*
    #: text; this cap exists so an absurd body is refused before it is swept
    #: character by character. Generous by design: the sweep can only make
    #: text shorter, so a raw cap below the swept limit would reject text the
    #: protocol would have accepted.
    text: str = Field(max_length=65536)


class ComposeDraftResponse(StrictModel):
    """What would be stored, and how it differs from what was typed.

    Both texts are returned so the UI can render the difference. Neither is
    a secret: this is the user's own message, on its way to a public room.
    """

    draft_id: str
    room: str
    #: Class markers on the room name, read from the live manifest.
    room_classes: list[str]
    raw_text: str
    swept_text: str
    changed_by_sweep: bool
    raw_chars: int
    swept_chars: int
    #: Bind step 2 to this exact content. Changing the text or the room
    #: changes the digest, and step 2 refuses a digest that does not match.
    draft_digest: str
    min_chars: int
    max_chars: int
    expires_in_seconds: int
    #: Things about this room the user should know before publishing.
    target_notes: list[str]


class ComposeSignRequest(StrictModel):
    """Step 2: the explicit signing approval.

    ``vault_passphrase`` is a ``SecretStr`` for the same reason it is on the
    recovery routes: an accidental repr, log line or traceback prints
    asterisks. It is present because a passphrase-protected vault cannot be
    opened without it (ADR-016: the passphrase is asked for at the moment the
    secret is used, not at launch), and it is never stored, echoed or logged.
    """

    draft_id: str
    #: Must equal the digest returned by step 1.
    draft_digest: str
    vault_passphrase: SecretStr | None = None


class ComposeSignResponse(StrictModel):
    """The exact bytes that were signed, and a single-use send approval.

    ``send_token`` is a capability: it is what turns "I have signed this"
    into "publish it". It is single-use, expires, and is bound to the
    canonical bytes, room, nonce, DID, session and manifest verdict.
    """

    draft_id: str
    room: str
    did: str
    nonce: str
    #: The canonical string, shown verbatim. This is what the signature
    #: covers - not the JSON body it travels in.
    canonical: str
    canonical_digest: str
    signature: str
    changed_by_sweep: bool
    send_token: str
    expires_in_seconds: int


class ComposeSendRequest(StrictModel):
    """Step 3: spend the approval. Carries nothing else on purpose."""

    send_token: str


class ComposeSendResponse(StrictModel):
    """The three-valued result of one write attempt.

    ``outcome`` is never reduced to a boolean. ``outcome_unknown`` means the
    server may have stored the message: presenting it as either sent or
    failed would be a claim the evidence does not support (ADR-0002 3).
    """

    outcome: Literal["accepted", "refused", "outcome_unknown"]
    room: str
    did: str
    nonce: str
    canonical_digest: str
    signature: str
    http_status: int
    detail: str
    #: A bounded, swept excerpt of the server's answer.
    response_excerpt: str
    #: True only for ``outcome_unknown``. Reconciliation needs a room read,
    #: which this release does not open, so the state is shown as it is.
    reconciliation_required: bool


class ComposeCapabilityResponse(StrictModel):
    """Whether composing is possible at all, and what it is bound by.

    A read. It reports the same gate the three composer steps re-run, so the
    UI can explain a closed door without a disabled button ever being the
    control that keeps it closed.
    """

    can_compose: bool
    blocking_reasons: list[str]
    #: The message lane, stated so the UI never has to assume it.
    write_method: Literal["POST"]
    write_path_template: str
    #: Rooms Station refuses outright.
    denied_rooms: list[str]
    #: Class markers the live manifest published on the last check.
    room_class_markers: list[str]
    max_chars: int
    min_chars: int
    draft_ttl_seconds: int
    approval_ttl_seconds: int
    #: The note lane is out of scope for this release, and why.
    note_lane_available: Literal[False] = False
    note_lane_detail: str


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
    #: Critical fields that are present and different: real drift.
    critical_mismatch_count: int
    #: Critical fields that could not be evaluated. The gate closes for these
    #: too, but the reason shown to the user is "could not verify", not a
    #: claim about what changed.
    critical_unevaluable_count: int
    warning_count: int
    origin: str
