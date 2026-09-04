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
