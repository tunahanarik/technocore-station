/**
 * The suite checking itself.
 *
 * ADR-0006 6 says a flaky test is not a green test. The things that reliably
 * make a browser suite flaky - sleeping instead of waiting for state, and
 * retrying until it passes - and the two that silently shrink it - a
 * committed `test.only` and a committed `test.skip` - are all mechanical, so
 * they are checked mechanically rather than left to review.
 *
 * **The source scan does not live here.** It lives in
 * `harness/discipline.ts` and is called from `global-setup.ts`, because a
 * review showed why: a committed `only` filtered this file out along with
 * everything else, the run reported `1 passed` and exited 0, and the guard
 * never executed. Global setup runs before test selection exists. These
 * tests call the same functions so a violation still shows up as a named
 * failure during an ordinary run - they are the readable surface, not the
 * enforcement.
 *
 * This would normally be an ESLint rule. `apps/station-web/eslint.config.js`
 * is write-protected in this environment (a repository hook refuses edits to
 * it), so the rules live in TypeScript instead.
 */

import config from "../../playwright.config";
import { disciplineViolations } from "../harness/discipline";
import { expect, test } from "../fixtures";

test.describe("suite discipline", () => {
  test("the tree keeps its own rules", async () => {
    // One assertion over every rule, because the scanner reports which rule
    // and which file, and a failure message that names both is worth more
    // than four separate tests that each name one.
    expect(await disciplineViolations()).toEqual([]);
  });

  test("a focused run cannot report success", () => {
    // `forbidOnly` used to be `!!process.env.CI`, so exactly the run a
    // developer looks at - the local one - was the run that accepted a
    // committed `only` and answered "1 passed".
    expect(config.forbidOnly).toBe(true);
  });

  test("retries stay at zero and the run stays single-worker", () => {
    // A retry budget turns "sometimes broken" into "reported passing".
    expect(config.retries).toBe(0);
    // One backend process and one SQLite file: parallel workers would
    // interleave writes to shared server state.
    expect(config.workers).toBe(1);
    expect(config.fullyParallel).toBe(false);
  });

  test("only Chromium is configured, and no browser is downloaded implicitly", () => {
    expect(config.projects?.map((project) => project.name)).toEqual(["chromium"]);
  });
});
