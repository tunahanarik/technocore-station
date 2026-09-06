import { useEffect, useState } from "react";

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchAppStatus } from "../api/client";
import type { AppStatus } from "../api/types";
import { SectionBoundary } from "./SectionBoundary";
import { SystemStatusBar } from "./SystemStatusBar";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * The surface the F5 crash was reported on, wired the way the app wires it:
 * the real client reads the real status document, and the real status bar
 * renders it inside the section boundary, beside navigation.
 *
 * A synthetic component that throws on purpose is a unit test of the boundary
 * (there is one below, and it stays). It is not this defect: the reported
 * failure came from a *successful* response whose nested objects were absent,
 * and only a test that drives the client and the component together can show
 * which of the two layers keeps the screen standing.
 */
function StatusSurface() {
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetchAppStatus()
      .then((value) => {
        if (alive) setStatus(value);
      })
      .catch(() => {
        // The honest empty state, exactly as the pages do it.
        if (alive) setStatus(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      <nav>Gezinme</nav>
      <SectionBoundary>
        <SystemStatusBar status={status} loading={loading} />
      </SectionBoundary>
    </>
  );
}

function jsonOk(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("the status surface under a malformed successful response", () => {
  it.each([
    ["an empty object", {}],
    ["objects with no fields in them", { service: {}, database: {}, session_security: {}, technocore: {} }],
  ])("keeps a 200 carrying %s away from the status bar", async (_name, body) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonOk(body)));

    render(<StatusSurface />);

    // The honest "we could not read it" state, produced by the component's own
    // null branch - not by a crash that something caught.
    expect(await screen.findAllByText("Ulasilamiyor")).not.toHaveLength(0);
    // The boundary is the net, and the net must stay empty: if it has fired,
    // the malformed document reached React and the client let it through.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText("render_failed")).not.toBeInTheDocument();
  });

  it("shows a status document that is actually complete", async () => {
    const status: AppStatus = {
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
        state: "never_checked",
        write_available_from_stage: 4,
        detail: "Resmi kaynaklar bu oturumda henuz denetlenmedi.",
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonOk(status)));

    render(<StatusSurface />);

    // Guards the fix from the other direction: a validator strict enough to
    // refuse a real document would pass the test above and break the app.
    expect(await screen.findByText("Calisiyor")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("the section boundary", () => {
  it("contains the real status bar's failure without dropping navigation", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    // The exact payload the measurement crashed on, forced past the type
    // system the way a `data as T` cast used to force it past the client.
    const malformed = {} as unknown as AppStatus;

    render(
      <>
        <nav>Gezinme</nav>
        <SectionBoundary>
          <SystemStatusBar status={malformed} loading={false} />
        </SectionBoundary>
      </>,
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("render_failed");
    });
    // Navigation stands, so the user can leave the broken section.
    expect(screen.getByRole("navigation")).toHaveTextContent("Gezinme");
    // The raw exception never becomes screen text.
    expect(screen.queryByText(/Cannot read properties/)).not.toBeInTheDocument();
    expect(screen.queryByText(/TypeError/)).not.toBeInTheDocument();
  });

  it("contains a render failure without displaying its sensitive message", () => {
    // A unit test of the boundary's own contract: whatever a section throws,
    // the message does not reach the screen. Deliberately synthetic - the
    // regression test for the reported defect is the one above.
    vi.spyOn(console, "error").mockImplementation(() => {});
    function Broken(): never {
      throw new Error("TEST-ONLY private diagnostic");
    }
    render(
      <>
        <nav>Gezinme</nav>
        <SectionBoundary>
          <Broken />
        </SectionBoundary>
      </>,
    );
    expect(screen.getByRole("navigation")).toHaveTextContent("Gezinme");
    expect(screen.getByRole("alert")).toHaveTextContent("render_failed");
    expect(screen.queryByText(/private diagnostic/)).not.toBeInTheDocument();
  });
});
