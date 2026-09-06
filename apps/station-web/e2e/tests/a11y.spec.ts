/**
 * An accessibility smoke pass over every section, in a real browser.
 *
 * Deliberately narrow: plain DOM and accessibility-tree assertions, no new
 * dependency. This is not a WCAG audit and does not claim to be one - it
 * catches the structural regressions that a real page can have and a jsdom
 * render cannot show, and leaves judgement to a human review.
 */

import type { Page } from "@playwright/test";

import {
  ROOM_A,
  type ScanLedger,
  mockScanSurface,
  scanWithCandidates,
  tickRoom,
} from "../harness/workscan";
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

  test("no section hides content in a box that cannot be scrolled", async ({ page }) => {
    // The other half of bounding a list. A height bound with no overflow rule
    // does not scroll - it *clips*, and the clipped part is unreachable by
    // mouse, keyboard and screen reader alike. Measured in a real browser
    // because it is a layout fact: jsdom reports every box as zero-sized and
    // would agree with any styling at all.
    //
    // The scan surface is driven into a state that actually has a bounded
    // list in it, because a section with nothing tall on it would satisfy
    // this rule by having nothing to check. The mock answers the whole
    // `/api/workscan/*` group locally, so no room is read (ADR-0006 2).
    const ledger: ScanLedger = { cursors: [], rooms: [] };
    await mockScanSurface(page, ledger, () => scanWithCandidates(6));
    await openApp(page);

    for (const label of SECTION_LABELS) {
      await gotoSection(page, label);
      if (label === "Is Tara") {
        await page.getByRole("button", { name: "Oda listesini oku" }).click();
        await tickRoom(page, ROOM_A);
        await page.getByRole("button", { name: "Secili odalari tara" }).click();
        await expect(
          page.getByRole("region", { name: "Adaylar" }).locator("> ul > li"),
        ).toHaveCount(6);
      }
      const clipped = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("body *")]
          .filter((element) => {
            // A few pixels of rounding are not a clipped paragraph.
            const overflows =
              element.scrollHeight - element.clientHeight > 4 ||
              element.scrollWidth - element.clientWidth > 4;
            // A visually hidden label is a 1px box that clips on purpose:
            // its content is *for* the accessibility tree, which is the
            // opposite of the defect this rule looks for.
            if (!overflows || element.clientHeight <= 1 || element.clientWidth <= 1) {
              return false;
            }
            const style = getComputedStyle(element);
            // `visible` on either axis lets the content spill out and stay
            // readable; anything else has to offer a scrollbar.
            const scrollable = (value: string): boolean =>
              value === "auto" || value === "scroll" || value === "visible";
            return !(scrollable(style.overflowY) && scrollable(style.overflowX));
          })
          .map((element) => `${element.tagName.toLowerCase()}.${element.className}`),
      );
      expect(clipped, `content clipped out of reach in ${label}`).toEqual([]);
    }
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

/**
 * The progressive disclosure on "Gorevler", measured where it is real.
 *
 * This is the half a jsdom test cannot make: jsdom does not implement the
 * `details` collapse at all, so a Vitest assertion about visibility there
 * would pass whatever the markup said. What Vitest asserts is that the block
 * is closed and that no sentence was deleted; what a browser can assert - and
 * what these tests assert - is that closed really hides, that the disclosure
 * carries its own name and state into the accessibility tree, and that a
 * keyboard alone can open it again.
 *
 * The rule this guards: **nothing on this screen became unreachable.** The
 * screen stopped putting four blocked evidence cards and several paragraphs
 * between a person and the one control their task's state permits; it did not
 * stop saying any of it.
 */
test.describe("Gorevler: progressive disclosure", () => {
  test("a collapsed block hides its body, keeps it in the document and reopens from the keyboard", async ({
    page,
  }) => {
    await openApp(page);
    await gotoSection(page, "Gorevler");

    const region = page.getByRole("region", { name: "Yurutme durumu" });
    await expect(region).toBeVisible();

    // The summary is the always-readable half: the heading plus one line
    // saying why the rest is folded away. A disclosure whose trigger said
    // only "Ayrintilar" would be a worse screen, not a shorter one.
    const summary = region.locator("summary");
    await expect(summary).toBeVisible();
    expect(((await summary.textContent()) ?? "").trim().length).toBeGreaterThan(40);

    // Closed really means closed here, and the sentence is still in the
    // document rather than removed from it.
    const untested = page.getByTestId("tasks-untested");
    await expect(untested).toHaveCount(1);
    await expect(untested).toBeHidden();

    // One key, from the keyboard, with focus visible on the trigger. Native
    // `details`/`summary` is what makes this true without a line of our own
    // code: the role, the expanded state, the keyboard operation and the
    // announcement all come from the browser.
    await summary.focus();
    await expect(summary).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(untested).toBeVisible();
    await expect(region.locator("details")).toHaveAttribute("open", "");
    // Focus stays where the person put it: a disclosure that moved focus into
    // its own body would strand a keyboard user one Shift+Tab from where they
    // thought they were.
    await expect(summary).toBeFocused();

    // ...and it closes again the same way, so the collapse is a control the
    // person holds rather than a state the screen decides once.
    await page.keyboard.press("Enter");
    await expect(untested).toBeHidden();
  });

  test("every collapsed block on the section carries a name and a reason", async ({ page }) => {
    await openApp(page);
    await gotoSection(page, "Gorevler");

    // Read from the real accessibility surface rather than from a list this
    // test keeps: a block added later is covered by the same rule, and a
    // block that lost its summary text fails here instead of shipping as an
    // unlabelled toggle.
    const blocks = await page.evaluate(() =>
      [...document.querySelectorAll("details")].map((disclosure) => ({
        open: disclosure.open,
        heading: disclosure.querySelector("summary h3, summary h4")?.textContent?.trim() ?? "",
        summary: (disclosure.querySelector("summary")?.textContent ?? "").trim(),
      })),
    );

    expect(blocks.length, "the task surface renders its blocks as disclosures").toBeGreaterThan(3);
    for (const block of blocks) {
      expect(block.heading, "a disclosure without a heading is an unnamed control").not.toBe("");
      expect(
        block.summary.length,
        `"${block.heading}" collapsed without saying why`,
      ).toBeGreaterThan(block.heading.length + 20);
    }
  });
});
