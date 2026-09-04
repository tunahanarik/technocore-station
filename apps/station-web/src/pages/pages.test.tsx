import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bootstrapSession, resetSessionState } from "../api/client";
import type {
  AppStatus,
  AuditChainStatus,
  ComposeCapability,
  ConformanceStatus,
  EvidenceList,
  IdentityStatus,
  OpenCodeStatus,
  TechnocoreStatus,
} from "../api/types";
import { ComposeVerifyPage } from "./ComposeVerifyPage";
import { EvidencePage } from "./EvidencePage";
import { IdentityPage } from "./IdentityPage";
import { OverviewPage } from "./OverviewPage";
import { SettingsHelpPage } from "./SettingsHelpPage";
import { SourcesPage } from "./SourcesPage";

/**
 * These assertions encode product rules, not styling:
 * no seed anywhere, no invented identity, no airdrop claim, and a lock that
 * reflects the real write gate.
 */

const NO_IDENTITY: IdentityStatus = {
  state: "no_identity",
  identity: null,
  recovery: {
    exported_at: null,
    verified_at: null,
    file_fingerprint: null,
    kdf: null,
    kdf_time_cost: null,
    kdf_memory_kib: null,
    kdf_parallelism: null,
  },
  capability: {
    platform_supported: true,
    dpapi_available: true,
    aead_available: true,
    usable: true,
    detail: "DPAPI ve AEAD kullanilabilir.",
  },
  gate: {
    allowed: false,
    identity_ready: false,
    // Both conformance and manifest are real checks now. Conformance passes
    // on a healthy build; the manifest stays blocked until the user runs a
    // live check in this session.
    blocking_reasons: ["identity_present", "manifest_current"],
    checks: [
      { key: "identity_present", state: "blocked", detail: "Aktif bir kimlik gerekli.", stage: "2" },
      {
        key: "recovery_verified",
        state: "blocked",
        detail: "Recovery restore-test ile dogrulanmis olmali.",
        stage: "2",
      },
      {
        key: "conformance_verified",
        state: "passed",
        detail: "Sweep/canonical/imza uygunlugu self-test ile dogrulanmali.",
        stage: "2B",
      },
      {
        key: "manifest_current",
        state: "blocked",
        detail: "Resmi kaynaklar bu oturumda denetlenmis ve guncel olmali.",
        stage: "3",
      },
    ],
  },
  default_protection: "dpapi+passphrase",
  min_passphrase_chars: 16,
  create_confirmation_text: "KİMLİK OLUŞTUR",
};

//: TEST-ONLY fixture identity. Not a real DID.
const READY: IdentityStatus = {
  ...NO_IDENTITY,
  state: "ready",
  identity: {
    did: "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp",
    public_key: "aa".repeat(32),
    fingerprint: "bb".repeat(32),
    fingerprint_short: "bbbb bbbb bbbb bbbb",
    label: "TEST-ONLY",
    status: "ready",
    protection: "dpapi+passphrase",
    created_at: "2026-08-30T10:00:00+00:00",
    revoked_at: null,
  },
  recovery: { ...NO_IDENTITY.recovery, exported_at: "2026-08-30T10:05:00+00:00", verified_at: "2026-08-30T10:06:00+00:00" },
  gate: { ...NO_IDENTITY.gate, identity_ready: true },
};

//: TEST-ONLY conformance fixture. The digest is deliberately short: the full
//: 64-hex value must never reach the DOM, and a fixture that carried one
//: would hide a real leak from the assertion below.
const CONFORMANT: ConformanceStatus = {
  passed: true,
  checks: [
    { name: "sweep", passed: true, vectors: 32, detail: "swept text matches the reference" },
    { name: "did", passed: true, vectors: 4, detail: "did:key matches the reference" },
    { name: "canonical", passed: true, vectors: 15, detail: "canonical bytes match" },
    { name: "signing", passed: true, vectors: 15, detail: "signatures match the reference" },
    { name: "verification", passed: true, vectors: 15, detail: "reference signatures verify" },
    { name: "encoding", passed: true, vectors: 15, detail: "canonical base64url" },
    { name: "tamper", passed: true, vectors: 8, detail: "tampered payloads refused" },
    { name: "unicode_database", passed: true, vectors: 0, detail: "Unicode 15.0.0" },
  ],
  failures: [],
  capabilities: ["sweep", "did", "canonical", "signing", "verification", "encoding", "tamper"],
  bundle_digest: "688c6e4dcf14eeed",
  bundle_digest_short: "688c6e4dcf14",
  bundle_vectors: 104,
  upstream_commit: "7707cb63ebf638e8ef0cf59d1364818b9fef7d24",
  upstream_commit_short: "7707cb6",
  package_version: "0.3.0",
  python_version: "3.12.11",
  unicode_version: "15.0.0",
  bundle_unicode_version: "15.0.0",
  unicode_version_matches: true,
};

//: TEST-ONLY app status fixture, mirroring /api/app/status.
const APP_STATUS: AppStatus = {
  service: { state: "running", stage: 3, mode: "production" },
  database: {
    state: "ready",
    journal_mode: "wal",
    foreign_keys: true,
    schema_revision: "0002",
  },
  session_security: {
    state: "active",
    cookie_http_only: true,
    cookie_same_site: "strict",
    cookie_secure: false,
    csrf_required: true,
    transport: "loopback-http",
  },
  technocore: {
    state: "never_checked",
    write_available_from_stage: 4,
    detail: "Resmi kaynaklar bu oturumda henuz denetlenmedi.",
  },
};

//: TEST-ONLY read-only monitoring fixture. Mirrors the real response shape.
const TECHNOCORE_CURRENT: TechnocoreStatus = {
  state: "current",
  manifest_current: true,
  checked_at: "2026-08-30T18:00:00+00:00",
  last_attempt_at: "2026-08-30T18:00:00+00:00",
  last_success_at: "2026-08-30T18:00:00+00:00",
  reasons: [],
  sources: [
    {
      source_id: "openapi",
      url: "https://technocore.chat/openapi.json",
      authority: 1,
      outcome: "ok",
      http_status: 200,
      content_type: "application/json",
      etag: '"abc123"',
      last_modified: "",
      short_hash: "aabbccdd1122",
      byte_count: 60482,
      detail: "",
      rationale: "The authoritative API description.",
    },
  ],
  fields: [
    {
      key: "signature_pattern",
      label: "Imza bicimi",
      source_id: "openapi",
      // The real location and the real pattern. The earlier fixture carried
      // the wrong ones on both counts, which is what Stage 3.1 fixed.
      json_path:
        "/paths/~1r~1{room}/post/requestBody/content/application~1json/schema/dependentSchemas/did/properties/sig/pattern",
      severity: "critical",
      expected: "^[A-Za-z0-9_-]{85}[AQgw]$",
      observed: "^[A-Za-z0-9_-]{85}[AQgw]$",
      matches: true,
      outcome: "matched",
      rationale: "Padding'siz base64url, tam 86 karakter, son karakter AQgw.",
      detail: "",
    },
  ],
  critical_mismatch_count: 0,
  critical_unevaluable_count: 0,
  warning_count: 0,
  origin: "https://technocore.chat",
};

const TECHNOCORE_NEVER_CHECKED: TechnocoreStatus = {
  ...TECHNOCORE_CURRENT,
  state: "never_checked",
  manifest_current: false,
  checked_at: null,
  last_attempt_at: null,
  last_success_at: null,
  sources: [],
  fields: [],
};

const TECHNOCORE_DRIFTED: TechnocoreStatus = {
  ...TECHNOCORE_CURRENT,
  state: "drifted",
  manifest_current: false,
  last_success_at: null,
  reasons: [
    "Imza bicimi: beklenen '^[A-Za-z0-9_-]{85}[AQgw]$', gorulen '^[A-Za-z0-9+/]{88}$'",
  ],
  fields: [
    {
      ...TECHNOCORE_CURRENT.fields[0]!,
      observed: "^[A-Za-z0-9+/]{88}$",
      matches: false,
      outcome: "mismatch",
    },
  ],
  critical_mismatch_count: 1,
};

/**
 * A check that reached the documents but could not read a critical field.
 *
 * The distinction the UI has to keep: this is not evidence that the server
 * changed anything, and the panel must not say it is.
 */
const TECHNOCORE_UNEVALUABLE: TechnocoreStatus = {
  ...TECHNOCORE_CURRENT,
  state: "unavailable",
  manifest_current: false,
  last_success_at: null,
  reasons: [
    "Imza bicimi: sema bicimi okunamadi (desteklenmeyen sema anahtari: $ref); protokol uyumu dogrulanamadi",
  ],
  fields: [
    {
      ...TECHNOCORE_CURRENT.fields[0]!,
      observed: "<yok>",
      matches: false,
      outcome: "unsupported",
      detail: "desteklenmeyen sema anahtari: $ref",
    },
  ],
  critical_mismatch_count: 0,
  critical_unevaluable_count: 1,
};

/** Same verdict, different cause: the field is simply not in the document. */
const TECHNOCORE_FIELD_MISSING: TechnocoreStatus = {
  ...TECHNOCORE_UNEVALUABLE,
  reasons: [
    "Imza bicimi: belgede bulunamadi (/paths/~1r~1{room}/post/...); protokol uyumu dogrulanamadi",
  ],
  fields: [
    {
      ...TECHNOCORE_UNEVALUABLE.fields[0]!,
      outcome: "missing",
      detail: "",
    },
  ],
};

/** A mismatch proved by contradiction rather than by a differing value. */
const TECHNOCORE_CONFLICT: TechnocoreStatus = {
  ...TECHNOCORE_DRIFTED,
  reasons: [
    "DID bicimi: did: uzunluk araligi bos (en az 100, en fazla 56); hicbir deger ikisini birden saglayamaz",
  ],
  fields: [
    {
      ...TECHNOCORE_DRIFTED.fields[0]!,
      observed: "<yok>",
      outcome: "mismatch",
      detail:
        "did: uzunluk araligi bos (en az 100, en fazla 56); hicbir deger ikisini birden saglayamaz",
    },
  ],
};

const NOT_CONFORMANT: ConformanceStatus = {
  ...CONFORMANT,
  passed: false,
  checks: CONFORMANT.checks.map((check) =>
    check.name === "sweep" ? { ...check, passed: false } : check,
  ),
  failures: ["sweep: vector ascii-plain swept differently"],
  capabilities: CONFORMANT.capabilities.filter((name) => name !== "sweep"),
};

/**
 * The composer capability, derived from the gate in the identity fixture.
 *
 * Deriving it keeps the two from disagreeing: a fixture that said "composing
 * is open" while the gate fixture said "identity missing" would test a state
 * the backend cannot produce.
 */
function capabilityFor(status: IdentityStatus): ComposeCapability {
  return {
    can_compose: status.gate.allowed,
    blocking_reasons: [...status.gate.blocking_reasons],
    write_method: "POST",
    write_path_template: "/r/{room}",
    denied_rooms: ["lobby", "meta"],
    room_class_markers: [],
    max_chars: 4096,
    min_chars: 1,
    draft_ttl_seconds: 180,
    approval_ttl_seconds: 180,
    note_lane_available: false,
    note_lane_detail: "Imzali note gonderimi bu surumde yoktur.",
  };
}

//: TEST-ONLY evidence ledger fixture: the honest first-use state. The record
//: view has its own suite (`EvidenceLedgerPanel.test.tsx`); these page-level
//: tests only need the section to render without inventing anything.
const EMPTY_LEDGER: EvidenceList = {
  records: [],
  record_count: 0,
  chain_state: "empty",
  chain_detail: "Henuz audit satiri yok.",
  chain_link_count: 0,
};

//: TEST-ONLY audit verdict. `claim` is the backend's own sentence and is the
//: only description of the chain the UI is allowed to show.
const AUDIT_EMPTY: AuditChainStatus = {
  state: "empty",
  detail: "Henuz audit satiri yok.",
  link_count: 0,
  head_count: 0,
  first_bad_seq: null,
  claim:
    "Audit zinciri cevrimdisi degisiklige karsi tespit edicidir. Ayni Windows kullanicisi olarak calisan bir saldirgana, guvenilir bir zamana veya ucuncu bir tarafa ispata karsilik gelmez.",
};

/**
 * Route the stub by URL.
 *
 * The pages read seven endpoints between them. A stub that answered every
 * request with the identity payload would make the other panels render from
 * the wrong shape and quietly pass.
 */
//: TEST-ONLY OpenCode fixture. No key is configured, so the settings screen
//: renders its one masked field and the narrowed promise can be asserted.
const OPENCODE_UNCONFIGURED: OpenCodeStatus = {
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
    listing_caveat:
      "Bu liste saglayicinin acik katalogudur ve anahtarsiz da yanit verir. Bir modelin listelenmesi, bu hesabin onu cagirabildigi anlamina gelmez.",
  },
  spending: {
    budget_available: false,
    limits: [{ window: "hafta", amount_usd: 30, note: "Haftalik yayimlanmis ust sinir." }],
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
      "Akis (streaming) ve arac cagrisi bu surumde yoktur: resmi belgede bu iki bicimin sozlesmesi yayimlanmamis, tahmin edilmemistir.",
    shape_provenance:
      "Uc protokol ailesinin govde bicimi OpenCode belgelerinde yayimlanmis degildir.",
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

function stubIdentity(
  status: IdentityStatus,
  conformance: ConformanceStatus | null = CONFORMANT,
  technocore: TechnocoreStatus = TECHNOCORE_NEVER_CHECKED,
): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      // Each shape carries its URL differently; stringifying a Request would
      // yield "[object Object]" and route every call to the identity branch.
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;

      if (url.includes("/api/evidence/records")) {
        return Promise.resolve(
          new Response(JSON.stringify(EMPTY_LEDGER), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("/api/evidence/audit")) {
        return Promise.resolve(
          new Response(JSON.stringify(AUDIT_EMPTY), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("/api/compose/capability")) {
        return Promise.resolve(
          new Response(JSON.stringify(capabilityFor(status)), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("/api/technocore/")) {
        return Promise.resolve(
          new Response(JSON.stringify(technocore), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("/api/opencode/")) {
        return jsonOk(OPENCODE_UNCONFIGURED);
      }

      if (url.includes("/api/write-gate")) {
        return Promise.resolve(
          new Response(JSON.stringify(status.gate), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("/api/conformance/status")) {
        if (conformance === null) {
          return Promise.resolve(new Response("nope", { status: 500 }));
        }
        return Promise.resolve(
          new Response(JSON.stringify(conformance), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("/api/session/bootstrap")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              csrf_token: "test-only-value-not-a-real-token",
              csrf_header: "X-Station-CSRF",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      return Promise.resolve(
        new Response(JSON.stringify(status), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetSessionState();
});

describe("Identity surface", () => {
  it("shows an honest empty state instead of a placeholder identity", async () => {
    stubIdentity(NO_IDENTITY);
    render(<IdentityPage />);
    expect(await screen.findByText("Kimlik olusturulmadi")).toBeInTheDocument();
  });

  it("has no secret or private key input field", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
  });

  it("never renders a seed value, even when an identity exists", async () => {
    stubIdentity(READY);
    const { container } = render(<IdentityPage />);
    await screen.findByText(/did:key:z6Mk/);

    // A seed is 32 bytes written as 64 hex characters. The page may *mention*
    // the word "seed" in its reassurance copy - that text is the point - but no
    // 64-hex run may ever be rendered.
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b[0-9a-fA-F]{64}\b/);

    // The raw public key is also not rendered; only the short fingerprint is.
    expect(text).not.toContain(READY.identity!.public_key);
    expect(text).not.toContain(READY.identity!.fingerprint);
  });

  it("shows the public DID with a copy action", async () => {
    stubIdentity(READY);
    render(<IdentityPage />);
    expect(await screen.findByText(READY.identity!.did)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Public DID degerini kopyala/ }),
    ).toBeInTheDocument();
  });

  it("reports recovery as verified once the restore test has run", async () => {
    stubIdentity(READY);
    render(<IdentityPage />);
    expect(await screen.findByText("Dogrulandi")).toBeInTheDocument();
  });

  it("offers the next safe action rather than every action at once", async () => {
    stubIdentity(NO_IDENTITY);
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    expect(screen.getByRole("button", { name: "Yeni kimlik olustur" })).toBeInTheDocument();
    // Export and restore-test are meaningless before an identity exists.
    expect(screen.queryByRole("button", { name: "Restore-test yap" })).toBeNull();
  });

  it("shows blocked requirements as blocked, not as a future stage", async () => {
    // The stage badge exists only for requirements that are not built yet.
    // A blocked check is something the user can act on, not something to
    // wait for; no badge may claim a stage that does not match the text
    // beside it.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    const text = container.textContent ?? "";
    expect(text).not.toContain("Asama 4");
    // Blocked preconditions read as closed, which is actionable.
    expect(screen.getAllByText("Kapali").length).toBeGreaterThan(0);
  });

  it("shows the conformance verdict from the backend, not a hardcoded one", async () => {
    stubIdentity(NO_IDENTITY);
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    expect(await screen.findByText("Asama 2B · Hazir")).toBeInTheDocument();
    expect(screen.getByText("7707cb6")).toBeInTheDocument();
    expect(screen.getByText("688c6e4dcf14")).toBeInTheDocument();
    expect(screen.getByText("15.0.0")).toBeInTheDocument();
    expect(screen.getByText("3.12.11")).toBeInTheDocument();
  });

  it("names each verified capability with its vector count", async () => {
    stubIdentity(NO_IDENTITY);
    render(<IdentityPage />);
    await screen.findByText("Asama 2B · Hazir");

    for (const label of ["Sweep (32)", "Canonical (15)", "Imzalama (15)", "Dogrulama (15)"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("ignores a check name that only exists on the prototype chain", async () => {
    // Regression: `name in CAPABILITY_LABELS` also matched inherited keys, so
    // a check called "toString" would have resolved to a function and been
    // rendered as a label.
    stubIdentity(NO_IDENTITY, {
      ...CONFORMANT,
      checks: [
        ...CONFORMANT.checks,
        { name: "toString", passed: true, vectors: 1, detail: "prototype key" },
      ],
    });
    const { container } = render(<IdentityPage />);
    await screen.findByText("Asama 2B · Hazir");

    expect(container.textContent ?? "").not.toContain("function");
    expect(screen.queryByText(/toString/)).toBeNull();
  });

  it("reports a failed self-test as failed, never as unknown", async () => {
    stubIdentity(NO_IDENTITY, NOT_CONFORMANT);
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    expect(await screen.findByText("Asama 2B · Basarisiz")).toBeInTheDocument();
    expect(
      screen.getByText("sweep: vector ascii-plain swept differently"),
    ).toBeInTheDocument();
  });

  it("shows an error region, not a fake verdict, when conformance cannot be read", async () => {
    stubIdentity(NO_IDENTITY, null);
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    // The failed read is a finding of its own: a persistent alert with a
    // retry, never a silent "still loading" or an invented verdict.
    expect(await screen.findByText("Uygunluk durumu okunamadi")).toBeInTheDocument();
    expect(screen.queryByText("Asama 2B · Hazir")).toBeNull();
    expect(screen.getAllByRole("button", { name: "Yeniden dene" }).length).toBeGreaterThan(0);
  });

  it("never renders the full vector bundle digest", async () => {
    // A SHA-256 and a seed are both 64 hex characters. The panel shows the
    // short form so the surface-wide "no 64-hex run" rule keeps its teeth.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<IdentityPage />);
    await screen.findByText("Asama 2B · Hazir");

    expect(container.textContent ?? "").not.toMatch(/\b[0-9a-fA-F]{64}\b/);
  });

  it("separates conformance with the pinned reference from server currency", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<IdentityPage />);
    await screen.findByText("Asama 2B · Hazir");

    const text = container.textContent ?? "";
    expect(text).toContain("pinlenmis referans commit");
    expect(text).toContain("gostermez");
  });

  it("surfaces a capability error and blocks creation", async () => {
    stubIdentity({
      ...NO_IDENTITY,
      state: "capability_error",
      capability: {
        platform_supported: false,
        dpapi_available: false,
        aead_available: true,
        usable: false,
        detail: "Bu surum yalniz Windows uzerinde calisir (DPAPI gerekli).",
      },
    });
    render(<IdentityPage />);

    expect(await screen.findByText("Secret kasasi kullanilamiyor")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yeni kimlik olustur" })).toBeDisabled();
  });
});

describe("Create identity dialog", () => {
  it("requires the exact confirmation text before enabling creation", async () => {
    stubIdentity(NO_IDENTITY);
    const user = userEvent.setup();
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    await user.click(screen.getByRole("button", { name: "Yeni kimlik olustur" }));

    const submit = await screen.findByRole("button", { name: "Kimligi olustur" });
    expect(submit).toBeDisabled();

    // Passphrase alone is not enough; the confirmation text is also required.
    const passphrases = screen.getAllByLabelText(/Kasa parolasi/);
    await user.type(passphrases[0]!, "TEST-ONLY-passphrase-01");
    await user.type(passphrases[1]!, "TEST-ONLY-passphrase-01");
    expect(submit).toBeDisabled();
  });

  it("states plainly that a DID is not a wallet or a claim", async () => {
    stubIdentity(NO_IDENTITY);
    const user = userEvent.setup();
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    await user.click(screen.getByRole("button", { name: "Yeni kimlik olustur" }));
    expect(await screen.findByText("Bu bir cuzdan adresi degildir")).toBeInTheDocument();
  });

  it("clears passphrase state when the dialog closes", async () => {
    stubIdentity(NO_IDENTITY);
    const user = userEvent.setup();
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    await user.click(screen.getByRole("button", { name: "Yeni kimlik olustur" }));
    const first = (await screen.findAllByLabelText(/Kasa parolasi/))[0]!;
    await user.type(first, "TEST-ONLY-passphrase-01");
    expect(first).toHaveValue("TEST-ONLY-passphrase-01");

    await user.click(screen.getByRole("button", { name: "Vazgec" }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Kimligi olustur" })).toBeNull();
    });

    await user.click(screen.getByRole("button", { name: "Yeni kimlik olustur" }));
    const reopened = (await screen.findAllByLabelText(/Kasa parolasi/))[0]!;
    expect(reopened).toHaveValue("");
  });
});

describe("Identity dialog error surfaces", () => {
  //: TEST-ONLY request id: 32 lower-case hex characters, like the header.
  const REQUEST_ID = "00112233445566778899aabbccddeeff";

  function bootstrapResponse(): Response {
    return new Response(
      JSON.stringify({
        csrf_token: "test-only-value-not-a-real-token",
        csrf_header: "X-Station-CSRF",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }

  it("carries the code, HTTP status and request id when creation fails", async () => {
    // The help screen tells the user to send the "copy diagnostics" output.
    // These dialogs used to print a bare sentence, so exactly where support
    // is most needed there was no code, no request id and nothing to copy.
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("/api/session/bootstrap")) return Promise.resolve(bootstrapResponse());
        if (url.includes("/api/conformance/status")) {
          return Promise.resolve(
            new Response(JSON.stringify(CONFORMANT), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
        if (init?.method === "POST") {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: "vault_locked" }), {
              status: 500,
              headers: {
                "Content-Type": "application/json",
                "X-Station-Request-Id": REQUEST_ID,
              },
            }),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify(NO_IDENTITY), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }),
    );

    await bootstrapSession();
    const user = userEvent.setup();
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    await user.click(screen.getByRole("button", { name: "Yeni kimlik olustur" }));
    const passphrases = await screen.findAllByLabelText(/Kasa parolasi/);
    await user.type(passphrases[0]!, "TEST-ONLY-passphrase-01");
    await user.type(passphrases[1]!, "TEST-ONLY-passphrase-01");
    await user.type(
      screen.getByLabelText(/Onaylamak icin tam olarak/),
      NO_IDENTITY.create_confirmation_text,
    );
    await user.click(screen.getByRole("button", { name: "Kimligi olustur" }));

    expect(await screen.findByText("Kimlik olusturulamadi")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).toContain("Kod: vault_locked");
    expect(text).toContain("HTTP: 500");
    expect(text).toContain(`Istek: ${REQUEST_ID}`);
    expect(
      screen.getByRole("button", { name: "Tani bilgisini kopyala" }),
    ).toBeInTheDocument();
    // A mutation is not re-fired from an alert; the user resubmits instead.
    expect(screen.queryByRole("button", { name: "Yeniden dene" })).toBeNull();
  });

  it("never shows a raw JavaScript message when a non-ApiError escapes", async () => {
    // `URL.createObjectURL` throwing a TypeError is a real path in the export
    // dialog. The old helper fell through to `error.message`, which would put
    // an internal engine string in front of the user.
    stubIdentity(READY);
    await bootstrapSession();

    const original = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: () => {
        throw new TypeError("TEST-ONLY-RAW-INTERNAL-DETAIL");
      },
    });

    try {
      const user = userEvent.setup();
      render(<IdentityPage />);
      await screen.findByText(/did:key:z6Mk/);

      await user.click(screen.getByRole("button", { name: "Recovery dosyasi olustur" }));
      const fields = await screen.findAllByLabelText(/Recovery parolasi/);
      await user.type(fields[0]!, "TEST-ONLY-recovery-passphrase-01");
      await user.type(fields[1]!, "TEST-ONLY-recovery-passphrase-01");
      await user.click(screen.getByRole("button", { name: "Recovery dosyasini indir" }));

      expect(await screen.findByText("Recovery olusturulamadi")).toBeInTheDocument();
      const text = document.body.textContent ?? "";
      expect(text).not.toContain("TEST-ONLY-RAW-INTERNAL-DETAIL");
      expect(text).toContain("Kod: unexpected_error");
      expect(text).toContain("Istek tamamlanamadi.");
    } finally {
      if (original !== undefined) {
        Object.defineProperty(URL, "createObjectURL", original);
      } else {
        Reflect.deleteProperty(URL, "createObjectURL");
      }
    }
  });
});

describe("Compose and Verify surface", () => {
  it("stays locked and reflects the real write gate", async () => {
    stubIdentity(NO_IDENTITY);
    render(<ComposeVerifyPage />);

    // The lock is no longer a fixed sentence on the page: it is the backend's
    // own capability verdict, and the preconditions beneath it are the gate.
    expect(await screen.findByText("Gonderim kapali")).toBeInTheDocument();
    expect(
      await screen.findByText("Recovery restore-test ile dogrulanmis olmali"),
    ).toBeInTheDocument();
  });

  it("offers no compose field and no send control while locked", async () => {
    // Package D opened the write path, so this assertion matters more than it
    // did while the whole surface was a placeholder: with the gate shut there
    // must still be nothing to type into and nothing to press.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Gonderim kapali");

    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(container.querySelectorAll("input")).toHaveLength(0);
    expect(container.querySelectorAll("button")).toHaveLength(0);
    for (const name of ["Taslagi hazirla", "Imzala", "Onayla ve gonder"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
  });

  it("names the blocking preconditions instead of showing an inert form", async () => {
    // A disabled button explains nothing. The closed door is stated, with the
    // backend's own reasons behind it.
    stubIdentity(NO_IDENTITY);
    render(<ComposeVerifyPage />);
    await screen.findByText("Gonderim kapali");

    // The bullet is the capability's own blocking reason, rendered beside the
    // precondition list rather than instead of it.
    expect(screen.getByText("• Kimlik olusturulmus olmali")).toBeInTheDocument();
    expect(screen.getByText(/Devre disi bir buton/)).toBeInTheDocument();
  });

  it("shows a persistent error region when the gate cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    render(<ComposeVerifyPage />);

    expect(await screen.findByText("Kapi durumu okunamadi")).toBeInTheDocument();
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Yeniden dene" })).toBeInTheDocument();
  });

  it("never shows an unmet requirement as passed", async () => {
    stubIdentity(NO_IDENTITY);
    render(<ComposeVerifyPage />);
    await screen.findByText("Gonderim kapali");

    // Every check is real, so unmet ones read as waiting rather than as a
    // future stage. What must never happen is one reading "Tamam".
    const waiting = await screen.findAllByText("Bekliyor");
    expect(waiting.length).toBeGreaterThan(0);
  });

  it("stays locked even though conformance now passes", async () => {
    // Building the conformance engine does not open the outward door,
    // because drift detection still has to pass in this session.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Gonderim kapali");

    expect(screen.getByText("Tamam")).toBeInTheDocument();
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(container.querySelectorAll("button")).toHaveLength(0);
    expect(screen.getByText("• Resmi manifest kontrolu kurulmus olmali")).toBeInTheDocument();
  });

  it("separates conformance with the pinned reference from server currency", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Gonderim kapali");

    const text = container.textContent ?? "";
    expect(text).toContain("pinlenmis referans commit");
    expect(text).toContain("Canli Technocore sunucusunun hala");
  });

  it("states that signing is not sending, gate open or shut", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Gonderim kapali");

    expect(screen.getByText("Otomatik gonderim yoktur")).toBeInTheDocument();
    expect(container.textContent).toContain("imza onayi gonderim onayi degildir");
  });

  it("labels each unbuilt requirement with the stage that delivers it", async () => {
    // Regression: both badges used to read "Asama 4" while the text beside
    // them said 2B and 3. The badge and the explanation must agree.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Gonderim kapali");

    expect(container.textContent).not.toContain("Asama 4");
  });
});

/**
 * The six phrases `station_api.evidence.language` refuses to let out of the
 * backend, folded the way that module folds them.
 *
 * Folding matters: the charter spells these with Turkish letters and the UI
 * writes diacritic-free Turkish, so "Sunucu Kanıtı" and "sunucu kaniti" are
 * the same claim in two spellings. A test that checked only one of them would
 * be a test anybody could pass by accident.
 */
const FORBIDDEN_CLAIMS = [
  "sunucu kaniti",
  "degismez kayit",
  "guvenilir zaman kaniti",
  "airdrop uygunluk kaniti",
  // Package E added these two: the same over-claim, about truncation.
  "degistirilemez kayit",
  "kurcalanamaz kayit",
] as const;

/** Case-fold, strip diacritics and map the dotless i, like the backend. */
function fold(text: string): string {
  return text
    .toLocaleLowerCase("tr")
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .replace(/ı/g, "i")
    .replace(/\s+/g, " ");
}

describe("Kanitlar surface", () => {
  it("shows an honest empty state instead of naming a future package", async () => {
    // Package E is this package. The old copy promised the ledger would
    // "arrive with Paket E", and updating it is the fix, not a loosening
    // (ADR-0003 10.5).
    stubIdentity(NO_IDENTITY);
    const { container } = render(<EvidencePage />);

    expect(await screen.findByText("Henuz kanit kaydi yok")).toBeInTheDocument();
    expect(container.textContent).not.toContain("Paket E");
    expect(container.textContent).toContain("kullanici onayli bir gonderim");
  });

  it("declares level 4 as absent rather than implying it exists", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<EvidencePage />);
    await screen.findByText("Henuz kanit kaydi yok");

    expect(container.textContent).toContain("Harici anchor");
    expect(container.textContent).toContain("MVP kapsaminda yoktur");
  });

  it("uses no forbidden over-claiming evidence language", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<EvidencePage />);
    await screen.findByText("Henuz kanit kaydi yok");

    const text = fold(container.textContent ?? "");
    for (const claim of FORBIDDEN_CLAIMS) {
      expect(text).not.toContain(claim);
    }
    // And the one sentence that *is* permitted about the chain is present.
    expect(text).toContain("cevrimdisi degisiklige karsi tespit edici");
  });

  it("carries the trust levels but not the official-source panel", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<EvidencePage />);
    await screen.findByText("Henuz kanit kaydi yok");

    expect(screen.getByText("Guven seviyeleri")).toBeInTheDocument();
    // Document access and drift moved to the Kaynaklar section.
    expect(container.textContent).not.toContain("Salt okunur baglanti durumu");
    expect(container.textContent).not.toContain("Belge erisimi");
  });

  it("presents the level list as a definition, not as a verdict", async () => {
    // The static list used to be the only thing on the page, so it read as a
    // status. Now that records carry their own levels, it has to say which of
    // the two it is.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<EvidencePage />);
    await screen.findByText("Henuz kanit kaydi yok");

    expect(container.textContent).toContain("bir kaydin durumu degildir");
    expect(container.textContent).toContain("tek bir rozete toplanmaz");
  });
});

describe("Kaynaklar surface", () => {
  it("carries the official-source panel but not the trust levels", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<SourcesPage />);
    await screen.findByText("Henuz denetlenmedi");

    expect(screen.getByText("Salt okunur baglanti durumu")).toBeInTheDocument();
    expect(container.textContent).not.toContain("Guven seviyeleri");
  });
});

describe("every surface", () => {
  it("renders no external link", () => {
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_CURRENT);
    const noNavigate = () => {};
    const surfaces = [
      <IdentityPage key="identity" />,
      <ComposeVerifyPage key="compose" />,
      <EvidencePage key="evidence" />,
      <SourcesPage key="sources" />,
      <OverviewPage key="overview" loading={false} onNavigate={noNavigate} status={APP_STATUS} />,
      <SettingsHelpPage key="settings" status={APP_STATUS} />,
    ];
    for (const surface of surfaces) {
      const { container, unmount } = render(surface);
      expect(container.querySelectorAll('a[href^="http"]')).toHaveLength(0);
      unmount();
    }
  });
});

describe("Read-only Technocore monitoring", () => {
  it("starts as not yet checked and offers an explicit user action", async () => {
    stubIdentity(NO_IDENTITY);
    render(<SourcesPage />);

    expect(await screen.findByText("Henuz denetlenmedi")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Resmi kaynaklari denetle" }),
    ).toBeInTheDocument();
  });

  it("shows official source metadata after a check", async () => {
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_CURRENT);
    render(<SourcesPage />);

    expect(await screen.findByText("Guncel")).toBeInTheDocument();
    expect(
      screen.getByText("https://technocore.chat/openapi.json"),
    ).toBeInTheDocument();
    expect(screen.getByText("aabbccdd1122")).toBeInTheDocument();
    expect(
      screen.getByText("Seviye 1 · makine-okunabilir resmi belge"),
    ).toBeInTheDocument();
  });

  it("never turns a remote URL into a clickable link", async () => {
    // AC-17: Technocore data is never active content.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_CURRENT);
    const { container } = render(<SourcesPage />);
    await screen.findByText("Guncel");

    expect(container.querySelectorAll("a")).toHaveLength(0);
    expect(container.innerHTML).not.toContain("<iframe");
    expect(container.innerHTML).not.toContain("<script");
    expect(
      screen.getByRole("button", { name: /adresini kopyala/ }),
    ).toBeInTheDocument();
  });

  it("separates a critical drift from a non-critical warning", async () => {
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_DRIFTED);
    render(<SourcesPage />);

    expect(await screen.findByText("Suruklenme tespit edildi")).toBeInTheDocument();
    expect(screen.getByText("Kritik protokol suruklenmesi")).toBeInTheDocument();
    expect(screen.getByText("Kritik")).toBeInTheDocument();
  });

  it("does not print a missing-value marker for a demonstrated contradiction", async () => {
    // A conflict is a mismatch with no single observed value behind it.
    // Showing the reader's `<yok>` would say "the field is missing", which is
    // a different finding; the explanation belongs in the detail line.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_CONFLICT);
    const { container } = render(<SourcesPage />);
    await screen.findByText("Suruklenme tespit edildi");

    expect(screen.getByText("sema kendisiyle celisiyor")).toBeInTheDocument();
    expect(screen.getByText(/^Celiski: /)).toBeInTheDocument();
    expect(container.textContent ?? "").not.toContain("<yok>");
  });

  it("distinguishes a missing field from an unreadable schema", async () => {
    // Both mean "not compared", but they send a reader to different places:
    // one says the document does not carry the field, the other says it
    // carries a shape this build cannot read.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_FIELD_MISSING);
    render(<SourcesPage />);
    await screen.findByText("Protokol uyumu dogrulanamadi");

    expect(screen.getByText("Bulunamadi")).toBeInTheDocument();
    expect(screen.getByText("belgede bulunamadi")).toBeInTheDocument();
    expect(screen.queryByText("sema okunamadi")).not.toBeInTheDocument();
  });

  it("does not call an unreadable field a change the server made", async () => {
    // A critical field that could not be read must be reported as
    // unverified - not as "the server changed the signature format", which
    // the panel used to say on exactly this input.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_UNEVALUABLE);
    const { container } = render(<SourcesPage />);

    expect(await screen.findByText("Protokol uyumu dogrulanamadi")).toBeInTheDocument();
    expect(screen.getByText("Okunamadi")).toBeInTheDocument();
    expect(
      screen.getByText(/desteklenmeyen sema anahtari/),
    ).toBeInTheDocument();

    const text = (container.textContent ?? "").toLowerCase();
    expect(text).not.toContain("kritik protokol suruklenmesi");
    expect(text).not.toContain("degismis");
  });

  it("reports document access separately from the protocol verdict", async () => {
    // Two independent questions. A fetched document does not yet mean the
    // protocol matches, and an unreadable schema is not a network problem.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_UNEVALUABLE);
    render(<SourcesPage />);
    await screen.findByText("Protokol uyumu dogrulanamadi");

    expect(screen.getByText("1. Belge erisimi")).toBeInTheDocument();
    expect(screen.getByText("1/1 resmi belge alindi.")).toBeInTheDocument();
    expect(screen.getByText("2. Protokol degerlendirmesi")).toBeInTheDocument();
  });

  it("shows the real signed-lane pointer, not the properties one", async () => {
    // The wrong pointer is what produced the false alarm; the UI shows where
    // the value was actually looked for, so the claim is checkable by hand.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_DRIFTED);
    render(<SourcesPage />);
    await screen.findByText("Suruklenme tespit edildi");

    expect(screen.getByText(/dependentSchemas/)).toBeInTheDocument();
    expect(screen.getByText("^[A-Za-z0-9_-]{85}[AQgw]$")).toBeInTheDocument();
  });

  it("states plainly that the check only reads", async () => {
    stubIdentity(NO_IDENTITY);
    render(<SourcesPage />);
    await screen.findByText("Henuz denetlenmedi");

    expect(screen.getByText("Bu denetim yalniz okur")).toBeInTheDocument();
  });

  it("makes no airdrop or eligibility claim on either surface", async () => {
    // AC-18 forbids *making* a claim, not naming one. The evidence page
    // carries an explicit disclaimer; neither surface may carry a claim.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_CURRENT);
    const sources = render(<SourcesPage />);
    await screen.findByText("Guncel");
    const sourcesText = (sources.container.textContent ?? "").toLowerCase();
    sources.unmount();

    const evidence = render(<EvidencePage />);
    const evidenceText = (evidence.container.textContent ?? "").toLowerCase();
    expect(evidenceText).toContain("hicbir airdrop garantisi");

    for (const claim of [
      "airdrop kazandiniz",
      "uygunlugunuz onaylandi",
      "tahsis edildi",
      "hak kazandiniz",
    ]) {
      expect(sourcesText).not.toContain(claim);
      expect(evidenceText).not.toContain(claim);
    }
  });

  it("disables the check button while a check is in flight", async () => {
    // Double-activation protection: the outbound check is an explicit user
    // action and a second click must not start a second request.
    let refreshCalls = 0;
    let releaseRefresh: (response: Response) => void = () => {};
    const pendingRefresh = new Promise<Response>((resolve) => {
      releaseRefresh = resolve;
    });

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url =
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("/api/session/bootstrap")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                csrf_token: "test-only-value-not-a-real-token",
                csrf_header: "X-Station-CSRF",
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        if (url.includes("/api/technocore/refresh")) {
          refreshCalls += 1;
          return pendingRefresh;
        }
        return Promise.resolve(
          new Response(JSON.stringify(TECHNOCORE_NEVER_CHECKED), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }),
    );

    await bootstrapSession();
    const user = userEvent.setup();
    render(<SourcesPage />);
    await screen.findByText("Henuz denetlenmedi");

    await user.click(screen.getByRole("button", { name: "Resmi kaynaklari denetle" }));

    const busyButton = await screen.findByRole("button", { name: "Denetleniyor..." });
    expect(busyButton).toBeDisabled();

    // A second activation while pending must be inert.
    fireEvent.click(busyButton);
    expect(refreshCalls).toBe(1);

    releaseRefresh(
      new Response(JSON.stringify(TECHNOCORE_CURRENT), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(await screen.findByText("Guncel")).toBeInTheDocument();
  });
});

describe("Identity next-step guidance", () => {
  function readyWith(conformance: string, manifest: string): IdentityStatus {
    return {
      ...READY,
      gate: {
        ...READY.gate,
        allowed: conformance === "passed" && manifest === "passed",
        checks: [
          { key: "conformance_verified", state: conformance, detail: "", stage: "2B" },
          { key: "manifest_current", state: manifest, detail: "", stage: "3" },
        ],
      },
    } as IdentityStatus;
  }

  it("points at Stage 2B when conformance fails", async () => {
    stubIdentity(readyWith("blocked", "blocked"));
    render(<IdentityPage />);
    expect(
      await screen.findByText(/Asama 2B motorunu inceleyin/),
    ).toBeInTheDocument();
  });

  it("points at the source check when the manifest is unverified", async () => {
    stubIdentity(readyWith("passed", "blocked"));
    render(<IdentityPage />);
    expect(
      await screen.findByText(/Resmi kaynaklar bu oturumda henuz dogrulanmadi/),
    ).toBeInTheDocument();
  });

  it("names the Kaynaklar section, not the retired Evidence tab", async () => {
    stubIdentity(readyWith("passed", "blocked"));
    const { container } = render(<IdentityPage />);
    await screen.findByText(/Resmi kaynaklar bu oturumda henuz dogrulanmadi/);
    expect(container.textContent).toContain("Kaynaklar bolumunden");
  });

  it("points at Stage 4 once every precondition is met", async () => {
    stubIdentity(readyWith("passed", "passed"));
    render(<IdentityPage />);
    expect(await screen.findByText(/Asama 4/)).toBeInTheDocument();
  });

  it("no longer claims Stage 2B is next", async () => {
    stubIdentity(readyWith("passed", "passed"));
    const { container } = render(<IdentityPage />);
    await screen.findByText(/Asama 4/);
    expect(container.textContent).not.toContain("Sonraki adim Asama 2B");
  });
});

describe("Genel Bakis surface", () => {
  it("composes identity, Technocore, conformance and service health", async () => {
    stubIdentity(READY, CONFORMANT, TECHNOCORE_CURRENT);
    render(
      <OverviewPage loading={false} onNavigate={() => {}} status={APP_STATUS} />,
    );

    // Identity summary with the shared next-step guidance.
    expect(await screen.findByText(/Sonraki guvenli adim/)).toBeInTheDocument();
    // Technocore drift state and last check time.
    expect(screen.getByText("Guncel")).toBeInTheDocument();
    expect(screen.getByText("Son basarili kontrol")).toBeInTheDocument();
    // Conformance summary.
    expect(screen.getByText(/Self-test gecti: 104 vektor/)).toBeInTheDocument();
    // Service health cards.
    expect(screen.getByText("Yerel servis")).toBeInTheDocument();
    expect(screen.getByText("Oturum guvenligi")).toBeInTheDocument();
  });

  it("shows summaries only: no hash runs and no source detail", async () => {
    stubIdentity(READY, CONFORMANT, TECHNOCORE_CURRENT);
    const { container } = render(
      <OverviewPage loading={false} onNavigate={() => {}} status={APP_STATUS} />,
    );
    await screen.findByText(/Sonraki guvenli adim/);

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b[0-9a-fA-F]{64}\b/);
    // The per-source hash list stays in the Kaynaklar section.
    expect(text).not.toContain("aabbccdd1122");
    expect(text).not.toContain(READY.identity!.did);
  });

  it("offers a go-to-section action on every summary card", async () => {
    stubIdentity(READY, CONFORMANT, TECHNOCORE_CURRENT);
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<OverviewPage loading={false} onNavigate={onNavigate} status={APP_STATUS} />);
    await screen.findByText(/Sonraki guvenli adim/);

    await user.click(screen.getByRole("button", { name: "Kaynaklar bolumune git" }));
    expect(onNavigate).toHaveBeenCalledWith("sources");

    await user.click(
      screen.getAllByRole("button", { name: "Kimlik ve Guvenlik bolumune git" })[0]!,
    );
    expect(onNavigate).toHaveBeenCalledWith("identity");
  });

  it("designs the first-use state instead of faking data", async () => {
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_NEVER_CHECKED);
    render(
      <OverviewPage loading={false} onNavigate={() => {}} status={APP_STATUS} />,
    );

    expect(await screen.findByText("Kimlik yok")).toBeInTheDocument();
    expect(screen.getByText("Henuz denetlenmedi")).toBeInTheDocument();
    expect(
      screen.getByText(/Station kendiliginden hicbir istek gondermez/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Yeni bir kimlik olusturun veya mevcut bir recovery/),
    ).toBeInTheDocument();
  });

  it("shows each failed summary as its own persistent error with retry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    render(<OverviewPage loading={false} onNavigate={() => {}} status={null} />);

    expect(await screen.findByText("Kimlik ozeti okunamadi")).toBeInTheDocument();
    expect(screen.getByText("Technocore ozeti okunamadi")).toBeInTheDocument();
    expect(screen.getByText("Uygunluk ozeti okunamadi")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Yeniden dene" }).length).toBe(3);
  });
});

describe("Restore-test file picker", () => {
  async function openRestoreDialog(): Promise<ReturnType<typeof render>> {
    const user = userEvent.setup();
    const view = render(<IdentityPage />);
    await screen.findByText(/did:key:z6Mk/);
    await user.click(screen.getByRole("button", { name: "Restore-test yap" }));
    await screen.findByText(/Henuz dosya secilmedi/);
    return view;
  }

  it("shows a labelled dropzone with explanatory text before a file is chosen", async () => {
    stubIdentity(READY);
    await openRestoreDialog();

    expect(screen.getByTestId("recovery-dropzone")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Recovery dosyasi (.tcrec)" }),
    ).toBeInTheDocument();
  });

  it("keeps the native input out of the tab order and filtered to .tcrec", async () => {
    stubIdentity(READY);
    await openRestoreDialog();

    // The dialog renders in a portal, so it is outside the render container.
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    expect(input?.accept).toContain(".tcrec");
    // One keyboard stop, not two: the button carries the accessible name.
    expect(input?.tabIndex).toBe(-1);
  });

  it("reports the chosen file and offers to change it", async () => {
    stubIdentity(READY);
    const user = userEvent.setup();
    await openRestoreDialog();

    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    await user.upload(
      input as HTMLInputElement,
      new File(["ciphertext"], "backup.tcrec", { type: "application/octet-stream" }),
    );

    expect(await screen.findByText("backup.tcrec")).toBeInTheDocument();
    expect(screen.getByText("Secildi")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Recovery dosyasi (.tcrec)" }),
    ).toHaveTextContent("Baska dosya sec");
  });

  it("keeps the picker reachable from the keyboard", async () => {
    stubIdentity(READY);
    await openRestoreDialog();

    const picker = screen.getByRole("button", {
      name: "Recovery dosyasi (.tcrec)",
    });
    picker.focus();
    expect(picker).toHaveFocus();
  });

  it("never puts the file contents in the DOM", async () => {
    stubIdentity(READY);
    const user = userEvent.setup();
    await openRestoreDialog();

    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    await user.upload(
      input as HTMLInputElement,
      new File(["SECRET-CIPHERTEXT-BYTES"], "backup.tcrec", {
        type: "application/octet-stream",
      }),
    );
    await screen.findByText("backup.tcrec");

    expect(document.body.innerHTML).not.toContain("SECRET-CIPHERTEXT-BYTES");
  });
});

/**
 * The write gate's own error alert.
 *
 * Needed because the settings screen now has two independent readers - the
 * write gate and the OpenCode connection - and both render an `ErrorRegion`
 * with a "Yeniden dene" button when the network is down. A page-wide query
 * for that button would match either one and silently assert about the wrong
 * component.
 */
async function gateErrorRegion(): Promise<HTMLElement> {
  const title = await screen.findByText("Kapi durumu okunamadi");
  const region = title.closest('[role="alert"]');
  if (region === null) throw new Error("gate error region not found");
  return region as HTMLElement;
}

describe("Ayarlar ve Yardim surface", () => {
  it("hosts the theme control and says the choice is not persisted", async () => {
    stubIdentity(NO_IDENTITY);
    render(<SettingsHelpPage status={APP_STATUS} />);
    await screen.findByText("Guvenlik kapilari");

    expect(screen.getByRole("button", { name: /temaya gec/ })).toBeInTheDocument();
    expect(screen.getByText(/kalici degildir/)).toBeInTheDocument();
  });

  it("shows the application and service facts from the backend status", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<SettingsHelpPage status={APP_STATUS} />);
    await screen.findByText("Guvenlik kapilari");

    const text = container.textContent ?? "";
    expect(text).toContain("loopback-http");
    expect(text).toContain("uretim");
    expect(text).toContain("journal wal");
  });

  it("renders the real write gate from /api/write-gate", async () => {
    stubIdentity(NO_IDENTITY);
    render(<SettingsHelpPage status={APP_STATUS} />);

    expect(await screen.findByText("Dis yazma kapali")).toBeInTheDocument();
    expect(screen.getByText("Aktif bir kimlik gerekli.")).toBeInTheDocument();
    expect(screen.getAllByText("Kapali").length).toBeGreaterThan(0);
  });

  it("shows a persistent error with retry when the gate cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    render(<SettingsHelpPage status={null} />);

    // Scoped to the gate's own alert: the OpenCode panel below fails on the
    // same stubbed rejection and offers its own retry, and a page-wide query
    // would now match both.
    const region = await gateErrorRegion();
    expect(within(region).getByRole("button", { name: "Yeniden dene" })).toBeInTheDocument();
  });

  it("disables the gate retry while the retry is in flight", async () => {
    // This page had no loading state at all, so its retry could be clicked
    // repeatedly and start a request each time.
    // Routed by URL rather than by call ordinal: the OpenCode panel reads its
    // own endpoint on mount, so counting every fetch would count that one too
    // and the assertion would stop being about the gate's retry.
    let gateCalls = 0;
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url =
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("/api/opencode/")) return jsonOk(OPENCODE_UNCONFIGURED);
        gateCalls += 1;
        if (gateCalls === 1) return Promise.reject(new TypeError("Failed to fetch"));
        return gate.then(
          () =>
            new Response(JSON.stringify(NO_IDENTITY.gate), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
        );
      }),
    );

    const user = userEvent.setup();
    render(<SettingsHelpPage status={null} />);

    const region = await gateErrorRegion();
    await user.click(within(region).getByRole("button", { name: "Yeniden dene" }));

    const busy = await within(region).findByRole("button", { name: "Yeniden deneniyor..." });
    expect(busy).toBeDisabled();
    const callsAfterRetry = gateCalls;
    fireEvent.click(busy);
    expect(gateCalls).toBe(callsAfterRetry);

    release();
    expect(await screen.findByText("Dis yazma kapali")).toBeInTheDocument();
  });

  it("is honest about what arrives in later packages", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<SettingsHelpPage status={APP_STATUS} />);
    await screen.findByText("Guvenlik kapilari");

    const text = container.textContent ?? "";
    // The OpenCode row moved from "arrives later" to "is here"; the guide has
    // not, and the copy must not promote it early.
    expect(text).toContain("OpenCode Go baglantisi bu pakette acildi");
    expect(text).toContain("kullanim kilavuzu Paket J'de");
  });

  /**
   * The promise this page makes about secrets, and the one narrow hole in it.
   *
   * This assertion used to be "no password input at all". Paket G opened the
   * OpenCode connection here, so the promise was rewritten in the copy and
   * this test was **narrowed rather than deleted**: the page may contain
   * exactly one masked field, that field must be the provider API key, and
   * every other kind of secret field must still be absent. A weaker version
   * of this test - "at least one password input exists", or no test at all -
   * would let a second one appear without anybody noticing.
   */
  it("permits exactly one masked field, and it is the OpenCode provider key", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<SettingsHelpPage status={APP_STATUS} />);
    await screen.findByText("Guvenlik kapilari");
    await screen.findByText("Baglanti denetimi");

    const masked = container.querySelectorAll('input[type="password"]');
    expect(masked).toHaveLength(1);
    expect(screen.getByLabelText("OpenCode Go API anahtari")).toBe(masked[0]);
    // Not bound to a saved-password autofill, and not offered for generation.
    expect(masked[0]).toHaveAttribute("autocomplete", "off");

    // Still no field for anything the exception does not cover.
    for (const forbidden of [/seed/i, /private key/i, /recovery/i, /kurtarma/i, /kasa parolasi/i]) {
      expect(screen.queryByLabelText(forbidden)).toBeNull();
    }
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
  });

  it("says the exception is only the provider key and covers no seed or recovery", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<SettingsHelpPage status={APP_STATUS} />);
    await screen.findByText("Guvenlik kapilari");

    const text = container.textContent ?? "";
    expect(text).toContain("DID seed");
    expect(text).toContain("hicbir istisna yoktur");
    expect(text).toContain("Tek istisna asagidaki OpenCode Go saglayici API anahtaridir");
    expect(text).toContain("kaydedildikten sonra alandan ve bellekten silinir");
  });

  it("never shows a stored key back, only a fingerprint", async () => {
    stubIdentity(NO_IDENTITY);
    render(<SettingsHelpPage status={APP_STATUS} />);
    await screen.findByText("Baglanti denetimi");

    expect(
      screen.getByText(/Kaydedilmis anahtari gosteren veya kopyalayan bir kontrol/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /anahtari (goster|kopyala)/i })).toBeNull();
  });
});
