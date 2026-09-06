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

import {
  type ResponseValidator,
  isActivityDeleteResponse,
  isActivityListResponse,
  isAgentSurfaceResponse,
  isAgentTaskRunsResponse,
  isAppStatus,
  isAuditChainStatus,
  isComposeCapability,
  isComposeDraft,
  isComposeSendResult,
  isComposeSignature,
  isConformanceStatus,
  isEvidenceCaptureResult,
  isEvidenceList,
  isIdentityStatus,
  isModelProposalResponse,
  isOpenCodeStatus,
  isProofPrepareResult,
  isProofWorkspace,
  isRecoveryInspectResult,
  isSessionBootstrap,
  isTaskListResponse,
  isTaskStatusResponse,
  isTechnocoreStatus,
  isWorkScanStatus,
  isWorkScanSuggestion,
  isWriteGateStatus,
} from "./response-validation";
import type {
  ActivityDeleteResponse,
  ActivityListResponse,
  AgentAcceptanceKindName,
  AgentSurfaceResponse,
  AgentTaskRunsResponse,
  AppStatus,
  AuditChainStatus,
  ComposeCapability,
  ComposeDraft,
  ComposeSendResult,
  ComposeSignature,
  ConformanceStatus,
  EvidenceCaptureResult,
  EvidenceExportFormat,
  EvidenceList,
  IdentityStatus,
  ModelProposalResponse,
  OpenCodeStatus,
  ProofBundleFormat,
  ProofPrepareResult,
  ProofWorkspace,
  ProtectionMode,
  RecoveryInspectResult,
  TaskListResponse,
  TaskStatusResponse,
  TaskUserTransitionName,
  TechnocoreStatus,
  WorkScanStatus,
  WorkScanSuggestion,
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

/**
 * Signing opens the secret vault, and a passphrase-protected vault costs an
 * Argon2id derivation before a single byte is signed. The default deadline is
 * sized for a local read, not for a deliberate KDF.
 */
export const SIGN_TIMEOUT_MS = 30000;

/**
 * The one outbound write, and the longest deadline in the app.
 *
 * The backend's own write budget is connect 5s + write 10s + read 15s, so a
 * single attempt can legitimately take about thirty seconds before the server
 * decides which of the three outcomes it saw. A client deadline shorter than
 * that would abandon the request *while the server is still writing* and
 * report `timeout` - a claim about the local service - instead of the honest
 * `outcome_unknown` the backend was about to return. The extra headroom keeps
 * the server's three-valued verdict, not our stopwatch, as the answer.
 */
export const SEND_TIMEOUT_MS = 45000;

/**
 * One read-only evidence capture, and the longest deadline in the app.
 *
 * A capture is not a local read: the backend opens the room's official export
 * and scans it line by line, under a 12 MiB ceiling (10 MiB ring plus header
 * headroom). Its own transport budget is connect 5s + read 30s, but that read
 * timeout applies **per chunk**, not to the whole scan - so a slow link
 * delivering megabytes can legitimately keep the route busy far longer than
 * thirty seconds while never once stalling for thirty.
 *
 * Ninety seconds is chosen to sit above that realistic scan and still bound
 * the UI. Cutting it shorter would abandon a scan that was making progress and
 * report `timeout` - a claim about the local service - instead of letting the
 * backend name which of the six capture states it actually reached. That
 * matters more here than elsewhere: the whole point of the six states is that
 * "we could not finish reading" is a different finding from "the line is not
 * there", and a client stopwatch must not collapse the two.
 */
export const CAPTURE_TIMEOUT_MS = 90000;

/**
 * Storing the OpenCode provider key. The one request in this app whose body
 * carries a provider secret, and the only reason it has its own deadline.
 *
 * It reaches **nobody**: the route writes a DPAPI envelope to local disk -
 * mkstemp, fsync, ACL, atomic replace, ACL again - and then reads back local
 * state. So a network-sized budget is wrong in both directions, and the
 * default 15s is sized for a local *read*, not for a blocking route that
 * queues in the server threadpool behind other blocking work and then waits
 * on two Windows ACL calls and an fsync.
 *
 * Twenty seconds is chosen because the failure mode of a short deadline is
 * uniquely expensive here. Abandoning a write mid-replace reports `timeout` -
 * a claim about the local service - while the envelope may well have landed,
 * and the only way for the user to find out is to **type the secret again**.
 * Every other request in this app can be retried for free; this one cannot.
 */
export const CREDENTIAL_TIMEOUT_MS = 20000;

/**
 * Refreshing the public model catalog, and the longest deadline in the app.
 *
 * The server's own budget is two bounded attempts, each connect 5s + read
 * 30s, with a capped 5s backoff between them: about 75 seconds before it can
 * honestly say `fetch_error`. A client deadline below that would abandon a
 * refresh the server was still making progress on and report `timeout`, which
 * is a claim about the *local* service - and it would throw away the catalog
 * state the server was about to return, which is the actual answer the user
 * asked for. Ninety seconds sits above the server budget and still bounds
 * the UI.
 *
 * The catalog request carries **no credential**: the provider's list answers
 * unauthenticated, which is exactly why fetching it proves nothing about the
 * stored key (ADR-0005 4).
 */
export const CATALOG_TIMEOUT_MS = 90000;

// Memory only. Cleared when the page unloads, exactly like the server session.
let csrfToken: string | null = null;
let csrfHeader: string = DEFAULT_CSRF_HEADER;

/**
 * How a request failed, as one of nine stable classes.
 *
 * "malformed" and "network" are deliberately distinct: a response that
 * arrived but could not be parsed is not the same finding as a connection
 * that dropped, and merging them sends whoever is debugging to the wrong
 * layer.
 *
 * "timeout" and "canceled" are distinct for the same reason. A timeout is a
 * claim about the service - it did not answer inside our deadline - and it is
 * only true when our own `AbortSignal.timeout` actually fired. An abort that
 * came from anywhere else (the document going away mid-request, or a cancel
 * control if one is ever added) says nothing about the service, and reporting
 * it as "the local service was too slow" would be a fabricated finding.
 */
export type ApiErrorKind =
  | "timeout"
  | "canceled"
  | "network"
  | "malformed"
  | "auth"
  | "rate_limited"
  | "unavailable"
  | "server"
  | "request";

/** Machine codes look like `not_found`; anything else is prose for humans. */
const MACHINE_CODE_RE = /^[a-z0-9_]+$/;

/**
 * The backend request id is 32 lower-case hex characters.
 *
 * Case-sensitive on purpose: the server writes `uuid4().hex`, which is always
 * lower case. Accepting upper case would quietly widen the documented shape
 * and let a header from somewhere else pass as ours.
 */
const REQUEST_ID_RE = /^[0-9a-f]{32}$/;

/** Safe Turkish fallbacks, keyed by failure class. */
const KIND_MESSAGES: Record<ApiErrorKind, string> = {
  timeout: "Istek zaman asimina ugradi. Yerel servis zamaninda yanit vermedi.",
  canceled: "Istek tamamlanmadan durduruldu.",
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
  "canceled",
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

/** Did *our* deadline fire, or did something else abort the request? */
function deadlineExpired(deadline: AbortSignal): boolean {
  if (!deadline.aborted) return false;
  const reason: unknown = deadline.reason;
  return reason instanceof DOMException && reason.name === "TimeoutError";
}

/**
 * A fetch that threw instead of responding: deadline, cancellation or
 * connectivity.
 *
 * The abort branch checks the signal we passed rather than trusting the name
 * on the rejection. `TimeoutError` is only ever produced by a timeout signal,
 * so it is conclusive; a bare `AbortError` is not, and is a timeout only when
 * our own deadline is the signal that fired. Anything else that aborted the
 * request is reported as `canceled`, which claims nothing about the service.
 */
function classifyFetchFailure(caught: unknown, deadline: AbortSignal): ApiError {
  if (caught instanceof DOMException) {
    if (caught.name === "TimeoutError") {
      return new ApiError(0, "timeout", { kind: "timeout" });
    }
    if (caught.name === "AbortError") {
      return deadlineExpired(deadline)
        ? new ApiError(0, "timeout", { kind: "timeout" })
        : new ApiError(0, "request_canceled", { kind: "canceled" });
    }
  }
  // fetch rejects with TypeError on connection failure; anything else that
  // escapes it is equally "the bytes never arrived".
  return new ApiError(0, "network_error", { kind: "network" });
}

function readRequestId(response: Response): string | null {
  const value = response.headers.get("X-Station-Request-Id");
  return value !== null && REQUEST_ID_RE.test(value) ? value : null;
}

/**
 * One request, one deadline, one validated document.
 *
 * `validate` is a **required parameter**, and that is the whole mechanism: a
 * new endpoint cannot be added without saying what its response must look
 * like, because the call site does not compile until it does. The previous
 * shape - a single `if (path === "/api/app/status")` guard - checked one URL
 * and returned `data as T` for every other one, so a 200 carrying `{}` was
 * accepted everywhere else and only failed later, inside a component, as a
 * `TypeError` on a nested field.
 */
async function request<T>(
  path: string,
  validate: ResponseValidator<T>,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  // Held in a variable so a failure can ask whether *this* deadline fired.
  const deadline = AbortSignal.timeout(timeoutMs);
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      // Same-origin only: the cookie must never ride along to another origin.
      credentials: "same-origin",
      signal: deadline,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (caught) {
    throw classifyFetchFailure(caught, deadline);
  }

  const requestId = readRequestId(response);

  if (!response.ok) {
    // Surface the backend's own Turkish message so the user sees why.
    throw new ApiError(response.status, await readErrorDetail(response), { requestId });
  }

  try {
    const data: unknown = await response.json();
    // Every endpoint, not one of them. The check descends into nested objects
    // and list elements, so a body that is the right shape only at the top
    // level is refused here rather than crashing a screen later.
    if (!validate(data)) throw new Error("invalid_document_shape");
    return data;
  } catch (caught) {
    if (caught instanceof DOMException &&
        (caught.name === "TimeoutError" || caught.name === "AbortError")) {
      throw classifyFetchFailure(caught, deadline);
    }
    // The response arrived and claimed success but does not parse. That is a
    // different finding from a dropped connection and is reported as such.
    throw new ApiError(response.status, "malformed_response", { kind: "malformed", requestId });
  }
}

/** Exchange the session cookie for this session's CSRF value. */
export async function bootstrapSession(): Promise<void> {
  const data = await request("/api/session/bootstrap", isSessionBootstrap);
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
  return request("/api/app/status", isAppStatus);
}

/**
 * The single chokepoint for state-changing requests: every write goes through
 * here so the CSRF header can never be forgotten at a call site.
 */
export async function mutate<T>(
  path: string,
  validate: ResponseValidator<T>,
  body: unknown,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }
  return request(
    path,
    validate,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
    },
    timeoutMs,
  );
}

/** Multipart POST. Used only to send an already-encrypted .tcrec file. */
async function mutateForm<T>(
  path: string,
  validate: ResponseValidator<T>,
  form: FormData,
): Promise<T> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }
  // Content-Type is intentionally omitted: the browser must set the multipart
  // boundary itself.
  return request(path, validate, {
    method: "POST",
    body: form,
    headers: { [csrfHeader]: csrfToken },
  });
}

// --- Identity and recovery -------------------------------------------------

export async function fetchIdentity(): Promise<IdentityStatus> {
  return request("/api/identity", isIdentityStatus);
}

/**
 * The write gate on its own, without the rest of the identity payload.
 * Read-only; used by the settings surface to show why outward writing is
 * open or closed.
 */
export async function fetchWriteGate(): Promise<WriteGateStatus> {
  return request("/api/write-gate", isWriteGateStatus);
}

/**
 * The runtime conformance verdict.
 *
 * Read-only and public: check names, vector counts and the pinned reference,
 * package, Python and Unicode versions. No vectors and no key material cross
 * this boundary.
 */
export async function fetchConformance(): Promise<ConformanceStatus> {
  return request("/api/conformance/status", isConformanceStatus);
}

/**
 * The read-only Technocore verdict. Reading it makes no outbound request:
 * it reports what the last user-initiated check found, or that none has run.
 */
export async function fetchTechnocore(): Promise<TechnocoreStatus> {
  return request("/api/technocore/status", isTechnocoreStatus);
}

/**
 * Run the read-only check. This is the one call that reaches the public
 * internet, so it goes through the CSRF chokepoint and carries no body:
 * the backend runs a fixed source registry and there is nothing to steer.
 */
export async function refreshTechnocore(): Promise<TechnocoreStatus> {
  return mutate("/api/technocore/refresh", isTechnocoreStatus, {}, REFRESH_TIMEOUT_MS);
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
  return mutate("/api/identity", isIdentityStatus, {
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

  const deadline = AbortSignal.timeout(DEFAULT_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch("/api/identity/recovery/export", {
      method: "POST",
      credentials: "same-origin",
      signal: deadline,
      headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
      body: JSON.stringify({
        recovery_passphrase: input.recoveryPassphrase,
        recovery_passphrase_confirm: input.recoveryPassphraseConfirm,
        vault_passphrase: input.vaultPassphrase,
      }),
    });
  } catch (caught) {
    throw classifyFetchFailure(caught, deadline);
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
  return mutateForm("/api/identity/recovery/verify", isIdentityStatus, form);
}

export async function inspectRecovery(
  file: File,
  recoveryPassphrase: string,
): Promise<RecoveryInspectResult> {
  const form = new FormData();
  form.append("recovery_file", file);
  form.append("recovery_passphrase", recoveryPassphrase);
  return mutateForm("/api/identity/recovery/inspect", isRecoveryInspectResult, form);
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
  return mutateForm("/api/identity/recovery/adopt", isIdentityStatus, form);
}

export async function revokeIdentity(confirmDid: string): Promise<IdentityStatus> {
  return mutate("/api/identity/revoke", isIdentityStatus, { confirm_did: confirmDid });
}

// --- Composer (Paket D) ----------------------------------------------------
//
// Three steps, three requests, in that order and never fused: the whole point
// of the chain is that approving a signature is not approving a send
// (ADR-0002 2). There is deliberately no helper here that does two of them.

/**
 * What the composer can do right now, and what is blocking it.
 *
 * A read: it reaches nobody outside this machine. The disabled state of a
 * button is never the control that keeps the door shut - all three steps
 * re-run the same gate server-side - but the UI needs this to *explain* a
 * closed door instead of showing an inert form.
 */
export async function fetchComposeCapability(): Promise<ComposeCapability> {
  return request("/api/compose/capability", isComposeCapability);
}

/** Step 1: sweep and bind a digest. Reserves no nonce and signs nothing. */
export async function createComposeDraft(input: {
  readonly room: string;
  readonly text: string;
}): Promise<ComposeDraft> {
  return mutate("/api/compose/draft", isComposeDraft, {
    room: input.room,
    text: input.text,
  });
}

/**
 * Step 2: the explicit signing approval.
 *
 * `draftDigest` is echoed back so the server can refuse a digest that no
 * longer matches the draft - an old approval cannot sign new content.
 * The passphrase is passed straight through from component state and is never
 * stored, echoed or logged here.
 */
export async function signComposeDraft(input: {
  readonly draftId: string;
  readonly draftDigest: string;
  readonly vaultPassphrase: string | null;
}): Promise<ComposeSignature> {
  return mutate("/api/compose/sign", isComposeSignature,
    {
      draft_id: input.draftId,
      draft_digest: input.draftDigest,
      vault_passphrase: input.vaultPassphrase,
    },
    SIGN_TIMEOUT_MS,
  );
}

/**
 * Step 3: spend the approval and publish once.
 *
 * The token is the entire request body on purpose: everything else that
 * matters was bound to it at signing time, so there is nothing here a caller
 * could steer. There is no retry wrapper and there must never be one - the
 * nonce is spent whatever the outcome (ADR-0002 3).
 */
export async function sendComposeMessage(sendToken: string): Promise<ComposeSendResult> {
  return mutate("/api/compose/send", isComposeSendResult,
    { send_token: sendToken },
    SEND_TIMEOUT_MS,
  );
}

// --- Evidence and audit (Paket E) ------------------------------------------
//
// Four calls, and none of them can publish anything. `captureEvidenceLine` is
// a POST because it makes the backend reach outwards, not because it writes:
// the request body is one stored record id, the room comes from the row, and
// there is no parameter here - or in the route behind it - that could turn a
// capture into a second send (ADR-0003 4).

/** The archive plus the audit chain's verdict, in one read. */
export async function fetchEvidenceRecords(): Promise<EvidenceList> {
  return request("/api/evidence/records", isEvidenceList);
}

/**
 * Ask for one read-only capture of one record's exported line.
 *
 * On request only. Nothing in this app calls it on a timer, on mount or as a
 * step of a send, and the result is never reduced to a boolean by the caller:
 * the six states mean six different things (`docs/evidence-model.md` 3).
 */
export async function captureEvidenceLine(
  evidenceId: string,
): Promise<EvidenceCaptureResult> {
  return mutate("/api/evidence/capture", isEvidenceCaptureResult,
    { evidence_id: evidenceId },
    CAPTURE_TIMEOUT_MS,
  );
}

/** Recompute the chain and compare it against its separately held head. */
export async function fetchAuditChain(): Promise<AuditChainStatus> {
  return request("/api/evidence/audit", isAuditChainStatus);
}

/**
 * Download the evidence archive. Explicit consent is part of the request.
 *
 * `acknowledged` is passed through from the caller rather than defaulted here,
 * because a default in this function would be a way to export without consent
 * that type-checks. The backend refuses a body without it (422) and refuses a
 * `false` again in the handler; this is the third refusal, not the only one.
 *
 * The response is a file, so it cannot go through `request`. The server's
 * `Content-Disposition` name is deliberately **not** read back: the download
 * name is a client-side concern, the server already rebuilds its own from an
 * allow-list, and parsing a header to recover a name we can state ourselves
 * would only add a parser to be wrong about.
 */
export async function exportEvidence(input: {
  readonly format: EvidenceExportFormat;
  readonly acknowledged: boolean;
}): Promise<{ blob: Blob }> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }

  const deadline = AbortSignal.timeout(DEFAULT_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch("/api/evidence/export", {
      method: "POST",
      credentials: "same-origin",
      signal: deadline,
      headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
      body: JSON.stringify({ format: input.format, acknowledged: input.acknowledged }),
    });
  } catch (caught) {
    throw classifyFetchFailure(caught, deadline);
  }

  const requestId = readRequestId(response);

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response), { requestId });
  }

  try {
    return { blob: await response.blob() };
  } catch {
    throw new ApiError(response.status, "malformed_response", { kind: "malformed", requestId });
  }
}

// --- OpenCode Go connection (Paket G) --------------------------------------
//
// Five calls, and the shape of the set is the point. There is one way in for
// the provider key and **no way back out**: no read route, no masked echo, no
// "show for verification". After `storeOpenCodeCredential` returns, the only
// thing this app can learn about the key is a twelve-character fingerprint.
//
// There is also no completion call here. Sending a metered request belongs to
// the executor package, and a button for it on this surface would have made
// "Station never spends money on its own" a claim with a footnote.

/** The whole connection, read-only. Contacts nobody outside this machine. */
export async function fetchOpenCodeStatus(): Promise<OpenCodeStatus> {
  return request("/api/opencode/status", isOpenCodeStatus);
}

/**
 * Store the provider key. The one request in this app that carries one.
 *
 * The value is passed straight through from component state to the body and
 * is never copied, echoed, logged or held here. The caller wipes its own
 * state as soon as this resolves; this function keeps nothing, so there is
 * no second copy to forget about.
 *
 * The reply is the same status document every other call in this group
 * returns - so after storing a key the user is told it was **saved and not
 * verified**, from the same fields that would have said anything else.
 */
export async function storeOpenCodeCredential(apiKey: string): Promise<OpenCodeStatus> {
  return mutate("/api/opencode/credential", isOpenCodeStatus, { api_key: apiKey }, CREDENTIAL_TIMEOUT_MS);
}

/** Remove the stored key. Empty body: there is nothing here to steer. */
export async function forgetOpenCodeCredential(): Promise<OpenCodeStatus> {
  return mutate("/api/opencode/credential/forget", isOpenCodeStatus, {});
}

/**
 * Fetch the public model catalog, on the user's request only.
 *
 * Nothing calls this on mount, on a timer or as a step of anything else. The
 * body is empty because the address comes from the backend's closed endpoint
 * registry: there is no path from anything typed on this surface to an
 * outbound host.
 */
export async function refreshOpenCodeCatalog(): Promise<OpenCodeStatus> {
  return mutate("/api/opencode/catalog/refresh", isOpenCodeStatus, {}, CATALOG_TIMEOUT_MS);
}

/**
 * Choose a model, or be refused with a reason.
 *
 * `trainingAcknowledged` is passed through from the caller rather than
 * defaulted here: a default in this function would be a way to accept a
 * data-sharing term the user never saw, and it would type-check. The backend
 * defaults it to `false` and refuses again on its own side.
 *
 * There is no fallback parameter and there must never be one. A model that
 * cannot be addressed is a refusal naming the reason, never a quiet
 * substitution of some other model (ADR-0005 11).
 */
export async function selectOpenCodeModel(input: {
  readonly modelId: string;
  readonly trainingAcknowledged: boolean;
}): Promise<OpenCodeStatus> {
  return mutate("/api/opencode/model", isOpenCodeStatus, {
    model_id: input.modelId,
    training_acknowledged: input.trainingAcknowledged,
  });
}

// --- Public-room work scan (Paket H1) --------------------------------------
//
// Five calls, and the shape of the set is the point.
//
// * **Nothing here is called on a timer.** No interval, no background task
//   and no `wait` parameter. There *is* now a cursor - the discovery log's
//   `since` - and it is a parameter of a call rather than a value this module
//   keeps: it comes from the caller on the press that uses it, so continuing
//   the log is a user action and not the second half of a loop.
//   `fetchWorkScanStatus` runs once on mount and contacts nobody; the other
//   four run only inside a click (ADR-0007 4).
// * **The scope is the caller's room list.** There is no scan-everything
//   call and no endpoint behind one. `scanWorkRooms` sends the rooms it was
//   given and nothing about an address.
// * **`suggestWorkScanCandidate` approves nothing.** It opens a local task in
//   `suggested`; moving it forward is a separate act on the task surface.

/**
 * Reading the room overview. One blocking outbound GET on the server side.
 *
 * The backend's per-target budget is two attempts of connect 5s + read 10s,
 * with a fixed 1s backoff it will extend to at most 5s when the service asks
 * it to - about thirty-five seconds before it can honestly say the room list
 * could not be read. Forty-five seconds sits above that with margin for the
 * strict parse and still bounds the UI. A shorter deadline would abandon a
 * read the server was still making and report `timeout`, which is a claim
 * about the *local* service and would be false.
 */
export const WORK_SCAN_ROOMS_TIMEOUT_MS = 45000;

/**
 * The fixed part of a scan's deadline: session, policy and parse work that
 * happens once however many rooms were chosen.
 */
export const WORK_SCAN_BASE_TIMEOUT_MS = 10000;

/**
 * The deadline one room adds to a scan.
 *
 * A scan reads the chosen rooms **sequentially**, one bounded HTTP exchange
 * each, so its honest budget is per room rather than per request: the same
 * thirty-five second worst case as the overview read, plus margin for the
 * strict parse and the derivation. It is multiplied by the number of rooms
 * the caller actually named rather than by the ceiling of ten, so choosing
 * two rooms does not buy a six-minute hang.
 *
 * This is the one deadline in the app that is computed instead of constant,
 * and the reason is the same reason the others are long: abandoning a scan
 * mid-flight throws away every room the server had already read and reports
 * `timeout` in place of the per-room result - including the per-room
 * *failures*, which are the whole point of the failure list.
 */
export const WORK_SCAN_ROOM_TIMEOUT_MS = 40000;

/**
 * How many rooms one scan may name.
 *
 * Mirrors `WorkScanScanRequest`'s own `max_length` and the service's
 * `MAX_ROOMS_PER_SCAN`. Held here so the UI cannot build a request the server
 * would reject with a 422 - the bound is the server's, and this is a copy of
 * it rather than a second, independent limit.
 */
export const WORK_SCAN_MAX_ROOMS = 10;

/** The room count one read of the overview asks for. The published clamp is
 * 1..200 and the backend's own default is 50; this sends it explicitly so the
 * number is visible at the call site rather than inherited silently. */
export const WORK_SCAN_ROOM_INDEX_LIMIT = 50;

/** Messages read per room in one scan. Same published clamp, same reason. */
export const WORK_SCAN_MESSAGE_LIMIT = 50;

/**
 * Lines read from the discovery log in one read. Same published clamp again.
 *
 * The log is an ordinary room to the backend - `/r/{room}` with a
 * compile-time room name - so it inherits the same 1..200 clamp, and this
 * sends the number explicitly for the same reason the other two do.
 */
export const WORK_SCAN_DISCOVERY_LIMIT = 50;

/**
 * The whole scan surface, read-only.
 *
 * Contacts nobody: it reports what the last user-initiated read found, or
 * that none has run. This is the only call in the group anything invokes on
 * mount, and that is safe precisely because it makes no outbound request.
 */
export async function fetchWorkScanStatus(): Promise<WorkScanStatus> {
  return request("/api/workscan/status", isWorkScanStatus);
}

/**
 * Read the public room overview once, because the user asked.
 *
 * Separate from the scan on purpose: "show me what is out there" and "read
 * these rooms" are two decisions, and one button doing both would always
 * read everything.
 */
export async function refreshWorkScanRooms(): Promise<WorkScanStatus> {
  return mutate("/api/workscan/rooms/refresh", isWorkScanStatus,
    { limit: WORK_SCAN_ROOM_INDEX_LIMIT },
    WORK_SCAN_ROOMS_TIMEOUT_MS,
  );
}

/**
 * Read the discovery log once, because the user asked.
 *
 * `GET /r/events` is the service's own append-ordered log of new public rooms.
 * It is a third decision, not a step inside either of the other two: "what has
 * opened lately", "show me the current list" and "read these rooms" are things
 * a person chooses separately, and a button that did two of them would always
 * do the more expensive one.
 *
 * `since` is the cursor **the caller carries**, taken from the previous read's
 * `last_seq` and passed back only when a person presses the continue control.
 * Nothing on this side stores it between reads: a remembered cursor plus any
 * scheduler is a crawl, and this module owns the half it can refuse.
 *
 * The deadline is `WORK_SCAN_ROOMS_TIMEOUT_MS` rather than a number of its
 * own, and that reuse is the honest choice: behind this route the server makes
 * exactly one bounded outbound read, through the same client, against the same
 * per-target budget as the overview read. A second constant here would be a
 * second answer to a question that has one.
 */
export async function refreshWorkScanDiscovery(
  since: number | null,
): Promise<WorkScanStatus> {
  return mutate("/api/workscan/discovery/refresh", isWorkScanStatus,
    { since, limit: WORK_SCAN_DISCOVERY_LIMIT },
    WORK_SCAN_ROOMS_TIMEOUT_MS,
  );
}

/**
 * Read the rooms the user chose, once each.
 *
 * The room names are the entire addressable part of this request: there is no
 * host, path, URL or room template here or in the route behind it, and each
 * name goes through the write path's room policy - `DENIED_ROOMS`, Lobby
 * included - server-side.
 */
export async function scanWorkRooms(rooms: readonly string[]): Promise<WorkScanStatus> {
  return mutate("/api/workscan/scan", isWorkScanStatus,
    { rooms: [...rooms], limit: WORK_SCAN_MESSAGE_LIMIT },
    WORK_SCAN_BASE_TIMEOUT_MS + rooms.length * WORK_SCAN_ROOM_TIMEOUT_MS,
  );
}

/**
 * Open one candidate as a local task in `suggested`.
 *
 * A local database write and nothing else: it sends nothing outward and it
 * approves nothing. The default deadline is right because no part of this
 * leaves the machine.
 */
export async function suggestWorkScanCandidate(
  candidateId: string,
): Promise<WorkScanSuggestion> {
  return mutate("/api/workscan/suggest", isWorkScanSuggestion, {
    candidate_id: candidateId,
  });
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

// --- Tasks, runs and the Activity Desk (Paket H2) ---------------------------
//
// Every call below is **local**. Nothing in this group opens an outbound
// connection: a run is a chain of deterministic tools over files inside one
// task's workspace, and the Activity Desk reads a table on this machine. The
// group therefore has no long deadline for a remote service and no retry of
// its own - the one long deadline here is `AGENT_RUN_TIMEOUT_MS`, and it is
// long because the *server* holds the request open while it works, not
// because anything is waiting on a network.
//
// Three shapes are deliberately absent:
//
// * **there is no call that runs a command.** No function here, and no
//   argument to a function here, reaches a shell, a process or an
//   interpreter. `execution_unavailable` arrives as a reason with a sentence
//   from `fetchAgentSurface` (ADR-0008 1);
// * **there is no call that records evidence.** Nothing lets a caller assert
//   that a test passed or that a result was accepted; those fields are
//   written by what actually produced them, or not at all;
// * **there is no timer and no poll.** Every function below runs inside a
//   user action, once. A restart resumes nothing on its own, and
//   `resumeRun` exists so continuing is a person's decision (SI-224,
//   SI-272).

/**
 * The deadline for starting or resuming a run.
 *
 * A run executes **inside the request that asked for it**: the backend has no
 * scheduler and no background task, so `POST /runs/{id}/start` holds the
 * connection open for as long as the tool chain takes. The server's own
 * ceiling is 120 wall-clock seconds (`AgentCeilingStatus.max_wall_clock_seconds`),
 * after which it stops the run itself and answers with a
 * `budget_exhausted` phase; 150 000 ms sits above that with margin for the
 * final digest pass and the response write.
 *
 * A shorter deadline would abandon a run the server is still executing and
 * report `timeout` - a claim about the local service - while discarding the
 * per-step record that is the entire point of the reply.
 */
export const AGENT_RUN_TIMEOUT_MS = 150000;

/** The tasks, newest first, bounded. Reads a local table and nothing else. */
export async function fetchTasks(): Promise<TaskListResponse> {
  return request("/api/tasks", isTaskListResponse);
}

/**
 * The agent surface: what runs, what does not, and why.
 *
 * Read on mount, and safe there for the same reason `fetchWorkScanStatus` is:
 * it contacts nobody. It carries the `execution_unavailable` reason, the
 * ceiling with its refused units, the whole tool registry and any run a
 * restart left interrupted - which it **lists** and never continues.
 */
export async function fetchAgentSurface(): Promise<AgentSurfaceResponse> {
  return request("/api/tasks/surface", isAgentSurfaceResponse);
}

/** One task's runs and the files its workspace currently holds. */
export async function fetchTaskRuns(taskId: string): Promise<AgentTaskRunsResponse> {
  return request(`/api/tasks/${taskId}/runs`, isAgentTaskRunsResponse);
}

/**
 * Move a task the way a person may move it.
 *
 * The target type omits `running` and `paused` - those belong to the runner
 * and are reached by recording a plan first - and omits `ready_to_publish`,
 * which is derived from evidence and cannot be asked for.
 */
export async function transitionTask(input: {
  readonly taskId: string;
  readonly target: TaskUserTransitionName;
  readonly detail?: string;
}): Promise<TaskStatusResponse> {
  return mutate(`/api/tasks/${input.taskId}/transition`, isTaskStatusResponse, {
    target: input.target,
    detail: input.detail ?? "",
  });
}

/**
 * Record a plan. **Runs nothing.**
 *
 * Two decisions rather than one, the shape the composer uses for signing and
 * sending: a person approves *what will be done*, and then, separately, that
 * it be done. The recorded plan is frozen - re-planning opens a new run - so
 * a success criterion cannot be loosened after the fact.
 */
export async function planTaskRun(input: {
  readonly taskId: string;
  readonly steps: readonly { readonly tool_id: string; readonly arguments: Record<string, string> }[];
  readonly expectedArtifacts: readonly string[];
  readonly testCondition: string;
  /**
   * How success is established for a **machine**, as conditions from the
   * closed acceptance registry.
   *
   * Optional, and its absence is not an oversight: a plan may record only the
   * sentence, and such a plan reports `not_implemented` and leaves the task
   * short of publication - which is exactly what an unchecked plan has
   * earned. Defaulting this to something non-empty here would be this client
   * inventing a success criterion nobody wrote.
   */
  readonly acceptance?: readonly {
    readonly kind: AgentAcceptanceKindName;
    readonly arguments: Record<string, string>;
  }[];
}): Promise<AgentTaskRunsResponse> {
  return mutate(`/api/tasks/${input.taskId}/runs`, isAgentTaskRunsResponse, {
    steps: input.steps.map((step) => ({ tool_id: step.tool_id, arguments: step.arguments })),
    expected_artifacts: [...input.expectedArtifacts],
    test_condition: input.testCondition,
    acceptance: (input.acceptance ?? []).map((entry) => ({
      kind: entry.kind,
      arguments: entry.arguments,
    })),
  });
}

/** Carry the recorded plan out. Blocking on the server; see the deadline. */
export async function startTaskRun(
  taskId: string,
  runId: string,
): Promise<AgentTaskRunsResponse> {
  return mutate(`/api/tasks/${taskId}/runs/${runId}/start`, isAgentTaskRunsResponse,
    {},
    AGENT_RUN_TIMEOUT_MS,
  );
}

/**
 * Block the next tool call.
 *
 * Not a cancellation of the request in flight: the flag is read by the runner
 * before each call, and a result that arrives after a stop is discarded
 * rather than recorded. The default deadline is right because this writes one
 * flag.
 */
export async function stopTaskRun(
  taskId: string,
  runId: string,
): Promise<AgentTaskRunsResponse> {
  return mutate(`/api/tasks/${taskId}/runs/${runId}/stop`, isAgentTaskRunsResponse, {});
}

/** Continue a paused run, within the scope already approved. */
export async function resumeTaskRun(
  taskId: string,
  runId: string,
): Promise<AgentTaskRunsResponse> {
  return mutate(`/api/tasks/${taskId}/runs/${runId}/resume`, isAgentTaskRunsResponse,
    {},
    AGENT_RUN_TIMEOUT_MS,
  );
}

/**
 * Ask Station to re-derive whether this task is ready to publish.
 *
 * **There is no target in this body, and that is the whole design.** SI-222
 * says `ready_to_publish` is derived from evidence and cannot be asked for,
 * so it is absent from `TaskUserTransitionName` and there is no parameter
 * here that could name it. What this asks for is a *re-reading* of three
 * fields three different acts filled - what the runner produced, what the
 * plan's own acceptance conditions decided over those bytes, and a person's
 * acceptance - and the task moves only if all three are verified.
 *
 * A caller may ask as often as they like and can never make it come out
 * differently. A task with a missing or unverified field gets a refusal that
 * names the fields, not a state change.
 */
export async function deriveTaskPublishReadiness(input: {
  readonly taskId: string;
  readonly detail?: string;
}): Promise<TaskStatusResponse> {
  return mutate(
    `/api/tasks/${encodeURIComponent(input.taskId)}/publish-readiness`,
    isTaskStatusResponse,
    { detail: input.detail ?? "" },
  );
}

// --- The model planning lane (ADR-0012) ------------------------------------
//
// The one group in this file that causes an outbound request, and it causes
// exactly one per call: the server spends a single model turn inside the
// request that asked for it. Three properties are worth stating at the call
// site rather than only in the route:
//
// * **it starts nothing.** The best outcome is `planned` - a recorded plan in
//   the `planned` phase, waiting for the start route a person invokes. There
//   is no argument here that could start it and no code path from the planner
//   to the runner;
// * **it cannot choose a model, a prompt or a tool list.** The model comes
//   from the stored selection, the tools are the whole compile-time registry
//   and the system prompt is a constant. The only free text is the person's
//   own instruction;
// * **it schedules nothing.** One turn per call, inside the call. No timer,
//   no background task, no retry of its own (SI-272).

/**
 * The deadline for one model turn.
 *
 * The server's own transport budget for the metered endpoint is connect 5s +
 * write 10s + read 30s with **exactly one attempt**, and the turn then
 * resolves the proposal against the tool registry and records a plan. Sixty
 * seconds sits above that with margin.
 *
 * A shorter deadline would abandon a turn the provider may already have
 * billed and report `timeout` - a claim about the *local* service - while
 * discarding the outcome, which is the only thing that says whether a plan
 * was recorded.
 */
export const MODEL_PLAN_TIMEOUT_MS = 60000;

/**
 * Spend one model turn on this task and record whatever plan it proposed.
 *
 * `instruction` is the person's own words and the only free text that reaches
 * the provider besides the task's own recorded facts. It is swept, bounded
 * and **not stored**: what gets written down is the plan the turn produced.
 *
 * The response carries the task and its runs after the turn, so a caller
 * needs one request rather than three to show what changed.
 */
export async function proposeModelPlan(input: {
  readonly taskId: string;
  readonly instruction?: string;
}): Promise<ModelProposalResponse> {
  return mutate(
    `/api/tasks/${encodeURIComponent(input.taskId)}/model-plan`,
    isModelProposalResponse,
    { instruction: input.instruction ?? "" },
    MODEL_PLAN_TIMEOUT_MS,
  );
}

/**
 * Drop this task's planning session so the next turn starts from nothing.
 *
 * Contacts nobody, which is why it keeps the default deadline. Starting over
 * is not a resume and it is not a way around the ceiling: the recorded runs,
 * the workspace and the task's evidence are all untouched, and the turn
 * counter comes back in the response rather than being reset here.
 */
export async function forgetModelPlanSession(taskId: string): Promise<ModelProposalResponse> {
  return mutate(
    `/api/tasks/${encodeURIComponent(taskId)}/model-plan/forget`,
    isModelProposalResponse,
    {},
  );
}

/**
 * The timeline, newest first, bounded.
 *
 * `runId` is the only narrowing this endpoint accepts and it is matched for
 * equality against a column; it never becomes a path, a name or an address.
 * An empty value means "every run".
 */
export async function fetchActivity(runId = ""): Promise<ActivityListResponse> {
  const query = runId === "" ? "" : `?run_id=${encodeURIComponent(runId)}`;
  return request(`/api/activity${query}`, isActivityListResponse);
}

/**
 * Remove timeline rows, and record that removal as an audit event.
 *
 * Chain-referenced rows are kept and counted separately. The two numbers are
 * never summed: "twelve removed" and "three kept because the chain refers to
 * them" answer different questions.
 */
export async function deleteActivity(runId = ""): Promise<ActivityDeleteResponse> {
  return mutate("/api/activity/delete", isActivityDeleteResponse, { run_id: runId });
}

// --- The proof workspace (Paket H3) ----------------------------------------
//
// Five calls, and the shape of the set is the point.
//
// * **Nothing here names a destination.** `takeProofBundle` asks for a format
//   and spends a token; there is no path, no filename and no directory
//   parameter, so the traversal, symlink and overwrite questions are absent
//   from this feature rather than defended against (ADR-0009 3).
// * **Nothing here can cause a send.** `recordProofPublicShare` carries an
//   evidence record's identity and nothing else - no room, no address, no
//   text. It records that a send already in the archive belongs to this task;
//   the send itself goes out through the composer chain, and
//   `OUTBOUND_CLIENT_MODULES` stays at five (ADR-0009 11).
// * **Nothing here moves a task.** Acceptance is the input to a publication
//   decision, not its output, and there is no transition parameter on any of
//   these functions (ADR-0009 8, SI-222).

/** One task's proof, as it stands. A read: it writes nothing and sends nothing. */
export async function fetchProof(taskId: string): Promise<ProofWorkspace> {
  return request(`/api/proof/${encodeURIComponent(taskId)}`, isProofWorkspace);
}

/**
 * Mint one single-use approval, bound to the bundle as it stands right now.
 *
 * Preparing delivers nothing. It returns the digest beside the token so the
 * second request can be checked against the first: if an artifact changes in
 * between, the digest changes and the approval no longer matches. The token is
 * held in component state and never written to any browser storage (SI-24).
 */
export async function prepareProofShare(taskId: string): Promise<ProofPrepareResult> {
  return mutate(`/api/proof/${encodeURIComponent(taskId)}/prepare`, isProofPrepareResult,
    {},
  );
}

/**
 * Spend the approval and take the file.
 *
 * `acknowledged` is passed through from the caller rather than defaulted here,
 * for the reason `exportEvidence` gives: a default in this function would be a
 * way to take the bundle without consent that type-checks. The backend refuses
 * a body without the key (422) and refuses a `false` again in the handler.
 *
 * The response is a file, so it cannot go through `request`. The server's
 * `Content-Disposition` name is deliberately not read back; the download name
 * is stated on this side, from a constant.
 *
 * A refused delivery **spends the token too**. That is the server's rule, not
 * this function's, and the surface says so before the button is pressed - a
 * caller that quietly re-prepared on failure would be hiding it.
 */
export async function takeProofBundle(input: {
  readonly taskId: string;
  readonly shareToken: string;
  readonly format: ProofBundleFormat;
  readonly acknowledged: boolean;
}): Promise<{ blob: Blob }> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }

  const deadline = AbortSignal.timeout(DEFAULT_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`/api/proof/${encodeURIComponent(input.taskId)}/share`, {
      method: "POST",
      credentials: "same-origin",
      signal: deadline,
      headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
      body: JSON.stringify({
        share_token: input.shareToken,
        format: input.format,
        acknowledged: input.acknowledged,
      }),
    });
  } catch (caught) {
    throw classifyFetchFailure(caught, deadline);
  }

  const requestId = readRequestId(response);

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response), { requestId });
  }

  try {
    return { blob: await response.blob() };
  } catch {
    throw new ApiError(response.status, "malformed_response", { kind: "malformed", requestId });
  }
}

/**
 * The header carrying the delivered file's own digest.
 *
 * A header rather than a wrapper around the bytes, because the response body
 * has to *be* the file: a person who saves it and hashes it must get the
 * number the bundle printed, and any envelope at all would break that.
 */
const ARTIFACT_DIGEST_HEADER = "X-Station-Artifact-Sha256";

/** The digest of the bundle the spent approval was bound to. */
const ARTIFACT_BUNDLE_HEADER = "X-Station-Bundle-Sha256";

/**
 * Spend the approval and take **one produced file**, as the file.
 *
 * The route a proof was missing: a bundle is the document *about* a task, and
 * until this existed the report a run wrote stayed on disk while its name and
 * digest travelled. This hands over the bytes.
 *
 * It is not a second consent shape. The approval is the one `prepareProofShare`
 * minted - single-use, bound to the bundle digest - and since that digest now
 * covers the artifact bodies it covers these exact bytes. **A refused delivery
 * spends the token too**, exactly as the bundle download does, so "the
 * approval is spent once" stays true across both routes rather than per route.
 *
 * `name` selects an entry from the document the approval was bound to; it is
 * not a path, and the server opens none. A file whose body was left out of
 * the bundle - a ceiling, a secret-pattern hit, bytes that are not UTF-8 -
 * comes back as a refusal that says which, rather than as a truncated file.
 *
 * The two digests come back as headers beside the bytes and are returned to
 * the caller so the surface can print what was delivered without re-hashing
 * anything itself.
 */
export async function takeProofArtifact(input: {
  readonly taskId: string;
  readonly shareToken: string;
  readonly name: string;
  readonly acknowledged: boolean;
}): Promise<{ blob: Blob; sha256: string; bundleSha256: string }> {
  if (csrfToken === null) {
    throw new Error("session_not_bootstrapped");
  }

  const deadline = AbortSignal.timeout(DEFAULT_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`/api/proof/${encodeURIComponent(input.taskId)}/artifact`, {
      method: "POST",
      credentials: "same-origin",
      signal: deadline,
      headers: { "Content-Type": "application/json", [csrfHeader]: csrfToken },
      body: JSON.stringify({
        share_token: input.shareToken,
        name: input.name,
        acknowledged: input.acknowledged,
      }),
    });
  } catch (caught) {
    throw classifyFetchFailure(caught, deadline);
  }

  const requestId = readRequestId(response);

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response), { requestId });
  }

  try {
    return {
      blob: await response.blob(),
      sha256: response.headers.get(ARTIFACT_DIGEST_HEADER) ?? "",
      bundleSha256: response.headers.get(ARTIFACT_BUNDLE_HEADER) ?? "",
    };
  } catch {
    throw new ApiError(response.status, "malformed_response", { kind: "malformed", requestId });
  }
}

/**
 * Record that a person accepted one exact bundle.
 *
 * `bundleSha256` is required by the wire and compared server-side against the
 * bundle as it stands: an acceptance recorded against a bundle that has since
 * changed is an acceptance of something else, and comes back `bundle_changed`.
 *
 * The response is the workspace again, not a transition. Nothing about this
 * call moves the task, and the returned `task.state` is the state it already
 * had.
 */
export async function recordProofAcceptance(input: {
  readonly taskId: string;
  readonly bundleSha256: string;
  readonly detail: string;
}): Promise<ProofWorkspace> {
  return mutate(`/api/proof/${encodeURIComponent(input.taskId)}/acceptance`, isProofWorkspace, {
    bundle_sha256: input.bundleSha256,
    detail: input.detail,
  });
}

/**
 * Point the fourth field at an archived send. Causes no send.
 *
 * `evidenceId` is an evidence record's own identity. Whether the reference
 * counts as verified is read server-side from that record's own write
 * outcome; there is no parameter here that could assert it.
 */
export async function recordProofPublicShare(input: {
  readonly taskId: string;
  readonly evidenceId: string;
  readonly detail: string;
}): Promise<ProofWorkspace> {
  return mutate(`/api/proof/${encodeURIComponent(input.taskId)}/public-share`, isProofWorkspace, {
    evidence_id: input.evidenceId,
    detail: input.detail,
  });
}
