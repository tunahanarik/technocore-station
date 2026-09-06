/**
 * "Is Tara" in a real browser: the section opens, the scan flow runs, and
 * nothing leaves the machine.
 *
 * The whole `/api/workscan/*` group is answered from `harness/workscan.ts`.
 * That is not convenience - it is the constraint. A real scan makes the
 * **backend** open outbound connections to `technocore.chat`, which ADR-0006 2
 * puts at zero for this suite and which no browser-side ledger could see.
 * Fulfilling the four routes locally means the flow under test is the one the
 * user drives while the server is never asked to read a public room at all.
 *
 * What is therefore proven here, and what is not: this spec proves the
 * rendering and the interaction - that the section is reachable by keyboard,
 * that a scan runs end to end, that a quoted line is inert text, that no
 * open/closed badge exists and that the strict CSP is not violated. It does
 * not prove anything about the backend's own reads; those are the Python
 * suite's, and a browser test claiming them would be claiming them from the
 * wrong side of the wire.
 *
 * The fixtures moved out of this file when `keyboard.spec.ts` needed the same
 * payloads to drive the candidate list's scroll container. They are shared
 * rather than copied so the two specs cannot disagree about what the backend
 * returns.
 *
 * No room named in this file is Lobby, in any fixture or any assertion.
 */

import {
  HONESTY,
  HOSTILE_TOPIC,
  QUOTE,
  READING_COST,
  ROOM_A,
  ROOM_B,
  type ScanLedger,
  mockScanSurface,
  tickRoom,
} from "../harness/workscan";
import { expect, navEntry, openApp, test } from "../fixtures";

test.describe("Is Tara", () => {
  test("appears in the navigation and opens from the keyboard", async ({ page }) => {
    const ledger: ScanLedger = { cursors: [], rooms: [] };
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
    const limits = page.getByRole("region", { name: "Cikarim sinirlari" });
    await expect(limits).toContainText(HONESTY);
    // ADR-0014: the cost is on screen before the button is pressed, and the
    // sentence that promised this build inferred nothing is gone rather than
    // moved. The retired phrase is assembled rather than written out because
    // `test_model_lane_claims.py` scans this tree for it as text, and a file
    // that spelled it would need an exemption from that scan.
    await expect(limits).toContainText(READING_COST);
    await expect(limits).not.toContainText(["anlamsal", "cikarim", "yoktur"].join(" "));
    // Exactly one entry is current at a time.
    await expect(
      page.getByRole("navigation", { name: "Ana bolumler" }).locator("[aria-current]"),
    ).toHaveCount(1);
  });

  test("runs the scan flow and sends only the rooms that were ticked", async ({ page }) => {
    const ledger: ScanLedger = { cursors: [], rooms: [] };
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
    const ledger: ScanLedger = { cursors: [], rooms: [] };
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

  test("renders a room topic that reads like an instruction as inert data", async ({
    consoleLog,
    page,
  }) => {
    const ledger: ScanLedger = { cursors: [], rooms: [] };
    await mockScanSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Is Tara").click();
    await page.getByRole("button", { name: "Oda listesini oku" }).click();

    // Measured in the real DOM rather than in jsdom: the topic is one text
    // node, the markup inside it created no element, and nothing in the block
    // it lives in is clickable.
    const topic = page.getByTestId(`workscan-room-topic-${ROOM_A}`);
    await expect(topic).toHaveText(HOSTILE_TOPIC);
    const rendered = await topic.evaluate((element) => ({
      tag: element.tagName,
      children: element.querySelectorAll("*").length,
      links: element.closest("[data-testid^='workscan-room-untrusted-']")
        ?.querySelectorAll("a").length ?? -1,
    }));
    expect(rendered.tag).toBe("PRE");
    expect(rendered.children, "a topic must create no elements").toBe(0);
    expect(rendered.links, "a topic is never a link").toBe(0);

    // The caller's strings and the service's measurements are two boxes, and
    // neither is inside the other.
    const nested = await page.evaluate((room) => {
      const untrusted = document.querySelector(`[data-testid="workscan-room-untrusted-${room}"]`);
      const measured = document.querySelector(`[data-testid="workscan-room-measured-${room}"]`);
      return {
        found: untrusted !== null && measured !== null,
        overlaps:
          (untrusted?.contains(measured ?? null) ?? true) ||
          (measured?.contains(untrusted ?? null) ?? true),
      };
    }, ROOM_A);
    expect(nested.found).toBe(true);
    expect(nested.overlaps, "the two halves may not nest").toBe(false);
    await expect(page.getByTestId(`workscan-room-measured-${ROOM_A}`)).toContainText(
      "messages: 1284",
    );

    // A hostile string in the DOM must not have cost anything at the policy
    // layer either.
    expect(consoleLog.cspViolations(), "CSP refusals while rendering a hostile topic").toEqual([]);
    expect(consoleLog.errors, "console errors while rendering a hostile topic").toEqual([]);
  });

  test("reads the discovery log on request and feeds the same bounded scope", async ({
    consoleLog,
    page,
  }) => {
    const ledger: ScanLedger = { cursors: [], rooms: [] };
    await mockScanSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Is Tara").click();

    // Not read until asked, and "not read" is a different sentence from
    // "read and empty".
    await expect(page.getByText("Kesif gunlugu bu oturumda henuz okunmadi")).toBeVisible();
    expect(ledger.cursors).toEqual([]);

    await page.getByRole("button", { name: "Kesif gunlugunu oku" }).click();
    await expect(page.getByTestId("workscan-discovery-counts")).toContainText("secilebilir: 1");
    // A first read carries no cursor.
    expect(ledger.cursors).toEqual([null]);

    // The unreadable line is shown as it arrived, with the reason beside it.
    await expect(page.getByTestId("workscan-discovery-line-92")).toHaveText(
      "new room opened: TEST-ONLY-forum (by nobody in particular)",
    );
    await expect(page.getByTestId("workscan-discovery-reason-92")).toContainText(
      "ayristirici uydurmaz",
    );
    await expect(page.getByTestId("workscan-discovery-write-refusal")).toContainText("403");

    // Continuing is a press that carries the cursor the reading reported.
    await page.getByRole("button", { name: "Bu okumanin devamini oku (since 92)" }).click();
    await expect(page.getByTestId("workscan-discovery-counts")).toContainText("secilebilir: 1");
    expect(ledger.cursors).toEqual([null, 92]);

    // The announced room reaches the scan through the ordinary scope, and the
    // scope is still only what was ticked.
    const log = page.getByRole("region", { name: "Kesif gunlugu" });
    const box = log.getByRole("checkbox", { name: new RegExp(ROOM_B) });
    await box.focus();
    await box.press("Space");
    await expect(box).toBeChecked();
    await page.getByRole("button", { name: "Secili odalari tara" }).click();
    expect(ledger.rooms).toEqual([[ROOM_B]]);

    expect(consoleLog.cspViolations(), "CSP refusals while reading the log").toEqual([]);
    expect(consoleLog.errors, "console errors while reading the log").toEqual([]);
  });

  test("shows the Kibble record as unverified support and violates no CSP rule", async ({
    consoleLog,
    page,
  }) => {
    const ledger: ScanLedger = { cursors: [], rooms: [] };
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
