import { Alert, Button, Card, Checkbox, Input, Label, Separator, TextArea, TextField } from "@heroui/react";
import { type ReactNode, useCallback, useEffect, useId, useState } from "react";

import {
  type ApiError,
  deriveTaskPublishReadiness,
  fetchAgentSurface,
  fetchEvidenceRecords,
  fetchOpenCodeStatus,
  fetchProof,
  fetchTaskRuns,
  fetchTasks,
  forgetModelPlanSession,
  proposeModelPlan,
  recordProofAcceptance,
  recordProofPublicShare,
  resumeTaskRun,
  startTaskRun,
  stopTaskRun,
  toApiError,
  transitionTask,
} from "../../api/client";
import type {
  AgentAcceptanceKindName,
  AgentRunPhaseName,
  AgentRunStatus,
  AgentStepPhaseName,
  AgentSurfaceResponse,
  AgentTaskRunsResponse,
  AgentTestResultStateName,
  AgentToolScopeName,
  AgentToolStatus,
  EvidenceList,
  EvidenceWriteOutcome,
  ModelProposalOutcomeName,
  ModelProposalResponse,
  OpenCodeStatus,
  ProofWorkspace,
  TaskCheckState,
  TaskEvidenceFieldName,
  TaskListResponse,
  TaskStateName,
  TaskStatusResponse,
  TaskUserTransitionName,
} from "../../api/types";
import { shortDigest } from "../../lib/digest";
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
 * 2. **A produced file is not a passed test.** `test_result_state` reports
 *    `passed`, `failed` or `not_implemented`, and the third is what a plan
 *    that recorded no machine-checkable condition earns - a run may write
 *    every file it promised and still leave the task short of publication.
 *    The verdict is derived from the plan's own acceptance conditions,
 *    re-decided over the workspace on every read; it is never a badge this
 *    screen composes and never something a request may assert (SI-222).
 * 3. **The model proposes; it does not run.** A model turn ends, at best, in
 *    a *recorded plan* in the `planned` phase. It passes the same four
 *    approvals a hand-written plan does, it cannot approve itself, it cannot
 *    add a tool to its own registry, and there is no code path from the
 *    planner to the runner's start. The model's reasoning is not stored and
 *    not shown, and `usage`/`cost` are the **provider's** statement rather
 *    than a measurement this station made (ADR-0012, ADR-0008 4).
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
  | "resume"
  // Paket H3. Three more, kept apart from the six above for the reason the
  // six are kept apart from each other: "the bundle could not be read",
  // "the acceptance was refused" and "the send could not be attached" are
  // three findings, and only the first repeats safely.
  | "proof"
  | "accept"
  | "mark"
  // Paket H4 / ADR-0012. Four more, and they stay apart for the same reason
  // the others do: "the model lane could not be read", "the turn failed",
  // "the session could not be dropped" and "the gate refused" are four
  // findings with four remedies, and only the first two repeat safely.
  | "modelLane"
  | "modelTurn"
  | "modelForget"
  | "readiness"
  // The one press that moves a `suggested` task and then asks for a plan.
  // Two members, not one, and the split is the whole point: "nothing
  // happened" and "the first half happened" are different findings, and only
  // the second one has to warn that pressing again may spend another turn.
  | "doWork"
  | "doWorkAfterMove";

type Busy = Step | null;

const ERROR_TITLE: Record<Step, string> = {
  read: "Gorev yuzeyi okunamadi",
  task: "Gorev ayrintisi okunamadi",
  transition: "Durum degistirilemedi",
  plan: "Plan kaydedilemedi",
  start: "Calisma baslatilamadi",
  stop: "Durdurma istegi islenemedi",
  resume: "Calisma surdurulemedi",
  proof: "Kanit paketi okunamadi",
  accept: "Kabul kaydedilemedi",
  mark: "Gonderim bu goreve isaretlenemedi",
  modelLane: "Model baglantisinin durumu okunamadi",
  modelTurn: "Model turu tamamlanamadi",
  modelForget: "Model oturumu unutulamadi",
  readiness: "Yayin hazirligi degerlendirilemedi",
  doWork: "Bu is baslatilamadi: gorev onaya alinamadi ve model turu istenmedi",
  // Precise on purpose. The task really did move, and a person who read
  // "nothing happened" here would press again - which may spend a turn the
  // first press already paid for.
  doWorkAfterMove:
    "Gorev onaya alindi, plan kaydedilmedi: model turu tamamlanamadi ve yeniden basmak bir model turu daha harcayabilir",
};

/**
 * The nine states, in the user's language.
 *
 * The **wire** names are untouched and cannot be touched: they are pinned by
 * the API tests and by `docs/security-invariants.md`. What is written here is
 * the word a person reads, and two of them were measured wrong the first time
 * this build met its owner.
 *
 * The rule the two rewrites follow: **a label that is the target of a control
 * must name what that control reached, never what is still outstanding.** A
 * person pressed "Onaya al", the task moved, and the screen answered "Onay
 * bekliyor" - which reads as "your click did nothing", and was reported as
 * exactly that. The state really is waiting for an approval, and the backend
 * still says so in `state_detail`, which is rendered verbatim beside this
 * label; the difference is that a *detail sentence* may describe what is
 * pending, while the *name of the state a button just produced* may not,
 * because that is the word the reader checks their click against.
 */
export const STATE_LABEL: Record<TaskStateName, string> = {
  suggested: "Onerildi",
  // was: "Onay bekliyor" - the measured defect. The button says "Onaya al".
  awaiting_approval: "Onaya alindi",
  running: "Calisiyor",
  paused: "Duraklatildi",
  blocked: "Engellendi",
  failed: "Basarisiz",
  // was: "Inceleme gerekiyor" - the same defect in the same shape. The button
  // says "Incelemeye al", so a person who presses it and is told a review is
  // "needed" has been told their action did not land.
  review_needed: "Incelemeye alindi",
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

/** Scopes a step can hold that put bytes in the workspace. */
const WRITING_SCOPES: ReadonlySet<string> = new Set(["write_workspace"]);

/** Whether any step of this run is one that can write. */
function writesAnything(run: AgentRunStatus): boolean {
  return run.steps.some((step) => WRITING_SCOPES.has(step.scope));
}

/**
 * What a finished run actually established, as a sentence and a tone.
 *
 * `completed` is one phase and three different findings, and the screen used
 * to print the best of them for all three. "Bitti: her adim yapildi, soz
 * verilen her cikti var" is **vacuously true** of a plan that promised
 * nothing: zero artifacts were promised, so every promised artifact exists,
 * and the reader is handed a green tick for a run that made nothing. The
 * owner met exactly that and could not tell whether anything had happened.
 *
 * The three are separated by what the run itself carries - the promise it
 * recorded and the scopes its steps hold - never by a new phase invented for
 * this screen and never by reading the task's workspace, which holds files
 * this run did not write.
 *
 * The honest half is kept and kept said: "her adim yapildi" is true in all
 * three, and only the clause claiming an achievement nobody made is withheld.
 * Neither of the two quieter endings is a failure - nothing was refused, no
 * ceiling was hit and no promise was broken - so they are toned `inactive`
 * rather than `problem`, which stays what `artifact_missing` and the two
 * refusals mean.
 */
export function deriveRunEnding(run: AgentRunStatus): {
  readonly label: string;
  readonly tone: "ok" | "pending" | "inactive" | "problem";
} {
  if (run.phase !== "completed") {
    return { label: RUN_PHASE_LABEL[run.phase], tone: RUN_PHASE_TONE[run.phase] };
  }
  if (run.expected_artifacts.length > 0) {
    return { label: RUN_PHASE_LABEL.completed, tone: RUN_PHASE_TONE.completed };
  }
  if (writesAnything(run)) {
    return {
      label: "Bitti: her adim yapildi, bir dosya uretildi ama plan onu soz vermedi, o yuzden denetlenmedi",
      tone: "inactive",
    };
  }
  return {
    label: "Bitti: her adim yapildi, ama plan bir cikti soz vermedi ve hicbir dosya uretmedi",
    tone: "inactive",
  };
}

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

/**
 * The five acceptance conditions, in the user's language.
 *
 * Keyed by the registry's own name so the set the screen can render and the
 * set the backend publishes cannot drift apart: a sixth kind appearing on the
 * wire is a compile error here, not a blank cell.
 */
const ACCEPTANCE_KIND_LABEL: Record<AgentAcceptanceKindName, string> = {
  artifact_exists: "Dosya calisma alaninda var mi",
  artifact_is_json: "Dosya gecerli bir JSON belgesi mi",
  artifact_has_json_keys: "JSON ust duzey anahtarlarinin hepsi var mi",
  artifact_contains: "Dosya istenen metni iceriyor mu",
  artifact_digest_is: "Dosyanin SHA-256 ozeti bekleneni veriyor mu",
};

/**
 * The three verdicts, each said in full.
 *
 * `not_implemented` is never worded as a near-pass and never toned as one: a
 * plan that recorded no machine-checkable condition has not been tested, and
 * the sentence says which of the three questions was answered.
 */
const TEST_RESULT_LABEL: Record<AgentTestResultStateName, string> = {
  passed: "Gecti: planin yazdigi kabul kosullarinin hepsi su anda saglaniyor",
  failed: "Kaldi: en az bir kabul kosulu su anda saglanmiyor",
  not_implemented:
    "Uygulanmadi: plan, makinenin karar verebilecegi bir kabul kosulu yazmadi",
};

const TEST_RESULT_TONE: Record<AgentTestResultStateName, "ok" | "problem" | "inactive"> = {
  passed: "ok",
  failed: "problem",
  not_implemented: "inactive",
};

/**
 * The seven endings of one model turn, in the user's language.
 *
 * None of them is "it ran", because there is no such outcome: the best a turn
 * can do is `planned`, and even that is a plan waiting for four approvals and
 * a separate start.
 *
 * Three of the seven are turns that produced **no call**, and the wording is
 * where the difference between them lives. Only `finished` may say the model
 * stopped: that is `finish_reason: "stop"` and nothing else. `truncated` is an
 * answer the provider **cut** at the output ceiling, and `inconclusive` is a
 * turn whose ending this build could not read. Saying "it stopped" about
 * either of those would be claiming a decision nobody measured - which is the
 * defect these two members were split out of.
 */
const PROPOSAL_OUTCOME_LABEL: Record<ModelProposalOutcomeName, string> = {
  planned: "Model bir plan onerdi ve plan kaydedildi (hicbir sey calistirilmadi)",
  finished: "Model arac cagirmayi birakti; oturum bitti",
  truncated: "Yanit cikti tavaninda kesildi; oturum acik kaldi",
  inconclusive: "Arac cagrisi gelmedi; nedeni okunamadi, oturum kapatilmadi",
  refused: "Oneri reddedildi",
  budget_exhausted: "Model cagrisi tavanina ulasildi; istek gonderilmedi",
  provider_failed: "Saglayici reddetti, basarisiz oldu veya hic cevap vermedi",
};

const PROPOSAL_OUTCOME_TONE: Record<
  ModelProposalOutcomeName,
  "ok" | "problem" | "inactive" | "pending"
> = {
  planned: "pending",
  // `inactive` is the tone for a session that is over. The two below are not
  // over, so they must not borrow it: a cut answer that looked the same as a
  // finished one is exactly what sent people away without retrying.
  finished: "inactive",
  truncated: "problem",
  inconclusive: "problem",
  refused: "problem",
  budget_exhausted: "problem",
  provider_failed: "problem",
};

/**
 * What the two non-endings mean, and what a person may do next.
 *
 * The backend already sends a full sentence in `detail`, and it is rendered
 * verbatim beside this. These are not a second copy of it: `detail` says what
 * the provider reported about *this* turn, and this says what the outcome
 * *is* - that nothing was proposed, that the session was not closed, and that
 * asking again is a thing the person is allowed to do. A pill and a provider
 * sentence together still left "so can I try again?" unanswered.
 *
 * Partial on purpose. The other five outcomes are complete in their own
 * label, and inventing a paragraph for each would bury these two.
 */
const PROPOSAL_OUTCOME_NOTE: Partial<Record<ModelProposalOutcomeName, string>> = {
  truncated:
    "Bu bir bitis degildir. Model arac cagirmaya gelemeden cikti tavaninda " +
    "kesildi: hicbir plan onerilmedi ve oturum kapatilmadi. Ayni gorev icin " +
    "turu yeniden isteyebilirsiniz; her istek bir tur harcar.",
  inconclusive:
    "Model hicbir arac cagrisi gondermedi ve turun neden bittigi bu yapida " +
    "okunamadi. Sebep, saglayicinin kendi yazimiyla yukaridaki cumlede " +
    "aktarilir; Station anlamini uydurmaz. Oturum kapatilmadi.",
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
export const TRANSITIONS: readonly { readonly target: TaskUserTransitionName; readonly label: string }[] = [
  { target: "awaiting_approval", label: "Onaya al" },
  { target: "review_needed", label: "Incelemeye al" },
  { target: "blocked", label: "Engellendi olarak isaretle" },
  { target: "failed", label: "Basarisiz olarak isaretle" },
  { target: "published", label: "Yayimlandi olarak isaretle" },
];

// --- what to do next -------------------------------------------------------

/**
 * The single next action, and the control that performs it.
 *
 * This exists because the screen used to answer eight questions before the
 * one a person arrives with. In `suggested` exactly one control on the whole
 * surface could do anything - the planner refuses a plan outside
 * `awaiting_approval`, and the only user transition out of `suggested` is to
 * it - and that control was the last thing on the screen, under four blocked
 * evidence cards and several paragraphs about what each field does not prove.
 *
 * Three properties, and each of them is a test:
 *
 * * **it is derived, never written into the JSX.** The line comes from this
 *   table and from the task's own runs. A tenth state that gained a label and
 *   no entry here renders nothing at all - so a runtime test walks
 *   `STATE_LABEL` and fails on the gap rather than letting the most important
 *   row of the screen go blank;
 * * **it names one action.** Not a list of what is possible: the single next
 *   thing, in this state, with what this task currently has;
 * * **it names the control verbatim.** The words in `control` are the words
 *   on the button, so a reader can search the screen for them. A state that
 *   offers no control says so, with an empty `control` *and* an empty
 *   `where`, rather than pointing at a button that is not there.
 */
export interface TaskNextStep {
  /** What to do next. One action, in the user's language. */
  readonly action: string;
  /** The label of the control that performs it, verbatim; "" when none. */
  readonly control: string;
  /** The block that control lives in; "" when there is no control. */
  readonly where: string;
}

/**
 * The two controls this screen is built around, named once.
 *
 * They are constants because three places have to agree on the exact words: a
 * button's label, the next-step line that tells a reader to look for it, and
 * the table that derives which of them applies. A literal repeated three
 * times is a literal that goes out of step twice.
 */
export const DO_THE_WORK_LABEL = "Bu isi yap";
export const START_THE_PLAN_LABEL = "Onayla ve baslat";
export const RESUME_THE_RUN_LABEL = "Onayla ve devam et";
/** The block both controls live in; the next-step line names it verbatim. */
export const PRIMARY_BLOCK_LABEL = "Bu gorevi yaptir";

const NEXT_STEP: Record<TaskStateName, TaskNextStep> = {
  suggested: {
    action:
      "Tek dugmeye basin: gorev onaya alinir ve ayni basista modelden bir plan istenir. Bir model turu harcanir ve o turun saglayicida bir para maliyeti vardir. Hicbir sey calistirilmaz; calistirma ikinci ve ayri bir onaydir.",
    control: DO_THE_WORK_LABEL,
    where: PRIMARY_BLOCK_LABEL,
  },
  awaiting_approval: {
    action:
      "Gorev onaya alindi ama kaydedilmis bir plan yok. Tek dugmeye basin: modelden bir plan istenir, bir tur harcanir ve plan, soz verdigi dosyalarin varligiyla denetlenmek uzere kaydedilir. Hicbir sey calistirilmaz.",
    control: DO_THE_WORK_LABEL,
    where: PRIMARY_BLOCK_LABEL,
  },
  running: {
    action:
      "Calisma sunucuda yurutuluyor. Buradaki tek islem onu durdurmaktir; ilerleme cubugu yoktur ve ekran kendiliginden yenilenmez.",
    control: "Durdur",
    where: "Calismalar",
  },
  paused: {
    action:
      "Durdurulmus calismayi ayni onayli kapsamda surdurun. Dugmenin ustundeki dort cumleyi okuyun; tek basis o dort onayi birlikte verir ve calismayi surdurur. Devam yeni bir adim eklemez.",
    control: RESUME_THE_RUN_LABEL,
    where: PRIMARY_BLOCK_LABEL,
  },
  blocked: {
    action:
      "Engelin sebebi giderildiyse gorevi yeniden onaya alin; engelli bir gorevde plan kaydedilemez.",
    control: "Onaya al",
    where: "Durum degisikligi",
  },
  failed: {
    action:
      "Bu gorev basarisiz olarak kapandi ve bu bir son durumdur: ileri tasinmaz. Ayni is icin yeni bir gorev acilir.",
    control: "",
    where: "",
  },
  review_needed: {
    action:
      "Kanit alanlari doldugunda yayin hazirligini degerlendirin. Bu islem bir durum istemez: uc kanit alaninin yeniden okunmasini ister ve karari kapi verir.",
    control: "Yayin hazirligini degerlendir (durumu istemez)",
    where: "Yayin hazirligi",
  },
  ready_to_publish: {
    action:
      "Uc kanit alani ayri ayri dogrulandi. Yayimi kendiniz yaptiysaniz gorevi yayimlandi olarak isaretleyin; bu isaret hicbir sey gondermez.",
    control: "Yayimlandi olarak isaretle",
    where: "Durum degisikligi",
  },
  published: {
    action:
      "Gorev yayimlandi olarak kapandi ve bu bir son durumdur: buradan baska bir duruma gecilmez.",
    control: "",
    where: "",
  },
};

/**
 * In `awaiting_approval`, a recorded plan changes what comes next.
 *
 * The one refinement the table alone cannot make, and it is derived from the
 * task's own runs rather than from a second state: "ask for a plan" and "run
 * the plan you already have" are different sentences, and pointing a person
 * at the planner when a plan is already sitting there unconsented is the same
 * class of mistake this whole line exists to fix.
 */
const RUN_THE_RECORDED_PLAN: TaskNextStep = {
  action:
    "Kaydedilmis bir plan var. Dugmenin hemen ustundeki dort cumleyi okuyun; tek basis o dort onayi birlikte verir ve calismayi baslatir. Onay bu plana aittir; farkli bir plan yeni bir calismadir ve kendi onayini ister.",
  control: START_THE_PLAN_LABEL,
  where: PRIMARY_BLOCK_LABEL,
};

/** Derive the next step from the task's own state and its own runs. */
export function deriveNextStep(
  state: TaskStateName,
  runs: readonly AgentRunStatus[],
): TaskNextStep {
  if (state === "awaiting_approval" && lastInPhase(runs, "planned") !== null) {
    return RUN_THE_RECORDED_PLAN;
  }
  return NEXT_STEP[state];
}

// --- the two controls ------------------------------------------------------

/**
 * The one act this task needs next, and the plan it would act on.
 *
 * The whole of this screen's answer to a measured defect: a person who had
 * scanned rooms, found real work and picked it still could not get it done.
 * Seven actions stood in the way - "Onaya al", a criterion, "Modelden plan
 * oner", four separate checkboxes and "Onayli plani calistir" - and each of
 * them was correct on its own.
 *
 * Three properties, and each of them is a test:
 *
 * * **`start` is impossible without a recorded plan.** It is not a disabled
 *   button: there is no `run` to name, so there is no action at all. That is
 *   what makes "no proposal may start itself" a shape rather than a rule
 *   somebody has to keep;
 * * **the plan is read from the runs, every time.** Never remembered from the
 *   last press: a *different* plan is a different run, and a consent given to
 *   one may not carry the next one into a start nobody looked at;
 * * **it is derived here, not written into the JSX**, for the same reason
 *   {@link deriveNextStep} is: the next-step line and the control it names
 *   have to be the same decision, or the line points at a button that is not
 *   there.
 */
export type PrimaryAction =
  | { readonly kind: "do"; readonly label: string }
  | { readonly kind: "start"; readonly label: string; readonly run: AgentRunStatus }
  | { readonly kind: "resume"; readonly label: string; readonly run: AgentRunStatus };

/** The last run in a given phase, or `null`. Latest wins: a re-plan is newer. */
function lastInPhase(
  runs: readonly AgentRunStatus[],
  phase: AgentRunPhaseName,
): AgentRunStatus | null {
  const matching = runs.filter((run) => run.phase === phase);
  return matching.length === 0 ? null : matching[matching.length - 1]!;
}

export function derivePrimaryAction(
  state: TaskStateName,
  runs: readonly AgentRunStatus[],
): PrimaryAction | null {
  if (state === "suggested") return { kind: "do", label: DO_THE_WORK_LABEL };
  if (state === "awaiting_approval") {
    const planned = lastInPhase(runs, "planned");
    return planned === null
      ? { kind: "do", label: DO_THE_WORK_LABEL }
      : { kind: "start", label: START_THE_PLAN_LABEL, run: planned };
  }
  if (state === "paused") {
    const paused = lastInPhase(runs, "paused");
    if (paused !== null) return { kind: "resume", label: RESUME_THE_RUN_LABEL, run: paused };
  }
  return null;
}

// --- progressive disclosure ------------------------------------------------

/**
 * Every collapsible block on this screen.
 *
 * Named as a closed type so the two tables below cannot drift apart: a block
 * added without a rule for when it opens, or without a sentence for why it is
 * closed, is a compile error rather than a blank summary line.
 */
type BlockId =
  | "execution"
  | "budget"
  | "trust"
  | "interrupted"
  | "fields"
  | "readiness"
  | "acceptance"
  | "share"
  | "model"
  | "composer"
  | "runs"
  | "workspace";

/**
 * Whether a block can complete what its heading promises, right now.
 *
 * Written once, derived from the rules the **backend** enforces rather than
 * from a preference about layout:
 *
 * * six blocks carry no control at all. They are measurement and reasoning,
 *   and they can never act - which is not a reason to remove them, only a
 *   reason to stop putting them between a person and a button;
 * * the publication gate calls `transition(READY_TO_PUBLISH)`, and the state
 *   machine allows that edge only from `review_needed`
 *   (`tasks/states.py::ALLOWED_TRANSITIONS`);
 * * the planner refuses a proposal outside `AWAITING_APPROVAL` whole, so the
 *   composer and the model lane can only act there;
 * * the runner's three controls belong to the three states a run can be in;
 * * acceptance and the public-share mark carry **no** state precondition on
 *   the wire - the routes write a field and stop - so they can act in every
 *   state and this rule never folds them. That is deliberate rather than an
 *   oversight: a first pass closed acceptance whenever the task had no
 *   recorded run, and `review_needed` with an empty run list is exactly the
 *   case where a person *is* about to accept a bundle. Claiming a
 *   precondition the backend does not have would be the same class of lie as
 *   hiding one it does.
 *
 * **Collapsing is never a gate.** Every one of these blocks expands on
 * demand, and the preconditions of the controls inside them are exactly what
 * they were: nothing here makes a control easier - or harder - to press.
 */
const BLOCK_ACTS: Record<
  BlockId,
  (task: TaskStatusResponse | null, runs: readonly AgentRunStatus[]) => boolean
> = {
  execution: () => false,
  budget: () => false,
  trust: () => false,
  interrupted: () => false,
  fields: () => false,
  workspace: () => false,
  readiness: (task) => task?.state === "review_needed",
  // Neither route carries a state precondition - they write a field and stop -
  // so neither is ever *unable* to act, and an earlier pass that folded
  // acceptance whenever a task had no recorded run was caught by a
  // `review_needed` test and was right to be: claiming a precondition the
  // backend does not have is the same class of lie as hiding one it does.
  //
  // What folds them here is not a precondition but an order. In `suggested`
  // and `awaiting_approval` there is nothing to accept yet and nothing to
  // mark shared, and putting both between a person and the one control that
  // can act is how this screen became unreadable. They open from
  // `review_needed` onward, which is where the earlier test lives, and they
  // expand on demand everywhere else.
  acceptance: (task) => task?.state !== "suggested" && task?.state !== "awaiting_approval",
  share: (task) => task?.state !== "suggested" && task?.state !== "awaiting_approval",
  // Three blocks that *can* act and are folded anyway, which is the one place
  // this table stopped being about capability.
  //
  // The two controls above them carry a task from a scan suggestion to a
  // finished run, so these three are the second way of doing the same thing:
  // choose the criterion by hand, spend the turn by hand, start the plan by
  // hand. Nothing here is removed and nothing here got harder to press - a
  // person who wants the long road opens the heading and takes it. What they
  // stopped doing is standing between a person and the one button that
  // answers the question they arrived with.
  model: () => false,
  composer: () => false,
  // `running` is the exception: the only control that can act on a run in
  // flight is "Durdur", and it lives here.
  runs: (task) => task?.state === "running",
};

/** Said of every block that has nothing to press, so the absence is a claim. */
const NO_CONTROL_HERE =
  "Bu bolumde basilacak bir kontrol yoktur: yalnizca olculmus bilgi ve gerekce. Hicbir cumle silinmedi; basligi secerek tamamini acabilirsiniz.";

/**
 * Said of the three blocks that can act and are folded anyway.
 *
 * The distinction matters and is why this is not {@link NO_CONTROL_HERE}:
 * those blocks have nothing to press, and these have controls that work
 * exactly as they did. Calling them "closed" without saying they still work
 * would be the screen hiding a capability it still has.
 */
const SECONDARY_HERE =
  "Buradaki kontroller calisir ve hicbiri kaldirilmadi; yukaridaki iki dugme ayni isi daha kisa yoldan yapar. Bu bolum ayrintiyi ve elle yurutulen uzun yolu tutar: basligi secerek acabilirsiniz.";

/**
 * Why a block is closed, in states rather than in adjectives.
 *
 * Reads `STATE_LABEL`, so the vocabulary fix above reaches these sentences
 * too and a state cannot be called one thing in a pill and another in an
 * explanation.
 */
function needsState(
  task: TaskStatusResponse | null,
  states: readonly TaskStateName[],
): string {
  if (task === null) return "Once bir gorev secin.";
  return `Buradaki kontroller yalnizca ${states
    .map((state) => `'${STATE_LABEL[state]}'`)
    .join(" veya ")} durumunda sonuc verir; gorev su anda '${STATE_LABEL[task.state]}'.`;
}

const BLOCK_CLOSED_REASON: Record<BlockId, (task: TaskStatusResponse | null) => string> = {
  execution: () => NO_CONTROL_HERE,
  budget: () => NO_CONTROL_HERE,
  trust: () => NO_CONTROL_HERE,
  interrupted: () => NO_CONTROL_HERE,
  fields: () => NO_CONTROL_HERE,
  workspace: () => NO_CONTROL_HERE,
  readiness: (task) => needsState(task, ["review_needed"]),
  // Never reached: both act in every state. Kept rather than removed, because
  // the type is what stops a thirteenth block shipping without a reason.
  acceptance: () => "",
  share: () => "",
  model: () => SECONDARY_HERE,
  composer: () => SECONDARY_HERE,
  runs: () => SECONDARY_HERE,
};

/**
 * One collapsible block: a heading and a summary that are always readable,
 * and a body one keystroke away.
 *
 * Native `details`/`summary` rather than a hand-rolled toggle, and that is the
 * accessibility decision rather than a convenience: the browser gives the
 * disclosure its role, its expanded state, its keyboard operation and its
 * announcement for free, and the body stays in the document either way. A
 * `hidden` div behind an `aria-expanded` button would have had to reproduce
 * all four, and any one of them missed is a block a screen-reader user cannot
 * reach at all.
 *
 * The open state is React state seeded from `open` and re-seeded when the
 * derivation changes - so moving a task from `suggested` to `awaiting_approval`
 * opens the composer, while an unrelated re-render never closes a block a
 * person opened by hand.
 */
function DisclosureBlock({
  children,
  label,
  level,
  open,
  summary,
  summaryTestId,
}: {
  readonly children: ReactNode;
  readonly label: string;
  readonly level: 3 | 4;
  readonly open: boolean;
  readonly summary: string;
  readonly summaryTestId: string;
}) {
  const [expanded, setExpanded] = useState(open);
  const [derived, setDerived] = useState(open);
  if (derived !== open) {
    setDerived(open);
    setExpanded(open);
  }
  const Heading = level === 3 ? "h3" : "h4";
  return (
    <section aria-label={label} className="flex flex-col gap-2">
      <details
        className="rounded-lg border border-border p-2"
        onToggle={(event) => {
          setExpanded(event.currentTarget.open);
        }}
        open={expanded}
      >
        <summary className="cursor-pointer">
          <Heading
            className={`inline ${level === 3 ? "text-sm" : "text-xs"} font-semibold text-foreground`}
          >
            {label}
          </Heading>
          <span className="mt-1 block text-xs text-muted" data-testid={summaryTestId}>
            {summary}
          </span>
        </summary>
        <div className="mt-3 flex flex-col gap-3">{children}</div>
      </details>
    </section>
  );
}

/** Join a block's standing description with the reason it is folded away. */
function blockSummary(base: string, whyClosed: string): string {
  return whyClosed === "" ? base : `${base} ${whyClosed}`;
}

/**
 * The four things a person is shown, and consents to, before a plan runs.
 *
 * They used to be four checkboxes and are now four sentences above one
 * button, and the rule did not move: **a person is shown these four specific
 * things and consents before anything runs.** What changed is that the
 * consent is one deliberate act instead of five, which is a claim about the
 * number of clicks and not about what is being agreed to. The four are still
 * four, still in the open, still above the control, and still unreadable-past
 * - nothing here is behind a disclosure.
 *
 * The set stays a list rather than a paragraph for the reason the four
 * evidence fields do: four questions folded into prose are four questions a
 * reader skips.
 */
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


/**
 * The model lane, in this surface's own words.
 *
 * It said the lane was closed until ADR-0012 measured the tool-call contract
 * and opened it. The sentence changed because the **fact** changed, not
 * because the rule softened: what used to be guaranteed by an empty set is
 * now guaranteed by structure, and this says which structure. A screen that
 * kept the old wording would be claiming safety from an absence that is no
 * longer there.
 */
const MODEL_LANE_STATEMENT =
  "Model plan ONERIR, calistirmaz. Bir model turu en iyi ihtimalle kaydedilmis bir plan uretir; o plan da elle yazilmis bir plan gibi ayni dort onaydan gecer. Model kendi planina onay veremez, kendi arac listesine arac ekleyemez ve bir calismayi baslatamaz: baslatma ayri bir kullanici islemidir ve planlayicidan kosucunun baslatma yoluna giden bir kod yolu yoktur. Onerilen ad kayitli araclarda yoksa oneri butunuyle reddedilir. Modelin muhakemesi saklanmaz ve gosterilmez.";

/** Arbitrary execution stayed closed when the model lane opened. */
const NO_ARBITRARY_EXECUTION_STATEMENT =
  "Keyfi kod ve kabuk yurutmesi kapali kalir. Model yolunun acilmasi bunu acmaz: model yalnizca kayitli, deterministik araclari onerebilir ve bir metni komut olarak kosacak bir yol bu urunde yoktur.";

/**
 * "A produced file is not a passed test", as a sentence on screen.
 *
 * It used to say the test result stays `not_implemented` no matter what a run
 * produced. That is now only true of a plan that recorded no machine-checkable
 * condition, so the sentence says *that* instead of the older, wider claim it
 * had outgrown.
 */
const UNTESTED_STATEMENT =
  "Uretilmis bir dosya gecmis bir test degildir. Test sonucu, planin kendi kabul kosullarindan turetilir ve her okumada calisma alani uzerinde yeniden karara baglanir. Hicbir kabul kosulu yazmamis bir plan, soz verdigi her dosyayi uretmis olsa bile 'uygulanmadi' alir ve gorevi yayimin esiginde birakir.";

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

/** A single draft acceptance condition: a registered kind and its arguments. */
interface DraftCondition {
  readonly kind: AgentAcceptanceKindName;
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
function ExecutionBlock({
  open,
  summary,
  surface,
}: {
  readonly open: boolean;
  readonly summary: string;
  readonly surface: AgentSurfaceResponse;
}) {
  const { execution } = surface;
  return (
    <DisclosureBlock
      label="Yurutme durumu"
      level={3}
      open={open}
      summary={blockSummary(
        `Keyfi kod ve kabuk yurutmesi kapali (${execution.reason}). Olculen izolasyon envanteri ve bu ekranin dort durustluk cumlesi burada durur.`,
        summary,
      )}
      summaryTestId="tasks-execution-summary"
    >
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
      <p className="text-xs text-muted" data-testid="tasks-no-arbitrary-execution">
        {NO_ARBITRARY_EXECUTION_STATEMENT}
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
    </DisclosureBlock>
  );
}

/** The ceiling, its units, and the units this product refuses to use. */
function BudgetBlock({
  open,
  summary,
  surface,
}: {
  readonly open: boolean;
  readonly summary: string;
  readonly surface: AgentSurfaceResponse;
}) {
  const { ceiling } = surface;
  return (
    <DisclosureBlock
      label="Butce ve tavan"
      level={3}
      open={open}
      summary={blockSummary(
        `Tavan: en cok ${String(ceiling.max_tool_calls)} arac cagrisi, ${String(
          ceiling.max_wall_clock_seconds,
        )} saniye, eszamanlilik ${String(
          ceiling.max_concurrency,
        )}. Reddedilen birimler: ${ceiling.refused_units.join(", ")}.`,
        summary,
      )}
      summaryTestId="tasks-budget-summary"
    >
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
    </DisclosureBlock>
  );
}

/** The registered tools, and the boundary around them. */
function TrustBoundaryBlock({
  open,
  summary,
  tools,
}: {
  readonly open: boolean;
  readonly summary: string;
  readonly tools: readonly AgentToolStatus[];
}) {
  return (
    <DisclosureBlock
      label="Guven siniri"
      level={3}
      open={open}
      summary={blockSummary(
        `${String(
          tools.length,
        )} kayitli arac; agent'in erisemedikleri ve yapamadiklari liste halinde.`,
        summary,
      )}
      summaryTestId="tasks-trust-summary"
    >
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
    </DisclosureBlock>
  );
}

/** The four fields, each on its own line. Never summed into a verdict. */
function EvidenceFields({
  open,
  summary,
  task,
}: {
  readonly open: boolean;
  readonly summary: string;
  readonly task: TaskStatusResponse;
}) {
  return (
    <DisclosureBlock
      label="Dort alan"
      level={4}
      open={open}
      summary={blockSummary(
        `Dort ayri alan, hicbiri digerinin yerine gecmez. ${
          task.ready_to_publish
            ? "Uc alan ayri ayri dogrulandi."
            : `Bekleyen alanlar: ${
                task.blocking_fields.length === 0 ? "(yok)" : task.blocking_fields.join(", ")
              }.`
        }`,
        summary,
      )}
      summaryTestId="tasks-fields-summary"
    >
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
      {/* The sentence changed when the route arrived, and the guarantee did
          not. There is now a way to *reach* the derived state and still no
          way to *ask for* it: the request carries no target field, the state
          is absent from the user transition list, and what the caller asks
          for is a re-reading of three fields (SI-222). */}
      <p className="text-xs text-muted" data-testid="tasks-publish-unreachable">
        &quot;Yayima hazir&quot; istenemez. Asagidaki durum degisikligi
        dugmelerinin arasinda karsiligi yoktur ve bu urunde hicbir istek onu
        adiyla hedefleyemez: yayin hazirligi istegi bir hedef alani tasimaz.
        Istenen sey, uc kanit alaninin yeniden okunmasidir; karari kapi verir
        ve ayni istegi kac kez yaparsaniz yapin cevap kanitin bir fonksiyonu
        olarak kalir.
      </p>
      <p className="text-xs text-muted" data-testid="tasks-public-share">
        {task.public_share_detail}
      </p>
      <p className="text-xs text-muted" data-testid="tasks-task-budget">
        {task.budget_detail}
      </p>
    </DisclosureBlock>
  );
}

/**
 * One run: its plan, its steps, its usage and its ending, kept apart.
 *
 * The record of a run, and - apart from "Durdur" - no longer a place a run
 * starts. Consent and starting moved to the one block above this one, so a
 * person meets the four statements and the control that acts on them in the
 * same place, rather than scrolling to the bottom of a list of every plan
 * this task ever had to find the four ticks for one of them.
 */
function RunCard({
  onStop,
  run,
  stopStatement,
  executionPending,
  stopPending,
}: {
  readonly onStop: (runId: string) => void;
  readonly run: AgentRunStatus;
  readonly stopStatement: string;
  readonly executionPending: boolean;
  readonly stopPending: boolean;
}) {
  const scopes = [...new Set(run.steps.map((item) => item.scope))];

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground">
          {`Calisma ${shortId(run.id)}`}
        </span>
        <span data-testid={`tasks-run-ending-${run.id}`}>
          <StatusPill label={deriveRunEnding(run).label} tone={deriveRunEnding(run).tone} />
        </span>
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
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-mono text-xs text-muted" data-testid="tasks-test-result-state">
            {`Test sonucu: ${run.test_result_state}`}
          </p>
          {/* The verdict is toned from a closed map, so `not_implemented` can
              never pick up an `ok` tone by omission. */}
          <StatusPill
            label={TEST_RESULT_LABEL[run.test_result_state]}
            tone={TEST_RESULT_TONE[run.test_result_state]}
          />
        </div>
        <p className="text-xs text-muted" data-testid="tasks-test-result-detail">
          {run.test_result_detail}
        </p>

        {/* The conditions the verdict was derived from. Listed rather than
            summarised: "which condition" and "how many" are different
            questions, and only the first one is actionable. */}
        <div className="flex flex-col gap-1" data-testid={`tasks-acceptance-${run.id}`}>
          <p className="text-xs font-medium text-foreground">
            {`Kabul kosullari (${String(run.acceptance.length)})`}
          </p>
          {run.acceptance.length === 0 ? (
            <p className="text-xs text-muted" data-testid={`tasks-acceptance-none-${run.id}`}>
              Bu plan makinenin karar verebilecegi bir kabul kosulu yazmadi.
              Basari olcutu yalnizca bir cumle olarak kaydedildi ve bu surumde
              hicbir cumle kosulmaz; bu yuzden sonuc &quot;uygulanmadi&quot;dir
              ve gorev yayimin esiginde kalir.
            </p>
          ) : (
            <>
              <ul className="flex flex-col gap-1">
                {run.acceptance.map((condition, index) => (
                  <li
                    className="flex flex-col gap-1 rounded-lg border border-border p-2"
                    key={`${run.id}-acc-${String(index)}`}
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-foreground">
                        {ACCEPTANCE_KIND_LABEL[condition.kind]}
                      </span>
                      <StatusPill
                        label={condition.satisfied ? "su anda saglaniyor" : "su anda saglanmiyor"}
                        tone={condition.satisfied ? "ok" : "problem"}
                      />
                    </span>
                    <span className="font-mono text-xs text-muted">{condition.label}</span>
                    <span className="text-xs text-muted">{condition.detail}</span>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted">
                Her kosul her okumada calisma alani uzerinde yeniden karara
                baglanir; saklanmis bir sonuc gosterilmez. Dun saglanan bir
                kosul bugun saglanmiyorsa burada ikincisi yazar.
              </p>
            </>
          )}
        </div>
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

      {/* The one control that belongs to a single run rather than to the
          task: a stop names *which* run to stop, and only a run in flight can
          be stopped. Consent, starting and resuming are one press each, in
          the block above; this card no longer offers a second way in. */}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          isDisabled={stopPending || (!executionPending && run.phase !== "running")}
          onPress={() => onStop(run.id)}
          variant="secondary"
        >
          {stopPending ? "Durduruluyor..." : "Durdur"}
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

/**
 * The two controls a person actually needs, and the consent one of them
 * carries.
 *
 * This block exists because the screen it replaces was correct and unusable.
 * Getting one scanned task done took seven actions - "Onaya al", pick a
 * criterion, "Modelden plan oner", four checkboxes, "Onayli plani calistir" -
 * and the owner's report was that having work done was an ordeal. Every one
 * of those seven was defensible on its own; the sum of them was the defect.
 *
 * What is **not** relaxed, and each line below is the shape of it:
 *
 * * **the four statements are on screen, visible, above the control.** Not
 *   folded, not behind a disclosure, not a link. A person is shown the same
 *   four things they were shown before and consents to them before anything
 *   runs; what changed is that the consent is one deliberate act rather than
 *   five, which is a claim about clicks and not about what is agreed to;
 * * **the control the consent belongs to does not exist until a plan does.**
 *   `derivePrimaryAction` returns a `start` only when a run is recorded in
 *   the `planned` phase, so this is an absence rather than a disabled button
 *   - there is no run id to name, so there is nothing to press;
 * * **the consent names its plan.** A different plan is a different run and
 *   arrives unconsented; the record below says which plan the last consent
 *   was given to, so "this is not the plan you approved" is readable rather
 *   than merely true;
 * * **the price is beside the button that charges it.** One model turn, and
 *   a turn costs money at the provider. The ceiling sentence, the "model
 *   proposes, does not run" sentence and the rest of the standing claims are
 *   where they were - one heading away, deleted from nowhere.
 */
function PrimaryActionRegion({
  action,
  busy,
  consentedRunId,
  outcome,
  onDoTheWork,
  onConsentAndRun,
}: {
  readonly action: PrimaryAction;
  readonly busy: Busy;
  /** The plan the last consent on this screen was given to; "" when none. */
  readonly consentedRunId: string;
  /** A turn that produced no plan, so the press can report its own result. */
  readonly outcome: ModelProposalResponse | null;
  readonly onDoTheWork: () => void;
  readonly onConsentAndRun: (action: PrimaryAction) => void;
}) {
  const pending = busy === "doWork" || busy === "start" || busy === "resume";
  return (
    <section
      aria-label={PRIMARY_BLOCK_LABEL}
      className="flex flex-col gap-2 rounded-lg border border-border p-3"
      data-testid="tasks-primary-action"
    >
      <h4 className="text-xs font-semibold text-foreground">{PRIMARY_BLOCK_LABEL}</h4>

      {action.kind === "do" ? (
        <>
          <div>
            <Button isDisabled={busy !== null} onPress={onDoTheWork}>
              {busy === "doWork" ? "Yapiliyor..." : action.label}
            </Button>
          </div>
          <p className="text-xs text-muted" data-testid="tasks-primary-cost">
            Bu dugme iki isi birlikte yapar: gorevi onaya alir ve modelden bir
            plan ister. Bir model turu harcar ve o turun saglayicida bir para
            maliyeti vardir; harcanan tur geri alinmaz. Hicbir sey
            calistirilmaz - calistirmak, asagidaki dort cumleyi okuyup ikinci
            dugmeye basmaktir.
          </p>
          {/* A turn that recorded no plan is reported here, where the press
              was. The model block says the same thing at length; a person who
              pressed this button must not have to go looking for the result
              of their own press. */}
          {outcome !== null && outcome.run_id === "" && (
            <p className="text-xs text-muted" data-testid="tasks-primary-outcome">
              {`${PROPOSAL_OUTCOME_LABEL[outcome.outcome]}. ${outcome.detail} Ayrinti "Modelden plan onerisi" bolumundedir.`}
            </p>
          )}
        </>
      ) : (
        <>
          {/* The card already says "Bu plan bir cikti dosyasi soz vermedi",
              which is a fact about the promise; a plan may promise nothing and
              still write something. This is the stronger reading, taken from
              the step scopes, and it moved here with the consent it qualifies:
              a person meets it before giving the consent rather than after the
              run. */}
          {action.run.phase === "planned" &&
            action.run.expected_artifacts.length === 0 &&
            !writesAnything(action.run) && (
              <p
                className="text-xs text-muted"
                data-testid={`tasks-writes-nothing-${action.run.id}`}
              >
                Bu planin hicbir adimi yazma yetkisi tasimiyor: onaylanip
                calistirilsa da hicbir dosya olusturmaz.
              </p>
            )}

          <p className="text-xs text-muted">
            {`Bu plan icin dort onay. Asagidaki dugmeye bir kez basmak bu dort cumlenin hepsini birlikte onaylar ve calismayi ${
              action.kind === "resume" ? "surdurur" : "baslatir"
            }.`}
          </p>
          <ul className="flex flex-col gap-1" data-testid="tasks-consent-statements">
            {APPROVALS.map((approval) => (
              <li className="text-xs text-foreground" key={approval.key}>
                {`• ${approval.label}`}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted" data-testid={`tasks-scope-change-${action.run.id}`}>
            Onaylar bu plana aittir. Plan icindeki kucuk ve guvenli dosya
            islemleri icin her adimda yeniden onay istenmez; kapsam veya risk
            degisirse yeni bir plan kaydedilir ve yeni plan yeniden onay ister.
          </p>
          <p className="font-mono text-xs text-muted" data-testid="tasks-consent-record">
            {consentedRunId === ""
              ? `Bu ekranda henuz hicbir plana onay verilmedi. Ekrandaki plan: ${shortId(action.run.id)}.`
              : consentedRunId === action.run.id
                ? `Onay bu plana verildi: ${shortId(action.run.id)}.`
                : `Onay baska bir plana verilmisti (${shortId(
                    consentedRunId,
                  )}). Ekrandaki plan ${shortId(action.run.id)} ve kendi onayini ister.`}
          </p>
          <div>
            <Button isDisabled={busy !== null} onPress={() => onConsentAndRun(action)}>
              {pending
                ? action.kind === "resume"
                  ? "Surduruluyor..."
                  : "Calistiriliyor..."
                : action.label}
            </Button>
          </div>
        </>
      )}
    </section>
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
  const [executionRunId, setExecutionRunId] = useState<string | null>(null);
  const [stoppingRunId, setStoppingRunId] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [step, setStep] = useState<Step>("read");


  // The machine-checkable half of a plan. Optional by construction: leaving
  // it empty records a plan whose verdict is `not_implemented`, which is the
  // honest outcome for a plan nobody wrote a condition for.
  const [checkKind, setCheckKind] = useState<AgentAcceptanceKindName | "">("");
  const [checkArgs, setCheckArgs] = useState<Readonly<Record<string, string>>>({});
  const [checkDraft, setCheckDraft] = useState<readonly DraftCondition[]>([]);

  // --- Paket H4 / ADR-0012: the model planning lane ----------------------
  //
  // `lane` is the stored connection state - which model is selected, and
  // whether the tool-call shape was measured for its protocol family. It is
  // read behind a button like everything else here, and reading it contacts
  // nobody: the route reports local state and a cached catalog.
  const [lane, setLane] = useState<OpenCodeStatus | null>(null);
  const [instruction, setInstruction] = useState("");
  const [proposal, setProposal] = useState<ModelProposalResponse | null>(null);

  // --- Paket H4: what the publication gate answered ----------------------
  const [gateRefusal, setGateRefusal] = useState("");
  const [gateMoved, setGateMoved] = useState(false);

  // The consent is keyed to a run id, exactly as the four checkboxes were. A
  // re-plan produces a *different* run, so it arrives unconsented by
  // construction rather than by a reset somebody has to remember to write -
  // and the press always consents to the plan currently on screen, never to
  // the one this field happens to hold.
  const [consentedRunId, setConsentedRunId] = useState("");

  // --- Paket H3: the two fields a person fills --------------------------
  //
  // Neither of these is read on task open. The bundle is read because
  // somebody pressed "read the bundle", and the archive is listed because
  // somebody pressed "list the archived sends" - so an acceptance is always
  // given against material that was actually put on screen first, and a
  // failure in either read is scoped to the region that asked for it rather
  // than taking the whole task detail down with it.
  const [proof, setProof] = useState<ProofWorkspace | null>(null);
  const [acceptRead, setAcceptRead] = useState(false);
  const [acceptNote, setAcceptNote] = useState("");
  /** The task state as it stood *before* an acceptance, so the surface can
   *  show that recording the field moved nothing (ADR-0009 8, SI-222). */
  const [stateBeforeAccept, setStateBeforeAccept] = useState<TaskStateName | null>(null);

  const [archive, setArchive] = useState<EvidenceList | null>(null);
  const [markEvidenceId, setMarkEvidenceId] = useState("");
  const [markNote, setMarkNote] = useState("");

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
    // A different task is a different workspace; a criterion chosen for the
    // old one would otherwise ride along to the new one.
    setCheckKind("");
    setCheckArgs({});
    setCheckDraft([]);
    setConsentedRunId("");
    // A different task is a different planning session and a different gate.
    setProposal(null);
    setInstruction("");
    setGateRefusal("");
    setGateMoved(false);
    // A different task is a different bundle and a different acceptance.
    setProof(null);
    setAcceptRead(false);
    setAcceptNote("");
    setStateBeforeAccept(null);
    setArchive(null);
    setMarkEvidenceId("");
    setMarkNote("");
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


  async function act(
    runId: string,
    action: "start" | "stop" | "resume",
  ): Promise<void> {
    if (selected === "") return;
    if (action === "stop") {
      if (stoppingRunId !== null) return;
      setStoppingRunId(runId);
      try {
        const stopped = await stopTaskRun(selected, runId);
        // An older stop acknowledgement cannot replace a completed response.
        setDetail((current) => current?.runs.some((run) => run.id === runId &&
          !["planned", "running"].includes(run.phase)) ? current : stopped);
      } catch (caught) {
        setError(toApiError(caught));
        setStep("stop");
      } finally {
        setStoppingRunId(null);
      }
      return;
    }
    if (busy !== null) return;
    setBusy(action);
    setExecutionRunId(runId);
    setError(null);
    try {
      const call =
        action === "start" ? startTaskRun : resumeTaskRun;
      setDetail(await call(selected, runId));
      setList(await fetchTasks());
      // The interrupted-run list is part of the surface, and a run that just
      // finished is no longer one; re-reading keeps the two consistent.
      setSurface(await fetchAgentSurface());
    } catch (caught) {
      setError(toApiError(caught));
      setStep(action);
    } finally {
      setExecutionRunId(null);
      setBusy(null);
    }
  }

  // --- Paket H4 / ADR-0012: the model planning lane -----------------------

  /**
   * Read which model is selected and what was measured about its protocol.
   *
   * Behind a button and never on mount, like every other read on this
   * surface. It contacts nobody: the route reports the stored selection, the
   * cached catalog and the protocol context. It is *offered* before a turn
   * rather than required, because a person about to spend a metered call is
   * entitled to see which model would answer it - the response of a turn does
   * not carry a model id, and this screen will not guess one.
   */
  async function readModelLane(): Promise<void> {
    if (busy !== null) return;
    setBusy("modelLane");
    setError(null);
    try {
      setLane(await fetchOpenCodeStatus());
    } catch (caught) {
      setLane(null);
      setError(toApiError(caught));
      setStep("modelLane");
    } finally {
      setBusy(null);
    }
  }

  /**
   * Spend one model turn. **Starts nothing.**
   *
   * The response carries the task and its runs after the turn, so the detail
   * is updated from that single document rather than re-read. The workspace
   * listing is carried over untouched, and that is correct rather than
   * convenient: a proposal writes no file, because a proposal runs no step.
   *
   * Every ending is a result, not an error - a provider failure, a proposal
   * naming an unregistered tool and a session at its ceiling all come back
   * `200` with an outcome that says which. They are rendered in the region
   * rather than thrown at the error surface, because flattening them into
   * "something went wrong" would lose the one thing they carry.
   */
  async function proposeFromModel(): Promise<void> {
    if (busy !== null || selected === "") return;
    setBusy("modelTurn");
    setError(null);
    try {
      const next = await proposeModelPlan({
        taskId: selected,
        instruction,
        acceptance: checkDraft.map((item) => ({ kind: item.kind, arguments: item.args })),
      });
      setProposal(next);
      setDetail((current) =>
        current === null ? current : { ...current, task: next.task, runs: [...next.runs] },
      );
      setList(await fetchTasks());
    } catch (caught) {
      setError(toApiError(caught));
      setStep("modelTurn");
    } finally {
      setBusy(null);
    }
  }

  /**
   * Drop this task's planning session so the next turn starts from nothing.
   *
   * Not a reset of the ceiling and not an undo: the recorded plans, the
   * workspace and the task's evidence are untouched, and the turn counter
   * comes back from the server in the same response.
   */
  async function forgetModelSession(): Promise<void> {
    if (busy !== null || selected === "") return;
    setBusy("modelForget");
    setError(null);
    try {
      const next = await forgetModelPlanSession(selected);
      setProposal(next);
      setInstruction("");
      setDetail((current) =>
        current === null ? current : { ...current, task: next.task, runs: [...next.runs] },
      );
    } catch (caught) {
      setError(toApiError(caught));
      setStep("modelForget");
    } finally {
      setBusy(null);
    }
  }

  // --- Paket H4: asking the gate to look again ----------------------------

  /**
   * Ask Station to re-derive whether this task is ready to publish.
   *
   * **This is not a transition control and it cannot be turned into one.**
   * The request carries no target: what is asked for is a re-reading of three
   * fields, and the gate decides. A refusal is kept in its own state and
   * rendered beside the button with the fields it named, because "which
   * evidence is missing" is the entire content of the answer and the shared
   * error region is not where a reader would look for it.
   */
  async function evaluatePublishReadiness(): Promise<void> {
    if (busy !== null || selected === "") return;
    setBusy("readiness");
    setError(null);
    setGateRefusal("");
    setGateMoved(false);
    try {
      const moved = await deriveTaskPublishReadiness({ taskId: selected });
      setDetail((current) => (current === null ? current : { ...current, task: moved }));
      setList(await fetchTasks());
      setGateMoved(true);
    } catch (caught) {
      const failure = toApiError(caught);
      // The gate's own sentence names the unverified fields. It is shown
      // here as well as in the error region: a refusal a reader has to go
      // looking for is a refusal that gets read as a bug.
      setGateRefusal(failure.userMessage);
      setError(failure);
      setStep("readiness");
    } finally {
      setBusy(null);
    }
  }

  // --- Paket H3 -----------------------------------------------------------

  /**
   * Read the bundle this task's acceptance would be given against.
   *
   * A read. It writes nothing, sends nothing and moves nothing; the reason it
   * is behind a button rather than on task open is that acceptance is only
   * honest when the material was actually put on screen first.
   */
  async function readProof(): Promise<void> {
    if (busy !== null || selected === "") return;
    setBusy("proof");
    setError(null);
    // A re-read may return a different bundle, and a tick given against the
    // previous one is a tick for something else.
    setAcceptRead(false);
    try {
      setProof(await fetchProof(selected));
    } catch (caught) {
      setProof(null);
      setError(toApiError(caught));
      setStep("proof");
    } finally {
      setBusy(null);
    }
  }

  /**
   * Record that a person accepted this exact bundle. Moves no state.
   *
   * The digest goes up with the request and is compared server-side: an
   * acceptance recorded against a bundle that has since changed is an
   * acceptance of something else and comes back refused. `stateBeforeAccept`
   * is captured here so the surface can show afterwards that the task is
   * where it was - acceptance is the input to a publication decision, never
   * its output (ADR-0009 8, SI-222).
   */
  async function accept(): Promise<void> {
    if (busy !== null || selected === "" || proof === null || !acceptRead) return;
    setBusy("accept");
    setError(null);
    setStateBeforeAccept(proof.task.state);
    try {
      const next = await recordProofAcceptance({
        taskId: selected,
        bundleSha256: proof.bundle_sha256,
        detail: acceptNote,
      });
      setProof(next);
      setDetail(await fetchTaskRuns(selected));
      setList(await fetchTasks());
      setAcceptRead(false);
      setAcceptNote("");
    } catch (caught) {
      setStateBeforeAccept(null);
      setError(toApiError(caught));
      setStep("accept");
    } finally {
      setBusy(null);
    }
  }

  /** List the archived sends. A read of a local table; contacts nobody. */
  async function listArchive(): Promise<void> {
    if (busy !== null) return;
    setBusy("proof");
    setError(null);
    try {
      setArchive(await fetchEvidenceRecords());
    } catch (caught) {
      setError(toApiError(caught));
      setStep("proof");
    } finally {
      setBusy(null);
    }
  }

  /**
   * Attach an archived send to this task. Causes no send.
   *
   * The request carries an evidence record's identity and nothing else - no
   * room, no address, no text - so there is no shape here that could reach an
   * outbound client. Whether the reference counts as verified is read
   * server-side from that record's own write outcome (ADR-0009 1, 11).
   */
  async function markPublicShare(): Promise<void> {
    if (busy !== null || selected === "" || markEvidenceId === "") return;
    setBusy("mark");
    setError(null);
    try {
      const next = await recordProofPublicShare({
        taskId: selected,
        evidenceId: markEvidenceId,
        detail: markNote,
      });
      setProof(next);
      setDetail(await fetchTaskRuns(selected));
      setList(await fetchTasks());
      setMarkEvidenceId("");
      setMarkNote("");
    } catch (caught) {
      setError(toApiError(caught));
      setStep("mark");
    } finally {
      setBusy(null);
    }
  }

  // --- the two presses ----------------------------------------------------

  /**
   * Press one: take the task on and ask the model for a plan. **Runs nothing.**
   *
   * Two existing client calls in order, and no new route, because none is
   * needed: the transition the person used to make by hand, then the turn
   * they used to spend by hand. What it does not do is start anything - the
   * best a turn can end in is a recorded plan in `planned`, and carrying that
   * out is the second press.
   *
   * `check_promised_files` is what makes the result of this press worth
   * having. Without it a model-proposed plan reports `not_implemented`
   * forever unless somebody hand-writes a condition, because the criterion a
   * proposer writes for itself is not a criterion. With it the product reads
   * the promise off the write calls the model proposed and judges the plan by
   * whether those files exist - the person asks *what* is checked, the
   * product derives *which* files, and the model is still never asked for a
   * criterion. `acceptance` goes up empty beside it on purpose: an explicit
   * choice is never added to, so sending both would be a contradiction. The
   * long road - choose conditions by hand, then "Modelden plan oner" - is
   * still there, one heading down, and still sends what was chosen.
   *
   * The two halves are reported apart. If the move lands and the turn does
   * not, the failure says the task moved: a person who reads "nothing
   * happened" presses again, and pressing again may spend a turn the first
   * press already paid for.
   */
  async function doTheWork(): Promise<void> {
    const current = detail?.task ?? null;
    if (busy !== null || selected === "" || current === null) return;
    setBusy("doWork");
    setError(null);
    let moved = false;
    try {
      if (current.state === "suggested") {
        const movedTask = await transitionTask({
          taskId: selected,
          target: "awaiting_approval",
        });
        moved = true;
        // On screen before the turn is asked for, so a failure in the second
        // half can never leave the first half invisible.
        setDetail((current) => (current === null ? current : { ...current, task: movedTask }));
      }
      const next = await proposeModelPlan({
        taskId: selected,
        instruction,
        acceptance: [],
        checkPromisedFiles: true,
      });
      setProposal(next);
      setDetail((current) =>
        current === null ? current : { ...current, task: next.task, runs: [...next.runs] },
      );
      setList(await fetchTasks());
    } catch (caught) {
      setError(toApiError(caught));
      setStep(moved ? "doWorkAfterMove" : "doWork");
    } finally {
      setBusy(null);
    }
  }

  /**
   * Press two: give the four approvals in one deliberate act, and carry the
   * plan out.
   *
   * The plan is the one `derivePrimaryAction` read off the task's own runs a
   * moment ago and the one whose four statements are on screen above the
   * button. It is passed in rather than looked up again here, and it is never
   * taken from {@link consentedRunId}: reaching for the last id this screen
   * held would start a plan nobody looked at, which is precisely the
   * inheritance the run-keyed approvals existed to prevent.
   */
  function consentAndRun(chosen: PrimaryAction): void {
    if (busy !== null || chosen.kind === "do") return;
    setConsentedRunId(chosen.run.id);
    void act(chosen.run.id, chosen.kind === "resume" ? "resume" : "start");
  }

  function addCondition(): void {
    if (checkKind === "") return;
    setCheckDraft((current) => [...current, { kind: checkKind, args: checkArgs }]);
    setCheckArgs({});
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

  const chosenCheck =
    surface.acceptance_checks.find((check) => check.kind === checkKind) ?? null;
  const task = detail?.task ?? null;
  const runsNow = detail?.runs ?? [];

  /**
   * The two halves of this screen's information design, both derived here so
   * a reader can see the whole rule in one place rather than hunting it
   * through the JSX.
   */
  const nextStep = task === null ? null : deriveNextStep(task.state, runsNow);
  const primary = task === null ? null : derivePrimaryAction(task.state, runsNow);
  const opened = (id: BlockId): boolean => BLOCK_ACTS[id](task, runsNow);
  const whyClosed = (id: BlockId): string =>
    opened(id) ? "" : BLOCK_CLOSED_REASON[id](task);

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Card.Title>Gorevler</Card.Title>
          <StatusPill label="Yurutme kapali (execution_unavailable)" tone="inactive" />
        </div>
        {/*
          The first sentence on this screen, so it is the one most likely to
          outlive what it describes - and it did. It said there was no model
          call, three paragraphs above the block that correctly explains what
          the model may propose. ADR-0012 opened that lane; what stayed shut
          is arbitrary code and shell execution, which is what the pill beside
          this text reports and what this sentence now says instead.
        */}
        <Card.Description>
          Plan once yazilir, sonra ayri bir istekle calistirilir. Plani bir
          model onerebilir; onayi ve baslatmayi kullanici yapar. Araclar kapali
          bir registry&apos;den gelir ve deterministiktir; kabuk komutu ve
          keyfi kod yurutmesi yoktur.
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

        <ExecutionBlock
          open={opened("execution")}
          summary={whyClosed("execution")}
          surface={surface}
        />

        <Separator />

        <BudgetBlock open={opened("budget")} summary={whyClosed("budget")} surface={surface} />

        <Separator />

        <TrustBoundaryBlock
          open={opened("trust")}
          summary={whyClosed("trust")}
          tools={surface.tools}
        />

        <Separator />

        {/* --- runs a restart left behind ------------------------------- */}
        <DisclosureBlock
          label="Kesilen calismalar"
          level={3}
          open={opened("interrupted")}
          summary={blockSummary(
            `${String(
              surface.interrupted_runs.length,
            )} calisma yeniden baslatmanin ardinda kaldi; acilista otomatik devam yoktur.`,
            whyClosed("interrupted"),
          )}
          summaryTestId="tasks-interrupted-summary"
        >
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
        </DisclosureBlock>

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
              {/*
                The first thing on a task, and the row this whole package was
                opened for. It is derived from the task's own state and its
                own runs (`deriveNextStep`), never written per state into this
                JSX: a tenth state would render an empty line here, so the
                derivation is walked by a test that fails instead.
              */}
              {nextStep !== null && (
                <div
                  className="flex flex-col gap-1 rounded-lg border border-border p-2"
                  data-testid="tasks-next-step"
                >
                  <p className="text-sm font-medium text-foreground">
                    {`Sirada ne var: ${nextStep.action}`}
                  </p>
                  <p className="text-xs text-muted" data-testid="tasks-next-step-control">
                    {nextStep.control === ""
                      ? "Bu durumda basilacak bir kontrol yok; asagidaki bolumler yalnizca kaydi gosterir."
                      : `Bunu yapan kontrol: "${nextStep.control}" — "${nextStep.where}" bolumunde.`}
                  </p>
                </div>
              )}

              <p className="text-xs text-muted" data-testid="tasks-state-detail">
                {task.state_detail}
              </p>

              {/*
                The two controls, immediately under the line that names them
                and above every explanation on the screen. A state that has no
                such act - a finished task, a run in flight - renders nothing
                here rather than a disabled button pretending there is
                something to press.
              */}
              {primary !== null && (
                <PrimaryActionRegion
                  action={primary}
                  busy={busy}
                  consentedRunId={consentedRunId}
                  onConsentAndRun={consentAndRun}
                  onDoTheWork={() => void doTheWork()}
                  outcome={proposal}
                />
              )}

              {/*
                Moved above the evidence blocks in this package, because this
                is where the next action lives for four of the nine states and
                it used to sit under every explanation on the screen. Nothing
                about the five transitions changed - only when a person meets
                them.
              */}
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

              <EvidenceFields
                open={opened("fields")}
                summary={whyClosed("fields")}
                task={task}
              />

              <PublishReadinessRegion
                busy={busy}
                moved={gateMoved}
                onEvaluate={() => void evaluatePublishReadiness()}
                open={opened("readiness")}
                refusal={gateRefusal}
                summary={whyClosed("readiness")}
                task={task}
              />

              <AcceptanceRegion
                busy={busy}
                note={acceptNote}
                onAccept={() => void accept()}
                onNote={setAcceptNote}
                onRead={() => void readProof()}
                onTick={setAcceptRead}
                open={opened("acceptance")}
                proof={proof}
                stateBefore={stateBeforeAccept}
                summary={whyClosed("acceptance")}
                task={task}
                ticked={acceptRead}
              />

              <PublicShareRegion
                archive={archive}
                busy={busy}
                chosen={markEvidenceId}
                name={`${ids}-archived-send`}
                note={markNote}
                onChoose={setMarkEvidenceId}
                onList={() => void listArchive()}
                onMark={() => void markPublicShare()}
                onNote={setMarkNote}
                open={opened("share")}
                summary={whyClosed("share")}
                task={task}
              />

              <p className="text-xs text-muted" data-testid="tasks-run-honesty">
                {detail.honesty}
              </p>
            </section>

            <Separator />

            {/* --- the success criterion, chosen before the turn ----- */}
            <DisclosureBlock
              label="Basari olcutu"
              level={3}
              open={opened("composer")}
              summary={blockSummary(
                "Kosul yazmazsaniz sonuc 'uygulanmadi' kalir ve gorev yayima hazir sayilmaz.",
                whyClosed("composer"),
              )}
              summaryTestId="tasks-composer-summary"
            >
              <fieldset className="flex flex-col gap-2" data-testid="tasks-acceptance-composer">
                <legend className="text-xs font-semibold text-foreground">
                  Kabul kosullari (istege bagli, ama yazilmazsa sonuc &quot;uygulanmadi&quot; olur)
                </legend>
                <p className="text-xs text-muted">
                  Yukaridaki olcut bir cumledir ve hicbir cumle kosulmaz. Test
                  sonucunun &quot;gecti&quot; veya &quot;kaldi&quot; olabilmesi
                  icin planin, kapali kayittan secilmis, makinenin karar
                  verebilecegi kosullar da yazmasi gerekir. Kosullar her
                  okumada calisma alani uzerinde yeniden karara baglanir.
                </p>

                {surface.acceptance_checks.map((check) => (
                  <label className="flex items-start gap-2" key={check.kind}>
                    <input
                      checked={checkKind === check.kind}
                      disabled={busy !== null}
                      name={`${ids}-acceptance`}
                      onChange={() => {
                        setCheckKind(check.kind);
                        setCheckArgs({});
                      }}
                      type="radio"
                      value={check.kind}
                    />
                    <span className="text-xs text-muted">
                      <span className="font-mono text-foreground">{check.kind}</span>
                      {` — ${ACCEPTANCE_KIND_LABEL[check.kind]}`}
                      <br />
                      {check.purpose}
                    </span>
                  </label>
                ))}

                {chosenCheck !== null &&
                  chosenCheck.params.map((param) => (
                    <TextField
                      className="w-full"
                      key={`${chosenCheck.kind}-${param.name}`}
                      onChange={(next: string) =>
                        setCheckArgs((current) => ({ ...current, [param.name]: next }))
                      }
                      value={checkArgs[param.name] ?? ""}
                    >
                      <Label>
                        {`${param.name} (${param.type}${
                          param.required ? ", zorunlu" : ", istege bagli"
                        }) — ${param.detail}`}
                      </Label>
                      <Input autoComplete="off" variant="secondary" />
                    </TextField>
                  ))}

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    isDisabled={busy !== null || checkKind === ""}
                    onPress={addCondition}
                    size="sm"
                    variant="secondary"
                  >
                    Kosulu plana ekle
                  </Button>
                  <span className="text-xs text-muted" data-testid="tasks-acceptance-draft-count">
                    {`Plandaki kabul kosulu sayisi: ${String(checkDraft.length)}`}
                  </span>
                </div>

                {checkDraft.length > 0 && (
                  <ul className="flex flex-col gap-1" data-testid="tasks-acceptance-draft">
                    {checkDraft.map((item, index) => (
                      <li
                        className="font-mono text-xs text-muted"
                        key={`${item.kind}-${String(index)}`}
                      >
                        {`${String(index + 1)}. ${item.kind} · argumanlar: ${
                          Object.keys(item.args).length === 0
                            ? "(yok)"
                            : Object.keys(item.args).join(", ")
                        }`}
                      </li>
                    ))}
                  </ul>
                )}
              </fieldset>
            </DisclosureBlock>

            <Separator />

            <ModelPlanRegion
              busy={busy}
              instruction={instruction}
              lane={lane}
              onForget={() => void forgetModelSession()}
              onInstruction={setInstruction}
              onPropose={() => void proposeFromModel()}
              onReadLane={() => void readModelLane()}
              open={opened("model")}
              proposal={proposal}
              summary={whyClosed("model")}
            />


            <Separator />

            {/* --- the runs ------------------------------------------- */}
            <DisclosureBlock
              label="Calismalar"
              level={3}
              // Forced open while this screen is carrying a run out: "Durdur"
              // lives in here, and a block that folds away exactly while the
              // one control that can interrupt a run is needed would be a
              // disclosure that took something away.
              open={opened("runs") || executionRunId !== null}
              summary={blockSummary(
                `${String(
                  detail.runs.length,
                )} kaydedilmis calisma; her birinin plani, adimlari, harcamasi ve sonu burada. Calisan bir isi durdurmak da burada.`,
                whyClosed("runs"),
              )}
              summaryTestId="tasks-runs-summary"
            >
              {detail.runs.length === 0 ? (
                <p className="text-sm text-muted">
                  Bu gorev icin kaydedilmis plan yok. Bos bir liste, yapilacak
                  is olmadigini degil, henuz plan yazilmadigini gosterir.
                </p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {detail.runs.map((run) => (
                    <RunCard
                      key={run.id}
                      executionPending={executionRunId === run.id}
                      stopPending={stoppingRunId === run.id}
                      onStop={(runId) => void act(runId, "stop")}
                      run={run}
                      stopStatement={surface.stop_statement}
                    />
                  ))}
                </ul>
              )}
            </DisclosureBlock>

            <Separator />

            {/* --- the workspace -------------------------------------- */}
            <DisclosureBlock
              label="Calisma alani"
              level={3}
              open={opened("workspace")}
              summary={blockSummary(
                `${String(
                  detail.workspace_files.length,
                )} dosya, adi ve ozetiyle listelenir; hicbir yol gosterilmez.`,
                whyClosed("workspace"),
              )}
              summaryTestId="tasks-workspace-summary"
            >
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
            </DisclosureBlock>
          </>
        )}
      </Card.Content>
    </Card>
  );
}

// --- Paket H4: asking the gate to look again -------------------------------

/**
 * The publication gate, and the difference between reaching a state and
 * asking for one.
 *
 * There is now a route that can move a task into `ready_to_publish`, and
 * SI-222 is untouched by it. The request body has **no target field**, the
 * state is still absent from the user transition list, and what a person asks
 * for is a re-reading of three fields that three different acts filled: what
 * the runner produced, what the plan's own acceptance conditions decided over
 * those bytes, and a person's acceptance.
 *
 * Three rules shape this region:
 *
 * * **the control is never worded as publication.** It says "evaluate", not
 *   "publish" and not "mark ready". A button that promised the state would be
 *   promising something the caller does not control;
 * * **a refusal names the evidence.** The gate answers with the unverified
 *   fields, and they are shown here, beside the button, together with the
 *   task's own `blocking_fields` - which are readable before anything is
 *   pressed, so a person can see why an attempt would fail without making
 *   one;
 * * **nothing here publishes.** Reaching `ready_to_publish` is not a send.
 *   Sharing goes through the composer's three-step chain, and no route on
 *   this surface can reach an outbound client.
 */
function PublishReadinessRegion({
  task,
  refusal,
  moved,
  busy,
  open,
  summary,
  onEvaluate,
}: {
  readonly task: TaskStatusResponse;
  readonly refusal: string;
  readonly moved: boolean;
  readonly busy: Busy;
  readonly open: boolean;
  readonly summary: string;
  readonly onEvaluate: () => void;
}) {
  return (
    <DisclosureBlock
      label="Yayin hazirligi"
      level={4}
      open={open}
      summary={blockSummary(
        task.ready_to_publish
          ? "Uc alan ayri ayri dogrulandi."
          : "Kanit tamam degil; bu islem bir durum istemez, uc alani yeniden okutur.",
        summary,
      )}
      summaryTestId="tasks-readiness-summary"
    >
      <div>
        <StatusPill
          label={task.ready_to_publish ? "uc alan dogrulandi" : "kanit tamam degil"}
          tone={task.ready_to_publish ? "ok" : "inactive"}
        />
      </div>

      <p className="text-xs text-muted" data-testid="tasks-readiness-rule">
        Bu islem bir durum istemez. Istek bir hedef alani tasimaz; yalnizca uc
        kanit alaninin yeniden okunmasini ister ve karari kapi verir. Ayni
        istegi kac kez yaparsaniz yapin cevap degismez: cevap kanitin bir
        fonksiyonudur. Bu islem hicbir sey yayimlamaz ve hicbir sey gondermez.
      </p>

      <p className="font-mono text-xs text-muted" data-testid="tasks-readiness-blocking">
        {task.blocking_fields.length === 0
          ? "Dogrulanmamis alan yok."
          : `Dogrulanmamis alanlar: ${task.blocking_fields.join(", ")}`}
      </p>

      <div>
        <Button isDisabled={busy !== null} onPress={onEvaluate} size="sm" variant="secondary">
          {busy === "readiness"
            ? "Degerlendiriliyor..."
            : "Yayin hazirligini degerlendir (durumu istemez)"}
        </Button>
      </div>

      {refusal !== "" && (
        <p className="text-xs text-muted" data-testid="tasks-readiness-refusal">
          {refusal}
        </p>
      )}

      {moved && (
        <p className="text-xs text-muted" data-testid="tasks-readiness-moved">
          {`Kapi uc alani da dogrulanmis buldu ve durum kanittan turetildi: gorev simdi '${
            STATE_LABEL[task.state]
          }'. Bu bir yayim degildir; dis paylasim ayri bir islemdir.`}
        </p>
      )}
    </DisclosureBlock>
  );
}

// --- Paket H4 / ADR-0012: the model proposes, and only proposes ------------

/**
 * The model planning lane.
 *
 * The lane this screen said did not exist. It exists now, and every sentence
 * in this region is here because the comfortable version of it would be a
 * lie:
 *
 * * **a turn cannot start anything.** The best outcome is a recorded plan in
 *   `planned`, which then meets the same four approvals a hand-written plan
 *   meets. `model_can_start_a_run` is `false` on the wire as a *type*, and it
 *   is rendered rather than assumed;
 * * **a model cannot widen its own scope.** A proposed name that is not in
 *   the compile-time registry refuses the whole turn, and the refusal is
 *   rendered as an outcome on screen rather than swallowed. Nothing is
 *   trimmed to the calls that happened to resolve: a plan made of the
 *   survivors is not the plan anybody wrote;
 * * **`usage` and `cost` are the provider's statement.** They are shown
 *   verbatim, labelled as the provider's own numbers, and they are never used
 *   as a ceiling - the ceiling is the model-call count, which this station
 *   can count for itself (ADR-0008 4, SI-250);
 * * **the model's reasoning is not here.** It is not hidden, filtered or
 *   collapsed: it is read from the response, used for nothing, stored
 *   nowhere and displayed nowhere (ADR-0012 1);
 * * **which model answered is read, not guessed.** A turn's response carries
 *   no model id, so the region offers the stored selection instead and says
 *   that is what it is.
 */
function ModelPlanRegion({
  lane,
  proposal,
  instruction,
  busy,
  open,
  summary,
  onReadLane,
  onPropose,
  onForget,
  onInstruction,
}: {
  readonly lane: OpenCodeStatus | null;
  readonly proposal: ModelProposalResponse | null;
  readonly instruction: string;
  readonly busy: Busy;
  readonly open: boolean;
  readonly summary: string;
  readonly onReadLane: () => void;
  readonly onPropose: () => void;
  readonly onForget: () => void;
  readonly onInstruction: (next: string) => void;
}) {
  return (
    <DisclosureBlock
      label="Modelden plan onerisi"
      level={3}
      open={open}
      summary={blockSummary(
        "Model plan ONERIR, calistirmaz: bir tur en iyi ihtimalle kaydedilmis bir plan uretir ve o plan da ayni dort onaydan gecer.",
        summary,
      )}
      summaryTestId="tasks-model-summary"
    >
      <div>
        <StatusPill label="Model onerir, calistirmaz" tone="inactive" />
      </div>

      <Alert status="warning">
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>Oneri onayi atlatmaz</Alert.Title>
          <Alert.Description>
            <span className="flex flex-col gap-2">
              <span data-testid="tasks-model-approval-rule">
                Modelin onerdigi bir plan, elle yazilmis bir planla ayni yoldan
                gecer: ayni dort onay istenir ve calistirma ayri bir kullanici
                islemidir. Model kendi planina onay veremez ve bir calismayi
                baslatamaz. Modelin onermis olmasi hicbir adimi atlatmaz.
              </span>
              <span data-testid="tasks-model-registry-rule">
                Model yalnizca derleme zamaninda yazilmis arac listesinden
                secebilir. Listede olmayan bir ad onerirse oneri butunuyle
                reddedilir - cozulen adimlarla kirpilmis bir plan kaydedilmez,
                cunku o plani kimse yazmamistir. Araclara yol veya adres
                verilemez: boyle bir parametre tipi yoktur.
              </span>
            </span>
          </Alert.Description>
        </Alert.Content>
      </Alert>

      {/* --- which model, and what was measured about it ---------------- */}
      <div className="flex flex-col gap-2">
        <div>
          <Button isDisabled={busy !== null} onPress={onReadLane} size="sm" variant="secondary">
            {busy === "modelLane" ? "Okunuyor..." : "Hangi model secili, oku"}
          </Button>
        </div>

        {lane === null ? (
          <p className="text-xs text-muted" data-testid="tasks-model-lane-unread">
            Model baglantisinin durumu okunmadi. Bir tur harcamadan once hangi
            modelin cevap verecegini gormek icin okuyabilirsiniz; turun kendi
            yaniti bir model kimligi tasimaz ve bu ekran bir model adi
            uydurmaz.
          </p>
        ) : (
          <div className="flex flex-col gap-1" data-testid="tasks-model-selection">
            <p className="font-mono text-xs text-muted">
              {`Secili model: ${
                lane.selected_model === "" ? "(secilmedi)" : lane.selected_model
              } · kimlik bilgisi kayitli: ${
                lane.configured ? "evet" : "hayir"
              } · baglanti durumu: ${lane.check.state}`}
            </p>
            <p className="text-xs text-muted" data-testid="tasks-model-tool-calls">
              {lane.protocol_context.tool_calls_supported
                ? "Arac cagrisi bicimi bu protokol ailesi icin olculmustur."
                : "Arac cagrisi bicimi bu yapida olculmus degildir; olculmemis bir sozlesme uydurulmaz."}
            </p>
            {/* Empty until something is measured. Rendered verbatim: a
                supported format with no provenance beside it would be exactly
                the unsourced claim this product refuses. */}
            {lane.protocol_context.tool_call_provenance !== "" && (
              <p className="text-xs text-muted" data-testid="tasks-model-provenance">
                {lane.protocol_context.tool_call_provenance}
              </p>
            )}
            <p className="text-xs text-muted">{lane.protocol_context.deferral}</p>
          </div>
        )}
      </div>

      {/* --- spending one turn ------------------------------------------ */}
      <TextField className="w-full" onChange={onInstruction} value={instruction}>
        <Label>Modele iletilecek yonerge (istege bagli, saklanmaz)</Label>
        <TextArea rows={3} variant="secondary" />
      </TextField>

      <div className="flex flex-wrap items-center gap-2">
        <Button isDisabled={busy !== null} onPress={onPropose} size="sm">
          {busy === "modelTurn" ? "Tur harcaniyor..." : "Modelden plan oner (calistirmaz)"}
        </Button>
        <Button isDisabled={busy !== null} onPress={onForget} size="sm" variant="secondary">
          {busy === "modelForget" ? "Unutuluyor..." : "Oturumu unut ve bastan basla"}
        </Button>
      </div>

      {/* The last sentence used to be a claim this build did not keep:
          `forget` dropped the session object the counter lived on, so the
          ceiling really did reset. ADR-0013 moved the counter to a per-task
          row; the sentence is now true and says the whole of it, including
          the relaunch, because "a ceiling a restart clears" and "a ceiling a
          restart does not clear" are different promises. */}
      <p className="text-xs text-muted" data-testid="tasks-model-turn-rule">
        Bir istek bir tur harcar; arka plan gorevi ve otomatik ikinci tur yoktur. Oturumu unutmak konusmayi duser, tavan sifirlanmaz — yeniden baslatmak da geri vermez.
      </p>

      {proposal === null ? (
        <p className="text-xs text-muted" data-testid="tasks-model-no-turn">
          Bu gorev icin bu ekranda henuz bir model turu harcanmadi.
        </p>
      ) : (
        <div className="flex flex-col gap-2" data-testid="tasks-model-outcome">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted">{`Sonuc: ${proposal.outcome}`}</span>
            <StatusPill
              label={PROPOSAL_OUTCOME_LABEL[proposal.outcome]}
              tone={PROPOSAL_OUTCOME_TONE[proposal.outcome]}
            />
          </div>

          {/* The refusal path lands here, on screen, with the reason the
              backend gave. It is a 200 with an outcome, not an exception. */}
          <p className="text-xs text-muted" data-testid="tasks-model-detail">
            {proposal.detail}
          </p>

          {/* Rendered only for the two outcomes that are not endings, and
              rendered *under* the provider's own sentence rather than instead
              of it. */}
          {PROPOSAL_OUTCOME_NOTE[proposal.outcome] !== undefined && (
            <p className="text-xs text-muted" data-testid="tasks-model-outcome-note">
              {PROPOSAL_OUTCOME_NOTE[proposal.outcome]}
            </p>
          )}

          <p className="font-mono text-xs text-muted" data-testid="tasks-model-calls">
            {`Harcanan model turu: ${String(proposal.model_calls_used)} / ${String(
              proposal.max_model_calls,
            )} · onerilen plan: ${
              proposal.run_id === "" ? "(kaydedilmedi)" : shortId(proposal.run_id)
            }`}
          </p>

          {/* Labelled as the provider's statement, every time it is shown. */}
          <p className="font-mono text-xs text-muted" data-testid="tasks-model-usage">
            {`Saglayicinin beyani: ${
              proposal.usage_detail === "" ? "(bildirilmedi)" : proposal.usage_detail
            }`}
          </p>
          <p className="text-xs text-muted" data-testid="tasks-model-usage-rule">
        Bu degerler saglayicinin bildirimidir: bizim olcumumuz degildir ve tavan olarak kullanilmaz.
      </p>

          {proposal.tool_call_provenance !== "" && (
            <p className="text-xs text-muted" data-testid="tasks-model-turn-provenance">
              {proposal.tool_call_provenance}
            </p>
          )}

          {proposal.closing_text !== "" && (
            <>
              <p className="text-xs font-medium text-foreground">
                Modelin kapanis sozu (bir sonuc iddiasi degildir)
              </p>
              {/* Imported text, rendered inert and unlinked like every other
                  imported string in this app. Shown once and stored nowhere. */}
              <pre
                className="whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-2 font-mono text-xs text-foreground"
                data-testid="tasks-model-closing"
              >
                {proposal.closing_text}
              </pre>
            </>
          )}

          <p className="text-xs text-muted" data-testid="tasks-model-cannot-start">
            {proposal.model_can_start_a_run
              ? "Model bir calismayi baslatabilir."
              : "Model bir calismayi baslatamaz. Onerilen plan asagida 'Calismalar' altinda, dort onayi bekleyerek durur; baslatmak sizin isleminizdir."}
          </p>

          <p className="text-xs text-muted" data-testid="tasks-model-no-reasoning">
            Modelin muhakemesi bu ekranda yoktur. Gizlenmis degildir:
            saglayicinin yanitindaki muhakeme alani okunur, kullanilmaz,
            saklanmaz, loglanmaz ve gosterilmez.
          </p>
        </div>
      )}
    </DisclosureBlock>
  );
}

// --- Paket H3: the two fields a person fills -------------------------------

/** The five archived write outcomes, in the user's language. */
const SHARE_OUTCOME_LABEL: Record<EvidenceWriteOutcome, string> = {
  in_flight: "Gonderim suruyor",
  accepted: "Kabul edildi",
  refused: "Reddedildi",
  outcome_unknown: "Sonuc bilinmiyor",
  not_sent: "Gonderim yapilmadi",
};

/**
 * Accepting one exact bundle, and the two things acceptance is not.
 *
 * It is **not a transition**. The route writes `user_acceptance` and stops;
 * the task stays where it was, and this region shows the state before and
 * after so that is visible rather than merely true. Making acceptance move the
 * task would give `ready_to_publish` a producer that is not "three separately
 * verified pieces of evidence" (ADR-0009 8, SI-222).
 *
 * It is **not a verdict about the work**. The bundle is read first, its named
 * gaps are on screen while the tick is given, and the backend's sentence about
 * what a digest establishes sits beside them. A person accepting a bundle with
 * four open gaps is accepting a bundle with four open gaps.
 */
function AcceptanceRegion({
  task,
  proof,
  ticked,
  note,
  busy,
  open,
  summary,
  stateBefore,
  onRead,
  onTick,
  onNote,
  onAccept,
}: {
  readonly task: TaskStatusResponse;
  readonly proof: ProofWorkspace | null;
  readonly ticked: boolean;
  readonly note: string;
  readonly busy: Busy;
  readonly open: boolean;
  readonly summary: string;
  readonly stateBefore: TaskStateName | null;
  readonly onRead: () => void;
  readonly onTick: (next: boolean) => void;
  readonly onNote: (next: string) => void;
  readonly onAccept: () => void;
}) {
  const field = task.evidence_fields.find((entry) => entry.evidence_field === "user_acceptance");

  return (
    <DisclosureBlock
      label="Kullanici kabulu"
      level={4}
      open={open}
      summary={blockSummary(
        "Kabul, gecisin girdisidir; hicbir durumu tasimaz ve hicbir sey yayimlamaz.",
        summary,
      )}
      summaryTestId="tasks-acceptance-summary"
    >
      <div>
        {field !== undefined && (
          <StatusPill label={CHECK_LABEL[field.state]} tone={CHECK_TONE[field.state]} />
        )}
      </div>

      <p className="text-xs text-muted" data-testid="tasks-acceptance-rule">
        Kabul kaydetmek gorevi hicbir duruma tasimaz ve hicbir sey yayimlamaz. Kabul o an okudugunuz paketin ozetine baglanir; paket degisirse yeniden okumaniz gerekir.
      </p>

      <div>
        <Button isDisabled={busy !== null} onPress={onRead} size="sm" variant="secondary">
          {busy === "proof"
            ? "Okunuyor..."
            : proof === null
              ? "Kabul edilecek paketi oku"
              : "Paketi yeniden oku"}
        </Button>
      </div>

      {proof === null ? (
        <p className="text-xs text-muted" data-testid="tasks-acceptance-unread">
          Paket henuz okunmadi. Okunmamis bir paket kabul edilemez: kabul
          dugmesi bir paket ozetine baglanmadan etkin olmaz.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="font-mono text-xs text-muted" data-testid="tasks-acceptance-digest">
            {`Kabul edilecek paket ozeti: ${shortDigest(proof.bundle_sha256)} · dosya ${String(
              proof.file_count,
            )} · adlandirilmis eksik ${String(proof.missing.length)}`}
          </p>

          {/* The backend's own sentence, verbatim. The UI writes no second
              version of it: a digest shown without it reads as an
              endorsement (ADR-0009 11). */}
          <p className="text-xs text-muted" data-testid="tasks-acceptance-hash-scope">
            {proof.hash_scope}
          </p>

          {proof.missing.length > 0 && (
            <ul className="flex flex-col gap-1" data-testid="tasks-acceptance-missing">
              {proof.missing.map((entry) => (
                <li className="font-mono text-xs text-muted" key={entry.key}>
                  {`• ${entry.key} · ${entry.state}`}
                </li>
              ))}
            </ul>
          )}

          <Checkbox isSelected={ticked} onChange={onTick}>
            <Checkbox.Content>
              <Checkbox.Control>
                <Checkbox.Indicator />
              </Checkbox.Control>
              Bu paketi okudum, yukarida adiyla listelenen eksikleri gordum ve
              kabulumun hicbir durumu tasimadigini anliyorum.
            </Checkbox.Content>
          </Checkbox>

          <TextField className="w-full" onChange={onNote} value={note}>
            <Label>Kabul notu (istege bagli)</Label>
            <TextArea rows={2} variant="secondary" />
          </TextField>

          <div>
            <Button isDisabled={busy !== null || !ticked} onPress={onAccept} size="sm">
              {busy === "accept" ? "Kaydediliyor..." : "Kabulumu kaydet (durumu tasimaz)"}
            </Button>
          </div>
        </div>
      )}

      {stateBefore !== null && (
        <p className="text-xs text-muted" data-testid="tasks-acceptance-no-transition">
          {`Kabul kaydedildi. Gorev durumu kabulden once '${STATE_LABEL[stateBefore]}' idi ve simdi '${STATE_LABEL[task.state]}'. Kabul bir gecis degildir; durumu tasiyan tek sey durum degisikligi islemidir.`}
        </p>
      )}
    </DisclosureBlock>
  );
}

/**
 * The fourth field: pointing at a send that already happened.
 *
 * Three things this region refuses to flatten:
 *
 * * **it cannot send anything.** The request carries an archived record's
 *   identity and nothing else. There is no room, no address and no text here,
 *   so there is no shape on this surface that could reach a write client
 *   (ADR-0009 11);
 * * **"archived" is not "verified".** Only a send whose own write outcome was
 *   `accepted` produces a verified reference. An `outcome_unknown` send is
 *   *recorded and not verified*, and that difference sits beside every row
 *   rather than being collapsed into "paylasildi";
 * * **it is not a publication requirement.** `public_share` stays out of the
 *   three fields that decide publication: a task can be finished without ever
 *   being shared (ADR-0004 4, ADR-0009 1).
 */
function PublicShareRegion({
  task,
  archive,
  chosen,
  note,
  busy,
  name,
  open,
  summary,
  onList,
  onChoose,
  onNote,
  onMark,
}: {
  readonly task: TaskStatusResponse;
  readonly archive: EvidenceList | null;
  readonly chosen: string;
  readonly note: string;
  readonly busy: Busy;
  readonly name: string;
  readonly open: boolean;
  readonly summary: string;
  readonly onList: () => void;
  readonly onChoose: (next: string) => void;
  readonly onNote: (next: string) => void;
  readonly onMark: () => void;
}) {
  const field = task.evidence_fields.find((entry) => entry.evidence_field === "public_share");

  return (
    <DisclosureBlock
      label="Public paylasim isareti"
      level={4}
      open={open}
      summary={blockSummary(
        "Arsivde zaten bulunan bir gonderimi bu goreve isaretler; hicbir sey gondermez ve yayim kararini vermez.",
        summary,
      )}
      summaryTestId="tasks-share-summary"
    >
      <div>
        {field !== undefined && (
          <StatusPill label={CHECK_LABEL[field.state]} tone={CHECK_TONE[field.state]} />
        )}
      </div>

      <p className="text-xs text-muted" data-testid="tasks-public-share-no-send">
        Bu islem hicbir sey gondermez ve gonderemez. Yalnizca arsivde zaten
        bulunan bir gonderimin bu goreve ait oldugunu kaydeder; istek bir oda
        adi, bir adres veya bir metin tasimaz. Gercek gonderim &quot;Olustur ve
        Dogrula&quot; bolumundeki uc adimli zincirden gecer.
      </p>

      <p className="text-xs text-muted" data-testid="tasks-public-share-verification-rule">
        Arsivlenmis olmak dogrulanmis olmak degildir. Yalnizca yazma sonucu
        &quot;Kabul edildi&quot; olan bir gonderim dogrulanmis sayilir. Sonucu
        bilinmeyen bir gonderim kaydedilir ve dogrulanmis sayilmaz: sunucu
        mesaji yazmis da olabilir, yazmamis da. Bu ayrimi bu ekran yapmaz;
        kaydin kendi yazma sonucundan okunur.
      </p>

      <p className="text-xs text-muted" data-testid="tasks-public-share-not-required">
        Bu alan yayim kararini vermez. Yayimi uc alan belirler; bir gorev hic
        paylasilmadan da tamamlanabilir.
      </p>

      <div>
        <Button isDisabled={busy !== null} onPress={onList} size="sm" variant="secondary">
          {busy === "proof" ? "Okunuyor..." : "Arsivlenmis gonderimleri listele"}
        </Button>
      </div>

      {archive !== null && archive.records.length === 0 && (
        <p className="text-xs text-muted" data-testid="tasks-public-share-empty">
          Arsivde hicbir gonderim yok. Isaretlenecek bir sey de yok: bu alan
          elle yazilan bir dizeyle degil, yalnizca gercekten olmus bir
          gonderimin kaydiyla doldurulabilir.
        </p>
      )}

      {archive !== null && archive.records.length > 0 && (
        <>
          <ul className="flex flex-col gap-2" data-testid="tasks-public-share-archive">
            {archive.records.map((record) => (
              <li
                className="rounded-lg border border-border p-2"
                data-testid={`tasks-archived-send-${record.id}`}
                key={record.id}
              >
                <label className="flex items-center gap-2">
                  <input
                    checked={chosen === record.id}
                    disabled={busy !== null}
                    name={name}
                    onChange={() => onChoose(record.id)}
                    type="radio"
                    value={record.id}
                  />
                  <span className="text-sm font-medium text-foreground">
                    {`Oda: ${record.room}`}
                  </span>
                </label>
                <span className="mt-1 flex flex-wrap items-center gap-2">
                  <StatusPill
                    label={SHARE_OUTCOME_LABEL[record.write_outcome]}
                    tone={record.write_outcome === "accepted" ? "ok" : "pending"}
                  />
                  <span className="font-mono text-xs text-muted">
                    {`${shortId(record.id)} · ${
                      record.write_outcome === "accepted"
                        ? "dogrulanmis olarak kaydedilir"
                        : "kaydedilir, dogrulanmis sayilmaz"
                    }`}
                  </span>
                </span>
              </li>
            ))}
          </ul>

          <TextField className="w-full" onChange={onNote} value={note}>
            <Label>Isaret notu (istege bagli)</Label>
            <TextArea rows={2} variant="secondary" />
          </TextField>

          <div>
            <Button
              isDisabled={busy !== null || chosen === ""}
              onPress={onMark}
              size="sm"
              variant="secondary"
            >
              {busy === "mark"
                ? "Isaretleniyor..."
                : "Bu gonderimi bu goreve isaretle (gonderim yapmaz)"}
            </Button>
          </div>
        </>
      )}
    </DisclosureBlock>
  );
}
