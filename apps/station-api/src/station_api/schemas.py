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
    #: True only for ``outcome_unknown``. Package E opens the read this needs
    #: - a user-initiated evidence capture against the official export lane -
    #: and it means "a capture may be attempted", never "send it again"
    #: (ADR-0003 4).
    reconciliation_required: bool
    #: The nonce reservation this send spent. A public uuid that names a
    #: ledger row; it is not a capability and confers nothing.
    reservation_id: str = ""
    #: The archived evidence record, when one was written.
    evidence_id: str = ""
    #: Whether the archive was written. A send is reported the same way
    #: either way: the two facts are separate and stay separate.
    evidence_recorded: bool = False
    evidence_detail: str = ""


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


# --- evidence and audit (Package E) -----------------------------------------


class EvidenceLevelStatus(StrictModel):
    """One of the four trust levels, and whether this record carries it.

    Reported per level rather than summed, because summing them is the exact
    mistake the model exists to prevent: a signature proof is not a server
    observation, and neither is a trusted time (charter 15).
    """

    level: Literal[1, 2, 3, 4]
    name: str
    present: bool
    detail: str


class EvidenceRecordResponse(StrictModel):
    """One archived send.

    Raw request and response bytes are deliberately **absent** from this
    model. They are stored and they are exported on explicit consent; a list
    endpoint that returned them would put them in every page load, which is a
    different decision wearing the same words. Hashes are returned instead.
    """

    id: str
    reservation_id: str
    room: str
    did: str
    nonce: str
    canonical_sha256: str
    signature: str
    http_status: int
    #: The three-valued send result, unchanged (ADR-0002 3).
    write_outcome: Literal[
        "in_flight", "accepted", "refused", "outcome_unknown", "not_sent"
    ]
    #: One of the six capture states, or "" before any capture was attempted.
    capture_state: Literal[
        "",
        "line_captured",
        "line_not_found",
        "generation_changed",
        "stream_truncated",
        "parse_problem",
        "fetch_failed",
    ]
    capture_detail: str
    captured_at: datetime | None
    #: The epoch this record was first seen under. The baseline, never
    #: overwritten - overwriting it made ``generation_changed`` a one-off.
    room_generation: str
    #: The epoch the stored line was read under, so a line and a generation
    #: are never reported side by side while belonging to different rooms.
    capture_generation: str
    #: Sticky: the room has been seen under more than one epoch, so the two
    #: sides are not comparable however the latest read turned out.
    generation_changed: bool
    captured_line_offset: int | None
    captured_line_length: int | None
    stream_sha256: str
    stream_bytes: int
    stream_truncated: bool
    unreadable_lines: int
    request_sha256: str
    response_sha256: str
    recorded_at: datetime
    #: Level 4. Always ``null`` in this release, and present in the payload so
    #: "absent" is stated rather than inferred from a missing key.
    external_anchor: str | None = None
    levels: list[EvidenceLevelStatus]


class EvidenceListResponse(StrictModel):
    """The archive, newest first, bounded."""

    records: list[EvidenceRecordResponse]
    record_count: int
    #: The audit chain's verdict, so a reader never sees records without it.
    chain_state: Literal[
        "intact", "empty", "broken_link", "head_mismatch", "unavailable"
    ]
    chain_detail: str
    chain_link_count: int


class EvidenceCaptureRequest(StrictModel):
    """Ask for one read-only capture of one record's export line."""

    evidence_id: str = Field(min_length=1, max_length=64)


class EvidenceCaptureResponse(StrictModel):
    """The result of one capture attempt.

    ``state`` is one of six and is never reduced to a boolean. Five of the
    six establish nothing about whether the message was published, and
    ``line_not_found`` in particular never converts an ``outcome_unknown``
    send into ``not_sent`` (ADR-0003 3).
    """

    evidence_id: str
    state: Literal[
        "line_captured",
        "line_not_found",
        "generation_changed",
        "stream_truncated",
        "parse_problem",
        "fetch_failed",
    ]
    detail: str
    #: True only for ``line_captured``, and it means level 2 - no more.
    server_observation: bool
    #: The epoch **this read** published, or "" when it published none. Not
    #: the record's baseline: the stored baseline is set once and answers a
    #: different question ("what epoch was this record first seen under"),
    #: and it is returned by ``/records`` as ``room_generation`` beside
    #: ``capture_generation`` and ``generation_changed``.
    room_generation: str
    line_offset: int | None
    line_length: int | None
    stream_sha256: str
    scanned_bytes: int
    stream_truncated: bool
    #: A read may be retried. A write may not, ever, under any state.
    read_retry_allowed: Literal[True] = True
    write_retry_allowed: Literal[False] = False


class EvidenceExportRequest(StrictModel):
    """The explicit consent an export requires.

    ``acknowledged`` has no default. A body that omits it is a 422 before any
    handler runs, which is the cheapest possible place for "no export without
    consent" to be enforced (charter 15.6).
    """

    format: Literal["json", "markdown"]
    acknowledged: bool


class AuditChainResponse(StrictModel):
    """What verifying the audit chain established.

    The wording is fixed: the chain is *detective against offline change*. It
    is not tamper-proof, it carries no trusted time, and it proves nothing to
    a third party - an attacker running as this Windows user can recompute
    both the chain and its head (ADR-0003 5).
    """

    state: Literal["intact", "empty", "broken_link", "head_mismatch", "unavailable"]
    detail: str
    link_count: int
    head_count: int | None
    first_bad_seq: int | None
    #: The only permitted description of what this mechanism provides.
    claim: str


# --- project modules and tasks (Package F) ----------------------------------
#
# These models live here rather than in ``station_api/tasks/`` on purpose
# (ADR-0004 8). All three tests in ``tests/security/test_no_secret_fields.py``
# walk ``vars(schemas)``; a task model declared in a new module would leave
# that protection silently out of scope - not a leak, but a lost control, and
# exactly the kind of quiet regression this project exists to catch. Widening
# the tests is acceptable, narrowing them is not (INV-06).
#
# Nothing here carries a seed, a private key, a passphrase or a vault path. A
# module id, a source id, a content digest, a state name and a Turkish
# sentence are all public values.


#: The three-valued check state, spelled the same way the write gate spells it.
TaskCheckState = Literal["passed", "blocked", "not_implemented"]

#: The four fields a result is recorded in. Never collapsed into one boolean.
TaskEvidenceFieldName = Literal[
    "task_outcome", "test_result", "user_acceptance", "public_share"
]

#: All nine states. Six are producible in this release; the other three are
#: defined, listed, and refused by ``validate_transition`` (ADR-0004 3).
TaskStateName = Literal[
    "suggested",
    "awaiting_approval",
    "running",
    "paused",
    "blocked",
    "failed",
    "review_needed",
    "ready_to_publish",
    "published",
]


class ModuleCheckStatus(StrictModel):
    """One module requirement and its verdict.

    ``not_implemented`` is a distinct value for the same reason it is on the
    write gate: an unbuilt requirement is never counted as passed, and a
    product gap is never shown as a user error.
    """

    key: str
    state: TaskCheckState
    detail: str
    #: Which of the four fields carries the evidence for this requirement.
    evidence_field: TaskEvidenceFieldName
    #: The package or roadmap stage that delivers the evidence.
    stage: str
    #: The evidence consulted, or "" when none was.
    ref_id: str = ""
    #: True when the requirement is refused by policy rather than unbuilt -
    #: "nobody has written it yet" and "this product will not do it" read
    #: identically in a status column, and only one of them is a queue item.
    policy_refused: bool = False


class ProjectModuleStatus(StrictModel):
    """One record from the compile-time registry.

    ``planned`` modules are registered so the target layout stays reviewable
    and are never rendered as features - the ``sections.ts`` rule, applied to
    the backend registry.
    """

    id: str
    name: str
    purpose: str
    state: Literal["available", "planned"]
    #: The package that opens a planned module; "" for available ones.
    available_from: str
    #: Dotted paths of the code that already owns this responsibility. Nothing
    #: was moved: the registry points, the code stays (ADR-0004 1).
    owners: list[str]
    checks: list[ModuleCheckStatus]
    #: Derived from the checks, never stored. False while any check is
    #: ``not_implemented``.
    complete: bool
    blocking_keys: list[str]
    not_implemented_keys: list[str]


class TaskFieldStatus(StrictModel):
    """One of the four fields, reported on its own.

    Reported per field rather than summed, because summing them is the exact
    mistake the model exists to prevent: a produced output is not a passed
    test, and neither is a person's acceptance (ADR-0004 4).
    """

    evidence_field: TaskEvidenceFieldName
    state: TaskCheckState
    detail: str
    ref_id: str = ""


class TaskStatusResponse(StrictModel):
    """One task, its state, and the four fields kept apart."""

    id: str
    module_id: str
    source_id: str
    #: SHA-256 over the content this task was opened for.
    content_sha256: str
    #: The domain-separated binding of source and content. Changing the
    #: content changes this, and evidence bound to the old value stops
    #: matching (ADR-0004 5).
    source_version_id: str
    title: str
    state: TaskStateName
    state_detail: str
    created_at: datetime
    updated_at: datetime
    evidence_fields: list[TaskFieldStatus]
    #: Derived from three separately verified fields. Never asked for.
    ready_to_publish: bool
    blocking_fields: list[str]
    #: External sharing is Package H3's subject and asks for its own
    #: single-use consent there. This release opens the field and never fills
    #: it, and says so rather than leaving it to be inferred.
    public_share_available: Literal[False] = False
    public_share_detail: str
    #: There is no budget in this release and no field that behaves like one.
    #: The requirement's budget half is deferred to G/H2 and is recorded
    #: visibly rather than dropped quietly (ADR-0004 7).
    budget_available: Literal[False] = False
    budget_detail: str


class TaskListResponse(StrictModel):
    """The tasks, newest first, bounded - and the honest state inventory."""

    tasks: list[TaskStatusResponse]
    task_count: int
    #: The states this release can genuinely reach.
    producible_states: list[TaskStateName]
    #: Defined, listed in the transition table, and unreachable. Named so a
    #: reader is never left to discover it by trying.
    unproducible_states: list[TaskStateName]
    unproducible_detail: str


class UnfinishedWriteStatus(StrictModel):
    """One send that was committed to and never settled.

    Public protocol values only: a ledger id, a DID, a room, a nonce and the
    time it was reserved. No canonical text, no signature, no response body.
    """

    reservation_id: str
    did: str
    room: str
    nonce: str
    reserved_at: datetime | None


class TaskReconciliationResponse(StrictModel):
    """What the read-only startup scan found.

    ``resumed_any`` is a ``Literal[False]``: this scan reads. It sends no
    request, changes no row and continues no send, and the shape of the model
    is where that is stated rather than only the prose (ADR-0004 6).
    """

    scanned_at: datetime
    unfinished_count: int
    entries: list[UnfinishedWriteStatus]
    resumed_any: Literal[False] = False
    detail: str


# --- the OpenCode Go connection (Package G) ---------------------------------
#
# Response models here are an explicit allow-list, and the allow-list has a
# hole in it on purpose: **there is no field carrying the provider key, and no
# endpoint that returns or copies it.** A stored credential is described by a
# twelve-character fingerprint prefix, two timestamps and a boolean, which is
# everything a person needs to recognise which key is installed and nothing
# anyone needs to use it.
#
# The models also refuse to flatten three things into one:
#
# * a connection verdict is a state **plus every reason it is not stronger**,
#   never a single boolean badge (ADR-0005 4);
# * a listed model is not a callable model, so ``selectable`` and the reason
#   it is false travel together (ADR-0005 5);
# * a spending context is published limits and where the controls live, never
#   a figure Station computed (ADR-0005 9).


class OpenCodeConnectionCheckStatus(StrictModel):
    """What can honestly be said about the stored credential.

    Note the absent value: ``state`` has no ``verified``. The catalog answers
    without a key, a GET on a protocol path answers 404, and a real metered
    call is not made automatically - so nothing in this build can produce a
    verified verdict, and a field that could hold one would be an invitation
    to write it from somewhere that had not earned it.
    """

    state: Literal["not_configured", "never_checked", "key_saved_unverified"]
    #: Plural on purpose. One reason reads like a problem to fix; the list is
    #: the actual epistemic position.
    reasons: list[str]
    detail: str


class OpenCodeStrictModel(StrictModel):
    """``StrictModel`` with room for a field genuinely called ``model_id``.

    Pydantic reserves the ``model_`` prefix for its own API and warns when a
    field takes it. Renaming the field to dodge the warning would have made
    the API speak differently from the provider it describes - the catalog's
    own key is ``id`` and everything about this feature is a *model* id - so
    the namespace is released here, narrowly, instead of on every model in
    this module.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class OpenCodeModelStatus(OpenCodeStrictModel):
    """One catalog row, joined to what this build knows about it."""

    model_id: str = Field(
        description="The wire identifier: bare, never carrying the provider prefix."
    )
    owned_by: str
    #: False whenever the protocol family was not published. Listing is not
    #: entitlement and is not addressability.
    selectable: bool
    #: Empty when there is no table entry. An absent protocol is not a
    #: default protocol.
    protocol: str
    protocol_verification: Literal["documented", "unverified"]
    #: Why it cannot be selected, in the user's language. Empty when it can.
    reason: str
    #: The provider's published retention term, or ``unknown``. Never
    #: rewritten into a reassurance.
    retention: str
    training_use: Literal["yes", "no", "unknown"]
    #: ``unknown`` asks for acknowledgement exactly as ``yes`` does.
    requires_training_acknowledgement: bool
    privacy_source: str
    privacy_read_on: str


class OpenCodeCatalogStatus(OpenCodeStrictModel):
    """The cached public catalog, its age, and any error reaching it.

    The file path the cache lives behind is deliberately absent (SI-36), as
    is the raw document: what is returned is the list and the metadata about
    the read.
    """

    state: Literal["never_fetched", "ok", "fetch_error", "parse_error"]
    #: The last **attempt**. A failed refresh moves this and nothing else.
    fetched_at: datetime | None
    #: When the listed models were actually read. Separate on purpose: a
    #: failed refresh must neither delete the cache nor lend it a date the
    #: cache did not earn.
    models_fetched_at: datetime | None
    detail: str
    http_status: int
    models: list[OpenCodeModelStatus]
    model_count: int
    selectable_count: int
    listing_caveat: str


class OpenCodePublishedLimit(StrictModel):
    """One usage limit exactly as the provider published it."""

    window: str
    amount_usd: int
    note: str


class OpenCodeSpendingContext(StrictModel):
    """Read-only spending context. No budget opens here.

    ``budget_available`` is a ``Literal[False]`` for the same reason
    ``TaskReconciliationResponse.resumed_any`` is: the shape of the model is
    where the decision is stated, so it cannot drift out of the prose
    (ADR-0005 9).
    """

    budget_available: Literal[False] = False
    limits: list[OpenCodePublishedLimit]
    limit_behaviour: str
    use_balance: str = Field(
        description="Where the preference lives. Station does not change it."
    )
    local_counter_caveat: str
    unknown_cost_sentence: str


class OpenCodeProtocolContext(StrictModel):
    """The three families, and the two formats deliberately not built."""

    protocols: list[str]
    streaming_supported: Literal[False] = False
    tool_calls_supported: Literal[False] = False
    deferral: str
    shape_provenance: str


class OpenCodeStatusResponse(StrictModel):
    """The whole connection, read-only. Sends nothing."""

    configured: bool
    #: Twelve characters of an HMAC over a fixed public label. It names which
    #: credential is installed without revealing any part of it.
    fingerprint_short: str
    configured_at: datetime | None
    updated_at: datetime | None
    check: OpenCodeConnectionCheckStatus
    selected_model: str
    #: The header assumption, restated to the user rather than buried in a
    #: source comment (ADR-0005 3).
    auth_header_caveat: str
    catalog: OpenCodeCatalogStatus
    spending: OpenCodeSpendingContext
    protocol_context: OpenCodeProtocolContext


class OpenCodeCredentialRequest(StrictModel):
    """The one place a provider key enters this process.

    ``SecretStr`` for the reason every passphrase input uses it: it prints
    ``**********`` in a repr, a log line or a traceback, so an accidental
    exception never spills the value. There is no matching response field -
    the key goes in and is never handed back.
    """

    api_key: SecretStr = Field(
        description="Saglayici anahtari. Kaydedilir, hicbir yanitta geri dondurulmez."
    )


class OpenCodeSelectModelRequest(OpenCodeStrictModel):
    """Choose a model. Refused, with a reason, when it cannot be addressed."""

    model_id: str
    #: Fail-closed. A model whose retention term is ``yes`` **or**
    #: ``unknown`` needs this, and the default is the safe answer.
    training_acknowledged: bool = False
