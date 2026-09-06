/**
 * "Gorevler" and "Aktivite" in a real browser: both sections open, the
 * approval flow runs end to end, and nothing leaves the machine.
 *
 * The whole `/api/tasks*` and `/api/activity*` group is answered from this
 * file, and that is a constraint rather than a convenience. A real run on the
 * live backend would write into the task database and the workspace directory
 * of the throwaway data directory, and - more to the point - a real *task*
 * only exists after a work scan has read a public room, which ADR-0006 2 puts
 * at zero outbound requests for this suite. Fulfilling the routes here means
 * the flow under test is the one a person drives, while the server is never
 * asked to read anything.
 *
 * What this therefore proves, and what it does not: it proves the rendering
 * and the interaction - that both sections are reachable by keyboard, that
 * `execution_unavailable` is on screen with its reason, that a plan cannot be
 * carried out until four separate approvals are given, that the test result
 * stays `not_implemented` and no publish-ready badge exists, that the
 * timeline keeps five kinds of moment apart and shows no progress control,
 * and that the strict CSP is not violated. It proves nothing about the
 * runner's own behaviour; that belongs to the Python suite, and a browser
 * test claiming it would be claiming it from the wrong side of the wire.
 */

import type { Page } from "@playwright/test";

import { expect, navEntry, openApp, test } from "../fixtures";

const TASK_ID = "3c1f9a7b5e2d84660a1b2c3d4e5f6071";
const RUN_ID = "aa11bb22cc33dd44ee55ff6677889900";

const EXECUTION_DETAIL =
  "TEST-ONLY: Keyfi kod ve kabuk yurutmesi bu surumde kapalidir. Guvenilir bir izolasyon urunun kendi kurulumunun parcasi degildir.";

const RUN_HONESTY =
  "TEST-ONLY: Bu surumde arac zinciri deterministiktir: model cagrisi, kabuk komutu ve keyfi kod yurutmesi yoktur.";

const STOP_STATEMENT =
  "TEST-ONLY: Durdur, sonraki arac cagrisini engeller. Iptalden sonra donen sonucu kaydedilmez.";

const TEST_RESULT_DETAIL =
  "TEST-ONLY: Test sonucu bu surumde uygulanmadi; onu kosacak yurutme kapalidir.";

const SURFACE = {
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
        detail: "TEST-ONLY: olculemeyen bir sey 'yok' diye yazilmaz.",
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
    refused_units_detail:
      "TEST-ONLY: token ve para birimi sayilmaz: model yolu kapalidir ve bir kullanim degeri uydurulmaz.",
    detail: "TEST-ONLY: Tavan derleme zamaninda yazilir; hicbir kod yolu onu degistirmez.",
    agent_can_raise_ceiling: false,
  },
  tools: [
    {
      id: "write_workspace_file",
      scope: "write_workspace",
      purpose: "TEST-ONLY: calisma alaninda metin dosyasi uretir.",
      params: [
        { name: "name", type: "file_name", required: true, detail: "TEST-ONLY: sade dosya adi." },
      ],
      call_cost: 1,
      produces_artifact: true,
    },
  ],
  // The closed acceptance registry, published beside the tools (Paket H4).
  // Two of the five, because a screen that rendered a hard-coded list would
  // pass with one.
  acceptance_checks: [
    {
      kind: "artifact_exists",
      purpose: "TEST-ONLY: adi verilen dosya calisma alaninda var mi.",
      params: [
        { name: "name", type: "file_name", required: true, detail: "TEST-ONLY: sade dosya adi." },
      ],
    },
    {
      kind: "artifact_contains",
      purpose: "TEST-ONLY: dosya istenen metni iceriyor mu.",
      params: [
        { name: "name", type: "file_name", required: true, detail: "TEST-ONLY: sade dosya adi." },
        { name: "text", type: "text", required: true, detail: "TEST-ONLY: aranacak metin." },
      ],
    },
  ],
  honesty: RUN_HONESTY,
  stop_statement: STOP_STATEMENT,
  interrupted_runs: [] as unknown[],
  resumed_any: false,
};

const TASK = {
  id: TASK_ID,
  module_id: "work_scan",
  source_id: "public_room_scan",
  content_sha256: "1f2e3d4c5b6a7988",
  source_version_id: "9f8e7d6c5b4a3928",
  title: "TEST-ONLY gorev: kucuk bir donusturucu",
  state: "awaiting_approval",
  state_detail: "TEST-ONLY: Gorev kullanicinin onayini bekliyor.",
  created_at: "2026-09-05T09:00:00Z",
  updated_at: "2026-09-05T09:05:00Z",
  evidence_fields: [
    {
      evidence_field: "task_outcome",
      state: "not_implemented",
      detail: "TEST-ONLY: cikti henuz uretilmedi.",
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
      detail: "TEST-ONLY: kullanici kabulu bir kisinin eylemidir.",
      ref_id: "",
    },
    {
      evidence_field: "public_share",
      state: "blocked",
      detail: "TEST-ONLY: dis paylasim bu surumde acilmadi.",
      ref_id: "",
    },
  ],
  ready_to_publish: false,
  blocking_fields: ["task_outcome", "test_result", "user_acceptance"],
  public_share_available: false,
  public_share_detail: "TEST-ONLY: dis paylasim kendi tek seferlik onayini ister.",
  budget_available: false,
  budget_detail: "TEST-ONLY: gorev katmaninda butce alani yoktur.",
};

const PLANNED_RUN = {
  id: RUN_ID,
  task_id: TASK_ID,
  phase: "planned",
  created_at: "2026-09-05T09:06:00Z",
  started_at: null,
  finished_at: null,
  stop_requested: false,
  plan_sha256: "5d4c3b2a19876543",
  test_condition: "TEST-ONLY: uretilen dosya alintiyla yan yana okunur.",
  // Empty on purpose: this plan recorded only the sentence, which is exactly
  // the case whose verdict has to stay `not_implemented` (Paket H4).
  acceptance: [] as unknown[],
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

const COMPLETED_RUN = {
  ...PLANNED_RUN,
  phase: "completed",
  started_at: "2026-09-05T09:07:00Z",
  finished_at: "2026-09-05T09:07:01Z",
  tool_calls_used: 1,
  elapsed_ms: 940,
  steps: [
    {
      ...PLANNED_RUN.steps[0],
      phase: "ran",
      artifact_name: "rapor.md",
      artifact_sha256: "77665544332211aabb",
    },
  ],
  detail: "TEST-ONLY: Her adim yapildi ve soz verilen cikti uretildi.",
};

const TASK_LIST = {
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
  unproducible_states: [] as string[],
  unproducible_detail: "TEST-ONLY: Bu surumde uretilemeyen durum yoktur; liste bos.",
};

function runsPayload(run: unknown): unknown {
  return {
    task: TASK,
    runs: [run],
    workspace_files: [{ name: "rapor.md", byte_count: 812, sha256: "77665544332211aabb" }],
    honesty: RUN_HONESTY,
  };
}

const ACTIVITY = {
  events: [
    {
      id: "e1",
      recorded_at: "2026-09-05T09:06:00Z",
      run_id: RUN_ID,
      task_id: TASK_ID,
      actor: "user",
      action: "run_planned",
      outcome: "ok",
      duration_ms: 0,
      artifact_sha256: "",
      check_sha256: "",
      detail: "TEST-ONLY: Plan kaydedildi.",
      chain_referenced: false,
    },
    {
      id: "e2",
      recorded_at: "2026-09-05T09:07:00Z",
      run_id: RUN_ID,
      task_id: TASK_ID,
      actor: "station_runner",
      action: "tool_called",
      outcome: "ok",
      duration_ms: 11,
      artifact_sha256: "",
      check_sha256: "",
      detail: "TEST-ONLY: write_workspace_file cagrildi.",
      chain_referenced: false,
    },
    {
      id: "e3",
      recorded_at: "2026-09-05T09:07:01Z",
      run_id: RUN_ID,
      task_id: TASK_ID,
      actor: "station_runner",
      action: "artifact_produced",
      outcome: "ok",
      duration_ms: 3,
      artifact_sha256: "77665544332211aabb",
      check_sha256: "",
      detail: "TEST-ONLY: 'rapor<script>alert(1)</script>.md' adli dosya uretildi.",
      chain_referenced: false,
    },
    {
      id: "e4",
      recorded_at: "2026-09-05T09:07:02Z",
      run_id: RUN_ID,
      task_id: TASK_ID,
      actor: "station_runner",
      action: "check_recorded",
      outcome: "ok",
      duration_ms: 4,
      artifact_sha256: "",
      check_sha256: "1122334455667788",
      detail: "TEST-ONLY: deterministik dogrulayici bir sonuc yazdi.",
      chain_referenced: false,
    },
    {
      id: "e5",
      recorded_at: "2026-09-05T09:07:03Z",
      run_id: RUN_ID,
      task_id: TASK_ID,
      actor: "user",
      action: "approval_awaited",
      outcome: "pending",
      duration_ms: 0,
      artifact_sha256: "",
      check_sha256: "",
      detail: "TEST-ONLY: Kullanicinin acik onayi bekleniyor.",
      chain_referenced: true,
    },
  ],
  event_count: 5,
  chain_referenced_count: 1,
  retained_events: 500,
  detail:
    "TEST-ONLY: Aktivite satirlari audit zincirinin halkasi degildir; zincirin atifta bulundugu satirlar budanmaz.",
};

/** Every start this spec sends, recorded from the intercepted requests. */
interface RunLedger {
  readonly starts: string[];
  /** Every model turn, so "a turn happens only inside a click" is checkable. */
  readonly turns: string[];
}

/**
 * One model turn's answer, mocked (ADR-0012).
 *
 * Mocked rather than real, and that is a rule rather than a convenience: a
 * spec that spent a real turn would make an outbound request from the test
 * suite, which `shell.spec.ts` measures and refuses. What is under test here
 * is what the *screen* does with a proposal, and that needs no provider.
 */
const MODEL_PROPOSAL = {
  outcome: "planned",
  run_id: RUN_ID,
  detail:
    "TEST-ONLY: Model 1 adimlik bir plan onerdi ve plan kaydedildi. Hicbir adim kosulmadi.",
  model_calls_used: 1,
  max_model_calls: 8,
  usage_detail: "giris token=184, cikis token=46, maliyet='0'",
  closing_text: "",
  tool_call_provenance:
    "TEST-ONLY: Arac cagrisi bicimi hesap sahibinin kendi anahtariyla olculdu.",
  task: TASK,
  runs: [PLANNED_RUN],
  model_can_start_a_run: false,
};

/**
 * Answer the task and activity groups locally.
 *
 * Registered before the app is opened, so the very first surface read is
 * already served from here and the backend is never asked to run anything.
 */
async function mockAgentSurface(page: Page, ledger: RunLedger): Promise<void> {
  await page.route(
    (url) =>
      url.pathname.startsWith("/api/tasks") || url.pathname.startsWith("/api/activity"),
    async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/tasks/surface") {
        await route.fulfill({ json: SURFACE });
        return;
      }
      if (url.pathname === "/api/tasks") {
        await route.fulfill({ json: TASK_LIST });
        return;
      }
      if (url.pathname.endsWith("/model-plan")) {
        ledger.turns.push(url.pathname);
        await route.fulfill({ json: MODEL_PROPOSAL });
        return;
      }
      if (url.pathname.endsWith("/start")) {
        ledger.starts.push(url.pathname);
        await route.fulfill({ json: runsPayload(COMPLETED_RUN) });
        return;
      }
      if (url.pathname.startsWith("/api/activity")) {
        await route.fulfill({ json: ACTIVITY });
        return;
      }
      await route.fulfill({
        json: runsPayload(ledger.starts.length === 0 ? PLANNED_RUN : COMPLETED_RUN),
      });
    },
  );
}

/**
 * Tick a checkbox the way a keyboard user does.
 *
 * The HeroUI checkbox keeps its real `<input>` in a visually hidden span
 * behind a styled control, so a pointer click lands on the decoration. Space
 * on the focused input is both the reliable path and the one a keyboard user
 * takes - which makes this say something extra: an approval can be given
 * without a mouse.
 */
async function tick(page: Page, name: RegExp): Promise<void> {
  const box = page.getByRole("checkbox", { name });
  await expect(box).not.toBeChecked();
  await box.focus();
  await box.press("Space");
  await expect(box).toBeChecked();
}

/** Open the one task and wait for its detail region. */
async function openTask(page: Page): Promise<void> {
  await page.getByRole("radio", { name: new RegExp(TASK.title) }).check();
  await expect(page.getByRole("region", { name: "Gorev ayrintisi" })).toBeVisible();
}

/**
 * The model lane, in a real browser and under the real CSP.
 *
 * What this proves that a jsdom test cannot: the region renders, its controls
 * are reachable, and a proposed plan still meets the four approvals with a
 * real focus ring and a real keyboard - the same path a hand-written plan
 * takes. Nothing here contacts a provider: the turn is answered by the route
 * mock above, and `shell.spec.ts` separately measures that the backend made
 * no outbound attempt during the whole run.
 */
test.describe("Gorevler: modelden plan onerisi", () => {
  test("spends no turn until a control is pressed, and starts nothing when it does", async ({
    page,
  }) => {
    const ledger: RunLedger = { starts: [], turns: [] };
    await mockAgentSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Gorevler").click();
    await openTask(page);

    // Opening a task reads; it does not spend anything.
    expect(ledger.turns, "opening a task may not spend a model turn").toEqual([]);
    await expect(page.getByTestId("tasks-model-no-turn")).toBeVisible();

    // The two rules are readable before the control that would spend a turn.
    await expect(page.getByTestId("tasks-model-approval-rule")).toContainText(
      "hicbir adimi atlatmaz",
    );
    await expect(page.getByTestId("tasks-model-registry-rule")).toContainText(
      "oneri butunuyle reddedilir",
    );

    await page.getByRole("button", { name: /Modelden plan oner/ }).click();
    await expect(page.getByTestId("tasks-model-outcome")).toBeVisible();

    expect(ledger.turns).toHaveLength(1);
    // The turn recorded a plan and started nothing.
    expect(ledger.starts, "a model turn may not start a run").toEqual([]);
    await expect(page.getByTestId("tasks-model-cannot-start")).toContainText(
      "Model bir calismayi baslatamaz",
    );
    // The provider's numbers, labelled as the provider's.
    await expect(page.getByTestId("tasks-model-usage")).toContainText("Saglayicinin beyani");
    await expect(page.getByTestId("tasks-model-usage-rule")).toContainText(
      "bizim olcumumuz degildir",
    );
  });

  test("still refuses to carry out the proposed plan until all four approvals are given", async ({
    page,
  }) => {
    const ledger: RunLedger = { starts: [], turns: [] };
    await mockAgentSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Gorevler").click();
    await openTask(page);

    await page.getByRole("button", { name: /Modelden plan oner/ }).click();
    await expect(page.getByTestId("tasks-model-outcome")).toBeVisible();

    const start = page.getByRole("button", { name: /Onayli plani calistir/ });
    await expect(start).toBeDisabled();

    // Three of four is not four. Every intermediate state is checked, because
    // an off-by-one in the approval gate would pass a test that only looked
    // at nought and four.
    await tick(page, /Plani okudum/);
    await expect(start).toBeDisabled();
    await tick(page, /Veri paylasimini/);
    await expect(start).toBeDisabled();
    await tick(page, /Calisma alanini/);
    await expect(start).toBeDisabled();
    await tick(page, /Butceyi/);
    await expect(start).toBeEnabled();

    expect(ledger.starts, "nothing may have started while approvals were given").toEqual([]);
  });

  test("says the publish-ready state is derived and offers no control that names it", async ({
    page,
  }) => {
    const ledger: RunLedger = { starts: [], turns: [] };
    await mockAgentSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Gorevler").click();
    await openTask(page);

    await expect(page.getByTestId("tasks-readiness-rule")).toContainText(
      "Istek bir hedef alani tasimaz",
    );
    await expect(page.getByTestId("tasks-readiness-blocking")).toContainText("test_result");

    const named = await page
      .getByRole("button")
      .filter({ hasText: /yayima hazir/i })
      .count();
    expect(named, "no control may name the derived state as its own output").toBe(0);
  });
});

test.describe("Gorevler", () => {
  test("appears in the navigation, opens from the keyboard and states why nothing runs", async ({
    page,
  }) => {
    const ledger: RunLedger = { starts: [], turns: [] };
    await mockAgentSurface(page, ledger);
    await openApp(page);

    const entry = navEntry(page, "Gorevler");
    await expect(entry).toBeVisible();

    // Focus and Enter, not a click: a section reachable only by mouse is a
    // section a keyboard user does not have.
    await entry.focus();
    await expect(entry).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(entry).toHaveAttribute("aria-current", "page");
    const execution = page.getByRole("region", { name: "Yurutme durumu" });
    await expect(execution).toBeVisible();
    await expect(page.getByTestId("tasks-execution-reason")).toContainText(
      "execution_unavailable",
    );
    await expect(page.getByTestId("tasks-execution-detail")).toContainText(EXECUTION_DETAIL);

    // Measured, and separately not relied upon.
    const inventory = page.getByTestId("tasks-execution-inventory");
    await expect(inventory).toContainText("docker_desktop");
    await expect(inventory).toContainText("dayanildi mi: hayir");
    await expect(inventory).toContainText("olcum: not_measured");

    // Exactly one entry is current at a time.
    await expect(
      page.getByRole("navigation", { name: "Ana bolumler" }).locator("[aria-current]"),
    ).toHaveCount(1);
  });

  test("shows the budget in three units and refuses to denominate it in tokens", async ({
    page,
  }) => {
    const ledger: RunLedger = { starts: [], turns: [] };
    await mockAgentSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Gorevler").click();

    await expect(page.getByTestId("tasks-budget-units")).toContainText("tool_call_count");
    await expect(page.getByTestId("tasks-budget-units")).toContainText("eszamanlilik 1");
    await expect(page.getByTestId("tasks-budget-refused-units")).toContainText("token, currency");
    await expect(page.getByText("Agent kendi butcesini yukseltemez")).toBeVisible();

    // The trust boundary is a list, not a sentence: an item folded into prose
    // is an item a reader skips.
    const boundary = page.getByTestId("tasks-trust-boundary");
    await expect(boundary).toContainText("Kasa (vault)");
    await expect(boundary).toContainText("Station'in kendi kaynak deposu");
    await expect(boundary).toContainText("git islemi");
    await expect(boundary).toContainText("kendi butce tavanini yukseltmek");
  });

  test("needs four approvals before a plan runs, and still reports the test as unimplemented", async ({
    page,
  }) => {
    const ledger: RunLedger = { starts: [], turns: [] };
    await mockAgentSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Gorevler").click();
    await openTask(page);

    // Nothing may be carried out before the four approvals exist.
    const start = page.getByRole("button", { name: "Onayli plani calistir" });
    await expect(start).toBeDisabled();
    expect(ledger.starts).toEqual([]);

    await tick(page, /Plani okudum/);
    await tick(page, /Veri paylasimini/);
    await tick(page, /Calisma alanini/);
    await expect(start).toBeDisabled();
    await tick(page, /Butceyi/);
    await expect(start).toBeEnabled();

    await start.click();

    await expect(page.getByText("Bitti: her adim yapildi, soz verilen her cikti var")).toBeVisible();
    expect(ledger.starts).toEqual([`/api/tasks/${TASK_ID}/runs/${RUN_ID}/start`]);

    // A finished run is still an untested one, and the surface says so.
    await expect(page.getByTestId("tasks-test-result-state")).toContainText("not_implemented");
    await expect(page.getByTestId("tasks-publish-state")).toContainText("Yayima hazir degil");

    // No badge anywhere announces the task as ready to publish.
    const claims = await page.evaluate(() =>
      [...document.querySelectorAll("*")].filter((element) =>
        /^(yayima hazir|hazir|ready_to_publish)$/i.test((element.textContent ?? "").trim()),
      ).length,
    );
    expect(claims, "nothing may announce this task as ready to publish").toBe(0);

    // The four fields are four regions, and the blocked one says blocked.
    await expect(page.getByTestId("tasks-field-task_outcome")).toContainText("Gorev basarisi");
    await expect(page.getByTestId("tasks-field-test_result")).toContainText("uygulanmadi");
    await expect(page.getByTestId("tasks-field-user_acceptance")).toContainText(
      "Kullanici kabulu",
    );
    await expect(page.getByTestId("tasks-field-public_share")).toContainText("engelli");
  });
});

test.describe("Aktivite", () => {
  test("opens from the keyboard and keeps five kinds of moment apart", async ({ page }) => {
    const ledger: RunLedger = { starts: [], turns: [] };
    await mockAgentSurface(page, ledger);
    await openApp(page);

    const entry = navEntry(page, "Aktivite");
    await entry.focus();
    await page.keyboard.press("Enter");
    await expect(entry).toHaveAttribute("aria-current", "page");

    for (const [action, label] of [
      ["run_planned", "Planlandi"],
      ["tool_called", "Arac cagrisi yapildi"],
      ["artifact_produced", "Cikti olusturuldu"],
      ["check_recorded", "Denetim kaydedildi"],
      ["approval_awaited", "Onay bekleniyor"],
    ] as const) {
      await expect(page.getByTestId(`activity-action-${action}`)).toContainText(label);
    }

    // Five distinct labels rather than one repeated badge.
    const labels = await page.evaluate(() =>
      [
        "run_planned",
        "tool_called",
        "artifact_produced",
        "check_recorded",
        "approval_awaited",
      ].map(
        (action) =>
          document.querySelector(`[data-testid="activity-action-${action}"]`)?.textContent?.trim() ??
          "",
      ),
    );
    expect(new Set(labels).size).toBe(5);

    // A waiting approval is pending, which is not ok - asserted inside that
    // row's badge group, because "pending" appearing *somewhere* on the page
    // would not say which event it belonged to.
    const awaiting = page.getByTestId("activity-action-approval_awaited").locator("xpath=..");
    await expect(awaiting.getByText("bekliyor", { exact: true })).toBeVisible();
    await expect(awaiting.getByText("tamam", { exact: true })).toHaveCount(0);
  });

  test("invents no progress, renders a detail as inert text and violates no CSP rule", async ({
    consoleLog,
    page,
  }) => {
    const ledger: RunLedger = { starts: [], turns: [] };
    await mockAgentSurface(page, ledger);
    await openApp(page);
    await navEntry(page, "Aktivite").click();

    await expect(page.getByTestId("activity-no-progress")).toContainText(
      "ilerleme cubugu, yuzde ve doner animasyon yoktur",
    );
    await expect(page.getByTestId("activity-no-model")).toContainText("boyle bir sutun yoktur");
    await expect(page.getByTestId("activity-retention")).toContainText("en yeni 500 satir");

    // Measured in the real DOM: no progress control and no animation standing
    // in for one.
    const measured = await page.evaluate(() => ({
      progress: document.querySelectorAll("progress, [role='progressbar']").length,
      animated: [...document.querySelectorAll("*")].filter((element) =>
        /\banimate-|\bspinner\b/.test(element.className.toString()),
      ).length,
    }));
    expect(measured.progress).toBe(0);
    expect(measured.animated).toBe(0);

    // The generated detail is text, and the markup inside it is text too.
    const rendered = await page.evaluate(() => {
      const row = document
        .querySelector('[data-testid="activity-action-artifact_produced"]')
        ?.closest("li");
      const detail = row?.querySelector("pre");
      return {
        tag: detail?.tagName ?? "",
        scripts: detail?.querySelectorAll("script").length ?? -1,
        links: row?.querySelectorAll("a").length ?? -1,
      };
    });
    expect(rendered.tag).toBe("PRE");
    expect(rendered.scripts).toBe(0);
    expect(rendered.links).toBe(0);

    expect(consoleLog.cspViolations(), "CSP refusals while rendering Aktivite").toEqual([]);
    expect(consoleLog.errors, "console errors while rendering Aktivite").toEqual([]);
  });
});
