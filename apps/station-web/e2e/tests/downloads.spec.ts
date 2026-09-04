/**
 * The blob download path, which jsdom stubbed away.
 *
 * Both exports in this product hand the user a file the same way: fetch the
 * bytes, wrap them in `URL.createObjectURL`, click a synthetic anchor, revoke
 * the URL. `URL.createObjectURL` does not exist in jsdom, so the Vitest suite
 * replaces it - which means the existing tests prove the component *called*
 * something, never that a browser produced a file. Here a real Chromium
 * really downloads one, and the name is read off the download.
 *
 * The evidence export runs against the real backend end to end. The recovery
 * export is driven with mocked responses on purpose: producing a genuine
 * `.tcrec` would mean generating a real seed and a real vault, which browser
 * QA is not allowed to do (ADR-0006 3). What is under test here is the
 * browser half - the `Content-Disposition` round-trip and the download - and
 * that half is real either way.
 */

import { expect, gotoSection, openApp, test } from "../fixtures";

/** A passphrase that exists only inside this test file. Never a real one. */
const TEST_ONLY_PASSPHRASE = "TEST-ONLY-browser-qa-passphrase-0000";

/** A `.tcrec` body that is deliberately not a real recovery envelope. */
const TEST_ONLY_TCREC = '{"TEST-ONLY":"not a recovery file"}';

test.describe("evidence export", () => {
  test("exporting the ledger produces a real download with the expected name", async ({ page }) => {
    await openApp(page);
    await gotoSection(page, "Kanitlar");

    const region = page.getByRole("region", { name: "Disa aktarim" });
    await expect(region).toBeVisible();

    const jsonButton = region.getByRole("button", { name: "JSON olarak disa aktar" });
    // The consent checkbox is the first gate; the button is inert until it
    // is ticked, which is itself worth asserting rather than assuming.
    await expect(jsonButton).toBeDisabled();

    await tickConsent(region);
    await expect(jsonButton).toBeEnabled();

    const downloadPromise = page.waitForEvent("download");
    await jsonButton.click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe("technocore-station-kanit.json");

    const body = await readDownload(download);
    // A real archive, not an error page rendered into a file.
    expect(() => JSON.parse(body) as unknown).not.toThrow();

    // INV-01 at the last possible moment: whatever else the archive carries,
    // it carries no secret material.
    expect(body).not.toMatch(/"(seed|private_key|secret|mnemonic)"/i);

    await expect(region).toContainText("technocore-station-kanit.json");
  });

  test("the markdown export is a separate, separately named file", async ({ page }) => {
    await openApp(page);
    await gotoSection(page, "Kanitlar");

    const region = page.getByRole("region", { name: "Disa aktarim" });
    await tickConsent(region);

    const downloadPromise = page.waitForEvent("download");
    await region.getByRole("button", { name: "Markdown olarak disa aktar" }).click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe("technocore-station-kanit.md");
    expect(await readDownload(download)).not.toMatch(/"(seed|private_key|secret|mnemonic)"/i);
  });
});

test.describe("recovery export", () => {
  test("the download name comes from the server's Content-Disposition", async ({ page }) => {
    const serverFilename = "technocore-station-TESTONLY-20260904.tcrec";

    // The identity read is patched from the *real* response, so every field
    // this surface uses keeps the shape the backend actually publishes; only
    // the state and the identity block are substituted.
    await page.route(
      (url) => url.pathname === "/api/identity",
      async (route) => {
        const response = await route.fetch();
        const status = (await response.json()) as Record<string, unknown>;
        await route.fulfill({
          json: {
            ...status,
            state: "recovery_pending",
            identity: {
              did: "did:key:zTESTONLYbrowserqafixturenotarealidentity",
              public_key: "TEST-ONLY",
              fingerprint: "TEST-ONLY-fingerprint",
              fingerprint_short: "TEST-ONLY",
              label: "TEST-ONLY",
              status: "recovery_pending",
              protection: "dpapi",
              created_at: "2026-09-04T00:00:00Z",
              revoked_at: null,
            },
          },
        });
      },
    );

    await page.route(
      (url) => url.pathname === "/api/identity/recovery/export",
      async (route) => {
        await route.fulfill({
          status: 200,
          headers: {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": `attachment; filename="${serverFilename}"`,
            "Cache-Control": "no-store",
          },
          body: TEST_ONLY_TCREC,
        });
      },
    );

    await openApp(page);
    await gotoSection(page, "Kimlik ve Guvenlik");

    await page.getByRole("button", { name: "Recovery dosyasi olustur" }).click();
    const dialog = page.getByRole("dialog", { name: "Recovery dosyasi olustur" });
    await expect(dialog).toBeVisible();

    await dialog.getByLabel("Recovery parolasi", { exact: true }).fill(TEST_ONLY_PASSPHRASE);
    await dialog.getByLabel("Recovery parolasi (tekrar)").fill(TEST_ONLY_PASSPHRASE);

    const submit = dialog.getByRole("button", { name: "Recovery dosyasini indir" });
    await expect(submit).toBeEnabled();

    const downloadPromise = page.waitForEvent("download");
    await submit.click();
    const download = await downloadPromise;

    // The whole point: the browser received a file, and its name is the one
    // the server put in `Content-Disposition` - a header jsdom never sees
    // because the Vitest suite never performs a download.
    expect(download.suggestedFilename()).toBe(serverFilename);
    expect(await readDownload(download)).toBe(TEST_ONLY_TCREC);

    await expect(dialog).toContainText("Dosya indirildi");
  });

  test("the export control stays disabled until the two passphrases agree", async ({ page }) => {
    await page.route(
      (url) => url.pathname === "/api/identity",
      async (route) => {
        const response = await route.fetch();
        const status = (await response.json()) as Record<string, unknown>;
        await route.fulfill({ json: { ...status, state: "recovery_pending" } });
      },
    );

    await openApp(page);
    await gotoSection(page, "Kimlik ve Guvenlik");
    await page.getByRole("button", { name: "Recovery dosyasi olustur" }).click();

    const dialog = page.getByRole("dialog", { name: "Recovery dosyasi olustur" });
    const submit = dialog.getByRole("button", { name: "Recovery dosyasini indir" });
    await expect(submit).toBeDisabled();

    await dialog.getByLabel("Recovery parolasi", { exact: true }).fill(TEST_ONLY_PASSPHRASE);
    await expect(submit, "a mismatched confirmation must not be exportable").toBeDisabled();

    await dialog.getByLabel("Recovery parolasi (tekrar)").fill(TEST_ONLY_PASSPHRASE);
    await expect(submit).toBeEnabled();

    // Nothing was downloaded and nothing was created: the dialog is dismissed.
    await dialog.getByRole("button", { name: "Vazgec" }).click();
    await expect(dialog).toBeHidden();
  });
});

/**
 * Tick the export consent box the way a keyboard user does.
 *
 * The HeroUI checkbox keeps its real `<input>` in a visually hidden span
 * behind a styled control, so a pointer click lands on the decoration. Space
 * on the focused input is both the reliable path and the one a keyboard user
 * actually takes - which makes this assertion say something extra: the
 * consent gate is reachable without a mouse.
 */
async function tickConsent(region: import("@playwright/test").Locator): Promise<void> {
  const box = region.getByRole("checkbox");
  await expect(box).not.toBeChecked();
  await box.focus();
  await expect(box).toBeFocused();
  await box.press("Space");
  await expect(box).toBeChecked();
}

async function readDownload(download: import("@playwright/test").Download): Promise<string> {
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk as Buffer));
  return Buffer.concat(chunks).toString("utf8");
}
