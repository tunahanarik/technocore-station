/**
 * Browser QA configuration (ADR-0006).
 *
 * Deliberate choices, each of which is a rule the run has to keep:
 *
 *   * **Chromium only.** This is a Windows-only desktop product (ADR-008,
 *     risk A1-R6) shipped as a local service the user opens in the browser
 *     they already have. Downloading Firefox and WebKit would add roughly
 *     300 MB and two more engines' worth of flakiness to prove behaviour on
 *     platforms the product does not target.
 *   * **`retries: 0`, everywhere.** ADR-0006 6: a flaky test is not a green
 *     test. A retry budget converts "sometimes broken" into "reported
 *     passing", which is the failure mode this suite exists to avoid. Every
 *     wait in these specs is state-based; there is no `waitForTimeout`.
 *   * **`workers: 1`.** One backend process, one SQLite file, one session
 *     table. Parallel workers would interleave writes to shared server state
 *     and produce exactly the nondeterminism the line above forbids.
 *   * **`forbidOnly`.** A committed `test.only` would silently shrink the
 *     suite to one test while still reporting success.
 *
 * `baseURL` is intentionally absent: the origin carries an ephemeral port
 * chosen by the operating system at launch (INV-02) and is read from the
 * running process by the `station` fixture.
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e/tests",
  globalSetup: "./e2e/global-setup.ts",

  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,

  timeout: 30_000,
  expect: { timeout: 7_000 },

  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  outputDir: "./e2e/.artifacts",

  use: {
    ...devices["Desktop Chrome"],
    // No baseURL: see the note above.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    acceptDownloads: true,
    // The product is Turkish and renders dates through the browser's
    // formatter; pinning both keeps assertions stable across machines.
    locale: "tr-TR",
    timezoneId: "Europe/Istanbul",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
