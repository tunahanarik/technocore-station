import { Alert, Button, Card, Checkbox, Input, Label, Separator, TextField } from "@heroui/react";
import { useCallback, useEffect, useState } from "react";

import {
  type ApiError,
  deleteActivity,
  fetchActivity,
  toApiError,
} from "../../api/client";
import type {
  ActivityActionName,
  ActivityActorName,
  ActivityDeleteResponse,
  ActivityEventStatus,
  ActivityListResponse,
  ActivityOutcomeName,
} from "../../api/types";
import { ErrorRegion } from "../ErrorRegion";
import { StatusPill } from "../StatusPill";

/**
 * "Aktivite": the Activity Desk - what the runner actually did, in order.
 *
 * The rules this surface keeps, and why each one is here:
 *
 * 1. **Fourteen kinds of moment, not one.** "Planned", "a tool was called",
 *    "an artifact was produced", "a check was recorded" and "waiting for
 *    approval" get five different labels, because a timeline that collapses
 *    them into a single badge can no longer answer "was anything actually
 *    checked?" (ADR-0008 6). `approval_awaited` carries the outcome
 *    `pending`, which is not `ok`.
 * 2. **No invented progress.** There is no progress bar, no percentage, no
 *    spinner and no animation anywhere on this surface. Progress is whatever
 *    the backend recorded, and nothing here interpolates between two events.
 * 3. **No reasoning and no provider payload.** Not "sanitised first" - the
 *    table these rows come from has no column for such a thing, and the model
 *    lane that would produce one is closed (ADR-0008 2, 6).
 * 4. **Two layers, never mixed.** Activity rows are not links in the audit
 *    chain, which is why the timeline may have a retention policy while the
 *    chain keeps not having one. Rows the chain refers to are marked, are
 *    never pruned and refuse deletion; the deletion itself is written to the
 *    chain as an event.
 * 5. **Remote and generated text is data.** A detail sentence is rendered as
 *    inert preformatted text, never markup and never a link (SI-54).
 * 6. **Nothing polls.** No timer, no auto-refresh, no long poll. One read on
 *    mount - which contacts nobody - and every later read inside a click
 *    (SI-272).
 */

/** Which action a failure came from; only the plain read repeats safely. */
type Step = "read" | "delete";

type Busy = Step | null;

const ERROR_TITLE: Record<Step, string> = {
  read: "Aktivite akisi okunamadi",
  delete: "Kayitlar silinemedi",
};

/**
 * The fourteen actions, each with its own sentence.
 *
 * Deliberately not grouped: "planned" and "called a tool" are the two the
 * product would most like to blur together, and they are exactly the two a
 * reader needs apart.
 */
const ACTION_LABEL: Record<ActivityActionName, string> = {
  run_planned: "Planlandi",
  run_started: "Calisma baslatildi",
  tool_called: "Arac cagrisi yapildi",
  artifact_produced: "Cikti olusturuldu",
  check_recorded: "Denetim kaydedildi",
  approval_awaited: "Onay bekleniyor",
  run_stopped: "Durduruldu",
  run_resumed: "Surduruldu",
  run_finished: "Calisma bitti",
  run_failed: "Calisma basarisiz oldu",
  permission_denied: "Izin reddedildi",
  budget_exhausted: "Tavana ulasildi",
  execution_unavailable: "Yurutme kullanilamiyor",
  activity_deleted: "Aktivite kaydi silindi",
};

/** There is no `model` actor, because there is no model lane. */
const ACTOR_LABEL: Record<ActivityActorName, string> = {
  user: "Kullanici",
  station_runner: "Station kosucusu",
};

const OUTCOME_LABEL: Record<ActivityOutcomeName, string> = {
  ok: "tamam",
  refused: "reddedildi",
  failed: "basarisiz",
  pending: "bekliyor",
};

const OUTCOME_TONE: Record<ActivityOutcomeName, "ok" | "problem" | "pending"> = {
  ok: "ok",
  refused: "problem",
  failed: "problem",
  pending: "pending",
};

/** Stated on every read, not only when something looks wrong. */
const NO_PROGRESS_STATEMENT =
  "Bu ekranda ilerleme cubugu, yuzde ve doner animasyon yoktur. Gorunen her satir backend'in kaydettigi bir olaydir; iki olay arasinda bir ilerleme uydurulmaz ve bir isin ne kadar kaldigi tahmin edilmez.";

const NO_MODEL_STATEMENT =
  "Modelin muhakemesi, istem metni ve ham saglayici yaniti burada gosterilmez. Bu bir temizleme degildir: bu satirlarin geldigi tabloda boyle bir sutun yoktur ve uretecek bir model yolu da yoktur.";

/** UTC first, then the reader's own clock. Both, because they differ. */
function formatUtc(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString();
}

function formatLocal(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

function shortId(value: string): string {
  return value === "" ? "(yok)" : value.slice(0, 12);
}

/** One timeline row. Everything it carries, and nothing it does not. */
function EventRow({ event }: { readonly event: ActivityEventStatus }) {
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-border p-2">
      <div className="flex flex-wrap items-center gap-2">
        {/* The action badge. One per action kind, never a shared "step" pill. */}
        <span data-testid={`activity-action-${event.action}`}>
          <StatusPill label={ACTION_LABEL[event.action]} tone="inactive" />
        </span>
        <StatusPill label={OUTCOME_LABEL[event.outcome]} tone={OUTCOME_TONE[event.outcome]} />
        {event.chain_referenced && (
          <StatusPill label="Zincir bu satira atifta bulunuyor" tone="pending" />
        )}
      </div>

      <p className="font-mono text-xs text-muted">
        {`${formatUtc(event.recorded_at)} (UTC) · yerel: ${formatLocal(event.recorded_at)}`}
      </p>
      <p className="font-mono text-xs text-muted">
        {`calisma ${shortId(event.run_id)} · gorev ${shortId(event.task_id)} · aktor ${
          ACTOR_LABEL[event.actor]
        } · sure ${String(event.duration_ms)} ms`}
      </p>
      <p className="font-mono text-xs text-muted">
        {`cikti ozeti: ${shortId(event.artifact_sha256)} · denetim ozeti: ${shortId(
          event.check_sha256,
        )}`}
      </p>

      {/* Generated text, rendered as data: preformatted, unlinked, inert. */}
      <pre className="whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-2 font-mono text-xs text-foreground">
        {event.detail}
      </pre>
    </li>
  );
}

export function ActivityPanel() {
  const [feed, setFeed] = useState<ActivityListResponse | null>(null);
  const [report, setReport] = useState<ActivityDeleteResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<Step>("read");

  // The applied filter, and the field the user is typing into. Two values,
  // because a listing must say which scope it is showing rather than which
  // scope somebody is halfway through typing. Plain React state (SI-24).
  const [runFilter, setRunFilter] = useState("");
  const [applied, setApplied] = useState("");
  const [deleteApproved, setDeleteApproved] = useState(false);

  /**
   * The one read that runs without a click.
   *
   * Safe because it contacts nobody: it reads a local, append-only table. It
   * is not scheduled, not repeated and not retried on its own.
   */
  const load = useCallback(async (runId: string): Promise<void> => {
    setLoading(true);
    setBusy("read");
    try {
      setFeed(await fetchActivity(runId));
      setApplied(runId);
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
    void load("");
  }, [load]);

  async function apply(runId: string): Promise<void> {
    if (busy !== null) return;
    setRunFilter(runId);
    setReport(null);
    await load(runId);
  }

  async function removeRows(): Promise<void> {
    if (busy !== null || !deleteApproved) return;
    setBusy("delete");
    setError(null);
    try {
      const next = await deleteActivity(applied);
      setReport(next);
      setDeleteApproved(false);
      setFeed(await fetchActivity(applied));
    } catch (caught) {
      setError(toApiError(caught));
      setStep("delete");
    } finally {
      setBusy(null);
    }
  }

  if (feed === null) {
    return (
      <Card>
        <Card.Header>
          <Card.Title>Aktivite</Card.Title>
        </Card.Header>
        <Card.Content className="flex flex-col gap-3">
          {error === null ? (
            <p className="text-sm text-muted">Aktivite akisi okunuyor...</p>
          ) : (
            <ErrorRegion
              error={error}
              onRetry={() => void load(applied)}
              retryPending={loading}
              section="Aktivite / Akis"
              title={ERROR_TITLE[step]}
            />
          )}
        </Card.Content>
      </Card>
    );
  }

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Card.Title>Aktivite</Card.Title>
          <StatusPill
            label={`Kayitli olay: ${String(feed.event_count)}`}
            tone="inactive"
          />
        </div>
        <Card.Description>
          Agent calisma ortaminin adim adim kaydi, en yenisi ustte. Her satir
          gerceklesmis bir olaydir; hicbir satir bir tahmin veya bir ilerleme
          gostergesi degildir.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        {error !== null && (
          <ErrorRegion
            error={error}
            onRetry={step === "read" ? () => void load(applied) : undefined}
            retryPending={busy === "read"}
            section="Aktivite"
            title={ERROR_TITLE[step]}
          />
        )}

        {/* --- what this timeline does not do --------------------------- */}
        <section aria-label="Akisin siniri" className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-foreground">Bu akisin siniri</h3>
          <p className="text-xs text-muted" data-testid="activity-no-progress">
            {NO_PROGRESS_STATEMENT}
          </p>
          <p className="text-xs text-muted" data-testid="activity-no-model">
            {NO_MODEL_STATEMENT}
          </p>
          <p className="text-xs text-muted" data-testid="activity-layers">
            {feed.detail}
          </p>
          <p className="font-mono text-xs text-muted" data-testid="activity-retention">
            {`Saklama siniri: en yeni ${String(
              feed.retained_events,
            )} satir · toplam olay ${String(feed.event_count)} · zincirin atifta bulundugu satir ${String(
              feed.chain_referenced_count,
            )}`}
          </p>
        </section>

        <Separator />

        {/* --- scope ---------------------------------------------------- */}
        <section aria-label="Akis kapsami" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Kapsam</h3>
          <p className="text-xs text-muted">
            Akis kendiliginden yenilenmez: yeni satirlari gormek icin
            asagidaki islemlerden birini siz baslatirsiniz.
          </p>

          <TextField className="w-full" onChange={setRunFilter} value={runFilter}>
            <Label>Calisma kimligi (bos birakilirsa butun kayitlar)</Label>
            <Input autoComplete="off" variant="secondary" />
          </TextField>

          <div className="flex flex-wrap items-center gap-2">
            <Button isDisabled={busy !== null} onPress={() => void apply(runFilter)}>
              {busy === "read" ? "Okunuyor..." : "Akisi oku"}
            </Button>
            <Button
              isDisabled={busy !== null || applied === ""}
              onPress={() => void apply("")}
              variant="secondary"
            >
              Filtreyi kaldir
            </Button>
            <span className="font-mono text-xs text-muted" data-testid="activity-scope">
              {applied === ""
                ? "Gosterilen kapsam: butun calismalar"
                : `Gosterilen kapsam: calisma ${applied}`}
            </span>
          </div>
        </section>

        <Separator />

        {/* --- deletion is itself an event ------------------------------ */}
        <section aria-label="Kayit silme" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">Kayit silme</h3>
          <p className="text-xs text-muted" data-testid="activity-delete-rule">
            Zincirin atifta bulundugu satirlar silinemez ve budanmaz; silme
            istegi onlari korur. Silme isleminin kendisi audit zincirine bir
            olay olarak yazilir, yani kayit sessizce kaybolmaz.
          </p>
          <Checkbox
            isDisabled={busy !== null}
            isSelected={deleteApproved}
            onChange={() => setDeleteApproved((current) => !current)}
          >
            <Checkbox.Content>
              <Checkbox.Control>
                <Checkbox.Indicator />
              </Checkbox.Control>
              Gosterilen kapsamdaki isaretsiz satirlarin silinmesini
              onayliyorum.
            </Checkbox.Content>
          </Checkbox>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              isDisabled={busy !== null || !deleteApproved}
              onPress={() => void removeRows()}
              variant="secondary"
            >
              {busy === "delete" ? "Siliniyor..." : "Kapsamdaki kayitlari sil"}
            </Button>
          </div>

          {report !== null && (
            <Alert data-testid="activity-delete-report" status="default">
              <Alert.Indicator />
              <Alert.Content>
                <Alert.Title>Silme islemi kaydedildi</Alert.Title>
                <Alert.Description>
                  <span className="flex flex-col gap-1">
                    {/* Two counts, never one total: "twelve removed" and
                        "three kept because the chain refers to them" answer
                        different questions. */}
                    <span className="font-mono text-xs">
                      {`Silinen satir: ${String(report.deleted)}`}
                    </span>
                    <span className="font-mono text-xs">
                      {`Zincir atifta bulundugu icin korunan satir: ${String(
                        report.kept_because_chain_referenced,
                      )}`}
                    </span>
                    <span>
                      {report.recorded_in_audit_chain
                        ? "Bu silme audit zincirine bir olay olarak yazildi."
                        : "Bu silme audit zincirine yazilmadi."}
                    </span>
                    <span>{report.detail}</span>
                  </span>
                </Alert.Description>
              </Alert.Content>
            </Alert>
          )}
        </section>

        <Separator />

        {/* --- the timeline --------------------------------------------- */}
        <section aria-label="Olay akisi" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">
            {`Olaylar (${String(feed.events.length)})`}
          </h3>
          {feed.events.length === 0 ? (
            <p className="text-sm text-muted">
              Bu kapsamda olay yok. Bos bir akis, bir sey yapilmadigini
              kanitlamaz: yalnizca bu kapsamda kayitli satir olmadigini
              gosterir.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {feed.events.map((event) => (
                <EventRow event={event} key={event.id} />
              ))}
            </ul>
          )}
        </section>
      </Card.Content>
    </Card>
  );
}
