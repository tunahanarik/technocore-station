/**
 * The composer's three approvals, in a real browser.
 *
 * The write path is driven with **mocked backend responses**, and that is a
 * requirement rather than a shortcut. Reaching a genuinely open write gate
 * would mean creating a real identity with a real seed, exporting a real
 * recovery file, and running a live manifest audit against
 * `technocore.chat` - all three of which browser QA is forbidden to do
 * (ADR-0006 2, 3, 4). No real Technocore write happens here, and the send
 * step never leaves this machine: `route.fulfill` answers it locally.
 *
 * What is genuinely under test is the part that lives in the browser: that
 * the send control does not exist before a signature exists, and that editing
 * the content destroys the approvals rather than merely warning about them.
 */

import type { Page } from "@playwright/test";

import { expect, gotoSection, openApp, test } from "../fixtures";

const ROOM = "test-only-room";
const TEXT = "TEST-ONLY tarayici QA metni. Gercek bir gonderim yapilmaz.";
const SEND_TOKEN = "TEST-ONLY-send-token";
const CANONICAL = `test-only-canonical|${ROOM}|${TEXT}`;

/** Requests the composer made, so a test can assert what did *not* happen. */
interface ComposeCalls {
  draft: number;
  sign: number;
  send: number;
  lastSendToken: string | null;
}

/**
 * Open the gate and answer the three write steps locally.
 *
 * The capability read is patched from the real response, so every published
 * limit the panel renders is the backend's own; only `can_compose` and the
 * blocking reasons are substituted.
 */
async function mockComposeBackend(page: Page): Promise<ComposeCalls> {
  const calls: ComposeCalls = { draft: 0, sign: 0, send: 0, lastSendToken: null };

  await page.route(
    (url) => url.pathname === "/api/compose/capability",
    async (route) => {
      const response = await route.fetch();
      const capability = (await response.json()) as Record<string, unknown>;
      await route.fulfill({ json: { ...capability, can_compose: true, blocking_reasons: [] } });
    },
  );

  await page.route(
    (url) => url.pathname === "/api/compose/draft",
    async (route) => {
      calls.draft += 1;
      const body = route.request().postDataJSON() as { room: string; text: string };
      await route.fulfill({
        json: {
          draft_id: `TEST-ONLY-draft-${String(calls.draft)}`,
          room: body.room,
          room_classes: ["test-only"],
          raw_text: body.text,
          swept_text: body.text,
          changed_by_sweep: false,
          raw_chars: body.text.length,
          swept_chars: body.text.length,
          draft_digest: `TEST-ONLY-digest-${String(calls.draft)}`,
          min_chars: 1,
          max_chars: 4096,
          expires_in_seconds: 300,
          target_notes: ["TEST-ONLY: bu oda yalniz tarayici testinde kullanilir."],
        },
      });
    },
  );

  await page.route(
    (url) => url.pathname === "/api/compose/sign",
    async (route) => {
      calls.sign += 1;
      await route.fulfill({
        json: {
          draft_id: `TEST-ONLY-draft-${String(calls.draft)}`,
          room: ROOM,
          did: "did:key:zTESTONLYbrowserqafixturenotarealidentity",
          nonce: "1",
          canonical: CANONICAL,
          canonical_digest: "0".repeat(64),
          signature: "TEST-ONLY-signature",
          changed_by_sweep: false,
          send_token: SEND_TOKEN,
          expires_in_seconds: 120,
        },
      });
    },
  );

  await page.route(
    (url) => url.pathname === "/api/compose/send",
    async (route) => {
      calls.send += 1;
      const body = route.request().postDataJSON() as Record<string, string>;
      calls.lastSendToken = body.send_token ?? null;
      await route.fulfill({
        json: {
          outcome: "accepted",
          room: ROOM,
          did: "did:key:zTESTONLYbrowserqafixturenotarealidentity",
          nonce: "1",
          canonical_digest: "0".repeat(64),
          signature: "TEST-ONLY-signature",
          http_status: 200,
          detail: "TEST-ONLY: yerel olarak yanitlandi, gercek bir yazma yapilmadi.",
          response_excerpt: "TEST-ONLY",
          reconciliation_required: false,
        },
      });
    },
  );

  return calls;
}

async function openComposer(page: Page): Promise<void> {
  await openApp(page);
  await gotoSection(page, "Olustur ve Dogrula");
  await expect(page.getByRole("region", { name: "Gonderim akisi" })).toBeVisible();
}

test.describe("composer, gate closed", () => {
  test("with the real gate there is no text area and no send control", async ({ page }) => {
    await openComposer(page);

    // The shipped state: the write gate is shut, so the form does not exist.
    // A disabled button is not a security control - the absent one is.
    await expect(page.getByText("Gonderim kapali")).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Mesaj metni" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Onayla ve gonder" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Taslagi hazirla" })).toHaveCount(0);
  });
});

test.describe("composer, three approvals", () => {
  test("draft, signature and send are three separate acts in order", async ({ page }) => {
    const calls = await mockComposeBackend(page);
    await openComposer(page);

    // Step 1 exists; steps 2 and 3 do not yet.
    const draftButton = page.getByRole("button", { name: "Taslagi hazirla" });
    await expect(draftButton).toBeDisabled();
    await expect(page.getByRole("region", { name: "Adim 2: Imza onayi" })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Adim 3: Gonderim onayi" })).toHaveCount(0);

    await page.getByRole("textbox", { name: "Hedef oda" }).fill(ROOM);
    await page.getByRole("textbox", { name: "Mesaj metni" }).fill(TEXT);
    await expect(draftButton).toBeEnabled();

    await draftButton.click();
    const signStep = page.getByRole("region", { name: "Adim 2: Imza onayi" });
    await expect(signStep).toBeVisible();
    // Signing is a second act: step 3 still does not exist.
    await expect(page.getByRole("region", { name: "Adim 3: Gonderim onayi" })).toHaveCount(0);
    expect(calls.sign).toBe(0);

    await signStep.getByRole("button", { name: "Imzala" }).click();
    const sendStep = page.getByRole("region", { name: "Adim 3: Gonderim onayi" });
    await expect(sendStep).toBeVisible();
    expect(calls.sign).toBe(1);
    // Nothing was sent by signing.
    expect(calls.send).toBe(0);

    // The bytes on screen are the bytes that were signed (charter 14).
    await expect(sendStep.locator("pre")).toHaveText(CANONICAL);

    await sendStep.getByRole("button", { name: "Onayla ve gonder" }).click();
    await expect(page.getByRole("region", { name: "Gonderim sonucu" })).toBeVisible();

    expect(calls.draft).toBe(1);
    expect(calls.sign).toBe(1);
    expect(calls.send).toBe(1);
    expect(calls.lastSendToken).toBe(SEND_TOKEN);
  });

  test("changing the text drops the signature and the send approval", async ({ page }) => {
    const calls = await mockComposeBackend(page);
    await openComposer(page);

    await page.getByRole("textbox", { name: "Hedef oda" }).fill(ROOM);
    const textbox = page.getByRole("textbox", { name: "Mesaj metni" });
    await textbox.fill(TEXT);
    await page.getByRole("button", { name: "Taslagi hazirla" }).click();
    await page.getByRole("button", { name: "Imzala" }).click();
    await expect(page.getByRole("region", { name: "Adim 3: Gonderim onayi" })).toBeVisible();

    // One keystroke is enough. The send token lives only in component state,
    // so once it is dropped there is nothing left that could publish the old
    // bytes - which is why the control disappears rather than disabling.
    await textbox.press("End");
    await textbox.pressSequentially("!");

    await expect(page.getByText("Onceki onay dusuruldu")).toBeVisible();
    await expect(page.getByRole("region", { name: "Adim 2: Imza onayi" })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Adim 3: Gonderim onayi" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Onayla ve gonder" })).toHaveCount(0);
    expect(calls.send, "nothing may be sent while approvals are being dropped").toBe(0);

    // Getting back to a send needs both acts again, on the new content.
    await page.getByRole("button", { name: "Taslagi hazirla" }).click();
    await expect(page.getByRole("region", { name: "Adim 2: Imza onayi" })).toBeVisible();
    expect(calls.draft).toBe(2);
  });

  test("changing the target room drops the approvals too", async ({ page }) => {
    await mockComposeBackend(page);
    await openComposer(page);

    const room = page.getByRole("textbox", { name: "Hedef oda" });
    await room.fill(ROOM);
    await page.getByRole("textbox", { name: "Mesaj metni" }).fill(TEXT);
    await page.getByRole("button", { name: "Taslagi hazirla" }).click();
    await page.getByRole("button", { name: "Imzala" }).click();
    await expect(page.getByRole("region", { name: "Adim 3: Gonderim onayi" })).toBeVisible();

    await room.press("End");
    await room.pressSequentially("2");

    await expect(page.getByText("Onceki onay dusuruldu")).toBeVisible();
    await expect(page.getByRole("region", { name: "Adim 3: Gonderim onayi" })).toHaveCount(0);
  });

  test("the send approval is single use: the controls are gone afterwards", async ({ page }) => {
    const calls = await mockComposeBackend(page);
    await openComposer(page);

    await page.getByRole("textbox", { name: "Hedef oda" }).fill(ROOM);
    await page.getByRole("textbox", { name: "Mesaj metni" }).fill(TEXT);
    await page.getByRole("button", { name: "Taslagi hazirla" }).click();
    await page.getByRole("button", { name: "Imzala" }).click();
    await page.getByRole("button", { name: "Onayla ve gonder" }).click();

    await expect(page.getByRole("region", { name: "Gonderim sonucu" })).toBeVisible();

    // The nonce is spent whatever the outcome was, so a second click must not
    // be one click away: both the signature step and the send step are gone.
    await expect(page.getByRole("button", { name: "Onayla ve gonder" })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Adim 2: Imza onayi" })).toHaveCount(0);
    expect(calls.send).toBe(1);
  });
});
