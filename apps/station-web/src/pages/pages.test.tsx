import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetSessionState } from "../api/client";
import type {
  ConformanceStatus,
  IdentityStatus,
  TechnocoreStatus,
} from "../api/types";
import { ComposeVerifyPage } from "./ComposeVerifyPage";
import { EvidencePage } from "./EvidencePage";
import { IdentityPage } from "./IdentityPage";

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
    // Stage 3: both conformance and manifest are real checks now.
    // Conformance passes on a healthy build; the manifest stays blocked
    // until the user runs a live check in this session.
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
 * Route the stub by URL.
 *
 * The Identity surface now reads two endpoints. A stub that answered every
 * request with the identity payload would make the conformance panel render
 * from the wrong shape and quietly pass.
 */
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

      if (url.includes("/api/technocore/")) {
        return Promise.resolve(
          new Response(JSON.stringify(technocore), {
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
    // Stage 2B made conformance real and Stage 3 made the manifest check
    // real, so nothing is badged with a stage any more - a blocked check is
    // something the user can act on, not something to wait for.
    //
    // The original regression this guards against remains covered: no badge
    // may claim a stage that does not match the text beside it.
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

  it("does not claim conformance when the status cannot be read", async () => {
    stubIdentity(NO_IDENTITY, null);
    render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    expect(await screen.findByText("Uygunluk durumu okunuyor...")).toBeInTheDocument();
    expect(screen.queryByText("Asama 2B · Hazir")).toBeNull();
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

describe("Compose and Verify surface", () => {
  it("stays locked and reflects the real write gate", async () => {
    stubIdentity(NO_IDENTITY);
    render(<ComposeVerifyPage />);

    expect(await screen.findByText("Bu yuzey kilitli")).toBeInTheDocument();
    expect(
      await screen.findByText("Recovery restore-test ile dogrulanmis olmali"),
    ).toBeInTheDocument();
  });

  it("offers no compose field and no send control while locked", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Bu yuzey kilitli");

    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(container.querySelectorAll("input")).toHaveLength(0);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  it("never shows an unmet requirement as passed", async () => {
    stubIdentity(NO_IDENTITY);
    render(<ComposeVerifyPage />);
    await screen.findByText("Bu yuzey kilitli");

    // Every Stage 3 check is real, so unmet ones read as waiting rather than
    // as a future stage. What must never happen is one reading "Tamam".
    const waiting = await screen.findAllByText("Bekliyor");
    expect(waiting.length).toBeGreaterThan(0);
  });

  it("stays locked even though conformance now passes", async () => {
    // The point of the stage: building the conformance engine does not open
    // the outward door, because drift detection is still missing.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Bu yuzey kilitli");

    expect(screen.getByText("Tamam")).toBeInTheDocument();
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  it("separates conformance with the pinned reference from server currency", async () => {
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Bu yuzey kilitli");

    const text = container.textContent ?? "";
    expect(text).toContain("pinlenmis referans commit");
    expect(text).toContain("Canli Technocore sunucusunun hala");
  });

  it("labels each unbuilt requirement with the stage that delivers it", async () => {
    // Regression: both badges used to read "Asama 4" while the text beside
    // them said 2B and 3. The badge and the explanation must agree.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<ComposeVerifyPage />);
    await screen.findByText("Bu yuzey kilitli");

    expect(container.textContent).not.toContain("Asama 4");
  });
});

describe("Evidence and Sources surface", () => {
  it("shows an empty state", () => {
    render(<EvidencePage />);
    expect(screen.getByText("Henuz kanit kaydi yok")).toBeInTheDocument();
  });

  it("declares level 4 as absent rather than implying it exists", () => {
    const { container } = render(<EvidencePage />);
    expect(container.textContent).toContain("Harici anchor");
    expect(container.textContent).toContain("MVP kapsaminda yoktur");
  });

  it("uses no forbidden over-claiming evidence language", () => {
    const { container } = render(<EvidencePage />);
    const text = container.textContent ?? "";
    expect(text).not.toContain("sunucu kaniti");
    expect(text).not.toContain("degismez kayit");
    expect(text).not.toContain("guvenilir zaman kaniti");
    expect(text).not.toContain("airdrop uygunluk");
  });
});

describe("every surface", () => {
  it("renders no external link", () => {
    stubIdentity(NO_IDENTITY);
    for (const Page of [IdentityPage, ComposeVerifyPage, EvidencePage]) {
      const { container, unmount } = render(<Page />);
      expect(container.querySelectorAll('a[href^="http"]')).toHaveLength(0);
      unmount();
    }
  });
});

describe("Read-only Technocore monitoring", () => {
  it("starts as not yet checked and offers an explicit user action", async () => {
    stubIdentity(NO_IDENTITY);
    render(<EvidencePage />);

    expect(await screen.findByText("Henuz denetlenmedi")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Resmi kaynaklari denetle" }),
    ).toBeInTheDocument();
  });

  it("shows official source metadata after a check", async () => {
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_CURRENT);
    render(<EvidencePage />);

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
    const { container } = render(<EvidencePage />);
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
    render(<EvidencePage />);

    expect(await screen.findByText("Suruklenme tespit edildi")).toBeInTheDocument();
    expect(screen.getByText("Kritik protokol suruklenmesi")).toBeInTheDocument();
    expect(screen.getByText("Kritik")).toBeInTheDocument();
  });

  it("distinguishes a missing field from an unreadable schema", async () => {
    // Both mean "not compared", but they send a reader to different places:
    // one says the document does not carry the field, the other says it
    // carries a shape this build cannot read.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_FIELD_MISSING);
    render(<EvidencePage />);
    await screen.findByText("Protokol uyumu dogrulanamadi");

    expect(screen.getByText("Bulunamadi")).toBeInTheDocument();
    expect(screen.getByText("belgede bulunamadi")).toBeInTheDocument();
    expect(screen.queryByText("sema okunamadi")).not.toBeInTheDocument();
  });

  it("does not call an unreadable field a change the server made", async () => {
    // The Stage 3.1 regression, at the UI. A critical field that could not be
    // read must be reported as unverified - not as "the server changed the
    // signature format", which the panel used to say on exactly this input.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_UNEVALUABLE);
    const { container } = render(<EvidencePage />);

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
    render(<EvidencePage />);
    await screen.findByText("Protokol uyumu dogrulanamadi");

    expect(screen.getByText("1. Belge erisimi")).toBeInTheDocument();
    expect(screen.getByText("1/1 resmi belge alindi.")).toBeInTheDocument();
    expect(screen.getByText("2. Protokol degerlendirmesi")).toBeInTheDocument();
  });

  it("shows the real signed-lane pointer, not the properties one", async () => {
    // The wrong pointer is what produced the false alarm; the UI shows where
    // the value was actually looked for, so the claim is checkable by hand.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_DRIFTED);
    render(<EvidencePage />);
    await screen.findByText("Suruklenme tespit edildi");

    expect(screen.getByText(/dependentSchemas/)).toBeInTheDocument();
    expect(screen.getByText("^[A-Za-z0-9_-]{85}[AQgw]$")).toBeInTheDocument();
  });

  it("states plainly that the check only reads", async () => {
    stubIdentity(NO_IDENTITY);
    render(<EvidencePage />);
    await screen.findByText("Henuz denetlenmedi");

    expect(screen.getByText("Bu denetim yalniz okur")).toBeInTheDocument();
  });

  it("makes no airdrop or eligibility claim", async () => {
    // AC-18 forbids *making* a claim, not naming one. The page carries an
    // explicit disclaimer, so a test that banned the word would fail on the
    // very sentence that satisfies the rule.
    stubIdentity(NO_IDENTITY, CONFORMANT, TECHNOCORE_CURRENT);
    const { container } = render(<EvidencePage />);
    await screen.findByText("Guncel");

    const text = (container.textContent ?? "").toLowerCase();
    expect(text).toContain("hicbir airdrop garantisi");
    for (const claim of [
      "airdrop kazandiniz",
      "uygunlugunuz onaylandi",
      "tahsis edildi",
      "hak kazandiniz",
    ]) {
      expect(text).not.toContain(claim);
    }
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
