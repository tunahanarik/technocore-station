/**
 * Response shapes, mirroring `station_api/schemas.py`.
 *
 * There is deliberately no seed, private key, mnemonic or database path in
 * any of these types, because there is none in the API (INV-01, SI-36).
 */

export interface SessionBootstrap {
  readonly csrf_token: string;
  readonly csrf_header: string;
}

export interface ServiceStatus {
  readonly state: "running";
  readonly stage: number;
  readonly mode: "production" | "development";
}

export interface DatabaseStatus {
  readonly state: "ready" | "unavailable";
  readonly journal_mode: string;
  readonly foreign_keys: boolean;
  readonly schema_revision: string;
}

export interface SessionSecurityStatus {
  readonly state: "active";
  readonly cookie_http_only: boolean;
  readonly cookie_same_site: "strict";
  readonly cookie_secure: boolean;
  readonly csrf_required: boolean;
  readonly transport: "loopback-http";
}

/** The four honest states of the read-only connection. */
export type DriftState = "never_checked" | "current" | "drifted" | "unavailable";

export interface TechnocoreHeaderStatus {
  readonly state: DriftState;
  /** Writing opens in Stage 4. Reading is Stage 3. */
  readonly write_available_from_stage: number;
  readonly detail: string;
}

export interface AppStatus {
  readonly service: ServiceStatus;
  readonly database: DatabaseStatus;
  readonly session_security: SessionSecurityStatus;
  readonly technocore: TechnocoreHeaderStatus;
}

// --- Identity and recovery (Stage 2) --------------------------------------
//
// Mirrors the allow-listed response models in station_api/schemas.py. There is
// no seed, private key or vault path here, because there is none in the API.

export type IdentityState =
  | "no_identity"
  | "creating"
  | "recovery_pending"
  | "ready"
  | "revoked"
  | "capability_error";

export type ProtectionMode = "dpapi" | "dpapi+passphrase";

export interface IdentityPublic {
  readonly did: string;
  readonly public_key: string;
  readonly fingerprint: string;
  readonly fingerprint_short: string;
  readonly label: string;
  readonly status: string;
  readonly protection: ProtectionMode | null;
  readonly created_at: string;
  readonly revoked_at: string | null;
}

export interface RecoveryStatus {
  readonly exported_at: string | null;
  readonly verified_at: string | null;
  readonly file_fingerprint: string | null;
  readonly kdf: string | null;
  readonly kdf_time_cost: number | null;
  readonly kdf_memory_kib: number | null;
  readonly kdf_parallelism: number | null;
}

export interface VaultCapabilityStatus {
  readonly platform_supported: boolean;
  readonly dpapi_available: boolean;
  readonly aead_available: boolean;
  readonly usable: boolean;
  readonly detail: string;
}

export type GateCheckState = "passed" | "blocked" | "not_implemented";

export interface GateCheckStatus {
  readonly key: string;
  readonly state: GateCheckState;
  readonly detail: string;
  /** Roadmap stage that delivers this requirement: "2", "2B", "3", ... */
  readonly stage: string;
}

export interface WriteGateStatus {
  readonly allowed: boolean;
  readonly identity_ready: boolean;
  readonly blocking_reasons: readonly string[];
  readonly checks: readonly GateCheckStatus[];
}

export interface IdentityStatus {
  readonly state: IdentityState;
  readonly identity: IdentityPublic | null;
  readonly recovery: RecoveryStatus;
  readonly capability: VaultCapabilityStatus;
  readonly gate: WriteGateStatus;
  readonly default_protection: ProtectionMode;
  readonly min_passphrase_chars: number;
  readonly create_confirmation_text: string;
}

export interface RecoveryInspectResult {
  readonly did: string;
  readonly fingerprint: string;
  readonly fingerprint_short: string;
}

// --- Conformance (Stage 2B) ------------------------------------------------
//
// Public metadata about this build's conformance with the *pinned reference
// commit*. It is deliberately not a statement about the live Technocore
// server, which is manifest drift and arrives in Stage 3.

export interface ConformanceCheck {
  readonly name: string;
  readonly passed: boolean;
  /** How many vectors backed this check. Zero means it proved nothing. */
  readonly vectors: number;
  readonly detail: string;
}

export interface ConformanceStatus {
  readonly passed: boolean;
  readonly checks: readonly ConformanceCheck[];
  readonly failures: readonly string[];
  readonly capabilities: readonly string[];
  /** Full SHA-256 of the vector bundle. Never rendered: it is 64 hex
   *  characters, the same shape as a seed, and the UI has a standing rule
   *  against rendering any such run. Use `bundle_digest_short`. */
  readonly bundle_digest: string;
  readonly bundle_digest_short: string;
  readonly bundle_vectors: number;
  readonly upstream_commit: string;
  readonly upstream_commit_short: string;
  readonly package_version: string;
  readonly python_version: string;
  readonly unicode_version: string;
  readonly bundle_unicode_version: string;
  readonly unicode_version_matches: boolean;
}

// --- Read-only Technocore monitoring (Stage 3) -----------------------------
//
// Metadata only. The API never returns a document body, so nothing here can
// carry remote markup, a room message or a note value.

export type SourceOutcome = "ok" | "fetch_error" | "parse_error";

export interface OfficialSourceStatus {
  readonly source_id: string;
  readonly url: string;
  readonly authority: number;
  readonly outcome: SourceOutcome;
  readonly http_status: number;
  readonly content_type: string;
  readonly etag: string;
  readonly last_modified: string;
  /** First 12 hex characters of the SHA-256 over the exact response bytes. */
  readonly short_hash: string;
  readonly byte_count: number;
  readonly detail: string;
  readonly rationale: string;
}

/**
 * Why a field did not match.
 *
 * `mismatch` means the value was read and is different - real drift.
 * `missing` and `unsupported` mean it could not be read at all, which is not
 * evidence that the server changed anything. The UI must not present the two
 * as the same thing.
 */
export type FieldOutcome = "matched" | "mismatch" | "missing" | "unsupported";

export interface ProtocolFieldStatus {
  readonly key: string;
  readonly label: string;
  readonly source_id: string;
  /** JSON Pointer into the source document. */
  readonly json_path: string;
  readonly severity: "critical" | "warning";
  readonly expected: string;
  readonly observed: string;
  readonly matches: boolean;
  readonly outcome: FieldOutcome;
  readonly rationale: string;
  /** Set when `outcome` is `unsupported`: what could not be read. */
  readonly detail: string;
}

// --- Composer (Paket D) ----------------------------------------------------
//
// Hand-written mirrors of the four `Compose*` models in
// `station_api/schemas.py`. Two things are deliberately absent and must stay
// absent: there is no seed or private key (INV-01), and there is no URL, host
// or method the caller can steer - `write_method` and `write_path_template`
// are reported *by* the server so the UI never has to assume the lane.

export interface ComposeCapability {
  readonly can_compose: boolean;
  /** Gate check keys, same vocabulary as `WriteGateStatus.blocking_reasons`. */
  readonly blocking_reasons: readonly string[];
  readonly write_method: "POST";
  readonly write_path_template: string;
  readonly denied_rooms: readonly string[];
  readonly room_class_markers: readonly string[];
  readonly max_chars: number;
  readonly min_chars: number;
  readonly draft_ttl_seconds: number;
  readonly approval_ttl_seconds: number;
  /** Always false in this release; the field exists so the UI cannot guess. */
  readonly note_lane_available: false;
  /** Why there is no note send path, in the backend's own words (ADR-0002 1). */
  readonly note_lane_detail: string;
}

/** Step 1. Nothing is signed and no nonce is reserved yet. */
export interface ComposeDraft {
  readonly draft_id: string;
  readonly room: string;
  readonly room_classes: readonly string[];
  readonly raw_text: string;
  readonly swept_text: string;
  readonly changed_by_sweep: boolean;
  readonly raw_chars: number;
  readonly swept_chars: number;
  /** Binds step 2 to this exact content; changing text or room changes it. */
  readonly draft_digest: string;
  readonly min_chars: number;
  readonly max_chars: number;
  readonly expires_in_seconds: number;
  readonly target_notes: readonly string[];
}

/** Step 2. The exact bytes that were signed, plus a single-use approval. */
export interface ComposeSignature {
  readonly draft_id: string;
  readonly room: string;
  readonly did: string;
  readonly nonce: string;
  /** The canonical string, shown verbatim: displayed is signed (charter 14). */
  readonly canonical: string;
  readonly canonical_digest: string;
  readonly signature: string;
  readonly changed_by_sweep: boolean;
  /** A capability. Held in component state only, and spent exactly once. */
  readonly send_token: string;
  readonly expires_in_seconds: number;
}

/**
 * The three-valued result of one write attempt (ADR-0002 3).
 *
 * `outcome_unknown` means the server may have stored the message. It is not a
 * synonym for failure and must never be rendered as one.
 */
export type WriteOutcome = "accepted" | "refused" | "outcome_unknown";

export interface ComposeSendResult {
  readonly outcome: WriteOutcome;
  readonly room: string;
  readonly did: string;
  readonly nonce: string;
  readonly canonical_digest: string;
  readonly signature: string;
  readonly http_status: number;
  readonly detail: string;
  /** A bounded, server-swept excerpt. Plain text only - never markup (SI-54). */
  readonly response_excerpt: string;
  /** True only for `outcome_unknown`; reconciliation is not in this release. */
  readonly reconciliation_required: boolean;
}

// --- Evidence and audit (Paket E) ------------------------------------------
//
// Hand-written mirrors of the `Evidence*` and `AuditChain*` models in
// `station_api/schemas.py`. Two absences are deliberate and must stay:
//
// 1. There are **no raw request or response bytes** here, because the listing
//    endpoint does not return them. Only digests cross this boundary; the
//    bytes themselves leave the machine solely through an explicitly
//    acknowledged export.
// 2. There is no field, flag or parameter that re-sends anything. A capture is
//    a read (ADR-0003 4), and the type system offers nothing else.

/** One of the four trust levels, reported per record and never summed. */
export interface EvidenceLevelStatus {
  readonly level: 1 | 2 | 3 | 4;
  readonly name: string;
  readonly present: boolean;
  readonly detail: string;
}

/**
 * How one capture attempt ended.
 *
 * Six values, and five of them establish nothing about whether the message was
 * published. `line_not_found` in particular never turns an `outcome_unknown`
 * send into `not_sent` (ADR-0003 3).
 */
export type CaptureAttemptState =
  | "line_captured"
  | "line_not_found"
  | "generation_changed"
  | "stream_truncated"
  | "parse_problem"
  | "fetch_failed";

/** A record's stored capture state. `""` means no capture has been asked for. */
export type EvidenceCaptureState = "" | CaptureAttemptState;

/**
 * The archived write outcome.
 *
 * Wider than `WriteOutcome` by two: a record can exist for an attempt that is
 * still in flight, or for one that never left this machine.
 */
export type EvidenceWriteOutcome =
  | "in_flight"
  | "accepted"
  | "refused"
  | "outcome_unknown"
  | "not_sent";

/** The audit chain's five verdicts. `unavailable` is never "passed". */
export type AuditChainState =
  | "intact"
  | "empty"
  | "broken_link"
  | "head_mismatch"
  | "unavailable";

/** One archived send. Hashes only - the raw bytes are not in this payload. */
export interface EvidenceRecord {
  readonly id: string;
  readonly reservation_id: string;
  readonly room: string;
  readonly did: string;
  readonly nonce: string;
  /** 64 hex characters. Never rendered whole; the UI shows a short prefix. */
  readonly canonical_sha256: string;
  readonly signature: string;
  readonly http_status: number;
  readonly write_outcome: EvidenceWriteOutcome;
  readonly capture_state: EvidenceCaptureState;
  readonly capture_detail: string;
  readonly captured_at: string | null;
  /** The epoch this record was first seen under. Set once, never overwritten. */
  readonly room_generation: string;
  /** The epoch the stored line was read under, so the two are never mixed. */
  readonly capture_generation: string;
  /** Sticky: the room has been seen under more than one epoch, so the two
   * sides are not comparable however the latest read turned out. */
  readonly generation_changed: boolean;
  readonly captured_line_offset: number | null;
  readonly captured_line_length: number | null;
  readonly stream_sha256: string;
  readonly stream_bytes: number;
  readonly stream_truncated: boolean;
  readonly unreadable_lines: number;
  readonly request_sha256: string;
  readonly response_sha256: string;
  readonly recorded_at: string;
  /** Level 4. Always `null` in this release; present so "absent" is stated. */
  readonly external_anchor: string | null;
  readonly levels: readonly EvidenceLevelStatus[];
}

export interface EvidenceList {
  readonly records: readonly EvidenceRecord[];
  readonly record_count: number;
  /** The chain's verdict, returned beside the records so neither stands alone. */
  readonly chain_state: AuditChainState;
  readonly chain_detail: string;
  readonly chain_link_count: number;
}

/** The result of one read-only capture attempt. */
export interface EvidenceCaptureResult {
  readonly evidence_id: string;
  readonly state: CaptureAttemptState;
  readonly detail: string;
  /** True only for `line_captured`, and it means level 2 - no more. */
  readonly server_observation: boolean;
  /** The epoch **this read** published, or "" when it published none - not
   * the record's frozen baseline, which `/records` returns as
   * `room_generation` beside `capture_generation`. */
  readonly room_generation: string;
  readonly line_offset: number | null;
  readonly line_length: number | null;
  readonly stream_sha256: string;
  readonly scanned_bytes: number;
  readonly stream_truncated: boolean;
  /** A read may be retried. */
  readonly read_retry_allowed: true;
  /** A write may not, ever. The field is `false` by construction server-side. */
  readonly write_retry_allowed: false;
}

export interface AuditChainStatus {
  readonly state: AuditChainState;
  readonly detail: string;
  readonly link_count: number;
  readonly head_count: number | null;
  readonly first_bad_seq: number | null;
  /**
   * The only permitted description of what this mechanism provides, produced
   * by the backend so the wording cannot drift between the two surfaces. It is
   * rendered verbatim; the UI never composes a claim of its own.
   */
  readonly claim: string;
}

export type EvidenceExportFormat = "json" | "markdown";

export interface TechnocoreStatus {
  readonly state: DriftState;
  readonly manifest_current: boolean;
  readonly checked_at: string | null;
  readonly last_attempt_at: string | null;
  readonly last_success_at: string | null;
  readonly reasons: readonly string[];
  readonly sources: readonly OfficialSourceStatus[];
  readonly fields: readonly ProtocolFieldStatus[];
  /** Critical fields read and found different: real drift. */
  readonly critical_mismatch_count: number;
  /** Critical fields that could not be evaluated at all. */
  readonly critical_unevaluable_count: number;
  readonly warning_count: number;
  readonly origin: string;
}

// --- OpenCode Go connection (Paket G) --------------------------------------
//
// Hand-written mirrors of the `OpenCode*` models in `station_api/schemas.py`.
// They copy the backend's shape including the holes in it, because the holes
// are the contract:
//
// * there is no `api_key`, `key`, `token` or `secret` field anywhere below,
//   in either direction after the one write, because the API has no route
//   that returns the stored key (ADR-0005 7);
// * a connection verdict has no `verified` value and no boolean badge - it is
//   a state plus every reason it is not stronger (ADR-0005 4);
// * `selectable` travels with the `reason` it is false, because listing a
//   model is not the same claim as being able to call it (ADR-0005 5);
// * `budget_available` is `false` as a *type*, so no future edit can open a
//   budget here by assigning to it (ADR-0005 9).

/**
 * What can honestly be said about the stored credential.
 *
 * Note the absent value: there is no `verified`. The provider's catalog
 * answers without a key, a GET on a protocol path answers 404, and this
 * build makes no metered call on its own - so nothing here can earn a
 * verified verdict, and the type refuses to hold one.
 */
export interface OpenCodeConnectionCheck {
  readonly state: "not_configured" | "never_checked" | "key_saved_unverified";
  /** Plural on purpose. One reason reads like a fixable problem; the list is
   * the actual epistemic position. */
  readonly reasons: readonly string[];
  readonly detail: string;
}

/** One catalog row, joined to what this build knows about it. */
export interface OpenCodeModel {
  readonly model_id: string;
  readonly owned_by: string;
  /** False whenever the protocol family was not published for this model. */
  readonly selectable: boolean;
  /** Empty when there is no table entry. An absent protocol is not a default. */
  readonly protocol: string;
  readonly protocol_verification: "documented" | "unverified";
  /** Why it cannot be selected, in the user's language. Empty when it can. */
  readonly reason: string;
  /** The provider's published retention term, or `unknown`. Rendered as it
   * arrives and never rewritten into a reassurance. */
  readonly retention: string;
  readonly training_use: "yes" | "no" | "unknown";
  /** `unknown` asks for acknowledgement exactly as `yes` does. */
  readonly requires_training_acknowledgement: boolean;
  readonly privacy_source: string;
  readonly privacy_read_on: string;
}

export interface OpenCodeCatalog {
  readonly state: "never_fetched" | "ok" | "fetch_error" | "parse_error";
  /** The last **attempt**. A failed refresh moves this and nothing else. */
  readonly fetched_at: string | null;
  /** When the listed models were actually read. Separate on purpose: a failed
   * refresh must not lend the cache a date it did not earn. */
  readonly models_fetched_at: string | null;
  readonly detail: string;
  readonly http_status: number;
  readonly models: readonly OpenCodeModel[];
  readonly model_count: number;
  readonly selectable_count: number;
  /** How many listed models the pinned protocol table has no row for. */
  readonly unmapped_count: number;
  readonly listing_caveat: string;
  /** When the pinned protocol table was read, and what the source page's own
   * footer said that day. Always present: the age of a transcription is a
   * fact about every reading of it, not an exception to report. */
  readonly table_provenance: string;
  /** Empty while the catalog and the pinned table agree; a warning once the
   * provider lists more unmapped models than the transcription accounted
   * for. Rendered verbatim, and never suppressed. */
  readonly drift_notice: string;
}

export interface OpenCodePublishedLimit {
  readonly window: string;
  readonly amount_usd: number;
  readonly note: string;
}

/** Read-only spending context. No budget opens here. */
export interface OpenCodeSpendingContext {
  readonly budget_available: false;
  readonly limits: readonly OpenCodePublishedLimit[];
  readonly limit_behaviour: string;
  /** Where the preference lives. Station does not change it. */
  readonly use_balance: string;
  readonly local_counter_caveat: string;
  readonly unknown_cost_sentence: string;
}

/** The three families, the format still not built, and the one measured. */
export interface OpenCodeProtocolContext {
  readonly protocols: readonly string[];
  /** Still a literal `false`. The streaming format was never published and
   * has never been measured, so a mirror that could hold anything else here
   * would be a mirror that could hold a guess. */
  readonly streaming_supported: false;
  /**
   * A plain `boolean`, and it was a literal `false` for a reason that has
   * stopped being true rather than for a reason that was dropped.
   *
   * ADR-0012 measured the tool-call contract against the provider's own
   * `chat/completions` endpoint, so the backend widened this to `bool` and
   * derives it from `TOOL_CALLS_SUPPORTED`. Widening rather than pinning to
   * `true` is the repair `public_share_available` already got: what the field
   * may carry is the server's decision, and a mirror that pinned the *new*
   * value would be the same defect facing the other way.
   */
  readonly tool_calls_supported: boolean;
  readonly deferral: string;
  readonly shape_provenance: string;
  /** What was measured, on which endpoint, and how far the measurement
   * reaches. Empty until something is measured: a supported format with no
   * provenance beside it is exactly the unsourced claim ADR-0005 1.2
   * refuses. Rendered verbatim. */
  readonly tool_call_provenance: string;
}

/** The whole connection, read-only. Reading it sends nothing outward. */
export interface OpenCodeStatus {
  readonly configured: boolean;
  /** Twelve characters of an HMAC over a fixed public label. It names which
   * credential is installed without revealing any part of it. */
  readonly fingerprint_short: string;
  readonly configured_at: string | null;
  readonly updated_at: string | null;
  readonly check: OpenCodeConnectionCheck;
  readonly selected_model: string;
  /** The header assumption, stated to the user rather than buried in a source
   * comment (ADR-0005 3). Rendered verbatim. */
  readonly auth_header_caveat: string;
  readonly catalog: OpenCodeCatalog;
  readonly spending: OpenCodeSpendingContext;
  readonly protocol_context: OpenCodeProtocolContext;
}

// --- Public-room work scan (Paket H1) --------------------------------------
//
// Hand-written mirrors of the `WorkScan*` models in `station_api/schemas.py`.
// As with the OpenCode group, the holes are copied deliberately, because the
// holes are the contract:
//
// * there is no `is_open` anywhere below. Element 8 is a sentence with the
//   moment of the reading in it, and a boolean would be read as an answer
//   this surface cannot produce (ADR-0007 8);
// * there is no `is_stale` and no threshold. What exists is the measured
//   reading time and the bound the *service* declares about itself
//   (ADR-0007 5);
// * there is no `score`, `rank` or `reputation` field in any direction. The
//   one third-party record below describes a service; it is not a client for
//   one, and `adapter_written`/`contacted` are `false` as *types*
//   (ADR-0007 1);
// * `budget_state` is `not_implemented` as a type, so no edit can make a
//   missing budget read as an approved one.

/**
 * Element 1: the verbatim line and its coordinates.
 *
 * `authority` is `3` - community - on every one of these, and it arrives on
 * the wire rather than being inferred here. The endpoint is official; what
 * came back through it is anonymous input written by strangers, and only one
 * of those two facts is about the text.
 */
export interface WorkScanQuote {
  readonly room: string;
  readonly seq: number;
  readonly ts: string;
  /** A `did:key` or a nickname the writer typed. Told apart by the flag
   * below, never by how the string looks. */
  readonly author: string;
  readonly author_is_did_key: boolean;
  /** The one sentence the backend permits about that value. Rendered as it
   * arrives, so no view can say more than the field supports. */
  readonly author_detail: string;
  /** The message body, swept for display. Data - never markup, never a link. */
  readonly quote: string;
  /** `room#seq@ts`, in one machine-checkable string. */
  readonly reference: string;
  readonly authority: 3;
}

/** Element 5: whether this build has the module and the gate for the work. */
export interface WorkScanCapability {
  readonly module_id: string;
  readonly module_state: string;
  readonly module_available: boolean;
  readonly write_gate_open: boolean;
  /** Both halves, and never one standing in for the other. */
  readonly ready: boolean;
  readonly detail: string;
}

/** Element 6: an estimate that says so in the payload, not in a tooltip. */
export interface WorkScanEffort {
  readonly label: "tahmin";
  readonly band: string;
  readonly basis: string;
}

/** Element 8. A sentence and a reading time; deliberately not a boolean. */
export interface WorkScanOpenState {
  readonly read_at: string;
  readonly detail: string;
}

/** One proposal, with all eight elements present. None of them may be hidden. */
export interface WorkScanCandidate {
  readonly id: string;
  readonly signal: string;
  readonly source: WorkScanQuote;
  readonly benefit: string;
  readonly deliverable: string;
  readonly success_condition: string;
  readonly test_method: string;
  readonly capability: WorkScanCapability;
  readonly effort: WorkScanEffort;
  readonly budget_state: "not_implemented";
  readonly budget_detail: string;
  readonly permissions: readonly string[];
  readonly risks: readonly string[];
  readonly open_state: WorkScanOpenState;
  readonly derivation: string;
}

/** A line the backend declined to propose work from, and why. Shown, not hidden. */
export interface WorkScanRefusal {
  readonly room: string;
  readonly seq: number;
  readonly shape: string;
  readonly detail: string;
}

/**
 * A room that could not be read.
 *
 * Never folded into "found nothing": "we read this room and found nothing"
 * and "we could not read this room" look identical in a candidate list, and
 * only one of them means there is nothing to do.
 */
export interface WorkScanRoomFailure {
  readonly room: string;
  readonly reason: string;
  readonly detail: string;
}

export interface WorkScanRoomResult {
  readonly room: string;
  readonly candidates: readonly WorkScanCandidate[];
  readonly refusals: readonly WorkScanRefusal[];
  /** How many lines were actually read. An empty candidate list beside a
   * non-zero count is a different finding from an empty room. */
  readonly lines_read: number;
}

/**
 * The reading time and the service's own declared cache bound.
 *
 * There is no `is_stale`. The backend invents no threshold, so it publishes
 * no verdict, and neither does this app.
 */
export interface WorkScanStaleness {
  readonly read_at: string;
  readonly declared_cache_seconds: number;
  /** Where that number was read, so a reader can check it. */
  readonly declared_by: string;
  readonly detail: string;
}

/**
 * The service's own machine-readable signal that history was dropped.
 *
 * Separate from `WorkScanStaleness` on the wire and separate on screen: "the
 * list may be three seconds old" and "messages you never read are gone" are
 * different findings and neither may stand in for the other.
 */
export interface WorkScanRingDrop {
  readonly since: number;
  readonly expected_first: number;
  readonly first_seq: number;
  readonly detail: string;
}

/**
 * One aggregate the **service** reports about a room.
 *
 * A separate type from the room's `name`/`topic` because it is a separate
 * kind of fact. The backend reads these structurally - every key on the entry
 * that is *not* caller-written - because the published `rooms[]` item schema
 * names no properties at all, so `key` is the service's own name for the
 * number and never one this product invented.
 */
export interface WorkScanMeasuredField {
  readonly key: string;
  readonly value: string;
}

/**
 * What the reply claimed about its own caller-written fields.
 *
 * Carried so a screen can show the claim, never so a screen can rely on it.
 * The set that counts is the **union** of `build_fields` and `fields`: a reply
 * may widen the untrusted set and can never narrow it, and `missing_fields`
 * is the record of an attempt to narrow it.
 */
export interface WorkScanUntrusted {
  /** Whether the reply carried an `untrusted` object at all. "No declaration"
   * and "a declaration that omits our fields" are two different answers. */
  readonly present: boolean;
  /** The fields the reply named. */
  readonly fields: readonly string[];
  readonly note: string;
  /** The fields this build treats as caller-written regardless. */
  readonly build_fields: readonly string[];
  /** Named by the reply and not by this build: the reply widened the set. */
  readonly extra_fields: readonly string[];
  /** Named by this build and not by the reply: an attempt to narrow it. */
  readonly missing_fields: readonly string[];
  readonly detail: string;
}

/**
 * One room as the overview listed it, with its two halves kept apart.
 *
 * `name` and `topic` are strings a stranger typed - that is what `authority:
 * 3` says, and the service's own `/rooms` description says the same thing in
 * its own words. `measured` is the *other* half: the service's aggregates over
 * its own bounded window, carried under the service's own key names. They are
 * two fields rather than one object with a caveat beside it precisely so a
 * reader never has to remember which is which.
 */
export interface WorkScanRoom {
  readonly name: string;
  readonly topic: string;
  readonly authority: 3;
  readonly measured: readonly WorkScanMeasuredField[];
  /** Whether the backend kept fewer measured fields than the entry carried. */
  readonly measured_truncated: boolean;
}

export interface WorkScanRoomIndex {
  readonly rooms: readonly WorkScanRoom[];
  /** The service's own count of every listed room. Not `rooms.length`. */
  readonly total: number;
  readonly kept_count: number;
  readonly truncated: boolean;
  readonly staleness: WorkScanStaleness;
  readonly sha256: string;
  readonly room_name_caveat: string;
  /** `topic` is a world-writable KV note, not an endorsement. */
  readonly topic_caveat: string;
  /** The sentence that travels with every `measured` list: these are the
   * service's own numbers and nothing is derived from them. */
  readonly measured_caveat: string;
  /** Always present: an unlisted (`p-`) room is never enumerated here, so the
   * listing's silence about one is not evidence that it does not exist. */
  readonly unlisted_note: string;
  readonly untrusted: WorkScanUntrusted;
}

/**
 * One line of the discovery log (`GET /r/events`).
 *
 * A line, not an endorsement. There is deliberately no `recommended`, `score`
 * or `rank` here. `selectable` is `false` for every line the backend could not
 * read as a room name - including a line announcing a room the service says it
 * never announces - and the raw `line` is kept so a reader sees the log's real
 * format rather than this product's guess at one. `line` is empty only where
 * repeating it would print a room this product never names.
 */
export interface WorkScanAnnouncedRoom {
  readonly seq: number;
  readonly ts: string;
  /** The room this line announces, or `""` when none could be read. Never a
   * placeholder: a placeholder would be a room name this build made up. */
  readonly name: string;
  readonly line: string;
  /** Why no name was read, or `""` when one was. */
  readonly unusable_reason: string;
  readonly selectable: boolean;
  readonly authority: 3;
}

/**
 * One read of the discovery log: new public rooms, in announcement order.
 *
 * `since` is a cursor the *caller* carries back from the previous read's
 * `last_seq`. Nothing on either side remembers it, because a remembered cursor
 * is the first half of a loop somebody schedules.
 */
export interface WorkScanDiscovery {
  readonly room: string;
  readonly entries: readonly WorkScanAnnouncedRoom[];
  readonly since: number | null;
  /** What a caller passes back as `since` to continue - by pressing something. */
  readonly last_seq: number;
  readonly first_seq: number | null;
  readonly lines_read: number;
  /** The rooms this log offers as one-click scan choices. */
  readonly selectable: readonly string[];
  readonly unusable_count: number;
  readonly ring_drop: WorkScanRingDrop | null;
  readonly staleness: WorkScanStaleness;
  readonly sha256: string;
  readonly room_name_caveat: string;
  readonly unlisted_note: string;
  /** Why this build never writes here, and what would happen if it tried. */
  readonly write_refusal: string;
}

/**
 * A fact about a scanned room's class. Not a failure: the room was read.
 *
 * An unlisted room appears in no listing, so its name came from somewhere
 * else; an ephemeral one can expire on read, so an absent line proves nothing.
 * No note is produced for an ordinary listed room, which makes this a
 * distinction rather than a banner.
 */
export interface WorkScanRoomNote {
  readonly room: string;
  readonly kind: "unlisted" | "ephemeral";
  readonly detail: string;
}

/** One thing about an external service, and whether anybody confirmed it. */
export interface WorkScanAdapterFact {
  readonly key: string;
  readonly detail: string;
  readonly state: "verified" | "not_verified";
}

/**
 * An external service record. Never a client, and never contacted.
 *
 * `adapter_written` and `contacted` are `false` as *types*: there is no state
 * in which this build holds an adapter for a third-party job board, and no
 * assignment can open one here.
 */
export interface WorkScanAdapter {
  readonly id: string;
  readonly name: string;
  readonly support: string;
  readonly authority: 3;
  readonly declared_origin: string;
  readonly adapter_written: false;
  readonly contacted: false;
  readonly verified: readonly WorkScanAdapterFact[];
  readonly unverified: readonly WorkScanAdapterFact[];
  /** The service's own description of itself, rendered as it arrives. */
  readonly self_description: string;
  /** The service's own two sentences, in the language it wrote them in.
   * They arrive on the wire rather than being transcribed into a constant
   * here: a quotation kept in two places is a quotation that can drift. */
  readonly self_description_source: string;
  readonly score_self_description: string;
  readonly score_caveat: string;
  /** When the record was written and how much of it was confirmed. Always
   * present: the age of a transcription is a fact about every reading of it. */
  readonly provenance: string;
}

/** One scan of one user-chosen room set. */
export interface WorkScanResult {
  readonly started_at: string;
  readonly completed_at: string;
  /** The rooms actually read, after the backend's room policy. */
  readonly rooms: readonly string[];
  readonly results: readonly WorkScanRoomResult[];
  readonly failures: readonly WorkScanRoomFailure[];
  /** What was true of a scanned room's *class*, when anything was. */
  readonly notes: readonly WorkScanRoomNote[];
  readonly candidate_count: number;
  readonly refusal_count: number;
}

/** The whole scan surface, read-only. Reading it sends nothing outward. */
export interface WorkScanStatus {
  /** The cost of a deterministic derivation, stated on every read and not
   * only beside a result (ADR-0007 2). Rendered verbatim. */
  readonly honesty: string;
  readonly capability: WorkScanCapability;
  readonly adapters: readonly WorkScanAdapter[];
  readonly room_index: WorkScanRoomIndex | null;
  /** The last discovery-log read, or `null` until a person asked for one.
   * `null` on a fresh process is the honest answer: a log that appeared
   * without a request would be an automatic read (SI-224, SI-272). */
  readonly discovery: WorkScanDiscovery | null;
  readonly last_scan: WorkScanResult | null;
  /** The query parameters this build refuses to send, named in the payload so
   * the absence of polling is checkable from outside the process. */
  readonly never_sent_params: readonly string[];
  readonly polling_statement: string;
  /** The refusal half of the honesty sentence: the prohibited work shapes are
   * matched by pattern, not recognised by meaning. */
  readonly prohibition_statement: string;
}

/** The task one candidate opened. Born `suggested`; approved by nobody. */
export interface WorkScanSuggestion {
  readonly task_id: string;
  readonly module_id: string;
  readonly source_id: string;
  readonly source_version_id: string;
  readonly state: "suggested";
  readonly detail: string;
  /**
   * The workspace file carrying the request's full text, or `""` when the
   * write did not happen.
   *
   * A scanned request is stored as a **digest**, so the readable form of one
   * used to be its title and nothing else - which is all a model could ever
   * be shown of it. The text is written into the new task's own workspace
   * now, where the agent's existing read tool reaches it, and this names the
   * file so a person can open the same bytes the model was given.
   */
  readonly request_file: string;
  /**
   * One sentence about that write, in either direction. Never empty.
   *
   * An empty `request_file` with a populated sentence here is a task that
   * exists, whose digest is correct, and behind which there is nothing
   * readable. That has to be sayable out loud rather than inferred from an
   * empty directory, which is why it is a field and not a silence.
   */
  readonly request_file_detail: string;
}

// --- Tasks, the agent runtime and the Activity Desk (Paket H2) --------------
//
// Hand-written mirrors of the `Task*`, `Agent*` and `Activity*` models in
// `station_api/schemas.py`. The holes below are copied on purpose, because
// the holes are the contract (ADR-0008):
//
// * there is **no boolean that says a task succeeded**. Four separate fields
//   carry the four separate questions, and nothing in this file can sum them
//   (ADR-0008 6, ADR-0004 4);
// * `test_result_state` is `not_implemented` as a *type*, so no edit can make
//   an unexecuted plan read as a tested one;
// * `arbitrary_execution_supported` and `agent_can_raise_ceiling` are `false`
//   as types, and `relied_upon` is `false` on every measured facility: a
//   sandbox that exists on one machine is not a guarantee the product offers
//   (ADR-0008 1, 4);
// * there is no `token` and no currency anywhere. `refused_units` names what
//   this build refuses to denominate a ceiling in, so the absence is a claim
//   on the wire rather than something a reader has to notice (ADR-0008 4);
// * there is no field for a model's reasoning, a prompt, a completion or a
//   raw provider payload. The model lane is closed and the table these rows
//   come from has no column for such a thing (ADR-0008 2, 6);
// * there is no filesystem path in either direction: a workspace file is
//   named, never located.

/** The three-valued check state, spelled the way the write gate spells it. */
export type TaskCheckState = "passed" | "blocked" | "not_implemented";

/** The four fields a result is recorded in. Never collapsed into one boolean. */
export type TaskEvidenceFieldName =
  | "task_outcome"
  | "test_result"
  | "user_acceptance"
  | "public_share";

/** All nine states. H2 opened `running` and `paused` (ADR-0008 3). */
export type TaskStateName =
  | "suggested"
  | "awaiting_approval"
  | "running"
  | "paused"
  | "blocked"
  | "failed"
  | "review_needed"
  | "ready_to_publish"
  | "published";

/**
 * The transitions a **person** may ask for.
 *
 * `running` and `paused` are absent: they belong to the runner and are
 * reached through the run routes, which write a plan down first.
 * `ready_to_publish` is absent because it is derived from evidence and
 * cannot be asked for (SI-222).
 */
export type TaskUserTransitionName =
  | "awaiting_approval"
  | "blocked"
  | "failed"
  | "review_needed"
  | "published";

/** One of the four fields, reported on its own. Never summed with another. */
export interface TaskFieldStatus {
  readonly evidence_field: TaskEvidenceFieldName;
  readonly state: TaskCheckState;
  readonly detail: string;
  readonly ref_id: string;
}

/** One task, its state, and the four fields kept apart. */
export interface TaskStatusResponse {
  readonly id: string;
  readonly module_id: string;
  readonly source_id: string;
  readonly content_sha256: string;
  readonly source_version_id: string;
  readonly title: string;
  readonly state: TaskStateName;
  readonly state_detail: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly evidence_fields: readonly TaskFieldStatus[];
  /** Derived from three separately verified fields. Never asked for. */
  readonly ready_to_publish: boolean;
  readonly blocking_fields: readonly string[];
  /**
   * Whether the fourth field can be filled at all.
   *
   * This was typed `false` through Package H2, because four separate layers
   * made `public_share` unrepresentable and the type said so. **Package H3
   * opened the field** (ADR-0009 1) and the backend now derives this from
   * `EvidenceField.PUBLIC_SHARE not in UNFILLABLE_FIELDS`, which is empty -
   * so the wire carries `true` and a `false` here was a type that had stopped
   * describing the server.
   *
   * Nothing broke while it was wrong, and that is the reason it is called out:
   * the fixtures build their own bodies and TypeScript never checks the wire,
   * so a mirror that has drifted looks exactly like a mirror that is right.
   * Widened to `boolean` rather than flipped to `true`: what the field can
   * carry is a server decision, and pinning the new answer as a type would
   * repeat the mistake in the opposite direction.
   */
  readonly public_share_available: boolean;
  readonly public_share_detail: string;
  /** There is no budget in the task layer, and the type says so (SI-225). */
  readonly budget_available: false;
  readonly budget_detail: string;
}

export interface TaskListResponse {
  readonly tasks: readonly TaskStatusResponse[];
  readonly task_count: number;
  readonly producible_states: readonly TaskStateName[];
  /** Empty since H2. The field stayed and the sentence changed, so a reader
   * who saw three names here last release is told the set is now empty. */
  readonly unproducible_states: readonly TaskStateName[];
  readonly unproducible_detail: string;
}

/** Where a run is. The four endings are distinct values, on purpose. */
export type AgentRunPhaseName =
  | "planned"
  | "running"
  | "paused"
  | "completed"
  | "cancelled"
  | "tool_error"
  | "budget_exhausted"
  | "artifact_missing";

/** What became of one planned step. */
export type AgentStepPhaseName = "planned" | "ran" | "refused" | "failed" | "skipped";

/** The permission a tool needs. None of them leaves this machine. */
export type AgentToolScopeName =
  | "read_approved_input"
  | "write_workspace"
  | "deterministic_check"
  | "read_run_state";

/** The parameter types. There is deliberately no `path` and no `url`. */
export type AgentToolParamTypeName = "text" | "file_name" | "digest";

/** What the measurement established. `not_measured` is not `absent`. */
export type AgentIsolationStateName = "present" | "absent" | "not_measured";

/**
 * The five acceptance conditions a plan may be judged by.
 *
 * A closed vocabulary, mirroring `AgentAcceptanceKindName`. A plan that
 * records none of them still reports `not_implemented`, which is what an
 * unchecked plan has earned.
 */
export type AgentAcceptanceKindName =
  | "artifact_exists"
  | "artifact_is_json"
  | "artifact_has_json_keys"
  | "artifact_contains"
  | "artifact_digest_is";

/**
 * What a run's test field reports. Three values, because they answer three
 * different questions: the conditions held, at least one did not, or the plan
 * never wrote one a machine could decide.
 *
 * It was `"not_implemented"` as a single literal here until Package H4, and
 * the *fact* changed rather than the rule. Arbitrary execution is still
 * closed and a `test_condition` sentence is still never run; what opened is a
 * closed registry of deterministic conditions decided over the bytes a run
 * produced. SI-222 is untouched: the state is still derived from evidence and
 * still cannot be asked for.
 */
export type AgentTestResultStateName = "passed" | "failed" | "not_implemented";

/** Who acted. There is no `model` actor, because there is no model lane. */
export type ActivityActorName = "user" | "station_runner";

export type ActivityOutcomeName = "ok" | "refused" | "failed" | "pending";

/**
 * The kinds of moment the timeline distinguishes.
 *
 * Seventeen values rather than one `step_done`: "planned", "a tool was
 * called", "an artifact was produced", "a check was recorded" and "waiting
 * for approval" answer different questions, and a timeline that folded them
 * into one badge could no longer say whether anything was actually checked
 * (ADR-0008 6).
 *
 * The last three arrived with the model planning lane (ADR-0012). They are
 * *actions*, not an actor: `ActivityActorName` still has no `model` member,
 * because a model turn is something the station's runner did on a person's
 * behalf, and nothing a model says gets recorded as its own act.
 */
export type ActivityActionName =
  | "run_planned"
  | "run_started"
  | "tool_called"
  | "artifact_produced"
  | "check_recorded"
  | "approval_awaited"
  | "run_stopped"
  | "run_resumed"
  | "run_finished"
  | "run_failed"
  | "permission_denied"
  | "budget_exhausted"
  | "execution_unavailable"
  | "activity_deleted"
  | "model_called"
  | "model_plan_proposed"
  | "model_session_ended";

export interface AgentToolParamStatus {
  readonly name: string;
  readonly type: AgentToolParamTypeName;
  readonly required: boolean;
  readonly detail: string;
}

/** One acceptance condition the registry offers, and what it asks for. */
export interface AgentAcceptanceCheckStatus {
  readonly kind: AgentAcceptanceKindName;
  readonly purpose: string;
  readonly params: readonly AgentToolParamStatus[];
}

/**
 * One condition a plan actually recorded, and how it stands right now.
 *
 * `satisfied` is recomputed from the workspace on every read rather than
 * stored, so a condition that held yesterday and does not hold now reports
 * the second thing.
 */
export interface AgentAcceptanceConditionStatus {
  readonly kind: AgentAcceptanceKindName;
  readonly label: string;
  readonly satisfied: boolean;
  readonly detail: string;
}

/** One registered tool, with everything a person needs to approve it. */
export interface AgentToolStatus {
  readonly id: string;
  readonly scope: AgentToolScopeName;
  readonly purpose: string;
  readonly params: readonly AgentToolParamStatus[];
  readonly call_cost: number;
  readonly produces_artifact: boolean;
}

/** The run ceiling, in the only three units this build can measure. */
export interface AgentCeilingStatus {
  readonly max_tool_calls: number;
  readonly max_wall_clock_seconds: number;
  readonly max_concurrency: 1;
  readonly units: readonly string[];
  /** Units this product refuses to denominate a ceiling in, and why. */
  readonly refused_units: readonly string[];
  readonly refused_units_detail: string;
  readonly detail: string;
  /** Structural: the ceiling is a compile-time constant nothing writes. */
  readonly agent_can_raise_ceiling: false;
}

/** One measured facility, and - separately - whether it is relied upon. */
export interface AgentIsolationFindingStatus {
  readonly facility: string;
  readonly measured: AgentIsolationStateName;
  readonly measured_at: string;
  readonly detail: string;
  readonly relied_upon: false;
}

/** Why arbitrary code and shell execution are closed, as a reason. */
export interface AgentExecutionStatus {
  readonly arbitrary_execution_supported: false;
  readonly reason: "execution_unavailable";
  readonly detail: string;
  readonly inventory: readonly AgentIsolationFindingStatus[];
}

/** One planned tool call and what became of it. */
export interface AgentRunStepStatus {
  readonly ordinal: number;
  readonly tool_id: string;
  readonly scope: AgentToolScopeName;
  readonly arguments_sha256: string;
  readonly phase: AgentStepPhaseName;
  readonly started_at: string | null;
  readonly finished_at: string | null;
  /** The name of the file this step produced, never its path. */
  readonly artifact_name: string;
  readonly artifact_sha256: string;
  readonly detail: string;
}

/** One workspace file: its name, its size and its digest. No path. */
export interface AgentWorkspaceFileStatus {
  readonly name: string;
  readonly byte_count: number;
  readonly sha256: string;
}

/** One run, with its plan, its usage and its ending kept apart. */
export interface AgentRunStatus {
  readonly id: string;
  readonly task_id: string;
  readonly phase: AgentRunPhaseName;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly finished_at: string | null;
  readonly stop_requested: boolean;
  readonly plan_sha256: string;
  /** The check the plan says would establish success. Recorded, never run. */
  readonly test_condition: string;
  /** The machine-checkable conditions the plan recorded beside that sentence,
   * each one a member of the closed acceptance registry, and each one
   * re-decided over the workspace as it stands right now. */
  readonly acceptance: readonly AgentAcceptanceConditionStatus[];
  /** What those conditions establish. `not_implemented` when the plan
   * recorded none - which is what a run that produced files and was never
   * checked has earned, and which keeps the publication gate closed. */
  readonly test_result_state: AgentTestResultStateName;
  readonly test_result_detail: string;
  readonly expected_artifacts: readonly string[];
  readonly steps: readonly AgentRunStepStatus[];
  readonly tool_calls_used: number;
  readonly elapsed_ms: number;
  readonly max_tool_calls: number;
  readonly max_wall_clock_seconds: number;
  readonly concurrency: 1;
  readonly detail: string;
}

/** The whole agent surface, read-only. Contacts nobody and runs nothing. */
export interface AgentSurfaceResponse {
  readonly execution: AgentExecutionStatus;
  readonly ceiling: AgentCeilingStatus;
  readonly tools: readonly AgentToolStatus[];
  /** The conditions a plan may be judged by, published beside the tools for
   * the same reason the tools are published: a person approving a plan has to
   * be able to see what "it worked" was defined to mean, and a set they
   * cannot enumerate is a set they cannot check. */
  readonly acceptance_checks: readonly AgentAcceptanceCheckStatus[];
  readonly honesty: string;
  readonly stop_statement: string;
  /** Runs a restart left in `running`. Listed, never resumed (SI-224). */
  readonly interrupted_runs: readonly AgentRunStatus[];
  readonly resumed_any: false;
}

/** One task's runs and the files its workspace currently holds. */
export interface AgentTaskRunsResponse {
  readonly task: TaskStatusResponse;
  readonly runs: readonly AgentRunStatus[];
  readonly workspace_files: readonly AgentWorkspaceFileStatus[];
  readonly honesty: string;
}

// --- The model planning lane (ADR-0012) ------------------------------------
//
// The lane the mirror above said did not exist. It exists now, and the shape
// of what it may return is the whole guarantee: `outcome` is never `"ran"`
// and there is no such member, because the best a turn can do is record a
// plan that a person then has to approve and start by hand.

/**
 * How one model planning turn ended. Seven, and none of them means "it ran".
 *
 * They are separate members rather than a success flag because they carry
 * separate remedies: a recorded plan waiting for approval, a model that chose
 * to stop, an answer cut off at the output ceiling, a turn whose ending this
 * build could not read, a proposal naming something outside the registry, a
 * session at its turn ceiling, and a provider that failed or never answered.
 *
 * `truncated` and `inconclusive` are the two that used to be spelled
 * `finished`. A live turn came back `finish_reason: "length"` with the output
 * ceiling spent to the token - the model had been **cut off** before it could
 * name a tool - and the product reported that it had chosen to stop and then
 * closed the session, so the person could not ask again. Two claims, neither
 * measured. They are their own members now, and only `finished` means the
 * model chose to stop.
 */
export type ModelProposalOutcomeName =
  | "planned"
  | "finished"
  | "truncated"
  | "inconclusive"
  | "refused"
  | "budget_exhausted"
  | "provider_failed";

/** What one turn produced, plus the task and its runs as they now stand. */
export interface ModelProposalResponse {
  readonly outcome: ModelProposalOutcomeName;
  /** The run this turn recorded a plan for, or "" when it recorded none. */
  readonly run_id: string;
  readonly detail: string;
  /** Turns spent by this task's session, against the compile-time ceiling. */
  readonly model_calls_used: number;
  readonly max_model_calls: number;
  /** What the **provider** reported it counted and charged, in its own
   * numbers. Recorded and shown; never read as a limit, and never presented
   * as this station's own measurement (ADR-0008 4, SI-250). */
  readonly usage_detail: string;
  /** The model's closing words when it stopped proposing calls. Swept and
   * bounded, shown once, stored nowhere. There is no reasoning trace here:
   * `reasoning_content` is read, unused, unstored and undisplayed
   * (ADR-0012 1). */
  readonly closing_text: string;
  /** The provenance of the tool-call wire format: measured, on which
   * endpoint, and how far the measurement reaches. Rendered verbatim. */
  readonly tool_call_provenance: string;
  readonly task: TaskStatusResponse;
  readonly runs: readonly AgentRunStatus[];
  /** Structural. A proposal is a recorded plan; starting it is a separate
   * request a person makes, and there is no code path from the planner to the
   * runner's start. */
  readonly model_can_start_a_run: false;
}

/** One timeline row. No reasoning trace, no prompt, no provider payload. */
export interface ActivityEventStatus {
  readonly id: string;
  readonly recorded_at: string;
  readonly run_id: string;
  readonly task_id: string;
  readonly actor: ActivityActorName;
  readonly action: ActivityActionName;
  readonly outcome: ActivityOutcomeName;
  readonly duration_ms: number;
  readonly artifact_sha256: string;
  readonly check_sha256: string;
  readonly detail: string;
  /** True when an audit link names this row. Those rows are never pruned
   * and never deleted, which is what lets the timeline have a retention
   * policy while the chain keeps not having one. */
  readonly chain_referenced: boolean;
}

export interface ActivityListResponse {
  readonly events: readonly ActivityEventStatus[];
  readonly event_count: number;
  readonly chain_referenced_count: number;
  readonly retained_events: number;
  readonly detail: string;
}

/** What a deletion did, as two counts that are never summed. */
export interface ActivityDeleteResponse {
  readonly deleted: number;
  readonly kept_because_chain_referenced: number;
  /** The deletion is itself an audit event (ADR-0008 6). */
  readonly recorded_in_audit_chain: true;
  readonly detail: string;
}

// --- The proof workspace (Paket H3) ----------------------------------------
//
// Hand-written mirrors of the `Proof*` models in `station_api/schemas.py`.
// The holes are copied on purpose, because here the holes are the whole
// subject (ADR-0009):
//
// * `ProofClaimState` is `"not_implemented"` as a **type**, not as one value
//   of a wider union. A surface that started reporting an independent check
//   as `passed` is a compile error rather than a screen somebody has to
//   notice (ADR-0009 6, 7);
// * there is **no score, no percentage and no completeness field**. What is
//   missing arrives as a list of named items with their own states, and
//   nothing in this file can sum them;
// * `hash_scope` and `bundle_scope` come **from the server**. They are not
//   composed here, because two surfaces writing the same disclaimer
//   independently is how the two eventually stop saying the same thing - the
//   rule `AuditChainStatus.claim` already follows;
// * a share request carries a **format and a token**, and no path, no
//   filename and no directory. The bundle is handed to the browser; there is
//   no server-side destination to name (ADR-0009 3);
// * a public-share request carries an **evidence record identity** and
//   nothing else. There is no room, no address and no text, so no shape in
//   this file can reach an outbound client (ADR-0009 11);
// * there is no field for a model's opinion of the work. The model lane is
//   closed and the bundle has no column for one (ADR-0008 2).

/**
 * One module requirement and its verdict.
 *
 * `not_implemented` is a distinct value from `blocked` for the reason the
 * write gate keeps them apart: an unbuilt requirement is not a user error, and
 * `policy_refused` separates "nobody has written this yet" from "this product
 * will not do it" - which read identically in a status column and are not the
 * same finding.
 */
export interface ModuleCheckStatus {
  readonly key: string;
  readonly state: TaskCheckState;
  readonly detail: string;
  readonly evidence_field: TaskEvidenceFieldName;
  readonly stage: string;
  readonly ref_id: string;
  readonly policy_refused: boolean;
}

/** One record from the compile-time module registry. */
export interface ProjectModuleStatus {
  readonly id: string;
  readonly name: string;
  readonly purpose: string;
  readonly state: "available" | "planned";
  readonly available_from: string;
  readonly owners: readonly string[];
  readonly checks: readonly ModuleCheckStatus[];
  /** Derived from the checks, never stored. False while any is unbuilt. */
  readonly complete: boolean;
  readonly blocking_keys: readonly string[];
  readonly not_implemented_keys: readonly string[];
}

/** The two formats a bundle is produced in. A closed set. */
export type ProofBundleFormat = "json" | "markdown";

/**
 * The only state the unproduced claims can be in.
 *
 * Written as a single-value literal, mirroring `ProofClaimStateName`. This is
 * the type that stops "bagimsiz kontrol" from ever rendering as a green tick.
 */
export type ProofClaimState = "not_implemented";

/** One file in the task workspace, with its own digest. Never its path. */
export interface ProofArtifactStatus {
  readonly name: string;
  readonly byte_count: number;
  /** 64 hex characters. Rendered through `shortDigest`, never whole. */
  readonly sha256: string;
}

/** A record this build does not produce, and the reason it does not. */
export interface ProofClaimStatus {
  readonly key: string;
  readonly state: ProofClaimState;
  readonly detail: string;
}

/** One named gap. Never summed, never turned into a badge. */
export interface ProofMissingStatus {
  readonly key: string;
  readonly state: string;
  readonly detail: string;
}

/** Everything a person needs in order to judge one task's proof. */
export interface ProofWorkspace {
  readonly task: TaskStatusResponse;
  readonly module: ProjectModuleStatus;
  readonly artifacts: readonly ProofArtifactStatus[];
  readonly file_count: number;
  readonly total_bytes: number;
  /** The digest over the produced set, as the run itself recorded it. */
  readonly artifact_set_sha256: string;
  /** The digest an approval and an acceptance are both bound to. */
  readonly bundle_sha256: string;
  readonly missing: readonly ProofMissingStatus[];
  readonly claims: readonly ProofClaimStatus[];
  readonly formats: readonly ProofBundleFormat[];
  /** What a SHA-256 does and does not establish. Rendered verbatim. */
  readonly hash_scope: string;
  readonly bundle_scope: string;
  readonly reproduction: string;
  readonly approval_ttl_seconds: number;
}

/**
 * The bundle as it stands, plus one single-use approval to deliver it.
 *
 * `share_token` is a capability the way `send_token` is: it turns "I have read
 * this bundle" into "hand me the file". Single-use, expiring, and bound to the
 * bundle digest, the task, the content version and this browser session. A
 * refused delivery spends it too (ADR-0009 4).
 */
export interface ProofPrepareResult {
  readonly workspace: ProofWorkspace;
  readonly share_token: string;
  readonly expires_in_seconds: number;
}
