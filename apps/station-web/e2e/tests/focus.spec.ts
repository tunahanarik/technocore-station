/**
 * Real focus management in the identity dialogs.
 *
 * A focus trap is the one accessibility property that cannot be asserted
 * without a browser: it is defined entirely by where the browser sends focus
 * when Tab is pressed at the end of a subtree, and jsdom never moves focus on
 * Tab at all. The same goes for focus restoration - "the trigger got focus
 * back" is a statement about the browser's focus, not about a React state.
 *
 * No dialog here is submitted. These tests open, traverse and dismiss; no
 * identity is created, no seed is generated, no vault is written
 * (ADR-0006 3).
 */

import type { Locator, Page } from "@playwright/test";

import { expect, gotoSection, openApp, test } from "../fixtures";

/** The identity section's create-identity dialog, and the button that opens it. */
async function openIdentity(page: Page): Promise<{ trigger: Locator; dialog: Locator }> {
  await openApp(page);
  await gotoSection(page, "Kimlik ve Guvenlik");

  const trigger = page.getByRole("button", { name: "Yeni kimlik olustur" });
  await expect(trigger).toBeVisible();
  await trigger.click();

  const dialog = page.getByRole("dialog", { name: "Yeni kimlik olustur" });
  await expect(dialog).toBeVisible();
  return { trigger, dialog };
}

/** Whether focus is currently inside the given element. */
async function focusInside(dialog: Locator): Promise<boolean> {
  return dialog.evaluate((element) => element.contains(document.activeElement));
}

test.describe("dialog focus management", () => {
  test("opening a dialog moves focus into it", async ({ page }) => {
    const { dialog } = await openIdentity(page);
    expect(await focusInside(dialog)).toBe(true);
  });

  test("Tab is trapped inside the dialog", async ({ page }) => {
    const { dialog } = await openIdentity(page);

    // Enough presses to walk past every control in the dialog several times
    // over. If the trap leaked, focus would land on the page behind it and
    // this would fail on whichever press escaped.
    for (let press = 0; press < 30; press += 1) {
      await page.keyboard.press("Tab");
      expect(await focusInside(dialog), `focus escaped on Tab #${String(press + 1)}`).toBe(
        true,
      );
    }

    // Backwards too: a trap that only holds in one direction is not a trap.
    for (let press = 0; press < 30; press += 1) {
      await page.keyboard.press("Shift+Tab");
      expect(
        await focusInside(dialog),
        `focus escaped on Shift+Tab #${String(press + 1)}`,
      ).toBe(true);
    }
  });

  test("Escape closes the dialog and returns focus to the trigger", async ({ page }) => {
    const { trigger, dialog } = await openIdentity(page);

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    // The point of the whole exercise: a keyboard user is put back where they
    // were, not at the top of the document.
    await expect(trigger).toBeFocused();
  });

  test("the cancel control closes the dialog and returns focus too", async ({ page }) => {
    const { trigger, dialog } = await openIdentity(page);

    await dialog.getByRole("button", { name: "Vazgec" }).click();
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("the content behind the dialog is inert while it is open", async ({ page }) => {
    const { dialog } = await openIdentity(page);
    const root = page.locator("#root");

    // React Aria marks the whole application subtree `inert` for the lifetime
    // of the modal. That is the real mechanism, and it is stronger than an
    // `aria-modal` attribute: `inert` removes the content from the
    // accessibility tree, from hit testing and from the tab order at once.
    await expect(dialog).toBeVisible();
    await expect(root).toHaveAttribute("inert", "");

    // ...and hands it back on close, rather than leaving the app unusable.
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(root).not.toHaveAttribute("inert", "");
  });

  test("passphrase fields inside the dialog are masked", async ({ page }) => {
    const { dialog } = await openIdentity(page);

    // Every password control in the dialog really is `type=password`: a
    // "masked by CSS" field would hand the value to the accessibility tree
    // and to autofill.
    const masked = dialog.locator('input[type="password"]');
    await expect(masked.first()).toBeVisible();

    const plainSecrets = await dialog.locator('input[type="text"][autocomplete*="password"]').count();
    expect(plainSecrets, "a passphrase field must never be a plain text input").toBe(0);
  });

  test("no seed, private key or mnemonic field exists on the identity surface", async ({
    page,
  }) => {
    await openApp(page);
    await gotoSection(page, "Kimlik ve Guvenlik");

    // INV-01 at the surface: there is no control through which a secret could
    // be shown or re-entered.
    const body = (await page.getByRole("main").textContent()) ?? "";
    expect(body.toLowerCase()).not.toContain("mnemonic");
    expect(body).not.toMatch(/\bseed\b/i);
    expect(body).not.toMatch(/private[ _-]?key/i);
  });
});

/**
 * Focus around the task screen's disclosures.
 *
 * The same property the dialog tests measure, in the place progressive
 * disclosure is most likely to break it: where the browser puts focus when
 * content appears and disappears under it. jsdom moves focus for nothing, so
 * this is only checkable here.
 */
test.describe("disclosure focus management", () => {
  test("opening and closing a block leaves focus on the control that did it", async ({
    page,
  }) => {
    await openApp(page);
    await gotoSection(page, "Gorevler");

    const summary = page.getByRole("region", { name: "Guven siniri" }).locator("summary");
    await summary.focus();
    await expect(summary).toBeFocused();

    await page.keyboard.press("Enter");
    await expect(page.getByTestId("tasks-trust-boundary")).toBeVisible();
    await expect(summary, "opening a block must not throw focus away").toBeFocused();

    await page.keyboard.press("Enter");
    await expect(page.getByTestId("tasks-trust-boundary")).toBeHidden();
    // The one that actually strands people: content collapsing under the
    // focused element and taking focus to `body` with it.
    await expect(summary, "closing a block must not drop focus to the document").toBeFocused();
  });

  test("a folded block puts nothing focusable in the tab order", async ({ page }) => {
    await openApp(page);
    await gotoSection(page, "Gorevler");

    // A collapsed disclosure removes its body from the tab order for free;
    // this is the assertion that would catch a hand-rolled replacement that
    // only hid the body visually and left every control inside it tabbable -
    // which is the version of this change that reads fine and is unusable.
    const reachable = await page.evaluate(() =>
      [...document.querySelectorAll("details:not([open])")].reduce(
        (total, disclosure) =>
          total +
          [...disclosure.querySelectorAll("button, input, textarea, select, a[href]")].filter(
            (control) => (control as HTMLElement).offsetParent !== null,
          ).length,
        0,
      ),
    );
    expect(reachable, "a folded block may not leave focusable controls on screen").toBe(0);
  });
});
