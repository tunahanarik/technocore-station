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

/** The three families, and the two formats deliberately not built. */
export interface OpenCodeProtocolContext {
  readonly protocols: readonly string[];
  readonly streaming_supported: false;
  readonly tool_calls_supported: false;
  readonly deferral: string;
  readonly shape_provenance: string;
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

/** One room as the overview listed it. Both fields are caller-written. */
export interface WorkScanRoom {
  readonly name: string;
  readonly topic: string;
  readonly authority: 3;
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
  readonly public_share_available: false;
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
export type AgentToolParamTypeName = "text" | "file_name" | "digest" | "json_text";

/** What the measurement established. `not_measured` is not `absent`. */
export type AgentIsolationStateName = "present" | "absent" | "not_measured";

/** Who acted. There is no `model` actor, because there is no model lane. */
export type ActivityActorName = "user" | "station_runner";

export type ActivityOutcomeName = "ok" | "refused" | "failed" | "pending";

/**
 * The kinds of moment the timeline distinguishes.
 *
 * Fourteen values rather than one `step_done`: "planned", "a tool was
 * called", "an artifact was produced", "a check was recorded" and "waiting
 * for approval" answer different questions, and a timeline that folded them
 * into one badge could no longer say whether anything was actually checked
 * (ADR-0008 6).
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
  | "activity_deleted";

export interface AgentToolParamStatus {
  readonly name: string;
  readonly type: AgentToolParamTypeName;
  readonly required: boolean;
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
  /** `not_implemented` as a type: a run that produced files has still not
   * been tested, and the task cannot become `ready_to_publish` (SI-222). */
  readonly test_result_state: "not_implemented";
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
