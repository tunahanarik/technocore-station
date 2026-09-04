import { Alert, Button, Checkbox, Input, Label, Separator, TextArea, TextField } from "@heroui/react";
import { useCallback, useEffect, useId, useState } from "react";

import {
  type ApiError,
  createComposeDraft,
  fetchComposeCapability,
  sendComposeMessage,
  signComposeDraft,
  toApiError,
} from "../../api/client";
import type {
  ComposeCapability,
  ComposeDraft,
  ComposeSendResult,
  ComposeSignature,
} from "../../api/types";
import { shortDigest } from "../../lib/digest";
import { gateReasonLabel } from "../../lib/identityGuidance";
import { ErrorRegion } from "../ErrorRegion";
import { PassphraseField } from "../identity/IdentityDialogs";
import { StatusPill, type StatusTone } from "../StatusPill";

/**
 * The composer: the only surface in this product that can write outwards.
 *
 * Four rules shape everything below, and none of them is cosmetic.
 *
 * 1. **Three steps, three approvals, in order.** Preparing a draft is not
 *    signing, and signing is **not** sending (charter 7.4, ADR-0002 2). Each
 *    step is a separate request and a separate, irreversible act, so the send
 *    control does not exist until a signature exists.
 * 2. **Changing the content drops every approval.** Editing the text or the
 *    room clears the draft, the signature and the send token, and says why.
 *    The token lives in this component's state and nowhere else, so once it is
 *    cleared there is no way for stale bytes to be published.
 * 3. **The result has three values, never two.** `outcome_unknown` means the
 *    server may have stored the message. It is presented as exactly that, with
 *    no retry control: retrying blind would risk publishing twice and this
 *    release has no room read to reconcile with (ADR-0002 3).
 * 4. **Nothing remote is active content.** The server's response excerpt is
 *    rendered as plain, unclickable text - no anchor, no markup (SI-54).
 *
 * The passphrase, when the vault needs one, lives in local state for the
 * length of one signing act and is wiped as soon as the step is left.
 */

const OUTCOME_TITLE: Record<ComposeSendResult["outcome"], string> = {
  accepted: "Kabul edildi",
  refused: "Reddedildi",
  outcome_unknown: "Sonuc bilinmiyor: sunucu yazmis olabilir",
};

const OUTCOME_TONE: Record<ComposeSendResult["outcome"], StatusTone> = {
  accepted: "ok",
  refused: "problem",
  outcome_unknown: "pending",
};

/** Which step a failure came from; only the read is safe to repeat. */
type ErrorStep = "capability" | "draft" | "sign" | "send";

type Busy = "draft" | "sign" | "send" | null;

const ERROR_TITLE: Record<ErrorStep, string> = {
  capability: "Gonderim yetkisi okunamadi",
  draft: "Taslak hazirlanamadi",
  sign: "Imzalanamadi",
  send: "Gonderim tamamlanamadi",
};

export function ComposerPanel({
  needsVaultPassphrase,
}: {
  /** True when the vault is passphrase-protected: signing will ask for it. */
  readonly needsVaultPassphrase: boolean;
}) {
  const ids = useId();
  const [capability, setCapability] = useState<ComposeCapability | null>(null);
  const [capabilityLoading, setCapabilityLoading] = useState(true);

  const [room, setRoom] = useState("");
  const [text, setText] = useState("");
  const [draft, setDraft] = useState<ComposeDraft | null>(null);
  const [sweepSeen, setSweepSeen] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [signature, setSignature] = useState<ComposeSignature | null>(null);
  const [result, setResult] = useState<ComposeSendResult | null>(null);
  const [dropped, setDropped] = useState(false);

  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [errorStep, setErrorStep] = useState<ErrorStep>("capability");

  const loadCapability = useCallback(async (): Promise<void> => {
    setCapabilityLoading(true);
    try {
      setCapability(await fetchComposeCapability());
      setError(null);
    } catch (caught) {
      setError(toApiError(caught));
      setErrorStep("capability");
    } finally {
      setCapabilityLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCapability();
  }, [loadCapability]);

  /**
   * Editing the content invalidates every approval that covered the old
   * content, and says so.
   *
   * This is the mechanism, not a reminder: the send token is dropped here, and
   * it is the only copy. There is no path from "changed the text" to "sent the
   * previous bytes", because after this call there is nothing left to send.
   * The passphrase goes with it - it was collected for a signing act that no
   * longer exists.
   */
  function dropApprovals(): void {
    if (draft === null && signature === null) return;
    setDraft(null);
    setSignature(null);
    setPassphrase("");
    setSweepSeen(false);
    setResult(null);
    setDropped(true);
  }

  function onRoomChange(next: string): void {
    setRoom(next);
    dropApprovals();
  }

  function onTextChange(next: string): void {
    setText(next);
    dropApprovals();
  }

  async function prepareDraft(): Promise<void> {
    if (busy !== null) return;
    setBusy("draft");
    setError(null);
    setDropped(false);
    setResult(null);
    try {
      const prepared = await createComposeDraft({ room, text });
      setDraft(prepared);
      setSweepSeen(false);
    } catch (caught) {
      setError(toApiError(caught));
      setErrorStep("draft");
    } finally {
      setBusy(null);
    }
  }

  async function sign(): Promise<void> {
    if (draft === null || busy !== null) return;
    setBusy("sign");
    setError(null);
    try {
      const signed = await signComposeDraft({
        draftId: draft.draft_id,
        draftDigest: draft.draft_digest,
        vaultPassphrase: needsVaultPassphrase ? passphrase : null,
      });
      setSignature(signed);
      // The passphrase was needed for exactly this call. Nothing later in the
      // chain uses it, so it does not stay in state waiting to be leaked.
      setPassphrase("");
    } catch (caught) {
      setError(toApiError(caught));
      setErrorStep("sign");
    } finally {
      setBusy(null);
    }
  }

  async function send(): Promise<void> {
    if (signature === null || busy !== null) return;
    const token = signature.send_token;
    setBusy("send");
    setError(null);
    try {
      setResult(await sendComposeMessage(token));
    } catch (caught) {
      setError(toApiError(caught));
      setErrorStep("send");
    } finally {
      setBusy(null);
      // The approval is single-use and the nonce is spent whatever happened -
      // including a failure whose outcome we never learned. Tearing the chain
      // down here is what makes a second attempt a deliberate re-draft and
      // re-signature rather than a second click.
      setSignature(null);
      setDraft(null);
      setSweepSeen(false);
      setPassphrase("");
    }
  }

  const counterId = `${ids}-counter`;
  const rangeErrorId = `${ids}-range`;
  const roomHintId = `${ids}-room-hint`;

  const minChars = capability?.min_chars ?? 0;
  const maxChars = capability?.max_chars ?? 0;
  const typed = text.length;
  // The sweep can only ever make text shorter, so raw text below the minimum
  // can never reach it and is refused here. Above the maximum is different:
  // the sweep may well bring it under, and the effective limit is applied
  // server-side to the *swept* text. Warning without blocking keeps the
  // backend the authority instead of guessing on its behalf.
  const tooShort = text.trim().length < minChars;
  const overMax = maxChars > 0 && typed > maxChars;
  const roomGiven = room.trim().length > 0;

  if (capabilityLoading && capability === null && error === null) {
    return <p className="text-sm text-muted">Gonderim yetkisi okunuyor...</p>;
  }

  if (capability === null) {
    return (
      <section aria-label="Gonderim yetkisi" className="flex flex-col gap-3">
        {error !== null && (
          <ErrorRegion
            error={error}
            onRetry={() => void loadCapability()}
            retryPending={capabilityLoading}
            section="Olustur ve Dogrula / Gonderim yetkisi"
            title={ERROR_TITLE.capability}
          />
        )}
      </section>
    );
  }

  return (
    <section aria-label="Gonderim akisi" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-foreground">Gonderim akisi</h3>
        <StatusPill
          label={capability.can_compose ? "Acik" : "Kapali"}
          tone={capability.can_compose ? "ok" : "inactive"}
        />
      </div>

      <p className="text-xs text-muted">
        {`Yazma yolu: ${capability.write_method} ${capability.write_path_template}`}
        {" — bu yolu istemci secmez, sunucu bildirir. Reddedilen odalar: "}
        {capability.denied_rooms.join(", ")}.
      </p>

      {error !== null && errorStep === "capability" && (
        <ErrorRegion
          error={error}
          onRetry={() => void loadCapability()}
          retryPending={capabilityLoading}
          section="Olustur ve Dogrula / Gonderim yetkisi"
          title={ERROR_TITLE.capability}
        />
      )}

      {!capability.can_compose ? (
        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Gonderim kapali</Alert.Title>
            <Alert.Description>
              <span className="flex flex-col gap-2">
                <span>
                  Bu yuzeyde metin alani ve gonderim kontrolu yoktur, cunku
                  asagidaki on kosullar tamamlanmamistir. Devre disi bir buton
                  bir guvenlik kontrolu degildir; kapali kapi sunucudadir ve uc
                  adimin ucu de ayni kapiyi yeniden kosar.
                </span>
                <span className="flex flex-col gap-1">
                  {capability.blocking_reasons.map((reason) => (
                    <span className="text-xs" key={reason}>
                      {`• ${gateReasonLabel(reason)}`}
                    </span>
                  ))}
                </span>
              </span>
            </Alert.Description>
          </Alert.Content>
        </Alert>
      ) : (
        <>
          {dropped && (
            <Alert status="warning">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title>Onceki onay dusuruldu</Alert.Title>
                <Alert.Description>
                  Metin veya hedef oda degisti. Eski taslak, imza ve gonderim
                  onayi yalniz eski icerigi kapsiyordu; ucu de silindi. Yeni
                  icerik icin yeniden taslak hazirlayip yeniden imzalamaniz
                  gerekir.
                </Alert.Description>
              </Alert.Content>
            </Alert>
          )}

          <section aria-label="Adim 1: Taslak" className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-sm font-semibold text-foreground">1. Taslak</h4>
              <StatusPill
                label={draft === null ? "Bekliyor" : "Hazir"}
                tone={draft === null ? "pending" : "ok"}
              />
            </div>

            <TextField className="w-full" onChange={onRoomChange} value={room}>
              <Label>Hedef oda</Label>
              <Input
                aria-describedby={roomHintId}
                autoComplete="off"
                variant="secondary"
              />
            </TextField>
            <p className="text-xs text-muted" id={roomHintId}>
              Oda adi sunucunun yayimladigi sinif isaretlerine gore dogrulanir;
              tahmin edilmez. Bu surumde gercek bir gonderim yapmadan once
              hedefi dikkatle kontrol edin.
            </p>

            <TextField
              className="w-full"
              isInvalid={overMax}
              onChange={onTextChange}
              value={text}
            >
              <Label>Mesaj metni</Label>
              <TextArea
                aria-describedby={overMax ? `${counterId} ${rangeErrorId}` : counterId}
                aria-invalid={overMax ? true : undefined}
                rows={6}
                variant="secondary"
              />
            </TextField>
            <p className="text-xs text-muted" id={counterId}>
              {`${String(typed)} / ${String(maxChars)} karakter (en az ${String(minChars)}). Sinirlar sunucunun yayimladigi etkin degerlerdir.`}
            </p>
            {overMax && (
              <p className="text-xs text-danger" id={rangeErrorId}>
                {`Metin ust siniri asiyor: ${String(typed)} karakter, en fazla ${String(maxChars)}. Supurme metni kisaltabilir, ama son karari sunucu supurulmus metin uzerinde verir.`}
              </p>
            )}

            <div>
              <Button
                isDisabled={busy !== null || tooShort || !roomGiven}
                onPress={() => void prepareDraft()}
              >
                {busy === "draft" ? "Hazirlaniyor..." : "Taslagi hazirla"}
              </Button>
            </div>

            {error !== null && errorStep === "draft" && (
              <ErrorRegion
                error={error}
                section="Olustur ve Dogrula / Taslak"
                title={ERROR_TITLE.draft}
              />
            )}
          </section>

          {draft !== null && (
            <>
              <Separator />
              <section aria-label="Adim 2: Imza onayi" className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm font-semibold text-foreground">
                    2. Imza onayi
                  </h4>
                  <StatusPill
                    label={signature === null ? "Bekliyor" : "Imzalandi"}
                    tone={signature === null ? "pending" : "ok"}
                  />
                </div>

                <SweepReview draft={draft} onSeen={setSweepSeen} seen={sweepSeen} />

                {draft.target_notes.length > 0 && (
                  <ul className="flex flex-col gap-1">
                    {draft.target_notes.map((note) => (
                      <li className="text-xs text-muted" key={note}>
                        {`• ${note}`}
                      </li>
                    ))}
                  </ul>
                )}

                {needsVaultPassphrase && signature === null && (
                  <PassphraseField
                    autoComplete="current-password"
                    label="Kasa parolasi (imzalamak icin)"
                    onChange={setPassphrase}
                    value={passphrase}
                  />
                )}

                <p className="text-xs text-muted">
                  Imzalamak gondermek degildir. Bu adim yalniz nonce ayirir,
                  kanonik bicimi kurar ve imzalar; gonderim ayri ve tek
                  kullanimlik bir onay ister.
                </p>

                <div>
                  <Button
                    isDisabled={
                      busy !== null ||
                      signature !== null ||
                      (draft.changed_by_sweep && !sweepSeen)
                    }
                    onPress={() => void sign()}
                  >
                    {busy === "sign" ? "Imzalaniyor..." : "Imzala"}
                  </Button>
                </div>

                {error !== null && errorStep === "sign" && (
                  <ErrorRegion
                    error={error}
                    section="Olustur ve Dogrula / Imza onayi"
                    title={ERROR_TITLE.sign}
                  />
                )}
              </section>
            </>
          )}

          {signature !== null && (
            <>
              <Separator />
              <SendApprovalStep
                busy={busy}
                onSend={() => void send()}
                signature={signature}
              />
            </>
          )}

          {error !== null && errorStep === "send" && (
            <div className="flex flex-col gap-3">
              <ErrorRegion
                error={error}
                section="Olustur ve Dogrula / Gonderim"
                title={ERROR_TITLE.send}
              />
              {(error.kind === "timeout" ||
                error.kind === "network" ||
                error.kind === "canceled") && (
                <Alert status="warning">
                  <Alert.Indicator />
                  <Alert.Content>
                    <Alert.Title>Bu sonuc bilinmiyor</Alert.Title>
                    <Alert.Description>
                      Istek yerel servise ulasamadi veya yaniti alinamadi. Bunu
                      &quot;gonderilmedi&quot; olarak sunmak yanlis olur: sunucu
                      mesaji yazmis olabilir. Onay harcanmistir; yeniden
                      gondermek yeni bir taslak ve yeni bir imza onayi ister.
                    </Alert.Description>
                  </Alert.Content>
                </Alert>
              )}
            </div>
          )}

          {result !== null && <SendResultRegion result={result} />}
        </>
      )}

      <Separator />

      <section aria-label="Not gonderimi" className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold text-foreground">
          Neden not gonderimi yok?
        </h4>
        {/* The backend's own sentence, shown rather than paraphrased: the
            absence is a decision (ADR-0002 1), not a missing button. */}
        <p className="text-xs text-muted">{capability.note_lane_detail}</p>
      </section>
    </section>
  );
}

/**
 * The sweep difference, and the gate that makes the user look at it.
 *
 * When the sweep changed the text, what gets signed is not what was typed.
 * Signing without having seen the difference would mean approving bytes the
 * user never read, so the acknowledgement is a precondition of the signing
 * button rather than a note beside it.
 */
function SweepReview({
  draft,
  seen,
  onSeen,
}: {
  readonly draft: ComposeDraft;
  readonly seen: boolean;
  readonly onSeen: (next: boolean) => void;
}) {
  if (!draft.changed_by_sweep) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-xs text-muted">
          {`Supurme metni degistirmedi: ${String(draft.swept_chars)} karakter. Asagidaki metin imzalanacak metindir.`}
        </p>
        <pre className="overflow-x-auto rounded-lg border border-border p-3 font-mono text-xs whitespace-pre-wrap">
          {draft.swept_text}
        </pre>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Alert status="warning">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Gorunmez karakterler silindi</Alert.Title>
          <Alert.Description>
            {`Supurme metni degistirdi: ${String(draft.raw_chars)} karakterden ${String(draft.swept_chars)} karaktere indi. Gorunmez ve protokolce kabul edilmeyen karakterler cikarildi. Imzalanacak ve gonderilecek olan supurulmus metindir; yazdiginiz ham metin degil.`}
          </Alert.Description>
        </Alert.Content>
      </Alert>

      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium text-foreground">Yazdiginiz</span>
        <pre className="overflow-x-auto rounded-lg border border-border p-3 font-mono text-xs whitespace-pre-wrap">
          {draft.raw_text}
        </pre>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium text-foreground">
          Gonderilecek (supurulmus)
        </span>
        <pre className="overflow-x-auto rounded-lg border border-border p-3 font-mono text-xs whitespace-pre-wrap">
          {draft.swept_text}
        </pre>
      </div>

      <Checkbox isSelected={seen} onChange={onSeen}>
        <Checkbox.Content>
          <Checkbox.Control>
            <Checkbox.Indicator />
          </Checkbox.Control>
          Ham metin ile gonderilecek metin arasindaki farki gordum.
        </Checkbox.Content>
      </Checkbox>
    </div>
  );
}

/**
 * Step 3: the separate, single-use send approval.
 *
 * The countdown is not decoration. The approval expires, and a button that
 * still looks live after it has expired would invite a click that can only
 * fail. When the timer reaches zero the control disables itself and says why.
 */
function SendApprovalStep({
  signature,
  busy,
  onSend,
}: {
  readonly signature: ComposeSignature;
  readonly busy: Busy;
  readonly onSend: () => void;
}) {
  const [secondsLeft, setSecondsLeft] = useState(signature.expires_in_seconds);

  useEffect(() => {
    setSecondsLeft(signature.expires_in_seconds);
    const timer = window.setInterval(() => {
      setSecondsLeft((previous) => (previous <= 1 ? 0 : previous - 1));
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [signature]);

  const expired = secondsLeft <= 0;

  return (
    <section aria-label="Adim 3: Gonderim onayi" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold text-foreground">3. Gonderim onayi</h4>
        <StatusPill
          label={expired ? "Suresi doldu" : `${String(secondsLeft)} saniye`}
          tone={expired ? "problem" : "pending"}
        />
      </div>

      <p className="text-xs text-muted">
        Asagidaki metin, imzanin kapsadigi kanonik dizenin tam kendisidir.
        Gosterilen ile imzalanan aynidir; gonderim bu baytlari yayimlar.
      </p>
      <pre className="overflow-x-auto rounded-lg border border-border p-3 font-mono text-xs whitespace-pre-wrap">
        {signature.canonical}
      </pre>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-2">
        <div className="flex justify-between gap-2">
          <dt>Hedef oda</dt>
          <dd className="font-mono">{signature.room}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Nonce</dt>
          <dd className="font-mono">{signature.nonce}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Kanonik ozet</dt>
          <dd className="font-mono">{shortDigest(signature.canonical_digest)}</dd>
        </div>
      </dl>

      {expired ? (
        <Alert status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Onay suresi doldu</Alert.Title>
            <Alert.Description>
              Bu gonderim onayi tek kullanimliktir ve suresi sinirlidir; sure
              doldugu icin artik gonderim yapamaz. Unutulmus bir onayin saatler
              sonra ateslenebilmesi istenmez. Yeniden imzalayarak yeni bir onay
              alin.
            </Alert.Description>
          </Alert.Content>
        </Alert>
      ) : (
        <p className="text-xs text-muted">
          Bu onay tek kullanimliktir. Gonderim denemesi sonuc ne olursa olsun
          nonce&apos;u harcar; yeniden gondermek yeni bir onay ister.
        </p>
      )}

      <div>
        <Button isDisabled={busy !== null || expired} onPress={onSend} variant="danger">
          {busy === "send" ? "Gonderiliyor..." : "Onayla ve gonder"}
        </Button>
      </div>
    </section>
  );
}

/**
 * The three-valued outcome, presented as three different things.
 *
 * There is no retry control in any branch. For `refused` a retry would be
 * refused again; for `outcome_unknown` a retry could publish the message a
 * second time, and this release cannot read the room to find out which
 * happened (ADR-0002 3).
 */
function SendResultRegion({ result }: { readonly result: ComposeSendResult }) {
  const unknown = result.outcome === "outcome_unknown";
  const duplicate = result.outcome === "refused" && result.http_status === 422;

  return (
    <section aria-label="Gonderim sonucu" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold text-foreground">Gonderim sonucu</h4>
        {/* The pill carries the stable machine value; the alert below carries
            the sentence. Repeating the sentence here would only make the two
            drift apart later. */}
        <StatusPill label={result.outcome} tone={OUTCOME_TONE[result.outcome]} />
      </div>

      <Alert
        status={
          result.outcome === "accepted"
            ? "success"
            : result.outcome === "refused"
              ? "danger"
              : "warning"
        }
      >
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>{OUTCOME_TITLE[result.outcome]}</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2">
              <span>{result.detail}</span>
              {unknown && (
                <span>
                  Bu sonuc ne &quot;gonderildi&quot; ne de &quot;basarisiz&quot;
                  demektir: sunucu mesaji yazmis olabilir. Ayni metni yeniden
                  yollarsaniz oda iki kopya tasiyabilir.
                </span>
              )}
              {unknown && result.reconciliation_required && (
                <span>
                  Uzlastirma odayi okumayi gerektirir ve oda okuma yolu bu
                  surumde acilmadi. Bu yuzden durum oldugu gibi birakiliyor;
                  Station sizin adiniza tahmin yurutmez.
                </span>
              )}
              {duplicate && (
                <span>
                  Ayni metin yakin zamanda yazilmis. Ayni baytlari yeniden
                  yollamak tekrar reddedilir; gonderi tekrarlanabilir degildir.
                </span>
              )}
              <span className="font-mono text-xs">
                {`Sonuc: ${result.outcome} · HTTP: ${result.http_status === 0 ? "-" : String(result.http_status)} · Oda: ${result.room} · Nonce: ${result.nonce} · Ozet: ${shortDigest(result.canonical_digest)}`}
              </span>
            </span>
          </Alert.Description>
        </Alert.Content>
      </Alert>

      {result.response_excerpt !== "" && (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-foreground">
            Sunucu yanitindan alinti (duz metin)
          </span>
          {/* Remote bytes. Rendered as text inside a <pre>, never as markup and
              never as a link: Technocore content is data, not active content
              (SI-54). */}
          <pre className="overflow-x-auto rounded-lg border border-border p-3 font-mono text-xs whitespace-pre-wrap">
            {result.response_excerpt}
          </pre>
        </div>
      )}

      <p className="text-xs text-muted">
        Onay harcandi ve nonce yeniden kullanilmaz. Yeni bir gonderim yeni bir
        taslak ve yeni bir imza onayi gerektirir; otomatik tekrar yoktur.
      </p>
    </section>
  );
}
