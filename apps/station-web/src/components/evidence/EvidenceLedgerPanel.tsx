import { Alert, Button, Checkbox, Separator } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import {
  type ApiError,
  captureEvidenceLine,
  exportEvidence,
  fetchAuditChain,
  fetchEvidenceRecords,
  toApiError,
} from "../../api/client";
import type {
  AuditChainState,
  AuditChainStatus,
  CaptureAttemptState,
  EvidenceCaptureResult,
  EvidenceExportFormat,
  EvidenceList,
  EvidenceRecord,
  EvidenceWriteOutcome,
} from "../../api/types";
import { shortDigest } from "../../lib/digest";
import { EmptyState } from "../EmptyState";
import { ErrorRegion } from "../ErrorRegion";
import { StatusPill, type StatusTone } from "../StatusPill";

/**
 * The evidence ledger: what this Station archived, and how little each part
 * of it proves.
 *
 * Five rules shape this surface, and none of them is cosmetic.
 *
 * 1. **The four trust levels are reported per record, never summed.** A
 *    signature proof is not a server observation, a server observation is not
 *    a trusted time, and level 4 does not exist in this release. Each record
 *    carries its own four-line answer (`docs/evidence-model.md` 1).
 * 2. **A capture is a read, and it happens only when asked.** It is not
 *    triggered on mount, on a timer, or as a step of anything else
 *    (ADR-0003 4).
 * 3. **Six capture states, presented as six things.** Five of them establish
 *    nothing about whether a message was published. `line_not_found` proves
 *    nothing at all - the ring forgets - and never converts an
 *    `outcome_unknown` send into a send that did not happen.
 * 4. **No write is ever offered again.** There is no resend control here, no
 *    parameter that could become one, and the read retry says in words that it
 *    is a read. Package D's stance is unchanged: Station does not guess on the
 *    user's behalf.
 * 5. **Nothing remote becomes active content.** Room names, generations and
 *    backend sentences are rendered as plain text; there is no anchor and no
 *    markup path anywhere below (SI-54).
 */

// --- vocabulary ------------------------------------------------------------

interface Presented {
  readonly title: string;
  readonly tone: StatusTone;
}

/**
 * The archived write outcome, in five spellings.
 *
 * `not_sent` reads "Gonderim yapilmadi" rather than the shorter negative, so
 * the sentence that must never appear next to an unknown outcome is not
 * lying around in the vocabulary waiting to be rendered by mistake.
 */
const WRITE_OUTCOME: Record<EvidenceWriteOutcome, Presented> = {
  in_flight: { title: "Gonderim suruyor", tone: "pending" },
  accepted: { title: "Kabul edildi", tone: "ok" },
  refused: { title: "Reddedildi", tone: "problem" },
  outcome_unknown: { title: "Sonuc bilinmiyor", tone: "pending" },
  not_sent: { title: "Gonderim yapilmadi", tone: "inactive" },
};

interface CapturePresentation extends Presented {
  /** What this state does and does not establish, in one paragraph. */
  readonly meaning: string;
}

/**
 * The six capture states, each with its own sentence.
 *
 * Only `line_captured` is a positive finding, and even that one is a level 2
 * server observation rather than proof of publication. The other five are
 * grouped by nothing: a missing line, a changed epoch and three different ways
 * of failing to read are four separate findings, and flattening them into
 * "capture failed" would let a reader treat an unreadable stream as evidence
 * that a record is absent.
 */
const CAPTURE: Record<CaptureAttemptState, CapturePresentation> = {
  line_captured: {
    title: "Satir yakalandi",
    tone: "ok",
    meaning:
      "Bu yalnizca Seviye 2 sunucu gozlemidir: sunucunun kendi disa aktariminda bizim kaydimizin satiri gorundu ve ham baytlariyla saklandi. Mesajin yayimlandiginin bagimsiz bir ispati degildir; tek bir sunucunun kendi durumu hakkindaki cevabidir.",
  },
  line_not_found: {
    title: "Satir bulunamadi",
    tone: "pending",
    meaning:
      "Bu sonuc hicbir sey kanitlamaz. Oda halkasi eski kayitlari unutur ve unutulmus bir kayit ile hic yazilmamis bir kayit taramada birebir ayni gorunur. Bu yuzden 'yayimlanmadi' sonucu cikarilmaz ve sonucu bilinmeyen bir gonderim bu bulgu yuzunden asla durum degistirmez.",
  },
  generation_changed: {
    title: "Oda donemi degisti",
    tone: "pending",
    meaning:
      "Odanin generation degeri imza anindakinden farkli. Iki taraf karsilastirilamaz: bu bir uyusmazlik degil, farkli bir donemdir. Bulunmus bir satir bile bu durumda karsilastirma icin kullanilmaz.",
  },
  stream_truncated: {
    title: "Tarama tamamlanamadi",
    tone: "pending",
    meaning:
      "Akis tarama tavanina dayandi; kayit defterinin tamami okunamadi. Bu bir okunamama durumudur. Eksik bir taramada satirin gorunmemesi, satirin yoklugunun kaniti degildir.",
  },
  parse_problem: {
    title: "Satirlar okunamadi",
    tone: "pending",
    meaning:
      "Akistaki bazi satirlarin yapisi cozulemedi. Bu bir okunamama durumudur: okunamayan bir satir degistirilmis bir satir demek degildir, yalnizca degerlendirilemeyen bir satirdir.",
  },
  fetch_failed: {
    title: "Okuma tamamlanamadi",
    tone: "problem",
    meaning:
      "Disa aktarim okumasi tamamlanmadi. Bu da bir okunamama durumudur ve gonderimin akibeti hakkinda hicbir sey soylemez.",
  },
};

/** The sentence that follows every capture outcome, without exception. */
const READ_ONLY_RULE =
  "Yakalama yalniz okur. Okuma dilediginiz kadar yeniden denenebilir; gonderim hicbir durumda ve hicbir yolla yeniden denenmez.";

const CHAIN: Record<AuditChainState, Presented> = {
  intact: { title: "Zincir tutarli", tone: "ok" },
  empty: { title: "Zincir bos", tone: "inactive" },
  broken_link: { title: "Zincir halkasi kirilmis", tone: "problem" },
  head_mismatch: { title: "Zincir basi uyusmuyor", tone: "problem" },
  unavailable: { title: "Zincir dogrulanamadi", tone: "pending" },
};

/** The download name. Client-side, fixed, and never taken from the response. */
const EXPORT_FILENAME: Record<EvidenceExportFormat, string> = {
  json: "technocore-station-kanit.json",
  markdown: "technocore-station-kanit.md",
};

const EXPORT_LABEL: Record<EvidenceExportFormat, string> = {
  json: "JSON olarak disa aktar",
  markdown: "Markdown olarak disa aktar",
};

function formatDate(value: string | null): string {
  if (value === null || value === "") return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

function formatCount(value: number | null): string {
  return value === null ? "-" : String(value);
}

// --- panel -----------------------------------------------------------------

export function EvidenceLedgerPanel() {
  const [ledger, setLedger] = useState<EvidenceList | null>(null);
  const [ledgerError, setLedgerError] = useState<ApiError | null>(null);
  const [ledgerLoading, setLedgerLoading] = useState(true);

  // The chain is read separately from the listing even though the listing
  // carries a summary of it: only this endpoint returns the permitted claim
  // sentence and the head comparison, and a failure to verify the chain must
  // not hide the records, nor a failure to list them hide the chain.
  const [audit, setAudit] = useState<AuditChainStatus | null>(null);
  const [auditError, setAuditError] = useState<ApiError | null>(null);
  const [auditLoading, setAuditLoading] = useState(true);

  const [capturingId, setCapturingId] = useState<string | null>(null);
  const [captures, setCaptures] = useState<Record<string, EvidenceCaptureResult>>({});
  const [captureError, setCaptureError] = useState<ApiError | null>(null);

  const [acknowledged, setAcknowledged] = useState(false);
  const [exporting, setExporting] = useState<EvidenceExportFormat | null>(null);
  const [exported, setExported] = useState<EvidenceExportFormat | null>(null);
  const [exportError, setExportError] = useState<ApiError | null>(null);

  const loadLedger = useCallback(async (): Promise<void> => {
    setLedgerLoading(true);
    try {
      setLedger(await fetchEvidenceRecords());
      setLedgerError(null);
    } catch (caught) {
      setLedgerError(toApiError(caught));
    } finally {
      setLedgerLoading(false);
    }
  }, []);

  const loadAudit = useCallback(async (): Promise<void> => {
    setAuditLoading(true);
    try {
      setAudit(await fetchAuditChain());
      setAuditError(null);
    } catch (caught) {
      setAuditError(toApiError(caught));
    } finally {
      setAuditLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLedger();
    void loadAudit();
  }, [loadAudit, loadLedger]);

  /**
   * One capture, for one record, because the user pressed a button.
   *
   * The guard is the double-activation rule (ui-action-map 1.4) and nothing
   * more: a capture is a read, so a second one would be harmless on the
   * server and merely confusing here.
   */
  async function capture(evidenceId: string): Promise<void> {
    if (capturingId !== null) return;
    setCapturingId(evidenceId);
    setCaptureError(null);
    try {
      const outcome = await captureEvidenceLine(evidenceId);
      setCaptures((previous) => ({ ...previous, [evidenceId]: outcome }));
      // The stored record now carries the new state; re-read it so the row and
      // the outcome region cannot disagree.
      await loadLedger();
    } catch (caught) {
      setCaptureError(toApiError(caught));
    } finally {
      setCapturingId(null);
    }
  }

  /**
   * The export, which only exists once consent has been given.
   *
   * The checkbox is not the control that enforces it - the backend refuses a
   * body without `acknowledged`, and refuses `false` again in the handler -
   * but a checkbox that were merely decorative would teach the user that the
   * consent step is decorative too.
   */
  async function runExport(format: EvidenceExportFormat): Promise<void> {
    if (!acknowledged || exporting !== null) return;
    setExporting(format);
    setExportError(null);
    try {
      const { blob } = await exportEvidence({ format, acknowledged: true });
      // Same delivery as the recovery file: a temporary object URL, clicked
      // and revoked immediately, so nothing lingers in the document.
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = EXPORT_FILENAME[format];
      anchor.click();
      URL.revokeObjectURL(url);
      setExported(format);
    } catch (caught) {
      setExportError(toApiError(caught));
    } finally {
      setExporting(null);
    }
  }

  return (
    <section aria-label="Kanit defteri" className="flex flex-col gap-4">
      <AuditChainRegion
        error={auditError}
        loading={auditLoading}
        onRetry={() => void loadAudit()}
        status={audit}
      />

      <Separator />

      <section aria-label="Kanit kayitlari" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">Kanit kayitlari</h3>
          {ledger !== null && (
            <StatusPill
              label={`${String(ledger.record_count)} kayit`}
              tone={ledger.record_count === 0 ? "inactive" : "ok"}
            />
          )}
        </div>

        {ledgerError !== null && (
          <ErrorRegion
            error={ledgerError}
            onRetry={() => void loadLedger()}
            retryPending={ledgerLoading}
            section="Kanitlar / Kanit kayitlari"
            title="Kanit kayitlari okunamadi"
          />
        )}

        {ledger === null && ledgerError === null && (
          <p className="text-sm text-muted">Kanit kayitlari okunuyor...</p>
        )}

        {ledger !== null && ledger.records.length === 0 && (
          <EmptyState
            description="Bu bilgisayarda henuz hicbir kanit kaydi yok. Bir kayit ancak kullanici onayli bir gonderim denendikten sonra olusur; Station kendiliginden hicbir sey gondermez ve kendiliginden hicbir kayit uretmez."
            title="Henuz kanit kaydi yok"
          />
        )}

        {captureError !== null && (
          <ErrorRegion
            error={captureError}
            section="Kanitlar / Yakalama"
            title="Yakalama tamamlanamadi"
          />
        )}

        {ledger !== null && ledger.records.length > 0 && (
          <ul className="flex flex-col gap-3">
            {ledger.records.map((record) => (
              <li key={record.id}>
                <RecordRow
                  busy={capturingId !== null}
                  capture={captures[record.id] ?? null}
                  capturing={capturingId === record.id}
                  onCapture={() => void capture(record.id)}
                  record={record}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <Separator />

      <ExportRegion
        acknowledged={acknowledged}
        error={exportError}
        exported={exported}
        exporting={exporting}
        onAcknowledge={setAcknowledged}
        onExport={(format) => void runExport(format)}
      />
    </section>
  );
}

// --- audit chain -----------------------------------------------------------

/**
 * The chain's verdict, and the limits of what it can mean.
 *
 * `claim` is rendered exactly as the backend produced it. The UI does not
 * compose a sentence about what the chain provides, because two surfaces
 * writing the same claim independently is how the two eventually stop saying
 * the same thing.
 */
function AuditChainRegion({
  status,
  error,
  loading,
  onRetry,
}: {
  readonly status: AuditChainStatus | null;
  readonly error: ApiError | null;
  readonly loading: boolean;
  readonly onRetry: () => void;
}) {
  return (
    <section aria-label="Audit zinciri" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-foreground">Audit zinciri</h3>
        {status !== null && (
          <StatusPill label={CHAIN[status.state].title} tone={CHAIN[status.state].tone} />
        )}
      </div>

      {error !== null && (
        <ErrorRegion
          error={error}
          onRetry={onRetry}
          retryPending={loading}
          section="Kanitlar / Audit zinciri"
          title="Audit zinciri okunamadi"
        />
      )}

      {status === null && error === null && (
        <p className="text-sm text-muted">Zincir durumu okunuyor...</p>
      )}

      {status !== null && (
        <>
          <p className="text-sm text-foreground">{status.detail}</p>

          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-2">
            <div className="flex justify-between gap-2">
              <dt>Durum</dt>
              <dd className="font-mono">{status.state}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Zincirdeki satir</dt>
              <dd className="font-mono">{String(status.link_count)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Ayri tutulan bastaki satir</dt>
              <dd className="font-mono">{formatCount(status.head_count)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Ilk sorunlu satir</dt>
              <dd className="font-mono">{formatCount(status.first_bad_seq)}</dd>
            </div>
          </dl>

          <Alert status="default">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Bu zincirin sagladigi ve saglamadigi sey</Alert.Title>
              <Alert.Description>
                <span className="flex flex-col gap-2">
                  {/* Verbatim, from the backend. The UI produces no claim of
                      its own about what this mechanism provides. */}
                  <span>{status.claim}</span>
                  <span>
                    Zincirin icinde kendi uzunlugunu soyleyen bir sey yoktur:
                    sonun kesilmesi, ayri bir zarfta tutulan zincir basi
                    olmadan tespit edilemez.
                  </span>
                  <span>
                    Bu bir garanti degildir. Ayni Windows kullanicisi olarak
                    calisan bir saldirgan ayni zarfi acabilir, butun MAC
                    degerlerini yeniden hesaplayabilir ve basi yeniden
                    yazabilir. Bu yuzden burada kullanilabilecek tek ifade
                    &quot;cevrimdisi degisiklige karsi tespit edici&quot;dir.
                  </span>
                  <span>
                    Yarim kalan bir yazma da bir saldiri degildir: bir dosya ile
                    bir veritabani islemi atomik olarak birlikte islenemez ve
                    aradaki pencerede bir cokme, basi bir satir ileride veya
                    geride birakir.
                  </span>
                </span>
              </Alert.Description>
            </Alert.Content>
          </Alert>
        </>
      )}
    </section>
  );
}

// --- one record ------------------------------------------------------------

function RecordRow({
  record,
  capture,
  capturing,
  busy,
  onCapture,
}: {
  readonly record: EvidenceRecord;
  /** The result of a capture made in this session, if there was one. */
  readonly capture: EvidenceCaptureResult | null;
  readonly capturing: boolean;
  /** True while *any* capture is in flight: one at a time, on request. */
  readonly busy: boolean;
  readonly onCapture: () => void;
}) {
  const outcome = WRITE_OUTCOME[record.write_outcome];
  const state: CaptureAttemptState | null =
    capture?.state ?? (record.capture_state === "" ? null : record.capture_state);
  const presented = state === null ? null : CAPTURE[state];

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground">{`Oda: ${record.room}`}</span>
        <StatusPill label={outcome.title} tone={outcome.tone} />
        <StatusPill
          label={presented === null ? "Yakalama denenmedi" : presented.title}
          tone={presented === null ? "inactive" : presented.tone}
        />
      </div>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-2">
        <div className="flex justify-between gap-2">
          <dt>Nonce</dt>
          <dd className="font-mono">{record.nonce}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Yerel kayit zamani</dt>
          <dd className="font-mono">{formatDate(record.recorded_at)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>HTTP</dt>
          <dd className="font-mono">
            {record.http_status === 0 ? "-" : String(record.http_status)}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Oda donemi</dt>
          <dd className="font-mono">
            {record.room_generation === "" ? "-" : record.room_generation}
          </dd>
        </div>
        {/* Digests only, and only their first twelve characters: the payload
            has no raw bytes in it, and a full 64-hex run is the same shape as
            a seed. */}
        <div className="flex justify-between gap-2">
          <dt>Kanonik ozet</dt>
          <dd className="font-mono">{shortDigest(record.canonical_sha256)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Istek ozeti</dt>
          <dd className="font-mono">{shortDigest(record.request_sha256)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Yanit ozeti</dt>
          <dd className="font-mono">{shortDigest(record.response_sha256)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Akis ozeti</dt>
          <dd className="font-mono">
            {record.stream_sha256 === "" ? "-" : shortDigest(record.stream_sha256)}
          </dd>
        </div>
      </dl>

      <RecordLevels record={record} />

      {presented !== null && state !== null && (
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium text-foreground">
            {`Yakalama sonucu: ${presented.title}`}
          </span>
          <p className="text-xs text-muted">{presented.meaning}</p>
          {/* The backend's own sentence for this state, beside ours rather
              than instead of it. */}
          <p className="text-xs text-muted">
            {capture?.detail !== undefined && capture.detail !== ""
              ? capture.detail
              : record.capture_detail}
          </p>
          {state === "line_captured" && (
            <p className="font-mono text-xs text-muted">
              {`Satir konumu: ${formatCount(capture?.line_offset ?? record.captured_line_offset)} · uzunluk: ${formatCount(capture?.line_length ?? record.captured_line_length)} · yakalama zamani: ${formatDate(record.captured_at)}`}
            </p>
          )}
          {(capture?.stream_truncated ?? record.stream_truncated) && (
            <p className="text-xs text-muted">
              Tarama tavana dayandi; kayit defterinin tamami okunmadi.
            </p>
          )}
          {record.unreadable_lines > 0 && (
            <p className="text-xs text-muted">
              {`Okunamayan satir sayisi: ${String(record.unreadable_lines)}. Okunamayan bir satir degistirilmis bir satir demek degildir.`}
            </p>
          )}
          <p className="text-xs text-muted">{READ_ONLY_RULE}</p>
        </div>
      )}

      {record.write_outcome === "outcome_unknown" && (
        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Bu gonderimin sonucu hala bilinmiyor</Alert.Title>
            <Alert.Description>
              <span className="flex flex-col gap-2">
                <span>
                  Sunucu bu mesaji yazmis olabilir. Kanit yakalama bir okumadir
                  ve bu durumu &quot;gonderim yapilmadi&quot; haline getirmez.
                </span>
                {state === "line_not_found" && (
                  <span>
                    Satirin bulunmamasi da bunu degistirmez: oda halkasi unutur,
                    bu yuzden yayimlanmis ve dusmus bir kayit ile hic
                    yayimlanmamis bir kayit ayni gorunur.
                  </span>
                )}
                <span>
                  Station sizin adiniza tahmin yurutmez ve yeniden gonderim
                  onermez. Bu yuzeyde yeniden gonderme kontrolu yoktur.
                </span>
              </span>
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      <div>
        {/* A read. The label says so, because a button here that merely said
            "Yeniden dene" would be read as "send it again". */}
        <Button
          isDisabled={busy}
          onPress={onCapture}
          size="sm"
          variant="secondary"
        >
          {capturing
            ? "Yakalaniyor..."
            : state === null
              ? "Kanit satirini yakala (yalniz okur)"
              : "Yakalamayi yeniden dene (yalniz okur)"}
        </Button>
      </div>
    </div>
  );
}

/**
 * The four levels for one record, one line each.
 *
 * They are never collapsed into a single badge. Summing them is the exact
 * mistake the model exists to prevent, and a reader who sees one green pill
 * cannot tell which of four different things was established.
 */
function RecordLevels({ record }: { readonly record: EvidenceRecord }) {
  return (
    <ul className="flex flex-col gap-1">
      {record.levels.map((level) => (
        <li className="flex flex-col gap-1" key={level.level}>
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-foreground">
              {`Seviye ${String(level.level)} · ${level.name}`}
            </span>
            <StatusPill
              label={level.present ? "Var" : "Yok"}
              tone={level.present ? "ok" : "inactive"}
            />
          </span>
          <span className="text-xs text-muted">{level.detail}</span>
          {level.level === 4 && record.external_anchor === null && (
            <span className="text-xs text-muted">
              Bu kayitta harici anchor yoktur. Alan bos birakilmaz, null olarak
              tutulur; atlanan bir anahtar &quot;kimse bakmadi&quot; gibi
              okunur, null ise alinmis bir karari gosterir.
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

// --- export ----------------------------------------------------------------

function ExportRegion({
  acknowledged,
  exporting,
  exported,
  error,
  onAcknowledge,
  onExport,
}: {
  readonly acknowledged: boolean;
  readonly exporting: EvidenceExportFormat | null;
  readonly exported: EvidenceExportFormat | null;
  readonly error: ApiError | null;
  readonly onAcknowledge: (next: boolean) => void;
  readonly onExport: (format: EvidenceExportFormat) => void;
}) {
  return (
    <section aria-label="Disa aktarim" className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-foreground">Disa aktarim</h3>

      <Alert status="warning">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Paylasim kimlik baglantisi dogurur</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2">
              <span>
                Disa aktarilan dosya public DID&apos;inizi, imzalarinizi ve
                gonderim kayitlarinizi tasir. Bunlar gizli degerler degildir,
                ama paylasildiklarinda bu makinedeki kimlik ile dosyayi
                paylastiginiz yer arasinda kalici bir kimlik baglantisi kurulur.
                Dosyayi yalniz bunu bilerek paylasin.
              </span>
              <span>
                Bu dosya, hata bolgelerindeki &quot;Tani bilgisini
                kopyala&quot; ciktisiyla ayni sey degildir ve onun yerine
                kullanilmamalidir. Tani ciktisi redaktedir ve yalnizca hata
                kodu, HTTP durumu, hata sinifi, istek kimligi, bolum adi ve
                zaman damgasi tasir; kanit disa aktarimi ise kayitlarin
                kendisidir.
              </span>
            </span>
          </Alert.Description>
        </Alert.Content>
      </Alert>

      <Checkbox isSelected={acknowledged} onChange={onAcknowledge}>
        <Checkbox.Content>
          <Checkbox.Control>
            <Checkbox.Indicator />
          </Checkbox.Control>
          Disa aktarilan dosyanin public DID ve imza tasidigini, paylasildiginda
          kimlik baglantisi dogurdugunu anladim.
        </Checkbox.Content>
      </Checkbox>

      <p className="text-xs text-muted">
        Onay verilmeden istek gonderilmez. Yerel servis de onaysiz bir govdeyi
        kabul etmez; buradaki kutu tek engel degildir, ilk engeldir.
      </p>

      <div className="flex flex-wrap gap-2">
        {(["json", "markdown"] as const).map((format) => (
          <Button
            isDisabled={!acknowledged || exporting !== null}
            key={format}
            onPress={() => onExport(format)}
            size="sm"
            variant="secondary"
          >
            {exporting === format ? "Hazirlaniyor..." : EXPORT_LABEL[format]}
          </Button>
        ))}
      </div>

      {exported !== null && exporting === null && error === null && (
        <p className="text-xs text-muted">
          {`Dosya tarayiciya verildi: ${EXPORT_FILENAME[exported]}. Sunucu hicbir yola dosya yazmaz; indirme tamamen tarayicinizdadir.`}
        </p>
      )}

      {error !== null && (
        // No retry callback: the user re-presses the export control they
        // already understand, rather than re-firing a half-finished action
        // from inside an alert box.
        <ErrorRegion
          error={error}
          section="Kanitlar / Disa aktarim"
          title="Disa aktarim tamamlanamadi"
        />
      )}
    </section>
  );
}
