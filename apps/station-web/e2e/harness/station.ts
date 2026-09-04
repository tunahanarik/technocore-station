/**
 * The Node half of the browser-test harness: where the app under test lives.
 *
 * Nothing here is a mock of the product. The tests drive the **real** backend
 * process serving the **real** production SPA build over loopback, which is
 * the whole point of adding browser QA (ADR-0006 1): the properties being
 * proven - actual CSP headers, actual focus order, actual downloads - do not
 * exist in jsdom and cannot be faked into existing.
 *
 * Two invariants are enforced here rather than assumed:
 *
 *   * the data directory is a throwaway temp directory, never
 *     `%LOCALAPPDATA%\TechnocoreStation` (the Python harness refuses the
 *     production path a second time, and a test asserts it a third);
 *   * the server binds loopback on an OS-chosen ephemeral port (INV-02), so
 *     the origin is discovered from the running process, never hardcoded.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** apps/station-web/e2e/harness -> repository root. */
export const REPO_ROOT = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
export const WEB_ROOT = path.join(REPO_ROOT, "apps", "station-web");
export const WEB_DIST = path.join(WEB_ROOT, "dist");

/** Environment variable naming the per-run scratch directory. */
export const RUN_DIR_ENV = "STATION_E2E_DIR";

export interface Handshake {
  readonly origin: string;
  readonly host: string;
  readonly port: number;
  readonly data_dir: string;
  readonly database_path: string;
  readonly web_dist: string;
  readonly pid: number;
}

function runDir(): string {
  const dir = process.env[RUN_DIR_ENV];
  if (dir === undefined || dir === "") {
    throw new Error(`${RUN_DIR_ENV} is unset: the Playwright global setup did not run`);
  }
  return dir;
}

async function waitForFile(file: string, timeoutMs: number, what: string): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    try {
      const body = await readFile(file, "utf8");
      if (body.length > 0) return body;
    } catch {
      // Not written yet.
    }
    if (Date.now() > deadline) {
      throw new Error(`timed out after ${String(timeoutMs)}ms waiting for ${what} (${file})`);
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

/** Where the running server published its origin and data directory. */
export async function readHandshake(): Promise<Handshake> {
  const body = await readFile(path.join(runDir(), "handshake.json"), "utf8");
  return JSON.parse(body) as Handshake;
}

/**
 * Ask the running server for one fresh single-use bootstrap token.
 *
 * Tokens expire in thirty seconds and are spent on first use, so a worker has
 * to mint its own at the moment it needs one. The request travels as a file
 * inside the throwaway run directory: adding a second listening socket to a
 * process whose security model is "exactly one loopback port" would have been
 * a strange thing to do for a test's convenience.
 */
export async function mintBootstrapToken(): Promise<string> {
  const id = `t${Math.random().toString(16).slice(2)}${String(Date.now())}`;
  const tokens = path.join(runDir(), "tokens");
  await writeFile(path.join(tokens, "req", id), "", "utf8");
  const token = await waitForFile(path.join(tokens, "out", id), 10_000, "a bootstrap token");
  return token.trim();
}

/** The one-shot handoff URL a launcher would have opened in the browser. */
export async function sessionUrl(): Promise<string> {
  const { origin } = await readHandshake();
  return `${origin}/session/${await mintBootstrapToken()}`;
}

export interface StartedStation {
  readonly handshake: Handshake;
  stop(): Promise<void>;
}

/**
 * Start the backend and wait until it has published its port.
 *
 * `uv run --directory apps/station-api` is the same interpreter and the same
 * locked environment the repository's other gates use, so a browser run
 * cannot silently test a different dependency set.
 */
export async function startStation(): Promise<StartedStation> {
  if (!existsSync(path.join(WEB_DIST, "index.html"))) {
    throw new Error(
      `no production build at ${WEB_DIST}. Run: npm --prefix apps/station-web run build`,
    );
  }

  const dir = await mkdtemp(path.join(tmpdir(), "station-e2e-"));
  process.env[RUN_DIR_ENV] = dir;

  const dataDir = path.join(dir, "data");
  const tokenDir = path.join(dir, "tokens");
  const handshake = path.join(dir, "handshake.json");
  await mkdir(dataDir, { recursive: true });
  await mkdir(path.join(tokenDir, "req"), { recursive: true });
  await mkdir(path.join(tokenDir, "out"), { recursive: true });

  const child = spawn(
    "uv",
    [
      "run",
      "--directory",
      path.join(REPO_ROOT, "apps", "station-api"),
      "python",
      path.join(WEB_ROOT, "e2e", "harness", "serve.py"),
    ],
    {
      cwd: REPO_ROOT,
      shell: process.platform === "win32",
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        STATION_DATA_DIR: dataDir,
        STATION_E2E_TOKEN_DIR: tokenDir,
        STATION_E2E_HANDSHAKE: handshake,
        // Production path on purpose: development mode would pin the port,
        // widen the accepted origins and defeat the point of the exercise.
        STATION_DEV: "0",
      },
    },
  );

  const output: string[] = [];
  child.stdout.on("data", (chunk: Buffer) => output.push(chunk.toString("utf8")));
  child.stderr.on("data", (chunk: Buffer) => output.push(chunk.toString("utf8")));

  let exited: number | null = null;
  child.on("exit", (code) => {
    exited = code ?? -1;
  });

  try {
    await waitForFile(handshake, 90_000, "the backend to publish its port");
  } catch (caught) {
    child.kill();
    throw new Error(
      `${String(caught)}\nbackend exit code: ${String(exited)}\nbackend output:\n${output.join("")}`,
    );
  }

  const parsed = JSON.parse(await readFile(handshake, "utf8")) as Handshake;

  return {
    handshake: parsed,
    stop: async () => {
      await stopChild(child);
      // The temp tree holds the throwaway SQLite database and any DPAPI
      // envelope a test wrote. None of it outlives the run.
      await rm(dir, { recursive: true, force: true, maxRetries: 5 });
    },
  };
}

async function stopChild(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const ended = new Promise<void>((resolve) => child.once("exit", () => resolve()));
  if (process.platform === "win32" && child.pid !== undefined) {
    // uv spawns python as a child; SIGTERM to the shell wrapper would leave
    // the server holding the port.
    spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGTERM");
  }
  await Promise.race([ended, new Promise((resolve) => setTimeout(resolve, 15_000))]);
}
