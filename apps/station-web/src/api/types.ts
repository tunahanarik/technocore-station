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

export interface TechnocoreStatus {
  readonly state: "not_connected";
  readonly available_from_stage: number;
  readonly detail: string;
}

export interface AppStatus {
  readonly service: ServiceStatus;
  readonly database: DatabaseStatus;
  readonly session_security: SessionSecurityStatus;
  readonly technocore: TechnocoreStatus;
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
