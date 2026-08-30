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

import type { AppStatus, SessionBootstrap } from "./types";

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
    throw new ApiError(response.status, `request_failed_${response.status}`);
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
