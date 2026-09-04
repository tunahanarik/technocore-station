import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bootstrapSession, resetSessionState } from "../../api/client";
import type {
  AuditChainState,
  AuditChainStatus,
  CaptureAttemptState,
  EvidenceCaptureResult,
  EvidenceLevelStatus,
  EvidenceList,
  EvidenceRecord,
} from "../../api/types";
import { EvidenceLedgerPanel } from "./EvidenceLedgerPanel";

/**
 * These assertions encode the evidence model's product rules, not styling.
 *
 * The four trust levels are shown per record and never summed; the six capture
 * states are six different findings and only one of them is a server
 * observation; `line_not_found` proves nothing and never turns an unknown send
 * into one that did not happen; no surface here offers to write anything a
 * second time; the audit chain's claim is the backend's sentence rendered
 * verbatim; and an export cannot leave without explicit consent.
 *
 * Every fixture is TEST-ONLY. No real DID, no real signature, and the target
 * room is never `lobby` or `meta` - the denied rooms may not appear as a
 * target anywhere, including in a test that never reaches the network
 * (INV-05).
 */

const ROOM = "test-only-oda";

/**
 * Case-fold, strip diacritics and map the dotless i - the same folding
 * `station_api.evidence.language` applies.
 *
 * The charter spells the forbidden claims with Turkish letters and the UI
 * writes diacritic-free Turkish, so one claim has two spellings. A check
 * against a single spelling is one anybody could pass by accident.
 */
function fold(text: string): string {
  return text
    .toLocaleLowerCase("tr")
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .replace(/ı/g, "i")
    .replace(/\s+/g, " ");
}

//: TEST-ONLY levels, mirroring `EvidenceView.levels` for an uncaptured record.
const LEVELS: readonly EvidenceLevelStatus[] = [
  {
    level: 1,
    name: "Imza kaniti",
    present: true,
    detail: "Station kendi kanonik metnini kendi imzasiyla dogruladi.",
  },
  {
    level: 2,
    name: "Sunucu gozlemi",
    present: false,
    detail: "Henuz yakalama denenmedi.",
  },
  {
    level: 3,
    name: "Yerel kayit zamani",
    present: true,
    detail: "Bu makinenin saati; guvenilir bir zaman damgasi degildir.",
  },
  {
    level: 4,
    name: "Harici anchor",
    present: false,
    detail: "MVP kapsaminda yoktur; null olarak yazilir.",
  },
];

/**
 * TEST-ONLY record with **full-length** digests.
 *
 * Deliberately not shortened: a SHA-256 is 64 hex characters, the same shape
 * as a seed, and the surface-wide "no 64-hex run in the DOM" rule is only
 * proved by a fixture that actually carries one. A fixture with pre-shortened
 * digests would pass that assertion while the component rendered them whole.
 */
const RECORD: EvidenceRecord = {
  id: "ev-test-only-1",
  reservation_id: "res-test-only-1",
  room: ROOM,
  did: "did:key:z6MkTESTONLYEVIDENCEFIXTURE",
  nonce: "424242",
  canonical_sha256: "ab".repeat(32),
  signature: "TESTONLYSIGNATUREVALUE",
  http_status: 0,
  write_outcome: "outcome_unknown",
  capture_state: "",
  capture_detail: "",
  captured_at: null,
  room_generation: "7",
  capture_generation: "",
  generation_changed: false,
  captured_line_offset: null,
  captured_line_length: null,
  stream_sha256: "",
  stream_bytes: 0,
  stream_truncated: false,
  unreadable_lines: 0,
  request_sha256: "cd".repeat(32),
  response_sha256: "ef".repeat(32),
  recorded_at: "2026-09-04T10:00:00+00:00",
  external_anchor: null,
  levels: LEVELS,
};

const LEDGER: EvidenceList = {
  records: [RECORD],
  record_count: 1,
  chain_state: "intact",
  chain_detail: "Zincir tutarli.",
  chain_link_count: 3,
};

const EMPTY_LEDGER: EvidenceList = {
  records: [],
  record_count: 0,
  chain_state: "empty",
  chain_detail: "Henuz audit satiri yok.",
  chain_link_count: 0,
};

//: The backend's own sentence. The UI renders it and composes none of its own.
const CHAIN_CLAIM =
  "Audit zinciri cevrimdisi degisiklige karsi tespit edicidir. Ayni Windows " +
  "kullanicisi olarak calisan bir saldirgana, guvenilir bir zamana veya " +
  "ucuncu bir tarafa ispata karsilik gelmez.";

const AUDIT: AuditChainStatus = {
  state: "intact",
  detail: "3 satir dogrulandi ve zincir basi ayni sayiyi soyluyor.",
  link_count: 3,
  head_count: 3,
  first_bad_seq: null,
  claim: CHAIN_CLAIM,
};

/** The backend's sentence for each capture state, kept beside our own. */
const CAPTURE_DETAIL: Record<CaptureAttemptState, string> = {
  line_captured: "Kendi kaydimizin disa aktarilan satiri bulundu.",
  line_not_found: "Taranan kayitlar arasinda kendi satirimiz yoktu.",
  generation_changed: "Odanin generation degeri onceki yakalamadakinden farkli.",
  stream_truncated: "Disa aktarim akisi tarama tavanina dayandi.",
  parse_problem: "Akistaki bazi satirlar okunamadi.",
  fetch_failed: "Disa aktarim okunamadi.",
};

/** The title this surface must give each state. Six states, six titles. */
const CAPTURE_TITLE: Record<CaptureAttemptState, string> = {
  line_captured: "Satir yakalandi",
  line_not_found: "Satir bulunamadi",
  generation_changed: "Oda donemi degisti",
  stream_truncated: "Tarama tamamlanamadi",
  parse_problem: "Satirlar okunamadi",
  fetch_failed: "Okuma tamamlanamadi",
};

const ALL_STATES = Object.keys(CAPTURE_TITLE) as CaptureAttemptState[];

function captureResult(state: CaptureAttemptState): EvidenceCaptureResult {
  return {
    evidence_id: RECORD.id,
    state,
    detail: CAPTURE_DETAIL[state],
    server_observation: state === "line_captured",
    room_generation: "7",
    line_offset: state === "line_captured" ? 4096 : null,
    line_length: state === "line_captured" ? 312 : null,
    stream_sha256: "12".repeat(32),
    scanned_bytes: 65536,
    stream_truncated: state === "stream_truncated",
    read_retry_allowed: true,
    write_retry_allowed: false,
  };
}

type Route = "bootstrap" | "records" | "audit" | "capture" | "export";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

interface Stub {
  readonly calls: Record<Route, number>;
  readonly bodies: string[];
}

/**
 * Route the stub by URL.
 *
 * Four evidence endpoints. A stub answering everything with the ledger would
 * let the audit region render from the wrong shape and quietly pass.
 */
function stubApi(
  handlers: Partial<Record<Route, () => Promise<Response> | Response>> = {},
): Stub {
  const calls: Record<Route, number> = {
    bootstrap: 0,
    records: 0,
    audit: 0,
    capture: 0,
    export: 0,
  };
  const bodies: string[] = [];

  const defaults: Record<Route, () => Promise<Response> | Response> = {
    bootstrap: () =>
      json({ csrf_token: "test-only-value-not-a-real-token", csrf_header: "X-Station-CSRF" }),
    records: () => json(LEDGER),
    audit: () => json(AUDIT),
    capture: () => json(captureResult("line_captured")),
    export: () =>
      new Response("{}", {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      }),
  };

  function routeFor(url: string): Route | null {
    if (url.includes("/api/session/bootstrap")) return "bootstrap";
    if (url.includes("/api/evidence/records")) return "records";
    if (url.includes("/api/evidence/audit")) return "audit";
    if (url.includes("/api/evidence/capture")) return "capture";
    if (url.includes("/api/evidence/export")) return "export";
    return null;
  }

  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const route = routeFor(url);
      if (route === null) {
        return Promise.resolve(new Response("no route", { status: 404 }));
      }
      calls[route] += 1;
      if (typeof init?.body === "string") bodies.push(init.body);
      return Promise.resolve((handlers[route] ?? defaults[route])());
    }),
  );

  return { calls, bodies };
}

/** jsdom implements neither object-URL method; the export path needs both. */
function stubObjectUrls(): { readonly downloads: string[] } {
  const downloads: string[] = [];
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: () => "blob:test-only",
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: () => undefined,
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    downloads.push(this.download);
  });
  return { downloads };
}

function stubClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}

/** Render and wait for both independent reads to settle, however they end. */
async function renderPanel(): Promise<ReturnType<typeof render>> {
  await bootstrapSession();
  const view = render(<EvidenceLedgerPanel />);
  await waitFor(() => {
    expect(screen.queryByText("Kanit kayitlari okunuyor...")).toBeNull();
    expect(screen.queryByText("Zincir durumu okunuyor...")).toBeNull();
  });
  return view;
}

function recordsRegion(): HTMLElement {
  return screen.getByRole("region", { name: "Kanit kayitlari" });
}

/** Render, then ask for one capture and wait for its outcome region. */
async function captureWith(state: CaptureAttemptState): Promise<Stub> {
  const stub = stubApi({ capture: () => json(captureResult(state)) });
  const user = userEvent.setup();
  await renderPanel();
  await user.click(screen.getByRole("button", { name: /Kanit satirini yakala/ }));
  await screen.findByText(`Yakalama sonucu: ${CAPTURE_TITLE[state]}`);
  return stub;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetSessionState();
  Reflect.deleteProperty(URL, "createObjectURL");
  Reflect.deleteProperty(URL, "revokeObjectURL");
});

describe("Evidence ledger listing", () => {
  it("lists an archived record with its room, nonce and outcome", async () => {
    stubApi();
    await renderPanel();

    const region = recordsRegion();
    expect(within(region).getByText(`Oda: ${ROOM}`)).toBeInTheDocument();
    expect(within(region).getByText(RECORD.nonce)).toBeInTheDocument();
    expect(within(region).getByText("Sonuc bilinmiyor")).toBeInTheDocument();
    expect(within(region).getByText("Yakalama denenmedi")).toBeInTheDocument();
  });

  it("shows an honest empty state when nothing has been archived", async () => {
    stubApi({ records: () => json(EMPTY_LEDGER) });
    await renderPanel();

    expect(screen.getByText("Henuz kanit kaydi yok")).toBeInTheDocument();
    expect(screen.getByText(/kullanici onayli bir gonderim/)).toBeInTheDocument();
    // No invented record, and no capture control for a record that is not there.
    expect(screen.queryByRole("button", { name: /Kanit satirini yakala/ })).toBeNull();
  });

  it("never renders a 64-hex run, the same shape as a seed", async () => {
    // The fixture carries full-length digests on purpose, so this assertion
    // is about the component's shortening rather than about the fixture.
    stubApi();
    const { container } = await renderPanel();

    expect(container.textContent ?? "").not.toMatch(/\b[0-9a-fA-F]{64}\b/);
    expect(within(recordsRegion()).getByText("abababababab")).toBeInTheDocument();
  });

  it("shows a persistent error with a retry when the ledger cannot be read", async () => {
    stubApi({ records: () => Promise.reject(new TypeError("Failed to fetch")) });
    await renderPanel();

    expect(screen.getByText("Kanit kayitlari okunamadi")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Yeniden dene" }).length).toBeGreaterThan(0);
  });
});

describe("Evidence trust levels", () => {
  it("reports all four levels separately instead of summing them", async () => {
    stubApi();
    await renderPanel();
    const region = recordsRegion();

    for (const level of LEVELS) {
      expect(
        within(region).getByText(`Seviye ${String(level.level)} · ${level.name}`),
      ).toBeInTheDocument();
      expect(within(region).getByText(level.detail)).toBeInTheDocument();
    }

    // Two filled, two empty - four separate answers, never one badge.
    expect(within(region).getAllByText("Var")).toHaveLength(2);
    expect(within(region).getAllByText("Yok")).toHaveLength(2);
  });

  it("states that level 4 is absent rather than leaving it blank", async () => {
    stubApi();
    await renderPanel();
    const region = recordsRegion();

    expect(within(region).getByText(/Bu kayitta harici anchor yoktur/)).toBeInTheDocument();
    expect(within(region).getByText(/null olarak tutulur/)).toBeInTheDocument();
  });
});

describe("Evidence capture states", () => {
  it.each(ALL_STATES)("presents %s as a finding of its own", async (state) => {
    await captureWith(state);

    expect(screen.getByText(`Yakalama sonucu: ${CAPTURE_TITLE[state]}`)).toBeInTheDocument();
    // The backend's own sentence sits beside ours, not instead of it.
    expect(screen.getByText(CAPTURE_DETAIL[state])).toBeInTheDocument();
    // Every state, without exception, restates that this was a read.
    expect(
      screen.getByText(/gonderim hicbir durumda ve hicbir yolla yeniden denenmez/),
    ).toBeInTheDocument();
  });

  it.each(ALL_STATES)("offers no write retry after %s", async (state) => {
    await captureWith(state);

    const labels = screen.getAllByRole("button").map((button) => button.textContent ?? "");
    expect(labels.length).toBeGreaterThan(0);
    for (const label of labels) {
      expect(fold(label)).not.toMatch(/gonder/);
    }
  });

  it("calls a captured line a server observation and nothing more", async () => {
    await captureWith("line_captured");

    expect(screen.getByText(/yalnizca Seviye 2 sunucu gozlemidir/)).toBeInTheDocument();
    expect(screen.getByText(/bagimsiz bir ispati degildir/)).toBeInTheDocument();
  });

  it("says in words that a missing line proves nothing", async () => {
    await captureWith("line_not_found");

    expect(screen.getByText(/Bu sonuc hicbir sey kanitlamaz/)).toBeInTheDocument();
    expect(screen.getByText(/Oda halkasi eski kayitlari unutur/)).toBeInTheDocument();
  });

  it("never turns an unknown outcome plus a missing line into a send that did not happen", async () => {
    // This is the single inference the whole model exists to refuse
    // (ADR-0003 4). The record's outcome is `outcome_unknown` and the capture
    // found nothing; the surface must still say the outcome is unknown.
    await captureWith("line_not_found");

    expect(screen.getByText("Bu gonderimin sonucu hala bilinmiyor")).toBeInTheDocument();
    expect(screen.getByText(/Satirin bulunmamasi da bunu degistirmez/)).toBeInTheDocument();

    const text = fold(document.body.textContent ?? "");
    expect(text).not.toContain("gonderilmedi");
    expect(text).not.toContain("gonderilmemis");
  });

  it("calls a changed generation incomparable rather than a mismatch", async () => {
    await captureWith("generation_changed");

    expect(screen.getByText(/karsilastirilamaz/)).toBeInTheDocument();
    expect(screen.getByText(/farkli bir donemdir/)).toBeInTheDocument();
  });

  it.each(["stream_truncated", "parse_problem", "fetch_failed"] as const)(
    "presents %s as unreadable rather than as absence",
    async (state) => {
      await captureWith(state);
      expect(screen.getByText(/okunamama durumudur/)).toBeInTheDocument();
    },
  );

  it("offers a read retry, and labels it as a read", async () => {
    await captureWith("line_not_found");

    expect(
      screen.getByRole("button", { name: /Yakalamayi yeniden dene \(yalniz okur\)/ }),
    ).toBeInTheDocument();
  });

  it("starts no second capture while one is in flight", async () => {
    let release: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const stub = stubApi({ capture: () => pending });
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("button", { name: /Kanit satirini yakala/ }));
    const busy = await screen.findByRole("button", { name: "Yakalaniyor..." });
    expect(busy).toBeDisabled();

    fireEvent.click(busy);
    expect(stub.calls.capture).toBe(1);

    release(json(captureResult("line_captured")));
    expect(await screen.findByText("Yakalama sonucu: Satir yakalandi")).toBeInTheDocument();
  });

  it("keeps the redacted diagnostics payload unchanged when a capture fails", async () => {
    stubApi({
      capture: () =>
        new Response(JSON.stringify({ detail: "evidence_not_found" }), {
          status: 404,
          headers: {
            "Content-Type": "application/json",
            "X-Station-Request-Id": "00112233445566778899aabbccddeeff",
          },
        }),
    });
    // `userEvent.setup()` installs its own clipboard stub, so ours has to be
    // planted after it or it is silently replaced.
    const user = userEvent.setup();
    let copied = "";
    stubClipboard((value) => {
      copied = value;
      return Promise.resolve();
    });
    await renderPanel();

    await user.click(screen.getByRole("button", { name: /Kanit satirini yakala/ }));
    await screen.findByText("Yakalama tamamlanamadi");
    await user.click(screen.getByRole("button", { name: "Tani bilgisini kopyala" }));
    await screen.findByRole("button", { name: "Kopyalandi" });

    const payload = JSON.parse(copied) as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual([
      "code",
      "kind",
      "request_id",
      "section",
      "status",
      "timestamp",
    ]);
    expect(payload["section"]).toBe("Kanitlar / Yakalama");
    // No evidence field joins the payload: not a room, a nonce, a DID or a
    // digest.
    expect(copied).not.toContain(ROOM);
    expect(copied).not.toContain(RECORD.nonce);
    expect(copied).not.toContain(RECORD.did);
    expect(copied).not.toContain(RECORD.canonical_sha256);
  });
});

describe("Evidence audit chain", () => {
  const CHAIN_TITLE: Record<AuditChainState, string> = {
    intact: "Zincir tutarli",
    empty: "Zincir bos",
    broken_link: "Zincir halkasi kirilmis",
    head_mismatch: "Zincir basi uyusmuyor",
    unavailable: "Zincir dogrulanamadi",
  };

  it.each(Object.keys(CHAIN_TITLE) as AuditChainState[])(
    "names the %s verdict distinctly",
    async (state) => {
      stubApi({ audit: () => json({ ...AUDIT, state }) });
      await renderPanel();

      expect(screen.getByText(CHAIN_TITLE[state])).toBeInTheDocument();
      for (const [other, title] of Object.entries(CHAIN_TITLE)) {
        if (other !== state) expect(screen.queryByText(title)).toBeNull();
      }
    },
  );

  it("shows the backend's claim verbatim and invents none of its own", async () => {
    stubApi();
    await renderPanel();

    expect(screen.getByText(CHAIN_CLAIM)).toBeInTheDocument();
  });

  it("says truncation is undetectable without the separately held head", async () => {
    stubApi();
    await renderPanel();

    expect(
      screen.getByText(/sonun kesilmesi, ayri bir zarfta tutulan zincir basi olmadan/),
    ).toBeInTheDocument();
    // Scoped to a phrase the backend's own claim does not also contain: both
    // sentences name the same attacker, which is the point, so the assertion
    // has to pick the one this component wrote.
    expect(screen.getByText(/Bu bir garanti degildir/)).toBeInTheDocument();
    expect(
      screen.getByText(/butun MAC degerlerini yeniden hesaplayabilir/),
    ).toBeInTheDocument();
  });

  it("reports an unverifiable chain as unverified, never as passed", async () => {
    stubApi({
      audit: () =>
        json({
          ...AUDIT,
          state: "unavailable",
          detail: "Zincir dogrulanamadi: anahtar materyali acilamadi.",
          head_count: null,
        }),
    });
    await renderPanel();

    expect(screen.getByText("Zincir dogrulanamadi")).toBeInTheDocument();
    expect(screen.queryByText("Zincir tutarli")).toBeNull();
  });

  it("keeps the ledger readable when only the chain read fails", async () => {
    stubApi({ audit: () => Promise.reject(new TypeError("Failed to fetch")) });
    await renderPanel();

    expect(screen.getByText("Audit zinciri okunamadi")).toBeInTheDocument();
    expect(within(recordsRegion()).getByText(`Oda: ${ROOM}`)).toBeInTheDocument();
  });
});

describe("Evidence export", () => {
  it("sends no request until consent has been given", async () => {
    const stub = stubApi();
    await renderPanel();

    const jsonButton = screen.getByRole("button", { name: "JSON olarak disa aktar" });
    expect(jsonButton).toBeDisabled();

    fireEvent.click(jsonButton);
    expect(stub.calls.export).toBe(0);
  });

  it("exports JSON once the consent box is ticked", async () => {
    const stub = stubApi();
    const { downloads } = stubObjectUrls();
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "JSON olarak disa aktar" }));

    await screen.findByText(/technocore-station-kanit\.json/);
    expect(stub.calls.export).toBe(1);
    expect(JSON.parse(stub.bodies.at(-1) ?? "{}")).toEqual({
      format: "json",
      acknowledged: true,
    });
    // The download name is the client's own constant, not a parsed header.
    expect(downloads).toEqual(["technocore-station-kanit.json"]);
  });

  it("exports Markdown under the same single consent step", async () => {
    const stub = stubApi();
    const { downloads } = stubObjectUrls();
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Markdown olarak disa aktar" }));

    await screen.findByText(/technocore-station-kanit\.md/);
    expect(JSON.parse(stub.bodies.at(-1) ?? "{}")).toEqual({
      format: "markdown",
      acknowledged: true,
    });
    expect(downloads).toEqual(["technocore-station-kanit.md"]);
  });

  it("warns that sharing the file creates an identity link", async () => {
    stubApi();
    await renderPanel();

    expect(screen.getByText("Paylasim kimlik baglantisi dogurur")).toBeInTheDocument();
    expect(screen.getByText(/kalici bir kimlik baglantisi kurulur/)).toBeInTheDocument();
  });

  it("keeps the export separate from the redacted diagnostics report", async () => {
    // Two different surfaces carrying two different things. Offering the
    // export where a bug report is wanted would hand over the archive itself.
    stubApi();
    await renderPanel();

    expect(screen.getByText(/Tani ciktisi redaktedir ve yalnizca hata/)).toBeInTheDocument();
  });

  it("reports a refused export instead of pretending a file was produced", async () => {
    stubApi({ export: () => json({ detail: "export_refused" }, 400) });
    stubObjectUrls();
    const user = userEvent.setup();
    await renderPanel();

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "JSON olarak disa aktar" }));

    expect(await screen.findByText("Disa aktarim tamamlanamadi")).toBeInTheDocument();
    expect(screen.queryByText(/Dosya tarayiciya verildi/)).toBeNull();
  });
});

describe("Evidence language and inert content", () => {
  /** The six phrases the backend's language registry refuses, folded. */
  const FORBIDDEN = [
    "sunucu kaniti",
    "degismez kayit",
    "guvenilir zaman kaniti",
    "airdrop uygunluk kaniti",
    // Package E added these two: the same over-claim, about truncation.
    "degistirilemez kayit",
    "kurcalanamaz kayit",
  ] as const;

  it.each(ALL_STATES)("uses none of the forbidden claims after %s", async (state) => {
    await captureWith(state);
    const panel = screen.getByRole("region", { name: "Kanit defteri" });

    const text = fold(panel.textContent ?? "");
    for (const claim of FORBIDDEN) {
      expect(text).not.toContain(claim);
    }
    // And the one permitted sentence about the chain is present.
    expect(text).toContain("cevrimdisi degisiklige karsi tespit edici");
  });

  it("renders no anchor and no markup from any archived value", async () => {
    // AC-17 / SI-54. Room names and generations come from the network side of
    // this product; they are data, never active content.
    stubApi({
      records: () =>
        json({
          ...LEDGER,
          records: [{ ...RECORD, room: '<a href="https://evil.test">tikla</a>' }],
        }),
    });
    const { container } = await renderPanel();

    expect(
      within(recordsRegion()).getByText('Oda: <a href="https://evil.test">tikla</a>'),
    ).toBeInTheDocument();
    expect(container.querySelectorAll("a")).toHaveLength(0);
    expect(container.innerHTML).not.toContain("<a href");
  });
});
