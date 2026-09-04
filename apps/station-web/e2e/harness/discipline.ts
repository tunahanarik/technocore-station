/**
 * The suite's rules about itself, as a plain module rather than as a test.
 *
 * Why it is not (only) a spec
 * ---------------------------
 * It used to be one, and a review broke it in a single line: committing a
 * `test.only` anywhere shrank the run to that one test, reported `1 passed`
 * and exited 0 - because `only` mode also filters out the very spec that was
 * meant to catch it. A guard a violation can disable is not a guard.
 *
 * So the scanner lives here and is called from **`global-setup.ts`**, which
 * Playwright runs before any test selection exists and regardless of `only`,
 * `--grep` or a filtered command line. `suite-discipline.spec.ts` calls the
 * same functions as well, so a violation is reported as a named failing test
 * when the suite is running normally; the setup call is what makes it
 * impossible to skip.
 *
 * Two backstops sit beside it in `playwright.config.ts`: `forbidOnly` is now
 * unconditional (it used to be `!!process.env.CI`, so a local run reported
 * success on a suite of one), and `retries`/`workers` are asserted by the
 * spec.
 *
 * A note on the patterns below
 * ----------------------------
 * They are built from fragments so that this file does not match its own
 * rules. Exempting the scanner from the scan would have been the other
 * option, and a self-exemption is exactly the kind of hole this module
 * exists to close.
 */

import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const E2E_ROOT = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");

export interface Source {
  /** Path relative to `e2e/`, in POSIX form. */
  readonly file: string;
  readonly body: string;
}

/** Every `.ts` file under `e2e/`, with its text. */
export async function sources(root: string = E2E_ROOT): Promise<Source[]> {
  const files: string[] = [];
  async function walk(dir: string): Promise<void> {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.name.endsWith(".ts")) files.push(full);
    }
  }
  await walk(root);
  return Promise.all(
    files.map(async (file) => ({
      file: path.relative(root, file).split(path.sep).join("/"),
      body: await readFile(file, "utf8"),
    })),
  );
}

/** Crude but sufficient: strip line and block comments before scanning. */
export function stripComments(body: string): string {
  return body.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/**
 * A committed `.only`, anywhere.
 *
 * Checked over the whole tree rather than only over `tests/`: a helper that
 * exported a focused block would shrink the run just as effectively.
 */
const ONLY = new RegExp("\\b(?:test|describe|it)\\.(?:only)\\s*\\(");

/**
 * A committed `.skip` or `.fixme`, anywhere.
 *
 * This was not checked at all, and a review disabled the entire CSP spec -
 * the file that carries the evidence for risk A1-R1 - with one word. The run
 * answered `5 skipped / 46 passed`, exit 0, and did the same under `CI=1`,
 * because `forbidOnly` says nothing about skipping.
 *
 * Playwright's conditional form (`test.skip(condition, reason)` inside a
 * body) is refused too. This suite has no environment it legitimately skips
 * in: it is Chromium-only, Windows-only and runs one real backend, so a
 * conditional skip here would only ever be a way to stop asserting
 * something.
 */
const SKIPPED = new RegExp("\\b(?:test|describe|it)\\.(?:skip|fixme)\\b");

/**
 * Sleeping instead of waiting for state.
 *
 * The previous pattern was `waitForTimeout` or the literal two tokens
 * `setTimeout(` followed by `resolve` - so it was keyed on the *name of a
 * callback*. Renaming it (`setTimeout(done, 750)`) walked straight past the
 * rule; a review demonstrated it with four passing tests and exit 0. Any
 * `setTimeout` in a spec is now a violation, which is the rule that was
 * meant all along.
 */
const SLEEP = new RegExp("\\.waitForTimeout\\s*\\(|\\bsetTimeout\\s*\\(|\\bsleep\\s*\\(");

/**
 * The request channels the outbound ledger cannot see.
 *
 * `context.request` and `page.request` are wrapped by the `outbound` fixture,
 * so those are fine. Playwright's standalone `request` fixture and
 * `playwright.request.newContext()` create an APIRequestContext the fixture
 * never touches: nothing counts it and nothing blocks it, and a review sent
 * a real DNS query through exactly that gap. It is refused in specs rather
 * than left to be remembered.
 */
const UNMETERED_REQUEST = new RegExp(
  // `playwright.request.newContext()`, and the bare `request` fixture in a
  // test's destructured argument list. The second alternative is bounded by
  // `}` and `)` so that it matches one argument list rather than everything
  // between two braces several lines apart.
  "playwright\\.request\\b|async\\s*\\(\\s*\\{[^})]*\\brequest\\b[^})]*\\}\\s*\\)",
);

function offenders(all: Source[], pattern: RegExp, within?: string): string[] {
  return all
    .filter(({ file }) => within === undefined || file.startsWith(within))
    .filter(({ body }) => pattern.test(stripComments(body)))
    .map(({ file }) => file);
}

/** Every discipline violation in the tree, as human-readable lines. */
export async function disciplineViolations(root: string = E2E_ROOT): Promise<string[]> {
  const all = await sources(root);
  const found: string[] = [];

  for (const file of offenders(all, ONLY)) {
    found.push(`${file}: a committed .only would shrink the suite and still report success`);
  }
  for (const file of offenders(all, SKIPPED)) {
    found.push(`${file}: a committed .skip/.fixme silently removes an assertion`);
  }
  // `harness/station.ts` is allowed to poll the filesystem for the handshake:
  // there is no event to await on a file another process has not written yet.
  // Nothing under `tests/` may.
  for (const file of offenders(all, SLEEP, "tests")) {
    found.push(`${file}: sleeps instead of waiting for state`);
  }
  for (const file of offenders(all, UNMETERED_REQUEST, "tests")) {
    found.push(`${file}: uses a request context the outbound ledger cannot see`);
  }
  return found;
}

/**
 * Throw if the tree violates its own rules.
 *
 * Called from `global-setup.ts`, before Playwright has selected a single
 * test, so no committed `only`, `skip` or `grep` can prevent it from running.
 */
export async function assertSuiteDiscipline(root: string = E2E_ROOT): Promise<void> {
  const found = await disciplineViolations(root);
  if (found.length > 0) {
    throw new Error(`suite discipline violated:\n  ${found.join("\n  ")}`);
  }
}
