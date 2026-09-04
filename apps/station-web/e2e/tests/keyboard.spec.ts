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

import { SECTION_LABELS, expect, gotoSection, navEntry, openApp, test } from "../fixtures";

/** The accessible name of whatever currently has focus. */
async function focusedName(page: import("@playwright/test").Page): Promise<string> {
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
