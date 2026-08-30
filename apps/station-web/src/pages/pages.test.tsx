import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetSessionState } from "../api/client";
import type { ConformanceStatus, IdentityStatus } from "../api/types";
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
    // Stage 2B: conformance is a real check and passes on a healthy build.
    // Manifest drift is still unbuilt, so the gate stays shut on that alone.
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
        state: "not_implemented",
        detail: "Resmi manifest surukleme kontrolu Asama 3 ile gelir.",
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
): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      // Each shape carries its URL differently; stringifying a Request would
      // yield "[object Object]" and route every call to the identity branch.
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;

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

  it("labels unbuilt gate requirements with the correct stage", async () => {
    // The same badges render on Identity and on Compose & Verify, both driven
    // by check.stage. Regression: both read "Asama 4".
    //
    // Since Stage 2B, conformance is a real check rather than an unbuilt one,
    // so manifest is the only requirement still badged with a stage.
    stubIdentity(NO_IDENTITY);
    const { container } = render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    expect(screen.getByText("Asama 3")).toBeInTheDocument();
    expect(container.textContent).not.toContain("Asama 4");
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

  it("shows unimplemented requirements as a stage, never as passed", async () => {
    stubIdentity(NO_IDENTITY);
    render(<ComposeVerifyPage />);
    await screen.findByText("Bu yuzey kilitli");

    // Manifest drift is the requirement that remains unbuilt.
    expect(await screen.findByText("Asama 3")).toBeInTheDocument();
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
