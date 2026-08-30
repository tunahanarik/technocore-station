import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { resetSessionState } from "./api/client";
import type { AppStatus, IdentityStatus } from "./api/types";

const HEALTHY_STATUS: AppStatus = {
  service: { state: "running", stage: 2, mode: "production" },
  database: {
    state: "ready",
    journal_mode: "wal",
    foreign_keys: true,
    schema_revision: "0002",
  },
  session_security: {
    state: "active",
    cookie_http_only: true,
    cookie_same_site: "strict",
    cookie_secure: false,
    csrf_required: true,
    transport: "loopback-http",
  },
  technocore: {
    state: "not_connected",
    available_from_stage: 3,
    detail: "Asama 3 kapsaminda.",
  },
};

const NO_IDENTITY: IdentityStatus = {
  state: "no_identity",
  identity: null,
  recovery: {
    exported_at: null,
    verified_at: null,
    file_fingerprint: null,
    kdf: null,
    kdf_time_cost: null,
    kdf_memory_kib: null,
    kdf_parallelism: null,
  },
  capability: {
    platform_supported: true,
    dpapi_available: true,
    aead_available: true,
    usable: true,
    detail: "DPAPI ve AEAD kullanilabilir.",
  },
  gate: {
    allowed: false,
    identity_ready: false,
    blocking_reasons: ["identity_present"],
    checks: [
      { key: "identity_present", state: "blocked", detail: "Aktif bir kimlik gerekli.", stage: "2" },
    ],
  },
  default_protection: "dpapi+passphrase",
  min_passphrase_chars: 16,
  create_confirmation_text: "KİMLİK OLUŞTUR",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Route the mock by URL rather than by call order.
 *
 * Order-based mocks break as soon as a page adds a request, and the failure
 * looks like a component bug rather than a stale test.
 */
function stubBackend(overrides: Record<string, Response> = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.pathname
            : new URL(input.url, "http://127.0.0.1").pathname;
      const override = overrides[url];
      if (override) return Promise.resolve(override.clone());
      if (url === "/api/session/bootstrap") {
        return Promise.resolve(
          jsonResponse({
            csrf_token: "test-only-value-not-a-real-token",
            csrf_header: "X-Station-CSRF",
          }),
        );
      }
      if (url === "/api/app/status") return Promise.resolve(jsonResponse(HEALTHY_STATUS));
      if (url === "/api/identity") return Promise.resolve(jsonResponse(NO_IDENTITY));
      return Promise.resolve(jsonResponse({ detail: "not_found" }, 404));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetSessionState();
});

describe("App shell", () => {
  it("bootstraps the session and renders the three MVP surfaces", async () => {
    stubBackend();
    render(<App />);

    expect(await screen.findByRole("tab", { name: "Identity" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Compose & Verify" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Evidence & Sources" })).toBeInTheDocument();
  });

  it("reports Technocore as not connected", async () => {
    stubBackend();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Bagli degil")).toBeInTheDocument();
    });
  });

  it("uses tabs rather than a sidebar", async () => {
    stubBackend();
    const { container } = render(<App />);
    await screen.findByRole("tab", { name: "Identity" });

    expect(container.querySelector("aside")).toBeNull();
  });

  it("surfaces a connection error when the local core is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ detail: "x" }, 401))),
    );

    render(<App />);

    expect(await screen.findByText("Yerel cekirdege baglanilamadi")).toBeInTheDocument();
  });

  it("still shows the Stage 2 identity surface inside the shell", async () => {
    stubBackend();
    render(<App />);

    expect(await screen.findByText("Kimlik olusturulmadi")).toBeInTheDocument();
  });
});
