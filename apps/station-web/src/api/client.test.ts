import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as clientModule from "./client";
import {
  adoptRecovery,
  ApiError,
  bootstrapSession,
  captureEvidenceLine,
  createComposeDraft,
  createIdentity,
  deleteActivity,
  deriveTaskPublishReadiness,
  fetchActivity,
  fetchAgentSurface,
  fetchAppStatus,
  fetchAuditChain,
  fetchComposeCapability,
  fetchConformance,
  fetchEvidenceRecords,
  fetchIdentity,
  fetchOpenCodeStatus,
  fetchProof,
  fetchTaskRuns,
  fetchTasks,
  fetchTechnocore,
  fetchWorkScanStatus,
  fetchWriteGate,
  forgetModelPlanSession,
  forgetOpenCodeCredential,
  hasCsrfToken,
  inspectRecovery,
  mutate,
  planTaskRun,
  prepareProofShare,
  proposeModelPlan,
  recordProofAcceptance,
  recordProofPublicShare,
  refreshOpenCodeCatalog,
  refreshTechnocore,
  refreshWorkScanDiscovery,
  refreshWorkScanRooms,
  resetSessionState,
  resumeTaskRun,
  revokeIdentity,
  scanWorkRooms,
  selectOpenCodeModel,
  sendComposeMessage,
  signComposeDraft,
  startTaskRun,
  stopTaskRun,
  storeOpenCodeCredential,
  suggestWorkScanCandidate,
  toApiError,
  transitionTask,
  verifyRecovery,
} from "./client";
import type { TechnocoreStatus } from "./types";

/**
 * A complete read-only verdict.
 *
 * Complete on purpose: the client now refuses a partial document, so a fixture
 * that named two fields would be exercising the validator instead of the
 * deadline the test is about.
 */
const TECHNOCORE_CURRENT: TechnocoreStatus = {
  state: "current",
  manifest_current: true,
  checked_at: "2026-01-01T00:00:00Z",
  last_attempt_at: "2026-01-01T00:00:00Z",
  last_success_at: "2026-01-01T00:00:00Z",
  reasons: [],
  sources: [],
  fields: [],
  critical_mismatch_count: 0,
  critical_unevaluable_count: 0,
  warning_count: 0,
  origin: "test-only",
};

const CSRF_VALUE = "test-only-csrf-value-not-a-real-token";

//: TEST-ONLY request id: 32 hex characters, like the backend header.
const REQUEST_ID = "00112233445566778899aabbccddeeff";

function jsonResponse(
  body: unknown,
  status = 200,
  extraHeaders: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...extraHeaders },
  });
}

function bootstrapBody() {
  return { csrf_token: CSRF_VALUE, csrf_header: "X-Station-CSRF" };
}

/**
 * The probe path the CSRF tests drive. `mutate` takes a validator as a
 * required argument, so even a test path has to say what it expects back -
 * which is the property that keeps a real endpoint from being added without
 * one.
 */
function isProbeAck(value: unknown): value is { readonly ok: boolean } {
  return typeof value === "object" && value !== null && "ok" in value;
}

async function captureApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (caught) {
    expect(caught).toBeInstanceOf(ApiError);
    return caught as ApiError;
  }
  throw new Error("expected the request to fail");
}

describe("api client", () => {
  it.each([{}, { service: null }, { service: { state: "running" } }])(
    "rejects an incomplete successful status response: %j",
    async (body) => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(body)));
      const error = await captureApiError(fetchAppStatus());
      expect(error.kind).toBe("malformed");
      expect(error.code).toBe("malformed_response");
    },
  );

  it("keeps a response-body timeout distinct from malformed JSON", async () => {
    const response = jsonResponse({});
    vi.spyOn(response, "json").mockRejectedValue(new DOMException("TEST-ONLY", "TimeoutError"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    expect((await captureApiError(fetchAppStatus())).kind).toBe("timeout");
  });
  beforeEach(() => {
    resetSessionState();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("calls relative URLs so no backend port is ever hardcoded", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(bootstrapBody()));
    vi.stubGlobal("fetch", fetchMock);

    await bootstrapSession();

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/session/bootstrap");
    expect(url.startsWith("http")).toBe(false);
    expect(url).not.toMatch(/\d{4,5}/);
  });

  it("sends the session cookie only to the same origin", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(bootstrapBody()));
    vi.stubGlobal("fetch", fetchMock);

    await bootstrapSession();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.credentials).toBe("same-origin");
  });

  it("keeps the CSRF value in memory and never in browser storage", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(bootstrapBody()));
    vi.stubGlobal("fetch", fetchMock);

    // Spying on the prototype covers both persistent web storage objects:
    // they are Storage instances sharing this method. That is a stricter
    // assertion than inspecting either object directly, and it needs no
    // banned identifier.
    const setItem = vi.spyOn(Storage.prototype, "setItem");

    await bootstrapSession();

    expect(hasCsrfToken()).toBe(true);
    expect(setItem).not.toHaveBeenCalled();

    setItem.mockRestore();
  });

  it("attaches the CSRF header to state-changing requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(bootstrapBody()))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await bootstrapSession();
    await mutate("/api/probe", isProbeAck, { hello: "world" });

    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-Station-CSRF"]).toBe(CSRF_VALUE);
  });

  it("refuses a state-changing request before the session is bootstrapped", async () => {
    vi.stubGlobal("fetch", vi.fn());
    await expect(mutate("/api/probe", isProbeAck, {})).rejects.toThrow(
      "session_not_bootstrapped",
    );
  });

  it("raises ApiError with the status code on failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "x" }, 401)));

    await expect(fetchAppStatus()).rejects.toBeInstanceOf(ApiError);
    await expect(fetchAppStatus()).rejects.toMatchObject({ status: 401 });
  });
});

describe("request deadlines", () => {
  beforeEach(() => {
    resetSessionState();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("gives every request an abort deadline of 15 seconds by default", async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(bootstrapBody())));

    await bootstrapSession();

    expect(timeoutSpy).toHaveBeenCalledWith(15000);
  });

  it("gives the official-source check a longer 30 second deadline", async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(bootstrapBody()))
        .mockResolvedValueOnce(jsonResponse(TECHNOCORE_CURRENT)),
    );

    await bootstrapSession();
    await refreshTechnocore();

    expect(timeoutSpy).toHaveBeenLastCalledWith(30000);
  });

  it("classifies an expired deadline as a retryable timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("The operation timed out.", "TimeoutError")),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.kind).toBe("timeout");
    expect(error.code).toBe("timeout");
    expect(error.status).toBe(0);
    expect(error.retryable).toBe(true);
    expect(error.userMessage).toContain("zaman asimina");
  });

  it("calls an abort a timeout only when our own deadline fired", async () => {
    // Some runtimes surface a timed-out signal as a plain AbortError. The
    // claim "the service was too slow" is still true there, because the
    // signal we passed is the one that aborted.
    const controller = new AbortController();
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(controller.signal);
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        controller.abort(new DOMException("The operation timed out.", "TimeoutError"));
        return Promise.reject(new DOMException("Aborted.", "AbortError"));
      }),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.kind).toBe("timeout");
    expect(error.code).toBe("timeout");
  });

  it("classifies an abort our deadline did not cause as canceled, not a timeout", async () => {
    // The old code called every abort a timeout, which asserts that the local
    // service failed to answer in time. Nothing here observed that.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("Aborted.", "AbortError")),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.kind).toBe("canceled");
    expect(error.code).toBe("request_canceled");
    expect(error.status).toBe(0);
    expect(error.retryable).toBe(true);
    expect(error.userMessage).not.toContain("zaman asimina");
  });
});

describe("failure classification", () => {
  beforeEach(() => {
    resetSessionState();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("classifies a dropped connection as a retryable network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = await captureApiError(fetchAppStatus());
    expect(error.kind).toBe("network");
    expect(error.code).toBe("network_error");
    expect(error.status).toBe(0);
    expect(error.retryable).toBe(true);
  });

  it("separates an unparseable success body from a dropped connection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>not json</html>", { status: 200 })),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.kind).toBe("malformed");
    expect(error.code).toBe("malformed_response");
    expect(error.status).toBe(200);
    expect(error.retryable).toBe(false);
  });

  it.each([
    [401, "auth", false],
    [403, "auth", false],
    [429, "rate_limited", true],
    [503, "unavailable", true],
    [500, "server", true],
    [404, "request", false],
  ] as const)("maps HTTP %i to kind %s", async (status, kind, retryable) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "" }, status)));

    const error = await captureApiError(fetchAppStatus());
    expect(error.kind).toBe(kind);
    expect(error.retryable).toBe(retryable);
  });

  it("keeps a machine code as the code but never as the user message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "vault_locked" }, 409)),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.code).toBe("vault_locked");
    expect(error.userMessage).not.toBe("vault_locked");
    expect(error.userMessage.length).toBeGreaterThan(0);
  });

  it("shows a backend Turkish sentence to the user verbatim", async () => {
    const sentence = "Onay metni tam olarak yazilmalidir.";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: sentence }, 400)),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.userMessage).toBe(sentence);
    expect(error.code).toBe("http_400");
  });

  it("falls back to the catalogue when the error body is empty", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));

    const error = await captureApiError(fetchAppStatus());
    expect(error.code).toBe("http_500");
    expect(error.userMessage).toContain("beklenmeyen bir hata");
  });

  it("captures the backend request id from the response header", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "internal_error" }, 500, {
          "X-Station-Request-Id": REQUEST_ID,
        }),
      ),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.requestId).toBe(REQUEST_ID);
    expect(error.code).toBe("internal_error");
  });

  it("refuses an upper-case request id: the server writes lower-case hex", async () => {
    // uuid4().hex is always lower case, so an upper-case value did not come
    // from the shape we documented and must not be reported as our id.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "internal_error" }, 500, {
          "X-Station-Request-Id": REQUEST_ID.toUpperCase(),
        }),
      ),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.requestId).toBeNull();
  });

  it("treats a missing or malformed request id header as null", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "internal_error" }, 500, {
          "X-Station-Request-Id": "not-a-request-id",
        }),
      ),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.requestId).toBeNull();
  });

  it("normalises an unbootstrapped session into an auth-class ApiError", () => {
    const error = toApiError(new Error("session_not_bootstrapped"));
    expect(error.kind).toBe("auth");
    expect(error.code).toBe("session_not_bootstrapped");
    expect(error.retryable).toBe(false);
  });

  it("passes an ApiError through toApiError unchanged", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "x" }, 404)));
    const original = await captureApiError(fetchAppStatus());
    expect(toApiError(original)).toBe(original);
  });
});

// ---------------------------------------------------------------------------
// The boundary itself, not one path through it.
//
// The defect these cover: validation used to be attached to a single URL, so
// every other endpoint returned `data as T` and a 200 carrying `{}` reached
// React as if it were a document. The first screen to dereference a nested
// field then threw a TypeError, and the section boundary - not the client -
// was what kept the app standing.
// ---------------------------------------------------------------------------

/** A .tcrec file is ciphertext to this layer; the bytes here are irrelevant. */
function recoveryFile(): File {
  return new File(["TEST-ONLY not a real recovery file"], "test.tcrec");
}

interface Probe {
  readonly name: string;
  readonly call: () => Promise<unknown>;
}

/**
 * One probe per exported call that reads a JSON document.
 *
 * Every request below is answered by a stub. Nothing here opens a socket, and
 * no room named in these arguments is ever contacted.
 */
const JSON_PROBES: readonly Probe[] = [
  { name: "bootstrapSession", call: () => bootstrapSession() },
  { name: "fetchAppStatus", call: () => fetchAppStatus() },
  { name: "fetchIdentity", call: () => fetchIdentity() },
  { name: "fetchWriteGate", call: () => fetchWriteGate() },
  { name: "fetchConformance", call: () => fetchConformance() },
  { name: "fetchTechnocore", call: () => fetchTechnocore() },
  { name: "refreshTechnocore", call: () => refreshTechnocore() },
  {
    name: "createIdentity",
    call: () =>
      createIdentity({
        protection: "dpapi",
        passphrase: null,
        passphraseConfirm: null,
        label: "test",
        confirmation: "test",
        acceptDpapiOnlyRisk: true,
      }),
  },
  { name: "verifyRecovery", call: () => verifyRecovery(recoveryFile(), "test-only") },
  { name: "inspectRecovery", call: () => inspectRecovery(recoveryFile(), "test-only") },
  {
    name: "adoptRecovery",
    call: () =>
      adoptRecovery({
        file: recoveryFile(),
        recoveryPassphrase: "test-only",
        protection: "dpapi",
        vaultPassphrase: null,
        confirmDid: "did:key:test-only",
        label: "test",
      }),
  },
  { name: "revokeIdentity", call: () => revokeIdentity("did:key:test-only") },
  { name: "fetchComposeCapability", call: () => fetchComposeCapability() },
  { name: "createComposeDraft", call: () => createComposeDraft({ room: "test-room", text: "x" }) },
  {
    name: "signComposeDraft",
    call: () =>
      signComposeDraft({ draftId: "d1", draftDigest: "0".repeat(64), vaultPassphrase: null }),
  },
  { name: "sendComposeMessage", call: () => sendComposeMessage("test-only-token") },
  { name: "fetchEvidenceRecords", call: () => fetchEvidenceRecords() },
  { name: "captureEvidenceLine", call: () => captureEvidenceLine("e1") },
  { name: "fetchAuditChain", call: () => fetchAuditChain() },
  { name: "fetchOpenCodeStatus", call: () => fetchOpenCodeStatus() },
  {
    name: "storeOpenCodeCredential",
    call: () => storeOpenCodeCredential("test-only-not-a-real-key"),
  },
  { name: "forgetOpenCodeCredential", call: () => forgetOpenCodeCredential() },
  { name: "refreshOpenCodeCatalog", call: () => refreshOpenCodeCatalog() },
  {
    name: "selectOpenCodeModel",
    call: () => selectOpenCodeModel({ modelId: "test/model", trainingAcknowledged: false }),
  },
  { name: "fetchWorkScanStatus", call: () => fetchWorkScanStatus() },
  { name: "refreshWorkScanRooms", call: () => refreshWorkScanRooms() },
  {
    name: "refreshWorkScanDiscovery",
    // `null` is the first read: no cursor, newest lines. The cursor form is
    // exercised where it belongs, in the panel test that measures the body.
    call: () => refreshWorkScanDiscovery(null),
  },
  { name: "scanWorkRooms", call: () => scanWorkRooms(["genesis"]) },
  { name: "suggestWorkScanCandidate", call: () => suggestWorkScanCandidate("c1") },
  { name: "fetchTasks", call: () => fetchTasks() },
  { name: "fetchAgentSurface", call: () => fetchAgentSurface() },
  { name: "fetchTaskRuns", call: () => fetchTaskRuns("t1") },
  { name: "transitionTask", call: () => transitionTask({ taskId: "t1", target: "blocked" }) },
  {
    name: "planTaskRun",
    call: () => planTaskRun({ taskId: "t1", steps: [], expectedArtifacts: [], testCondition: "x" }),
  },
  { name: "startTaskRun", call: () => startTaskRun("t1", "r1") },
  { name: "stopTaskRun", call: () => stopTaskRun("t1", "r1") },
  { name: "resumeTaskRun", call: () => resumeTaskRun("t1", "r1") },
  { name: "fetchActivity", call: () => fetchActivity() },
  { name: "deleteActivity", call: () => deleteActivity() },
  {
    name: "deriveTaskPublishReadiness",
    call: () => deriveTaskPublishReadiness({ taskId: "t1" }),
  },
  {
    name: "proposeModelPlan",
    call: () => proposeModelPlan({ taskId: "t1", instruction: "TEST-ONLY" }),
  },
  { name: "forgetModelPlanSession", call: () => forgetModelPlanSession("t1") },
  { name: "fetchProof", call: () => fetchProof("t1") },
  { name: "prepareProofShare", call: () => prepareProofShare("t1") },
  {
    name: "recordProofAcceptance",
    call: () => recordProofAcceptance({ taskId: "t1", bundleSha256: "0".repeat(64), detail: "x" }),
  },
  {
    name: "recordProofPublicShare",
    call: () => recordProofPublicShare({ taskId: "t1", evidenceId: "e1", detail: "x" }),
  },
];

/**
 * Exports that read no JSON document, and why each one is here.
 *
 * `mutate` is the write chokepoint every mutating probe above already goes
 * through. The three file calls return an opaque Blob: there is no document to
 * validate, and the type system offers the caller nothing to dereference. The
 * rest touch no network at all.
 */
const NON_DOCUMENT_EXPORTS: ReadonlySet<string> = new Set([
  "ApiError",
  "toApiError",
  "hasCsrfToken",
  "resetSessionState",
  "mutate",
  "exportRecovery",
  "exportEvidence",
  "takeProofBundle",
  // The fourth file call. It returns an opaque Blob plus two digests the
  // server sent as headers; there is no document to validate and nothing for
  // a caller to dereference.
  "takeProofArtifact",
]);

/** Answer the bootstrap with a usable session and everything else with `body`. */
function stubEveryEndpoint(body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : new URL(input as URL).pathname;
      if (url === "/api/session/bootstrap") {
        return Promise.resolve(jsonResponse(bootstrapBody()));
      }
      return Promise.resolve(jsonResponse(body));
    }),
  );
}

/** Answer every path, the bootstrap included, with `body`. */
function stubEveryEndpointIncludingBootstrap(body: unknown): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(body)));
}

describe("response validation at the API boundary", () => {
  beforeEach(() => {
    resetSessionState();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("leaves no exported call outside the empty-body probe table", () => {
    const exported = Object.entries(clientModule)
      .filter(([, value]) => typeof value === "function")
      .map(([name]) => name);
    const covered = new Set([...JSON_PROBES.map((probe) => probe.name), ...NON_DOCUMENT_EXPORTS]);
    const unprobed = exported.filter((name) => !covered.has(name)).sort();

    // A new endpoint added without a probe lands here, so "it was forgotten"
    // is a failing test rather than a silently unvalidated response.
    expect(unprobed).toEqual([]);
  });

  it.each(JSON_PROBES.map((probe) => [probe.name, probe] as const))(
    "%s rejects a 200 whose body is an empty object",
    async (_name, probe) => {
      if (probe.name === "bootstrapSession") {
        // The bootstrap document is the one under test here, so it meets the
        // empty body itself rather than a valid session.
        stubEveryEndpointIncludingBootstrap({});
      } else {
        // Every other call needs the CSRF value first, and the stub answers
        // the bootstrap - and only the bootstrap - with a valid document.
        stubEveryEndpoint({});
        await bootstrapSession();
      }

      const error = await captureApiError(probe.call());
      expect(error.kind).toBe("malformed");
      expect(error.code).toBe("malformed_response");
    },
  );

  it.each([null, [], "", 0, true])("rejects a 200 whose body is %j", async (body) => {
    stubEveryEndpoint(body);
    expect((await captureApiError(fetchTasks())).kind).toBe("malformed");
  });

  it.each([
    [
      "fetchAppStatus",
      { service: {}, database: {}, session_security: {}, technocore: {} },
      () => fetchAppStatus(),
    ],
    [
      "fetchOpenCodeStatus",
      {
        configured: false,
        fingerprint_short: "",
        configured_at: null,
        updated_at: null,
        check: {},
        selected_model: "",
        auth_header_caveat: "",
        catalog: {},
        spending: {},
        protocol_context: {},
      },
      () => fetchOpenCodeStatus(),
    ],
    [
      "fetchTaskRuns",
      { task: {}, runs: [], workspace_files: [], honesty: "" },
      () => fetchTaskRuns("t1"),
    ],
    [
      "fetchProof",
      {
        task: {},
        module: {},
        artifacts: [],
        file_count: 0,
        total_bytes: 0,
        artifact_set_sha256: "",
        bundle_sha256: "",
        missing: [],
        claims: [],
        formats: [],
        hash_scope: "",
        bundle_scope: "",
        reproduction: "",
        approval_ttl_seconds: 0,
      },
      () => fetchProof("t1"),
    ],
    [
      "fetchWorkScanStatus",
      {
        honesty: "",
        capability: {},
        adapters: [],
        room_index: null,
        discovery: null,
        last_scan: null,
        never_sent_params: [],
        polling_statement: "",
        prohibition_statement: "",
      },
      () => fetchWorkScanStatus(),
    ],
    [
      // Every top-level key is present and only the list element is hollow, so
      // this one fails when list elements stop being checked.
      "fetchTasks",
      {
        tasks: [{}],
        task_count: 1,
        producible_states: [],
        unproducible_states: [],
        unproducible_detail: "",
      },
      () => fetchTasks(),
    ],
  ] as const)("%s rejects a body whose nested object is empty", async (_name, body, call) => {
    // The measured crash was on a *nested* field, so every body here carries
    // all of its top-level keys and is hollow only underneath. A guard that
    // checked names at the top level would pass every one of them.
    stubEveryEndpoint(body);
    expect((await captureApiError(call())).kind).toBe("malformed");
  });

  it.each([
    [
      "fetchActivity",
      {
        events: [{}],
        event_count: 1,
        chain_referenced_count: 0,
        retained_events: 1,
        detail: "",
      },
      () => fetchActivity(),
    ],
    [
      "fetchEvidenceRecords",
      { records: [{}], record_count: 1, chain_state: "intact", chain_detail: "", chain_link_count: 1 },
      () => fetchEvidenceRecords(),
    ],
    [
      "fetchAgentSurface",
      {
        execution: {
          arbitrary_execution_supported: false,
          reason: "execution_unavailable",
          detail: "",
          inventory: [],
        },
        ceiling: {
          max_tool_calls: 1,
          max_wall_clock_seconds: 1,
          max_concurrency: 1,
          units: [],
          refused_units: [],
          refused_units_detail: "",
          detail: "",
          agent_can_raise_ceiling: false,
        },
        tools: [{}],
        honesty: "",
        stop_statement: "",
        interrupted_runs: [],
        resumed_any: false,
      },
      () => fetchAgentSurface(),
    ],
  ] as const)("%s rejects a document whose list element is hollow", async (_name, body, call) => {
    // A list is only as checked as its elements. One row of a table the UI
    // maps over is enough to throw on the screen.
    stubEveryEndpoint(body);
    expect((await captureApiError(call())).kind).toBe("malformed");
  });

  /**
   * The closed vocabularies this package opened, checked as vocabularies.
   *
   * `test_result_state` was a bare `str` in the validator while the mirror
   * typed it as a single literal - consistent then, and not any more. It is
   * three members now and the surface renders a different thing for each, so
   * an unknown fourth is a document this client cannot draw rather than one
   * it draws wrongly: it has to be refused at the boundary instead of
   * reaching a `Record` lookup and rendering `undefined`. `acceptance.kind`
   * has the same shape and the same reason.
   *
   * Each case proves attribution rather than just rejection: the *unpatched*
   * document is accepted first, in the same test, so the refusal that follows
   * can only be the member that changed.
   */
  it.each([
    ["test_result_state", { test_result_state: "probably_passed" }],
    [
      "acceptance.kind",
      {
        acceptance: [
          { kind: "artifact_smells_right", label: "", satisfied: true, detail: "" },
        ],
      },
    ],
  ] as const)("fetchTaskRuns rejects an unknown %s member", async (_name, patch) => {
    const run = {
      id: "r1",
      task_id: "t1",
      phase: "planned",
      created_at: "2026-09-06T09:00:00Z",
      started_at: null,
      finished_at: null,
      stop_requested: false,
      plan_sha256: "",
      test_condition: "",
      acceptance: [],
      test_result_state: "not_implemented",
      test_result_detail: "",
      expected_artifacts: [],
      steps: [],
      tool_calls_used: 0,
      elapsed_ms: 0,
      max_tool_calls: 1,
      max_wall_clock_seconds: 1,
      concurrency: 1,
      detail: "",
    };
    const task = {
      id: "t1",
      module_id: "",
      source_id: "",
      content_sha256: "",
      source_version_id: "",
      title: "",
      state: "awaiting_approval",
      state_detail: "",
      created_at: "2026-09-06T09:00:00Z",
      updated_at: "2026-09-06T09:00:00Z",
      evidence_fields: [],
      ready_to_publish: false,
      blocking_fields: [],
      public_share_available: false,
      public_share_detail: "",
      budget_available: false,
      budget_detail: "",
    };
    const document = (body: unknown) => ({
      task,
      runs: [body],
      workspace_files: [],
      honesty: "",
    });

    stubEveryEndpoint(document(run));
    await bootstrapSession();
    await expect(fetchTaskRuns("t1")).resolves.toBeDefined();

    stubEveryEndpoint(document({ ...run, ...patch }));
    expect((await captureApiError(fetchTaskRuns("t1"))).kind).toBe("malformed");
  });
});

describe("the model planning outcome vocabulary", () => {
  beforeEach(() => {
    resetSessionState();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const TASK = {
    id: "t1",
    module_id: "",
    source_id: "",
    content_sha256: "",
    source_version_id: "",
    title: "",
    state: "awaiting_approval",
    state_detail: "",
    created_at: "2026-09-06T09:00:00Z",
    updated_at: "2026-09-06T09:00:00Z",
    evidence_fields: [],
    ready_to_publish: false,
    blocking_fields: [],
    public_share_available: false,
    public_share_detail: "",
    budget_available: false,
    budget_detail: "",
  };

  const proposal = (outcome: string) => ({
    outcome,
    run_id: "",
    detail: "",
    model_calls_used: 0,
    max_model_calls: 3,
    usage_detail: "",
    closing_text: "",
    tool_call_provenance: "",
    task: TASK,
    runs: [],
    model_can_start_a_run: false,
  });

  /**
   * The two outcomes the truncation fix added, at the boundary that has to
   * let them through.
   *
   * `truncated` and `inconclusive` are the whole point of that fix: a turn
   * that was cut off, and a turn whose ending the build could not read, stop
   * being reported as "the model chose to stop". A validator that still
   * counts five members turns each of them into a `malformed` refusal, so the
   * person never sees the cut at all - the exact failure the fix was written
   * to remove, moved one layer outwards.
   */
  it.each(["truncated", "inconclusive"] as const)(
    "accepts a %s outcome rather than refusing the document",
    async (outcome) => {
      stubEveryEndpoint(proposal(outcome));
      await bootstrapSession();
      await expect(proposeModelPlan({ taskId: "t1" })).resolves.toMatchObject({ outcome });
    },
  );

  it("still refuses an outcome nobody defined", async () => {
    stubEveryEndpoint(proposal("ran"));
    await bootstrapSession();
    expect((await captureApiError(proposeModelPlan({ taskId: "t1" }))).kind).toBe("malformed");
  });
});

describe("what a suggestion says a model can read", () => {
  beforeEach(() => {
    resetSessionState();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const SUGGESTION = {
    task_id: "3c1f9a7b5e2d84660a1b2c3d4e5f6071",
    module_id: "work_scan",
    source_id: "public_room_scan",
    source_version_id: "9f8e7d6c5b4a3928",
    state: "suggested",
    detail: "",
    request_file: "oda-istegi.md",
    request_file_detail: "",
  };

  /**
   * A scanned request is stored as a digest, so what a model can read of it is
   * a workspace file - and these two fields are how a document says whether
   * that file is there. A body without them is one from a build that kept the
   * digest and nothing else; drawing it would show a suggestion as though its
   * text were readable when it is not, so it is refused at the boundary.
   *
   * The unpatched document is accepted first, in the same test, so the refusal
   * that follows can only be the field that was removed.
   */
  it.each(["request_file", "request_file_detail"] as const)(
    "refuses a suggestion with no %s",
    async (field) => {
      stubEveryEndpoint(SUGGESTION);
      await bootstrapSession();
      await expect(suggestWorkScanCandidate("c1")).resolves.toBeDefined();

      const without: Record<string, unknown> = { ...SUGGESTION };
      delete without[field];
      stubEveryEndpoint(without);
      expect((await captureApiError(suggestWorkScanCandidate("c1"))).kind).toBe("malformed");
    },
  );
});
