import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { cwd } from "node:process";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bootstrapSession, resetSessionState } from "../../api/client";
import type {
  AgentRunStatus,
  AgentSurfaceResponse,
  AgentTaskRunsResponse,
  TaskListResponse,
  TaskStatusResponse,
} from "../../api/types";
import { AppShell } from "../AppShell";
import { TasksPanel } from "./TasksPanel";

/**
 * These assertions encode the product rules of the task surface, not its
 * styling. Every one of them fails closed on the same class of mistake:
 * letting an unexecuted, untested plan read as a finished piece of work.
 *
 * The load-bearing negatives:
 *
 * * **no execution, and the reason on screen.** `execution_unavailable` is
 *   rendered with the backend's sentence *and* the measured isolation
 *   inventory, including the facility that is present and deliberately not
 *   relied upon (ADR-0008 1);
 * * **no publish-ready badge.** The test result is `not_implemented`, so a
 *   run that produced files leaves the task short of `ready_to_publish`
 *   (SI-222);
 * * **no single verdict.** The four evidence fields are rendered apart and
 *   nothing sums them (ADR-0004 4);
 * * **no token and no currency.** The ceiling's refused units are on screen
 *   with the reason (ADR-0008 4);
 * * **no timer**, asserted at runtime and over the source, and **no browser
 *   storage** (SI-272, SI-24);
 * * **no unapproved run.** Four approvals, keyed to one plan.
 */

//: TEST-ONLY sentences. Shaped like the backend's, never copied from a live
//: response, and none of them is a real measurement of this machine.
const EXECUTION_DETAIL =
  "TEST-ONLY: Keyfi kod ve kabuk yurutmesi bu surumde kapalidir. Guvenilir bir izolasyon urunun kendi kurulumunun parcasi degildir.";

const RUN_HONESTY =
  "TEST-ONLY: Bu surumde arac zinciri deterministiktir: model cagrisi, kabuk komutu ve keyfi kod yurutmesi yoktur.";

const STOP_STATEMENT =
  "TEST-ONLY: Durdur, sonraki arac cagrisini engeller. Iptalden sonra donen sonucu kaydedilmez ve urettigi dosya calisma alanindan kaldirilir.";

const REFUSED_UNITS_DETAIL =
  "TEST-ONLY: Bu surumde token ve para birimi sayilmaz: model yolu kapalidir, dolayisiyla saglayicidan gelen bir kullanim degeri yoktur ve uydurulmaz.";

const CEILING_DETAIL =
  "TEST-ONLY: Tavan derleme zamaninda yazilir; hicbir kod yolu onu degistirmez.";

const TEST_RESULT_DETAIL =
  "TEST-ONLY: Test sonucu bu surumde uygulanmadi. Plan bir basari olcutu kaydeder, fakat onu kosacak yurutme kapalidir.";

const SURFACE: AgentSurfaceResponse = {
  execution: {
    arbitrary_execution_supported: false,
    reason: "execution_unavailable",
    detail: EXECUTION_DETAIL,
    inventory: [
      {
        facility: "docker_desktop",
        measured: "present",
        measured_at: "2026-09-05",
        detail: "TEST-ONLY: kurulu ve cevap veriyor; buna ragmen kullanilmiyor.",
        relied_upon: false,
      },
      {
        facility: "windows_optional_features",
        measured: "not_measured",
        measured_at: "2026-09-05",
        detail: "TEST-ONLY: sorgu admin yetkisi istiyor; olculemeyen bir sey 'yok' diye yazilmaz.",
        relied_upon: false,
      },
    ],
  },
  ceiling: {
    max_tool_calls: 32,
    max_wall_clock_seconds: 120,
    max_concurrency: 1,
    units: ["tool_call_count", "wall_clock_seconds", "concurrency"],
    refused_units: ["token", "currency"],
    refused_units_detail: REFUSED_UNITS_DETAIL,
    detail: CEILING_DETAIL,
    agent_can_raise_ceiling: false,
  },
  tools: [
    {
      id: "write_workspace_file",
      scope: "write_workspace",
      purpose: "TEST-ONLY: calisma alaninda metin dosyasi uretir.",
      params: [
        { name: "name", type: "file_name", required: true, detail: "TEST-ONLY: sade dosya adi." },
        { name: "content", type: "text", required: true, detail: "TEST-ONLY: dosya icerigi." },
      ],
      call_cost: 1,
      produces_artifact: true,
    },
    {
      id: "validate_json_file",
      scope: "deterministic_check",
      purpose: "TEST-ONLY: dosya iyi bicimli JSON mu?",
      params: [
        { name: "name", type: "file_name", required: true, detail: "TEST-ONLY: sade dosya adi." },
      ],
      call_cost: 1,
      produces_artifact: false,
    },
  ],
  honesty: RUN_HONESTY,
  stop_statement: STOP_STATEMENT,
  interrupted_runs: [],
  resumed_any: false,
};

const TASK: TaskStatusResponse = {
  id: "3c1f9a7b5e2d84660a1b2c3d4e5f6071",
  module_id: "work_scan",
  source_id: "public_room_scan",
  content_sha256: "1f2e3d4c5b6a7988",
  source_version_id: "9f8e7d6c5b4a3928",
  title: "TEST-ONLY gorev: kucuk bir CSV donusturucu",
  state: "awaiting_approval",
  state_detail: "TEST-ONLY: Gorev kullanicinin onayini bekliyor; hicbir sey calistirilmadi.",
  created_at: "2026-09-05T09:00:00Z",
  updated_at: "2026-09-05T09:05:00Z",
  evidence_fields: [
    {
      evidence_field: "task_outcome",
      state: "not_implemented",
      detail: "TEST-ONLY: Gorevin ciktisi henuz uretilmedi.",
      ref_id: "",
    },
    {
      evidence_field: "test_result",
      state: "not_implemented",
      detail: TEST_RESULT_DETAIL,
      ref_id: "",
    },
    {
      evidence_field: "user_acceptance",
      state: "not_implemented",
      detail: "TEST-ONLY: Kullanici kabulu bir kisinin eylemidir ve henuz yapilmadi.",
      ref_id: "",
    },
    {
      evidence_field: "public_share",
      state: "blocked",
      detail: "TEST-ONLY: Dis paylasim isareti henuz konmadi.",
      ref_id: "",
    },
  ],
  ready_to_publish: false,
  blocking_fields: ["task_outcome", "test_result", "user_acceptance"],
  // Paket H3 opened this field, so the wire carries `true` here now. The
  // fixture is updated because the backend changed, not to make anything
  // pass: `UNFILLABLE_FIELDS` is empty and the response derives this value
  // from it (ADR-0009 1). A fixture still saying `false` would be describing
  // the release before this one while looking perfectly correct.
  public_share_available: true,
  public_share_detail:
    "TEST-ONLY: Dis paylasim yalnizca arsivlenmis bir gonderime baglanabilir ve yayimi belirleyen uc alandan biri degildir.",
  budget_available: false,
  budget_detail: "TEST-ONLY: Gorev katmaninda butce alani yoktur; tavan calismanin kendisine aittir.",
};

const PLANNED_RUN: AgentRunStatus = {
  id: "aa11bb22cc33dd44ee55ff6677889900",
  task_id: TASK.id,
  phase: "planned",
  created_at: "2026-09-05T09:06:00Z",
  started_at: null,
  finished_at: null,
  stop_requested: false,
  plan_sha256: "5d4c3b2a19876543",
  test_condition: "TEST-ONLY: cikti dosyasi acilir ve alintiyla yan yana okunur.",
  test_result_state: "not_implemented",
  test_result_detail: TEST_RESULT_DETAIL,
  expected_artifacts: ["rapor.md"],
  steps: [
    {
      ordinal: 1,
      tool_id: "write_workspace_file",
      scope: "write_workspace",
      arguments_sha256: "abcdef0123456789",
      phase: "planned",
      started_at: null,
      finished_at: null,
      artifact_name: "",
      artifact_sha256: "",
      detail: "",
    },
  ],
  tool_calls_used: 0,
  elapsed_ms: 0,
  max_tool_calls: 32,
  max_wall_clock_seconds: 120,
  concurrency: 1,
  detail: "TEST-ONLY: Plan kaydedildi; hicbir sey calistirilmadi.",
};

const RUNNING_RUN: AgentRunStatus = {
  ...PLANNED_RUN,
  phase: "running",
  started_at: "2026-09-05T09:07:00Z",
  tool_calls_used: 1,
  elapsed_ms: 240,
};

const PAUSED_RUN: AgentRunStatus = {
  ...RUNNING_RUN,
  phase: "paused",
  stop_requested: true,
  steps: [
    { ...PLANNED_RUN.steps[0]!, phase: "ran", artifact_name: "rapor.md", artifact_sha256: "77665544332211" },
    {
      ordinal: 2,
      tool_id: "validate_json_file",
      scope: "deterministic_check",
      arguments_sha256: "0011223344556677",
      phase: "skipped",
      started_at: null,
      finished_at: null,
      artifact_name: "",
      artifact_sha256: "",
      detail:
        "TEST-ONLY: Durdurma sonrasi donen sonuc kaydedilmedi ve urettigi dosya calisma alanindan kaldirildi.",
    },
  ],
  detail: "TEST-ONLY: Kullanici durdurdu; sonraki arac cagrisi yapilmadi.",
};

/** A second plan, with a different id. A different plan is a different run. */
const SECOND_RUN: AgentRunStatus = {
  ...PLANNED_RUN,
  id: "bb22cc33dd44ee55ff6677889900aa11",
  plan_sha256: "1122334455667788",
};

const LIST: TaskListResponse = {
  tasks: [TASK],
  task_count: 1,
  producible_states: [
    "awaiting_approval",
    "blocked",
    "failed",
    "paused",
    "published",
    "ready_to_publish",
    "review_needed",
    "running",
    "suggested",
  ],
  unproducible_states: [],
  unproducible_detail:
    "TEST-ONLY: Bu surumde uretilemeyen durum yoktur; liste bos ve yeni bir durum once burada reddedilmis olarak gorunur.",
};

//: TEST-ONLY. The proof workspace for this task, as the acceptance surface
//: reads it. The bundle digest is a full 64-hex run on purpose, so the
//: "never render a seed-shaped value" rule is tested against the component's
//: shortening rather than against a pre-trimmed fixture.
const BUNDLE_SHA = "ef".repeat(32);

const PROOF_HASH_SCOPE =
  "TEST-ONLY: Bir SHA-256 ozeti yalnizca dosyanin bayt bakimindan ayni kaldigini tanimlar; icerigin dogrulugu hakkinda hicbir sey soylemez.";

const PROOF = {
  task: TASK,
  module: {
    id: "agent_workspace",
    name: "Agent calisma alani",
    purpose: "TEST-ONLY: bir gorevin calisma alani.",
    state: "available",
    available_from: "",
    owners: ["station_api.agent.service"],
    checks: [],
    complete: false,
    blocking_keys: [],
    not_implemented_keys: [],
  },
  artifacts: [{ name: "rapor.md", byte_count: 812, sha256: "cd".repeat(32) }],
  file_count: 1,
  total_bytes: 812,
  artifact_set_sha256: "ab".repeat(32),
  bundle_sha256: BUNDLE_SHA,
  missing: [
    {
      key: "evidence.test_result",
      state: "not_implemented",
      detail: TEST_RESULT_DETAIL,
    },
  ],
  claims: [
    {
      key: "independent_check",
      state: "not_implemented",
      detail: "TEST-ONLY: Bagimsiz kontrol bu surumde uygulanmadi.",
    },
    {
      key: "exit_code",
      state: "not_implemented",
      detail: "TEST-ONLY: Gercek bir cikis kodu uretilmedi.",
    },
    { key: "test_result", state: "not_implemented", detail: TEST_RESULT_DETAIL },
  ],
  formats: ["json", "markdown"],
  hash_scope: PROOF_HASH_SCOPE,
  bundle_scope: "TEST-ONLY: Paket hicbir yola yazilmaz; tarayiciya teslim edilir.",
  reproduction: "TEST-ONLY: Yeniden uretmek icin ozetleri kendi kopyanizla karsilastirin.",
  approval_ttl_seconds: 180,
};

//: TEST-ONLY. Two archived sends whose outcomes differ, because the whole
//: point of the fourth field is that "archived" and "verified" are not the
//: same thing. A fixture with one `accepted` row could not show that.
const ACCEPTED_SEND_ID = "11223344556677889900aabbccddeeff";
const UNKNOWN_SEND_ID = "ffeeddccbbaa00998877665544332211";

const ARCHIVE = {
  records: [
    {
      id: ACCEPTED_SEND_ID,
      reservation_id: "res-test-only-1",
      room: "test-only-room",
      did: "did:key:z6MkTESTONLYFIXTURE",
      nonce: "424242",
      canonical_sha256: "ab".repeat(32),
      signature: "TESTONLYSIGNATUREVALUE",
      http_status: 200,
      write_outcome: "accepted",
      capture_state: "",
      capture_detail: "",
      captured_at: null,
      room_generation: "1",
      capture_generation: "",
      generation_changed: false,
      captured_line_offset: null,
      captured_line_length: null,
      stream_sha256: "",
      stream_bytes: 0,
      stream_truncated: false,
      unreadable_lines: 0,
      request_sha256: "cd".repeat(32),
      response_sha256: "ef".repeat(32),
      recorded_at: "2026-09-05T09:10:00Z",
      external_anchor: null,
      levels: [],
    },
    {
      id: UNKNOWN_SEND_ID,
      reservation_id: "res-test-only-2",
      room: "test-only-room-two",
      did: "did:key:z6MkTESTONLYFIXTURE",
      nonce: "434343",
      canonical_sha256: "ba".repeat(32),
      signature: "TESTONLYSIGNATUREVALUE",
      http_status: 0,
      write_outcome: "outcome_unknown",
      capture_state: "",
      capture_detail: "",
      captured_at: null,
      room_generation: "1",
      capture_generation: "",
      generation_changed: false,
      captured_line_offset: null,
      captured_line_length: null,
      stream_sha256: "",
      stream_bytes: 0,
      stream_truncated: false,
      unreadable_lines: 0,
      request_sha256: "dc".repeat(32),
      response_sha256: "fe".repeat(32),
      recorded_at: "2026-09-05T09:11:00Z",
      external_anchor: null,
      levels: [],
    },
  ],
  record_count: 2,
  chain_state: "intact",
  chain_detail: "TEST-ONLY: zincir tutarli.",
  chain_link_count: 2,
};

function runsFor(runs: readonly AgentRunStatus[]): AgentTaskRunsResponse {
  return {
    task: TASK,
    runs: [...runs],
    workspace_files: [{ name: "rapor.md", byte_count: 812, sha256: "77665544332211" }],
    honesty: RUN_HONESTY,
  };
}

interface Recorded {
  readonly url: string;
  readonly body: unknown;
}

function jsonOk(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Route the mock by URL, and record every POST body.
 *
 * The bodies are the evidence for the rules that cannot be seen in the DOM:
 * that recording a plan runs nothing, that starting is a *separate* request,
 * and that nothing is sent at all until a control is pressed.
 */
function stub(
  runs: AgentTaskRunsResponse,
  options: {
    readonly sent?: Recorded[];
    readonly onPost?: (url: string, body: unknown) => Response | null;
    readonly proof?: unknown;
    readonly archive?: unknown;
    /** Keeps every answered POST pending until it resolves. */
    readonly hold?: Promise<void>;
  } = {},
): ReturnType<typeof vi.fn> {
  const mock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : new URL(input as URL).pathname;
    if (url === "/api/session/bootstrap") {
      return Promise.resolve(
        jsonOk({ csrf_token: "test-only-value-not-a-real-token", csrf_header: "X-Station-CSRF" }),
      );
    }
    if (init?.method === "POST") {
      const body: unknown =
        typeof init.body === "string" ? (JSON.parse(init.body) as unknown) : null;
      options.sent?.push({ url, body });
      const answer = options.onPost?.(url, body);
      if (answer !== null && answer !== undefined) {
        // `hold` keeps the response pending, which is the only way to
        // observe an in-flight guard: a mock that answers immediately makes
        // every second activation land *after* the first one finished, and a
        // double-activation test written against it passes whether the guard
        // exists or not.
        return options.hold === undefined
          ? Promise.resolve(answer)
          : options.hold.then(() => answer);
      }
    }
    if (url === "/api/tasks/surface") return Promise.resolve(jsonOk(SURFACE));
    if (url === "/api/tasks") return Promise.resolve(jsonOk(LIST));
    if (url === `/api/tasks/${TASK.id}/runs`) return Promise.resolve(jsonOk(runs));
    // Paket H3. Both are reads behind a button, never on mount - which is
    // why the "exactly two mount reads" assertion above still holds.
    if (url === `/api/proof/${TASK.id}`) {
      return Promise.resolve(jsonOk(options.proof ?? PROOF));
    }
    if (url === "/api/evidence/records") {
      return Promise.resolve(jsonOk(options.archive ?? ARCHIVE));
    }
    return Promise.resolve(jsonOk({ detail: "not_found" }, 404));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

/** Wait for the first two reads to settle: the panel replaces its placeholder. */
async function ready(): Promise<void> {
  await screen.findByRole("region", { name: "Gorev listesi" });
}

/** Open the one task and wait for its runs to arrive. */
async function openTask(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole("radio", { name: new RegExp(TASK.title) }));
  await screen.findByRole("region", { name: "Gorev ayrintisi" });
}

/** Tick all four approvals on the run card that carries them. */
async function approveAll(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  for (const label of [/Plani okudum/, /Veri paylasimini/, /Calisma alanini/, /Butceyi/]) {
    await user.click(screen.getByRole("checkbox", { name: label }));
  }
}

/** The `src` tree, found from the working directory (heroui-surface pattern). */
function resolveSrcDir(): string {
  const candidates = [join(cwd(), "src"), join(cwd(), "apps", "station-web", "src")];
  const found = candidates.find((candidate) => existsSync(join(candidate, "App.tsx")));
  if (found === undefined) throw new Error(`station-web/src not found from ${cwd()}`);
  return found;
}

/** Every non-test source file this section owns. */
function taskSurfaceSources(): { file: string; body: string }[] {
  const root = resolveSrcDir();
  const dir = join(root, "components", "tasks");
  const files = readdirSync(dir)
    .filter((name) => /\.tsx?$/.test(name) && !name.includes(".test."))
    .map((name) => join(dir, name));
  files.push(join(root, "pages", "TasksPage.tsx"));
  return files.map((file) => ({ file, body: readFileSync(file, "utf8") }));
}

function stubClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  resetSessionState();
});

describe("Gorevler section", () => {
  it("is reachable from the shell navigation and mounts the task surface", async () => {
    stub(runsFor([]));
    const user = userEvent.setup();
    render(
      <AppShell connectionError={null} loading={false} onRetryConnection={() => {}} status={null} />,
    );

    await user.click(screen.getByRole("button", { name: "Gorevler" }));

    expect(await screen.findByRole("region", { name: "Yurutme durumu" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Gorevler/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});

describe("Gorevler: no polling", () => {
  it("installs no timer and makes exactly the two mount reads without a click", async () => {
    const interval = vi.spyOn(globalThis, "setInterval");
    const mock = stub(runsFor([]));
    render(<TasksPanel />);
    await ready();

    // Vitest's own real-timer watchdog is excluded by name rather than by
    // silencing the assertion; every other interval still fails here.
    const installed = interval.mock.calls
      .map((call) => (typeof call[0] === "function" ? call[0].name : String(call[0])))
      .filter((name) => name !== "checkRealTimersCallback");
    expect(installed, "nothing on this surface may schedule a repeating task").toEqual([]);

    const urls = mock.mock.calls.map((call) => String(call[0])).sort();
    expect(urls).toEqual(["/api/tasks", "/api/tasks/surface"]);
  });

  it("carries no timer or storage primitive in its own source", () => {
    const sources = taskSurfaceSources();
    expect(sources.length).toBeGreaterThan(1);
    for (const { body, file } of sources) {
      const code = body.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      expect(code, `${file} schedules work`).not.toMatch(
        /\bsetInterval\s*\(|\bsetTimeout\s*\(|requestAnimationFrame\s*\(/,
      );
      expect(code, `${file} touches browser storage`).not.toMatch(
        /localStorage|sessionStorage|indexedDB/,
      );
      expect(code, `${file} renders untrusted content as HTML`).not.toContain(
        "dangerouslySetInnerHTML",
      );
    }
  });
});

describe("Gorevler: the honesty surface", () => {
  it("shows execution_unavailable with its reason and the measured inventory", async () => {
    stub(runsFor([]));
    render(<TasksPanel />);
    await ready();

    expect(screen.getByTestId("tasks-execution-reason")).toHaveTextContent(
      "execution_unavailable",
    );
    expect(screen.getByTestId("tasks-execution-detail")).toHaveTextContent(EXECUTION_DETAIL);
    expect(screen.getByTestId("tasks-honesty")).toHaveTextContent(RUN_HONESTY);

    // Measured *and* not relied upon: dropping the second half would turn
    // "we found a sandbox and chose not to trust it" into "there was none".
    const inventory = screen.getByTestId("tasks-execution-inventory");
    expect(inventory).toHaveTextContent("docker_desktop");
    expect(inventory).toHaveTextContent("olcum: present");
    expect(inventory).toHaveTextContent("dayanildi mi: hayir");
    // And "not measured" is kept apart from "absent".
    expect(inventory).toHaveTextContent("olcum: not_measured");
  });

  it("says the model lane is closed and that there is no model output at all", async () => {
    stub(runsFor([]));
    render(<TasksPanel />);
    await ready();

    const statement = screen.getByTestId("tasks-model-lane");
    expect(statement).toHaveTextContent("Model yolu bu surumde kapalidir");
    expect(statement).toHaveTextContent("model ciktisi diye bir sey yoktur");
    expect(statement).toHaveTextContent("'model' diye bir aktor tanimli degildir");
  });

  it("reports the test result as not_implemented and shows no publish-ready badge", async () => {
    stub(runsFor([PLANNED_RUN]));
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    expect(screen.getByTestId("tasks-untested")).toHaveTextContent(
      "Calistirilmamis kod test edilmis sayilmaz",
    );
    expect(screen.getByTestId("tasks-test-result-state")).toHaveTextContent(
      "Test sonucu: not_implemented",
    );
    expect(screen.getByTestId("tasks-test-result-detail")).toHaveTextContent(TEST_RESULT_DETAIL);
    expect(screen.getByTestId("tasks-publish-state")).toHaveTextContent("Yayima hazir degil");

    // No badge anywhere reduces the four fields to "ready to publish".
    const badges = [...document.body.querySelectorAll<HTMLElement>("*")].filter((element) =>
      /^(yayima hazir|hazir|ready_to_publish)$/i.test((element.textContent ?? "").trim()),
    );
    expect(badges, "no element may announce this task as ready to publish").toHaveLength(0);
  });

  it("keeps the four evidence fields apart, each with its own state", async () => {
    stub(runsFor([PLANNED_RUN]));
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    const outcome = screen.getByTestId("tasks-field-task_outcome");
    const result = screen.getByTestId("tasks-field-test_result");
    const acceptance = screen.getByTestId("tasks-field-user_acceptance");
    const share = screen.getByTestId("tasks-field-public_share");

    expect(within(outcome).getByText("Gorev basarisi")).toBeInTheDocument();
    expect(within(result).getByText("Test sonucu")).toBeInTheDocument();
    expect(within(acceptance).getByText("Kullanici kabulu")).toBeInTheDocument();
    expect(within(share).getByText("Public paylasim")).toBeInTheDocument();

    // Four regions, and none of them contains another: the separation is
    // structural rather than a matter of wording.
    for (const [a, b] of [
      [outcome, result],
      [result, acceptance],
      [acceptance, share],
      [share, outcome],
    ]) {
      expect(a!.contains(b!)).toBe(false);
    }
    // The blocked field is shown as blocked, not folded into the others.
    expect(share).toHaveTextContent("engelli");
    expect(result).toHaveTextContent("uygulanmadi");
  });

  it("shows the ceiling in its three units and names the units it refuses", async () => {
    stub(runsFor([]));
    render(<TasksPanel />);
    await ready();

    const units = screen.getByTestId("tasks-budget-units");
    expect(units).toHaveTextContent("tool_call_count");
    expect(units).toHaveTextContent("wall_clock_seconds");
    expect(units).toHaveTextContent("concurrency");
    expect(units).toHaveTextContent("eszamanlilik 1");

    // Refused units are a claim on screen, not an absence to be noticed.
    expect(screen.getByTestId("tasks-budget-refused-units")).toHaveTextContent("token, currency");
    expect(screen.getByTestId("tasks-budget-refused-detail")).toHaveTextContent(
      REFUSED_UNITS_DETAIL,
    );
    expect(screen.getByText("Agent kendi butcesini yukseltemez")).toBeInTheDocument();
  });

  it("lists what the agent cannot reach and what it cannot do", async () => {
    stub(runsFor([]));
    render(<TasksPanel />);
    await ready();

    const boundary = screen.getByTestId("tasks-trust-boundary");
    for (const item of [
      "Imzalayici",
      "Kasa (vault)",
      "Recovery dosyasi",
      "Saglayici (OpenCode) kimlik bilgisi",
      "Global ortam degiskenleri",
      "Kullanicinin home dizini",
      "Station'in kendi kaynak deposu",
    ]) {
      expect(boundary, `missing from the boundary: ${item}`).toHaveTextContent(item);
    }
    for (const item of [
      "git islemi",
      "paket kurmak",
      "izin listesi",
      "plugin",
      "kendi arac listesine",
      "kendi butce tavanini yukseltmek",
    ]) {
      expect(boundary, `missing from the boundary: ${item}`).toHaveTextContent(item);
    }
    // The registry is published, so the count is data rather than a claim.
    expect(screen.getByText(/Kayitli arac sayisi: 2/)).toBeInTheDocument();
  });

  it("says a restart resumes nothing, even when there is nothing to resume", async () => {
    stub(runsFor([]));
    render(<TasksPanel />);
    await ready();

    expect(screen.getByTestId("tasks-interrupted")).toHaveTextContent(
      "acilista otomatik devam yoktur",
    );
  });

  it("shows no progress bar and no invented completion figure", async () => {
    stub(runsFor([RUNNING_RUN]));
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    expect(screen.queryAllByRole("progressbar")).toHaveLength(0);
    expect(document.querySelectorAll("progress")).toHaveLength(0);
    // Usage is the measured pair, against the published ceiling.
    expect(screen.getByTestId(`tasks-usage-${RUNNING_RUN.id}`)).toHaveTextContent(
      "1 / 32 arac cagrisi",
    );
  });
});

describe("Gorevler: approval and control", () => {
  it("refuses to carry out a plan until all four approvals are given", async () => {
    const sent: Recorded[] = [];
    stub(runsFor([PLANNED_RUN]), { sent });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    const start = screen.getByRole("button", { name: "Onayli plani calistir" });
    expect(start).toBeDisabled();

    // Three of four is still not four.
    await user.click(screen.getByRole("checkbox", { name: /Plani okudum/ }));
    await user.click(screen.getByRole("checkbox", { name: /Veri paylasimini/ }));
    await user.click(screen.getByRole("checkbox", { name: /Calisma alanini/ }));
    expect(screen.getByRole("button", { name: "Onayli plani calistir" })).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: /Butceyi/ }));
    expect(screen.getByRole("button", { name: "Onayli plani calistir" })).toBeEnabled();

    // And nothing has been sent while the approvals were being collected.
    expect(sent).toHaveLength(0);
  });

  it("says a change of scope needs a new approval, and a new plan is unapproved", async () => {
    const sent: Recorded[] = [];
    // The second POST records a *different* run; approvals are keyed to a run
    // id, so the new plan cannot inherit the old plan's approvals.
    stub(runsFor([PLANNED_RUN]), {
      sent,
      onPost: (url) =>
        url === `/api/tasks/${TASK.id}/runs` ? jsonOk(runsFor([SECOND_RUN])) : null,
    });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    expect(screen.getByTestId(`tasks-scope-change-${PLANNED_RUN.id}`)).toHaveTextContent(
      "kapsam veya risk degisirse yeni bir plan kaydedilir ve yeni plan yeniden onay ister",
    );

    await approveAll(user);
    expect(screen.getByRole("button", { name: "Onayli plani calistir" })).toBeEnabled();

    // Record a different plan: one step and a success criterion.
    await user.click(screen.getByRole("radio", { name: /validate_json_file/ }));
    await user.type(screen.getByLabelText(/^name /), "rapor.md");
    await user.click(screen.getByRole("button", { name: "Adimi plana ekle" }));
    await user.type(
      screen.getByLabelText(/Basari olcutu/),
      "TEST-ONLY: dosya iyi bicimli JSON olmali.",
    );
    await user.click(screen.getByRole("button", { name: "Plani kaydet (calistirmaz)" }));

    // The new run is on screen and its start control is disabled again.
    await screen.findByText(new RegExp(SECOND_RUN.id.slice(0, 12)));
    expect(screen.getByRole("button", { name: "Onayli plani calistir" })).toBeDisabled();

    // Recording a plan ran nothing: the only write was the plan itself.
    expect(sent.map((entry) => entry.url)).toEqual([`/api/tasks/${TASK.id}/runs`]);
  });

  it("stops a run, and shows that the late result produced no side effect", async () => {
    const sent: Recorded[] = [];
    stub(runsFor([RUNNING_RUN]), {
      sent,
      onPost: (url) => (url.endsWith("/stop") ? jsonOk(runsFor([PAUSED_RUN])) : null),
    });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    // The statement is on screen before the button is pressed, not after.
    expect(screen.getByTestId(`tasks-stop-statement-${RUNNING_RUN.id}`)).toHaveTextContent(
      STOP_STATEMENT,
    );

    await user.click(screen.getByRole("button", { name: "Durdur" }));

    await waitFor(() => {
      expect(screen.getByText("Kullanici durdurdu")).toBeInTheDocument();
    });
    expect(sent[0]?.url).toBe(`/api/tasks/${TASK.id}/runs/${RUNNING_RUN.id}/stop`);
    // The skipped step says what happened to the result that arrived late.
    expect(screen.getByText(/atlandi/)).toBeInTheDocument();
    expect(
      screen.getByText(/Durdurma sonrasi donen sonuc kaydedilmedi/),
    ).toBeInTheDocument();
    // Continuing is a person's act, and a crash never continues on its own.
    expect(screen.getByTestId(`tasks-resume-statement-${PAUSED_RUN.id}`)).toHaveTextContent(
      "Cokme veya yeniden baslatma sonrasi otomatik devam yoktur",
    );
  });

  it("does not start a second run while the first start is in flight", async () => {
    let starts = 0;
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : new URL(input as URL).pathname;
        if (url === "/api/session/bootstrap") {
          return Promise.resolve(
            jsonOk({
              csrf_token: "test-only-value-not-a-real-token",
              csrf_header: "X-Station-CSRF",
            }),
          );
        }
        if (url.endsWith("/start") && init?.method === "POST") {
          starts += 1;
          return gate.then(() => jsonOk(runsFor([PAUSED_RUN])));
        }
        if (url === "/api/tasks/surface") return Promise.resolve(jsonOk(SURFACE));
        if (url === "/api/tasks") return Promise.resolve(jsonOk(LIST));
        return Promise.resolve(jsonOk(runsFor([PLANNED_RUN])));
      }),
    );
    await bootstrapSession();
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);
    await approveAll(user);

    await user.click(screen.getByRole("button", { name: "Onayli plani calistir" }));
    const busy = await screen.findByRole("button", { name: "Calistiriliyor..." });
    expect(busy).toBeDisabled();

    // A second activation while pending must not start another run.
    fireEvent.click(busy);
    expect(starts).toBe(1);

    release();
    await waitFor(() => {
      expect(starts).toBe(1);
    });
  });

  it("uses no browser-side persistence for the plan, the approvals or the result", async () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { getItem: () => null, setItem, removeItem: vi.fn() });
    vi.stubGlobal("sessionStorage", { getItem: () => null, setItem, removeItem: vi.fn() });

    stub(runsFor([PLANNED_RUN]));
    await bootstrapSession();
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);
    await approveAll(user);

    expect(setItem).not.toHaveBeenCalled();
  });

  it("keeps a failed start on screen and copies only the redacted diagnostics", async () => {
    stub(runsFor([PLANNED_RUN]), {
      onPost: (url) =>
        url.endsWith("/start")
          ? jsonOk({ detail: "Plan degismis; bu calisma baslatilamaz." }, 409)
          : null,
    });
    await bootstrapSession();
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);
    await approveAll(user);

    await user.click(screen.getByRole("button", { name: "Onayli plani calistir" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Calisma baslatilamadi");
    expect(alert).toHaveTextContent("Kod: http_409");
    // A refused start offers no retry: repeating it would refuse again.
    expect(within(alert).queryByRole("button", { name: "Yeniden dene" })).toBeNull();

    let copied = "";
    stubClipboard((text) => {
      copied = text;
      return Promise.resolve();
    });
    await user.click(within(alert).getByRole("button", { name: "Tani bilgisini kopyala" }));
    await screen.findByRole("button", { name: "Kopyalandi" });

    // The payload is the same six redacted keys every other surface copies.
    const payload = JSON.parse(copied) as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual([
      "code",
      "kind",
      "request_id",
      "section",
      "status",
      "timestamp",
    ]);
    expect(payload["section"]).toBe("Gorevler");
    expect(payload["code"]).toBe("http_409");
  });
});

describe("Gorevler: kabul gecisin girdisidir", () => {
  it("offers no acceptance control until the bundle has actually been read", async () => {
    const sent: Recorded[] = [];
    stub(runsFor([PLANNED_RUN]), { sent });
    const user = userEvent.setup();
    await bootstrapSession();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    expect(screen.getByTestId("tasks-acceptance-unread")).toHaveTextContent(
      "Okunmamis bir paket kabul edilemez",
    );
    expect(screen.queryByRole("button", { name: /Kabulumu kaydet/ })).toBeNull();
    expect(
      sent.filter((entry) => entry.url.includes("/acceptance")),
      "nothing may be accepted before it is read",
    ).toEqual([]);
  });

  it("shows the digest, the named gaps and the hash sentence beside the tick", async () => {
    stub(runsFor([PLANNED_RUN]));
    const user = userEvent.setup();
    await bootstrapSession();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: /Kabul edilecek paketi oku/ }));
    await screen.findByTestId("tasks-acceptance-digest");

    // Twelve characters, never the whole 64-hex run.
    expect(screen.getByTestId("tasks-acceptance-digest")).toHaveTextContent("efefefefefef");
    expect(document.body.textContent ?? "").not.toMatch(/\b[0-9a-fA-F]{64}\b/);

    // The gap is named while the tick is being given, not summarised.
    expect(screen.getByTestId("tasks-acceptance-missing")).toHaveTextContent(
      "evidence.test_result",
    );
    // And the backend's own sentence about what a digest establishes is
    // beside it, rather than a second version written here.
    expect(screen.getByTestId("tasks-acceptance-hash-scope")).toHaveTextContent(
      PROOF_HASH_SCOPE,
    );
  });

  it("sends the digest of the bundle that was read, and nothing else", async () => {
    const sent: Recorded[] = [];
    stub(runsFor([PLANNED_RUN]), {
      sent,
      onPost: (url) => (url.endsWith("/acceptance") ? jsonOk(PROOF) : null),
    });
    const user = userEvent.setup();
    await bootstrapSession();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: /Kabul edilecek paketi oku/ }));
    await screen.findByTestId("tasks-acceptance-digest");

    const accept = screen.getByRole("button", { name: /Kabulumu kaydet/ });
    expect(accept, "an unread bundle may not be accepted by an untouched tick").toBeDisabled();

    await user.click(
      screen.getByRole("checkbox", { name: /Bu paketi okudum/ }),
    );
    expect(accept).toBeEnabled();
    await user.click(accept);

    await waitFor(() => {
      expect(sent.filter((entry) => entry.url.endsWith("/acceptance"))).toHaveLength(1);
    });
    const body = sent.find((entry) => entry.url.endsWith("/acceptance"))?.body as Record<
      string,
      unknown
    >;
    expect(body.bundle_sha256).toBe(BUNDLE_SHA);
    // Two keys and no third: there is no state, no transition and no target
    // in this request, because acceptance is not a transition (SI-222).
    expect(Object.keys(body).sort()).toEqual(["bundle_sha256", "detail"]);
  });

  it("records the acceptance without moving the task, and says the state did not move", async () => {
    const sent: Recorded[] = [];
    stub(runsFor([PLANNED_RUN]), {
      sent,
      onPost: (url) => (url.endsWith("/acceptance") ? jsonOk(PROOF) : null),
    });
    const user = userEvent.setup();
    await bootstrapSession();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: /Kabul edilecek paketi oku/ }));
    await screen.findByTestId("tasks-acceptance-digest");
    await user.click(screen.getByRole("checkbox", { name: /Bu paketi okudum/ }));
    await user.click(screen.getByRole("button", { name: /Kabulumu kaydet/ }));

    const note = await screen.findByTestId("tasks-acceptance-no-transition");
    // The state before and the state after are both on screen and they are
    // the same one. Saying "kabul edildi" alone would leave a reader to
    // assume the task advanced.
    expect(note).toHaveTextContent("kabulden once 'Onay bekliyor' idi");
    expect(note).toHaveTextContent("simdi 'Onay bekliyor'");

    // No transition request was made as a side effect of the acceptance.
    expect(
      sent.filter((entry) => entry.url.endsWith("/state")),
      "acceptance must not move the task",
    ).toEqual([]);
    expect(screen.getByTestId("tasks-publish-state")).toHaveTextContent("Yayima hazir degil");
  });

  it("starts no second acceptance while the first one is still in flight", async () => {
    const sent: Recorded[] = [];
    let release = (): void => {};
    const hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    stub(runsFor([PLANNED_RUN]), {
      sent,
      hold,
      onPost: (url) => (url.endsWith("/acceptance") ? jsonOk(PROOF) : null),
    });
    const user = userEvent.setup();
    await bootstrapSession();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    await user.click(screen.getByRole("button", { name: /Kabul edilecek paketi oku/ }));
    await screen.findByTestId("tasks-acceptance-digest");
    await user.click(screen.getByRole("checkbox", { name: /Bu paketi okudum/ }));

    // Both activations happen while the request is still open. The
    // double-activation rule (ui-action-map 1.4) is what has to stop the
    // second one; the post-success reset cannot, because it has not run.
    const accept = screen.getByRole("button", { name: /Kabulumu kaydet/ });
    await user.click(accept);
    await user.click(accept);
    expect(sent.filter((entry) => entry.url.endsWith("/acceptance"))).toHaveLength(1);

    release();
    await waitFor(() => {
      expect(screen.getByTestId("tasks-acceptance-no-transition")).toBeInTheDocument();
    });
    expect(sent.filter((entry) => entry.url.endsWith("/acceptance"))).toHaveLength(1);
  });

  it("says the publish-ready state cannot be asked for, and offers no control that would", async () => {
    stub(runsFor([PLANNED_RUN]));
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    expect(screen.getByTestId("tasks-publish-unreachable")).toHaveTextContent(
      "tasiyan bir kullanici yolu bu surumde yoktur",
    );
    // The five user transitions, and `ready_to_publish` is not among them.
    const labels = screen
      .getAllByRole("button")
      .map((element) => element.textContent ?? "");
    expect(labels.filter((label) => /yayima hazir/i.test(label))).toEqual([]);
  });
});

describe("Gorevler: the fourth field points at an archived send", () => {
  it("states that it sends nothing and that archived is not verified", async () => {
    stub(runsFor([PLANNED_RUN]));
    const user = userEvent.setup();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    expect(screen.getByTestId("tasks-public-share-no-send")).toHaveTextContent(
      "hicbir sey gondermez ve gonderemez",
    );
    expect(screen.getByTestId("tasks-public-share-verification-rule")).toHaveTextContent(
      "Arsivlenmis olmak dogrulanmis olmak degildir",
    );
    expect(screen.getByTestId("tasks-public-share-not-required")).toHaveTextContent(
      "hic paylasilmadan da tamamlanabilir",
    );
  });

  it("keeps an accepted send and an unknown one apart in the list", async () => {
    stub(runsFor([PLANNED_RUN]));
    const user = userEvent.setup();
    await bootstrapSession();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    await user.click(
      screen.getByRole("button", { name: /Arsivlenmis gonderimleri listele/ }),
    );
    await screen.findByTestId("tasks-public-share-archive");

    const accepted = screen.getByTestId(`tasks-archived-send-${ACCEPTED_SEND_ID}`);
    const unknown = screen.getByTestId(`tasks-archived-send-${UNKNOWN_SEND_ID}`);

    expect(accepted).toHaveTextContent("Kabul edildi");
    expect(accepted).toHaveTextContent("dogrulanmis olarak kaydedilir");

    // The unknown outcome is recorded and *not* verified, and the row says
    // exactly that rather than flattening to "paylasildi".
    expect(unknown).toHaveTextContent("Sonuc bilinmiyor");
    expect(unknown).toHaveTextContent("kaydedilir, dogrulanmis sayilmaz");
    expect(unknown.textContent ?? "", "an unknown outcome may not carry a success glyph")
      .not.toContain("✓");
  });

  it("sends an evidence identity and nothing that could reach a write client", async () => {
    const sent: Recorded[] = [];
    stub(runsFor([PLANNED_RUN]), {
      sent,
      onPost: (url) => (url.endsWith("/public-share") ? jsonOk(PROOF) : null),
    });
    const user = userEvent.setup();
    await bootstrapSession();
    render(<TasksPanel />);
    await ready();
    await openTask(user);

    await user.click(
      screen.getByRole("button", { name: /Arsivlenmis gonderimleri listele/ }),
    );
    await screen.findByTestId("tasks-public-share-archive");

    const mark = screen.getByRole("button", { name: /Bu gonderimi bu goreve isaretle/ });
    expect(mark, "nothing may be marked before a record is chosen").toBeDisabled();

    await user.click(
      within(screen.getByTestId(`tasks-archived-send-${UNKNOWN_SEND_ID}`)).getByRole("radio"),
    );
    await user.click(mark);

    await waitFor(() => {
      expect(sent.filter((entry) => entry.url.endsWith("/public-share"))).toHaveLength(1);
    });
    const body = sent.find((entry) => entry.url.endsWith("/public-share"))?.body as Record<
      string,
      unknown
    >;
    expect(body.evidence_id).toBe(UNKNOWN_SEND_ID);
    // Two keys and no third. No room, no address, no text: there is no shape
    // in this request that an outbound client could be reached with.
    expect(Object.keys(body).sort()).toEqual(["detail", "evidence_id"]);
    for (const key of ["room", "url", "path", "text", "message", "did"]) {
      expect(body, `the request may not carry ${key}`).not.toHaveProperty(key);
    }
  });
});
