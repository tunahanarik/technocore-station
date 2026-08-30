import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { resetSessionState } from "./api/client";
import type { AppStatus } from "./api/types";

const HEALTHY_STATUS: AppStatus = {
  service: { state: "running", stage: 1, mode: "production" },
  database: {
    state: "ready",
    journal_mode: "wal",
    foreign_keys: true,
    schema_revision: "0001",
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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubHealthyBackend(): void {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          csrf_token: "test-only-value-not-a-real-token",
          csrf_header: "X-Station-CSRF",
        }),
      )
      .mockResolvedValueOnce(jsonResponse(HEALTHY_STATUS)),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetSessionState();
});

describe("App shell", () => {
  it("bootstraps the session and renders the three MVP surfaces", async () => {
    stubHealthyBackend();

    render(<App />);

    expect(await screen.findByRole("tab", { name: "Identity" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Compose & Verify" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Evidence & Sources" })).toBeInTheDocument();
  });

  it("reports Technocore as not connected", async () => {
    stubHealthyBackend();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Bagli degil")).toBeInTheDocument();
    });
  });

  it("uses tabs rather than a sidebar", async () => {
    stubHealthyBackend();

    const { container } = render(<App />);
    await screen.findByRole("tab", { name: "Identity" });

    expect(container.querySelector("aside")).toBeNull();
  });

  it("surfaces a connection error when the local core is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "x" }, 401)));

    render(<App />);

    expect(await screen.findByText("Yerel cekirdege baglanilamadi")).toBeInTheDocument();
  });
});
