/**
 * Shared fixtures: the session handoff, the console ledger and the outbound
 * network meter.
 *
 * The outbound meter is the part worth reading twice. ADR-0006 2 says these
 * tests reach `technocore.chat` and `opencode.ai` zero times. "We did not
 * click anything that would" is an argument, not evidence, so this file both
 * **blocks** every request that leaves the application origin and **counts**
 * every request that leaves it.
 *
 * Which channels are actually covered, and which are not
 * ------------------------------------------------------
 * An earlier version of this comment said the listener was one "routing
 * cannot bypass". That was true of the page it was attached to and false of
 * everything else, and a review demonstrated both halves:
 *
 * * a second page opened with `context.newPage()` **was** blocked by
 *   `context.route`, but its requests never reached `seen`, because the
 *   listener was `page.on(...)` on the one page the fixture happened to
 *   receive. The counter was narrower than the blocker;
 * * `context.request` - Playwright's `APIRequestContext` - was neither
 *   blocked nor counted. `context.route` does not intercept it at all, and
 *   the probe's request went out as far as a real DNS lookup. `shell.spec.ts`
 *   already uses that channel, so this was not a hypothetical.
 *
 * What is covered now:
 *
 * 1. **every page in the context**, counted from `context.on("request")` and
 *    blocked by `context.route("**\/*")`;
 * 2. **`context.request` and `page.request`**, wrapped below so an off-origin
 *    call is counted *and* refused before it is issued;
 * 3. **the server's own outbound attempts**, which no browser-side listener
 *    can see and which `shell.spec.ts` therefore reads back from the backend.
 *
 * What is still not covered, and is refused in source instead: Playwright's
 * standalone `request` fixture and `playwright.request.newContext()`, which
 * build an `APIRequestContext` this file never touches.
 * `harness/discipline.ts` fails the run if a spec uses either.
 *
 * Both counters have a negative control in `shell.spec.ts`. Not just the
 * blocker: a meter that is broken and a suite that is quiet look identical,
 * so `seen`/`external()` is provoked deliberately too.
 */

import {
  expect,
  test as base,
  type APIRequestContext,
  type Page,
  type TestInfo,
} from "@playwright/test";

import { readHandshake, sessionUrl, type Handshake } from "./harness/station";

/** Schemes a page uses internally; they never leave the machine. */
const LOCAL_SCHEMES = ["about:", "data:", "blob:", "chrome-error:"];

export class OutboundLedger {
  /** Every request URL any page in the context issued, in order. */
  readonly seen: string[] = [];
  /** Requests the guard refused because they left the app origin. */
  readonly blocked: string[] = [];
  private expectedBlocked = 0;
  private expectedExternal = 0;

  constructor(private readonly origin: string) {}

  isLocal(url: string): boolean {
    return LOCAL_SCHEMES.some((scheme) => url.startsWith(scheme)) || url.startsWith(this.origin);
  }

  /** Off-origin URLs something actually asked for, whatever routing did next. */
  external(): string[] {
    return this.seen.filter((url) => !this.isLocal(url));
  }

  /** Record a request the browser-side listener cannot see (an API call). */
  record(url: string): void {
    this.seen.push(url);
  }

  /** Refuse an off-origin API call, and count the refusal. */
  refuse(url: string): void {
    this.blocked.push(url);
  }

  /**
   * Declare that this test provokes `count` blocked requests on purpose.
   *
   * Only the guard's own self-tests use this, and they provoke them from a
   * throwaway page or a throwaway API call rather than from the application.
   * Every other test asserts a flat zero on both counters.
   */
  expectBlocked(count: number): void {
    this.expectedBlocked = count;
  }

  /**
   * Declare that this test issues `count` off-origin requests on purpose.
   *
   * Separate from {@link expectBlocked} because the two counters answer
   * different questions - "was it stopped" and "was it seen" - and a
   * negative control for one is not a negative control for the other. That
   * distinction is the whole finding: the blocker had a self-test and the
   * meter did not.
   */
  expectExternal(count: number): void {
    this.expectedExternal = count;
  }

  assertClean(): void {
    expect(
      this.external(),
      "nothing in this context may request anything outside the local origin",
    ).toHaveLength(this.expectedExternal);
    expect(this.blocked, "off-origin requests refused by the guard").toHaveLength(
      this.expectedBlocked,
    );
  }
}

/**
 * Count and gate one `APIRequestContext`.
 *
 * `context.route` does not intercept these calls, so the only place to stand
 * is in front of the methods themselves. Own properties are assigned over the
 * prototype's, which is enough: the object is created fresh per test context
 * and thrown away with it.
 *
 * An off-origin call is rejected instead of aborted. There is no route to
 * abort it in, and a rejection is the honest shape anyway - the request was
 * never issued at all.
 */
function meterApiRequests(api: APIRequestContext, ledger: OutboundLedger): void {
  const methods = ["fetch", "get", "post", "put", "patch", "delete", "head"] as const;
  const target = api as unknown as Record<string, (...args: unknown[]) => unknown>;

  for (const method of methods) {
    const bound = target[method];
    if (bound === undefined) continue;
    const original = bound.bind(api);
    target[method] = (...args: unknown[]): unknown => {
      const url = typeof args[0] === "string" ? args[0] : String(args[0]);
      ledger.record(url);
      if (!ledger.isLocal(url)) {
        ledger.refuse(url);
        // A rejected promise rather than a synchronous throw: these methods
        // are `async` in Playwright's API and a caller writes `await`, so a
        // refusal has to arrive the way any other failure would.
        return Promise.reject(new Error(`blocked by the outbound guard: ${url}`));
      }
      return original(...args);
    };
  }
}

export class ConsoleLedger {
  readonly errors: string[] = [];
  readonly warnings: string[] = [];
  readonly pageErrors: string[] = [];
  private readonly allowed: RegExp[] = [];

  /**
   * Permit one console error this test provokes on purpose.
   *
   * Used only where the error *is* the evidence - a CSP refusal that proves
   * the policy is enforced. It never silences a class of message: the pattern
   * has to match the specific line, and everything else still fails the test.
   */
  allow(pattern: RegExp): void {
    this.allowed.push(pattern);
  }

  private unexpected(lines: string[]): string[] {
    return lines.filter((line) => !this.allowed.some((pattern) => pattern.test(line)));
  }

  /** Console messages naming a Content Security Policy refusal. */
  cspViolations(): string[] {
    return [...this.errors, ...this.warnings].filter((line) =>
      /content security policy|refused to (load|apply|execute)/i.test(line),
    );
  }

  assertClean(): void {
    expect(this.unexpected(this.pageErrors), "uncaught page errors").toHaveLength(0);
    expect(this.unexpected(this.errors), "console errors").toHaveLength(0);
  }
}

interface StationFixtures {
  readonly station: Handshake;
  readonly outbound: OutboundLedger;
  readonly consoleLog: ConsoleLedger;
}

export const test = base.extend<StationFixtures>({
  station: async ({}, use) => {
    await use(await readHandshake());
  },

  outbound: [
    async ({ context, page, station }, use) => {
      const ledger = new OutboundLedger(station.origin);

      // The measurement, at **context** level. A `request` event fires for
      // every request any page in the context makes, including ones a
      // page-level route later fulfils, so this cannot be silenced by a mock
      // a test registers afterwards - and, unlike the `page.on` listener it
      // replaces, it does not stop at the one page the fixture was handed.
      context.on("request", (request) => {
        ledger.record(request.url());
      });

      // The enforcement. Registered on the context before any test body runs,
      // so a same-origin mock registered later on the page still wins and
      // still gets counted above.
      await context.route("**/*", async (route) => {
        const url = route.request().url();
        if (ledger.isLocal(url)) {
          await route.fallback();
          return;
        }
        ledger.blocked.push(url);
        await route.abort("blockedbyclient");
      });

      // The channel neither of the two above can reach. `context.route` does
      // not intercept an `APIRequestContext`, and `context.on("request")` is
      // a page event; a review's probe went out to a real DNS lookup through
      // exactly this gap.
      meterApiRequests(context.request, ledger);
      meterApiRequests(page.request, ledger);

      await use(ledger);
      ledger.assertClean();
    },
    { auto: true },
  ],

  consoleLog: [
    async ({ page }, use) => {
      const ledger = new ConsoleLedger();
      page.on("console", (message) => {
        const line = `${message.type()}: ${message.text()}`;
        if (message.type() === "error") ledger.errors.push(line);
        if (message.type() === "warning") ledger.warnings.push(line);
      });
      page.on("pageerror", (error) => ledger.pageErrors.push(error.message));

      await use(ledger);
      ledger.assertClean();
    },
    { auto: true },
  ],
});

export { expect };

/**
 * Open the application the way the launcher does: a one-shot token URL that
 * redirects to `/` with the session cookie set.
 *
 * The token is minted from the live server for this navigation and is spent
 * by it. Waiting on the navigation's own response is not enough - the shell
 * only renders once `bootstrapSession` has returned - so this waits for the
 * navigation landmark, which is state, not time.
 */
export async function openApp(page: Page): Promise<void> {
  await page.goto(await sessionUrl(), { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("navigation", { name: "Ana bolumler" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "Technocore Station" })).toBeVisible();
}

/**
 * A left-navigation entry, by its accessible name.
 *
 * Matching is deliberately not exact: the selected entry appends a screen
 * reader-only " (secili bolum)" to its accessible name, which is the
 * behaviour under test elsewhere in this suite. No section label is a
 * substring of another, so a loose match is still unambiguous.
 */
export function navEntry(page: Page, label: string) {
  return page
    .getByRole("navigation", { name: "Ana bolumler" })
    .getByRole("button", { name: label });
}

/** Click a left-navigation entry and wait for its section to be current. */
export async function gotoSection(page: Page, label: string): Promise<void> {
  const entry = navEntry(page, label);
  await entry.click();
  await expect(entry).toHaveAttribute("aria-current", "page");
}

/** Every section the navigation offers, in navigation order. */
export const SECTION_LABELS = [
  "Genel Bakis",
  // Opened by Paket H1 (ADR-0007 9). Every loop over this list - the
  // accessibility pass, the CSP pass and the tab order - now covers it.
  "Is Tara",
  "Kimlik ve Guvenlik",
  "Olustur ve Dogrula",
  "Kaynaklar",
  "Kanitlar",
  "Ayarlar ve Yardim",
] as const;

/** Attach a body to the report so a failure is diagnosable without a rerun. */
export async function attachJson(info: TestInfo, name: string, body: unknown): Promise<void> {
  await info.attach(name, { body: JSON.stringify(body, null, 2), contentType: "application/json" });
}
