/**
 * Shared fixtures: the session handoff, the console ledger and the outbound
 * network meter.
 *
 * The outbound meter is the part worth reading twice. ADR-0006 2 says these
 * tests reach `technocore.chat` and `opencode.ai` zero times. "We did not
 * click anything that would" is an argument, not evidence, so this file both
 * **blocks** every request that leaves the application origin and **counts**
 * every request the page makes at all, from a listener that routing cannot
 * bypass. Every test asserts the count, and one test deliberately tries to
 * reach `technocore.chat` so that the meter is known to be live rather than
 * merely quiet.
 */

import { expect, test as base, type Page, type TestInfo } from "@playwright/test";

import { readHandshake, sessionUrl, type Handshake } from "./harness/station";

/** Schemes a page uses internally; they never leave the machine. */
const LOCAL_SCHEMES = ["about:", "data:", "blob:", "chrome-error:"];

export class OutboundLedger {
  /** Every request URL the page issued, in order. */
  readonly seen: string[] = [];
  /** Requests the guard refused because they left the app origin. */
  readonly blocked: string[] = [];
  private expectedBlocked = 0;

  constructor(private readonly origin: string) {}

  isLocal(url: string): boolean {
    return LOCAL_SCHEMES.some((scheme) => url.startsWith(scheme)) || url.startsWith(this.origin);
  }

  /** Off-origin URLs the page actually asked for, whatever routing did next. */
  external(): string[] {
    return this.seen.filter((url) => !this.isLocal(url));
  }

  /**
   * Declare that this test provokes `count` blocked requests on purpose.
   *
   * Only the guard's own self-test uses this, and it provokes them from a
   * throwaway page rather than from the application. Every other test asserts
   * a flat zero on both counters.
   */
  expectBlocked(count: number): void {
    this.expectedBlocked = count;
  }

  assertClean(): void {
    expect(
      this.external(),
      "the application page must never request anything outside the local origin",
    ).toHaveLength(0);
    expect(this.blocked, "off-origin requests refused by the guard").toHaveLength(
      this.expectedBlocked,
    );
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

      // The measurement. A `request` event fires for every request the page
      // makes, including ones a page-level route later fulfils, so this
      // cannot be silenced by a mock a test registers afterwards.
      page.on("request", (request) => ledger.seen.push(request.url()));

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
