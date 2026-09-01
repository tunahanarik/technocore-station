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
