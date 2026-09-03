import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, type ApiErrorKind } from "../api/client";
import { ErrorRegion } from "./ErrorRegion";

//: TEST-ONLY request id: 32 hex characters, like the backend header.
const REQUEST_ID = "00112233445566778899aabbccddeeff";

function stubClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
}

function errorOfKind(kind: ApiErrorKind): ApiError {
  switch (kind) {
    case "timeout":
      return new ApiError(0, "timeout", { kind: "timeout" });
    case "network":
      return new ApiError(0, "network_error", { kind: "network" });
    case "malformed":
      return new ApiError(200, "malformed_response", { kind: "malformed" });
    case "auth":
      return new ApiError(401, "");
    case "rate_limited":
      return new ApiError(429, "");
    case "unavailable":
      return new ApiError(503, "");
    case "server":
      return new ApiError(500, "internal_error", { requestId: REQUEST_ID });
    case "request":
      return new ApiError(400, "");
  }
}

const ALL_KINDS: readonly ApiErrorKind[] = [
  "timeout",
  "network",
  "malformed",
  "auth",
  "rate_limited",
  "unavailable",
  "server",
  "request",
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ErrorRegion", () => {
  it("is a persistent alert region, not a toast", () => {
    render(<ErrorRegion error={errorOfKind("server")} section="Test" />);

    const region = screen.getByRole("alert");
    expect(region).toBeInTheDocument();
    expect(region.textContent).toContain("internal_error");
  });

  it.each(ALL_KINDS.map((kind) => [kind] as const))(
    "renders a human sentence, the stable code and the status for kind %s",
    (kind) => {
      const error = errorOfKind(kind);
      const { container } = render(<ErrorRegion error={error} section="Test" />);

      const text = container.textContent ?? "";
      expect(text).toContain(error.userMessage);
      expect(text).toContain(`Kod: ${error.code}`);
      // A machine code is never the whole story shown to the user.
      expect(error.userMessage).not.toBe(error.code);
    },
  );

  it("offers a retry action for a retryable failure", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<ErrorRegion error={errorOfKind("timeout")} onRetry={onRetry} section="Test" />);

    await user.click(screen.getByRole("button", { name: "Yeniden dene" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("offers no retry for an auth failure and explains the session instead", () => {
    render(<ErrorRegion error={errorOfKind("auth")} onRetry={vi.fn()} section="Test" />);

    expect(screen.queryByRole("button", { name: "Yeniden dene" })).toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("launcher");
  });

  it("suggests checking the local service when it is unavailable", () => {
    render(<ErrorRegion error={errorOfKind("unavailable")} section="Test" />);

    expect(screen.getByRole("alert").textContent).toContain(
      "calisir durumda oldugunu kontrol edin",
    );
  });

  it("shows the request id when the backend sent one, and a dash when not", () => {
    const { unmount } = render(<ErrorRegion error={errorOfKind("server")} section="Test" />);
    expect(screen.getByRole("alert").textContent).toContain(`Istek: ${REQUEST_ID}`);
    unmount();

    render(<ErrorRegion error={errorOfKind("network")} section="Test" />);
    expect(screen.getByRole("alert").textContent).toContain("Istek: -");
  });

  it("copies only redacted diagnostics: no URL, no DID, no path, no message", async () => {
    // A worst-case backend sentence: prose, so it becomes the user message,
    // and stuffed with values that must never leave through the copy button.
    const error = new ApiError(
      500,
      "Kayit islenemedi: did:key:z6MkTESTONLYVALUE https://technocore.chat/openapi.json C:\\Users\\gizli\\vault.json parola=TESTONLY",
      { requestId: REQUEST_ID },
    );

    // Stub the clipboard after userEvent.setup(), which installs its own.
    const user = userEvent.setup();
    let copied = "";
    stubClipboard((text) => {
      copied = text;
      return Promise.resolve();
    });
    render(<ErrorRegion error={error} section="Kimlik ve Guvenlik" />);
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
    expect(payload["code"]).toBe("http_500");
    expect(payload["kind"]).toBe("server");
    expect(payload["request_id"]).toBe(REQUEST_ID);
    expect(payload["section"]).toBe("Kimlik ve Guvenlik");

    expect(copied).not.toContain("did:key");
    expect(copied).not.toContain("https:");
    expect(copied).not.toContain("technocore");
    expect(copied).not.toContain("gizli");
    expect(copied).not.toContain("parola");
    expect(copied).not.toContain("Kayit islenemedi");
  });

  it("reports a refused clipboard instead of pretending it copied", async () => {
    const user = userEvent.setup();
    stubClipboard(() => Promise.reject(new Error("denied")));
    render(<ErrorRegion error={errorOfKind("server")} section="Test" />);
    await user.click(screen.getByRole("button", { name: "Tani bilgisini kopyala" }));

    expect(await screen.findByRole("button", { name: "Kopyalanamadi" })).toBeInTheDocument();
  });
});
