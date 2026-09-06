/**
 * Real keyboard navigation.
 *
 * jsdom has no focus model worth the name: `Tab` does nothing, tab order is
 * not computed, and `:focus-visible` does not exist. Testing-library's
 * `user-event` simulates a tab order from the DOM rather than reading the
 * browser's, so a Vitest test can agree with itself while the shipped app
 * traps or skips a control. These assertions are about what Chromium actually
 * does with the production bundle.
 */

import type { Locator, Page } from "@playwright/test";

import {
  ROOM_A,
  type ScanLedger,
  mockScanSurface,
  scanWithCandidates,
  tickRoom,
} from "../harness/workscan";
import { SECTION_LABELS, expect, gotoSection, navEntry, openApp, test } from "../fixtures";

/** The accessible name of whatever currently has focus. */
async function focusedName(page: Page): Promise<string> {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (element === null) return "";
    const label = element.getAttribute("aria-label");
    return (label ?? element.textContent ?? "").replace(/\s+/g, " ").trim();
  });
}

test.describe("keyboard navigation", () => {
  test("tab order walks the collapse control, then the sections in order", async ({ page }) => {
    await openApp(page);
    await page.locator("body").press("Tab");

    // The collapse toggle is the first thing a keyboard user reaches: it is
    // the control that changes the shape of everything after it.
    expect(await focusedName(page)).toBe("Menuyu daralt");

    for (const label of SECTION_LABELS) {
      await page.keyboard.press("Tab");
      const focused = await focusedName(page);
      expect(focused, `after ${label} the focus order diverged`).toContain(label);
    }
  });

  test("Enter on a focused section selects it", async ({ page }) => {
    await openApp(page);

    const target = navEntry(page, "Kanitlar");
    await target.focus();
    await expect(target).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(target).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("region", { name: "Kanit defteri" })).toBeVisible();

    // Exactly one entry is current at a time - the previous one must have
    // given the attribute up, not merely shared it.
    const current = page.getByRole("navigation", { name: "Ana bolumler" }).locator("[aria-current]");
    await expect(current).toHaveCount(1);
  });

  test("aria-current follows the selection and the label says so out loud", async ({ page }) => {
    await openApp(page);

    // The default section on launch.
    await expect(navEntry(page, "Genel Bakis")).toHaveAttribute("aria-current", "page");
    await expect(navEntry(page, "Genel Bakis")).toContainText("(secili bolum)");

    await gotoSection(page, "Kimlik ve Guvenlik");
    await expect(navEntry(page, "Genel Bakis")).not.toHaveAttribute("aria-current", "page");
    await expect(navEntry(page, "Kimlik ve Guvenlik")).toContainText("(secili bolum)");
  });

  test("collapsing narrows the menu without taking it away", async ({ page }) => {
    await openApp(page);

    const nav = page.getByRole("navigation", { name: "Ana bolumler" });
    const toggle = page.getByRole("button", { name: "Menuyu daralt" });
    await expect(toggle).toHaveAttribute("aria-expanded", "true");

    await toggle.click();
    const reopen = page.getByRole("button", { name: "Menuyu ac" });
    await expect(reopen).toHaveAttribute("aria-expanded", "false");

    // The landmark and every entry survive: a collapsed menu that unmounted
    // the <nav> would take the whole menu away from a screen-reader user
    // while a sighted user still sees a narrow one.
    await expect(nav).toBeVisible();
    for (const label of SECTION_LABELS) {
      await expect(navEntry(page, label)).toBeVisible();
    }

    // And it is still operable by keyboard while collapsed.
    await navEntry(page, "Kaynaklar").focus();
    await page.keyboard.press("Enter");
    await expect(navEntry(page, "Kaynaklar")).toHaveAttribute("aria-current", "page");

    await reopen.click();
    await expect(toggle).toBeVisible();
  });

  test("the collapse toggle points at the menu it controls", async ({ page }) => {
    await openApp(page);

    const toggle = page.getByRole("button", { name: "Menuyu daralt" });
    const controls = await toggle.getAttribute("aria-controls");
    expect(controls).toBeTruthy();
    // Attribute selector, not `#id`: React's generated ids contain
    // characters that are not valid in a CSS id selector without escaping.
    await expect(page.locator(`[id="${String(controls)}"]`)).toHaveRole("navigation");
  });
});

/**
 * The candidate list's scroll container, measured in a real browser.
 *
 * jsdom has no layout, so "the page grows instead of the list scrolling" is
 * not a statement any Vitest test can make: `clientHeight` is zero there and
 * every box is the same size as every other. The three assertions below are
 * the ones that need Chromium - a document that stops growing when the reply
 * grows, a box that really scrolls, and a keyboard user who can still get out
 * of it.
 */
test.describe("the candidate list is bounded, and still operable by keyboard", () => {
  /** Run one scan and return the candidate list. */
  async function scanned(page: Page): Promise<Locator> {
    await gotoSection(page, "Is Tara");
    await page.getByRole("button", { name: "Oda listesini oku" }).click();
    await tickRoom(page, ROOM_A);
    await page.getByRole("button", { name: "Secili odalari tara" }).click();
    const list = page.getByRole("region", { name: "Adaylar" }).locator("> ul");
    await expect(list).toBeVisible();
    return list;
  }

  test("the page stops growing when the reply carries more candidates", async ({ page }) => {
    let count = 2;
    const ledger: ScanLedger = { cursors: [], rooms: [] };
    await mockScanSurface(page, ledger, () => scanWithCandidates(count));
    await openApp(page);

    // Measured on the `main` landmark rather than on
    // `documentElement.scrollHeight`: the shell is a flex column with
    // `min-h-screen`, so the document's own scroll height is not a reading of
    // how tall the section became, and it was observed reporting a figure the
    // laid-out tree did not agree with.
    const pageHeight = async (): Promise<number> =>
      page.getByRole("main").evaluate((el) => el.getBoundingClientRect().height);

    const list = await scanned(page);
    await expect(list.locator("> li")).toHaveCount(2);
    const card = await list
      .locator("> li")
      .first()
      .evaluate((el) => el.getBoundingClientRect().height);
    const short = await pageHeight();

    // The same surface, ten more candidates. Nothing else about the reply
    // changes, so any growth in the section is growth the list caused.
    count = 12;
    await page.getByRole("button", { name: "Secili odalari tara" }).click();
    await expect(list.locator("> li")).toHaveCount(12);
    const tall = await pageHeight();

    // Ten more cards used to add ten more cards' worth of page - 6660px,
    // measured. The bound makes the difference smaller than a single card,
    // which is the only threshold that separates "bounded" from "grew a
    // little less".
    expect(card, "a candidate card should be a substantial box").toBeGreaterThan(200);
    expect(
      tall - short,
      `ten more candidates grew the section by ${String(Math.round(tall - short))}px ` +
        `against a ${String(Math.round(card))}px card`,
    ).toBeLessThan(card);
  });

  test("the list scrolls inside itself rather than pushing its own controls away", async ({
    page,
  }) => {
    const ledger: ScanLedger = { cursors: [], rooms: [] };
    await mockScanSurface(page, ledger, () => scanWithCandidates(8));
    await openApp(page);
    const list = await scanned(page);

    const box = await list.evaluate((el) => ({
      client: el.clientHeight,
      scroll: el.scrollHeight,
      viewport: window.innerHeight,
    }));
    // It really has more content than box...
    expect(box.scroll, "the list must actually overflow its box").toBeGreaterThan(box.client);
    // ...and the box itself fits the window, which is what keeps the button
    // under the list on screen.
    expect(box.client, "the list must fit inside the viewport").toBeLessThanOrEqual(
      box.viewport,
    );
  });

  test("a keyboard user can walk the list, scroll it and leave it", async ({ page }) => {
    const ledger: ScanLedger = { cursors: [], rooms: [] };
    await mockScanSurface(page, ledger, () => scanWithCandidates(8));
    await openApp(page);
    const list = await scanned(page);

    // A scroll container must not be given a tab stop of its own when its
    // content is already focusable: that would be one more press between a
    // keyboard user and the button, for nothing.
    expect(await list.getAttribute("tabindex")).toBeNull();

    const radios = list.locator('input[type="radio"]');
    await expect(radios).toHaveCount(8);
    await radios.first().focus();
    await expect(radios.first()).toBeFocused();
    expect(await list.evaluate((el) => el.scrollTop)).toBe(0);

    // Arrow keys, because a radio group is one tab stop: this is how a
    // keyboard user actually moves between candidates.
    for (let press = 0; press < 7; press += 1) {
      await page.keyboard.press("ArrowDown");
    }
    await expect(radios.last()).toBeFocused();
    await expect(radios.last()).toBeChecked();

    // The container scrolled to follow the focus - the browser could only do
    // that because the container is the scrollable thing.
    expect(
      await list.evaluate((el) => el.scrollTop),
      "the list must scroll to keep the focused candidate visible",
    ).toBeGreaterThan(0);

    // And it is not a trap: one Tab leaves the group for the control the list
    // exists to feed.
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("button", { name: "Secili adayi yerel gorev olarak ac" }),
    ).toBeFocused();
  });
});

/**
 * The task screen's disclosures, from the keyboard only.
 *
 * `keyboard.spec.ts` is where "can a person do this without a mouse" is
 * measured, and progressive disclosure is exactly the kind of change that
 * passes a mouse test and fails a keyboard one. Both keys the platform binds
 * to a disclosure are checked, because a control that answers only Enter is a
 * control half the keyboard cannot use.
 */
test.describe("Gorevler disclosures from the keyboard", () => {
  test("Tab reaches a folded block and Space opens it", async ({ page }) => {
    await openApp(page);
    await gotoSection(page, "Gorevler");

    const region = page.getByRole("region", { name: "Butce ve tavan" });
    const summary = region.locator("summary");
    const ceiling = page.getByTestId("tasks-budget-refused-detail");

    // The claim it guards is in the document and off the screen.
    await expect(ceiling).toHaveCount(1);
    await expect(ceiling).toBeHidden();

    // Reached by Tab, not by a click: `summary` is focusable by default and
    // this is the assertion that keeps it that way if anyone ever swaps it
    // for a styled div.
    await summary.focus();
    await expect(summary).toBeFocused();
    await page.keyboard.press("Space");
    await expect(ceiling).toBeVisible();

    // The refused units are the point of the block, and they are readable
    // without a pointer.
    await expect(page.getByTestId("tasks-budget-refused-units")).toContainText("token");
    await expect(page.getByText("Agent kendi butcesini yukseltemez")).toBeVisible();
  });

  test("opening one block leaves the others as they were", async ({ page }) => {
    await openApp(page);
    await gotoSection(page, "Gorevler");

    const execution = page.getByRole("region", { name: "Yurutme durumu" }).locator("details");
    const trust = page.getByRole("region", { name: "Guven siniri" }).locator("details");
    await expect(execution).not.toHaveAttribute("open", "");
    await expect(trust).not.toHaveAttribute("open", "");

    await execution.locator("summary").focus();
    await page.keyboard.press("Enter");

    // Not an accordion: these are independent claims and reading one is not a
    // reason to fold another away.
    await expect(execution).toHaveAttribute("open", "");
    await expect(trust).not.toHaveAttribute("open", "");
  });
});
