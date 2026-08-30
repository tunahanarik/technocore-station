import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resetSessionState } from "../api/client";
import type { IdentityStatus } from "../api/types";
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
    blocking_reasons: ["identity_present", "conformance_verified", "manifest_current"],
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
        state: "not_implemented",
        detail: "Sweep/canonical/imza uygunlugu Asama 2B ile gelir.",
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

function stubIdentity(status: IdentityStatus): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(status), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
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
    stubIdentity(NO_IDENTITY);
    const { container } = render(<IdentityPage />);
    await screen.findByText("Kimlik olusturulmadi");

    expect(screen.getByText("Asama 2B")).toBeInTheDocument();
    expect(screen.getByText("Asama 3")).toBeInTheDocument();
    expect(container.textContent).not.toContain("Asama 4");
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

    expect(await screen.findByText("Asama 2B")).toBeInTheDocument();
    expect(screen.getByText("Asama 3")).toBeInTheDocument();
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
