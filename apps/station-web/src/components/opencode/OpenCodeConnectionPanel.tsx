import { Alert, Button, Card, Checkbox, Separator } from "@heroui/react";
import { useCallback, useEffect, useId, useState } from "react";

import {
  ApiError,
  fetchOpenCodeStatus,
  forgetOpenCodeCredential,
  refreshOpenCodeCatalog,
  selectOpenCodeModel,
  storeOpenCodeCredential,
  toApiError,
} from "../../api/client";
import type { OpenCodeModel, OpenCodeStatus } from "../../api/types";
import { ErrorRegion } from "../ErrorRegion";
import { PassphraseField } from "../identity/IdentityDialogs";
import { StatusPill, type StatusTone } from "../StatusPill";

/**
 * The OpenCode Go connection: the one surface in this product that accepts a
 * provider API key.
 *
 * Six rules shape everything below, and none of them is cosmetic.
 *
 * 1. **The key goes in once and never comes back.** It lives in this
 *    component's state for the length of one request, is wiped the moment
 *    that request succeeds, and there is no control anywhere that shows,
 *    masks, partially reveals or copies a stored key - because there is no
 *    route that returns one. What the user sees afterwards is a twelve
 *    character fingerprint and two timestamps (ADR-0005 7).
 * 2. **Nothing here is persisted by the browser.** Not the key, not the
 *    chosen model, not a "remember me" of any kind (SI-24). The selected
 *    model is a backend setting; this panel only asks for it.
 * 3. **Checking the connection produces no green badge.** The provider's
 *    catalog answers without a key, a GET on a protocol path answers 404,
 *    and this build makes no metered call on its own. The strongest honest
 *    verdict is "saved, not verified", carried with *every* reason it is not
 *    stronger (ADR-0005 4). The tone table below has no `ok` entry, so the
 *    rule is structural rather than a habit.
 * 4. **Listed is not callable.** A model with no published protocol family
 *    is shown, with its reason, and cannot be picked. There is no fallback:
 *    a refused model is a refusal, never a quiet substitution (ADR-0005 5).
 * 5. **A data-sharing term is acknowledged, not defaulted.** A model whose
 *    retention says training use is `yes` - or `unknown`, which is treated
 *    identically - is never preselected and needs an explicit extra consent
 *    before it can be chosen.
 * 6. **No figure is invented.** Published limits are shown as published, an
 *    absent cost is `unknown` and never zero, and the subscription is never
 *    called unlimited. The provider's own sentences arrive from the backend
 *    and are rendered verbatim so the wording cannot drift between the two
 *    surfaces.
 */

/** Which action a failure came from; only the plain read is safe to repeat. */
type Step = "read" | "check" | "save" | "forget" | "refresh" | "select";

type Busy = Step | null;

const ERROR_TITLE: Record<Step, string> = {
  read: "Baglanti durumu okunamadi",
  check: "Baglanti durumu okunamadi",
  save: "Anahtar kaydedilemedi",
  forget: "Anahtar kaldirilamadi",
  refresh: "Model listesi yenilenemedi",
  select: "Model secilemedi",
};

/**
 * The connection verdict, as labels and tones.
 *
 * There is deliberately no `ok` tone in this table and no `verified` state to
 * give one to. A single green pill is exactly the reduction ADR-0005 4
 * forbids, and the cheapest way to make that impossible is to leave the
 * colour out of the mapping rather than out of the review checklist.
 */
const CHECK_LABEL: Record<OpenCodeStatus["check"]["state"], string> = {
  not_configured: "Anahtar kaydedilmedi",
  never_checked: "Henuz denetlenmedi",
  key_saved_unverified: "Anahtar kaydedildi, dogrulanmadi",
};

const CHECK_TONE: Record<OpenCodeStatus["check"]["state"], StatusTone> = {
  not_configured: "inactive",
  never_checked: "pending",
  key_saved_unverified: "pending",
};

const CATALOG_LABEL: Record<OpenCodeStatus["catalog"]["state"], string> = {
  never_fetched: "Liste henuz cekilmedi",
  ok: "Liste okundu",
  fetch_error: "Listeye erisilemedi",
  parse_error: "Liste cozumlenemedi",
};

const CATALOG_TONE: Record<OpenCodeStatus["catalog"]["state"], StatusTone> = {
  never_fetched: "inactive",
  ok: "ok",
  fetch_error: "problem",
  parse_error: "problem",
};

/**
 * How the provider's training term is spoken.
 *
 * `unknown` says "bilinmiyor" and nothing else. Rendering an unknown or stale
 * privacy term as "saklanmiyor" would be a reassurance this build has not
 * earned, and it is the exact sentence a user would rely on when deciding
 * what to hand a model.
 */
const TRAINING_LABEL: Record<OpenCodeModel["training_use"], string> = {
  yes: "Egitim icin kullaniliyor",
  no: "Egitim icin kullanilmiyor",
  unknown: "Egitim kullanimi bilinmiyor",
};

const TRAINING_TONE: Record<OpenCodeModel["training_use"], StatusTone> = {
  yes: "problem",
  no: "ok",
  unknown: "pending",
};

const PROTOCOL_VERIFICATION_LABEL: Record<OpenCodeModel["protocol_verification"], string> = {
  documented: "belgelenmis eslesme",
  unverified: "dogrulanmamis eslesme",
};

function formatDate(value: string | null): string {
  if (value === null) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

/**
 * Rebuild an error without the server's prose.
 *
 * Used on the two calls that manage the credential, and only on those. A
 * backend or an upstream can, in principle, quote a submitted value back
 * inside a message - a validation error naming the bad input is the ordinary
 * way that happens - and `ErrorRegion` renders `userMessage` verbatim. Here
 * the message is replaced by the stable machine code, which makes `ApiError`
 * fall back to its own safe catalogue sentence for the failure class. The
 * code, the HTTP status, the failure class and the request id all survive,
 * so the redacted diagnostics payload is exactly as useful as it was; the
 * only thing dropped is the one field that could carry the key.
 *
 * The other three calls keep their prose: neither the catalog refresh nor
 * the model selection sends a credential, and their messages ("this model
 * has no published protocol family") are the whole point of the refusal.
 */
function withoutServerProse(error: ApiError): ApiError {
  return new ApiError(error.status, error.code, {
    kind: error.kind,
    requestId: error.requestId,
  });
}

export function OpenCodeConnectionPanel() {
  const ids = useId();
  const [status, setStatus] = useState<OpenCodeStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // The provider key. Local to this component, wiped on success, and never
  // lifted into a store, a context or a browser-side cache.
  const [apiKey, setApiKey] = useState("");
  const [editing, setEditing] = useState(false);

  // The pending selection. Deliberately empty on mount rather than seeded
  // from `selected_model`: this group is "the change you are about to make",
  // and starting it empty is what makes "no model - least of all a training
  // model - is chosen by default" true of the markup and not just the copy.
  const [pendingModel, setPendingModel] = useState("");
  const [trainingAck, setTrainingAck] = useState(false);

  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<Step>("read");

  const load = useCallback(async (as: "read" | "check"): Promise<void> => {
    setLoading(true);
    setBusy(as);
    try {
      setStatus(await fetchOpenCodeStatus());
      setError(null);
    } catch (caught) {
      setError(toApiError(caught));
      setStep(as);
    } finally {
      setLoading(false);
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    void load("read");
  }, [load]);

  async function save(): Promise<void> {
    // Double-click guard. Two stores of the same key would write the envelope
    // twice, and the second write would race the first one's atomic replace.
    if (busy !== null || apiKey.length === 0) return;
    setBusy("save");
    setError(null);
    try {
      const next = await storeOpenCodeCredential(apiKey);
      // The key was needed for exactly this request and for nothing after it.
      // Wiping before the next render is what makes "it does not stay on the
      // screen" a property of the code rather than a promise in the copy.
      setApiKey("");
      setEditing(false);
      setStatus(next);
    } catch (caught) {
      // The value is kept on failure - and only on failure - so a dropped
      // connection does not force the user to fetch the key from the provider
      // console and type it again. It is still gone the moment a store
      // succeeds, which is what ADR-0001 6 asks for.
      setError(withoutServerProse(toApiError(caught)));
      setStep("save");
    } finally {
      setBusy(null);
    }
  }

  async function forget(): Promise<void> {
    if (busy !== null) return;
    setBusy("forget");
    setError(null);
    try {
      const next = await forgetOpenCodeCredential();
      setApiKey("");
      setEditing(false);
      setStatus(next);
    } catch (caught) {
      setError(withoutServerProse(toApiError(caught)));
      setStep("forget");
    } finally {
      setBusy(null);
    }
  }

  async function refresh(): Promise<void> {
    if (busy !== null) return;
    setBusy("refresh");
    setError(null);
    try {
      setStatus(await refreshOpenCodeCatalog());
    } catch (caught) {
      setError(toApiError(caught));
      setStep("refresh");
    } finally {
      setBusy(null);
    }
  }

  async function select(): Promise<void> {
    if (busy !== null || pendingModel === "") return;
    setBusy("select");
    setError(null);
    try {
      const next = await selectOpenCodeModel({
        modelId: pendingModel,
        // Passed through from the checkbox, never defaulted to true here.
        trainingAcknowledged: trainingAck,
      });
      setStatus(next);
      setPendingModel("");
      setTrainingAck(false);
    } catch (caught) {
      setError(toApiError(caught));
      setStep("select");
    } finally {
      setBusy(null);
    }
  }

  /** Changing the pick drops the consent that covered the previous pick. */
  function choose(modelId: string): void {
    setPendingModel(modelId);
    setTrainingAck(false);
  }

  if (status === null) {
    return (
      <Card>
        <Card.Header>
          <Card.Title>OpenCode Go baglantisi</Card.Title>
        </Card.Header>
        <Card.Content className="flex flex-col gap-3">
          {error === null ? (
            <p className="text-sm text-muted">Baglanti durumu okunuyor...</p>
          ) : (
            <ErrorRegion
              error={error}
              onRetry={() => void load("read")}
              retryPending={loading}
              section="Ayarlar ve Yardim / OpenCode Go baglantisi"
              title={ERROR_TITLE[step]}
            />
          )}
        </Card.Content>
      </Card>
    );
  }

  const { catalog, check, protocol_context: protocols, spending } = status;
  const models = catalog.models;
  const pending = models.find((model) => model.model_id === pendingModel) ?? null;
  const needsAck = pending?.requires_training_acknowledgement ?? false;
  const canSelect =
    busy === null && pending !== null && pending.selectable && (!needsAck || trainingAck);
  const showField = !status.configured || editing;

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Card.Title>OpenCode Go baglantisi</Card.Title>
          <StatusPill label={CHECK_LABEL[check.state]} tone={CHECK_TONE[check.state]} />
        </div>
        <Card.Description>
          Saglayici API anahtariniz burada kaydedilir. Bu ekranda anahtar yalniz
          yazilir; kaydedildikten sonra ne bu sayfada kalir ne de herhangi bir
          yoldan geri gosterilebilir.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        {error !== null && (
          <ErrorRegion
            error={error}
            onRetry={step === "read" ? () => void load("read") : undefined}
            retryPending={busy === "read"}
            section="Ayarlar ve Yardim / OpenCode Go baglantisi"
            title={ERROR_TITLE[step]}
          />
        )}

        {/* --- credential ---------------------------------------------- */}
        <section aria-label="Saglayici anahtari" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Saglayici anahtari</h3>

          {status.configured ? (
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Kayitli anahtar</dt>
                <dd className="font-mono">{`parmak izi ${status.fingerprint_short}`}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Ilk kayit</dt>
                <dd className="font-mono">{formatDate(status.configured_at)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted">Son guncelleme</dt>
                <dd className="font-mono">{formatDate(status.updated_at)}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted">
              Henuz bir anahtar kaydedilmedi. Anahtari saglayicinin kendi
              konsolundan alip asagiya yazin.
            </p>
          )}

          <p className="text-xs text-muted" id={`${ids}-key-hint`}>
            Parmak izi, hangi anahtarin kurulu oldugunu tanimak icindir; anahtarin
            kendisinden bir parca degildir ve ondan geri hesaplanamaz. Kaydedilmis
            anahtari gosteren veya kopyalayan bir kontrol bilerek yoktur, cunku onu
            dondurecek bir uc nokta da yoktur.
          </p>

          {showField && (
            <div className="flex flex-col gap-2">
              <PassphraseField
                autoComplete="off"
                describedBy={`${ids}-key-hint`}
                label="OpenCode Go API anahtari"
                onChange={setApiKey}
                value={apiKey}
              />
              <p className="text-xs text-muted">
                Anahtar ayni-origin yerel servise bir kez iletilir ve Windows DPAPI
                zarfinda saklanir. Panoya kopyalanmaz, bildirim metnine yazilmaz,
                hicbir tani veya olcum kaydina girmez.
              </p>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {showField && (
              <Button isDisabled={busy !== null || apiKey.length === 0} onPress={() => void save()}>
                {busy === "save" ? "Kaydediliyor..." : "Anahtari kaydet"}
              </Button>
            )}
            {status.configured && !editing && (
              <Button isDisabled={busy !== null} onPress={() => setEditing(true)} variant="secondary">
                Anahtari degistir
              </Button>
            )}
            {status.configured && editing && (
              <Button
                isDisabled={busy !== null}
                onPress={() => {
                  setApiKey("");
                  setEditing(false);
                }}
                variant="secondary"
              >
                Vazgec
              </Button>
            )}
            <Button isDisabled={busy !== null} onPress={() => void load("check")} variant="secondary">
              {busy === "check" ? "Denetleniyor..." : "Baglantiyi denetle"}
            </Button>
            {status.configured && (
              <Button isDisabled={busy !== null} onPress={() => void forget()} variant="ghost">
                {busy === "forget" ? "Kaldiriliyor..." : "Baglantiyi kaldir"}
              </Button>
            )}
          </div>
        </section>

        <Separator />

        {/* --- what the check can and cannot say ------------------------ */}
        <section aria-label="Baglanti denetimi" className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">Baglanti denetimi</h3>
            <StatusPill label={CHECK_LABEL[check.state]} tone={CHECK_TONE[check.state]} />
          </div>
          <p className="text-sm">{check.detail}</p>
          <p className="text-xs text-muted">
            &quot;Baglantiyi denetle&quot; yeni bir dogrulama uretmez ve yesil bir
            rozetle sonuclanmaz: yerel servisin bu anahtar hakkinda dururken
            soyleyebildigi seyi yeniden okur. Anahtarin bicimi dogru diye gecerli
            sayilmaz; ucretli gercek bir cagri bu surumde kendiliginden yapilmaz.
          </p>
          <ul className="flex flex-col gap-1">
            {check.reasons.map((reason) => (
              <li className="text-xs text-muted" key={reason}>
                {`• ${reason}`}
              </li>
            ))}
          </ul>
        </section>

        <Separator />

        {/* --- honesty about the wire ----------------------------------- */}
        <section aria-label="Sozlesme notlari" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Sozlesme notlari</h3>

          <Alert status="warning">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Kimlik dogrulama basligi dogrulanmadi</Alert.Title>
              <Alert.Description>{status.auth_header_caveat}</Alert.Description>
            </Alert.Content>
          </Alert>

          <Alert status="default">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>
                {protocols.tool_calls_supported
                  ? "Akis bu surumde yok; arac cagrisi olculdu"
                  : "Akis ve arac cagrisi bu surumde yok"}
              </Alert.Title>
              <Alert.Description>
                <span className="flex flex-col gap-2">
                  <span>{protocols.deferral}</span>
                  <span>{protocols.shape_provenance}</span>
                  {/* `streaming_supported` is `false` as a *type* and the
                      word beside it therefore cannot drift. `tool_calls_supported`
                      is a plain `bool` since ADR-0012 measured the contract, so
                      its word is **read from the value** rather than written
                      out: the panel used to print "arac cagrisi: yok"
                      unconditionally, which stayed on screen after the wire
                      started saying otherwise. */}
                  <span className="font-mono text-xs" data-testid="opencode-protocol-summary">
                    {`Protokol aileleri: ${protocols.protocols.join(", ")} · akis: yok · arac cagrisi: ${
                      protocols.tool_calls_supported ? "olculdu" : "yok"
                    }`}
                  </span>
                  {/* Empty until something is measured. A supported format
                      with no provenance beside it would be exactly the
                      unsourced claim ADR-0005 1.2 refuses, so the sentence
                      travels with the capability rather than under it. */}
                  {protocols.tool_call_provenance !== "" && (
                    <span data-testid="opencode-tool-call-provenance">
                      {protocols.tool_call_provenance}
                    </span>
                  )}
                </span>
              </Alert.Description>
            </Alert.Content>
          </Alert>

          <Alert status="default">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Anahtarin bagli olmasi dosya paylasimi demek degildir</Alert.Title>
              <Alert.Description>
                Kaydedilmis bir anahtar, bilgisayarinizdaki dosyalarin modele
                gonderilebilecegi anlamina gelmez. Bir gorevde modelle hangi
                kaynaklarin paylasilacagi, gorev baslamadan once o gorevin kendi
                ekraninda tek tek gorunur.
              </Alert.Description>
            </Alert.Content>
          </Alert>
        </section>

        <Separator />

        {/* --- catalog and selection ------------------------------------ */}
        <section aria-label="Model katalogu" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">Model katalogu</h3>
              <StatusPill
                label={CATALOG_LABEL[catalog.state]}
                tone={CATALOG_TONE[catalog.state]}
              />
            </div>
            <Button isDisabled={busy !== null} onPress={() => void refresh()} variant="secondary">
              {busy === "refresh" ? "Yenileniyor..." : "Modelleri yenile"}
            </Button>
          </div>

          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            <div className="flex justify-between gap-2">
              <dt className="text-muted">Listenin okundugu an</dt>
              <dd className="font-mono">{formatDate(catalog.models_fetched_at)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted">Son deneme</dt>
              <dd className="font-mono">{formatDate(catalog.fetched_at)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted">Model sayisi</dt>
              <dd className="font-mono">
                {`${String(catalog.model_count)} listelendi · ${String(catalog.selectable_count)} secilebilir`}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted">Secili model</dt>
              <dd className="font-mono">
                {status.selected_model === "" ? "secilmedi" : status.selected_model}
              </dd>
            </div>
          </dl>

          {catalog.detail !== "" && (
            <p className="text-xs text-muted">
              {`Son okuma: ${catalog.detail}${
                catalog.http_status === 0 ? "" : ` (HTTP ${String(catalog.http_status)})`
              }`}
            </p>
          )}

          {catalog.drift_notice !== "" && (
            <Alert data-testid="opencode-catalog-drift" status="warning">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title>Model tablosu bayat olabilir</Alert.Title>
                <Alert.Description>{catalog.drift_notice}</Alert.Description>
              </Alert.Content>
            </Alert>
          )}

          <p className="text-xs text-muted">{catalog.listing_caveat}</p>

          {/* Not conditional on anything going wrong: the pinned table's age
              is a property of every reading of it, and a provenance line that
              only appears alongside a problem is one nobody ever reads. */}
          <p className="text-xs text-muted" data-testid="opencode-table-provenance">
            {catalog.table_provenance}
          </p>

          <p className="text-xs text-muted">
            Liste yalniz siz istediginizde yenilenir. Saglayicinin acik katalogu
            gorunur ad, baglam/cikti limiti ve arac destegi alanlarini
            dondurmez; bu surum onlari uydurmaz ve bos birakir. Protokol
            eslemesi ise derleme zamani kapali bir tablodan gelir.
          </p>

          {models.length === 0 ? (
            <p className="text-sm text-muted">
              Henuz model listelenmedi. &quot;Modelleri yenile&quot; ile
              saglayicinin acik katalogunu okuyabilirsiniz.
            </p>
          ) : (
            <fieldset className="flex max-h-96 flex-col gap-2 overflow-y-auto">
              <legend className="text-sm font-medium text-foreground">
                Kullanilacak model
              </legend>
              {models.map((model) => (
                <label
                  className="flex items-start gap-2 rounded-lg border border-border p-3"
                  data-selectable={model.selectable}
                  key={model.model_id}
                >
                  <input
                    checked={pendingModel === model.model_id}
                    disabled={!model.selectable || busy !== null}
                    name={`${ids}-model`}
                    onChange={() => choose(model.model_id)}
                    type="radio"
                    value={model.model_id}
                  />
                  <span className="flex flex-col gap-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm">{model.model_id}</span>
                      <span className="text-xs text-muted">{model.owned_by}</span>
                      <StatusPill
                        label={TRAINING_LABEL[model.training_use]}
                        tone={TRAINING_TONE[model.training_use]}
                      />
                    </span>
                    <span className="text-xs text-muted">
                      {`Protokol: ${model.protocol === "" ? "yayimlanmamis" : model.protocol} · ${
                        PROTOCOL_VERIFICATION_LABEL[model.protocol_verification]
                      }`}
                    </span>
                    <span className="text-xs text-muted">
                      {`Veri saklama: ${model.retention} · kaynak: ${model.privacy_source} · okundugu tarih: ${model.privacy_read_on}`}
                    </span>
                    {!model.selectable && (
                      <span className="text-xs text-danger">
                        {`Secilemez: ${model.reason}`}
                      </span>
                    )}
                    {model.selectable && model.requires_training_acknowledgement && (
                      <span className="text-xs text-danger">
                        Bu model ek paylasim onayi ister; varsayilan olarak
                        secilmez.
                      </span>
                    )}
                  </span>
                </label>
              ))}
            </fieldset>
          )}

          {needsAck && (
            <Alert status="warning">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title>Ek paylasim onayi gerekiyor</Alert.Title>
                <Alert.Description>
                  <span className="flex flex-col gap-2">
                    <span>
                      {`Bu modelin yayimlanmis veri isleme kosulu: ${
                        pending?.retention ?? "-"
                      } (${TRAINING_LABEL[pending?.training_use ?? "unknown"]}). Kaynak: ${
                        pending?.privacy_source ?? "-"
                      }, okundugu tarih: ${pending?.privacy_read_on ?? "-"}.`}
                    </span>
                    <Checkbox isSelected={trainingAck} onChange={setTrainingAck}>
                      <Checkbox.Content>
                        <Checkbox.Control>
                          <Checkbox.Indicator />
                        </Checkbox.Control>
                        Bu modele gonderdiklerimin egitim icin kullanilabilecegini
                        anliyorum ve paylasmayi kabul ediyorum.
                      </Checkbox.Content>
                    </Checkbox>
                  </span>
                </Alert.Description>
              </Alert.Content>
            </Alert>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button isDisabled={!canSelect} onPress={() => void select()}>
              {busy === "select" ? "Seciliyor..." : "Modeli sec"}
            </Button>
          </div>

          <p className="text-xs text-muted">
            Secim kalici bir ayardir ve yerel servis tarafinda tutulur; tarayici
            tarafinda hicbir yere yazilmaz. Ancak secilmis olmak erisimi
            kanitlamaz: erisim ve yetenekler her calistirmanin basinda yeniden
            dogrulanir. Secilen model sessizce baska bir modele veya saglayiciya
            cevrilmez.
          </p>
        </section>

        <Separator />

        {/* --- spending context ----------------------------------------- */}
        <section aria-label="Kota ve maliyet" className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">Kota ve maliyet</h3>
            {/* `budget_available` is `false` as a type. There is no branch
                here because there is no state in which this build opens a
                budget (ADR-0005 9). */}
            <StatusPill label="Butce bu surumde yok" tone="inactive" />
          </div>

          <ul className="flex flex-col gap-1">
            {spending.limits.map((limit) => (
              <li
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2"
                key={limit.window}
              >
                <span className="text-xs text-muted">{limit.note}</span>
                <span className="font-mono text-xs">
                  {`${limit.window}: ${String(limit.amount_usd)} USD`}
                </span>
              </li>
            ))}
          </ul>

          <p className="text-xs text-muted">{spending.limit_behaviour}</p>
          <p className="text-xs text-muted">{spending.use_balance}</p>
          <p className="text-xs text-muted">{spending.local_counter_caveat}</p>
          <p className="text-xs text-muted">{spending.unknown_cost_sentence}</p>
        </section>
      </Card.Content>
    </Card>
  );
}
