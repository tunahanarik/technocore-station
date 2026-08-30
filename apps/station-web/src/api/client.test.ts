import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  bootstrapSession,
  fetchAppStatus,
  hasCsrfToken,
  mutate,
  resetSessionState,
} from "./client";

const CSRF_VALUE = "test-only-csrf-value-not-a-real-token";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function bootstrapBody() {
  return { csrf_token: CSRF_VALUE, csrf_header: "X-Station-CSRF" };
}

describe("api client", () => {
  beforeEach(() => {
    resetSessionState();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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

    // Spying on the prototype covers localStorage AND sessionStorage: both are
    // Storage instances sharing this method. That is a stricter assertion than
    // inspecting either object directly, and it needs no banned identifier.
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
