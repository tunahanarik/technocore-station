/**
 * The proof workspace in a real browser: what it shows, what it refuses to
 * imply, and what leaves the machine when a person takes a copy.
 *
 * The whole `/api/proof*`, `/api/tasks*` and `/api/evidence/records` group is
 * answered from this file, and that is a constraint rather than a
 * convenience. A real bundle exists only for a real task, and a real task
 * exists only after a work scan has read a public room - which ADR-0006 2 puts
 * at zero outbound requests for this suite. Fulfilling the routes here means
 * the flow under test is the one a person drives while the server is never
 * asked to build anything.
 *
 * What this therefore proves, and what it does not
 * ------------------------------------------------
 * It proves the **browser half**: that the section is reachable by keyboard,
 * that the sentence about what a digest does not establish is on screen before
 * any digest is, that the three unproduced records render as `not_implemented`
 * with no success glyph anywhere near them, that the gaps are named and no
 * progress control exists, that the single-use approval's terms are readable
 * before the control that spends one, that a real file reaches the browser
 * with the name this app states, that a spent approval locks the delivery, and
 * that acceptance writes a field without moving the task.
 *
 * It proves **nothing about the server's own behaviour**. That the approval is
 * really single-use, really bound to the bundle digest and really spent by a
 * refused delivery is asserted in the Python suite, against the code that
 * enforces it. The fixtures below are shaped like the wire; a browser test
 * claiming the server's guarantees would be claiming them from the wrong side
 * of the wire, and the guarantees would survive the fixtures being wrong.
 *
 * Two further limits worth naming: the bundle bytes here are a fixture, so
 * nothing in this file says the real document is deterministic or that its
 * digest matches the artifact set; and the accessibility, CSP and keyboard
 * passes over this section run against the **live** backend in their own
 * specs, where the panel finds no tasks at all.
 */

import type { Page } from "@playwright/test";

import { expect, navEntry, openApp, test } from "../fixtures";

const TASK_ID = "3c1f9a7b5e2d84660a1b2c3d4e5f6071";
const ACCEPTED_SEND_ID = "11223344556677889900aabbccddeeff";
const UNKNOWN_SEND_ID = "ffeeddccbbaa00998877665544332211";

const BUNDLE_SHA = "ef".repeat(32);

const HASH_SCOPE =
  "TEST-ONLY: Bir SHA-256 ozeti yalnizca dosyanin bayt bakimindan ayni kaldigini tanimlar. Icerigin ne kadar dogru, eksiksiz veya yararli oldugu hakkinda hicbir sey soylemez.";

const BUNDLE_SCOPE =
  "TEST-ONLY: Paket bu makinede toplanan malzemenin bir kopyasidir ve hicbir yola yazilmaz; tarayiciya teslim edilir.";

const INDEPENDENT_DETAIL =
  "TEST-ONLY: Bagimsiz kontrol bu surumde uygulanmadi. Model yolu kapalidir, bu yuzden kaydedilecek ikinci bir gorus yoktur.";

const EXIT_CODE_DETAIL =
  "TEST-ONLY: Gercek bir cikis kodu uretilmedi. Keyfi kod ve kabuk yurutmesi kapalidir.";

const TEST_RESULT_DETAIL =
  "TEST-ONLY: Test sonucu bu surumde uygulanmadi; onu kosacak yurutme kapalidir.";

const TASK = {
  id: TASK_ID,
  module_id: "agent_workspace",
  source_id: "public_room_scan",
  content_sha256: "1f2e3d4c5b6a7988",
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
      ref_id: "aa11bb22cc33",
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
      state: "blocked",
      detail: "TEST-ONLY: dis paylasim isareti henuz konmadi.",
      ref_id: "",
    },
  ],
  ready_to_publish: false,
  blocking_fields: ["test_result", "user_acceptance"],
  public_share_available: true,
  public_share_detail:
    "TEST-ONLY: dis paylasim yalnizca arsivlenmis bir gonderime baglanabilir.",
  budget_available: false,
  budget_detail: "TEST-ONLY: gorev katmaninda butce alani yoktur.",
};

const TASK_LIST = {
  tasks: [TASK],
  task_count: 1,
  producible_states: ["review_needed"],
  unproducible_states: [] as string[],
  unproducible_detail: "TEST-ONLY: uretilemeyen durum yok.",
};

const PROOF = {
  task: TASK,
  module: {
    id: "agent_workspace",
    name: "Agent calisma alani",
    purpose: "TEST-ONLY: bir gorevin calisma alani.",
    state: "available",
    available_from: "",
    owners: ["station_api.agent.service"],
    checks: [],
    complete: false,
    blocking_keys: [] as string[],
    not_implemented_keys: [] as string[],
  },
  artifacts: [{ name: "rapor.md", byte_count: 812, sha256: "cd".repeat(32) }],
  file_count: 1,
  total_bytes: 812,
  artifact_set_sha256: "ab".repeat(32),
  bundle_sha256: BUNDLE_SHA,
  missing: [
    { key: "evidence.test_result", state: "not_implemented", detail: TEST_RESULT_DETAIL },
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
  reproduction: "TEST-ONLY: Yeniden uretmek icin ozetleri kendi kopyanizla karsilastirin.",
  approval_ttl_seconds: 180,
};

const SHARE_TOKEN = "test-only-share-token-not-a-real-capability";

/** The bytes the fixture hands back. Not a real bundle and not deterministic. */
const BUNDLE_BODY = '{"kind":"TEST-ONLY","note":"fixture bytes, not a real bundle"}';

function archivedSend(id: string, room: string, outcome: string): unknown {
  return {
    id,
    reservation_id: `res-${id.slice(0, 6)}`,
    room,
    did: "did:key:z6MkTESTONLYFIXTURE",
    nonce: "424242",
    canonical_sha256: "ab".repeat(32),
    signature: "TESTONLYSIGNATUREVALUE",
    http_status: outcome === "accepted" ? 200 : 0,
    write_outcome: outcome,
    capture_state: "",
    capture_detail: "",
    captured_at: null,
    room_generation: "1",
    capture_generation: "",
    generation_changed: false,
    captured_line_offset: null,
    captured_line_length: null,
    stream_sha256: "",
    stream_bytes: 0,
    stream_truncated: false,
    unreadable_lines: 0,
    request_sha256: "cd".repeat(32),
    response_sha256: "ef".repeat(32),
    recorded_at: "2026-09-05T09:10:00Z",
    external_anchor: null,
    levels: [],
  };
}

const ARCHIVE = {
  records: [
    archivedSend(ACCEPTED_SEND_ID, "test-only-room", "accepted"),
    archivedSend(UNKNOWN_SEND_ID, "test-only-room-two", "outcome_unknown"),
  ],
  record_count: 2,
  chain_state: "intact",
  chain_detail: "TEST-ONLY: zincir tutarli.",
  chain_link_count: 2,
};

/** Every state-changing request this spec sends, in order. */
interface ProofLedger {
  readonly posts: { url: string; body: unknown }[];
}

/**
 * Answer the proof, task and archive groups locally.
 *
 * Registered before the app is opened, so the very first read is already
 * served from here and the backend is never asked to build a bundle. The
 * approval is modelled the way the server models it - **spent by the
 * attempt** - so the second delivery is refused here too, and the surface's
 * behaviour after a refusal is what the test observes.
 */
async function mockProof(page: Page, ledger: ProofLedger): Promise<void> {
  let tokenLive = false;

  await page.route(
    (url) =>
      url.pathname.startsWith("/api/proof") ||
      url.pathname.startsWith("/api/tasks") ||
      url.pathname === "/api/evidence/records",
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());

      if (request.method() === "POST") {
        ledger.posts.push({
          url: url.pathname,
          body: JSON.parse(request.postData() ?? "null") as unknown,
        });
      }

      if (url.pathname === `/api/proof/${TASK_ID}/prepare`) {
        tokenLive = true;
        await route.fulfill({
          json: { workspace: PROOF, share_token: SHARE_TOKEN, expires_in_seconds: 180 },
        });
        return;
      }

      if (url.pathname === `/api/proof/${TASK_ID}/share`) {
        if (!tokenLive) {
          await route.fulfill({
            status: 409,
            json: { detail: "Bu onay gecerli degil veya zaten harcandi." },
          });
          return;
        }
        // Spent by the attempt, exactly as the server spends it.
        tokenLive = false;
        await route.fulfill({
          body: BUNDLE_BODY,
          contentType: "application/json; charset=utf-8",
          headers: {
            "Content-Disposition":
              'attachment; filename="technocore-station-kanit-paketi.json"',
          },
        });
        return;
      }

      if (
        url.pathname === `/api/proof/${TASK_ID}/acceptance` ||
        url.pathname === `/api/proof/${TASK_ID}/public-share`
      ) {
        await route.fulfill({ json: PROOF });
        return;
      }

      if (url.pathname === `/api/proof/${TASK_ID}`) {
        await route.fulfill({ json: PROOF });
        return;
      }

      if (url.pathname === "/api/evidence/records") {
        await route.fulfill({ json: ARCHIVE });
        return;
      }

      if (url.pathname === "/api/tasks") {
        await route.fulfill({ json: TASK_LIST });
        return;
      }

      if (url.pathname === "/api/tasks/surface") {
        await route.fulfill({ json: SURFACE });
        return;
      }

      await route.fulfill({
        json: { task: TASK, runs: [], workspace_files: [], honesty: RUN_HONESTY },
      });
    },
  );
}

const RUN_HONESTY =
  "TEST-ONLY: Bu surumde arac zinciri deterministiktir: model cagrisi, kabuk komutu ve keyfi kod yurutmesi yoktur.";

const SURFACE = {
  execution: {
    arbitrary_execution_supported: false,
    reason: "execution_unavailable",
    detail: "TEST-ONLY: Keyfi kod ve kabuk yurutmesi bu surumde kapalidir.",
    inventory: [] as unknown[],
  },
  ceiling: {
    max_tool_calls: 32,
    max_wall_clock_seconds: 120,
    max_concurrency: 1,
    units: ["tool_call_count", "wall_clock_seconds", "concurrency"],
    refused_units: ["token", "currency"],
    refused_units_detail: "TEST-ONLY: token ve para birimi sayilmaz.",
    detail: "TEST-ONLY: Tavan derleme zamaninda yazilir.",
    agent_can_raise_ceiling: false,
  },
  tools: [] as unknown[],
  honesty: RUN_HONESTY,
  stop_statement: "TEST-ONLY: Durdur, sonraki arac cagrisini engeller.",
  interrupted_runs: [] as unknown[],
  resumed_any: false,
};

/** Open Kanitlar and select the one task, so the workspace is on screen. */
async function openWorkspace(page: Page): Promise<void> {
  await navEntry(page, "Kanitlar").click();
  await page.getByRole("radio", { name: new RegExp(TASK.title) }).check();
  await expect(page.getByRole("region", { name: "Uretilen dosyalar" })).toBeVisible();
}

/** Open Gorevler and the one task's detail. */
async function openTaskDetail(page: Page): Promise<void> {
  await navEntry(page, "Gorevler").click();
  await page.getByRole("radio", { name: new RegExp(TASK.title) }).check();
  await expect(page.getByRole("region", { name: "Gorev ayrintisi" })).toBeVisible();
}

test.describe("Kanit calisma alani", () => {
  test("opens from the keyboard and says what a digest does not establish", async ({
    page,
  }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);

    const entry = navEntry(page, "Kanitlar");
    // Focus and Enter, not a click: a section reachable only by mouse is a
    // section a keyboard user does not have.
    await entry.focus();
    await expect(entry).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(entry).toHaveAttribute("aria-current", "page");

    await page.getByRole("radio", { name: new RegExp(TASK.title) }).check();
    await expect(page.getByTestId("proof-hash-scope")).toContainText(HASH_SCOPE);
    await expect(page.getByTestId("proof-bundle-scope")).toContainText(BUNDLE_SCOPE);

    // The digest is twelve characters, and a 64-hex run - the same shape as a
    // seed - appears nowhere on the page.
    await expect(page.getByTestId("proof-bundle-digest")).toHaveText("efefefefefef");
    const seedShaped = await page.evaluate(() =>
      /\b[0-9a-fA-F]{64}\b/.test(document.body.textContent ?? ""),
    );
    expect(seedShaped, "no 64-hex run may reach the DOM").toBe(false);

    // Reading built and delivered nothing.
    expect(ledger.posts).toEqual([]);
  });

  test("reports the three unproduced records without a single success glyph", async ({
    page,
  }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);
    await openWorkspace(page);

    for (const [key, detail] of [
      ["independent_check", INDEPENDENT_DETAIL],
      ["exit_code", EXIT_CODE_DETAIL],
      ["test_result", TEST_RESULT_DETAIL],
    ] as const) {
      const claim = page.getByTestId(`proof-claim-${key}`);
      await expect(claim).toContainText("not_implemented");
      await expect(claim).toContainText(detail);
    }

    // Measured in the real DOM. A tick or the word "dogrulandi" inside one of
    // these rows would present a closed lane as a passed check.
    const dishonest = await page.evaluate(() =>
      ["independent_check", "exit_code", "test_result"]
        .map(
          (key) =>
            document.querySelector(`[data-testid="proof-claim-${key}"]`)?.textContent ?? "",
        )
        .filter((text) => text.includes("✓") || /dogrulan|kanitlan|onaylan/i.test(text)),
    );
    expect(dishonest, "an unimplemented record may not be badged as verified").toEqual([]);

    // Nor may anything on the page announce the derived state as reachable.
    await expect(page.getByTestId("proof-publish-unreachable")).toContainText(
      "tasiyan bir kullanici yolu bu surumde yoktur",
    );
  });

  test("names every gap and invents no progress", async ({ page }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);
    await openWorkspace(page);

    await expect(page.getByTestId("proof-missing-evidence.test_result")).toContainText(
      "not_implemented",
    );
    await expect(page.getByTestId("proof-missing-artifact.ozet.md")).toContainText("absent");
    await expect(page.getByTestId("proof-missing-rule")).toContainText(
      "puan, yuzde, tamamlanma orani veya tek bir rozet yoktur",
    );

    const measured = await page.evaluate(() => ({
      progress: document.querySelectorAll("progress, [role='progressbar']").length,
      percent: /\d\s*%/.test(document.body.textContent ?? ""),
      animated: [...document.querySelectorAll("*")].filter((element) =>
        /\banimate-|\bspinner\b/.test(element.className.toString()),
      ).length,
    }));
    expect(measured.progress).toBe(0);
    expect(measured.percent, "a percentage would sum four different gaps").toBe(false);
    expect(measured.animated).toBe(0);
  });

  test("states the approval's terms before anything can spend one", async ({ page }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);
    await openWorkspace(page);

    const terms = page.getByTestId("proof-share-terms");
    await expect(terms).toContainText("Onay bir kez harcanir");
    await expect(terms).toContainText("Reddedilen bir teslim de onayi harcar");
    await expect(terms).toContainText("180 saniye");
    await expect(terms).toContainText("hicbir yola yazilmaz");

    // Both deliveries are locked while the terms are being read.
    await expect(page.getByRole("button", { name: "JSON olarak indir" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Markdown olarak indir" })).toBeDisabled();
    expect(ledger.posts).toEqual([]);
  });

  test("delivers a real file only after an approval and a consent, and spends both", async ({
    page,
  }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);
    await openWorkspace(page);

    const json = page.getByRole("button", { name: "JSON olarak indir" });
    await expect(json).toBeDisabled();

    await page.getByRole("button", { name: "Tek kullanimlik onay hazirla" }).click();
    await expect(page.getByTestId("proof-share-state")).toContainText("Onay hazir");
    // An approval without consent still delivers nothing.
    await expect(json).toBeDisabled();

    // Space on the focused input, not a pointer click: the HeroUI checkbox
    // keeps its real input behind a styled control, and this also says the
    // consent can be given without a mouse.
    const consent = page.getByRole("checkbox", { name: /tek kullanimlik oldugunu/ });
    await consent.focus();
    await consent.press("Space");
    await expect(consent).toBeChecked();
    await expect(json).toBeEnabled();

    const downloadPromise = page.waitForEvent("download");
    await json.click();
    const download = await downloadPromise;

    // The name is this app's own constant, not the server's header: the
    // download name is a client-side concern and there is no parser here to
    // be wrong about it.
    expect(download.suggestedFilename()).toBe("technocore-station-kanit-paketi.json");
    await expect(page.getByTestId("proof-share-result")).toContainText(
      "technocore-station-kanit-paketi.json",
    );

    // The request carried a token, a format and an acknowledgement - and no
    // destination of any kind.
    const share = ledger.posts.find((post) => post.url.endsWith("/share"));
    expect(share?.body).toEqual({
      share_token: SHARE_TOKEN,
      format: "json",
      acknowledged: true,
    });

    // The approval is gone, and the surface says so rather than leaving a
    // control that would now be refused.
    await expect(page.getByTestId("proof-share-state")).toContainText("Onay harcandi");
    await expect(page.getByRole("button", { name: "Markdown olarak indir" })).toBeDisabled();
    await expect(json).toBeDisabled();
    expect(ledger.posts.filter((post) => post.url.endsWith("/share"))).toHaveLength(1);
  });

  test("drops a held approval when the bundle is read again", async ({ page }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);
    await openWorkspace(page);

    await page.getByRole("button", { name: "Tek kullanimlik onay hazirla" }).click();
    await expect(page.getByTestId("proof-share-state")).toContainText("Onay hazir");

    await page.getByRole("button", { name: /Paketi yeniden oku/ }).click();
    await expect(page.getByTestId("proof-share-state")).toContainText(
      "Henuz onay hazirlanmadi",
    );
    await expect(page.getByRole("button", { name: "JSON olarak indir" })).toBeDisabled();
  });

  test("violates no CSP rule and logs no console error", async ({ consoleLog, page }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);
    await openWorkspace(page);

    expect(consoleLog.cspViolations(), "CSP refusals while rendering the proof").toEqual([]);
    expect(consoleLog.errors, "console errors while rendering the proof").toEqual([]);
  });
});

test.describe("Kabul ve dis paylasim isareti", () => {
  test("accepts only a bundle that was read, and moves nothing", async ({ page }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);
    await openTaskDetail(page);

    // Before the bundle is read there is no acceptance control at all.
    await expect(page.getByTestId("tasks-acceptance-unread")).toContainText(
      "Okunmamis bir paket kabul edilemez",
    );
    await expect(page.getByRole("button", { name: /Kabulumu kaydet/ })).toHaveCount(0);

    await page.getByRole("button", { name: /Kabul edilecek paketi oku/ }).click();
    await expect(page.getByTestId("tasks-acceptance-digest")).toContainText("efefefefefef");
    // The gap is named while the tick is being given.
    await expect(page.getByTestId("tasks-acceptance-missing")).toContainText(
      "evidence.test_result",
    );

    const accept = page.getByRole("button", { name: /Kabulumu kaydet/ });
    await expect(accept).toBeDisabled();

    const tick = page.getByRole("checkbox", { name: /Bu paketi okudum/ });
    await tick.focus();
    await tick.press("Space");
    await expect(accept).toBeEnabled();
    await accept.click();

    await expect(page.getByTestId("tasks-acceptance-no-transition")).toContainText(
      "Kabul bir gecis degildir",
    );

    // The body carried the digest of what was read, and two keys only: no
    // state, no target, no transition.
    const acceptance = ledger.posts.find((post) => post.url.endsWith("/acceptance"));
    expect(acceptance?.body).toEqual({ bundle_sha256: BUNDLE_SHA, detail: "" });

    // And no transition request was made as a side effect.
    expect(ledger.posts.filter((post) => post.url.endsWith("/state"))).toHaveLength(0);
    await expect(page.getByTestId("tasks-publish-state")).toContainText("Yayima hazir degil");
  });

  test("keeps an archived send apart from a verified one", async ({ page }) => {
    const ledger: ProofLedger = { posts: [] };
    await mockProof(page, ledger);
    await openApp(page);
    await openTaskDetail(page);

    await expect(page.getByTestId("tasks-public-share-no-send")).toContainText(
      "hicbir sey gondermez ve gonderemez",
    );
    await expect(page.getByTestId("tasks-public-share-verification-rule")).toContainText(
      "Arsivlenmis olmak dogrulanmis olmak degildir",
    );

    await page.getByRole("button", { name: /Arsivlenmis gonderimleri listele/ }).click();
    await expect(page.getByTestId("tasks-public-share-archive")).toBeVisible();

    const accepted = page.getByTestId(`tasks-archived-send-${ACCEPTED_SEND_ID}`);
    const unknown = page.getByTestId(`tasks-archived-send-${UNKNOWN_SEND_ID}`);
    await expect(accepted).toContainText("dogrulanmis olarak kaydedilir");
    await expect(unknown).toContainText("kaydedilir, dogrulanmis sayilmaz");

    // The unknown outcome carries no success glyph: "we do not know" and
    // "it was published" are different findings and stay different.
    const glyphs = await page.evaluate(
      (id) =>
        document.querySelector(`[data-testid="tasks-archived-send-${id}"]`)?.textContent ?? "",
      UNKNOWN_SEND_ID,
    );
    expect(glyphs.includes("✓")).toBe(false);

    await unknown.getByRole("radio").check();
    await page.getByRole("button", { name: /Bu gonderimi bu goreve isaretle/ }).click();

    const mark = ledger.posts.find((post) => post.url.endsWith("/public-share"));
    // An identity and a note. No room, no address, no text: nothing in this
    // request could reach an outbound client.
    expect(mark?.body).toEqual({ evidence_id: UNKNOWN_SEND_ID, detail: "" });
  });
});
