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
  OpenCodeStatus,
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

async function request<T>(
  path: string,
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
  return request<ComposeCapability>("/api/compose/capability");
}

/** Step 1: sweep and bind a digest. Reserves no nonce and signs nothing. */
export async function createComposeDraft(input: {
  readonly room: string;
  readonly text: string;
}): Promise<ComposeDraft> {
  return mutate<ComposeDraft>("/api/compose/draft", {
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
  return mutate<ComposeSignature>(
    "/api/compose/sign",
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
  return mutate<ComposeSendResult>(
    "/api/compose/send",
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
  return request<EvidenceList>("/api/evidence/records");
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
  return mutate<EvidenceCaptureResult>(
    "/api/evidence/capture",
    { evidence_id: evidenceId },
    CAPTURE_TIMEOUT_MS,
  );
}

/** Recompute the chain and compare it against its separately held head. */
export async function fetchAuditChain(): Promise<AuditChainStatus> {
  return request<AuditChainStatus>("/api/evidence/audit");
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
  return request<OpenCodeStatus>("/api/opencode/status");
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
  return mutate<OpenCodeStatus>("/api/opencode/credential", { api_key: apiKey }, CREDENTIAL_TIMEOUT_MS);
}

/** Remove the stored key. Empty body: there is nothing here to steer. */
export async function forgetOpenCodeCredential(): Promise<OpenCodeStatus> {
  return mutate<OpenCodeStatus>("/api/opencode/credential/forget", {});
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
  return mutate<OpenCodeStatus>("/api/opencode/catalog/refresh", {}, CATALOG_TIMEOUT_MS);
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
  return mutate<OpenCodeStatus>("/api/opencode/model", {
    model_id: input.modelId,
    training_acknowledged: input.trainingAcknowledged,
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
