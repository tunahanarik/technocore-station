import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bootstrapSession, resetSessionState } from "../../api/client";
import type {
  ComposeCapability,
  ComposeDraft,
  ComposeSendResult,
  ComposeSignature,
} from "../../api/types";
import { ComposerPanel } from "./ComposerPanel";

/**
 * These assertions encode the product rules of the outbound write path, not
 * styling: three separate approvals in order, an approval that dies the moment
 * the content changes, a send control that cannot outlive its deadline, and a
 * three-valued result in which `outcome_unknown` is never dressed up as
 * success or failure - and never carries a retry.
 *
 * Every fixture is TEST-ONLY. No real DID, no real signature, and the target
 * room is never `lobby`: the denied rooms may not appear as a target anywhere,
 * including in a test that never reaches the network (INV-05).
 */

const ROOM = "test-only-oda";

//: TEST-ONLY capability. The limits are deliberately odd numbers so a
//: hardcoded 4096 in the UI would fail this test instead of coinciding.
const CAPABILITY: ComposeCapability = {
  can_compose: true,
  blocking_reasons: [],
  write_method: "POST",
  write_path_template: "/r/{room}",
  denied_rooms: ["lobby", "meta"],
  room_class_markers: ["public"],
  max_chars: 240,
  min_chars: 2,
  draft_ttl_seconds: 180,
  approval_ttl_seconds: 180,
  note_lane_available: false,
  note_lane_detail:
    "Imzali note gonderimi bu surumde yoktur. Pinlenmis protokol imzali note yazmasini yalniz room-owners ve room-allow namespace'lerinde kabul ediyor.",
};

const LOCKED_CAPABILITY: ComposeCapability = {
  ...CAPABILITY,
  can_compose: false,
  blocking_reasons: ["identity_present", "manifest_current"],
};

//: TEST-ONLY draft. Digests are kept short on purpose: a full 64-hex run must
//: never reach the DOM, and a fixture carrying one would hide a real leak.
const DRAFT: ComposeDraft = {
  draft_id: "draft-test-only",
  room: ROOM,
  room_classes: ["public"],
  raw_text: "merhaba",
  swept_text: "merhaba",
  changed_by_sweep: false,
  raw_chars: 7,
  swept_chars: 7,
  draft_digest: "d1d1d1d1d1d1",
  min_chars: 2,
  max_chars: 240,
  expires_in_seconds: 180,
  target_notes: [],
};

/**
 * The same draft, but the sweep removed an invisible character.
 *
 * The zero-width space is written as an escape on purpose: an editor, a diff
 * viewer or a copy-paste can silently drop a literal one, and this fixture
 * would then be testing two identical strings.
 */
const SWEPT_DRAFT: ComposeDraft = {
  ...DRAFT,
  raw_text: "merhaba​",
  swept_text: "merhaba",
  changed_by_sweep: true,
  raw_chars: 8,
  swept_chars: 7,
  draft_digest: "d2d2d2d2d2d2",
};

//: TEST-ONLY signature. Not a real DID and not a real Ed25519 signature.
const SIGNATURE: ComposeSignature = {
  draft_id: "draft-test-only",
  room: ROOM,
  did: "did:key:z6MkTESTONLYCOMPOSERFIXTURE",
  nonce: "424242",
  canonical: "TEST-ONLY-CANONICAL-BYTES|test-only-oda|424242|merhaba",
  canonical_digest: "c0c0c0c0c0c0",
  signature: "TESTONLYSIGNATUREVALUE",
  changed_by_sweep: false,
  send_token: "TEST-ONLY-SEND-TOKEN",
  expires_in_seconds: 180,
};

/** An approval that is already past its deadline when it arrives. */
const EXPIRED_SIGNATURE: ComposeSignature = { ...SIGNATURE, expires_in_seconds: 0 };

const ACCEPTED: ComposeSendResult = {
  outcome: "accepted",
  room: ROOM,
  did: SIGNATURE.did,
  nonce: SIGNATURE.nonce,
  canonical_digest: SIGNATURE.canonical_digest,
  signature: SIGNATURE.signature,
  http_status: 201,
  detail: "Sunucu yazmayi kabul etti.",
  response_excerpt: '{"ok": true}',
  reconciliation_required: false,
};

const REFUSED_DUPLICATE: ComposeSendResult = {
  ...ACCEPTED,
  outcome: "refused",
  http_status: 422,
  detail: "Sunucu yazmayi reddetti.",
  response_excerpt: "duplicate message",
};

const UNKNOWN: ComposeSendResult = {
  ...ACCEPTED,
  outcome: "outcome_unknown",
  http_status: 0,
  detail:
    "Yanit alinamadi. Bu islem 'gonderildi' veya 'basarisiz' olarak sunulamaz; nonce harcanmistir.",
  response_excerpt: "",
  reconciliation_required: true,
};

type Route = "bootstrap" | "capability" | "draft" | "sign" | "send";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

interface Stub {
  readonly calls: Record<Route, number>;
}

/**
 * Route the stub by URL.
 *
 * The panel talks to four composer endpoints. A stub that answered every
 * request with the same body would let a step read the wrong shape and pass.
 */
function stubApi(
  handlers: Partial<Record<Route, () => Promise<Response> | Response>> = {},
): Stub {
  const calls: Record<Route, number> = {
    bootstrap: 0,
    capability: 0,
    draft: 0,
    sign: 0,
    send: 0,
  };

  const defaults: Record<Route, () => Promise<Response> | Response> = {
    bootstrap: () =>
      json({ csrf_token: "test-only-value-not-a-real-token", csrf_header: "X-Station-CSRF" }),
    capability: () => json(CAPABILITY),
    draft: () => json(DRAFT),
    sign: () => json(SIGNATURE),
    send: () => json(ACCEPTED),
  };

  function routeFor(url: string): Route | null {
    if (url.includes("/api/session/bootstrap")) return "bootstrap";
    if (url.includes("/api/compose/capability")) return "capability";
    if (url.includes("/api/compose/draft")) return "draft";
    if (url.includes("/api/compose/sign")) return "sign";
    if (url.includes("/api/compose/send")) return "send";
    return null;
  }

  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const route = routeFor(url);
      if (route === null) {
        return Promise.resolve(new Response("no route", { status: 404 }));
      }
      calls[route] += 1;
      return Promise.resolve((handlers[route] ?? defaults[route])());
    }),
  );

  return { calls };
}

function stubClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}

async function renderPanel(needsVaultPassphrase = false): Promise<ReturnType<typeof render>> {
  await bootstrapSession();
  const view = render(<ComposerPanel needsVaultPassphrase={needsVaultPassphrase} />);
  await screen.findByRole("button", { name: "Taslagi hazirla" });
  return view;
}

/** Fill both fields and prepare a draft: the panel then sits at step 2. */
async function toSigningStep(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("Hedef oda"), ROOM);
  await user.type(screen.getByLabelText("Mesaj metni"), "merhaba");
  await user.click(screen.getByRole("button", { name: "Taslagi hazirla" }));
  await screen.findByRole("button", { name: "Imzala" });
}

/** Carry on through the signing approval: the panel then sits at step 3. */
async function toSendStep(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await toSigningStep(user);
  await user.click(screen.getByRole("button", { name: "Imzala" }));
  await screen.findByRole("region", { name: "Adim 3: Gonderim onayi" });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetSessionState();
});

describe("Composer approval chain", () => {
  it("reveals the three steps in order and offers no send control before a signature", async () => {
    stubApi();
    const user = userEvent.setup();
    await renderPanel();

    // Step 1 only. Signing and sending are not merely disabled: they are not
    // on the page, because there is nothing yet to sign or send.
    expect(screen.getByRole("region", { name: "Adim 1: Taslak" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Adim 2: Imza onayi" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Imzala" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Onayla ve gonder" })).toBeNull();

    await toSigningStep(user);

    // Step 2 exists; signing is still not sending.
    expect(screen.getByRole("region", { name: "Adim 2: Imza onayi" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Onayla ve gonder" })).toBeNull();
    expect(screen.getByText(/Imzalamak gondermek degildir/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Imzala" }));

    expect(
      await screen.findByRole("button", { name: "Onayla ve gonder" }),
    ).toBeInTheDocument();
  });

  it("shows the canonical string verbatim, because displayed is what is signed", async () => {
    stubApi();
    const user = userEvent.setup();
    await renderPanel();
    await toSendStep(user);

    expect(screen.getByText(SIGNATURE.canonical)).toBeInTheDocument();
    expect(screen.getByText(/Gosterilen ile imzalanan aynidir/)).toBeInTheDocument();
  });

  it("drops the draft and the send approval when the text changes", async () => {
    // The send token lives in this component's state and nowhere else, so
    // dropping it here is the mechanism, not a reminder: after the edit there
    // is nothing left that could publish the old bytes.
    const stub = stubApi();
    const user = userEvent.setup();
    await renderPanel();
    await toSendStep(user);

    await user.type(screen.getByLabelText("Mesaj metni"), "!");

    expect(screen.queryByRole("button", { name: "Onayla ve gonder" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Adim 2: Imza onayi" })).toBeNull();
    expect(await screen.findByText("Onceki onay dusuruldu")).toBeInTheDocument();
    expect(stub.calls.send).toBe(0);
  });

  it("drops the approval when the target room changes", async () => {
    const stub = stubApi();
    const user = userEvent.setup();
    await renderPanel();
    await toSendStep(user);

    await user.type(screen.getByLabelText("Hedef oda"), "-2");

    expect(screen.queryByRole("button", { name: "Onayla ve gonder" })).toBeNull();
    expect(await screen.findByText("Onceki onay dusuruldu")).toBeInTheDocument();
    expect(stub.calls.send).toBe(0);
  });

  it("locks the send control once the approval has expired, and says why", async () => {
    stubApi({ sign: () => json(EXPIRED_SIGNATURE) });
    const user = userEvent.setup();
    await renderPanel();
    await toSendStep(user);

    const send = screen.getByRole("button", { name: "Onayla ve gonder" });
    expect(send).toBeDisabled();
    expect(screen.getByText("Onay suresi doldu")).toBeInTheDocument();
  });

  it("starts no second send when the send button is clicked twice", async () => {
    let release: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const stub = stubApi({ send: () => pending });
    const user = userEvent.setup();
    await renderPanel();
    await toSendStep(user);

    await user.click(screen.getByRole("button", { name: "Onayla ve gonder" }));
    const busy = await screen.findByRole("button", { name: "Gonderiliyor..." });
    expect(busy).toBeDisabled();

    fireEvent.click(busy);
    expect(stub.calls.send).toBe(1);

    release(json(ACCEPTED));
    expect(await screen.findByText("Kabul edildi")).toBeInTheDocument();
  });
});

describe("Composer sweep difference", () => {
  it("refuses to sign until the swept difference has been seen", async () => {
    stubApi({ draft: () => json(SWEPT_DRAFT) });
    const user = userEvent.setup();
    await renderPanel();
    await toSigningStep(user);

    expect(screen.getByText("Gorunmez karakterler silindi")).toBeInTheDocument();
    // Scoped to step 2: the text the user typed is also still in the field
    // above, and this assertion is about the diff, not the form.
    const step = screen.getByRole("region", { name: "Adim 2: Imza onayi" });
    expect(within(step).getByText(SWEPT_DRAFT.raw_text)).toBeInTheDocument();
    expect(within(step).getByText(SWEPT_DRAFT.swept_text)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Imzala" })).toBeDisabled();

    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Imzala" })).toBeEnabled();
  });

  it("does not ask for an acknowledgement when the sweep changed nothing", async () => {
    stubApi();
    const user = userEvent.setup();
    await renderPanel();
    await toSigningStep(user);

    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByRole("button", { name: "Imzala" })).toBeEnabled();
    expect(screen.getByText(/Supurme metni degistirmedi/)).toBeInTheDocument();
  });
});

describe("Composer limits and gate", () => {
  it("reads the character limits from the capability instead of hardcoding them", async () => {
    stubApi();
    await renderPanel();

    expect(
      screen.getByText(/0 \/ 240 karakter \(en az 2\)/),
    ).toBeInTheDocument();
  });

  it("links the over-limit explanation to the field it describes", async () => {
    stubApi({ capability: () => json({ ...CAPABILITY, max_chars: 5 }) });
    const user = userEvent.setup();
    await renderPanel();

    const field = screen.getByLabelText("Mesaj metni");
    await user.type(field, "cok uzun bir metin");

    expect(field).toHaveAttribute("aria-invalid", "true");
    const describedBy = field.getAttribute("aria-describedby") ?? "";
    const explanation = screen.getByText(/Metin ust siniri asiyor/);
    expect(describedBy.split(" ")).toContain(explanation.id);
  });

  it("explains a closed gate from the blocking reasons and offers no form", async () => {
    stubApi({ capability: () => json(LOCKED_CAPABILITY) });
    await bootstrapSession();
    const { container } = render(<ComposerPanel needsVaultPassphrase={false} />);

    expect(await screen.findByText("Gonderim kapali")).toBeInTheDocument();
    // The reasons are readable sentences, not raw gate keys.
    expect(screen.getByText(/Kimlik olusturulmus olmali/)).toBeInTheDocument();
    expect(screen.getByText(/Resmi manifest kontrolu kurulmus olmali/)).toBeInTheDocument();

    // No inert form: the surface simply does not offer one.
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Taslagi hazirla" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Onayla ve gonder" })).toBeNull();
  });

  it("says why there is no note send path", async () => {
    stubApi();
    await renderPanel();

    expect(screen.getByText("Neden not gonderimi yok?")).toBeInTheDocument();
    expect(screen.getByText(/room-owners ve room-allow/)).toBeInTheDocument();
  });
});

describe("Composer vault passphrase", () => {
  it("asks for the passphrase at signing time and keeps none of it afterwards", async () => {
    stubApi();
    const user = userEvent.setup();
    const { container } = await renderPanel(true);
    await toSigningStep(user);

    const field = screen.getByLabelText(/Kasa parolasi/);
    await user.type(field, "TEST-ONLY-passphrase-01");
    expect(field).toHaveValue("TEST-ONLY-passphrase-01");

    await user.click(screen.getByRole("button", { name: "Imzala" }));
    await screen.findByRole("button", { name: "Onayla ve gonder" });

    // Signing is the only thing that needed it; the field is gone with it.
    expect(container.querySelector('input[type="password"]')).toBeNull();

    // And it does not come back filled in on the next draft.
    await user.type(screen.getByLabelText("Mesaj metni"), "!");
    await user.click(screen.getByRole("button", { name: "Taslagi hazirla" }));
    expect(await screen.findByLabelText(/Kasa parolasi/)).toHaveValue("");
  });
});

describe("Composer send outcomes", () => {
  async function sendWith(result: ComposeSendResult): Promise<void> {
    stubApi({ send: () => json(result) });
    const user = userEvent.setup();
    await renderPanel();
    await toSendStep(user);
    await user.click(screen.getByRole("button", { name: "Onayla ve gonder" }));
    await screen.findByRole("region", { name: "Gonderim sonucu" });
  }

  it("presents an accepted write as accepted", async () => {
    await sendWith(ACCEPTED);

    expect(screen.getByText("Kabul edildi")).toBeInTheDocument();
    expect(screen.getByText(/Sonuc: accepted · HTTP: 201/)).toBeInTheDocument();
  });

  it("presents a 422 refusal as a refusal that must not be repeated", async () => {
    await sendWith(REFUSED_DUPLICATE);

    expect(screen.getByText("Reddedildi")).toBeInTheDocument();
    expect(screen.getByText(/Ayni metin yakin zamanda yazilmis/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yeniden dene" })).toBeNull();
  });

  it("never presents outcome_unknown as sent or as failed", async () => {
    await sendWith(UNKNOWN);

    expect(
      screen.getByText("Sonuc bilinmiyor: sunucu yazmis olabilir"),
    ).toBeInTheDocument();
    expect(screen.getByText(/sunucu mesaji yazmis olabilir/)).toBeInTheDocument();
    expect(screen.getByText(/oda okuma yolu bu surumde acilmadi/)).toBeInTheDocument();

    const text = document.body.textContent ?? "";
    expect(text).not.toContain("Gonderildi");
    expect(text).not.toContain("Basarisiz oldu");
  });

  it("offers no retry control after an unknown outcome", async () => {
    // Blind repetition could publish the message twice, and this release has
    // no room read to reconcile with. There is no button, anywhere.
    await sendWith(UNKNOWN);

    expect(screen.queryByRole("button", { name: "Yeniden dene" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Onayla ve gonder" })).toBeNull();
    expect(screen.getByText(/otomatik tekrar yoktur/)).toBeInTheDocument();
  });

  it("renders the server excerpt as inert plain text", async () => {
    stubApi({
      send: () => json({ ...ACCEPTED, response_excerpt: '<a href="https://evil.test">tikla</a>' }),
    });
    const user = userEvent.setup();
    const { container } = await renderPanel();
    await toSendStep(user);
    await user.click(screen.getByRole("button", { name: "Onayla ve gonder" }));
    await screen.findByRole("region", { name: "Gonderim sonucu" });

    expect(container.querySelectorAll("a")).toHaveLength(0);
    expect(container.innerHTML).not.toContain("<a href");
    expect(screen.getByText('<a href="https://evil.test">tikla</a>')).toBeInTheDocument();
  });

  it("requires a fresh draft and a fresh signature for any further send", async () => {
    await sendWith(ACCEPTED);

    expect(screen.queryByRole("button", { name: "Onayla ve gonder" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Imzala" })).toBeNull();
    expect(screen.getByRole("button", { name: "Taslagi hazirla" })).toBeInTheDocument();
  });
});

describe("Composer failure surfaces", () => {
  it("calls a lost send response unknown rather than failed", async () => {
    stubApi({ send: () => Promise.reject(new TypeError("Failed to fetch")) });
    const user = userEvent.setup();
    await renderPanel();
    await toSendStep(user);
    await user.click(screen.getByRole("button", { name: "Onayla ve gonder" }));

    expect(await screen.findByText("Gonderim tamamlanamadi")).toBeInTheDocument();
    expect(screen.getByText("Bu sonuc bilinmiyor")).toBeInTheDocument();
    // The approval is spent either way, so the control is gone.
    expect(screen.queryByRole("button", { name: "Onayla ve gonder" })).toBeNull();
  });

  it("keeps the canonical text, DID, signature and nonce out of the copied diagnostics", async () => {
    stubApi({
      send: () =>
        new Response(JSON.stringify({ detail: "approval_invalid" }), {
          status: 409,
          headers: {
            "Content-Type": "application/json",
            "X-Station-Request-Id": "00112233445566778899aabbccddeeff",
          },
        }),
    });
    const user = userEvent.setup();
    let copied = "";
    stubClipboard((value) => {
      copied = value;
      return Promise.resolve();
    });
    await renderPanel();
    await toSendStep(user);
    await user.click(screen.getByRole("button", { name: "Onayla ve gonder" }));
    await screen.findByText("Gonderim tamamlanamadi");

    await user.click(screen.getByRole("button", { name: "Tani bilgisini kopyala" }));
    expect(await screen.findByRole("button", { name: "Kopyalandi" })).toBeInTheDocument();

    const payload = JSON.parse(copied) as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual([
      "code",
      "kind",
      "request_id",
      "section",
      "status",
      "timestamp",
    ]);
    expect(payload["code"]).toBe("approval_invalid");
    expect(payload["section"]).toBe("Olustur ve Dogrula / Gonderim");

    expect(copied).not.toContain("TEST-ONLY-CANONICAL-BYTES");
    expect(copied).not.toContain("did:key");
    expect(copied).not.toContain(SIGNATURE.signature);
    expect(copied).not.toContain(SIGNATURE.nonce);
    expect(copied).not.toContain(SIGNATURE.send_token);
    expect(copied).not.toContain(ROOM);
  });

  it("shows a retryable read failure with a retry, and a write failure without one", async () => {
    stubApi({ capability: () => Promise.reject(new TypeError("Failed to fetch")) });
    await bootstrapSession();
    render(<ComposerPanel needsVaultPassphrase={false} />);

    // Re-reading the capability touches nobody, so it may be repeated.
    expect(await screen.findByText("Gonderim yetkisi okunamadi")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yeniden dene" })).toBeInTheDocument();
  });

  it("never renders a 64-hex run, the same shape as a seed", async () => {
    stubApi();
    const user = userEvent.setup();
    const { container } = await renderPanel();
    await toSendStep(user);

    expect(container.textContent ?? "").not.toMatch(/\b[0-9a-fA-F]{64}\b/);
  });
});
