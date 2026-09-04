import { Alert, Button, Card, Checkbox, Separator } from "@heroui/react";
import { useCallback, useEffect, useId, useState } from "react";

import {
  type ApiError,
  WORK_SCAN_MAX_ROOMS,
  fetchWorkScanStatus,
  refreshWorkScanRooms,
  scanWorkRooms,
  suggestWorkScanCandidate,
  toApiError,
} from "../../api/client";
import type {
  WorkScanAdapter,
  WorkScanAdapterFact,
  WorkScanCandidate,
  WorkScanResult,
  WorkScanRoomIndex,
  WorkScanStaleness,
  WorkScanStatus,
  WorkScanSuggestion,
} from "../../api/types";
import { ErrorRegion } from "../ErrorRegion";
import { StatusPill } from "../StatusPill";

/**
 * "Is Tara": read a set of public rooms the user chose, and propose work from
 * what was actually read.
 *
 * Seven rules shape this surface, and every one of them is about not saying
 * more than the data supports.
 *
 * 1. **Nothing here polls.** There is no `setInterval`, no `setTimeout`, no
 *    background task and no auto-refresh. `fetchWorkScanStatus` runs once on
 *    mount and contacts nobody; every outbound read happens inside a click.
 *    A test asserts that no timer is ever installed, because a comment saying
 *    "we do not poll" is a promise and a counted timer is evidence
 *    (ADR-0007 4).
 * 2. **The scope is the user's room set.** The overview from `/rooms` is a
 *    list to choose from, not a queue to work through. Nothing scans the room
 *    universe, and the checkbox list is the whole addressable surface: room
 *    names go to the backend, which puts each one through the write path's
 *    policy - Lobby included - before it resolves an address.
 * 3. **The limit of a deterministic derivation is on screen.** The backend's
 *    own sentence - pattern matching, no semantic inference, so not every
 *    opportunity in a room is seen - is rendered on *every* read, above the
 *    results rather than under a fold (ADR-0007 2).
 * 4. **No staleness threshold is invented.** What is shown is the measured
 *    moment of the reading and the bound the *service* declares about itself.
 *    The ring-drop signal is shown separately, because "the list may be three
 *    seconds old" and "messages you never read are gone" are two different
 *    findings and one must not stand in for the other (ADR-0007 5).
 * 5. **The word "open" is not used.** Element 8 is the backend's sentence
 *    with the moment of the reading in it. There is no boolean badge anywhere
 *    on this surface, and there is no field to build one from.
 * 6. **Room content is community input, and it is data.** A quote is rendered
 *    as preformatted text - never markup, never a link. A `from` that is not
 *    a `did:key` is shown as a self-asserted nickname. A `topic` is a
 *    world-writable note and says so.
 * 7. **No third party's number becomes one of our sentences.** The single
 *    external record on this surface is a description of a service that was
 *    never contacted, its unverified column is shown beside its verified one,
 *    and its own disclaimer is quoted rather than paraphrased (ADR-0007 1).
 */

/** Which action a failure came from; only the plain read repeats safely. */
type Step = "read" | "rooms" | "scan" | "suggest";

type Busy = Step | null;

const ERROR_TITLE: Record<Step, string> = {
  read: "Tarama yuzeyi okunamadi",
  rooms: "Oda listesi okunamadi",
  scan: "Tarama tamamlanamadi",
  suggest: "Aday gorev olarak acilamadi",
};

/**
 * The four signals the backend recognises, in the user's language.
 *
 * A lookup with a fallback rather than an exhaustive `Record`: `signal`
 * arrives as a plain string, and a value this table does not know is shown as
 * it came rather than dropped or renamed into the nearest match.
 */
const SIGNAL_LABEL: Record<string, string> = {
  help_wanted: "yardim cagrisi",
  defect_report: "hata bildirimi",
  review_request: "inceleme istegi",
  documentation_gap: "belge eksigi",
};

/** How far an external service was taken. Never "supported": none is. */
const SUPPORT_LABEL: Record<string, string> = {
  support_unverified: "Destek dogrulanamadi",
  declined: "Incelendi ve elendi",
  unexamined: "Henuz incelenmedi",
};

/**
 * Kibble's own two sentences, in the language it wrote them in.
 *
 * They are constants here because the wire carries only the Turkish rendering
 * of them (`self_description`), and ADR-0007 1 asks for the service's own
 * words. A translated disclaimer is a weaker disclaimer, so both are shown:
 * the quotation, and the Turkish sentence the backend sends beside it.
 *
 * Transcribed from ADR-0007 1, which recorded them from the service's own
 * landing page on 2026-09-04. They are quotations, not claims of ours.
 */
const KIBBLE_SELF_DESCRIPTION = "Kibble is not FLOP Network and not Technocore. It settles nothing.";
const KIBBLE_SCORE_DESCRIPTION = "Advisory IOU from the public tape. Nothing is paid.";

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

/**
 * The staleness line that goes with a snapshot the service declared a bound
 * for.
 *
 * Rendered unconditionally, never behind a condition: a note that only
 * appeared when something looked wrong would be a note nobody ever reads, and
 * there is no threshold here that could decide when to show it.
 */
function StalenessLine({
  staleness,
  testId,
}: {
  readonly staleness: WorkScanStaleness;
  readonly testId: string;
}) {
  return (
    <p className="text-xs text-muted" data-testid={testId}>
      {`${staleness.detail} Olculen okuma ani: ${formatDate(staleness.read_at)}. Sunucunun kendi beyani: ${String(
        staleness.declared_cache_seconds,
      )} saniye (kaynak: ${staleness.declared_by}).`}
    </p>
  );
}

/** One verified/unverified fact row. The state travels with the sentence. */
function FactList({ facts, label }: { readonly facts: readonly WorkScanAdapterFact[]; readonly label: string }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs font-medium text-foreground">
        {`${label} (${String(facts.length)})`}
      </p>
      <ul className="flex flex-col gap-1">
        {facts.map((fact) => (
          <li className="text-xs text-muted" key={fact.key}>
            {`• ${fact.key}: ${fact.detail}`}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The external service record.
 *
 * Two columns and both of them shown. A record that listed only what worked
 * would be the "reporting an absence as full support" failure the charter
 * names, and the unverified column is the entire reason no adapter exists.
 */
function AdapterRecord({ adapter }: { readonly adapter: WorkScanAdapter }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground">{adapter.name}</span>
        <StatusPill label={SUPPORT_LABEL[adapter.support] ?? adapter.support} tone="pending" />
        {/* `adapter_written` and `contacted` are `false` as types, so these
            two pills have no branch behind them and cannot drift. */}
        <StatusPill label="Adapter yazilmadi" tone="inactive" />
        <StatusPill label="Hicbir istek gonderilmedi" tone="inactive" />
      </div>

      <p className="font-mono text-xs text-muted">
        {`Beyan edilen kaynak: ${adapter.declared_origin} · otorite seviyesi ${String(adapter.authority)} (topluluk)`}
      </p>

      <FactList facts={adapter.verified} label="Dogrulanan" />
      <FactList facts={adapter.unverified} label="Dogrulanamayan" />

      {/* The service's own words, quoted. Preformatted and unlinked like every
          other piece of foreign text on this surface. */}
      <blockquote className="flex flex-col gap-1 border-l-2 border-border pl-3">
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground">
          {KIBBLE_SELF_DESCRIPTION}
        </pre>
        <pre className="whitespace-pre-wrap break-words font-mono text-xs text-foreground">
          {KIBBLE_SCORE_DESCRIPTION}
        </pre>
        <span className="text-xs text-muted">
          Servisin kendi ifadeleri, yazildigi dilde. Asagidaki Turkce cumle
          yerel servisten geldigi gibi gosterilir.
        </span>
      </blockquote>

      <p className="text-xs text-muted">{adapter.self_description}</p>
      <p className="text-xs text-muted" data-testid="workscan-score-caveat">
        {adapter.score_caveat}
      </p>
      <p className="text-xs text-muted" data-testid="workscan-adapter-provenance">
        {adapter.provenance}
      </p>
    </div>
  );
}

/**
 * One candidate, with all eight elements on screen.
 *
 * Nothing is collapsed and nothing is omitted. The backend cannot produce a
 * candidate that is missing one of these, and a UI that hid one would undo
 * that guarantee at the last step: the elements a reader would skip - the
 * risks, the permissions, the estimate's basis - are exactly the ones that
 * decide whether accepting the suggestion is a good idea.
 */
function CandidateCard({
  candidate,
  disabled,
  groupName,
  onChoose,
  selected,
}: {
  readonly candidate: WorkScanCandidate;
  readonly disabled: boolean;
  readonly groupName: string;
  readonly onChoose: (id: string) => void;
  readonly selected: boolean;
}) {
  const { capability, effort, open_state: openState, source } = candidate;

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2">
          <input
            checked={selected}
            disabled={disabled}
            name={groupName}
            onChange={() => onChoose(candidate.id)}
            type="radio"
            value={candidate.id}
          />
          <span className="text-sm font-medium text-foreground">
            {`Aday: ${SIGNAL_LABEL[candidate.signal] ?? candidate.signal}`}
          </span>
        </label>
        <StatusPill label="Topluluk icerigi (seviye 3)" tone="pending" />
      </div>

      <section aria-label={`1. Birebir alinti - ${source.reference}`} className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">1. Birebir alinti ve kaynak</h4>
        {/* Data, not markup and not a link. `pre` keeps it verbatim, and there
            is no anchor, no auto-linking and no `dangerouslySetInnerHTML`
            anywhere on this surface (SI-54). */}
        <pre
          className="whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-2 font-mono text-xs text-foreground"
          data-testid="workscan-quote"
        >
          {source.quote}
        </pre>
        <p className="font-mono text-xs text-muted">
          {`Kaynak: ${source.reference} · oda ${source.room} · sira ${String(source.seq)} · zaman ${source.ts}`}
        </p>
        <p className="font-mono text-xs text-muted">
          {`Yazar: ${source.author === "" ? "(bos)" : source.author} · ${
            source.author_is_did_key ? "did:key kalibina uyuyor" : "kendi beyan ettigi takma ad"
          }`}
        </p>
        <p className="text-xs text-muted">{source.author_detail}</p>
      </section>

      <section aria-label="2. Kime faydasi var" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">2. Kime faydasi var</h4>
        <p className="text-xs text-muted">{candidate.benefit}</p>
      </section>

      <section aria-label="3. Teslimat" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">3. Teslimat</h4>
        <p className="text-xs text-muted">{candidate.deliverable}</p>
      </section>

      <section aria-label="4. Basari kosulu ve testi" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">4. Basari kosulu ve nasil test edilecegi</h4>
        <p className="text-xs text-muted">{candidate.success_condition}</p>
        <p className="text-xs text-muted">{candidate.test_method}</p>
      </section>

      <section aria-label="5. Arac ve veri yetkinligi" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">
          5. Agent bu ise yetecek araca ve veriye sahip mi
        </h4>
        <p className="text-xs text-muted">{capability.detail}</p>
        <p className="font-mono text-xs text-muted">
          {`Modul: ${capability.module_id} (${capability.module_state}) · modul var: ${
            capability.module_available ? "evet" : "hayir"
          } · yazma kapisi: ${capability.write_gate_open ? "acik" : "kapali"} · ikisi birden: ${
            capability.ready ? "evet" : "hayir"
          }`}
        </p>
      </section>

      <section aria-label="6. Calisma tahmini ve butce" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">6. Calisma tahmini ve butce</h4>
        <p className="text-xs text-muted" data-testid="workscan-effort">
          {`Bu bir ${effort.label}tir, olcum degildir: ${effort.band}.`}
        </p>
        <p className="text-xs text-muted">{effort.basis}</p>
        <p className="text-xs text-muted" data-testid="workscan-budget">
          {`Butce durumu: ${candidate.budget_state}. ${candidate.budget_detail}`}
        </p>
      </section>

      <section aria-label="7. Izinler ve riskler" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">7. Gereken izinler ve riskler</h4>
        <ul className="flex flex-col gap-1">
          {candidate.permissions.map((permission) => (
            <li className="text-xs text-muted" key={permission}>{`• Izin: ${permission}`}</li>
          ))}
          {candidate.risks.map((risk) => (
            <li className="text-xs text-muted" key={risk}>{`• Risk: ${risk}`}</li>
          ))}
        </ul>
      </section>

      <section aria-label="8. Aciklik notu" className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">8. Isin durumu hakkinda soylenebilecek</h4>
        {/* The one permitted wording, rendered as it arrives. There is no
            badge here and no boolean to build one from. */}
        <p className="text-xs text-muted" data-testid="workscan-open-state">
          {openState.detail}
        </p>
        <p className="font-mono text-xs text-muted">
          {`Anlik goruntunun okundugu an: ${formatDate(openState.read_at)}`}
        </p>
      </section>

      <p className="font-mono text-xs text-muted">
        {`Uretim yontemi: ${candidate.derivation} · aday kimligi: ${candidate.id.slice(0, 12)}`}
      </p>
    </li>
  );
}

/** The room overview, and the checkboxes that make the scope the user's. */
function RoomChooser({
  busy,
  chosen,
  index,
  onToggle,
}: {
  readonly busy: boolean;
  readonly chosen: readonly string[];
  readonly index: WorkScanRoomIndex;
  readonly onToggle: (room: string) => void;
}) {
  const atLimit = chosen.length >= WORK_SCAN_MAX_ROOMS;

  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-xs text-muted">
        {`Servisin bildirdigi toplam: ${String(index.total)} · burada tutulan: ${String(
          index.kept_count,
        )} · kirpildi mi: ${index.truncated ? "evet" : "hayir"} · belge ozeti: ${index.sha256.slice(0, 12)}`}
      </p>
      <StalenessLine staleness={index.staleness} testId="workscan-staleness-rooms" />
      <p className="text-xs text-muted">{index.room_name_caveat}</p>
      <p className="text-xs text-muted" data-testid="workscan-topic-caveat">
        {`${index.topic_caveat} Bir baslik bir onay degildir ve odanin ne oldugunu kanitlamaz.`}
      </p>

      {index.rooms.length === 0 ? (
        <p className="text-sm text-muted">
          Listede oda yok. Bu, taranacak bir sey olmadigi anlamina gelmez;
          yalnizca bu okumada oda listelenmedigi anlamina gelir.
        </p>
      ) : (
        <fieldset className="flex max-h-96 flex-col gap-2 overflow-y-auto">
          <legend className="text-sm font-medium text-foreground">
            {`Taranacak odalar (secili: ${String(chosen.length)} / en cok ${String(WORK_SCAN_MAX_ROOMS)})`}
          </legend>
          {index.rooms.map((room) => {
            const isChosen = chosen.includes(room.name);
            return (
              <div className="rounded-lg border border-border p-2" key={room.name}>
                <Checkbox
                  isDisabled={busy || (!isChosen && atLimit)}
                  isSelected={isChosen}
                  onChange={() => onToggle(room.name)}
                >
                  <Checkbox.Content>
                    <Checkbox.Control>
                      <Checkbox.Indicator />
                    </Checkbox.Control>
                    {room.name}
                  </Checkbox.Content>
                </Checkbox>
                <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-xs text-muted">
                  {room.topic === "" ? "(baslik yok)" : `baslik: ${room.topic}`}
                </pre>
              </div>
            );
          })}
        </fieldset>
      )}

      {atLimit && (
        <p className="text-xs text-muted">
          {`Tek bir taramada en cok ${String(
            WORK_SCAN_MAX_ROOMS,
          )} oda okunur. Kalan odalari ayri bir taramayla secebilirsiniz.`}
        </p>
      )}
    </div>
  );
}

/** What one scan produced, room by room, including what it could not read. */
function ScanReport({ scan }: { readonly scan: WorkScanResult }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="font-mono text-xs text-muted" data-testid="workscan-staleness-scan">
        {`Bu tarama ${formatDate(scan.started_at)} ile ${formatDate(
          scan.completed_at,
        )} arasinda, bir kez okundu. Okunan oda sayisi: ${String(scan.rooms.length)} · aday: ${String(
          scan.candidate_count,
        )} · reddedilen satir: ${String(scan.refusal_count)}.`}
      </p>
      <p className="text-xs text-muted">
        Bu yanit oda mesajlari icin sunucunun kendi bayatlik beyanini
        tasimiyor; yukaridaki degerler bu istasyonun olctugu okuma anlaridir.
        Sunucunun uc saniyelik beyani oda listesi icindir ve oda listesinin
        kendi anlik goruntusuyle birlikte gosterilir. Bir esik uydurulmadi.
      </p>

      {/* Separate from the staleness line above, and deliberately so: "the
          list may be a few seconds old" and "messages you never read are
          gone" are different findings, and folding the second into the first
          would turn a concrete loss into a general caveat (ADR-0007 5). */}
      <Alert data-testid="workscan-ring-drop" status="default">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Halka dususu ayri bir sinyaldir</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-1">
              <span>
                Bu yanitta halka (ring) dususu sinyali yok. Tarama imlecsiz
                yapilir: &quot;since&quot; gonderilmez, ve sunucunun
                &quot;first_seq &gt; since + 1&quot; sinyali ancak imlecli bir
                okumada uretilir.
              </span>
              <span>
                Okunmamis mesajlarin halkadan dusmus olmasi bayatliktan ayri
                bir olaydir ve burada ayri gosterilir; birine bakip digerini
                varsaymayin.
              </span>
            </span>
          </Alert.Description>
        </Alert.Content>
      </Alert>

      {scan.failures.length > 0 && (
        <Alert data-testid="workscan-failures" status="warning">
          <Alert.Indicator />
          <Alert.Content>
            <Alert.Title>Okunamayan odalar</Alert.Title>
            <Alert.Description>
              <span className="flex flex-col gap-1">
                <span>
                  Asagidaki odalar okunamadi. Bu, o odalarda is olmadigi
                  anlamina gelmez; okunmadiklari anlamina gelir.
                </span>
                {scan.failures.map((failure) => (
                  <span className="font-mono text-xs" key={`${failure.room}-${failure.reason}`}>
                    {`${failure.room} · ${failure.reason} · ${failure.detail}`}
                  </span>
                ))}
              </span>
            </Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      <ul className="flex flex-col gap-2">
        {scan.results.map((result) => (
          <li className="rounded-lg border border-border p-2" key={result.room}>
            <p className="font-mono text-xs text-muted">
              {`${result.room} · okunan satir: ${String(result.lines_read)} · aday: ${String(
                result.candidates.length,
              )} · reddedilen: ${String(result.refusals.length)}`}
            </p>
            {result.refusals.map((refusal) => (
              <p className="text-xs text-muted" key={`${refusal.room}-${String(refusal.seq)}`}>
                {`• Reddedildi (${refusal.shape}, sira ${String(refusal.seq)}): ${refusal.detail}`}
              </p>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function WorkScanPanel() {
  const ids = useId();
  const [status, setStatus] = useState<WorkScanStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<Step>("read");

  // The scope, and the only addressable thing this surface sends. Plain React
  // state: never a browser store, and never seeded from one (SI-24).
  const [chosen, setChosen] = useState<readonly string[]>([]);
  const [candidateId, setCandidateId] = useState("");
  const [suggestion, setSuggestion] = useState<WorkScanSuggestion | null>(null);

  /**
   * The one read that runs without a click.
   *
   * Safe precisely because it contacts nobody: it reports what a previous
   * user-initiated read found, or that none has run. It is not scheduled, not
   * repeated and not retried on its own.
   */
  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setBusy("read");
    try {
      setStatus(await fetchWorkScanStatus());
      setError(null);
    } catch (caught) {
      setError(toApiError(caught));
      setStep("read");
    } finally {
      setLoading(false);
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function readRooms(): Promise<void> {
    // Double-click guard. Two overviews in flight would spend two reads from
    // a per-IP bucket to learn the same thing.
    if (busy !== null) return;
    setBusy("rooms");
    setError(null);
    try {
      const next = await refreshWorkScanRooms();
      setStatus(next);
      // A room that is no longer listed must not stay in the scope: the next
      // scan would name a room this reading did not offer.
      const listed = new Set((next.room_index?.rooms ?? []).map((room) => room.name));
      setChosen((current) => current.filter((room) => listed.has(room)));
    } catch (caught) {
      setError(toApiError(caught));
      setStep("rooms");
    } finally {
      setBusy(null);
    }
  }

  async function scan(): Promise<void> {
    if (busy !== null || chosen.length === 0) return;
    setBusy("scan");
    setError(null);
    setSuggestion(null);
    try {
      setStatus(await scanWorkRooms(chosen));
      // Candidate identities belong to one scan. Keeping the previous pick
      // would let a stale identifier be submitted against a new reading.
      setCandidateId("");
    } catch (caught) {
      setError(toApiError(caught));
      setStep("scan");
    } finally {
      setBusy(null);
    }
  }

  async function suggest(): Promise<void> {
    if (busy !== null || candidateId === "") return;
    setBusy("suggest");
    setError(null);
    try {
      setSuggestion(await suggestWorkScanCandidate(candidateId));
    } catch (caught) {
      setError(toApiError(caught));
      setStep("suggest");
    } finally {
      setBusy(null);
    }
  }

  function toggleRoom(room: string): void {
    setChosen((current) =>
      current.includes(room)
        ? current.filter((name) => name !== room)
        : current.length >= WORK_SCAN_MAX_ROOMS
          ? current
          : [...current, room],
    );
  }

  if (status === null) {
    return (
      <Card>
        <Card.Header>
          <Card.Title>Is tarama</Card.Title>
        </Card.Header>
        <Card.Content className="flex flex-col gap-3">
          {error === null ? (
            <p className="text-sm text-muted">Tarama yuzeyi okunuyor...</p>
          ) : (
            <ErrorRegion
              error={error}
              onRetry={() => void load()}
              retryPending={loading}
              section="Is Tara / Tarama yuzeyi"
              title={ERROR_TITLE[step]}
            />
          )}
        </Card.Content>
      </Card>
    );
  }

  const { capability, last_scan: lastScan, room_index: roomIndex } = status;
  const candidates = (lastScan?.results ?? []).flatMap((result) => result.candidates);

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Card.Title>Is tarama</Card.Title>
          <StatusPill
            label={capability.ready ? "Modul ve yazma kapisi hazir" : "Modul veya yazma kapisi hazir degil"}
            tone={capability.ready ? "ok" : "pending"}
          />
        </div>
        <Card.Description>
          Sectiginiz acik odalar bir kez okunur ve okunanlardan aday is
          cikarilir. Hicbir sey gonderilmez, hicbir sey onaylanmaz ve hicbir
          oda siz secmeden taranmaz.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        {error !== null && (
          <ErrorRegion
            error={error}
            onRetry={step === "read" ? () => void load() : undefined}
            retryPending={busy === "read"}
            section="Is Tara"
            title={ERROR_TITLE[step]}
          />
        )}

        {/* --- what a deterministic derivation cannot do ----------------- */}
        <section aria-label="Cikarim sinirlari" className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-foreground">Bu taramanin siniri</h3>
          <Alert status="warning">
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>Anlamsal cikarim yoktur</Alert.Title>
              {/* The backend's sentence, verbatim, on every read - not only
                  beside a result (ADR-0007 2). */}
              <Alert.Description>
                <span data-testid="workscan-honesty">{status.honesty}</span>
              </Alert.Description>
            </Alert.Content>
          </Alert>
          <p className="text-xs text-muted" data-testid="workscan-polling">
            {status.polling_statement}
          </p>
          <p className="font-mono text-xs text-muted">
            {`Hicbir istekte gonderilmeyen parametreler: ${status.never_sent_params.join(", ")}`}
          </p>
          <p className="text-xs text-muted">{capability.detail}</p>
        </section>

        <Separator />

        {/* --- the scope, chosen by the user ---------------------------- */}
        <section aria-label="Oda secimi" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">Oda secimi</h3>
            <Button isDisabled={busy !== null} onPress={() => void readRooms()} variant="secondary">
              {busy === "rooms" ? "Oda listesi okunuyor..." : "Oda listesini oku"}
            </Button>
          </div>
          <p className="text-xs text-muted">
            Oda listesi yalnizca siz istediginizde okunur ve kendiliginden
            yenilenmez. Taramanin kapsami bu listeden sectiginiz odalardir;
            butun oda evreni taranmaz.
          </p>

          {roomIndex === null ? (
            <p className="text-sm text-muted">
              Oda listesi bu oturumda henuz okunmadi. Secim yapabilmek icin
              once listeyi okuyun.
            </p>
          ) : (
            <RoomChooser
              busy={busy !== null}
              chosen={chosen}
              index={roomIndex}
              onToggle={toggleRoom}
            />
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button isDisabled={busy !== null || chosen.length === 0} onPress={() => void scan()}>
              {busy === "scan" ? "Taraniyor..." : "Secili odalari tara"}
            </Button>
            <span className="text-xs text-muted">
              {chosen.length === 0
                ? "Once en az bir oda secin."
                : `Taranacak: ${chosen.join(", ")}`}
            </span>
          </div>
        </section>

        <Separator />

        {/* --- what the scan read -------------------------------------- */}
        <section aria-label="Tarama sonucu" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Tarama sonucu</h3>
          {lastScan === null ? (
            <p className="text-sm text-muted">
              Bu oturumda henuz tarama yapilmadi. Bu, taranacak is olmadigi
              anlamina gelmez.
            </p>
          ) : (
            <ScanReport scan={lastScan} />
          )}
        </section>

        <Separator />

        {/* --- candidates ---------------------------------------------- */}
        <section aria-label="Adaylar" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Adaylar</h3>
          {candidates.length === 0 ? (
            <p className="text-sm text-muted">
              Gosterilecek aday yok. Bos bir aday listesi, okunan odalarda is
              olmadigini kanitlamaz: yukaridaki okunan satir sayilarina ve
              okunamayan odalara bakin.
            </p>
          ) : (
            <>
              <ul className="flex flex-col gap-3">
                {candidates.map((candidate) => (
                  <CandidateCard
                    candidate={candidate}
                    disabled={busy !== null}
                    groupName={`${ids}-candidate`}
                    key={candidate.id}
                    onChoose={setCandidateId}
                    selected={candidateId === candidate.id}
                  />
                ))}
              </ul>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  isDisabled={busy !== null || candidateId === ""}
                  onPress={() => void suggest()}
                >
                  {busy === "suggest" ? "Aciliyor..." : "Secili adayi yerel gorev olarak ac"}
                </Button>
                <span className="text-xs text-muted">
                  Bu islem yalnizca bu bilgisayarda bir kayit acar. Hicbir
                  mesaj gonderilmez ve gorev onaylanmaz.
                </span>
              </div>
            </>
          )}

          {suggestion !== null && (
            <Alert data-testid="workscan-suggestion" status="default">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title>Aday yerel gorev olarak acildi</Alert.Title>
                <Alert.Description>
                  <span className="flex flex-col gap-1">
                    <span>{suggestion.detail}</span>
                    <span className="font-mono text-xs">
                      {`Gorev: ${suggestion.task_id.slice(0, 12)} · durum: ${suggestion.state} · modul: ${
                        suggestion.module_id
                      } · kaynak: ${suggestion.source_id}`}
                    </span>
                    <span>
                      Bu gorev onaylanmadi. Onaya gecirmek gorev yuzeyinde ayri
                      bir islemdir ve kullanicinin kendi eylemidir.
                    </span>
                  </span>
                </Alert.Description>
              </Alert.Content>
            </Alert>
          )}
        </section>

        <Separator />

        {/* --- external service records -------------------------------- */}
        <section aria-label="Dis servis kayitlari" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Dis servis kayitlari</h3>
          <p className="text-xs text-muted">
            Asagidaki kayitlar birer inceleme notudur, bir entegrasyon degil.
            Station bu servislerin hicbirine istek gondermez ve hicbirinin
            verisini bir aday uretiminde kullanmaz.
          </p>
          {status.adapters.map((adapter) => (
            <AdapterRecord adapter={adapter} key={adapter.id} />
          ))}
        </section>
      </Card.Content>
    </Card>
  );
}
