/**
 * The only place this app talks to the backend.
 *
 * Three rules hold here and are worth stating plainly:
 *
 * 1. Every URL is **relative**. The SPA is served from the same origin as the
 *    API, so it never needs to know the port. No backend port is compiled
 *    into the bundle (SI-37).
 * 2. The CSRF value lives in a module variable and nowhere else. It is never
 *    written to any browser storage (SI-24), and it is never logged.
 * 3. Every request has a deadline and every failure is classified. A page
 *    never has to guess whether "it broke" means the service is down, the
 *    response was garbage or the session expired; `ApiError` says which.
 */

import type {
  AppStatus,
  ConformanceStatus,
  IdentityStatus,
  ProtectionMode,
  RecoveryInspectResult,
  SessionBootstrap,
  TechnocoreStatus,
  WriteGateStatus,
} from "./types";

const DEFAULT_CSRF_HEADER = "X-Station-CSRF";

/** Every request is abandoned after this long unless stated otherwise. */
export const DEFAULT_TIMEOUT_MS = 15000;

/**
 * The official-source check fans out to several remote documents server-side,
 * so it gets a longer leash than a local read.
 */
export const REFRESH_TIMEOUT_MS = 30000;

// Memory only. Cleared when the page unloads, exactly like the server session.
let csrfToken: string | null = null;
let csrfHeader: string = DEFAULT_CSRF_HEADER;

/**
 * How a request failed, as one of eight stable classes.
 *
 * "malformed" and "network" are deliberately distinct: a response that
 * arrived but could not be parsed is not the same finding as a connection
 * that dropped, and merging them sends whoever is debugging to the wrong
 * layer.
 */
export type ApiErrorKind =
  | "timeout"
  | "network"
  | "malformed"
  | "auth"
  | "rate_limited"
  | "unavailable"
  | "server"
  | "request";

/** Machine codes look like `not_found`; anything else is prose for humans. */
const MACHINE_CODE_RE = /^[a-z0-9_]+$/;

/** The backend request id is 32 hex characters; anything else is noise. */
const REQUEST_ID_RE = /^[0-9a-f]{32}$/i;

/** Safe Turkish fallbacks, keyed by failure class. */
const KIND_MESSAGES: Record<ApiErrorKind, string> = {
  timeout: "Istek zaman asimina ugradi. Yerel servis zamaninda yanit vermedi.",
  network: "Yerel servise baglanilamadi.",
  malformed: "Yerel servisten beklenmeyen bicimde bir yanit geldi.",
  auth: "Oturum dogrulanamadi. Uygulamayi launcher uzerinden yeniden acin.",
  rate_limited: "Cok fazla istek gonderildi. Kisa bir sure bekleyip yeniden deneyin.",
  unavailable: "Servis su anda kullanilamiyor. Yerel servisin calistigini kontrol edin.",
  server: "Yerel serviste beklenmeyen bir hata olustu.",
  request: "Istek tamamlanamadi.",
};

const RETRYABLE_KINDS: ReadonlySet<ApiErrorKind> = new Set([
  "timeout",
  "network",
  "rate_limited",
  "unavailable",
  "server",
]);

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401 || status === 403) return "auth";
  if (status === 429) return "rate_limited";
  if (status === 503) return "unavailable";
  if (status >= 500) return "server";
  return "request";
}

export class ApiError extends Error {
  /** HTTP status, or 0 when no response arrived (timeout, network). */
  readonly status: number;
  /** Stable machine code: the backend's own code, or `http_<status>`. */
  readonly code: string;
  readonly kind: ApiErrorKind;
  /** `X-Station-Request-Id` of the failed response, if one arrived. */
  readonly requestId: string | null;
  /** Safe Turkish sentence for the user. Never a raw machine code. */
  readonly userMessage: string;
  /** Whether simply trying again is a sensible recovery. */
  readonly retryable: boolean;

  constructor(
    status: number,
    detail: string,
    options: { readonly kind?: ApiErrorKind; readonly requestId?: string | null } = {},
  ) {
    const kind = options.kind ?? kindForStatus(status);
    const machine = MACHINE_CODE_RE.test(detail);
    const userMessage = detail !== "" && !machine ? detail : KIND_MESSAGES[kind];
    super(detail !== "" ? detail : userMessage);
    this.name = "ApiError";
    this.status = status;
    this.code = machine ? detail : `http_${String(status)}`;
    this.kind = kind;
    this.requestId = options.requestId ?? null;
    this.userMessage = userMessage;
    this.retryable = RETRYABLE_KINDS.has(kind);
  }
}

/**
 * Normalise any caught value into an `ApiError` so error surfaces have one
 * shape to render. Client-side guard failures (an unbootstrapped session)
 * classify as `auth`: the recovery - reopen via the launcher - is the same.
 */
export function toApiError(caught: unknown): ApiError {
  if (caught instanceof ApiError) return caught;
  if (caught instanceof Error && caught.message === "session_not_bootstrapped") {
    return new ApiError(0, "session_not_bootstrapped", { kind: "auth" });
  }
  return new ApiError(0, "unexpected_error", { kind: "request" });
}

/** A fetch that threw instead of responding: deadline or connectivity. */
function classifyFetchFailure(caught: unknown): ApiError {
  if (
    caught instanceof DOMException &&
    (caught.name === "TimeoutError" || caught.name === "AbortError")
  ) {
    return new ApiError(0, "timeout", { kind: "timeout" });
  }
  // fetch rejects with TypeError on connection failure; anything else that
  // escapes it is equally "the bytes never arrived".
  return new ApiError(0, "network_error", { kind: "network" });
}

function readRequestId(response: Response): string | null {
  const value = response.headers.get("X-Station-Request-Id");
  return value !== null && REQUEST_ID_RE.test(value) ? value : null;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      // Same-origin only: the cookie must never ride along to another origin.
      credentials: "same-origin",
      signal: AbortSignal.timeout(timeoutMs),
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (caught) {
    throw classifyFetchFailure(caught);
  }

  const requestId = readRequestId(response);

  if (!response.ok) {
    // Surface the backend's own Turkish message so the user sees why.
    throw new ApiError(response.status, await readErrorDetail(response), { requestId });
  }

  try {
    return (await response.json()) as T;
  } catch {
    // The response arrived and claimed success but does not parse. That is a
    // different finding from a dropped connection and is reported as such.
    throw new ApiError(response.status, "malformed_response", { kind: "malformed", requestId });
  }
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
 * The single chokepoint for state-changing requests: every write goes through
 * here so the CSRF header can never be forgotten at a call site.
 */
export async function mutate<T>(
  path: string,
  body: unknown,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }
  return request<T>(
    path,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
    },
    timeoutMs,
  );
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
 * The write gate on its own, without the rest of the identity payload.
 * Read-only; used by the settings surface to show why outward writing is
 * open or closed.
 */
export async function fetchWriteGate(): Promise<WriteGateStatus> {
  return request<WriteGateStatus>("/api/write-gate");
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

/**
 * The read-only Technocore verdict. Reading it makes no outbound request:
 * it reports what the last user-initiated check found, or that none has run.
 */
export async function fetchTechnocore(): Promise<TechnocoreStatus> {
  return request<TechnocoreStatus>("/api/technocore/status");
}

/**
 * Run the read-only check. This is the one call that reaches the public
 * internet, so it goes through the CSRF chokepoint and carries no body:
 * the backend runs a fixed source registry and there is nothing to steer.
 */
export async function refreshTechnocore(): Promise<TechnocoreStatus> {
  return mutate<TechnocoreStatus>("/api/technocore/refresh", {}, REFRESH_TIMEOUT_MS);
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

  let response: Response;
  try {
    response = await fetch("/api/identity/recovery/export", {
      method: "POST",
      credentials: "same-origin",
      signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
      body: JSON.stringify({
        recovery_passphrase: input.recoveryPassphrase,
        recovery_passphrase_confirm: input.recoveryPassphraseConfirm,
        vault_passphrase: input.vaultPassphrase,
      }),
    });
  } catch (caught) {
    throw classifyFetchFailure(caught);
  }

  const requestId = readRequestId(response);

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response), { requestId });
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  try {
    return { blob: await response.blob(), filename: match?.[1] ?? "technocore-station.tcrec" };
  } catch {
    throw new ApiError(response.status, "malformed_response", { kind: "malformed", requestId });
  }
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

/**
 * Pull the backend's Turkish message out of an error response, if present.
 * Returns "" when there is none; the `ApiError` constructor then falls back
 * to the safe catalogue text for the failure class.
 */
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
    // No parseable body; fall through to the catalogue fallback.
  }
  return "";
}
