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

#: All nine states. Under Package F six were producible; H1 opened
#: ``suggested`` when it built a suggester, and H2 opened ``running`` and
#: ``paused`` when it built the deterministic tool runner (ADR-0008 3). All
#: nine are reachable now, which is why ``unproducible_states`` on
#: ``TaskListResponse`` is an empty list rather than a removed field: a reader
#: who saw three names there last release is told the set is now empty rather
#: than left to notice the field went away.
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

#: The transitions a **person** may ask for over HTTP.
#:
#: ``running`` and ``paused`` are deliberately absent. They are the runner's,
#: and they are reached through the run routes - which record a plan, its
#: promised artifacts and its success criterion first. A route that let a
#: person put a task straight into ``running`` would be a way into the
#: executing state with no plan written down, which is the property ADR-0008 7
#: exists to protect. ``ready_to_publish`` is absent for the older reason: it
#: is derived from evidence and cannot be asked for (SI-222).
TaskUserTransitionName = Literal[
    "awaiting_approval",
    "blocked",
    "failed",
    "review_needed",
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
    #: Whether the fourth field can be filled at all.
    #:
    #: A plain ``bool`` since Package H3, and it was ``Literal[False]`` before
    #: that for a reason that has stopped being true rather than for a reason
    #: that was dropped: the field is fillable now, from an archived send and
    #: from nothing else (ADR-0009 1). The value is **derived** from
    #: ``UNFILLABLE_FIELDS`` in ``tasks/views.py`` rather than written out
    #: here, so it cannot disagree with the constant that decides it.
    #:
    #: Fillable is not the same as required: ``public_share`` is still absent
    #: from ``PUBLICATION_FIELDS``, so a task can be finished without ever
    #: being published (ADR-0004 4, ADR-0009 1).
    public_share_available: bool
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
    #: How many listed models the pinned protocol table has no row for.
    unmapped_count: int
    listing_caveat: str
    #: When the pinned protocol table was read, and what the source page's
    #: own footer said that day. Always present: the age of a transcription
    #: is a fact about every reading of it, not an exception to report.
    table_provenance: str
    #: Empty while the catalog and the pinned table agree. Non-empty once the
    #: provider lists more unmapped models than the transcription accounted
    #: for - the drift signal that was missing when the table went stale and
    #: nothing said so.
    drift_notice: str


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


# ---------------------------------------------------------------------------
# Package H1 - the public-room work scan
#
# Nothing here carries a wallet, a claim, a score or a rank. Nothing here
# carries a boolean saying a work item is open: element 8 is a sentence with a
# timestamp in it, and a field named ``is_open`` would be read as an answer
# this surface cannot produce (ADR-0007 8).
# ---------------------------------------------------------------------------


class WorkScanQuote(StrictModel):
    """Element 1: the verbatim line and where it came from.

    ``authority`` is 3 on every one of these and is sent rather than implied:
    the endpoint is official, the content is anonymous input from strangers,
    and a client that only saw the endpoint would draw the wrong conclusion.
    """

    room: str
    seq: int
    ts: str
    author: str
    author_is_did_key: bool
    author_detail: str
    quote: str
    reference: str
    authority: Literal[3] = 3


class WorkScanCapability(StrictModel):
    """Element 5: whether this build has the tools and the data."""

    module_id: str
    module_state: str
    module_available: bool
    write_gate_open: bool
    ready: bool
    detail: str


class WorkScanEffort(StrictModel):
    """Element 6: an estimate that says so in the payload, not in a tooltip."""

    label: Literal["tahmin"] = "tahmin"
    band: str
    basis: str


class WorkScanOpenState(StrictModel):
    """Element 8. A sentence and a reading time; deliberately not a boolean."""

    read_at: datetime
    detail: str


class WorkScanCandidate(StrictModel):
    """One proposal, with all eight elements present."""

    id: str
    signal: str
    source: WorkScanQuote
    benefit: str
    deliverable: str
    success_condition: str
    test_method: str
    capability: WorkScanCapability
    effort: WorkScanEffort
    #: Always ``not_implemented``. There is no budget in this release, and a
    #: missing budget never reads as an approved one.
    budget_state: Literal["not_implemented"] = "not_implemented"
    budget_detail: str
    permissions: list[str]
    risks: list[str]
    open_state: WorkScanOpenState
    derivation: str


class WorkScanRefusal(StrictModel):
    """A line this build declined to propose work from, and why."""

    room: str
    seq: int
    shape: str
    detail: str


class WorkScanRoomFailure(StrictModel):
    """A room that could not be read. Never folded into "found nothing"."""

    room: str
    reason: str
    detail: str


class WorkScanRoomResult(StrictModel):
    """One room's outcome, including how many lines were actually read."""

    room: str
    candidates: list[WorkScanCandidate]
    refusals: list[WorkScanRefusal]
    lines_read: int


class WorkScanStaleness(StrictModel):
    """The reading time and the service's own declared cache bound.

    No ``is_stale`` field. This build invents no threshold, so it publishes no
    verdict (ADR-0007 5).
    """

    read_at: datetime
    declared_cache_seconds: int
    declared_by: str
    detail: str


class WorkScanRingDrop(StrictModel):
    """The service's own machine-readable signal that history was dropped."""

    since: int
    expected_first: int
    first_seq: int
    detail: str


class WorkScanRoom(StrictModel):
    """One room as the overview listed it. Both fields are caller-written."""

    name: str
    topic: str
    authority: Literal[3] = 3


class WorkScanRoomIndex(StrictModel):
    """The room overview as read once, at one moment."""

    rooms: list[WorkScanRoom]
    total: int
    kept_count: int
    truncated: bool
    staleness: WorkScanStaleness
    sha256: str
    room_name_caveat: str
    topic_caveat: str


class WorkScanAdapterFact(StrictModel):
    """One thing about an external service, and whether anybody confirmed it."""

    key: str
    detail: str
    state: Literal["verified", "not_verified"]


class WorkScanAdapter(StrictModel):
    """An external service record. Never a client, and never contacted."""

    id: str
    name: str
    support: str
    authority: Literal[3] = 3
    declared_origin: str
    #: ``Literal[False]`` is the wire half of SI-281 and it stays: nothing can
    #: serialise another value here. The route no longer leaves it to this
    #: default, though - it reads the record's derived property and refuses a
    #: true one - because a default the producer never passes makes an
    #: assertion about this field a restatement of this line.
    adapter_written: Literal[False] = False
    contacted: Literal[False] = False
    verified: list[WorkScanAdapterFact]
    unverified: list[WorkScanAdapterFact]
    #: The Turkish rendering of the service's own words.
    self_description: str
    #: The service's own two sentences, in the language it wrote them in.
    #: Carried on the wire so that "the service's own words are quoted
    #: verbatim" is a property of the response rather than of a frontend
    #: constant transcribed by hand from an ADR.
    self_description_source: str
    score_self_description: str
    score_caveat: str
    provenance: str


class WorkScanResult(StrictModel):
    """One scan of one user-chosen room set."""

    started_at: datetime
    completed_at: datetime
    rooms: list[str]
    results: list[WorkScanRoomResult]
    failures: list[WorkScanRoomFailure]
    candidate_count: int
    refusal_count: int


class WorkScanStatusResponse(StrictModel):
    """The whole scan surface, read-only. Sends nothing."""

    #: Shown on every read, not only beside a result (ADR-0007 2).
    honesty: str
    capability: WorkScanCapability
    adapters: list[WorkScanAdapter]
    room_index: WorkScanRoomIndex | None
    last_scan: WorkScanResult | None
    #: The parameters this package refuses to send, named in the payload so
    #: the absence of polling is checkable from outside the process.
    never_sent_params: list[str]
    polling_statement: str
    #: The refusal half of the same honesty: the six prohibited work shapes
    #: are matched by pattern, not recognised by meaning. Shown beside the
    #: derivation sentence rather than left in a design document.
    prohibition_statement: str


class WorkScanRefreshRequest(StrictModel):
    """Read the room overview. Carries a count and nothing addressable."""

    limit: int = Field(default=50, ge=1, le=200)


class WorkScanScanRequest(StrictModel):
    """Scan the rooms the user chose. The scope is this list and nothing else."""

    rooms: list[str] = Field(min_length=1, max_length=10)
    limit: int = Field(default=50, ge=1, le=200)


class WorkScanSuggestRequest(StrictModel):
    """Turn one candidate from the last scan into a local suggested task."""

    candidate_id: str


class WorkScanSuggestResponse(StrictModel):
    """The task that was opened. Born ``suggested``; approved by nobody."""

    task_id: str
    module_id: str
    source_id: str
    source_version_id: str
    state: Literal["suggested"] = "suggested"
    detail: str


# --- the agent runtime and the Activity Desk (Package H2) -------------------
#
# Declared here rather than in ``station_api/agent/`` for the reason the task
# models are (ADR-0004 8, ADR-0008 9): all three tests in
# ``tests/security/test_no_secret_fields.py`` walk ``vars(schemas)``, and a
# response model declared in a new module would leave that protection silently
# out of scope. Not a leak - a lost control, which is worse because it looks
# like nothing.
#
# Four things these models refuse to flatten:
#
# * an **ending** is not "failed". Running out of the ceiling, a tool
#   refusing, the user stopping the run and a promised artifact never being
#   produced are four phases with four sentences (ADR-0008 7);
# * a **test result** is not a boolean the runner supplies. It is
#   ``not_implemented`` and stays that way while execution is closed, which is
#   why a finished run leaves a task in ``review_needed`` and not in
#   ``ready_to_publish``;
# * a **measured facility** is not a relied-upon one. Docker is reported as
#   present *and* ``relied_upon: false`` rather than omitted (ADR-0008 1);
# * an **activity row** is not an audit link. ``chain_referenced`` says which
#   rows the chain refers to, and those are the rows nothing may prune.
#
# There is no field here for a model's reasoning or a provider payload, and
# no field carrying a filesystem path: a workspace file is named, never
# located.


#: Where a run is. The four endings are distinct values, on purpose.
AgentRunPhaseName = Literal[
    "planned",
    "running",
    "paused",
    "completed",
    "cancelled",
    "tool_error",
    "budget_exhausted",
    "artifact_missing",
]

#: What became of one planned step.
AgentStepPhaseName = Literal["planned", "ran", "refused", "failed", "skipped"]

#: The permission a tool needs. None of them leaves this machine.
AgentToolScopeName = Literal[
    "read_approved_input",
    "write_workspace",
    "deterministic_check",
    "read_run_state",
]

#: The parameter types the tool registry declares. There is deliberately no
#: ``path`` and no ``url``: a tool cannot be handed an address.
AgentToolParamTypeName = Literal["text", "file_name", "digest"]

#: What the measurement established. ``not_measured`` is not ``absent``.
AgentIsolationStateName = Literal["present", "absent", "not_measured"]

#: Who acted. There is no ``model`` actor, because there is no model lane.
ActivityActorName = Literal["user", "station_runner"]

ActivityOutcomeName = Literal["ok", "refused", "failed", "pending"]

ActivityActionName = Literal[
    "run_planned",
    "run_started",
    "tool_called",
    "artifact_produced",
    "check_recorded",
    "approval_awaited",
    "run_stopped",
    "run_resumed",
    "run_finished",
    "run_failed",
    "permission_denied",
    "budget_exhausted",
    "execution_unavailable",
    "activity_deleted",
]


class AgentToolParamStatus(StrictModel):
    """One typed parameter of one tool."""

    name: str
    type: AgentToolParamTypeName
    required: bool
    detail: str


class AgentToolStatus(StrictModel):
    """One registered tool, with everything a person needs to approve it."""

    id: str
    scope: AgentToolScopeName
    purpose: str
    params: list[AgentToolParamStatus]
    #: What one call spends against the ceiling. One, for every tool.
    call_cost: int
    produces_artifact: bool


class AgentCeilingStatus(StrictModel):
    """The run ceiling, in the only three units this build can measure."""

    max_tool_calls: int
    max_wall_clock_seconds: int
    max_concurrency: Literal[1] = 1
    units: list[str]
    #: Units this product refuses to denominate a ceiling in, and why. Stated
    #: rather than left out, so "there is no token budget" is a claim on the
    #: wire instead of an absence a reader has to notice (ADR-0008 4).
    refused_units: list[str]
    refused_units_detail: str
    detail: str
    #: The ceiling is a compile-time constant and no code path writes it.
    #: A ``Literal[False]`` rather than prose, so the wire value is structural.
    agent_can_raise_ceiling: Literal[False] = False


class AgentIsolationFindingStatus(StrictModel):
    """One measured facility, and - separately - whether it is relied upon."""

    facility: str
    measured: AgentIsolationStateName
    measured_at: str
    detail: str
    #: Always false. Docker being installed on the developer's machine is not
    #: a guarantee the product may offer (ADR-0008 1).
    relied_upon: Literal[False] = False


class AgentExecutionStatus(StrictModel):
    """Why arbitrary code and shell execution are closed, as a reason."""

    #: Structural: there is no code path that runs a command.
    arbitrary_execution_supported: Literal[False] = False
    reason: Literal["execution_unavailable"] = "execution_unavailable"
    detail: str
    inventory: list[AgentIsolationFindingStatus]


class AgentRunStepStatus(StrictModel):
    """One planned tool call and what became of it.

    ``arguments_sha256`` rather than the arguments: the digest is what a
    later reader needs to know the step was not edited, and the text is
    already the user's own.
    """

    ordinal: int
    tool_id: str
    scope: AgentToolScopeName
    arguments_sha256: str
    phase: AgentStepPhaseName
    started_at: datetime | None
    finished_at: datetime | None
    #: The name of the file this step produced, never its path.
    artifact_name: str = ""
    artifact_sha256: str = ""
    detail: str = ""


class AgentWorkspaceFileStatus(StrictModel):
    """One workspace file: its name, its size and its digest. No path."""

    name: str
    byte_count: int
    sha256: str


class AgentRunStatus(StrictModel):
    """One run, with its plan, its usage and its ending kept apart."""

    id: str
    task_id: str
    phase: AgentRunPhaseName
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    stop_requested: bool
    #: Digest over the frozen plan: steps, expected artifacts, test condition.
    #: A start whose recomputed digest differs is refused (ADR-0008 7).
    plan_sha256: str
    #: The check the plan says would establish success. Recorded, never run.
    test_condition: str
    #: Always ``not_implemented`` in this release, and it is a field rather
    #: than an omission: a run that produced files has still not been tested,
    #: and the task cannot become ``ready_to_publish`` (SI-222).
    test_result_state: Literal["not_implemented"] = "not_implemented"
    test_result_detail: str
    expected_artifacts: list[str]
    steps: list[AgentRunStepStatus]
    tool_calls_used: int
    elapsed_ms: int
    max_tool_calls: int
    max_wall_clock_seconds: int
    concurrency: Literal[1] = 1
    detail: str


class AgentSurfaceResponse(StrictModel):
    """The whole agent surface, read-only. Contacts nobody and runs nothing."""

    execution: AgentExecutionStatus
    ceiling: AgentCeilingStatus
    tools: list[AgentToolStatus]
    honesty: str
    stop_statement: str
    #: Runs a restart left in ``running``. Listed, never resumed: continuing
    #: is a person's decision and there is no startup hook that makes it
    #: (SI-224, ADR-0008 10).
    interrupted_runs: list[AgentRunStatus]
    resumed_any: Literal[False] = False


class AgentTaskRunsResponse(StrictModel):
    """One task's runs and the files its workspace currently holds."""

    task: TaskStatusResponse
    runs: list[AgentRunStatus]
    workspace_files: list[AgentWorkspaceFileStatus]
    honesty: str


class AgentPlanStepRequest(StrictModel):
    """One step of a plan: a registered tool id and its arguments."""

    tool_id: str
    #: Validated against the tool's declared parameters before the plan is
    #: recorded, so an unregistered tool or a bad argument is refused while
    #: planning rather than half-way through a run.
    arguments: dict[str, str] = Field(default_factory=dict)


class AgentPlanRequest(StrictModel):
    """Record a plan for one task. Nothing runs until a separate request."""

    steps: list[AgentPlanStepRequest] = Field(min_length=1, max_length=32)
    #: The file names the plan promises to produce. A promise that is not
    #: kept ends the run in ``artifact_missing``.
    expected_artifacts: list[str] = Field(default_factory=list, max_length=16)
    #: How success would be established. Recorded, never run in this release.
    test_condition: str = Field(min_length=1, max_length=500)


class TaskTransitionRequest(StrictModel):
    """A user-driven state change.

    ``running`` and ``paused`` are deliberately **absent** from
    :data:`TaskUserTransitionName`. They belong to the runner and are reached
    through the run routes, which record a plan first; a route that let a
    person put a task into ``running`` directly would be a way to reach the
    executing state without a plan ever being written down.
    """

    target: TaskUserTransitionName
    detail: str = Field(default="", max_length=200)


class ActivityEventStatus(StrictModel):
    """One timeline row.

    No reasoning trace, no prompt, no completion and no raw provider payload:
    the model lane is closed, and the table this comes from has nowhere to
    put such a thing (ADR-0008 6).
    """

    id: str
    recorded_at: datetime
    run_id: str
    task_id: str
    actor: ActivityActorName
    action: ActivityActionName
    outcome: ActivityOutcomeName
    duration_ms: int
    artifact_sha256: str
    check_sha256: str
    detail: str
    #: True when an audit link names this row. Those rows are never pruned
    #: and never deleted, which is what lets the timeline have a retention
    #: policy while the chain keeps not having one.
    chain_referenced: bool


class ActivityListResponse(StrictModel):
    """The timeline, newest first, bounded."""

    events: list[ActivityEventStatus]
    event_count: int
    chain_referenced_count: int
    retained_events: int
    detail: str


class ActivityDeleteRequest(StrictModel):
    """Remove timeline rows. Chain-referenced rows are kept regardless."""

    #: Empty means "every row". A run id narrows it to one run.
    run_id: str = Field(default="", max_length=32)


class ActivityDeleteResponse(StrictModel):
    """What the deletion did, as two counts that are never summed."""

    deleted: int
    kept_because_chain_referenced: int
    #: The deletion is itself an audit event (ADR-0008 6). Stated on the wire
    #: so a user is told their removal was recorded rather than discovering it.
    recorded_in_audit_chain: Literal[True] = True
    detail: str


# --- the proof workspace (Package H3) ---------------------------------------
#
# ADR-0009 11 asks that the models declared here **stay here**. Three tests in
# ``test_no_secret_fields.py`` walk ``vars(schemas)`` and nothing else, so a
# response model declared in a package module would be exempt from the
# secret-field rule, the extra-forbid rule and the passphrase rule at once -
# silently, and only for the newest code.
#
# The models refuse to flatten three things:
#
# * a hash is not a verdict. ``artifact_set_sha256`` travels beside
#   ``hash_scope`` - the sentence that says what a digest does and does not
#   establish - because a digest shown alone reads as an endorsement;
# * what is missing is a **list of named items**, never a count and never a
#   percentage. Four different gaps have four different remedies;
# * a claim this build cannot produce carries its own state and its own
#   reason, rather than being omitted and left to be inferred.


#: The two formats a bundle is produced in. A closed set.
ProofBundleFormatName = Literal["json", "markdown"]

#: The only state the two unproduced claims can be in. Written as a
#: single-value literal rather than as the wider check-state union: a route
#: that started reporting ``passed`` here would be a type error at build time,
#: which is the point of ADR-0009 6 and 7.
ProofClaimStateName = Literal["not_implemented"]


class ProofArtifactStatus(StrictModel):
    """One file in the workspace, with its own digest."""

    name: str
    byte_count: int
    sha256: str


class ProofClaimStatus(StrictModel):
    """A record this build does not produce, and the reason it does not.

    ``state`` is fixed at ``not_implemented``: the model lane is closed and
    arbitrary execution is closed, so there is no second opinion and no exit
    code (ADR-0009 6, 7). Reporting the absence at full volume is the whole
    point - an omitted key would read as an oversight.
    """

    key: str
    state: ProofClaimStateName
    detail: str


class ProofMissingStatus(StrictModel):
    """One named gap. Never summed into a score."""

    key: str
    state: str
    detail: str


class ProofWorkspaceResponse(StrictModel):
    """Everything a person needs in order to judge one task's proof."""

    task: TaskStatusResponse
    module: ProjectModuleStatus
    artifacts: list[ProofArtifactStatus]
    file_count: int
    total_bytes: int
    #: The digest over the whole produced set. The same number the run
    #: recorded when it finished, not a second one computed differently.
    artifact_set_sha256: str
    #: The digest of the bundle document as it stands right now. An approval
    #: and an acceptance are both bound to this value.
    bundle_sha256: str
    missing: list[ProofMissingStatus]
    claims: list[ProofClaimStatus]
    formats: list[ProofBundleFormatName]
    #: What a SHA-256 does and does not establish (ADR-0009 11). Returned
    #: rather than left to the interface, so the wording cannot drift between
    #: the two surfaces.
    hash_scope: str
    bundle_scope: str
    reproduction: str
    #: How long a share approval stays spendable once it is minted.
    approval_ttl_seconds: int


class ProofPrepareResponse(StrictModel):
    """The bundle as it stands, plus one single-use approval to deliver it.

    ``share_token`` is a capability in the sense ``send_token`` is: it turns
    "I have read this bundle" into "hand me the file". It is single-use, it
    expires, and it is bound to the bundle digest, the task, the content
    version and this browser session (ADR-0009 4).
    """

    workspace: ProofWorkspaceResponse
    share_token: str
    expires_in_seconds: int


class ProofShareRequest(StrictModel):
    """Spend the approval and take the file.

    ``acknowledged`` has no default, so a body that omits it never reaches a
    handler - the rule the evidence export is built on, applied to the surface
    that hands a proof to the browser.
    """

    share_token: str = Field(min_length=1, max_length=128)
    format: ProofBundleFormatName
    acknowledged: Literal[True]


class ProofAcceptanceRequest(StrictModel):
    """A person accepting what one exact bundle showed them.

    ``bundle_sha256`` is required and is compared against the bundle as it
    stands: an acceptance recorded against a bundle that has since changed is
    an acceptance of something else. Recording the field moves no state - the
    acceptance is the input to a publication decision, not its output
    (ADR-0009 8, SI-222).
    """

    bundle_sha256: str = Field(min_length=64, max_length=64)
    detail: str = Field(default="", max_length=500)


class ProofPublicShareRequest(StrictModel):
    """Point the fourth field at an archived send.

    ``evidence_id`` is an evidence record's own identity and nothing else. A
    sentence somebody typed has the wrong shape and is refused by
    ``EvidenceRef``'s constructor before any row is read (ADR-0009 1).
    """

    evidence_id: str = Field(min_length=32, max_length=32)
    detail: str = Field(default="", max_length=500)
