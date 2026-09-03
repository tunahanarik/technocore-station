import { Alert, Button } from "@heroui/react";
import { useState } from "react";

import type { ApiError } from "../api/client";

/**
 * The app's one way of showing a failed operation.
 *
 * A persistent region, not a toast: it stays until the user acts, carries the
 * stable machine code and the backend request id so a report can be matched
 * to a server log line, and offers the recovery that fits the failure class.
 *
 * The "copy diagnostics" payload is deliberately redacted. It contains only
 * {code, HTTP status, kind, request id, timestamp, section} - never a URL,
 * payload, DID, file path, passphrase or cookie. The user message is also
 * excluded: a backend sentence may quote user input, and this payload is
 * built to be pasted into an issue without review.
 */

interface ErrorRegionProps {
  readonly error: ApiError;
  /** Section (or dialog) name, used only in the diagnostics payload. */
  readonly section: string;
  readonly title?: string;
  /** Offered when the failure class is retryable. */
  readonly onRetry?: () => void;
}

type CopyState = "idle" | "copied" | "failed";

const COPY_LABEL: Record<CopyState, string> = {
  idle: "Tani bilgisini kopyala",
  copied: "Kopyalandi",
  failed: "Kopyalanamadi",
};

/** Extra recovery guidance for classes where "try again" is not the answer. */
function recoveryHint(error: ApiError): string | null {
  if (error.kind === "auth") {
    return "Oturum bulunamadi veya suresi doldu. Uygulamayi launcher uzerinden yeniden acin; acilis baglantisi tek kullanimliktir.";
  }
  if (error.kind === "unavailable") {
    return "Yerel servisin calisir durumda oldugunu kontrol edin, sonra yeniden deneyin.";
  }
  return null;
}

export function ErrorRegion({ error, section, title, onRetry }: ErrorRegionProps) {
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const hint = recoveryHint(error);

  async function copyDiagnostics(): Promise<void> {
    // Redacted on purpose; see the module comment before adding a field.
    const payload = JSON.stringify(
      {
        code: error.code,
        status: error.status,
        kind: error.kind,
        request_id: error.requestId,
        timestamp: new Date().toISOString(),
        section,
      },
      null,
      2,
    );
    try {
      await navigator.clipboard.writeText(payload);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <div role="alert">
      <Alert status="danger">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>{title ?? "Islem basarisiz oldu"}</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2">
              <span>{error.userMessage}</span>
              {hint !== null && <span>{hint}</span>}
              <span className="font-mono text-xs">
                {`Kod: ${error.code} · HTTP: ${error.status === 0 ? "-" : String(error.status)} · Istek: ${error.requestId ?? "-"}`}
              </span>
              <span className="flex flex-wrap gap-2">
                {error.retryable && onRetry !== undefined && (
                  <Button onPress={onRetry} size="sm" variant="secondary">
                    Yeniden dene
                  </Button>
                )}
                <Button onPress={() => void copyDiagnostics()} size="sm" variant="ghost">
                  {COPY_LABEL[copyState]}
                </Button>
              </span>
            </span>
          </Alert.Description>
        </Alert.Content>
      </Alert>
    </div>
  );
}
