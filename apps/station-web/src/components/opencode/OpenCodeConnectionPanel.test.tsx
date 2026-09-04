import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bootstrapSession, resetSessionState } from "../../api/client";
import type { OpenCodeModel, OpenCodeStatus } from "../../api/types";
import { OpenCodeConnectionPanel } from "./OpenCodeConnectionPanel";

/**
 * These assertions encode the product rules of the credential surface, not
 * its styling.
 *
 * The key one is negative and easy to lose: **the provider key must not
 * survive the request that carries it**, must not be readable back from any
 * control, must not reach the redacted diagnostics payload, and must not be
 * rendered even when the server hands it straight back inside an error
 * message. A fixture that never contains a realistic key would let all four
 * of those regress silently, so the canary below is a long, distinctive,
 * TEST-ONLY string that is searched for across the whole document.
 */

//: TEST-ONLY. Not a credential for anything; it exists so a leak has a shape
//: to be found by. Long enough to survive a short-value redaction filter.
const TEST_ONLY_KEY = "TEST-ONLY-OPENCODE-KEY-NOT-REAL-4d9f2ab7c1e6";

const FREE_MODEL: OpenCodeModel = {
  model_id: "glm-5.3",
  owned_by: "zhipu",
  selectable: true,
  protocol: "chat_completions",
  protocol_verification: "documented",
  reason: "",
  retention: "Saklanmiyor (0 gun)",
  training_use: "no",
  requires_training_acknowledgement: false,
  privacy_source: "opencode.ai/docs/go Privacy tablosu",
  privacy_read_on: "2026-09-04",
};

const TRAINING_MODEL: OpenCodeModel = {
  model_id: "muse-spark-1",
  owned_by: "muse",
  selectable: true,
  protocol: "messages",
  protocol_verification: "unverified",
  reason: "",
  retention: "30 gun",
  training_use: "yes",
  requires_training_acknowledgement: true,
  privacy_source: "opencode.ai/docs/go Privacy tablosu",
  privacy_read_on: "2026-09-04",
};

const UNMAPPED_MODEL: OpenCodeModel = {
  model_id: "grok-4.6",
  owned_by: "xai",
  selectable: false,
  protocol: "",
  protocol_verification: "unverified",
  reason: "Protokol ailesi yayimlanmadigi icin bu model adreslenemiyor.",
  retention: "unknown",
  training_use: "unknown",
  requires_training_acknowledgement: true,
  privacy_source: "yayimlanmamis",
  privacy_read_on: "-",
};

const BASE: OpenCodeStatus = {
  configured: false,
  fingerprint_short: "",
  configured_at: null,
  updated_at: null,
  check: {
    state: "not_configured",
    reasons: ["Anahtar kaydedilmedi."],
    detail: "Saglayici anahtari kaydedilmedi.",
  },
  selected_model: "",
  auth_header_caveat:
    "Kimlik dogrulama basligi resmi belgede yayimlanmamistir. Station yaygin uygulamayi izleyerek 'Authorization: Bearer' gonderir; bu bir varsayimdir ve dogrulanmamistir.",
  catalog: {
    state: "never_fetched",
    fetched_at: null,
    models_fetched_at: null,
    detail: "",
    http_status: 0,
    models: [],
    model_count: 0,
    selectable_count: 0,
    unmapped_count: 0,
    listing_caveat:
      "Bu liste saglayicinin acik katalogudur ve anahtarsiz da yanit verir. Bir modelin listelenmesi, bu hesabin onu cagirabildigi anlamina gelmez.",
    table_provenance:
      "Protokol eslemesi bu surumde sabit: 27 satirlik tablo 2026-09-04 tarihinde okundu ve kaynak sayfanin o gunku altbilgisi '2026-09-03' diyordu. Kaynak o tarihten sonra degismis olabilir; Station sayfayi kendiliginden yeniden okumaz.",
    drift_notice: "",
  },
  spending: {
    budget_available: false,
    limits: [
      { window: "5 saat", amount_usd: 12, note: "Bes saatlik pencerede yayimlanmis ust sinir." },
      { window: "hafta", amount_usd: 30, note: "Haftalik yayimlanmis ust sinir." },
      { window: "ay", amount_usd: 60, note: "Aylik yayimlanmis ust sinir." },
    ],
    limit_behaviour:
      "Yayimlanmis sinir dolunca saglayici ucretsiz modellere duser veya tercihe gore Zen bakiyesinden dusurur.",
    use_balance:
      "'Use balance' tercihi saglayicinin kendi konsolundadir ve API uzerinden sorgulanamaz. Station bu ayari degistirmez ve engelledigini iddia etmez.",
    local_counter_caveat:
      "Yerel sayac yalnizca bu kurulumun gonderdigini sayar. Paylasilan bir abonelikte gercek kullanimi kanitlamaz.",
    unknown_cost_sentence:
      "Token ve maliyet bilgisi saglayicidan gelmedi; bilinmiyor. Sifir yazilmaz.",
  },
  protocol_context: {
    protocols: ["responses", "messages", "chat_completions"],
    streaming_supported: false,
    tool_calls_supported: false,
    deferral:
      "Akis (streaming) ve arac cagrisi bu surumde yoktur: resmi belgede bu iki bicimin sozlesmesi yayimlanmamis, tahmin edilmemistir. Sozlesme yayimlandiginda yurutucu paketinin isidir.",
    shape_provenance:
      "Uc protokol ailesinin govde bicimi OpenCode belgelerinde yayimlanmis degildir. Station, endpoint adlarinin isaret ettigi ust protokol ailelerinin bilinen non-streaming bicimini kullanir.",
  },
};

const WITH_CATALOG: OpenCodeStatus = {
  ...BASE,
  catalog: {
    ...BASE.catalog,
    state: "ok",
    fetched_at: "2026-09-04T09:30:00+00:00",
    models_fetched_at: "2026-09-04T09:30:00+00:00",
    detail: "Katalog okundu.",
    http_status: 200,
    models: [FREE_MODEL, TRAINING_MODEL, UNMAPPED_MODEL],
    model_count: 3,
    selectable_count: 2,
    unmapped_count: 1,
  },
};

/**
 * The catalog after it outgrew the pinned protocol table.
 *
 * The backend decides when this sentence exists; the panel's only job is to
 * show it when it does and to show nothing when it does not. Both halves are
 * asserted, because a warning that is always on is not a warning.
 */
const WITH_DRIFT: OpenCodeStatus = {
  ...BASE,
  catalog: {
    ...BASE.catalog,
    state: "ok",
    fetched_at: "2026-09-04T09:30:00+00:00",
    models_fetched_at: "2026-09-04T09:30:00+00:00",
    detail: "Katalog okundu.",
    http_status: 200,
    models: [FREE_MODEL, TRAINING_MODEL, UNMAPPED_MODEL],
    model_count: 35,
    selectable_count: 2,
    unmapped_count: 8,
    drift_notice:
      "Saglayicinin katalogu 35 model listeledi ve bunlarin 8 tanesi bu surumun pinli tablosunda yok. Tablo 2026-09-04 tarihinde okundugunda fazlalik 7 idi. Kaynak sayfa buyumus gorunuyor: tablo bayat olabilir. Eslemesi olmayan modeller secilemez, tahmin de edilmez.",
  },
};

const SAVED: OpenCodeStatus = {
  ...WITH_CATALOG,
  configured: true,
  fingerprint_short: "a1b2c3d4e5f6",
  configured_at: "2026-09-04T10:00:00+00:00",
  updated_at: "2026-09-04T10:00:00+00:00",
  check: {
    state: "key_saved_unverified",
    reasons: [
      "Katalog anahtarsiz da yanit verdigi icin listeyi cekebilmek anahtari dogrulamaz.",
      "Protokol yollarina yapilan kimliksiz bir GET 404 dondurur; probe olarak kullanilamaz.",
      "Ucretli gercek bir cagri bu surumde kendiliginden yapilmaz.",
    ],
    detail: "Anahtar kaydedildi, dogrulanmadi.",
  },
};

function jsonOk(body: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

interface Recorded {
  readonly url: string;
  readonly body: string;
}

/**
 * Stub `fetch` for the whole panel. `sent` records every request body so the
 * assertions can check what actually crossed the boundary rather than what
 * the component claims it sent.
 */
function stub(
  status: OpenCodeStatus,
  overrides: {
    readonly onPost?: (url: string) => Promise<Response> | null;
    readonly sent?: Recorded[];
  } = {},
): ReturnType<typeof vi.fn> {
  const spy = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;

    if (url.includes("/api/session/bootstrap")) {
      return jsonOk({
        csrf_token: "test-only-value-not-a-real-token",
        csrf_header: "X-Station-CSRF",
      });
    }

    if (init?.method === "POST") {
      overrides.sent?.push({ url, body: typeof init.body === "string" ? init.body : "" });
      const replacement = overrides.onPost?.(url);
      if (replacement !== null && replacement !== undefined) return replacement;
    }

    return jsonOk(status);
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

async function ready(): Promise<void> {
  await screen.findByText("Baglanti denetimi");
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetSessionState();
});

describe("OpenCode credential surface", () => {
  it("wipes the key from the field and from the document once it is stored", async () => {
    const sent: Recorded[] = [];
    stub(BASE, {
      sent,
      onPost: (url) => (url.includes("/credential") ? jsonOk(SAVED) : null),
    });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<OpenCodeConnectionPanel />);
    await ready();

    const field = screen.getByLabelText("OpenCode Go API anahtari");
    await user.type(field, TEST_ONLY_KEY);
    expect(field).toHaveValue(TEST_ONLY_KEY);

    await user.click(screen.getByRole("button", { name: "Anahtari kaydet" }));
    await screen.findByText("Anahtar kaydedildi, dogrulanmadi.");

    // It crossed the boundary exactly once...
    expect(sent.filter((entry) => entry.body.includes(TEST_ONLY_KEY))).toHaveLength(1);
    // ...and it is gone from the field, from state and from the document.
    expect(screen.queryByLabelText("OpenCode Go API anahtari")).toBeNull();
    expect(document.body.innerHTML).not.toContain(TEST_ONLY_KEY);
  });

  it("offers no control that reads a stored key back", async () => {
    stub(SAVED);
    render(<OpenCodeConnectionPanel />);
    await ready();

    // What is shown instead is a fingerprint, which is not part of the key.
    expect(screen.getByText(/parmak izi a1b2c3d4e5f6/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /goster/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /kopyala$/i })).toBeNull();
    // No masked field either, until the user asks to change the key.
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(0);
  });

  it("keeps the redacted diagnostics payload free of the key when a store fails", async () => {
    stub(BASE, {
      onPost: (url) =>
        url.includes("/credential")
          ? Promise.resolve(
              new Response(
                // The upstream reflects the submitted value back. This is the
                // case the redaction exists for.
                JSON.stringify({ detail: `Saglayici anahtari reddetti: ${TEST_ONLY_KEY}` }),
                {
                  status: 400,
                  headers: {
                    "Content-Type": "application/json",
                    "X-Station-Request-Id": "0".repeat(32),
                  },
                },
              ),
            )
          : null,
    });
    await bootstrapSession();
    const user = userEvent.setup();
    // Stubbed after `userEvent.setup()`, which installs a clipboard of its own.
    let copied = "";
    const clipboard = vi.fn((text: string) => {
      copied = text;
      return Promise.resolve();
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboard },
    });
    render(<OpenCodeConnectionPanel />);
    await ready();

    await user.type(screen.getByLabelText("OpenCode Go API anahtari"), TEST_ONLY_KEY);
    await user.click(screen.getByRole("button", { name: "Anahtari kaydet" }));

    const alert = await screen.findByText("Anahtar kaydedilemedi");
    const region = alert.closest('[role="alert"]');
    expect(region).not.toBeNull();
    // The reflected key is not rendered, even though the server sent it.
    expect(region?.textContent ?? "").not.toContain(TEST_ONLY_KEY);
    // The stable code, status and request id survived the redaction.
    expect(region?.textContent ?? "").toContain("http_400");
    expect(region?.textContent ?? "").toContain("0".repeat(32));

    await user.click(within(region as HTMLElement).getByRole("button", { name: /kopyala/i }));
    await waitFor(() => {
      expect(clipboard).toHaveBeenCalledTimes(1);
    });
    expect(copied).not.toContain(TEST_ONLY_KEY);
    // The payload shape is fixed by Paket C and this package does not widen it.
    expect(Object.keys(JSON.parse(copied) as object).sort()).toEqual([
      "code",
      "kind",
      "request_id",
      "section",
      "status",
      "timestamp",
    ]);
  });

  it("starts no second store while one is in flight", async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let stores = 0;

    stub(BASE, {
      onPost: (url) => {
        if (!url.includes("/credential")) return null;
        stores += 1;
        return held.then(() => new Response(JSON.stringify(SAVED), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }));
      },
    });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<OpenCodeConnectionPanel />);
    await ready();

    await user.type(screen.getByLabelText("OpenCode Go API anahtari"), TEST_ONLY_KEY);
    await user.click(screen.getByRole("button", { name: "Anahtari kaydet" }));

    const busy = await screen.findByRole("button", { name: "Kaydediliyor..." });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    expect(stores).toBe(1);

    release();
    await screen.findByText("Anahtar kaydedildi, dogrulanmadi.");
    expect(stores).toBe(1);
  });

  it("uses no browser-side persistence for the key or the selection", async () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { getItem: () => null, setItem, removeItem: vi.fn() });
    vi.stubGlobal("sessionStorage", { getItem: () => null, setItem, removeItem: vi.fn() });

    const sent: Recorded[] = [];
    stub(WITH_CATALOG, { sent, onPost: (url) => (url.includes("/model") ? jsonOk(SAVED) : null) });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<OpenCodeConnectionPanel />);
    await ready();

    await user.type(screen.getByLabelText("OpenCode Go API anahtari"), TEST_ONLY_KEY);
    await user.click(screen.getByRole("radio", { name: /glm-5\.3/ }));
    await user.click(screen.getByRole("button", { name: "Modeli sec" }));
    await waitFor(() => {
      expect(sent.some((entry) => entry.url.includes("/model"))).toBe(true);
    });

    expect(setItem).not.toHaveBeenCalled();
  });
});

describe("OpenCode honest status", () => {
  it("produces no verified verdict and no green badge from a check", async () => {
    stub(SAVED);
    const user = userEvent.setup();
    render(<OpenCodeConnectionPanel />);
    await ready();

    await user.click(screen.getByRole("button", { name: "Baglantiyi denetle" }));
    await waitFor(() => {
      expect(screen.getAllByText("Anahtar kaydedildi, dogrulanmadi").length).toBeGreaterThan(0);
    });

    const text = document.body.textContent ?? "";
    expect(text).not.toContain("Dogrulandi");
    expect(text).toContain("yeni bir dogrulama uretmez");
    expect(text).toContain("Anahtarin bicimi dogru diye gecerli sayilmaz");
    // Plural reasons, all of them, not one summarised excuse.
    for (const reason of SAVED.check.reasons) {
      expect(screen.getByText(`• ${reason}`)).toBeInTheDocument();
    }
  });

  it("states that the auth header is an unverified assumption", async () => {
    stub(BASE);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(screen.getByText("Kimlik dogrulama basligi dogrulanmadi")).toBeInTheDocument();
    expect(screen.getByText(BASE.auth_header_caveat)).toBeInTheDocument();
  });

  it("says streaming and tool calls are absent and why", async () => {
    stub(BASE);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(screen.getByText(BASE.protocol_context.deferral)).toBeInTheDocument();
    expect(screen.getByText(BASE.protocol_context.shape_provenance)).toBeInTheDocument();
    expect(screen.getByText(/akis: yok · arac cagrisi: yok/)).toBeInTheDocument();
  });

  it("says a connected key is not permission to share files", async () => {
    stub(SAVED);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(
      screen.getByText("Anahtarin bagli olmasi dosya paylasimi demek degildir"),
    ).toBeInTheDocument();
    expect(screen.getByText(/gorev baslamadan once o gorevin kendi ekraninda/)).toBeInTheDocument();
  });

  it("never calls the subscription unlimited and never turns an unknown cost into zero", async () => {
    stub(SAVED);
    render(<OpenCodeConnectionPanel />);
    await ready();

    const text = (document.body.textContent ?? "").toLowerCase();
    expect(text).not.toContain("sinirsiz");
    expect(text).not.toContain("unlimited");

    expect(screen.getByText(SAVED.spending.unknown_cost_sentence)).toBeInTheDocument();
    expect(screen.getByText(SAVED.spending.local_counter_caveat)).toBeInTheDocument();
    // "Use balance" lives in the provider console; Station claims no control.
    expect(screen.getByText(SAVED.spending.use_balance)).toBeInTheDocument();
    expect(screen.getByText("Butce bu surumde yok")).toBeInTheDocument();
    expect(screen.getByText("hafta: 30 USD")).toBeInTheDocument();
  });
});

describe("OpenCode model catalogue", () => {
  it("shows the cache date and the listing caveat", async () => {
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(screen.getByText(WITH_CATALOG.catalog.listing_caveat)).toBeInTheDocument();
    expect(screen.getByText("Listenin okundugu an")).toBeInTheDocument();
    expect(screen.getByText("3 listelendi · 2 secilebilir")).toBeInTheDocument();
    // A real date, not an empty dash: the cache has an age and it is visible.
    expect(screen.getAllByText(/2026/).length).toBeGreaterThan(0);
  });

  it("always shows where the pinned protocol table came from and when", async () => {
    // Not conditional on a problem. The table's age is a fact about every
    // reading of it, and a provenance line that only appears next to a
    // warning is a line nobody has ever read.
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    const provenance = screen.getByTestId("opencode-table-provenance");
    expect(provenance).toHaveTextContent("2026-09-04 tarihinde okundu");
    expect(provenance).toHaveTextContent("2026-09-03");
    expect(provenance).toHaveTextContent("degismis olabilir");
  });

  it("stays quiet about drift while the catalog matches the pinned table", async () => {
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(screen.queryByTestId("opencode-catalog-drift")).not.toBeInTheDocument();
    expect(screen.queryByText("Model tablosu bayat olabilir")).not.toBeInTheDocument();
  });

  it("warns, visibly, when the catalog has outgrown the pinned table", async () => {
    // The case the connection was blind to: the source page gained rows and
    // every number in this build stayed where it was, so the surplus models
    // were listed as unselectable and looked exactly like the expected ones.
    stub(WITH_DRIFT);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(screen.getByText("Model tablosu bayat olabilir")).toBeInTheDocument();
    const notice = screen.getByTestId("opencode-catalog-drift");
    expect(notice).toHaveTextContent("35 model listeledi");
    expect(notice).toHaveTextContent("8 tanesi");
    expect(notice).toHaveTextContent("bayat olabilir");
  });

  it("reports a failed refresh without deleting the cache or its date", async () => {
    const failed: OpenCodeStatus = {
      ...WITH_CATALOG,
      catalog: {
        ...WITH_CATALOG.catalog,
        state: "fetch_error",
        fetched_at: "2026-09-04T11:00:00+00:00",
        detail: "Katalog okunamadi.",
        http_status: 503,
      },
    };
    stub(failed);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(screen.getByText("Listeye erisilemedi")).toBeInTheDocument();
    expect(screen.getByText(/Katalog okunamadi\. \(HTTP 503\)/)).toBeInTheDocument();
    // The models and the date they were actually read under both survive.
    expect(screen.getByRole("radio", { name: /glm-5\.3/ })).toBeInTheDocument();
  });

  it("lists an unmapped model but refuses to let it be selected, and says why", async () => {
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    const unmapped = screen.getByRole("radio", { name: /grok-4\.6/ });
    expect(unmapped).toBeDisabled();
    expect(screen.getByText(`Secilemez: ${UNMAPPED_MODEL.reason}`)).toBeInTheDocument();
    expect(screen.getByText(/Protokol: yayimlanmamis/)).toBeInTheDocument();
  });

  it("does not invent a display name, a limit or tool support", async () => {
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(
      screen.getByText(/gorunur ad, baglam\/cikti limiti ve arac destegi alanlarini/),
    ).toBeInTheDocument();
  });

  it("says an unknown retention is unknown rather than reassuring", async () => {
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(screen.getByText("Egitim kullanimi bilinmiyor")).toBeInTheDocument();
    expect(screen.getByText(/Veri saklama: unknown · kaynak: yayimlanmamis/)).toBeInTheDocument();
  });

  it("shows the data policy with its source and the date it was read", async () => {
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(
      screen.getAllByText(/kaynak: opencode\.ai\/docs\/go Privacy tablosu · okundugu tarih: 2026-09-04/)
        .length,
    ).toBeGreaterThan(0);
  });

  it("preselects nothing, so a training model is never the default", async () => {
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).not.toBeChecked();
    }
    expect(screen.getByRole("button", { name: "Modeli sec" })).toBeDisabled();
    expect(screen.getByText("secilmedi")).toBeInTheDocument();
  });

  it("requires an extra sharing consent before a training model can be chosen", async () => {
    const sent: Recorded[] = [];
    stub(WITH_CATALOG, { sent, onPost: (url) => (url.includes("/model") ? jsonOk(SAVED) : null) });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<OpenCodeConnectionPanel />);
    await ready();

    await user.click(screen.getByRole("radio", { name: /muse-spark-1/ }));
    expect(screen.getByRole("button", { name: "Modeli sec" })).toBeDisabled();
    expect(screen.getByText("Ek paylasim onayi gerekiyor")).toBeInTheDocument();
    expect(screen.getByText(/Bu modelin yayimlanmis veri isleme kosulu: 30 gun/)).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Modeli sec" }));

    await waitFor(() => {
      expect(sent.some((entry) => entry.url.includes("/model"))).toBe(true);
    });
    const body = JSON.parse(sent.find((entry) => entry.url.includes("/model"))?.body ?? "{}") as {
      model_id: string;
      training_acknowledged: boolean;
    };
    expect(body).toEqual({ model_id: "muse-spark-1", training_acknowledged: true });
  });

  it("drops the consent when the pick changes", async () => {
    stub(WITH_CATALOG);
    await bootstrapSession();
    const user = userEvent.setup();
    render(<OpenCodeConnectionPanel />);
    await ready();

    await user.click(screen.getByRole("radio", { name: /muse-spark-1/ }));
    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Modeli sec" })).toBeEnabled();

    await user.click(screen.getByRole("radio", { name: /glm-5\.3/ }));
    await user.click(screen.getByRole("radio", { name: /muse-spark-1/ }));
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Modeli sec" })).toBeDisabled();
  });

  it("says the selection is permanent but proves nothing about access", async () => {
    stub(WITH_CATALOG);
    render(<OpenCodeConnectionPanel />);
    await ready();

    expect(screen.getByText(/erisim ve yetenekler her calistirmanin basinda/)).toBeInTheDocument();
    expect(screen.getByText(/sessizce baska bir modele veya saglayiciya/)).toBeInTheDocument();
  });

  it("starts no second refresh while one is in flight", async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let refreshes = 0;

    stub(BASE, {
      onPost: (url) => {
        if (!url.includes("/catalog/refresh")) return null;
        refreshes += 1;
        return held.then(() => new Response(JSON.stringify(WITH_CATALOG), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }));
      },
    });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<OpenCodeConnectionPanel />);
    await ready();

    await user.click(screen.getByRole("button", { name: "Modelleri yenile" }));
    const busy = await screen.findByRole("button", { name: "Yenileniyor..." });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    expect(refreshes).toBe(1);

    release();
    await screen.findByText("Liste okundu");
    expect(refreshes).toBe(1);
  });

  it("keeps a refusal to select as a refusal, with the server's reason", async () => {
    stub(WITH_CATALOG, {
      onPost: (url) =>
        url.includes("/model")
          ? Promise.resolve(
              new Response(
                JSON.stringify({ detail: "Bu model icin protokol eslemesi yok; secilemez." }),
                { status: 400, headers: { "Content-Type": "application/json" } },
              ),
            )
          : null,
    });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<OpenCodeConnectionPanel />);
    await ready();

    await user.click(screen.getByRole("radio", { name: /glm-5\.3/ }));
    await user.click(screen.getByRole("button", { name: "Modeli sec" }));

    expect(await screen.findByText("Model secilemedi")).toBeInTheDocument();
    // The reason is the point of the refusal, so this lane keeps its prose.
    expect(
      screen.getByText("Bu model icin protokol eslemesi yok; secilemez."),
    ).toBeInTheDocument();
    // And nothing was silently substituted.
    expect(screen.getByText("secilmedi")).toBeInTheDocument();
  });
});
