import { Alert, Button, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import { type ApiError, fetchTechnocore, refreshTechnocore, toApiError } from "../api/client";
import type {
  DriftState,
  FieldOutcome,
  ProtocolFieldStatus,
  TechnocoreStatus,
} from "../api/types";
import { ErrorRegion } from "./ErrorRegion";
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
    "Denetim tamamlanamadi. Kanit olmadigi icin kapi fail-closed davranir; asagida hangi adimin tamamlanamadigi yazili.",
};

/**
 * What happened to one field.
 *
 * `mismatch` is the only outcome that licenses saying the server changed
 * something. `missing` and `unsupported` mean the value was not read, and a
 * UI that showed all three as "changed" would be asserting evidence it does
 * not have - which is exactly the false alarm this panel used to show.
 */
const OUTCOME_LABEL: Record<FieldOutcome, string> = {
  matched: "Ayni",
  mismatch: "Degismis",
  missing: "Bulunamadi",
  unsupported: "Okunamadi",
};

const OUTCOME_TONE: Record<FieldOutcome, StatusTone> = {
  matched: "ok",
  mismatch: "problem",
  missing: "pending",
  unsupported: "pending",
};

/**
 * What to show where the observed value would go.
 *
 * `missing` and `unsupported` both mean "not compared", but they are not the
 * same finding: one says the document does not carry the field, the other
 * says it carries a shape this build cannot read. Collapsing them into one
 * word sends whoever is debugging to the wrong place.
 */
const OUTCOME_VALUE: Record<FieldOutcome, string> = {
  matched: "",
  mismatch: "",
  missing: "belgede bulunamadi",
  unsupported: "sema okunamadi",
};

/**
 * A mismatch does not always have a value to show.
 *
 * Most are a plain difference and print what the document said. Some are a
 * demonstrated contradiction - two bounds that cannot both hold, a type that
 * refuses what we send - and there is no single observed value behind them.
 * Printing the reader's `<yok>` there would say "the field is missing", which
 * is a different and wrong finding; the explanation sits in `detail`.
 */
function fieldValueLabel(field: ProtocolFieldStatus): string {
  if (OUTCOME_VALUE[field.outcome] !== "") return "Durum";
  return field.detail === "" ? "Gorulen" : "Durum";
}

function fieldValueText(field: ProtocolFieldStatus): string {
  const byOutcome = OUTCOME_VALUE[field.outcome];
  if (byOutcome !== "") return byOutcome;
  return field.detail === "" ? field.observed : "sema kendisiyle celisiyor";
}

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
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(url);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      // Clipboard access can be refused; say so instead of silently resetting.
      setCopyState("failed");
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
        {copyState === "copied" ? "Kopyalandi" : copyState === "failed" ? "Kopyalanamadi" : "Kopyala"}
      </Button>
    </span>
  );
}

export function TechnocoreSourcesPanel() {
  const [status, setStatus] = useState<TechnocoreStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  // Which action failed decides what "Yeniden dene" repeats: re-reading local
  // state is harmless, but re-running the outbound check must stay the same
  // explicit action the user already took, never an upgrade of a mere read.
  const [errorSource, setErrorSource] = useState<"load" | "check">("load");

  const load = useCallback(async (): Promise<void> => {
    try {
      setStatus(await fetchTechnocore());
      setError(null);
    } catch (caught) {
      setError(toApiError(caught));
      setErrorSource("load");
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
      setError(toApiError(caught));
      setErrorSource("check");
    } finally {
      setBusy(false);
    }
  }

  const state: DriftState = status?.state ?? "never_checked";
  const fields = status?.fields ?? [];
  const criticalFields = fields.filter((field) => field.severity === "critical");
  const changed = fields.filter((field) => !field.matches);

  // Two independent questions, deliberately not merged: could the documents be
  // fetched, and did the protocol they describe still match. A 503 on a
  // supplementary document is not a protocol finding, and an unreadable schema
  // is not a fetch failure.
  const sources = status?.sources ?? [];
  const reachable = sources.filter((source) => source.outcome === "ok").length;
  const fetchFailed = sources.filter((source) => source.outcome !== "ok");
  const unevaluable = status?.critical_unevaluable_count ?? 0;
  const mismatched = status?.critical_mismatch_count ?? 0;

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
        <ErrorRegion
          error={error}
          onRetry={() => void (errorSource === "check" ? check() : load())}
          section="Kaynaklar / Resmi kaynak denetimi"
          title={errorSource === "check" ? "Denetim yapilamadi" : "Durum okunamadi"}
        />
      )}

      {state === "unavailable" && unevaluable > 0 && (
        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Protokol uyumu dogrulanamadi</Alert.Title>
            <Alert.Description>
              {`Belgeler alindi, fakat ${String(unevaluable)} kritik alan okunamadi.`}{" "}
              Bu, sunucunun bir seyi degistirdigi anlamina gelmez; yalniz
              beklenen konumda okunabilir bir deger bulunamadigi anlamina
              gelir. Kanit olmadigi icin dis yazma kapisi kapali kalir.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      {state === "unavailable" && unevaluable === 0 && (
        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Zorunlu belge alinamadi</Alert.Title>
            <Alert.Description>
              Protokol karsilastirmasi hic calistirilamadi, cunku zorunlu bir
              belge alinamadi veya okunamadi. Dis yazma kapisi kapali kalir.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      {state === "drifted" && (
        <Alert status="danger">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Kritik protokol suruklenmesi</Alert.Title>
            <Alert.Description>
              {`Imzanin gecerliligini etkileyen ${String(mismatched)} alan okundu ve beklenenden farkli.`}{" "}
              Bu durumda uretilen bir imza sunucu tarafindan reddedilebilir
              veya onaylamadiginiz baytlari kapsayabilir. Dis yazma kapisi
              kapali.
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
        <h4 className="text-sm font-semibold text-foreground">
          1. Belge erisimi
        </h4>
        {/* Reachability, on its own. A document that arrived says nothing yet
            about whether the protocol still matches; that is the section
            below. Keeping them apart is what stops a 503 from reading as a
            protocol change, and a schema we cannot parse from reading as a
            network problem. */}
        {status !== null && sources.length > 0 && (
          <p className="text-xs text-muted">
            {`${String(reachable)}/${String(sources.length)} resmi belge alindi.`}
            {fetchFailed.length > 0 &&
              ` Alinamayan: ${fetchFailed.map((source) => source.source_id).join(", ")}.`}
          </p>
        )}
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
            <h4 className="text-sm font-semibold text-foreground">
              2. Protokol degerlendirmesi
            </h4>
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
                    <span className="flex items-center gap-2">
                      <StatusPill
                        label={OUTCOME_LABEL[field.outcome]}
                        tone={OUTCOME_TONE[field.outcome]}
                      />
                      <StatusPill
                        label={field.severity === "critical" ? "Kritik" : "Uyari"}
                        tone={field.severity === "critical" ? "problem" : "pending"}
                      />
                    </span>
                  </div>
                  <p className="text-xs text-muted">{field.rationale}</p>
                  {field.detail !== "" && (
                    <p className="text-xs text-muted">
                      {field.outcome === "unsupported"
                        ? `Okunamama sebebi: ${field.detail}`
                        : `Celiski: ${field.detail}`}
                    </p>
                  )}
                  <dl className="flex flex-col gap-1 text-xs text-muted">
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt>Beklenen</dt>
                      <dd className="font-mono">{field.expected}</dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt>{fieldValueLabel(field)}</dt>
                      <dd className="font-mono">{fieldValueText(field)}</dd>
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
          {`${String(criticalFields.length)} kritik alanin tamami okundu ve beklenen degerle ayni. Bu sonuc yalniz bu denetim anina aittir.`}
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
