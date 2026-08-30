import { Alert, Button, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import { fetchTechnocore, refreshTechnocore } from "../api/client";
import type { DriftState, TechnocoreStatus } from "../api/types";
import { StatusPill, type StatusTone } from "./StatusPill";

/**
 * The read-only Technocore surface.
 *
 * Two rules shape everything here.
 *
 * **Nothing remote is rendered as content.** Every value shown is a short,
 * server-swept metadata string - a hash prefix, an ETag, a pattern. There is
 * no `dangerouslySetInnerHTML`, no anchor built from a remote value, and no
 * room, topic or message text: this stage does not fetch any. A source URL is
 * a fixed constant from our own registry, and it is shown as plain text with
 * a copy button rather than as a link (AC-17).
 *
 * **Checking is an explicit user action.** The panel reads state on mount,
 * which touches nobody, and only the button below reaches the network.
 */

const STATE_LABEL: Record<DriftState, string> = {
  never_checked: "Henuz denetlenmedi",
  current: "Guncel",
  drifted: "Suruklenme tespit edildi",
  unavailable: "Erisilemiyor",
};

const STATE_TONE: Record<DriftState, StatusTone> = {
  never_checked: "inactive",
  current: "ok",
  drifted: "problem",
  unavailable: "pending",
};

const STATE_EXPLANATION: Record<DriftState, string> = {
  never_checked:
    "Station kendiliginden hicbir istek gondermez. Resmi kaynaklari denetlemek icin asagidaki dugmeyi kullanin.",
  current:
    "Kritik protokol sozlesmesi Station'in imzaladigi bicimle ayni. Bu sonuc yalniz bu denetim anina aittir.",
  drifted:
    "Kritik bir alan degismis. Dis yazma kapisi kapali kalir; asagidaki farki inceleyin.",
  unavailable:
    "Zorunlu bir belge alinamadi veya okunamadi. Kanit olmadigi icin kapi fail-closed davranir.",
};

const AUTHORITY_LABEL: Record<number, string> = {
  1: "Seviye 1 · makine-okunabilir resmi belge",
  2: "Seviye 2 · resmi dokumantasyon",
};

function formatDate(value: string | null): string {
  if (value === null) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

function outcomeLabel(outcome: string, httpStatus: number): string {
  if (outcome === "ok") return `HTTP ${String(httpStatus)}`;
  return outcome === "parse_error" ? "Okunamadi" : "Alinamadi";
}

function CopyableUrl({ url }: { readonly url: string }) {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <span className="flex flex-wrap items-center gap-2">
      {/* Plain text, never an anchor: a clickable remote URL is active
          content, and this product does not turn Technocore data into it. */}
      <code className="rounded bg-surface-secondary px-1.5 py-0.5 font-mono text-xs">
        {url}
      </code>
      <Button
        aria-label={`${url} adresini kopyala`}
        onPress={() => void copy()}
        size="sm"
        variant="ghost"
      >
        {copied ? "Kopyalandi" : "Kopyala"}
      </Button>
    </span>
  );
}

export function TechnocoreSourcesPanel() {
  const [status, setStatus] = useState<TechnocoreStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    try {
      setStatus(await fetchTechnocore());
      setError(null);
    } catch {
      setError("Durum okunamadi. Yerel servise baglanilamadi.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function check(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      setStatus(await refreshTechnocore());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Denetim tamamlanamadi.");
    } finally {
      setBusy(false);
    }
  }

  const state: DriftState = status?.state ?? "never_checked";
  const fields = status?.fields ?? [];
  const criticalFields = fields.filter((field) => field.severity === "critical");
  const changed = fields.filter((field) => !field.matches);

  return (
    <section aria-label="Resmi kaynak denetimi" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">
            Salt okunur baglanti durumu
          </h3>
          <StatusPill label={STATE_LABEL[state]} tone={STATE_TONE[state]} />
        </div>
        <Button isDisabled={busy} onPress={() => void check()}>
          {busy ? "Denetleniyor..." : "Resmi kaynaklari denetle"}
        </Button>
      </div>

      <p className="text-xs text-muted">{STATE_EXPLANATION[state]}</p>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-2">
        <div className="flex justify-between gap-2">
          <dt>Son basarili kontrol</dt>
          <dd className="font-mono">{formatDate(status?.last_success_at ?? null)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Son deneme</dt>
          <dd className="font-mono">{formatDate(status?.last_attempt_at ?? null)}</dd>
        </div>
      </dl>

      {error !== null && (
        <Alert status="danger">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Denetim yapilamadi</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      {state === "drifted" && (
        <Alert status="danger">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Kritik protokol suruklenmesi</Alert.Title>
            <Alert.Description>
              Imzanin gecerliligini etkileyen bir alan degismis. Bu durumda
              uretilen bir imza sunucu tarafindan reddedilebilir veya
              onaylamadiginiz baytlari kapsayabilir. Dis yazma kapisi kapali.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      {state === "current" && (status?.warning_count ?? 0) > 0 && (
        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Kritik olmayan degisiklik</Alert.Title>
            <Alert.Description>
              Kapasite veya surum bilgisi degismis. Imza gecerliligini
              etkilemedigi icin kapi bu nedenle kapanmaz; yine de gormeniz icin
              listelenmistir.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      <Separator />

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold text-foreground">Resmi kaynaklar</h4>
        {status === null && <p className="text-xs text-muted">Durum okunuyor...</p>}
        {status !== null && status.sources.length === 0 && (
          <p className="text-xs text-muted">
            Bu oturumda henuz denetim yapilmadi, bu yuzden gosterilecek kaynak
            kaydi yok.
          </p>
        )}
        <ul className="flex flex-col gap-2">
          {(status?.sources ?? []).map((source) => (
            <li
              key={source.source_id}
              className="flex flex-col gap-1 rounded-lg border border-border p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium text-foreground">
                  {source.source_id}
                </span>
                <StatusPill
                  label={outcomeLabel(source.outcome, source.http_status)}
                  tone={source.outcome === "ok" ? "ok" : "problem"}
                />
              </div>
              <CopyableUrl url={source.url} />
              <p className="text-xs text-muted">
                {AUTHORITY_LABEL[source.authority] ??
                  `Seviye ${String(source.authority)}`}
              </p>
              <dl className="grid grid-cols-1 gap-x-4 text-xs text-muted sm:grid-cols-3">
                <div className="flex justify-between gap-2">
                  <dt>Hash</dt>
                  <dd className="font-mono">{source.short_hash || "-"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>ETag</dt>
                  <dd className="font-mono">{source.etag || "-"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Last-Modified</dt>
                  <dd className="font-mono">{source.last_modified || "-"}</dd>
                </div>
              </dl>
              {source.detail !== "" && (
                <p className="text-xs text-danger">{source.detail}</p>
              )}
            </li>
          ))}
        </ul>
      </div>

      {changed.length > 0 && (
        <>
          <Separator />
          <div className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold text-foreground">Degisen alanlar</h4>
            <ul className="flex flex-col gap-2">
              {changed.map((field) => (
                <li
                  key={field.key}
                  className="flex flex-col gap-1 rounded-lg border border-border p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium text-foreground">
                      {field.label}
                    </span>
                    <StatusPill
                      label={field.severity === "critical" ? "Kritik" : "Uyari"}
                      tone={field.severity === "critical" ? "problem" : "pending"}
                    />
                  </div>
                  <p className="text-xs text-muted">{field.rationale}</p>
                  <dl className="flex flex-col gap-1 text-xs text-muted">
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt>Beklenen</dt>
                      <dd className="font-mono">{field.expected}</dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt>Gorulen</dt>
                      <dd className="font-mono">{field.observed}</dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt>Konum</dt>
                      <dd className="font-mono">{field.json_path}</dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {criticalFields.length > 0 && changed.length === 0 && (
        <p className="text-xs text-muted">
          {`${String(criticalFields.length)} kritik alanin tamami beklenen degerle ayni.`}
        </p>
      )}

      <Alert status="default">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Bu denetim yalniz okur</Alert.Title>
          <Alert.Description>
            Yalniz sabit bir listedeki resmi belgeler okunur. Oda, mesaj veya
            note icerigi alinmaz; hicbir yazma istegi gonderilmez. Technocore&apos;da
            bazi GET yollari yazma yapar, bu yuzden istemci keyfi bir adres
            kabul etmez.
          </Alert.Description>
        </Alert.Content>
      </Alert>
    </section>
  );
}
