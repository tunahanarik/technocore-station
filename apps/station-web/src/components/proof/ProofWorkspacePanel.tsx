import { Alert, Button, Checkbox, Separator } from "@heroui/react";
import { useCallback, useEffect, useId, useState } from "react";

import {
  type ApiError,
  fetchProof,
  fetchTasks,
  prepareProofShare,
  takeProofBundle,
  toApiError,
} from "../../api/client";
import type {
  ProofBundleFormat,
  ProofClaimStatus,
  ProofWorkspace,
  TaskListResponse,
} from "../../api/types";
import { shortDigest } from "../../lib/digest";
import { EmptyState } from "../EmptyState";
import { ErrorRegion } from "../ErrorRegion";
import { StatusPill } from "../StatusPill";

/**
 * "Kanit calisma alani": one task's collected material, and how little of it
 * is a verdict.
 *
 * This section is called *Kanitlar*, and a reader is entitled to read that as
 * *kanitlandi*. The product refuses that reading in words rather than by
 * hoping nobody makes it, and seven rules below are the shape of that refusal.
 * None of them is cosmetic; each one is the difference between a screen that
 * is honest and a screen that merely looks finished.
 *
 * 1. **A hash fixes bytes, not truth.** `hash_scope` is rendered verbatim from
 *    the backend, at the top of the surface, before any digest appears - not
 *    in a footnote under one. It is not composed here: the same sentence goes
 *    into the downloaded file, and two surfaces authoring one disclaimer
 *    independently is how the two eventually stop saying the same thing
 *    (ADR-0009 11).
 * 2. **"Bagimsiz kontrol" is `not_implemented`, and says why.** The model lane
 *    is closed, so there is no second opinion in this release. It is rendered
 *    as an inactive state with its reason, never as a tick and never as a
 *    "dogrulandi" badge: a run's own output presented as a third party's
 *    verdict is the specific dishonesty ADR-0009 6 refuses.
 * 3. **"Gercek exit code" is `not_implemented`, and says why.** Arbitrary
 *    execution is closed (ADR-0008 1), so there is no check to run and no
 *    number to report. The plan's criterion travels as text; code that was
 *    never run is not tested code.
 * 4. **Gaps are named, never counted.** No score, no percentage, no
 *    completeness bar. Four kinds of gap have four different remedies and a
 *    single number would erase all four (`docs/proof-workspace.md` 5).
 * 5. **The share approval's terms are readable before the button.** It is
 *    single-use, it is bound to the bundle digest, it expires, and **a refused
 *    delivery spends it too**. A person who learns that after pressing was
 *    told too late (ADR-0009 4).
 * 6. **Nothing here is written to a path.** The bundle is handed to the
 *    browser through an object URL, exactly as the recovery file and the
 *    evidence export are. There is no directory to choose, so there is no
 *    traversal question to answer (ADR-0009 3).
 * 7. **Nothing here polls and nothing here sends.** Two reads on mount; every
 *    other request is inside a click (SI-272). No route on this surface can
 *    reach an outbound client.
 */

// --- vocabulary ------------------------------------------------------------

/** Which action a failure came from; only the plain reads repeat safely. */
type Step = "read" | "proof" | "prepare" | "share";

const ERROR_TITLE: Record<Step, string> = {
  read: "Gorev listesi okunamadi",
  proof: "Kanit calisma alani okunamadi",
  prepare: "Paylasim onayi hazirlanamadi",
  share: "Paket teslim edilemedi",
};

/**
 * The three claims, in the user's language.
 *
 * Keyed by the backend's own key so a fourth claim appearing on the wire is
 * rendered with its raw key rather than silently dropped: a claim this screen
 * does not recognise is still a claim the reader is entitled to see.
 */
const CLAIM_LABEL: Record<string, string> = {
  independent_check: "Bagimsiz kontrol",
  exit_code: "Gercek cikis kodu",
  test_result: "Test sonucu",
};

/** The download name. Client-side, fixed, never read from the response. */
const BUNDLE_FILENAME: Record<ProofBundleFormat, string> = {
  json: "technocore-station-kanit-paketi.json",
  markdown: "technocore-station-kanit-paketi.md",
};

const FORMAT_LABEL: Record<ProofBundleFormat, string> = {
  json: "JSON olarak indir",
  markdown: "Markdown olarak indir",
};

function claimLabel(claim: ProofClaimStatus): string {
  return CLAIM_LABEL[claim.key] ?? claim.key;
}

function shortId(value: string): string {
  return value === "" ? "(yok)" : value.slice(0, 12);
}

// --- panel -----------------------------------------------------------------

export function ProofWorkspacePanel() {
  const ids = useId();

  const [list, setList] = useState<TaskListResponse | null>(null);
  const [selected, setSelected] = useState("");
  const [proof, setProof] = useState<ProofWorkspace | null>(null);

  const [busy, setBusy] = useState<Step | null>(null);
  const [step, setStep] = useState<Step>("read");
  const [error, setError] = useState<ApiError | null>(null);

  // The approval. Held here and nowhere else: it is a capability, and a
  // capability in `localStorage` outlives the tab that earned it (SI-24).
  const [shareToken, setShareToken] = useState("");
  const [tokenDigest, setTokenDigest] = useState("");
  const [expiresIn, setExpiresIn] = useState(0);
  const [acknowledged, setAcknowledged] = useState(false);
  const [delivered, setDelivered] = useState<ProofBundleFormat | null>(null);
  const [spent, setSpent] = useState(false);

  const loadTasks = useCallback(async (): Promise<void> => {
    setBusy("read");
    setError(null);
    try {
      setList(await fetchTasks());
    } catch (caught) {
      setError(toApiError(caught));
      setStep("read");
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  /**
   * Forget the approval.
   *
   * Called whenever the bundle it was bound to may no longer be the bundle on
   * screen: a different task, a fresh read, a spent delivery. Holding a token
   * past that point would only produce a refusal the server has to explain.
   */
  function dropApproval(): void {
    setShareToken("");
    setTokenDigest("");
    setExpiresIn(0);
    setDelivered(null);
    setSpent(false);
    setAcknowledged(false);
  }

  async function openTask(taskId: string): Promise<void> {
    if (busy !== null) return;
    setSelected(taskId);
    dropApproval();
    setBusy("proof");
    setError(null);
    try {
      setProof(await fetchProof(taskId));
    } catch (caught) {
      setProof(null);
      setError(toApiError(caught));
      setStep("proof");
    } finally {
      setBusy(null);
    }
  }

  async function reread(): Promise<void> {
    if (busy !== null || selected === "") return;
    dropApproval();
    setBusy("proof");
    setError(null);
    try {
      setProof(await fetchProof(selected));
    } catch (caught) {
      setError(toApiError(caught));
      setStep("proof");
    } finally {
      setBusy(null);
    }
  }

  async function prepare(): Promise<void> {
    if (busy !== null || selected === "") return;
    setBusy("prepare");
    setError(null);
    try {
      const result = await prepareProofShare(selected);
      setProof(result.workspace);
      setShareToken(result.share_token);
      setTokenDigest(result.workspace.bundle_sha256);
      setExpiresIn(result.expires_in_seconds);
      setDelivered(null);
      setSpent(false);
    } catch (caught) {
      setError(toApiError(caught));
      setStep("prepare");
    } finally {
      setBusy(null);
    }
  }

  /**
   * Spend the approval and hand the file to the browser.
   *
   * `spent` is set before the request is awaited, because the token is spent
   * by the attempt rather than by its success. A surface that only marked it
   * spent on the happy path would leave a refused delivery looking retryable,
   * which is exactly the property ADR-0009 4 built the token to remove.
   */
  async function share(format: ProofBundleFormat): Promise<void> {
    if (busy !== null || selected === "" || shareToken === "" || !acknowledged) return;
    setBusy("share");
    setError(null);
    setSpent(true);
    try {
      const { blob } = await takeProofBundle({
        taskId: selected,
        shareToken,
        format,
        acknowledged: true,
      });
      // The recovery file's delivery, unchanged: a temporary object URL,
      // clicked and revoked at once, so nothing lingers in the document.
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = BUNDLE_FILENAME[format];
      anchor.click();
      URL.revokeObjectURL(url);
      setDelivered(format);
    } catch (caught) {
      setError(toApiError(caught));
      setStep("share");
    } finally {
      setShareToken("");
      setBusy(null);
    }
  }

  return (
    <section aria-label="Kanit calisma alani" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-foreground">Kanit calisma alani</h3>
        <StatusPill label="Toplanmis malzeme, sonuc degil" tone="inactive" />
      </div>

      {error !== null && (
        <ErrorRegion
          error={error}
          onRetry={
            step === "read"
              ? () => void loadTasks()
              : step === "proof"
                ? () => void reread()
                : undefined
          }
          retryPending={busy === "read" || busy === "proof"}
          section="Kanitlar / Kanit calisma alani"
          title={ERROR_TITLE[step]}
        />
      )}

      <TaskChooser
        busy={busy !== null}
        list={list}
        name={`${ids}-proof-task`}
        onOpen={(taskId) => void openTask(taskId)}
        selected={selected}
      />

      {proof !== null && (
        <>
          <Separator />

          {/* Reading again is a read: it writes nothing and sends nothing.
              It also **drops any approval held**, because an approval is
              bound to the bundle digest and the digest is exactly what a
              re-read may have changed (ADR-0009 4). */}
          <div>
            <Button
              data-testid="proof-reread"
              isDisabled={busy !== null}
              onPress={() => void reread()}
              size="sm"
              variant="secondary"
            >
              {busy === "proof"
                ? "Okunuyor..."
                : "Paketi yeniden oku (bekleyen onayi dusurur)"}
            </Button>
          </div>

          <HashScope proof={proof} />

          <Separator />
          <ArtifactRegion proof={proof} />

          <Separator />
          <MissingRegion proof={proof} />

          <Separator />
          <ClaimRegion proof={proof} />

          <Separator />
          <ShareRegion
            acknowledged={acknowledged}
            busy={busy}
            delivered={delivered}
            expiresIn={expiresIn}
            onAcknowledge={setAcknowledged}
            onPrepare={() => void prepare()}
            onShare={(format) => void share(format)}
            proof={proof}
            shareToken={shareToken}
            spent={spent}
            tokenDigest={tokenDigest}
          />
        </>
      )}
    </section>
  );
}

// --- choosing a task -------------------------------------------------------

function TaskChooser({
  list,
  selected,
  busy,
  name,
  onOpen,
}: {
  readonly list: TaskListResponse | null;
  readonly selected: string;
  readonly busy: boolean;
  readonly name: string;
  readonly onOpen: (taskId: string) => void;
}) {
  if (list === null) {
    return <p className="text-sm text-muted">Gorev listesi okunuyor...</p>;
  }

  if (list.tasks.length === 0) {
    return (
      <EmptyState
        description="Kanit paketi bir gorevin toplanmis malzemesidir, bu yuzden once bir gorev gerekir. Bu istasyonda henuz gorev acilmadi; Is Tara bolumunden bir aday yerel gorev olarak acilabilir."
        title="Paketi olusturulacak bir gorev yok"
      />
    );
  }

  return (
    <section aria-label="Paket icin gorev secimi" className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-foreground">
        {`Gorev secin (${String(list.task_count)})`}
      </h4>
      <ul className="flex flex-col gap-2">
        {list.tasks.map((entry) => (
          <li className="rounded-lg border border-border p-2" key={entry.id}>
            <label className="flex items-center gap-2">
              <input
                checked={selected === entry.id}
                disabled={busy}
                name={name}
                onChange={() => onOpen(entry.id)}
                type="radio"
                value={entry.id}
              />
              <span className="text-sm font-medium text-foreground">{entry.title}</span>
            </label>
            <span className="mt-1 block font-mono text-xs text-muted">
              {`${shortId(entry.id)} · modul ${entry.module_id} · durum ${entry.state}`}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- what a hash establishes -----------------------------------------------

/**
 * The sentence that has to be on screen before any digest is.
 *
 * Rendered above the artifacts rather than beneath them, and verbatim: this is
 * the wording the bundle itself carries, and the backend is its author.
 */
function HashScope({ proof }: { readonly proof: ProofWorkspace }) {
  return (
    <Alert status="warning">
      <Alert.Indicator />
      <Alert.Content>
        <Alert.Title>Bir ozet neyi belirler, neyi belirlemez</Alert.Title>
        <Alert.Description>
          <span className="flex flex-col gap-2">
            <span data-testid="proof-hash-scope">{proof.hash_scope}</span>
            <span data-testid="proof-bundle-scope">{proof.bundle_scope}</span>
            <span data-testid="proof-reproduction">{proof.reproduction}</span>
          </span>
        </Alert.Description>
      </Alert.Content>
    </Alert>
  );
}

// --- the produced files ----------------------------------------------------

function ArtifactRegion({ proof }: { readonly proof: ProofWorkspace }) {
  return (
    <section aria-label="Uretilen dosyalar" className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-foreground">Uretilen dosyalar</h4>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-2">
        <div className="flex justify-between gap-2">
          <dt>Dosya sayisi</dt>
          <dd className="font-mono">{String(proof.file_count)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Toplam bayt</dt>
          <dd className="font-mono">{String(proof.total_bytes)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Kume ozeti</dt>
          {/* Twelve characters. A full 64-hex run is the same shape as a seed
              and this app never renders one. */}
          <dd className="font-mono" data-testid="proof-artifact-set">
            {shortDigest(proof.artifact_set_sha256)}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Paket ozeti</dt>
          <dd className="font-mono" data-testid="proof-bundle-digest">
            {shortDigest(proof.bundle_sha256)}
          </dd>
        </div>
      </dl>

      {proof.artifacts.length === 0 ? (
        <p className="text-xs text-muted" data-testid="proof-artifacts-empty">
          Bu gorevin calisma alaninda hicbir dosya yok. Bu, isin yapilmadigi
          anlamina gelmez; yalnizca bu istasyonda kaydedilmis bir cikti
          olmadigi anlamina gelir ve eksikler asagida adiyla listelenir.
        </p>
      ) : (
        <ul className="flex flex-col gap-1" data-testid="proof-artifacts">
          {proof.artifacts.map((file) => (
            <li className="flex flex-col gap-1 rounded-lg border border-border p-2" key={file.name}>
              <span className="text-xs font-medium text-foreground">{file.name}</span>
              <span className="font-mono text-xs text-muted">
                {`${String(file.byte_count)} bayt · ozet ${shortDigest(file.sha256)}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- what is missing -------------------------------------------------------

/**
 * The gaps, each with its own name, state and remedy.
 *
 * There is no count and no proportion here on purpose, and the sentence says
 * so: an unfilled evidence field, an unmet module requirement, a run that did
 * not finish and a promised file that is not on disk are four different
 * problems, and a single number would let a reader treat them as one.
 */
function MissingRegion({ proof }: { readonly proof: ProofWorkspace }) {
  return (
    <section aria-label="Eksikler" className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-foreground">Eksikler</h4>

      <p className="text-xs text-muted" data-testid="proof-missing-rule">
        Eksikler adiyla listelenir. Burada puan, yuzde, tamamlanma orani veya
        tek bir rozet yoktur: dolmamis bir kanit alani, karsilanmamis bir modul
        gereksinimi, tamamlanmamis bir calisma ve soz verilip uretilmemis bir
        dosya dort ayri sorundur ve dordunun cozumu ayridir.
      </p>

      {proof.missing.length === 0 ? (
        <p className="text-xs text-muted" data-testid="proof-missing-none">
          Adlandirilmis bir eksik kalmadi. Bu, isin dogru veya yararli oldugu
          anlamina gelmez; yalnizca bu listenin dort kaynagindan hicbirinin
          acik bir kalem bildirmedigi anlamina gelir.
        </p>
      ) : (
        <ul className="flex flex-col gap-1" data-testid="proof-missing">
          {proof.missing.map((entry) => (
            <li
              className="flex flex-col gap-1 rounded-lg border border-border p-2"
              data-testid={`proof-missing-${entry.key}`}
              key={entry.key}
            >
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-medium text-foreground">{entry.key}</span>
                <StatusPill label={entry.state} tone="pending" />
              </span>
              <span className="text-xs text-muted">{entry.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- the records this build does not produce -------------------------------

/**
 * Three claims that stay empty, each with its own reason.
 *
 * Every one of them is rendered with an **inactive** pill and the literal
 * `not_implemented`, never with a tick and never with the word "dogrulandi".
 * That is the whole point of the region: a reader who skims must not be able
 * to come away thinking an independent party looked at this, or that a test
 * ran and passed.
 */
function ClaimRegion({ proof }: { readonly proof: ProofWorkspace }) {
  return (
    <section aria-label="Uretilmeyen kayitlar" className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-foreground">
        Uretilmeyen kayitlar (bos degil, &quot;uygulanmadi&quot;)
      </h4>

      <ul className="flex flex-col gap-2">
        {proof.claims.map((claim) => (
          <li
            className="flex flex-col gap-1 rounded-lg border border-border p-2"
            data-testid={`proof-claim-${claim.key}`}
            key={claim.key}
          >
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-foreground">{claimLabel(claim)}</span>
              {/* `inactive`, not `ok`. There is no tick anywhere in this list:
                  an unimplemented record rendered as a success glyph is the
                  single most likely way this screen could lie. */}
              <StatusPill label={`uygulanmadi (${claim.state})`} tone="inactive" />
            </span>
            <span className="text-xs text-muted">{claim.detail}</span>
          </li>
        ))}
      </ul>

      <p className="text-xs text-muted" data-testid="proof-claims-rule">
        Bu ucu de bir onay degildir ve onay yerine gecmez. Ayni kosmanin kendi
        ciktisi disaridan gelen bir gorus gibi sunulmaz; kosulmamis bir kod
        denenmis sayilmaz. Ucunun de kapali olma sebebi mimaridir ve
        yukarida yazilidir.
      </p>

      <p className="text-xs text-muted" data-testid="proof-publish-unreachable">
        Uc yayim alani ayri ayri dogrulanmis olsa bile gorevi &quot;Yayima
        hazir&quot; durumuna tasiyan bir kullanici yolu bu surumde yoktur.
        &quot;Yayima hazir&quot; kanittan turetilir, istenemez; bu ekranda onu
        isteyen bir dugme bulunmamasinin sebebi budur.
      </p>
    </section>
  );
}

// --- taking a copy ---------------------------------------------------------

function ShareRegion({
  proof,
  shareToken,
  tokenDigest,
  expiresIn,
  acknowledged,
  busy,
  delivered,
  spent,
  onAcknowledge,
  onPrepare,
  onShare,
}: {
  readonly proof: ProofWorkspace;
  readonly shareToken: string;
  readonly tokenDigest: string;
  readonly expiresIn: number;
  readonly acknowledged: boolean;
  readonly busy: Step | null;
  readonly delivered: ProofBundleFormat | null;
  readonly spent: boolean;
  readonly onAcknowledge: (next: boolean) => void;
  readonly onPrepare: () => void;
  readonly onShare: (format: ProofBundleFormat) => void;
}) {
  const stale = tokenDigest !== "" && tokenDigest !== proof.bundle_sha256;

  return (
    <section aria-label="Paketi disariya al" className="flex flex-col gap-3">
      <h4 className="text-xs font-semibold text-foreground">Paketi disariya al</h4>

      {/* The terms, before the control. A person who learns that a refused
          delivery also spends the token after pressing the button was told
          too late. */}
      <Alert status="warning">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Onay tek kullanimliktir ve pakete baglidir</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2" data-testid="proof-share-terms">
              <span>
                {`Onay bir kez harcanir ve ${String(
                  proof.approval_ttl_seconds,
                )} saniye sonra duser. Reddedilen bir teslim de onayi harcar: paket o arada degistigi icin reddedilse bile ayni onayla ikinci bir deneme yapilamaz.`}
              </span>
              <span>
                Onay paketin ozetine baglidir. Bir dosya degisirse ozet degisir
                ve eski onay artik eslesmez; boyle bir durumda yeni paketi
                okuyup yeni bir onay hazirlamaniz gerekir.
              </span>
              <span>
                Onay ayrica bu goreve ve bu tarayici oturumuna baglidir. Baska
                bir gorevin paketini teslim edemez.
              </span>
              <span>
                Paket bu makinede hicbir yola yazilmaz; dosya dogrudan
                tarayiciniza teslim edilir. Paylasilan dosya bu istasyonun
                topladigi malzemeyi tasir ve icindeki eksikler adiyla
                yazilidir.
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
          Onayin tek kullanimlik oldugunu, reddedilen bir teslimin de onayi
          harcadigini ve paketin bir sonuc degil toplanmis malzeme oldugunu
          anladim.
        </Checkbox.Content>
      </Checkbox>

      <div className="flex flex-wrap gap-2">
        <Button
          isDisabled={busy !== null}
          onPress={onPrepare}
          size="sm"
          variant="secondary"
        >
          {busy === "prepare" ? "Hazirlaniyor..." : "Tek kullanimlik onay hazirla"}
        </Button>

        {proof.formats.map((format) => (
          <Button
            isDisabled={busy !== null || shareToken === "" || !acknowledged}
            key={format}
            onPress={() => onShare(format)}
            size="sm"
            variant="secondary"
          >
            {busy === "share" ? "Teslim ediliyor..." : FORMAT_LABEL[format]}
          </Button>
        ))}
      </div>

      <p className="text-xs text-muted" data-testid="proof-share-state">
        {shareToken !== ""
          ? `Onay hazir ve harcanmadi. ${String(
              expiresIn,
            )} saniye gecerli; bagli oldugu paket ozeti ${shortDigest(tokenDigest)}.`
          : spent
            ? "Onay harcandi. Yeni bir teslim icin yeniden onay hazirlamaniz gerekir; ayni onay ikinci kez kullanilamaz."
            : "Henuz onay hazirlanmadi. Onay hazirlamak hicbir sey teslim etmez ve hicbir sey gondermez; yalnizca paketin o andaki ozetine bagli bir izin uretir."}
      </p>

      {stale && (
        <p className="text-xs text-muted" data-testid="proof-share-stale">
          Ekrandaki paketin ozeti, onayin bagli oldugu ozetten farkli. Bu onay
          artik eslesmez; yeni paketi okuyup yeni bir onay hazirlayin.
        </p>
      )}

      {delivered !== null && (
        <p className="text-xs text-muted" data-testid="proof-share-result">
          {`Dosya tarayiciya verildi: ${BUNDLE_FILENAME[delivered]}. Sunucu hicbir yola dosya yazmadi ve hicbir yere bir sey gondermedi; indirme tamamen tarayicinizdadir.`}
        </p>
      )}
    </section>
  );
}
