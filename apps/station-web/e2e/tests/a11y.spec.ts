/**
 * An accessibility smoke pass over every section, in a real browser.
 *
 * Deliberately narrow: plain DOM and accessibility-tree assertions, no new
 * dependency. This is not a WCAG audit and does not claim to be one - it
 * catches the structural regressions that a real page can have and a jsdom
 * render cannot show, and leaves judgement to a human review.
 */

import type { Page } from "@playwright/test";

import { SECTION_LABELS, expect, gotoSection, openApp, test } from "../fixtures";

/** Form controls whose accessible name is missing. */
async function unnamedControls(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const controls = [
      ...document.querySelectorAll<HTMLElement>("input, textarea, select"),
    ];
    return controls
      .filter((control) => {
        const labelled = control as HTMLInputElement;
        const hasLabelElement = (labelled.labels?.length ?? 0) > 0;
        const aria = control.getAttribute("aria-label")?.trim() ?? "";
        const labelledBy = control.getAttribute("aria-labelledby")?.trim() ?? "";
        return !hasLabelElement && aria === "" && labelledBy === "";
      })
      .map((control) => {
        const type = control.getAttribute("type") ?? control.tagName.toLowerCase();
        const name = control.getAttribute("name") ?? "";
        return `${control.tagName.toLowerCase()}[type=${type}]${name === "" ? "" : `[name=${name}]`}`;
      });
  });
}

test.describe("accessibility smoke", () => {
  for (const label of SECTION_LABELS) {
    test(`${label}: one h1, the landmarks, and named form controls`, async ({ page }) => {
      await openApp(page);
      await gotoSection(page, label);

      // Exactly one level-1 heading. The shell owns it, so a section that
      // grew its own would produce two and break the document outline.
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);

      // The four landmarks a screen-reader user navigates by.
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("navigation", { name: "Ana bolumler" })).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      await expect(page.getByRole("contentinfo")).toHaveCount(1);

      expect(await unnamedControls(page), `unlabelled controls in ${label}`).toEqual([]);
    });
  }

  test("the heading outline is consistent and no worse than the known HeroUI gap", async ({
    page,
  }) => {
    await openApp(page);

    for (const label of SECTION_LABELS) {
      await gotoSection(page, label);
      const levels = await page.evaluate(() =>
        [...document.querySelectorAll("h1, h2, h3, h4, h5, h6")].map((heading) =>
          Number(heading.tagName.slice(1)),
        ),
      );

      expect(levels[0], `${label} must start at the shell's h1`).toBe(1);

      // KNOWN FINDING, recorded rather than papered over (docs/browser-qa.md
      // "Open findings"): HeroUI v3's `Card.Title` renders an `<h3>`, so the
      // outline steps h1 -> h3 on every section. It is a real, minor outline
      // defect, it is not this package's to fix - correcting it means
      // changing a HeroUI component's element, which CLAUDE.md rule 7
      // forbids guessing at - and it must not be allowed to get worse. So
      // the first step is bounded at h3 instead of h2: an h4 here would fail,
      // and so would a future regression, while a HeroUI fix to h2 would not
      // raise a false alarm.
      expect(levels[1] ?? 3, `${label}: the outline degraded past the known h1 -> h3 gap`)
        .toBeLessThanOrEqual(3);

      // Below that first step the outline must be strictly well formed.
      for (let index = 2; index < levels.length; index += 1) {
        const previous = levels[index - 1] ?? 1;
        const current = levels[index] ?? 1;
        expect(
          current - previous,
          `${label}: heading level jumped from h${String(previous)} to h${String(current)}`,
        ).toBeLessThanOrEqual(1);
      }
    }
  });

  test("every section is reachable and renders without a console error", async ({
    page,
    consoleLog,
  }) => {
    await openApp(page);

    for (const label of SECTION_LABELS) {
      await gotoSection(page, label);
      await expect(page.getByRole("main")).toBeVisible();
      // Something was actually rendered: an empty <main> would pass every
      // landmark assertion above while showing the user nothing.
      //
      // Polled rather than sampled once, and the threshold is unchanged. A
      // section whose panel reads on mount renders a short placeholder first
      // ("Kimlik okunuyor..." is 23 characters), so a single instantaneous
      // read raced the first paint and failed on timing rather than on
      // behaviour - intermittently, and on whichever section happened to be
      // slowest that run. Waiting for the same assertion to hold makes an
      // empty main still fail, and only an empty main fail.
      await expect
        .poll(
          async () => ((await page.getByRole("main").textContent()) ?? "").trim().length,
          { message: `${label} rendered an empty main`, timeout: 7_000 },
        )
        .toBeGreaterThan(50);
    }

    // Belt and braces: the auto fixture asserts this too, but naming it here
    // makes the requirement visible in the report rather than implicit.
    expect(consoleLog.errors).toEqual([]);
    expect(consoleLog.pageErrors).toEqual([]);
  });

  test("no image or icon is presented without an accessible name", async ({ page }) => {
    await openApp(page);

    for (const label of SECTION_LABELS) {
      await gotoSection(page, label);
      const undescribed = await page.evaluate(() =>
        [...document.querySelectorAll("img")]
          .filter(
            (image) =>
              image.getAttribute("alt") === null &&
              image.getAttribute("aria-hidden") !== "true" &&
              image.getAttribute("role") !== "presentation",
          )
          .map((image) => image.currentSrc || image.src),
      );
      expect(undescribed, `undescribed images in ${label}`).toEqual([]);
    }
  });
});
