import { Alert, Button, Card, Checkbox, Input, Label, Separator, TextArea, TextField } from "@heroui/react";
import { useCallback, useEffect, useId, useState } from "react";

import {
  type ApiError,
  fetchAgentSurface,
  fetchTaskRuns,
  fetchTasks,
  planTaskRun,
  resumeTaskRun,
  startTaskRun,
  stopTaskRun,
  toApiError,
  transitionTask,
} from "../../api/client";
import type {
  AgentRunPhaseName,
  AgentRunStatus,
  AgentStepPhaseName,
  AgentSurfaceResponse,
  AgentTaskRunsResponse,
  AgentToolScopeName,
  AgentToolStatus,
  TaskCheckState,
  TaskEvidenceFieldName,
  TaskListResponse,
  TaskStateName,
  TaskStatusResponse,
  TaskUserTransitionName,
} from "../../api/types";
import { ErrorRegion } from "../ErrorRegion";
import { StatusPill } from "../StatusPill";

/**
 * "Gorevler": the task surface and the agent's deterministic tool runner.
 *
 * This is the package's honesty surface, and every rule below exists because
 * the comfortable version of this screen would be a lie.
 *
 * 1. **`execution_unavailable` is shown with its reason, not inferred from a
 *    missing button.** The backend reports arbitrary code and shell execution
 *    as closed *and says why*, including the measured isolation inventory -
 *    Docker present, and `relied_upon: false` beside it. A sandbox that
 *    exists on the developer's machine is not a guarantee the product can
 *    offer, and both halves of that sentence are on screen (ADR-0008 1).
 * 2. **Code that was never run is not tested code.** `test_result_state` is
 *    `not_implemented` as a *type*, so a run that produced files still leaves
 *    the task short of `ready_to_publish`. The surface says so in words and
 *    renders no publish-ready badge (SI-222).
 * 3. **The model lane is closed.** There is no model call in production, so
 *    "model output is never executed directly" is not a promise here - there
 *    is no model output. The timeline has no `model` actor to write one with
 *    (ADR-0008 2).
 * 4. **A budget is only ever three units.** Tool calls, wall-clock seconds
 *    and a concurrency of one. Tokens and currency are *refused* units and
 *    the backend publishes them as such, so the absence is a claim on screen
 *    rather than something a reader has to notice. The ceiling is a
 *    compile-time constant and the agent has no tool that could raise it
 *    (ADR-0008 4).
 * 5. **The four fields never become one boolean.** Task outcome, test result,
 *    user acceptance and public sharing are four questions with four answers,
 *    rendered apart (ADR-0004 4).
 * 6. **Approval belongs to a plan, not to a session.** The four approvals are
 *    keyed to the run id, and a different plan is a *different run*: a
 *    re-plan is unapproved by construction rather than by a reset somebody
 *    has to remember. Small, safe file operations inside an approved plan do
 *    not ask again; a change of scope or risk is a new plan and asks again.
 * 7. **Nothing here polls.** No `setInterval`, no `setTimeout`, no auto
 *    refresh and no background task. Two reads happen on mount and contact
 *    nobody; every other request is inside a click (SI-272). A restart
 *    resumes nothing: interrupted runs are listed and continuing is a
 *    person's act (SI-224).
 */

/** Which action a failure came from; only the plain read repeats safely. */
type Step =
  | "read"
  | "task"
  | "transition"
  | "plan"
  | "start"
  | "stop"
  | "resume";

type Busy = Step | null;

const ERROR_TITLE: Record<Step, string> = {
  read: "Gorev yuzeyi okunamadi",
  task: "Gorev ayrintisi okunamadi",
  transition: "Durum degistirilemedi",
  plan: "Plan kaydedilemedi",
  start: "Calisma baslatilamadi",
  stop: "Durdurma istegi islenemedi",
  resume: "Calisma surdurulemedi",
};

/** The nine states, in the user's language. */
const STATE_LABEL: Record<TaskStateName, string> = {
  suggested: "Onerildi",
  awaiting_approval: "Onay bekliyor",
  running: "Calisiyor",
  paused: "Duraklatildi",
  blocked: "Engellendi",
  failed: "Basarisiz",
  review_needed: "Inceleme gerekiyor",
  ready_to_publish: "Yayima hazir",
  published: "Yayimlandi",
};

/** The four fields. Four labels, because they are four questions. */
const FIELD_LABEL: Record<TaskEvidenceFieldName, string> = {
  task_outcome: "Gorev basarisi",
  test_result: "Test sonucu",
  user_acceptance: "Kullanici kabulu",
  public_share: "Public paylasim",
};

/**
 * The three check states.
 *
 * "uygulanmadi" rather than a blank: an unbuilt requirement is never counted
 * as passed, and a product gap is never shown as a user error.
 */
const CHECK_LABEL: Record<TaskCheckState, string> = {
  passed: "dogrulandi",
  blocked: "engelli",
  not_implemented: "uygulanmadi",
};

const CHECK_TONE: Record<TaskCheckState, "ok" | "problem" | "inactive"> = {
  passed: "ok",
  blocked: "problem",
  not_implemented: "inactive",
};

/** The four permission scopes. None of them leaves this machine. */
const SCOPE_LABEL: Record<AgentToolScopeName, string> = {
  read_approved_input: "onaylanmis girdiyi okur",
  write_workspace: "yalnizca bu gorevin calisma alanina yazar",
  deterministic_check: "uretilen dosya uzerinde deterministik denetim yapar",
  read_run_state: "calismanin kendi kaydini okur",
};

/**
 * The eight run phases, with the four endings kept apart.
 *
 * "Your budget ran out", "your input was refused", "you stopped it" and "the
 * file you promised is not there" are four different findings, and a user who
 * cannot tell them apart cannot act on any of them.
 */
const RUN_PHASE_LABEL: Record<AgentRunPhaseName, string> = {
  planned: "Plan kaydedildi, calistirilmadi",
  running: "Calisiyor",
  paused: "Kullanici durdurdu",
  completed: "Bitti: her adim yapildi, soz verilen her cikti var",
  cancelled: "Iptal edildi",
  tool_error: "Bir arac reddetti veya basarisiz oldu",
  budget_exhausted: "Tavana ulasildi",
  artifact_missing: "Soz verilen cikti uretilmedi",
};

const RUN_PHASE_TONE: Record<AgentRunPhaseName, "ok" | "pending" | "inactive" | "problem"> = {
  planned: "inactive",
  running: "pending",
  paused: "pending",
  completed: "ok",
  cancelled: "inactive",
  tool_error: "problem",
  budget_exhausted: "problem",
  artifact_missing: "problem",
};

/** What became of one planned step. Never "kod calistirildi": none was. */
const STEP_PHASE_LABEL: Record<AgentStepPhaseName, string> = {
  planned: "planlandi",
  ran: "arac cagrisi yapildi",
  refused: "reddedildi",
  failed: "basarisiz oldu",
  skipped: "atlandi",
};

/** The five transitions a person may ask for. */
const TRANSITIONS: readonly { readonly target: TaskUserTransitionName; readonly label: string }[] = [
  { target: "awaiting_approval", label: "Onaya al" },
  { target: "review_needed", label: "Incelemeye al" },
  { target: "blocked", label: "Engellendi olarak isaretle" },
  { target: "failed", label: "Basarisiz olarak isaretle" },
  { target: "published", label: "Yayimlandi olarak isaretle" },
];

/** The four approvals one plan needs before it may be carried out. */
type ApprovalKey = "plan" | "data" | "workspace" | "budget";

const APPROVALS: readonly { readonly key: ApprovalKey; readonly label: string }[] = [
  {
    key: "plan",
    label:
      "Plani okudum: adimlar, soz verilen ciktilar ve basari olcutu benim onayimdir.",
  },
  {
    key: "data",
    label:
      "Veri paylasimini onayliyorum: bu calisma yalnizca onaylanmis girdiyi okur ve hicbir sey disariya gonderilmez.",
  },
  {
    key: "workspace",
    label:
      "Calisma alanini onayliyorum: dosyalar yalnizca bu gorevin calisma alaninda olusur.",
  },
  {
    key: "budget",
    label:
      "Butceyi onayliyorum: arac cagrisi sayisi, sure ve eszamanlilik (=1) tavani asilirsa calisma durur.",
  },
];

const APPROVAL_KEYS: readonly ApprovalKey[] = APPROVALS.map((entry) => entry.key);

type ApprovalState = Readonly<Record<ApprovalKey, boolean>>;

const NO_APPROVALS: ApprovalState = {
  plan: false,
  data: false,
  workspace: false,
  budget: false,
};

/**
 * The model lane, in this surface's own words.
 *
 * The backend's `honesty` sentence already says a run makes no model call;
 * this says the consequence out loud, because "model output is never executed
 * directly" reads like a safeguard and in this release it is a description of
 * an empty set (ADR-0008 2).
 */
const MODEL_LANE_STATEMENT =
  "Model yolu bu surumde kapalidir: tool-call tel bicimi yayimlanmadigi icin uretimde hicbir model cagrisi yapilmaz. 'Model ciktisi dogrudan yurutulmez' burada bir onlem degil, yapisal bir gercektir - bu surumde model ciktisi diye bir sey yoktur. Zaman cizelgesinde aktor yalnizca kullanici veya Station kosucusudur; 'model' diye bir aktor tanimli degildir.";

/** "Code that was never run is not tested code", as a sentence on screen. */
const UNTESTED_STATEMENT =
  "Calistirilmamis kod test edilmis sayilmaz. Bir calisma dosya uretmis olsa bile test sonucu 'uygulanmadi' kalir, bu yuzden gorev yayima hazir duruma gecemez.";

/** What the agent cannot reach. A list, because a sentence hides items. */
const CANNOT_REACH: readonly string[] = [
  "Imzalayici (signer) ve imzalama yolu",
  "Kasa (vault), kasa parolasi ve isletim sistemi koruma yuzeyi",
  "Recovery dosyasi ve seed ice aktarma yolu",
  "Saglayici (OpenCode) kimlik bilgisi",
  "Global ortam degiskenleri",
  "Kullanicinin home dizini",
  "Station'in kendi kaynak deposu",
];

/** What the agent cannot do. Development authority is not inherited. */
const CANNOT_DO: readonly string[] = [
  "git islemi, pull request acma veya merge",
  "paket kurmak (pip, npm veya baskasi)",
  "ayar, izin listesi veya yapilandirma degistirmek",
  "plugin veya eklenti yuklemek",
  "kendi arac listesine yeni bir arac eklemek",
  "kendi butce tavanini yukseltmek",
];

/** A single draft step: a registered tool id and its typed arguments. */
interface DraftStep {
  readonly toolId: string;
  readonly args: Readonly<Record<string, string>>;
}

function formatLocal(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("tr-TR");
}

function shortId(value: string): string {
  return value === "" ? "(yok)" : value.slice(0, 12);
}

/**
 * Why execution is closed, and the inventory that was measured anyway.
 *
 * The inventory is not decoration: dropping the present-but-unused facilities
 * would turn "we measured a sandbox and chose not to rely on it" into "there
 * was nothing", and only the first one is true.
 */
function ExecutionBlock({ surface }: { readonly surface: AgentSurfaceResponse }) {
  const { execution } = surface;
  return (
    <section aria-label="Yurutme durumu" className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-foreground">Yurutme durumu</h3>

      <Alert status="warning">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Keyfi kod ve kabuk yurutmesi kapali</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2">
              <span className="font-mono text-xs" data-testid="tasks-execution-reason">
                {`Neden: ${execution.reason}`}
              </span>
              <span data-testid="tasks-execution-detail">{execution.detail}</span>
            </span>
          </Alert.Description>
        </Alert.Content>
      </Alert>

      <p className="text-xs text-muted" data-testid="tasks-honesty">
        {surface.honesty}
      </p>
      <p className="text-xs text-muted" data-testid="tasks-untested">
        {UNTESTED_STATEMENT}
      </p>
      <p className="text-xs text-muted" data-testid="tasks-model-lane">
        {MODEL_LANE_STATEMENT}
      </p>

      <div className="flex flex-col gap-2" data-testid="tasks-execution-inventory">
        <p className="text-xs font-medium text-foreground">
          {`Olculen izolasyon envanteri (${String(execution.inventory.length)} madde)`}
        </p>
        <p className="text-xs text-muted">
          Olculdu, guvenilmedi: bir olcumun sonucu ile ona dayanilip
          dayanilmadigi ayri iki satirdir ve ikisi de asagida yazilidir.
        </p>
        <ul className="flex flex-col gap-1">
          {execution.inventory.map((finding) => (
            <li className="text-xs text-muted" key={finding.facility}>
              <span className="font-mono">
                {`${finding.facility} · olcum: ${finding.measured} · dayanildi mi: ${
                  finding.relied_upon ? "evet" : "hayir"
                } · olcum tarihi: ${finding.measured_at}`}
              </span>
              <br />
              {finding.detail}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/** The ceiling, its units, and the units this product refuses to use. */
function BudgetBlock({ surface }: { readonly surface: AgentSurfaceResponse }) {
  const { ceiling } = surface;
  return (
    <section aria-label="Butce ve tavan" className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-foreground">Butce ve tavan</h3>
      <p className="font-mono text-xs text-muted" data-testid="tasks-budget-units">
        {`Olculen birimler: ${ceiling.units.join(", ")} · en cok ${String(
          ceiling.max_tool_calls,
        )} arac cagrisi · en cok ${String(
          ceiling.max_wall_clock_seconds,
        )} saniye · eszamanlilik ${String(ceiling.max_concurrency)}`}
      </p>
      <p className="text-xs text-muted">{ceiling.detail}</p>
      <p className="font-mono text-xs text-muted" data-testid="tasks-budget-refused-units">
        {`Reddedilen birimler: ${ceiling.refused_units.join(", ")}`}
      </p>
      <p className="text-xs text-muted" data-testid="tasks-budget-refused-detail">
        {ceiling.refused_units_detail}
      </p>
      {/* `agent_can_raise_ceiling` is `false` as a type, so this pill has no
          branch behind it and cannot drift away from the wire value. */}
      <div>
        <StatusPill
          label={
            ceiling.agent_can_raise_ceiling
              ? "Tavan degistirilebilir"
              : "Agent kendi butcesini yukseltemez"
          }
          tone="inactive"
        />
      </div>
    </section>
  );
}

/** The registered tools, and the boundary around them. */
function TrustBoundaryBlock({ tools }: { readonly tools: readonly AgentToolStatus[] }) {
  return (
    <section aria-label="Guven siniri" className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-foreground">Guven siniri</h3>
      <p className="text-xs text-muted">
        {`Kayitli arac sayisi: ${String(
          tools.length,
        )}. Bu liste derleme zamaninda yazilir; calisma aninda ne genisler ne de daralir, ve agent'in kendisine arac ekleyecek bir araci yoktur.`}
      </p>

      <ul className="flex flex-col gap-2">
        {tools.map((tool) => (
          <li className="rounded-lg border border-border p-2" key={tool.id}>
            <p className="font-mono text-xs text-foreground">
              {`${tool.id} · ${SCOPE_LABEL[tool.scope]} · maliyet ${String(
                tool.call_cost,
              )} cagri · cikti uretir: ${tool.produces_artifact ? "evet" : "hayir"}`}
            </p>
            <p className="text-xs text-muted">{tool.purpose}</p>
            {tool.params.length > 0 && (
              <p className="font-mono text-xs text-muted">
                {`Parametreler: ${tool.params
                  .map((param) => `${param.name}:${param.type}${param.required ? "" : "?"}`)
                  .join(", ")}`}
              </p>
            )}
          </li>
        ))}
      </ul>

      <div className="flex flex-col gap-2" data-testid="tasks-trust-boundary">
        <p className="text-xs font-medium text-foreground">Agent'in erisemedikleri</p>
        <ul className="flex flex-col gap-1">
          {CANNOT_REACH.map((item) => (
            <li className="text-xs text-muted" key={item}>{`• ${item}`}</li>
          ))}
        </ul>
        <p className="text-xs font-medium text-foreground">Agent'in yapamadiklari</p>
        <ul className="flex flex-col gap-1">
          {CANNOT_DO.map((item) => (
            <li className="text-xs text-muted" key={item}>{`• ${item}`}</li>
          ))}
        </ul>
        <p className="text-xs text-muted">
          Gelistirme sirasinda bir kodlama asistanina verilmis commit, pull
          request ve merge yetkisi son urundeki agent'a miras verilmez.
          Erisebildigi tek dizin bu gorevin calisma alanidir.
        </p>
      </div>
    </section>
  );
}

/** The four fields, each on its own line. Never summed into a verdict. */
function EvidenceFields({ task }: { readonly task: TaskStatusResponse }) {
  return (
    <section aria-label="Dort alan" className="flex flex-col gap-2">
      <h4 className="text-xs font-semibold text-foreground">
        Dort ayri alan (hicbiri digerinin yerine gecmez)
      </h4>
      <ul className="flex flex-col gap-2">
        {task.evidence_fields.map((field) => (
          <li
            className="flex flex-col gap-1 rounded-lg border border-border p-2"
            data-testid={`tasks-field-${field.evidence_field}`}
            key={field.evidence_field}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-foreground">
                {FIELD_LABEL[field.evidence_field]}
              </span>
              <StatusPill label={CHECK_LABEL[field.state]} tone={CHECK_TONE[field.state]} />
            </div>
            <p className="text-xs text-muted">{field.detail}</p>
            <p className="font-mono text-xs text-muted">
              {`Alan: ${field.evidence_field} · durum: ${field.state} · kanit: ${
                field.ref_id === "" ? "(yok)" : shortId(field.ref_id)
              }`}
            </p>
          </li>
        ))}
      </ul>

      <p className="text-xs text-muted" data-testid="tasks-publish-state">
        {task.ready_to_publish
          ? "Uc alan ayri ayri dogrulandi."
          : `Yayima hazir degil. Bekleyen alanlar: ${
              task.blocking_fields.length === 0 ? "(yok)" : task.blocking_fields.join(", ")
            }.`}
      </p>
      <p className="text-xs text-muted" data-testid="tasks-public-share">
        {task.public_share_detail}
      </p>
      <p className="text-xs text-muted" data-testid="tasks-task-budget">
        {task.budget_detail}
      </p>
    </section>
  );
}

/** One run: its plan, its steps, its usage and its ending, kept apart. */
function RunCard({
  approvals,
  approvalRunId,
  busy,
  onApprove,
  onResume,
  onStart,
  onStop,
  run,
  stopStatement,
}: {
  readonly approvals: ApprovalState;
  readonly approvalRunId: string;
  readonly busy: Busy;
  readonly onApprove: (runId: string, key: ApprovalKey) => void;
  readonly onResume: (runId: string) => void;
  readonly onStart: (runId: string) => void;
  readonly onStop: (runId: string) => void;
  readonly run: AgentRunStatus;
  readonly stopStatement: string;
}) {
  const approvedHere = approvalRunId === run.id;
  const fullyApproved = approvedHere && APPROVAL_KEYS.every((key) => approvals[key]);
  const scopes = [...new Set(run.steps.map((item) => item.scope))];

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground">
          {`Calisma ${shortId(run.id)}`}
        </span>
        <StatusPill label={RUN_PHASE_LABEL[run.phase]} tone={RUN_PHASE_TONE[run.phase]} />
        {run.stop_requested && <StatusPill label="Durdurma istendi" tone="pending" />}
      </div>

      <p className="font-mono text-xs text-muted">
        {`Plan ozeti: ${shortId(run.plan_sha256)} · kaydedildi: ${formatLocal(
          run.created_at,
        )} · baslatildi: ${
          run.started_at === null ? "(baslatilmadi)" : formatLocal(run.started_at)
        } · bitti: ${run.finished_at === null ? "(bitmedi)" : formatLocal(run.finished_at)}`}
      </p>
      <p className="text-xs text-muted">{run.detail}</p>

      <div className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">Basari olcutu ve test sonucu</h4>
        {/* The recorded criterion is the user's own text: preformatted, inert
            and unlinked like every other imported string in this app. */}
        <pre className="whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-2 font-mono text-xs text-foreground">
          {run.test_condition}
        </pre>
        <p className="font-mono text-xs text-muted" data-testid="tasks-test-result-state">
          {`Test sonucu: ${run.test_result_state}`}
        </p>
        <p className="text-xs text-muted" data-testid="tasks-test-result-detail">
          {run.test_result_detail}
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">Soz verilen ciktilar</h4>
        <p className="font-mono text-xs text-muted">
          {run.expected_artifacts.length === 0
            ? "Bu plan bir cikti dosyasi soz vermedi."
            : run.expected_artifacts.join(", ")}
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">Izinler ve riskler</h4>
        <p className="text-xs text-muted">
          {`Bu planin istedigi izin kapsamlari: ${
            scopes.length === 0
              ? "(adim yok)"
              : scopes.map((scope) => SCOPE_LABEL[scope]).join("; ")
          }.`}
        </p>
        <p className="text-xs text-muted">
          Risk: uretilen dosyalar denetlenmemis metindir; deterministik
          dogrulayicilar disinda hicbir sey onlari calistirmaz ve bir sonucu
          test edilmis saymaz.
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <h4 className="text-xs font-semibold text-foreground">Adimlar</h4>
        <ul className="flex flex-col gap-1">
          {run.steps.map((item) => (
            <li className="text-xs text-muted" key={`${run.id}-${String(item.ordinal)}`}>
              <span className="font-mono">
                {`${String(item.ordinal)}. ${item.tool_id} · ${SCOPE_LABEL[item.scope]} · ${
                  STEP_PHASE_LABEL[item.phase]
                } · arguman ozeti ${shortId(item.arguments_sha256)}${
                  item.artifact_name === ""
                    ? ""
                    : ` · cikti ${item.artifact_name} (${shortId(item.artifact_sha256)})`
                }`}
              </span>
              {item.detail !== "" && <span>{` — ${item.detail}`}</span>}
            </li>
          ))}
        </ul>
      </div>

      <p className="font-mono text-xs text-muted" data-testid={`tasks-usage-${run.id}`}>
        {`Harcanan: ${String(run.tool_calls_used)} / ${String(
          run.max_tool_calls,
        )} arac cagrisi · gecen sure ${String(run.elapsed_ms)} ms / ${String(
          run.max_wall_clock_seconds,
        )} saniye tavan · eszamanlilik ${String(run.concurrency)}`}
      </p>

      {/* --- the four approvals, keyed to this run --------------------- */}
      <fieldset className="flex flex-col gap-2 rounded-lg border border-border p-2">
        <legend className="text-xs font-semibold text-foreground">
          Bu plan icin dort onay
        </legend>
        {APPROVALS.map((approval) => (
          <Checkbox
            isDisabled={busy !== null}
            isSelected={approvedHere && approvals[approval.key]}
            key={approval.key}
            onChange={() => onApprove(run.id, approval.key)}
          >
            <Checkbox.Content>
              <Checkbox.Control>
                <Checkbox.Indicator />
              </Checkbox.Control>
              {approval.label}
            </Checkbox.Content>
          </Checkbox>
        ))}
        <p className="text-xs text-muted" data-testid={`tasks-scope-change-${run.id}`}>
          Onaylar bu plana aittir. Plan icindeki kucuk ve guvenli dosya
          islemleri icin her adimda yeniden onay istenmez; kapsam veya risk
          degisirse yeni bir plan kaydedilir ve yeni plan yeniden onay ister.
        </p>
      </fieldset>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          isDisabled={busy !== null || run.phase !== "planned" || !fullyApproved}
          onPress={() => onStart(run.id)}
        >
          {busy === "start" ? "Calistiriliyor..." : "Onayli plani calistir"}
        </Button>
        <Button
          isDisabled={busy !== null || run.phase !== "running"}
          onPress={() => onStop(run.id)}
          variant="secondary"
        >
          {busy === "stop" ? "Durduruluyor..." : "Durdur"}
        </Button>
        <Button
          isDisabled={busy !== null || run.phase !== "paused" || !fullyApproved}
          onPress={() => onResume(run.id)}
          variant="secondary"
        >
          {busy === "resume" ? "Surduruluyor..." : "Devam et"}
        </Button>
      </div>

      <p className="text-xs text-muted" data-testid={`tasks-stop-statement-${run.id}`}>
        {stopStatement}
      </p>
      <p className="text-xs text-muted" data-testid={`tasks-resume-statement-${run.id}`}>
        Devam yalnizca zaten onaylanmis kapsamda ilerler ve yeni bir adim
        eklemez. Cokme veya yeniden baslatma sonrasi otomatik devam yoktur:
        kesilen bir calisma listelenir, siz istemeden surdurulmez.
      </p>
    </li>
  );
}

export function TasksPanel() {
  const ids = useId();
  const [surface, setSurface] = useState<AgentSurfaceResponse | null>(null);
  const [list, setList] = useState<TaskListResponse | null>(null);
  const [detail, setDetail] = useState<AgentTaskRunsResponse | null>(null);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<Step>("read");

  // The plan being composed. Plain React state: never a browser store, and
  // never seeded from one (SI-24).
  const [toolId, setToolId] = useState("");
  const [args, setArgs] = useState<Readonly<Record<string, string>>>({});
  const [draft, setDraft] = useState<readonly DraftStep[]>([]);
  const [artifacts, setArtifacts] = useState("");
  const [condition, setCondition] = useState("");

  // Approvals are keyed to a run id. A re-plan produces a *different* run, so
  // it starts unapproved by construction rather than by a reset somebody has
  // to remember to write.
  const [approvalRunId, setApprovalRunId] = useState("");
  const [approvals, setApprovals] = useState<ApprovalState>(NO_APPROVALS);

  /**
   * The two reads that run without a click.
   *
   * Safe precisely because they contact nobody: one reads a local table and
   * the other reports what this build can and cannot do. Neither is
   * scheduled, repeated or retried on its own.
   */
  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setBusy("read");
    try {
      const [nextSurface, nextList] = await Promise.all([fetchAgentSurface(), fetchTasks()]);
      setSurface(nextSurface);
      setList(nextList);
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

  async function openTask(taskId: string): Promise<void> {
    if (busy !== null) return;
    setSelected(taskId);
    setBusy("task");
    setError(null);
    // A different task is a different workspace and a different plan; the
    // half-composed draft would otherwise be recorded against the new one.
    setDraft([]);
    setArgs({});
    setToolId("");
    setArtifacts("");
    setCondition("");
    setApprovalRunId("");
    setApprovals(NO_APPROVALS);
    try {
      setDetail(await fetchTaskRuns(taskId));
    } catch (caught) {
      setError(toApiError(caught));
      setStep("task");
    } finally {
      setBusy(null);
    }
  }

  async function move(target: TaskUserTransitionName): Promise<void> {
    if (busy !== null || selected === "") return;
    setBusy("transition");
    setError(null);
    try {
      await transitionTask({ taskId: selected, target });
      setDetail(await fetchTaskRuns(selected));
      setList(await fetchTasks());
    } catch (caught) {
      setError(toApiError(caught));
      setStep("transition");
    } finally {
      setBusy(null);
    }
  }

  async function recordPlan(): Promise<void> {
    if (busy !== null || selected === "" || draft.length === 0 || condition.trim() === "") return;
    setBusy("plan");
    setError(null);
    try {
      const next = await planTaskRun({
        taskId: selected,
        steps: draft.map((item) => ({ tool_id: item.toolId, arguments: item.args })),
        expectedArtifacts: artifacts
          .split(",")
          .map((name) => name.trim())
          .filter((name) => name !== ""),
        testCondition: condition,
      });
      setDetail(next);
      setDraft([]);
      setArgs({});
      setToolId("");
      setList(await fetchTasks());
    } catch (caught) {
      setError(toApiError(caught));
      setStep("plan");
    } finally {
      setBusy(null);
    }
  }

  async function act(
    runId: string,
    action: "start" | "stop" | "resume",
  ): Promise<void> {
    if (busy !== null || selected === "") return;
    setBusy(action);
    setError(null);
    try {
      const call =
        action === "start" ? startTaskRun : action === "stop" ? stopTaskRun : resumeTaskRun;
      setDetail(await call(selected, runId));
      setList(await fetchTasks());
      // The interrupted-run list is part of the surface, and a run that just
      // finished is no longer one; re-reading keeps the two consistent.
      setSurface(await fetchAgentSurface());
    } catch (caught) {
      setError(toApiError(caught));
      setStep(action);
    } finally {
      setBusy(null);
    }
  }

  function approve(runId: string, key: ApprovalKey): void {
    if (runId !== approvalRunId) {
      setApprovalRunId(runId);
      setApprovals({ ...NO_APPROVALS, [key]: true });
      return;
    }
    setApprovals((current) => ({ ...current, [key]: !current[key] }));
  }

  function addStep(): void {
    if (toolId === "") return;
    setDraft((current) => [...current, { toolId, args }]);
    setArgs({});
  }

  if (surface === null || list === null) {
    return (
      <Card>
        <Card.Header>
          <Card.Title>Gorevler</Card.Title>
        </Card.Header>
        <Card.Content className="flex flex-col gap-3">
          {error === null ? (
            <p className="text-sm text-muted">Gorev yuzeyi okunuyor...</p>
          ) : (
            <ErrorRegion
              error={error}
              onRetry={() => void load()}
              retryPending={loading}
              section="Gorevler / Gorev yuzeyi"
              title={ERROR_TITLE[step]}
            />
          )}
        </Card.Content>
      </Card>
    );
  }

  const chosenTool = surface.tools.find((tool) => tool.id === toolId) ?? null;
  const task = detail?.task ?? null;

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Card.Title>Gorevler</Card.Title>
          <StatusPill label="Yurutme kapali (execution_unavailable)" tone="inactive" />
        </div>
        <Card.Description>
          Plan once yazilir, sonra ayri bir istekle calistirilir. Araclar
          deterministiktir; hicbir kabuk komutu ve hicbir model cagrisi yoktur.
        </Card.Description>
      </Card.Header>

      <Card.Content className="flex flex-col gap-4">
        {error !== null && (
          <ErrorRegion
            error={error}
            onRetry={step === "read" ? () => void load() : undefined}
            retryPending={busy === "read"}
            section="Gorevler"
            title={ERROR_TITLE[step]}
          />
        )}

        <ExecutionBlock surface={surface} />

        <Separator />

        <BudgetBlock surface={surface} />

        <Separator />

        <TrustBoundaryBlock tools={surface.tools} />

        <Separator />

        {/* --- runs a restart left behind ------------------------------- */}
        <section aria-label="Kesilen calismalar" className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-foreground">Kesilen calismalar</h3>
          <p className="text-xs text-muted" data-testid="tasks-interrupted">
            {surface.interrupted_runs.length === 0
              ? "Yeniden baslatmanin geride biraktigi bir calisma yok. Boyle bir calisma olsaydi burada yalnizca listelenirdi: acilista otomatik devam yoktur."
              : `${String(
                  surface.interrupted_runs.length,
                )} calisma yeniden baslatmadan sonra 'calisiyor' fazinda kaldi. Yalnizca listelenirler; acilista otomatik devam yoktur ve surdurmek sizin isleminizdir.`}
          </p>
          {surface.interrupted_runs.map((run) => (
            <p className="font-mono text-xs text-muted" key={run.id}>
              {`${shortId(run.id)} · gorev ${shortId(run.task_id)} · ${
                RUN_PHASE_LABEL[run.phase]
              }`}
            </p>
          ))}
        </section>

        <Separator />

        {/* --- the task list ------------------------------------------- */}
        <section aria-label="Gorev listesi" className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold text-foreground">
            {`Gorevler (${String(list.task_count)})`}
          </h3>
          <p className="text-xs text-muted" data-testid="tasks-unproducible">
            {list.unproducible_detail}
          </p>
          <p className="font-mono text-xs text-muted">
            {`Uretilebilen durumlar: ${list.producible_states.join(", ")} · uretilemeyen: ${
              list.unproducible_states.length === 0
                ? "(bos)"
                : list.unproducible_states.join(", ")
            }`}
          </p>

          {list.tasks.length === 0 ? (
            <p className="text-sm text-muted">
              Kayitli gorev yok. Bu, yapilacak is olmadigi anlamina gelmez;
              yalnizca bu istasyonda henuz gorev acilmadigi anlamina gelir. Is
              Tara bolumunden bir aday yerel gorev olarak acilabilir.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {list.tasks.map((entry) => (
                <li className="rounded-lg border border-border p-2" key={entry.id}>
                  <label className="flex items-center gap-2">
                    <input
                      checked={selected === entry.id}
                      disabled={busy !== null}
                      name={`${ids}-task`}
                      onChange={() => void openTask(entry.id)}
                      type="radio"
                      value={entry.id}
                    />
                    <span className="text-sm font-medium text-foreground">{entry.title}</span>
                  </label>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <StatusPill label={STATE_LABEL[entry.state]} tone="inactive" />
                    <span className="font-mono text-xs text-muted">
                      {`${shortId(entry.id)} · modul ${entry.module_id} · guncellendi ${formatLocal(
                        entry.updated_at,
                      )}`}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {task !== null && detail !== null && (
          <>
            <Separator />

            {/* --- one task ------------------------------------------- */}
            <section aria-label="Gorev ayrintisi" className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-foreground">{task.title}</h3>
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill label={STATE_LABEL[task.state]} tone="inactive" />
                <span className="font-mono text-xs text-muted">
                  {`${shortId(task.id)} · kaynak ${task.source_id} · surum ${shortId(
                    task.source_version_id,
                  )}`}
                </span>
              </div>
              <p className="text-xs text-muted" data-testid="tasks-state-detail">
                {task.state_detail}
              </p>

              <EvidenceFields task={task} />

              <div className="flex flex-col gap-2">
                <h4 className="text-xs font-semibold text-foreground">Durum degisikligi</h4>
                <p className="text-xs text-muted">
                  Bu bes gecisi kullanici ister. 'Calisiyor' ve 'duraklatildi'
                  burada yoktur: onlara ancak bir plan kaydedildikten sonra,
                  calisma islemleriyle gecilir. 'Yayima hazir' istenemez; uc
                  alanin ayri ayri dogrulanmasindan turetilir.
                </p>
                <div className="flex flex-wrap gap-2">
                  {TRANSITIONS.map((entry) => (
                    <Button
                      isDisabled={busy !== null}
                      key={entry.target}
                      onPress={() => void move(entry.target)}
                      size="sm"
                      variant="secondary"
                    >
                      {entry.label}
                    </Button>
                  ))}
                </div>
              </div>

              <p className="text-xs text-muted" data-testid="tasks-run-honesty">
                {detail.honesty}
              </p>
            </section>

            <Separator />

            {/* --- the plan composer ---------------------------------- */}
            <section aria-label="Plan olustur" className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-foreground">Plan olustur</h3>
              <p className="text-xs text-muted">
                Plan kaydetmek hicbir seyi calistirmaz. Kaydedilen plan
                dondurulur: farkli bir plan yeni bir calismadir ve eskisi
                yargilandigi olcutu korur. Plan kaydetmek icin gorev 'onay
                bekliyor' durumunda olmalidir.
              </p>

              <fieldset className="flex flex-col gap-2">
                <legend className="text-xs font-semibold text-foreground">
                  Adim icin arac secin
                </legend>
                {surface.tools.map((tool) => (
                  <label className="flex items-start gap-2" key={tool.id}>
                    <input
                      checked={toolId === tool.id}
                      disabled={busy !== null}
                      name={`${ids}-tool`}
                      onChange={() => {
                        setToolId(tool.id);
                        setArgs({});
                      }}
                      type="radio"
                      value={tool.id}
                    />
                    <span className="text-xs text-muted">
                      <span className="font-mono text-foreground">{tool.id}</span>
                      {` — ${SCOPE_LABEL[tool.scope]}`}
                    </span>
                  </label>
                ))}
              </fieldset>

              {chosenTool !== null &&
                chosenTool.params.map((param) => (
                  <TextField
                    className="w-full"
                    key={param.name}
                    onChange={(next: string) =>
                      setArgs((current) => ({ ...current, [param.name]: next }))
                    }
                    value={args[param.name] ?? ""}
                  >
                    <Label>
                      {`${param.name} (${param.type}${param.required ? ", zorunlu" : ", istege bagli"})`}
                    </Label>
                    {param.type === "json_text" || param.type === "text" ? (
                      <TextArea rows={4} variant="secondary" />
                    ) : (
                      <Input autoComplete="off" variant="secondary" />
                    )}
                  </TextField>
                ))}

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  isDisabled={busy !== null || toolId === ""}
                  onPress={addStep}
                  size="sm"
                  variant="secondary"
                >
                  Adimi plana ekle
                </Button>
                <span className="text-xs text-muted">
                  {`Plandaki adim sayisi: ${String(draft.length)}`}
                </span>
              </div>

              {draft.length > 0 && (
                <ul className="flex flex-col gap-1" data-testid="tasks-draft-steps">
                  {draft.map((item, index) => (
                    <li
                      className="font-mono text-xs text-muted"
                      key={`${item.toolId}-${String(index)}`}
                    >
                      {`${String(index + 1)}. ${item.toolId} · argumanlar: ${
                        Object.keys(item.args).length === 0
                          ? "(yok)"
                          : Object.keys(item.args).join(", ")
                      }`}
                    </li>
                  ))}
                </ul>
              )}

              <TextField className="w-full" onChange={setArtifacts} value={artifacts}>
                <Label>Soz verilen cikti dosyalari (virgulle ayrilmis)</Label>
                <Input autoComplete="off" variant="secondary" />
              </TextField>

              <TextField className="w-full" onChange={setCondition} value={condition}>
                <Label>Basari olcutu (kaydedilir, bu surumde kosulmaz)</Label>
                <TextArea rows={3} variant="secondary" />
              </TextField>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  isDisabled={
                    busy !== null || draft.length === 0 || condition.trim() === ""
                  }
                  onPress={() => void recordPlan()}
                >
                  {busy === "plan" ? "Kaydediliyor..." : "Plani kaydet (calistirmaz)"}
                </Button>
                <span className="text-xs text-muted">
                  Kaydetmek calistirmaz. Calistirmak, dort onaydan sonra ayri
                  bir islemdir.
                </span>
              </div>
            </section>

            <Separator />

            {/* --- the runs ------------------------------------------- */}
            <section aria-label="Calismalar" className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-foreground">
                {`Calismalar (${String(detail.runs.length)})`}
              </h3>
              {detail.runs.length === 0 ? (
                <p className="text-sm text-muted">
                  Bu gorev icin kaydedilmis plan yok. Bos bir liste, yapilacak
                  is olmadigini degil, henuz plan yazilmadigini gosterir.
                </p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {detail.runs.map((run) => (
                    <RunCard
                      approvalRunId={approvalRunId}
                      approvals={approvals}
                      busy={busy}
                      key={run.id}
                      onApprove={approve}
                      onResume={(runId) => void act(runId, "resume")}
                      onStart={(runId) => void act(runId, "start")}
                      onStop={(runId) => void act(runId, "stop")}
                      run={run}
                      stopStatement={surface.stop_statement}
                    />
                  ))}
                </ul>
              )}
            </section>

            <Separator />

            {/* --- the workspace -------------------------------------- */}
            <section aria-label="Calisma alani" className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold text-foreground">Calisma alani</h3>
              <p className="text-xs text-muted">
                Dosyalar adiyla ve ozetiyle listelenir; hicbir yol gosterilmez
                ve hicbir dosya bu ekrandan calistirilamaz.
              </p>
              {detail.workspace_files.length === 0 ? (
                <p className="text-sm text-muted">Calisma alaninda dosya yok.</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {detail.workspace_files.map((file) => (
                    <li className="font-mono text-xs text-muted" key={file.name}>
                      {`${file.name} · ${String(file.byte_count)} bayt · ozet ${shortId(
                        file.sha256,
                      )}`}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </Card.Content>
    </Card>
  );
}
