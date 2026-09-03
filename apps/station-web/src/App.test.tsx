import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { resetSessionState } from "./api/client";
import type { AppStatus, ConformanceStatus, IdentityStatus, TechnocoreStatus } from "./api/types";

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
    // A freshly launched Station has contacted nobody, so this is the honest
    // opening state rather than a placeholder.
    state: "never_checked",
    write_available_from_stage: 4,
    detail: "Resmi kaynaklar bu oturumda henuz denetlenmedi.",
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

//: TEST-ONLY monitoring fixture: nothing checked yet, nothing fetched.
const TECHNOCORE_NEVER_CHECKED: TechnocoreStatus = {
  state: "never_checked",
  manifest_current: false,
  checked_at: null,
  last_attempt_at: null,
  last_success_at: null,
  reasons: [],
  sources: [],
  fields: [],
  critical_mismatch_count: 0,
  critical_unevaluable_count: 0,
  warning_count: 0,
  origin: "",
};

//: TEST-ONLY conformance fixture. Short digest on purpose: no 64-hex run
//: may ever reach the DOM, and a fixture carrying one would hide a leak.
const CONFORMANT: ConformanceStatus = {
  passed: true,
  checks: [],
  failures: [],
  capabilities: [],
  bundle_digest: "688c6e4dcf14eeed",
  bundle_digest_short: "688c6e4dcf14",
  bundle_vectors: 104,
  upstream_commit: "7707cb63ebf638e8ef0cf59d1364818b9fef7d24",
  upstream_commit_short: "7707cb6",
  package_version: "0.3.0",
  python_version: "3.12.11",
  unicode_version: "15.0.0",
  bundle_unicode_version: "15.0.0",
  unicode_version_matches: true,
};

const VISIBLE_SECTIONS = [
  "Genel Bakis",
  "Kimlik ve Guvenlik",
  "Olustur ve Dogrula",
  "Kaynaklar",
  "Kanitlar",
  "Ayarlar ve Yardim",
] as const;

const HIDDEN_SECTIONS = ["Is Tara", "Gorevler", "Aktivite"] as const;

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
            : new URL(input.url, "https://station.invalid").pathname;
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
      if (url === "/api/write-gate") return Promise.resolve(jsonResponse(NO_IDENTITY.gate));
      if (url === "/api/technocore/status")
        return Promise.resolve(jsonResponse(TECHNOCORE_NEVER_CHECKED));
      if (url === "/api/conformance/status") return Promise.resolve(jsonResponse(CONFORMANT));
      return Promise.resolve(jsonResponse({ detail: "not_found" }, 404));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetSessionState();
});

describe("App shell", () => {
  it("renders a left navigation with exactly the ready sections (ADR-0001)", async () => {
    stubBackend();
    render(<App />);

    const nav = await screen.findByRole("navigation", { name: "Ana bolumler" });
    const labels = within(nav)
      .getAllByRole("button")
      .map((button) => button.textContent?.replace(" (secili bolum)", "") ?? "");
    expect(labels).toEqual([...VISIBLE_SECTIONS]);
  });

  it("never shows a section that is not ready", async () => {
    // Is Tara, Gorevler and Aktivite stay registered for packages H1/H2 but
    // must not appear as empty menu items before they exist.
    stubBackend();
    render(<App />);
    await screen.findByRole("navigation", { name: "Ana bolumler" });

    for (const hidden of HIDDEN_SECTIONS) {
      expect(screen.queryByText(hidden)).toBeNull();
    }
  });

  it("uses a navigation landmark, not tabs (ADR-0001 replaced ADR-002 tabs)", async () => {
    stubBackend();
    render(<App />);
    await screen.findByRole("navigation", { name: "Ana bolumler" });

    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.queryAllByRole("tablist")).toHaveLength(0);
  });

  it("starts on Genel Bakis and marks it with aria-current", async () => {
    stubBackend();
    render(<App />);

    const overviewButton = await screen.findByRole("button", { name: /Genel Bakis/ });
    expect(overviewButton).toHaveAttribute("aria-current", "page");
    // Overview composition is mounted.
    expect(await screen.findByText("Technocore durumu")).toBeInTheDocument();
  });

  it("mounts only the selected section and moves aria-current on click", async () => {
    stubBackend();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Technocore durumu");

    await user.click(screen.getByRole("button", { name: "Kimlik ve Guvenlik" }));

    expect(await screen.findByText("Kimlik olusturulmadi")).toBeInTheDocument();
    // The overview is unmounted, not hidden.
    expect(screen.queryByText("Technocore durumu")).toBeNull();
    expect(screen.getByRole("button", { name: /Kimlik ve Guvenlik/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("button", { name: /Genel Bakis/ })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("is operable with the keyboard: tab to a section, Enter selects it", async () => {
    stubBackend();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Technocore durumu");

    // Tab order: collapse toggle, then the nav buttons in order.
    await user.tab();
    expect(screen.getByRole("button", { name: "Menuyu daralt" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: /Genel Bakis/ })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Kimlik ve Guvenlik" })).toHaveFocus();

    await user.keyboard("{Enter}");

    expect(await screen.findByText("Kimlik olusturulmadi")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kimlik ve Guvenlik/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("collapses the navigation without losing the selection", async () => {
    stubBackend();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Technocore durumu");

    await user.click(screen.getByRole("button", { name: "Kimlik ve Guvenlik" }));
    await screen.findByText("Kimlik olusturulmadi");

    const toggle = screen.getByRole("button", { name: "Menuyu daralt" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.click(toggle);

    const reopen = screen.getByRole("button", { name: "Menuyu ac" });
    expect(reopen).toHaveAttribute("aria-expanded", "false");
    // The selected section stays mounted while the menu is collapsed.
    expect(screen.getByText("Kimlik olusturulmadi")).toBeInTheDocument();

    await user.click(reopen);
    expect(screen.getByRole("button", { name: /Kimlik ve Guvenlik/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("keeps the navigation landmark and every section name while collapsed", async () => {
    // Collapsing narrows the menu for a sighted user. Unmounting the landmark
    // took the whole menu away from a screen-reader user, which is a
    // different and much larger change than "narrower".
    stubBackend();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Technocore durumu");

    await user.click(screen.getByRole("button", { name: "Menuyu daralt" }));

    const nav = screen.getByRole("navigation", { name: "Ana bolumler" });
    const names = within(nav)
      .getAllByRole("button")
      .map((button) => button.textContent?.replace(" (secili bolum)", "") ?? "");
    // The visible initial is aria-hidden; the accessible name stays whole.
    expect(names).toEqual(VISIBLE_SECTIONS.map((label) => `${label.slice(0, 1)}${label}`));
    for (const label of VISIBLE_SECTIONS) {
      expect(within(nav).getByRole("button", { name: new RegExp(`^${label}`) })).toBeInTheDocument();
    }
  });

  it("points the collapse toggle at the region it controls", async () => {
    stubBackend();
    render(<App />);

    const nav = await screen.findByRole("navigation", { name: "Ana bolumler" });
    const toggle = screen.getByRole("button", { name: "Menuyu daralt" });
    expect(toggle).toHaveAttribute("aria-controls", nav.id);
    expect(nav.id).not.toBe("");
  });

  it("selects a section from the collapsed menu", async () => {
    stubBackend();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Technocore durumu");

    await user.click(screen.getByRole("button", { name: "Menuyu daralt" }));
    const nav = screen.getByRole("navigation", { name: "Ana bolumler" });
    await user.click(within(nav).getByRole("button", { name: /^Kimlik ve Guvenlik/ }));

    expect(await screen.findByText("Kimlik olusturulmadi")).toBeInTheDocument();
  });

  it("reports Technocore as not yet checked on a fresh launch", async () => {
    // "Denetlenmedi" is the accurate opening value: Station contacts nobody
    // until the user asks, so neither "connected" nor "disconnected" is true.
    stubBackend();
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Denetlenmedi")).toBeInTheDocument();
    });
  });

  it("surfaces an auth failure with the launcher guidance and no retry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ detail: "session_expired" }, 401))),
    );

    render(<App />);

    expect(await screen.findByText("Yerel cekirdege baglanilamadi")).toBeInTheDocument();
    const regions = screen.getAllByRole("alert");
    const shellRegion = regions.find((region) =>
      region.textContent?.includes("Yerel cekirdege baglanilamadi"),
    );
    expect(shellRegion).toBeDefined();
    expect(shellRegion?.textContent).toContain("launcher");
    expect(shellRegion?.textContent).toContain("Kod: session_expired");
    expect(within(shellRegion as HTMLElement).queryByRole("button", { name: "Yeniden dene" })).toBeNull();
  });

  it("offers a retry when the local core is unreachable, and retries", async () => {
    const fetchMock = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App />);

    expect(await screen.findByText("Yerel cekirdege baglanilamadi")).toBeInTheDocument();
    const shellRegion = screen
      .getAllByRole("alert")
      .find((region) => region.textContent?.includes("Yerel cekirdege baglanilamadi"));
    const retry = within(shellRegion as HTMLElement).getByRole("button", {
      name: "Yeniden dene",
    });

    const callsBefore = fetchMock.mock.calls.length;
    await user.click(retry);
    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("disables the shell retry while the retry is in flight", async () => {
    // The shell already tracked a loading flag; it just never reached the
    // retry button, so a stuck connection could be retried five times over.
    let bootstrapCalls = 0;
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    // Routed by URL: the overview section fires its own reads on mount, so
    // counting raw calls would count the wrong ones.
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : new URL(input as URL).pathname;
        if (url === "/api/session/bootstrap") {
          bootstrapCalls += 1;
          if (bootstrapCalls === 1) return Promise.reject(new TypeError("Failed to fetch"));
          return gate.then(() =>
            jsonResponse({
              csrf_token: "test-only-value-not-a-real-token",
              csrf_header: "X-Station-CSRF",
            }),
          );
        }
        if (url === "/api/app/status") return gate.then(() => jsonResponse(HEALTHY_STATUS));
        if (url === "/api/identity") return Promise.resolve(jsonResponse(NO_IDENTITY));
        if (url === "/api/technocore/status")
          return Promise.resolve(jsonResponse(TECHNOCORE_NEVER_CHECKED));
        return Promise.resolve(jsonResponse(CONFORMANT));
      }),
    );

    const user = userEvent.setup();
    render(<App />);

    const region = await screen.findByText("Yerel cekirdege baglanilamadi");
    const alert = region.closest("[role='alert']") as HTMLElement;
    await user.click(within(alert).getByRole("button", { name: "Yeniden dene" }));

    const busy = await screen.findByRole("button", { name: "Yeniden deneniyor..." });
    expect(busy).toBeDisabled();

    // A second activation while pending must not start another bootstrap.
    expect(bootstrapCalls).toBe(2);
    await user.click(busy);
    expect(bootstrapCalls).toBe(2);

    release();
    await waitFor(() => {
      expect(screen.queryByText("Yerel cekirdege baglanilamadi")).toBeNull();
    });
  });

  it("still shows the identity surface inside the shell", async () => {
    stubBackend();
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("navigation", { name: "Ana bolumler" });

    await user.click(screen.getByRole("button", { name: "Kimlik ve Guvenlik" }));
    expect(await screen.findByText("Kimlik olusturulmadi")).toBeInTheDocument();
  });
});
