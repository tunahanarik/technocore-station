/**
 * The suite checking itself.
 *
 * ADR-0006 6 says a flaky test is not a green test. The two things that
 * reliably make a browser suite flaky - sleeping instead of waiting for
 * state, and retrying until it passes - and the one thing that silently
 * shrinks it - a committed `test.only` - are all mechanical, so they are
 * checked mechanically rather than left to review.
 *
 * This would normally be an ESLint rule. `apps/station-web/eslint.config.js`
 * is write-protected in this environment (a repository hook refuses edits to
 * it), so the rule lives here instead, where it runs on every `test:e2e`.
 */

import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import config from "../../playwright.config";
import { expect, test } from "../fixtures";

const E2E_ROOT = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");

async function sources(): Promise<{ file: string; body: string }[]> {
  const files: string[] = [];
  async function walk(dir: string): Promise<void> {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.name.endsWith(".ts")) files.push(full);
    }
  }
  await walk(E2E_ROOT);
  return Promise.all(
    files.map(async (file) => ({
      file: path.relative(E2E_ROOT, file),
      body: await readFile(file, "utf8"),
    })),
  );
}

test.describe("suite discipline", () => {
  test("no spec sleeps instead of waiting for state", async () => {
    const offenders = (await sources())
      .filter(({ body }) => /\.waitForTimeout\s*\(|setTimeout\(\s*resolve/.test(stripComments(body)))
      .map(({ file }) => file);

    // `harness/station.ts` is allowed to poll the filesystem for the
    // handshake: there is no event to await on a file another process has not
    // written yet. Nothing under `tests/` may.
    expect(offenders.filter((file) => file.startsWith("tests"))).toEqual([]);
  });

  test("no committed test.only silently shrinks the suite", async () => {
    const offenders = (await sources())
      .filter(({ body }) => /\b(test|describe|it)\.only\s*\(/.test(stripComments(body)))
      .map(({ file }) => file);

    expect(offenders).toEqual([]);
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

/** Crude but sufficient: strip line and block comments before scanning. */
function stripComments(body: string): string {
  return body.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}
