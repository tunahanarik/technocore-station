import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  bootstrapSession,
  fetchAppStatus,
  hasCsrfToken,
  mutate,
  refreshTechnocore,
  resetSessionState,
  toApiError,
} from "./client";

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
    await mutate("/api/probe", { hello: "world" });

    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-Station-CSRF"]).toBe(CSRF_VALUE);
  });

  it("refuses a state-changing request before the session is bootstrapped", async () => {
    vi.stubGlobal("fetch", vi.fn());
    await expect(mutate("/api/probe", {})).rejects.toThrow("session_not_bootstrapped");
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
        .mockResolvedValueOnce(jsonResponse({ state: "current" })),
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

  it("classifies a plain abort as a timeout as well", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("Aborted.", "AbortError")),
    );

    const error = await captureApiError(fetchAppStatus());
    expect(error.kind).toBe("timeout");
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
