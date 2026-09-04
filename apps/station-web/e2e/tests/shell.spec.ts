/**
 * The shell: how the application comes up, and what it is allowed to talk to.
 *
 * Everything here needs a real browser. The one-shot session handoff is a
 * 303 plus a `Set-Cookie` that jsdom never performs; the outbound meter
 * measures requests a real network stack made; and the data-directory
 * assertion is about the process the browser is actually talking to.
 */

import { expect, openApp, test } from "../fixtures";
import { mintBootstrapToken } from "../harness/station";

test.describe("session handoff and isolation", () => {
  test("the one-shot token URL redirects to a working session", async ({ page, station }) => {
    await openApp(page);

    await expect(page).toHaveURL(`${station.origin}/`);
    // The URL that carried the token is gone from the address bar. A token
    // left in history would be a token in the browser's on-disk profile.
    expect(page.url()).not.toContain("/session/");
  });

  test("the session cookie is HttpOnly, SameSite=Strict and loopback-scoped", async ({
    page,
    context,
    station,
  }) => {
    await openApp(page);

    const cookies = await context.cookies(station.origin);
    const session = cookies.find((cookie) => cookie.name === "station_session");
    expect(session, "the handoff must have set a session cookie").toBeDefined();
    expect(session?.httpOnly).toBe(true);
    expect(session?.sameSite).toBe("Strict");
    expect(session?.domain).toBe("127.0.0.1");
    expect(session?.path).toBe("/");
    // `Secure` is deliberately absent on loopback HTTP (IMP-103, risk A1-R3).
    // Asserting it here keeps the documented decision and the shipped
    // behaviour from drifting apart in either direction.
    expect(session?.secure).toBe(false);
  });

  test("a spent bootstrap token cannot be replayed", async ({ page, context, station }) => {
    const token = await mintBootstrapToken();
    const handoff = `${station.origin}/session/${token}`;

    await page.goto(handoff, { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(`${station.origin}/`);

    // Replay the same URL from a context with no session at all. The token
    // store consumed it on first use, so the second attempt is a 404 - the
    // same answer an unknown or expired token gets (routes/session.py).
    const clean = await context.request.get(handoff, { maxRedirects: 0 });
    expect(clean.status()).toBe(404);
    expect(clean.headers()["set-cookie"]).toBeUndefined();
  });

  test("the run never touches the production data directory", async ({ station }) => {
    const localAppData = process.env.LOCALAPPDATA;
    expect(localAppData, "this is a Windows-only product").toBeTruthy();

    const production = `${String(localAppData)}\\TechnocoreStation`.toLowerCase();
    const actual = station.data_dir.toLowerCase();

    expect(actual).not.toBe(production);
    expect(actual.startsWith(production)).toBe(false);
    // Positive half: it is a temp directory this run created.
    expect(actual).toContain("station-e2e-");
  });

  test("the server binds loopback on an ephemeral port", async ({ station }) => {
    expect(station.host).toBe("127.0.0.1");
    expect(station.origin).toBe(`http://127.0.0.1:${String(station.port)}`);
    // The ephemeral range; the number is chosen by the OS, never by us.
    expect(station.port).toBeGreaterThan(1024);
  });
});

test.describe("outbound network", () => {
  test("the guard is live: an off-origin request is refused and counted", async ({
    context,
    outbound,
  }) => {
    // A negative control on a throwaway page. Without it, "zero external
    // requests" everywhere else could equally mean the meter is broken.
    //
    // It cannot be provoked from the application page: the app's own CSP
    // refuses the connection before a request is ever issued, which is the
    // stronger property and is asserted separately in csp.spec.ts.
    outbound.expectBlocked(1);
    const scratch = await context.newPage();

    await expect(scratch.goto("https://technocore.chat/healthz")).rejects.toThrow(
      /ERR_BLOCKED_BY_CLIENT|net::ERR/,
    );

    expect(outbound.blocked).toHaveLength(1);
    expect(outbound.blocked[0]).toContain("technocore.chat");
    await scratch.close();
  });

  test("the backend itself made no outbound attempt during the run", async ({ page, station }) => {
    await openApp(page);

    // Browser-side counting cannot see a request the *server* would make, so
    // the server is asked what it did. `never_checked` and `never_fetched`
    // are only reachable if no manifest audit and no catalog read ever ran:
    // both record an attempt timestamp even when the attempt fails.
    const technocore = await page.evaluate(async () =>
      (await fetch("/api/technocore/status", { credentials: "same-origin" })).json(),
    );
    expect(technocore).toMatchObject({ state: "never_checked", last_attempt_at: null });

    const opencode = await page.evaluate(async () =>
      (await fetch("/api/opencode/status", { credentials: "same-origin" })).json(),
    );
    expect(opencode).toMatchObject({ catalog: { state: "never_fetched", fetched_at: null } });

    expect(station.origin).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
  });
});
