/**
 * The OpenCode connection surface: the provider key, and the model table.
 *
 * The key is stored against the **real** backend, which writes a real DPAPI
 * envelope - into the throwaway data directory this run created, never the
 * user's. The value typed is a TEST-ONLY string that is not a credential for
 * anything (ADR-0006 3), no metered call is made, and no request leaves the
 * machine: storing a key contacts nobody, and "Modelleri yenile" - the one
 * control that would reach `opencode.ai` - is never pressed here.
 *
 * The catalog half is driven from a patched status document instead, because
 * populating it for real would mean fetching the provider's live catalog.
 * What is being proven there is a rendering rule - an unmapped model must not
 * be selectable - and that rule lives entirely in the browser.
 */

import type { Page } from "@playwright/test";

import { expect, gotoSection, openApp, test } from "../fixtures";

/**
 * A string that is not an API key for anything, long enough to satisfy the
 * backend's twenty-character minimum, and distinctive enough that finding it
 * anywhere in the page is unambiguous.
 */
const TEST_ONLY_KEY = "TEST-ONLY-NOT-A-REAL-KEY-e2e-canary-8f3a1c";

/** A model the closed protocol table maps, so it can be chosen. */
const MAPPED_MODEL = "glm-5.3";

/** A model the table does not map. Named so it cannot be read as a real one. */
const UNMAPPED_MODEL = "TEST-ONLY-unmapped-model";

async function openConnection(page: Page): Promise<void> {
  await openApp(page);
  await gotoSection(page, "Ayarlar ve Yardim");
  await expect(page.getByRole("region", { name: "Saglayici anahtari" })).toBeVisible();
}

test.describe("provider key", () => {
  test("the key field is a masked password input", async ({ page }) => {
    await openConnection(page);

    const field = page.getByLabel("OpenCode Go API anahtari");
    await expect(field).toBeVisible();
    // Not "styled to look masked": the control's own type, which is what
    // keeps the value out of the accessibility tree and out of autofill.
    await expect(field).toHaveAttribute("type", "password");
  });

  test("a saved key is nowhere in the DOM afterwards", async ({ page }) => {
    await openConnection(page);

    await page.getByLabel("OpenCode Go API anahtari").fill(TEST_ONLY_KEY);
    await page.getByRole("button", { name: "Anahtari kaydet" }).click();

    // The surface flips to "configured": a fingerprint, and no field.
    await expect(page.getByText("Kayitli anahtar")).toBeVisible();
    await expect(page.getByRole("button", { name: "Anahtari degistir" })).toBeVisible();
    await expect(page.getByLabel("OpenCode Go API anahtari")).toHaveCount(0);

    // The claim, measured. Not "the input was cleared" - the whole rendered
    // document, attribute values and input values included, is searched.
    const traces = await page.evaluate((needle) => {
      const inputValues = [...document.querySelectorAll("input")].map((input) => input.value);
      return {
        inHtml: document.documentElement.outerHTML.includes(needle),
        inText: (document.body.innerText || "").includes(needle),
        inInputs: inputValues.some((value) => value.includes(needle)),
      };
    }, TEST_ONLY_KEY);

    expect(traces.inHtml, "the key must not survive anywhere in the markup").toBe(false);
    expect(traces.inText, "the key must not survive in the rendered text").toBe(false);
    expect(traces.inInputs, "the key must not survive in an input's value").toBe(false);

    // Reloading does not bring it back either: there is no read route.
    await page.reload({ waitUntil: "domcontentloaded" });
    await gotoSection(page, "Ayarlar ve Yardim");
    await expect(page.getByText("Kayitli anahtar")).toBeVisible();
    expect(await page.content()).not.toContain(TEST_ONLY_KEY);

    // Storing a key must not have produced a verified-looking badge: the
    // honest verdict is "saved, unverified".
    await expect(page.getByRole("region", { name: "Baglanti denetimi" })).toContainText(
      /dogrulanmadi|Kaydedildi/i,
    );

    // Put the shared backend back the way this test found it.
    await page.getByRole("button", { name: "Baglantiyi kaldir" }).click();
    await expect(page.getByRole("button", { name: "Anahtari kaydet" })).toBeVisible();
  });

  test("there is no control that reads a stored key back", async ({ page }) => {
    await openConnection(page);

    const panel = page.getByRole("region", { name: "Saglayici anahtari" });
    // The absence is the design (ADR-0005): one way in, no way out.
    await expect(panel.getByRole("button", { name: /goster|kopyala/i })).toHaveCount(0);
  });
});

test.describe("model catalog", () => {
  test("a model the protocol table does not map is not selectable", async ({ page }) => {
    await page.route(
      (url) => url.pathname === "/api/opencode/status",
      async (route) => {
        const response = await route.fetch();
        const status = (await response.json()) as Record<string, unknown>;
        const catalog = status.catalog as Record<string, unknown>;
        await route.fulfill({
          json: {
            ...status,
            catalog: {
              ...catalog,
              state: "ok",
              fetched_at: "2026-09-04T00:00:00Z",
              models_fetched_at: "2026-09-04T00:00:00Z",
              http_status: 200,
              model_count: 2,
              selectable_count: 1,
              models: [
                {
                  model_id: MAPPED_MODEL,
                  owned_by: "TEST-ONLY",
                  selectable: true,
                  protocol: "chat/completions",
                  protocol_verification: "documented",
                  reason: "",
                  retention: "0 gun",
                  training_use: "no",
                  requires_training_acknowledgement: false,
                  privacy_source: "TEST-ONLY",
                  privacy_read_on: "2026-09-04",
                },
                {
                  model_id: UNMAPPED_MODEL,
                  owned_by: "TEST-ONLY",
                  selectable: false,
                  protocol: "",
                  protocol_verification: "unverified",
                  reason: "Protokol eslemesi yok: adres tablosunda listelenmiyor.",
                  retention: "bilinmiyor",
                  training_use: "unknown",
                  requires_training_acknowledgement: false,
                  privacy_source: "TEST-ONLY",
                  privacy_read_on: "2026-09-04",
                },
              ],
            },
          },
        });
      },
    );

    await openApp(page);
    await gotoSection(page, "Ayarlar ve Yardim");

    const catalog = page.getByRole("region", { name: "Model katalogu" });
    await expect(catalog).toBeVisible();

    const mapped = catalog.getByRole("radio", { name: new RegExp(MAPPED_MODEL) });
    const unmapped = catalog.getByRole("radio", { name: new RegExp(UNMAPPED_MODEL) });

    await expect(mapped).toBeEnabled();
    // The rule: no fallback, no nearest match, no silent rewrite. A model the
    // closed table cannot address is not offered at all.
    await expect(unmapped).toBeDisabled();

    // And the reason is on screen, not swallowed.
    await expect(catalog).toContainText("Secilemez: Protokol eslemesi yok");
    await expect(catalog).toContainText("2 listelendi · 1 secilebilir");
  });

  test("an empty catalog says so instead of inventing rows", async ({ page }) => {
    await openConnection(page);

    const catalog = page.getByRole("region", { name: "Model katalogu" });
    // The real state on a fresh install: nothing has been fetched, and the
    // panel says exactly that rather than showing a plausible model list.
    await expect(catalog).toContainText("Henuz model listelenmedi");
    await expect(catalog.getByRole("radio")).toHaveCount(0);
  });
});
