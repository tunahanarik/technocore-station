import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ComposeVerifyPage } from "./ComposeVerifyPage";
import { EvidencePage } from "./EvidencePage";
import { IdentityPage } from "./IdentityPage";

/**
 * These assertions encode product rules, not styling:
 * no secret input anywhere, no invented identity, no airdrop claim.
 */
describe("Identity surface", () => {
  it("shows an honest empty state instead of a placeholder identity", () => {
    render(<IdentityPage />);
    expect(screen.getByText("Kimlik olusturulmadi")).toBeInTheDocument();
  });

  it("has no secret or private key input field", () => {
    const { container } = render(<IdentityPage />);
    expect(container.querySelectorAll("input")).toHaveLength(0);
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(container.querySelector('input[type="password"]')).toBeNull();
  });

  it("shows no example or fake DID", () => {
    const { container } = render(<IdentityPage />);
    // A real did:key value starts with "did:key:z". The term appears only as
    // prose here, never as a value that could be mistaken for an identity.
    expect(container.textContent).not.toMatch(/did:key:z/i);
  });
});

describe("Compose and Verify surface", () => {
  it("is locked until identity and conformance are complete", () => {
    render(<ComposeVerifyPage />);
    expect(screen.getByText("Bu yuzey kilitli")).toBeInTheDocument();
  });

  it("offers no compose field and no send control while locked", () => {
    const { container } = render(<ComposeVerifyPage />);
    expect(container.querySelectorAll("textarea")).toHaveLength(0);
    expect(container.querySelectorAll("input")).toHaveLength(0);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  it("names both blocking prerequisites", () => {
    render(<ComposeVerifyPage />);
    expect(screen.getByText("Kimlik ve recovery")).toBeInTheDocument();
    expect(screen.getByText("Uygunluk motoru")).toBeInTheDocument();
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
    for (const Page of [IdentityPage, ComposeVerifyPage, EvidencePage]) {
      const { container, unmount } = render(<Page />);
      expect(container.querySelectorAll('a[href^="http"]')).toHaveLength(0);
      unmount();
    }
  });
});
