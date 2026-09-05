import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { cwd } from "node:process";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bootstrapSession, resetSessionState } from "../../api/client";
import type { ProofWorkspace, TaskListResponse, TaskStatusResponse } from "../../api/types";
import { ProofWorkspacePanel } from "./ProofWorkspacePanel";

/**
 * These assertions encode the product rules of the proof workspace, not its
 * styling. Every one of them fails closed on the same class of mistake:
 * letting collected material read as an established result.
 *
 * The load-bearing negatives:
 *
 * * **no tick on an unimplemented claim.** The three claims render
 *   `not_implemented` with the inactive glyph, and the success glyph appears
 *   nowhere in that region. An independent check shown as a green badge is
 *   the single most valuable lie this screen could tell (ADR-0009 6);
 * * **no score.** What is missing is a list of named keys. The rendered text
 *   carries no percentage, no grade and no completeness figure
 *   (`docs/proof-workspace.md` 5);
 * * **the disclaimer precedes the digest.** `hash_scope` is on screen, from
 *   the backend, and is not composed here (ADR-0009 11);
 * * **the approval's terms precede the button.** Single-use, digest-bound,
 *   expiring, and spent by a refused delivery too (ADR-0009 4);
 * * **no path, no send.** Nothing in this component's source names a
 *   directory, and no request it makes can reach an outbound client;
 * * **no timer and no browser storage** (SI-272, SI-24).
 */

//: TEST-ONLY sentences. Shaped like the backend's, never copied from a live
//: response, and none of them is a real measurement of this machine.
const HASH_SCOPE =
  "TEST-ONLY: Bir SHA-256 ozeti yalnizca dosyanin bayt bakimindan ayni kaldigini tanimlar. Icerigin ne kadar dogru, eksiksiz veya yararli oldugu hakkinda hicbir sey soylemez.";

const BUNDLE_SCOPE =
  "TEST-ONLY: Paket bu makinede toplanan malzemenin bir kopyasidir ve hicbir yola yazilmaz; tarayiciya teslim edilir.";

const REPRODUCTION =
  "TEST-ONLY: Yeniden uretmek icin her dosyanin ozetini kendi kopyanizla karsilastirin.";

const INDEPENDENT_DETAIL =
  "TEST-ONLY: Bagimsiz kontrol bu surumde uygulanmadi. Model yolu kapalidir, bu yuzden kaydedilecek ikinci bir gorus yoktur.";

const EXIT_CODE_DETAIL =
  "TEST-ONLY: Gercek bir cikis kodu uretilmedi. Keyfi kod ve kabuk yurutmesi kapalidir, bu yuzden kosacak bir denetim yoktur.";

const TEST_RESULT_DETAIL =
  "TEST-ONLY: Test sonucu bu surumde uygulanmadi; onu kosacak yurutme kapalidir.";

const TASK_ID = "3c1f9a7b5e2d84660a1b2c3d4e5f6071";

const TASK: TaskStatusResponse = {
  id: TASK_ID,
  module_id: "proof_workspace",
  source_id: "public_room_scan",
  content_sha256: "1f2e3d4c5b6a798877665544332211aabbccddeeff0011223344556677889900",
  source_version_id: "9f8e7d6c5b4a3928",
  title: "TEST-ONLY gorev: kucuk bir donusturucu",
  state: "review_needed",
  state_detail: "TEST-ONLY: Gorev inceleme bekliyor.",
  created_at: "2026-09-05T09:00:00Z",
  updated_at: "2026-09-05T09:05:00Z",
  evidence_fields: [
    {
      evidence_field: "task_outcome",
      state: "passed",
      detail: "TEST-ONLY: cikti uretildi.",
      ref_id: "aa".repeat(16),
    },
    {
      evidence_field: "test_result",
      state: "not_implemented",
      detail: TEST_RESULT_DETAIL,
      ref_id: "",
    },
    {
      evidence_field: "user_acceptance",
      state: "not_implemented",
      detail: "TEST-ONLY: kullanici kabulu bir kisinin eylemidir.",
      ref_id: "",
    },
    {
      evidence_field: "public_share",
      state: "not_implemented",
      detail: "TEST-ONLY: dis paylasim isareti henuz konmadi.",
      ref_id: "",
    },
  ],
  ready_to_publish: false,
  blocking_fields: ["test_result", "user_acceptance"],
  // H3 opened the field, so the wire now says `true` here. The fixture says
  // it too, because a fixture that still said `false` would be testing the
  // release before this one.
  public_share_available: true,
  public_share_detail: "TEST-ONLY: dis paylasim arsivlenmis bir gonderime baglanir.",
  budget_available: false,
  budget_detail: "TEST-ONLY: gorev katmaninda butce alani yoktur.",
};

const LIST: TaskListResponse = {
  tasks: [TASK],
  task_count: 1,
  producible_states: ["review_needed"],
  unproducible_states: [],
  unproducible_detail: "TEST-ONLY: uretilemeyen durum yok.",
};

/**
 * The fixture carries **full-length** digests on purpose.
 *
 * A 64-hex run is the same shape as a seed and this app never renders one.
 * A fixture with pre-shortened values would pass that assertion while the
 * component rendered whole digests, which is the failure mode the rule exists
 * to catch.
 */
function workspaceWith(bundleDigest: string): ProofWorkspace {
  return {
    task: TASK,
    module: {
      id: "proof_workspace",
      name: "Kanit calisma alani",
      purpose: "TEST-ONLY: bir gorevin toplanmis malzemesi.",
      state: "available",
      available_from: "",
      owners: ["station_api.proof.service"],
      checks: [],
      complete: false,
      blocking_keys: [],
      not_implemented_keys: [],
    },
    artifacts: [{ name: "rapor.md", byte_count: 812, sha256: "cd".repeat(32) }],
    file_count: 1,
    total_bytes: 812,
    artifact_set_sha256: "ab".repeat(32),
    bundle_sha256: bundleDigest,
    missing: [
      {
        key: "evidence.test_result",
        state: "not_implemented",
        detail: TEST_RESULT_DETAIL,
      },
      {
        key: "artifact.ozet.md",
        state: "absent",
        detail: "TEST-ONLY: Plan bu ciktiyi soz verdi ve calisma alaninda bulunamadi.",
      },
    ],
    claims: [
      { key: "independent_check", state: "not_implemented", detail: INDEPENDENT_DETAIL },
      { key: "exit_code", state: "not_implemented", detail: EXIT_CODE_DETAIL },
      { key: "test_result", state: "not_implemented", detail: TEST_RESULT_DETAIL },
    ],
    formats: ["json", "markdown"],
    hash_scope: HASH_SCOPE,
    bundle_scope: BUNDLE_SCOPE,
    reproduction: REPRODUCTION,
    approval_ttl_seconds: 180,
  };
}

const WORKSPACE = workspaceWith("ef".repeat(32));

const SHARE_TOKEN = "test-only-share-token-not-a-real-capability";

interface Recorded {
  readonly url: string;
  readonly body: unknown;
}

function jsonOk(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Route the mock by URL and record every POST body.
 *
 * The bodies are the evidence for the rules that cannot be seen in the DOM:
 * that preparing delivers nothing, that a share carries a format and a token
 * and no destination, and that nothing is requested at all until a control is
 * pressed.
 */
function stub(
  options: {
    readonly sent?: Recorded[];
    readonly proof?: () => Promise<Response>;
    readonly onPost?: (url: string, body: unknown) => Response | null;
  } = {},
): ReturnType<typeof vi.fn> {
  const mock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : new URL(input as URL).pathname;
    if (url === "/api/session/bootstrap") {
      return Promise.resolve(
        jsonOk({ csrf_token: "test-only-value-not-a-real-token", csrf_header: "X-Station-CSRF" }),
      );
    }
    if (init?.method === "POST") {
      const body: unknown =
        typeof init.body === "string" ? (JSON.parse(init.body) as unknown) : null;
      options.sent?.push({ url, body });
      const answer = options.onPost?.(url, body);
      if (answer !== null && answer !== undefined) return Promise.resolve(answer);
      if (url === `/api/proof/${TASK_ID}/prepare`) {
        return Promise.resolve(
          jsonOk({
            workspace: WORKSPACE,
            share_token: SHARE_TOKEN,
            expires_in_seconds: 180,
          }),
        );
      }
      if (url === `/api/proof/${TASK_ID}/share`) {
        return Promise.resolve(
          new Response("TEST-ONLY bundle bytes", {
            status: 200,
            headers: { "Content-Type": "application/json; charset=utf-8" },
          }),
        );
      }
    }
    if (url === "/api/tasks") return Promise.resolve(jsonOk(LIST));
    if (url === `/api/proof/${TASK_ID}`) {
      return options.proof === undefined
        ? Promise.resolve(jsonOk(WORKSPACE))
        : options.proof();
    }
    return Promise.resolve(jsonOk({ detail: "not_found" }, 404));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

/**
 * Downloads go through an object URL and an anchor click.
 *
 * jsdom implements neither, so both are stubbed and the created URLs are
 * returned: a delivery that never produced one would look identical to a
 * delivery that did, otherwise.
 */
function stubDownload(): { readonly created: string[]; readonly revoked: string[] } {
  const created: string[] = [];
  const revoked: string[] = [];
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: (blob: Blob) => {
      created.push(`blob:test-only/${String(blob.size)}`);
      return created[created.length - 1] ?? "";
    },
    revokeObjectURL: (value: string) => {
      revoked.push(value);
    },
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  return { created, revoked };
}

/**
 * Exchange the cookie for a CSRF value, then render.
 *
 * The panel does not bootstrap on its own - the shell does that once, for the
 * whole app - so a test that skipped this step would exercise a session that
 * never existed and every write would fail as `session_not_bootstrapped`
 * rather than for the reason under test.
 */
async function renderPanel(): Promise<ReturnType<typeof render>> {
  await bootstrapSession();
  return render(<ProofWorkspacePanel />);
}

async function openTask(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(await screen.findByRole("radio", { name: new RegExp(TASK.title) }));
  await screen.findByRole("region", { name: "Uretilen dosyalar" });
}

/** The `src` tree, found from the working directory (heroui-surface pattern). */
function resolveSrcDir(): string {
  const candidates = [join(cwd(), "src"), join(cwd(), "apps", "station-web", "src")];
  const found = candidates.find((candidate) => existsSync(join(candidate, "App.tsx")));
  if (found === undefined) throw new Error(`station-web/src not found from ${cwd()}`);
  return found;
}

/**
 * Every non-test source file this surface owns.
 *
 * A new package covered by no scan is exactly the mistake ADR-0009 5 made a
 * merge condition on the backend, and the frontend has the same shape: the
 * task surface's own source scan reads `components/tasks` and would never have
 * looked inside `components/proof`. This one is scoped to the new directory
 * and asserts it found something, because a scan over an empty list passes
 * forever.
 */
function proofSources(): { file: string; body: string }[] {
  const root = resolveSrcDir();
  const dir = join(root, "components", "proof");
  return readdirSync(dir)
    .filter((name) => /\.tsx?$/.test(name) && !name.includes(".test."))
    .map((name) => join(dir, name))
    .map((file) => ({ file, body: readFileSync(file, "utf8") }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetSessionState();
});

describe("Kanit calisma alani: nothing happens on its own", () => {
  it("installs no timer and makes exactly one read without a click", async () => {
    const interval = vi.spyOn(globalThis, "setInterval");
    const mock = stub();
    render(<ProofWorkspacePanel />);
    await screen.findByRole("region", { name: "Paket icin gorev secimi" });

    const installed = interval.mock.calls
      .map((call) => (typeof call[0] === "function" ? call[0].name : String(call[0])))
      .filter((name) => name !== "checkRealTimersCallback");
    expect(installed, "nothing on this surface may schedule a repeating task").toEqual([]);

    const urls = mock.mock.calls.map((call) => String(call[0]));
    expect(urls).toEqual(["/api/tasks"]);
  });

  it("carries no timer, no storage and no filesystem destination in its source", () => {
    const sources = proofSources();
    expect(sources.length, "the scan must actually find this surface").toBeGreaterThan(0);
    for (const { body, file } of sources) {
      const code = body.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      expect(code, `${file} schedules work`).not.toMatch(
        /\bsetInterval\s*\(|\bsetTimeout\s*\(|requestAnimationFrame\s*\(/,
      );
      expect(code, `${file} touches browser storage`).not.toMatch(
        /localStorage|sessionStorage|indexedDB/,
      );
      expect(code, `${file} renders untrusted content as HTML`).not.toContain(
        "dangerouslySetInnerHTML",
      );
      // No destination, in either direction. The bundle is handed to the
      // browser; there is nothing on this surface that names where it lands.
      expect(code, `${file} names a filesystem destination`).not.toMatch(
        /\bdirectory\b|\bdirPath\b|\boutputPath\b/,
      );
    }
  });
});

describe("Kanit calisma alani: what a digest does not establish", () => {
  it("shows the backend's hash sentence verbatim beside the digests", async () => {
    stub();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    expect(screen.getByTestId("proof-hash-scope")).toHaveTextContent(HASH_SCOPE);
    expect(screen.getByTestId("proof-bundle-scope")).toHaveTextContent(BUNDLE_SCOPE);
    expect(screen.getByTestId("proof-reproduction")).toHaveTextContent(REPRODUCTION);
  });

  it("never renders a 64-hex run, the same shape as a seed", async () => {
    stub();
    const user = userEvent.setup();
    const { container } = await renderPanel();
    await openTask(user);

    expect(container.textContent ?? "").not.toMatch(/\b[0-9a-fA-F]{64}\b/);
    expect(screen.getByTestId("proof-artifact-set")).toHaveTextContent("abababababab");
    expect(screen.getByTestId("proof-bundle-digest")).toHaveTextContent("efefefefefef");
  });
});

describe("Kanit calisma alani: the records that were not produced", () => {
  it("reports all three claims as not_implemented, with their reasons", async () => {
    stub();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    for (const [key, detail] of [
      ["independent_check", INDEPENDENT_DETAIL],
      ["exit_code", EXIT_CODE_DETAIL],
      ["test_result", TEST_RESULT_DETAIL],
    ] as const) {
      const region = screen.getByTestId(`proof-claim-${key}`);
      expect(region).toHaveTextContent("not_implemented");
      expect(region).toHaveTextContent(detail);
    }
  });

  it("puts no success glyph and no verification word on an unimplemented claim", async () => {
    stub();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    for (const key of ["independent_check", "exit_code", "test_result"] as const) {
      const text = screen.getByTestId(`proof-claim-${key}`).textContent ?? "";
      // The success glyph belongs to `tone: "ok"`. Its presence here would
      // mean an unimplemented record had been given a passing badge.
      expect(text, `${key} carries a success glyph`).not.toContain("✓");
      expect(text, `${key} claims a verification`).not.toMatch(/dogrulan|kanitlan|onaylan/i);
      expect(text).toContain("uygulanmadi");
    }
  });

  it("says that the publish-ready state cannot be asked for from here", async () => {
    stub();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    // The wording changed when the derivation route arrived; what this test
    // protects did not. `ready_to_publish` is still derived rather than
    // requested, and there is still no control on *this* surface that asks
    // for it - the evaluation lives in "Gorevler" and carries no target.
    const statement = screen.getByTestId("proof-publish-unreachable");
    expect(statement).toHaveTextContent("kanittan turetilir ve istenemez");
    expect(statement).toHaveTextContent("adiyla hedefleyemez");
    expect(
      screen.queryByRole("button", { name: /Yayima hazir/i }),
      "no control on this surface may ask for the derived state",
    ).toBeNull();
  });
});

describe("Kanit calisma alani: gaps are named, never scored", () => {
  it("lists every gap by its own key and states that it is not a score", async () => {
    stub();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    expect(screen.getByTestId("proof-missing-evidence.test_result")).toHaveTextContent(
      "evidence.test_result",
    );
    expect(screen.getByTestId("proof-missing-artifact.ozet.md")).toHaveTextContent("absent");
    expect(screen.getByTestId("proof-missing-rule")).toHaveTextContent(
      "puan, yuzde, tamamlanma orani veya tek bir rozet yoktur",
    );
  });

  it("renders no percentage, grade or completeness figure anywhere", async () => {
    stub();
    const user = userEvent.setup();
    const { container } = await renderPanel();
    await openTask(user);

    const text = container.textContent ?? "";
    // The words appear only inside the sentence that refuses them, so the
    // check is for a *figure*: a percent sign, or a score-shaped ratio.
    expect(text, "a percentage would sum four different gaps into one").not.toMatch(/\d\s*%/);
    expect(text).not.toMatch(/\bskor\b|\bpuan:\s*\d/i);
    expect(container.querySelectorAll("progress, [role='progressbar']")).toHaveLength(0);
  });
});

describe("Kanit calisma alani: the single-use approval", () => {
  it("states the terms before any control can spend one", async () => {
    stub();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    const terms = screen.getByTestId("proof-share-terms");
    expect(terms).toHaveTextContent("Onay bir kez harcanir");
    expect(terms).toHaveTextContent("Reddedilen bir teslim de onayi harcar");
    expect(terms).toHaveTextContent("180 saniye");
    expect(terms).toHaveTextContent("Bir dosya degisirse ozet degisir");
    expect(terms).toHaveTextContent("hicbir yola yazilmaz");

    // The terms are on screen while both format controls are still locked.
    expect(screen.getByRole("button", { name: "JSON olarak indir" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Markdown olarak indir" })).toBeDisabled();
  });

  it("keeps the delivery locked until an approval exists and consent is given", async () => {
    const sent: Recorded[] = [];
    stub({ sent });
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    const json = screen.getByRole("button", { name: "JSON olarak indir" });
    expect(json).toBeDisabled();

    // Consent alone is not enough: there is still no approval to spend.
    await user.click(screen.getByRole("checkbox", { name: /tek kullanimlik oldugunu/ }));
    expect(json).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Tek kullanimlik onay hazirla" }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay hazir");
    });
    expect(json).toBeEnabled();

    // Preparing sends nothing: exactly one request, and it is the mint.
    expect(
      sent.map((entry) => entry.url),
      "preparing must deliver nothing",
    ).toEqual([`/api/proof/${TASK_ID}/prepare`]);

    // An approval alone is not enough either. Re-reading the bundle drops
    // both halves, and the delivery locks again.
    await user.click(screen.getByRole("button", { name: /Paketi yeniden oku/ }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Henuz onay hazirlanmadi");
    });
    expect(screen.getByRole("checkbox", { name: /tek kullanimlik oldugunu/ })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "JSON olarak indir" })).toBeDisabled();
  });

  it("sends the token, the format and the acknowledgement, and no destination", async () => {
    const sent: Recorded[] = [];
    stub({ sent });
    const download = stubDownload();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: "Tek kullanimlik onay hazirla" }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay hazir");
    });
    await user.click(screen.getByRole("checkbox", { name: /tek kullanimlik oldugunu/ }));
    await user.click(screen.getByRole("button", { name: "Markdown olarak indir" }));

    await waitFor(() => {
      expect(screen.getByTestId("proof-share-result")).toBeInTheDocument();
    });

    const share = sent.find((entry) => entry.url.endsWith("/share"));
    expect(share?.body).toEqual({
      share_token: SHARE_TOKEN,
      format: "markdown",
      acknowledged: true,
    });
    // Three keys and no fourth: no path, no filename, no directory.
    expect(Object.keys(share?.body as Record<string, unknown>).sort()).toEqual([
      "acknowledged",
      "format",
      "share_token",
    ]);
    expect(download.created).toHaveLength(1);
    expect(download.revoked).toEqual(download.created);
    expect(screen.getByTestId("proof-share-result")).toHaveTextContent(
      "technocore-station-kanit-paketi.md",
    );
  });

  it("treats the approval as spent once a delivery has been attempted", async () => {
    const sent: Recorded[] = [];
    stub({ sent });
    stubDownload();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: "Tek kullanimlik onay hazirla" }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay hazir");
    });
    await user.click(screen.getByRole("checkbox", { name: /tek kullanimlik oldugunu/ }));
    await user.click(screen.getByRole("button", { name: "JSON olarak indir" }));

    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay harcandi");
    });

    // The second control is locked too: one approval, one delivery.
    expect(screen.getByRole("button", { name: "Markdown olarak indir" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Markdown olarak indir" }));
    expect(sent.filter((entry) => entry.url.endsWith("/share"))).toHaveLength(1);
  });

  it("still calls the approval spent when the delivery was refused", async () => {
    const sent: Recorded[] = [];
    stub({
      sent,
      onPost: (url) =>
        url.endsWith("/share")
          ? jsonOk({ detail: "Paket bu arada degisti." }, 409)
          : null,
    });
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: "Tek kullanimlik onay hazirla" }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay hazir");
    });
    await user.click(screen.getByRole("checkbox", { name: /tek kullanimlik oldugunu/ }));
    await user.click(screen.getByRole("button", { name: "JSON olarak indir" }));

    // The refusal is persistent and named, and the token is gone with it: a
    // surface that offered the same token again would be teaching the user
    // that the approval survives a refusal. It does not (ADR-0009 4).
    expect(await screen.findByRole("alert")).toHaveTextContent("Paket teslim edilemedi");
    expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay harcandi");
    expect(screen.getByRole("button", { name: "JSON olarak indir" })).toBeDisabled();
    expect(sent.filter((entry) => entry.url.endsWith("/share"))).toHaveLength(1);
  });

  it("says the approval no longer matches when the bundle has changed under it", async () => {
    let reads = 0;
    stub({
      proof: () => {
        reads += 1;
        // The second read returns a different bundle: an artifact changed.
        return Promise.resolve(
          jsonOk(reads === 1 ? WORKSPACE : workspaceWith("ba".repeat(32))),
        );
      },
      onPost: (url) =>
        url.endsWith("/prepare")
          ? jsonOk({
              workspace: WORKSPACE,
              share_token: SHARE_TOKEN,
              expires_in_seconds: 180,
            })
          : null,
    });
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: "Tek kullanimlik onay hazirla" }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay hazir");
    });
    expect(screen.queryByTestId("proof-share-stale")).toBeNull();

    // Re-reading returns a different bundle: an artifact changed underneath.
    await user.click(screen.getByRole("button", { name: /Paketi yeniden oku/ }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-bundle-digest")).toHaveTextContent("babababababa");
    });

    // The approval was dropped with the re-read rather than left to fail
    // against a bundle it no longer matches.
    expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Henuz onay hazirlanmadi");
    expect(screen.getByRole("button", { name: "JSON olarak indir" })).toBeDisabled();
  });
});

describe("Kanit calisma alani: failures are named", () => {
  it("shows a persistent, retryable error when the bundle cannot be read", async () => {
    stub({ proof: () => Promise.reject(new TypeError("Failed to fetch")) });
    const user = userEvent.setup();
    await renderPanel();
    await user.click(await screen.findByRole("radio", { name: new RegExp(TASK.title) }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Kanit calisma alani okunamadi");
    expect(screen.queryByRole("region", { name: "Uretilen dosyalar" })).toBeNull();
  });

  it("says there is nothing to build a bundle for rather than inventing one", async () => {
    stub({});
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : new URL(input as URL).pathname;
        if (url === "/api/session/bootstrap") {
          return Promise.resolve(
            jsonOk({
              csrf_token: "test-only-value-not-a-real-token",
              csrf_header: "X-Station-CSRF",
            }),
          );
        }
        return Promise.resolve(
          jsonOk({ ...LIST, tasks: [], task_count: 0 }),
        );
      }),
    );
    render(<ProofWorkspacePanel />);

    expect(
      await screen.findByText("Paketi olusturulacak bir gorev yok"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("proof-bundle-digest")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Paket H4: the bodies travel, or the reason they did not does.
//
// Until the proof package carried artifact bodies, what a person downloaded
// was an inventory of their work plus the digests to check it against, and
// not the work. Two things had to become visible here at once: that a body is
// in the bundle, and - when it is not - which rule kept it out. A file listed
// with a name, a size and a digest but no contents looks complete in a table,
// which is exactly why the exclusion is rendered beside the file rather than
// only in the gap list.
// ---------------------------------------------------------------------------

const SECRET_EXCLUSION =
  "TEST-ONLY: Dosyanin govdesi pakete alinmadi: gizli deger taramasi bir kural eslesmesi buldu. Paket kullaniciya teslim edilen belgedir, bu yuzden govde redakte edilmez, disarida birakilir; eslesen deger hicbir yere yazilmaz.";

const ARTIFACT_DIGEST = "1a".repeat(32);

/** A workspace with one embedded body and one whose body was refused. */
const MIXED: ProofWorkspace = {
  ...WORKSPACE,
  artifacts: [
    { name: "rapor.md", byte_count: 812, sha256: "cd".repeat(32) },
    { name: "gizli.txt", byte_count: 64, sha256: "9a".repeat(32) },
  ],
  file_count: 2,
  total_bytes: 876,
  missing: [
    ...WORKSPACE.missing,
    { key: "artifact_body.gizli.txt", state: "excluded", detail: SECRET_EXCLUSION },
  ],
};

describe("Kanit calisma alani: a body either travels or says why not", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    resetSessionState();
  });

  it("names the rule that kept a body out, beside the file it belongs to", async () => {
    stub({ proof: () => Promise.resolve(jsonOk(MIXED)) });
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    // The excluded file is still listed with its name, size and digest: the
    // exclusion refuses the contents, never the record of the file.
    const excluded = screen.getByTestId("proof-artifact-gizli.txt");
    expect(excluded).toHaveTextContent("gizli.txt");
    expect(excluded).toHaveTextContent("64 bayt");
    expect(excluded).toHaveTextContent("govdesi pakete alinmadi");
    expect(screen.getByTestId("proof-artifact-excluded-gizli.txt")).toHaveTextContent(
      "gizli deger taramasi bir kural eslesmesi buldu",
    );

    // And the one that did travel says so, rather than being left blank.
    expect(screen.getByTestId("proof-artifact-rapor.md")).toHaveTextContent("govdesi pakette");
    expect(
      screen.queryByTestId("proof-artifact-excluded-rapor.md"),
      "a file whose body travelled has no exclusion to show",
    ).toBeNull();
  });

  it("counts the embedded bodies and says where the two numbers came from", async () => {
    stub({ proof: () => Promise.resolve(jsonOk(MIXED)) });
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    // One of two files, and only that file's bytes. The count is derived on
    // this side, and the sentence beside it refuses to pass the derivation
    // off as the document's own summary.
    expect(screen.getByTestId("proof-embedded-count")).toHaveTextContent(
      "Govdesi pakete alinan dosya: 1 / 2",
    );
    expect(screen.getByTestId("proof-embedded-count")).toHaveTextContent(
      "govdesi pakete alinan bayt: 812",
    );
    expect(screen.getByTestId("proof-embedded-derivation")).toHaveTextContent(
      "paketin kendi ozet satirindan degil",
    );
  });

  it("offers no file control for a body that was left out", async () => {
    stub({ proof: () => Promise.resolve(jsonOk(MIXED)) });
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    expect(screen.getByTestId("proof-take-rapor.md")).toBeInTheDocument();
    expect(
      screen.queryByTestId("proof-take-gizli.txt"),
      "a body that is not in the bundle cannot be handed over",
    ).toBeNull();
  });

  it("hands one file over under the same single-use approval and shows the server's digest", async () => {
    const sent: Recorded[] = [];
    const downloads = stubDownload();
    stub({
      sent,
      onPost: (url) =>
        url === `/api/proof/${TASK_ID}/artifact`
          ? new Response("TEST-ONLY artifact bytes", {
              status: 200,
              headers: {
                "Content-Type": "text/plain; charset=utf-8",
                "X-Station-Artifact-Sha256": ARTIFACT_DIGEST,
                "X-Station-Bundle-Sha256": WORKSPACE.bundle_sha256,
              },
            })
          : null,
    });
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    // Nothing is deliverable before an approval exists and the terms are
    // acknowledged: both halves are asserted, because either one alone would
    // let a delivery happen on a single act.
    expect(screen.getByTestId("proof-take-rapor.md")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Tek kullanimlik onay hazirla/ }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay hazir");
    });
    expect(screen.getByTestId("proof-take-rapor.md")).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: /Onayin tek kullanimlik/ }));
    await user.click(screen.getByTestId("proof-take-rapor.md"));

    await waitFor(() => {
      expect(screen.getByTestId("proof-artifact-result")).toBeInTheDocument();
    });

    const request = sent.find((entry) => entry.url === `/api/proof/${TASK_ID}/artifact`);
    expect(request, "the delivery must have been requested").toBeDefined();
    // A name and a token, and nothing that addresses the filesystem: no path,
    // no directory, no format and no destination of any kind.
    expect(request?.body).toEqual({
      share_token: SHARE_TOKEN,
      name: "rapor.md",
      acknowledged: true,
    });

    // The digest printed is the one the server sent in the header, shortened.
    expect(screen.getByTestId("proof-artifact-result")).toHaveTextContent(
      ARTIFACT_DIGEST.slice(0, 12),
    );
    expect(screen.getByTestId("proof-artifact-result")).toHaveTextContent(
      "icerigin dogrulugu hakkinda hicbir sey soylemez",
    );
    expect(downloads.created).toHaveLength(1);
    expect(downloads.revoked).toHaveLength(1);

    // The approval is gone: taking a file and taking the bundle are two ways
    // of spending one approval, not two deliveries.
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay harcandi");
    });
    expect(screen.getByTestId("proof-take-rapor.md")).toBeDisabled();
  });

  it("spends the approval even when the delivery is refused", async () => {
    stubDownload();
    stub({
      onPost: (url) =>
        url === `/api/proof/${TASK_ID}/artifact`
          ? jsonOk({ detail: "TEST-ONLY: paket bu arada degisti." }, 409)
          : null,
    });
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: /Tek kullanimlik onay hazirla/ }));
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay hazir");
    });
    await user.click(screen.getByRole("checkbox", { name: /Onayin tek kullanimlik/ }));
    await user.click(screen.getByTestId("proof-take-rapor.md"));

    // The refusal is shown *and* the token is gone. A surface that only
    // marked it spent on the happy path would leave a refused delivery
    // looking retryable, which is the property the token exists to remove.
    await waitFor(() => {
      expect(screen.getByTestId("proof-share-state")).toHaveTextContent("Onay harcandi");
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Dosya teslim edilemedi");
    expect(screen.queryByTestId("proof-artifact-result")).toBeNull();
  });

  it("states that one approval buys one delivery, before either control", async () => {
    stub();
    const user = userEvent.setup();
    await renderPanel();
    await openTask(user);

    expect(screen.getByTestId("proof-share-one-delivery")).toHaveTextContent(
      "Bir onay bir teslim eder",
    );
    expect(screen.getByTestId("proof-artifact-delivery-rule")).toHaveTextContent(
      "Sunucu dosyanin kendi SHA-256 ozetini yanit basliginda gonderir",
    );
  });
});
