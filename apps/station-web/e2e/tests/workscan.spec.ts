/**
 * "Is Tara" in a real browser: the section opens, the scan flow runs, and
 * nothing leaves the machine.
 *
 * The whole `/api/workscan/*` group is answered from this file. That is not
 * convenience - it is the constraint. A real scan makes the **backend** open
 * outbound connections to `technocore.chat`, which ADR-0006 2 puts at zero
 * for this suite and which no browser-side ledger could see. Fulfilling the
 * four routes here means the flow under test is the one the user drives while
 * the server is never asked to read a public room at all.
 *
 * What is therefore proven here, and what is not: this spec proves the
 * rendering and the interaction - that the section is reachable by keyboard,
 * that a scan runs end to end, that a quoted line is inert text, that no
 * open/closed badge exists and that the strict CSP is not violated. It does
 * not prove anything about the backend's own reads; those are the Python
 * suite's, and a browser test claiming them would be claiming them from the
 * wrong side of the wire.
 *
 * No room named in this file is Lobby, in any fixture or any assertion.
 */

import type { Page } from "@playwright/test";

import { expect, navEntry, openApp, test } from "../fixtures";

/** TEST-ONLY room names. Neither is Lobby and neither is a real target. */
const ROOM_A = "TEST-ONLY-genesis";
const ROOM_B = "TEST-ONLY-signal-lab";

/** A line shaped like something a stranger could write, markup included. */
const QUOTE = "help wanted: kucuk bir CSV donusturucu lazim <script>alert(1)</script>";

const HONESTY =
  "Bu surum adaylari kalip eslesmesiyle cikarir; anlamsal cikarim yoktur, bu yuzden bir odadaki her firsat gorulmez.";

const BASE = {
  honesty: HONESTY,
  capability: {
    module_id: "work_scan",
    module_state: "available",
    module_available: true,
    write_gate_open: false,
    ready: false,
    detail: "Bu isi ustlenecek modul bu surumde var. Yazma kapisi su anda kapali.",
  },
  adapters: [
    {
      id: "kibble",
      name: "Kibble",
      support: "support_unverified",
      authority: 3,
      declared_origin: "https://flop-kibble.onrender.com",
      adapter_written: false,
      contacted: false,
      verified: [
        { key: "service_exists", detail: "TEST-ONLY.", state: "verified" },
        { key: "read_endpoints_documented", detail: "TEST-ONLY.", state: "verified" },
        { key: "lifecycle", detail: "TEST-ONLY.", state: "verified" },
        { key: "stats_shape", detail: "TEST-ONLY.", state: "verified" },
        { key: "self_description", detail: "TEST-ONLY.", state: "verified" },
      ],
      unverified: [
        { key: "job_schema", detail: "TEST-ONLY.", state: "not_verified" },
        { key: "pagination", detail: "TEST-ONLY.", state: "not_verified" },
        { key: "rate_limit", detail: "TEST-ONLY.", state: "not_verified" },
        { key: "terms", detail: "TEST-ONLY.", state: "not_verified" },
        { key: "operator", detail: "TEST-ONLY.", state: "not_verified" },
      ],
      self_description: "Servis kendini resmi kaynak saymadigini soyluyor.",
      self_description_source: "Kibble is not FLOP Network and not Technocore. It settles nothing.",
      score_self_description: "Advisory IOU from the public tape. Nothing is paid.",
      score_caveat:
        "Ucuncu tarafin 'score' veya 'rank' alani o tarafin kendi hesabidir; Station onu kendi cumlesine katmaz.",
      provenance: "Bu kayit 2026-09-04 tarihinde yazildi: 5 madde dogrulandi, 5 madde dogrulanamadi.",
    },
  ],
  room_index: null as unknown,
  last_scan: null as unknown,
  never_sent_params: ["n", "wait"],
  polling_statement:
    "Bu yuzeyde zamanlayici, arka plan gorevi ve uzun bekleme (long-poll) yoktur. Her giden istek, bir kullanici eyleminin icinde ve bir kez yapilir.",
  prohibition_statement:
    "Yasakli is bicimleri de ayni yontemle, kalip eslesmesiyle reddedilir. Yasak listede olmayan bir sozcukle istenirse aday uretilebilir; bu yuzden bir adayi kabul etmeden once alintiyi okuyun.",
};

const ROOM_INDEX = {
  rooms: [
    { name: ROOM_A, topic: "TEST-ONLY baslik", authority: 3 },
    { name: ROOM_B, topic: "", authority: 3 },
  ],
  total: 2,
  kept_count: 2,
  truncated: false,
  staleness: {
    read_at: "2026-09-04T10:00:00Z",
    declared_cache_seconds: 3,
    declared_by: "pinli referans deposu, config.py::ROOMS_CACHE_SECONDS",
    detail:
      "Anlik goruntu okundu. Servis bu listeyi en cok 3 saniye bayat verebilecegini kendi bildiriyor.",
  },
  sha256: "1f2e3d4c5b6a7988",
  room_name_caveat: "Oda adi, o odaya ilk yazan kisinin sectigi bir metindir.",
  topic_caveat:
    "Oda basligi dunyaya yazilabilir bir nottur: herkes her oda icin yazabilir. Servis onu dogrulamaz.",
};

const CANDIDATE = {
  id: "b7c1e64d9f2ab7c1e64d9f2ab7c1e64d",
  signal: "help_wanted",
  source: {
    room: ROOM_A,
    seq: 412,
    ts: "2026-09-04T09:58:11Z",
    author: "TEST-ONLY-nickname",
    author_is_did_key: false,
    author_detail: "Yazar alani did:key degil; yazanin kendi beyan ettigi bir takma addir.",
    quote: QUOTE,
    reference: `${ROOM_A}#412@2026-09-04T09:58:11Z`,
    authority: 3,
  },
  benefit: "TEST-ONLY: isi yapan kisi cagriyi karsilamis olur.",
  deliverable: "TEST-ONLY: tek bir somut cikti.",
  success_condition: "TEST-ONLY: cikti alintidaki istegi karsiliyor.",
  test_method: "TEST-ONLY: cikti alintiyla yan yana okunur.",
  capability: {
    module_id: "work_scan",
    module_state: "available",
    module_available: true,
    write_gate_open: false,
    ready: false,
    detail: "Modul var; yazma kapisi kapali.",
  },
  effort: { label: "tahmin", band: "bir oturum veya daha az", basis: "Bu deger olculmedi." },
  budget_state: "not_implemented",
  budget_detail: "Bu surumde butce yoktur; butce Paket H2'nin konusudur.",
  permissions: ["TEST-ONLY izin: paylasim composer'da ayri bir onaydir."],
  risks: ["TEST-ONLY risk: yalnizca okunan dilim gorulmustur."],
  open_state: {
    read_at: "2026-09-04T10:01:00Z",
    detail:
      "Su ana kadar okunanda kapanis isareti gorulmedi (anlik goruntu: 2026-09-04T10:01:00+00:00).",
  },
  derivation: "rule_based_pattern_match",
};

const WITH_ROOMS = { ...BASE, room_index: ROOM_INDEX };

const WITH_SCAN = {
  ...WITH_ROOMS,
  last_scan: {
    started_at: "2026-09-04T10:00:55Z",
    completed_at: "2026-09-04T10:01:02Z",
    rooms: [ROOM_A],
    results: [{ room: ROOM_A, candidates: [CANDIDATE], refusals: [], lines_read: 50 }],
    failures: [
      { room: ROOM_B, reason: "room_unreadable", detail: "TEST-ONLY: oda okunamadi." },
    ],
    candidate_count: 1,
    refusal_count: 0,
  },
};

/** Every room name this spec sends, recorded from the intercepted bodies. */
interface ScanLedger {
  readonly rooms: string[][];
}

/**
 * Answer the whole scan group locally.
 *
 * Registered before the app is opened, so the very first status read is
 * already served from here and the backend is never asked to reach a public
 * room.
 */
async function mockScanSurface(page: Page, ledger: ScanLedger): Promise<void> {
  await page.route(
    (url) => url.pathname.startsWith("/api/workscan/"),
    async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/workscan/rooms/refresh") {
        await route.fulfill({ json: WITH_ROOMS });
        return;
      }
      if (url.pathname === "/api/workscan/scan") {
        const body = route.request().postDataJSON() as { rooms: string[] };
        ledger.rooms.push(body.rooms);
        await route.fulfill({ json: WITH_SCAN });
        return;
      }
      await route.fulfill({ json: BASE });
    },
  );
}

/**
 * Tick a room the way a keyboard user does.
 *
 * The HeroUI checkbox keeps its real `<input>` in a visually hidden span
 * behind a styled control, so a pointer click lands on the decoration. Space
 * on the focused input is both the reliable path and the one a keyboard user
 * actually takes - which makes this say something extra: choosing the scope
 * of a scan is possible without a mouse.
 */
async function tickRoom(page: Page, room: string): Promise<void> {
  const box = page.getByRole("checkbox", { name: new RegExp(room) });
  await expect(box).not.toBeChecked();
  await box.focus();
  await expect(box).toBeFocused();
  await box.press("Space");
  await expect(box).toBeChecked();
}

test.describe("Is Tara", () => {
  test("appears in the navigation and opens from the keyboard", async ({ page }) => {
    const ledger: ScanLedger = { rooms: [] };
    await mockScanSurface(page, ledger);
    await openApp(page);

    const entry = navEntry(page, "Is Tara");
    await expect(entry).toBeVisible();

    // Focus and Enter, not a click: a section reachable only by mouse is a
    // section a keyboard user does not have.
    await entry.focus();
    await expect(entry).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(entry).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("region", { name: "Oda secimi" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Cikarim sinirlari" })).toContainText(HONESTY);
    // Exactly one entry is current at a time.
    await expect(
      page.getByRole("navigation", { name: "Ana bolumler" }).locator("[aria-current]"),
    ).toHaveCount(1);
  });

  test("runs the scan flow and sends only the rooms that were ticked", async ({ page }) => {
    const ledger: ScanLedger = { rooms: [] };
    await mockScanSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Is Tara").click();

    // Nothing is scannable before the user asks for the list: the scope is a
    // decision, not a default.
    await expect(page.getByText("Oda listesi bu oturumda henuz okunmadi")).toBeVisible();
    await expect(page.getByRole("button", { name: "Secili odalari tara" })).toBeDisabled();

    await page.getByRole("button", { name: "Oda listesini oku" }).click();
    await expect(page.getByRole("checkbox", { name: new RegExp(ROOM_A) })).toBeVisible();
    // The staleness line carries the measured moment and the service's own
    // declared bound - and no verdict built from them.
    await expect(page.getByTestId("workscan-staleness-rooms")).toContainText("3 saniye");

    await tickRoom(page, ROOM_A);
    await page.getByRole("button", { name: "Secili odalari tara" }).click();

    await expect(page.getByRole("region", { name: "Adaylar" })).toContainText("Aday:");
    // The scope that reached the wire is the tick list, and only it.
    expect(ledger.rooms).toEqual([[ROOM_A]]);

    // The unread room is reported by name rather than folded into "nothing
    // found", and the ring-drop signal has its own region.
    await expect(page.getByTestId("workscan-failures")).toContainText(ROOM_B);
    await expect(page.getByTestId("workscan-ring-drop")).toContainText("first_seq");
  });

  test("renders a quoted line as inert text and shows no open/closed badge", async ({ page }) => {
    const ledger: ScanLedger = { rooms: [] };
    await mockScanSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Is Tara").click();
    await page.getByRole("button", { name: "Oda listesini oku" }).click();
    await tickRoom(page, ROOM_A);
    await page.getByRole("button", { name: "Secili odalari tara" }).click();

    const quote = page.getByTestId("workscan-quote");
    await expect(quote).toHaveText(QUOTE);

    // Measured in the real DOM: the markup inside the line is text, and no
    // script element was created from it.
    const rendered = await quote.evaluate((element) => ({
      tag: element.tagName,
      scripts: element.querySelectorAll("script").length,
      links: element.closest("li")?.querySelectorAll("a").length ?? -1,
    }));
    expect(rendered.tag).toBe("PRE");
    expect(rendered.scripts).toBe(0);
    expect(rendered.links).toBe(0);

    // Element 8 is a sentence with a timestamp, never a one-word verdict.
    await expect(page.getByTestId("workscan-open-state")).toContainText(
      "kapanis isareti gorulmedi",
    );
    const verdicts = await page.evaluate(() =>
      [...document.querySelectorAll("*")].filter((element) =>
        /^(acik|açık|kapali|kapalı|open|closed)$/i.test((element.textContent ?? "").trim()),
      ).length,
    );
    expect(verdicts, "no boolean open/closed badge may exist on this surface").toBe(0);
  });

  test("shows the Kibble record as unverified support and violates no CSP rule", async ({
    consoleLog,
    page,
  }) => {
    const ledger: ScanLedger = { rooms: [] };
    await mockScanSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Is Tara").click();

    const records = page.getByRole("region", { name: "Dis servis kayitlari" });
    await expect(records).toContainText("Destek dogrulanamadi");
    await expect(records).toContainText("Hicbir istek gonderilmedi");
    await expect(records).toContainText("Dogrulanan (5)");
    await expect(records).toContainText("Dogrulanamayan (5)");
    // The service's own sentences, quoted rather than paraphrased.
    await expect(records).toContainText("It settles nothing.");
    await expect(records).toContainText("Nothing is paid.");

    // The strict policy is what makes an inline handler or a smuggled style
    // impossible; a violation here would be a real regression, not noise.
    expect(consoleLog.cspViolations(), "CSP refusals while rendering Is Tara").toEqual([]);
    expect(consoleLog.errors, "console errors while rendering Is Tara").toEqual([]);
  });
});
