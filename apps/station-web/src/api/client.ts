/**
 * The only place this app talks to the backend.
 *
 * Two rules hold here and are worth stating plainly:
 *
 * 1. Every URL is **relative**. The SPA is served from the same origin as the
 *    API, so it never needs to know the port. No backend port is compiled
 *    into the bundle (SI-37).
 * 2. The CSRF value lives in a module variable and nowhere else. It is never
 *    written to localStorage, sessionStorage or IndexedDB (SI-24), and it is
 *    never logged.
 */

import type {
  AppStatus,
  ConformanceStatus,
  IdentityStatus,
  ProtectionMode,
  RecoveryInspectResult,
  SessionBootstrap,
} from "./types";

const DEFAULT_CSRF_HEADER = "X-Station-CSRF";

// Memory only. Cleared when the page unloads, exactly like the server session.
let csrfToken: string | null = null;
let csrfHeader: string = DEFAULT_CSRF_HEADER;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    // Same-origin only: the cookie must never ride along to another origin.
    credentials: "same-origin",
    headers: { Accept: "application/json", ...init?.headers },
  });

  if (!response.ok) {
    // Surface the backend's own message so the user sees why, in Turkish.
    throw new ApiError(response.status, await readErrorDetail(response));
  }

  return (await response.json()) as T;
}

/** Exchange the session cookie for this session's CSRF value. */
export async function bootstrapSession(): Promise<void> {
  const data = await request<SessionBootstrap>("/api/session/bootstrap");
  csrfToken = data.csrf_token;
  csrfHeader = data.csrf_header || DEFAULT_CSRF_HEADER;
}

export function hasCsrfToken(): boolean {
  return csrfToken !== null;
}

/** Test helper: forget the in-memory session state. */
export function resetSessionState(): void {
  csrfToken = null;
  csrfHeader = DEFAULT_CSRF_HEADER;
}

export async function fetchAppStatus(): Promise<AppStatus> {
  return request<AppStatus>("/api/app/status");
}

/**
 * The single chokepoint for state-changing requests.
 *
 * Stage 1 exposes no such endpoint yet, but every future write goes through
 * here so the CSRF header can never be forgotten at a call site.
 */
export async function mutate<T>(path: string, body: unknown): Promise<T> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
  });
}

/** Multipart POST. Used only to send an already-encrypted .tcrec file. */
async function mutateForm<T>(path: string, form: FormData): Promise<T> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }
  // Content-Type is intentionally omitted: the browser must set the multipart
  // boundary itself.
  return request<T>(path, { method: "POST", body: form, headers: { [csrfHeader]: csrfToken } });
}

// --- Identity and recovery -------------------------------------------------

export async function fetchIdentity(): Promise<IdentityStatus> {
  return request<IdentityStatus>("/api/identity");
}

/**
 * The runtime conformance verdict.
 *
 * Read-only and public: check names, vector counts and the pinned reference,
 * package, Python and Unicode versions. No vectors and no key material cross
 * this boundary.
 */
export async function fetchConformance(): Promise<ConformanceStatus> {
  return request<ConformanceStatus>("/api/conformance/status");
}

export interface CreateIdentityInput {
  readonly protection: ProtectionMode;
  readonly passphrase: string | null;
  readonly passphraseConfirm: string | null;
  readonly label: string;
  readonly confirmation: string;
  readonly acceptDpapiOnlyRisk: boolean;
}

export async function createIdentity(input: CreateIdentityInput): Promise<IdentityStatus> {
  return mutate<IdentityStatus>("/api/identity", {
    protection: input.protection,
    passphrase: input.passphrase,
    passphrase_confirm: input.passphraseConfirm,
    label: input.label,
    confirmation: input.confirmation,
    accept_dpapi_only_risk: input.acceptDpapiOnlyRisk,
  });
}

/**
 * Download the encrypted recovery file.
 *
 * The response body is ciphertext. It is handed straight to a temporary
 * object URL, which is revoked immediately after the click so the blob does
 * not linger in memory or in the document.
 */
export async function exportRecovery(input: {
  readonly recoveryPassphrase: string;
  readonly recoveryPassphraseConfirm: string;
  readonly vaultPassphrase: string | null;
}): Promise<{ blob: Blob; filename: string }> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }

  const response = await fetch("/api/identity/recovery/export", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
    body: JSON.stringify({
      recovery_passphrase: input.recoveryPassphrase,
      recovery_passphrase_confirm: input.recoveryPassphraseConfirm,
      vault_passphrase: input.vaultPassphrase,
    }),
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response));
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  return { blob: await response.blob(), filename: match?.[1] ?? "technocore-station.tcrec" };
}

export async function verifyRecovery(
  file: File,
  recoveryPassphrase: string,
): Promise<IdentityStatus> {
  const form = new FormData();
  form.append("recovery_file", file);
  form.append("recovery_passphrase", recoveryPassphrase);
  return mutateForm<IdentityStatus>("/api/identity/recovery/verify", form);
}

export async function inspectRecovery(
  file: File,
  recoveryPassphrase: string,
): Promise<RecoveryInspectResult> {
  const form = new FormData();
  form.append("recovery_file", file);
  form.append("recovery_passphrase", recoveryPassphrase);
  return mutateForm<RecoveryInspectResult>("/api/identity/recovery/inspect", form);
}

export async function adoptRecovery(input: {
  readonly file: File;
  readonly recoveryPassphrase: string;
  readonly protection: ProtectionMode;
  readonly vaultPassphrase: string | null;
  readonly confirmDid: string;
  readonly label: string;
}): Promise<IdentityStatus> {
  const form = new FormData();
  form.append("recovery_file", input.file);
  form.append("recovery_passphrase", input.recoveryPassphrase);
  form.append("protection", input.protection);
  form.append("confirm_did", input.confirmDid);
  form.append("label", input.label);
  if (input.vaultPassphrase !== null) {
    form.append("vault_passphrase", input.vaultPassphrase);
  }
  return mutateForm<IdentityStatus>("/api/identity/recovery/adopt", form);
}

export async function revokeIdentity(confirmDid: string): Promise<IdentityStatus> {
  return mutate<IdentityStatus>("/api/identity/revoke", { confirm_did: confirmDid });
}

/** Pull the backend's Turkish message out of an error response, if present. */
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const { detail } = body;
      if (typeof detail === "string") {
        return detail;
      }
    }
  } catch {
    // Fall through to the generic message below.
  }
  return `request_failed_${response.status}`;
}
