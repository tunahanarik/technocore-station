/**
 * What a successful response must look like before it reaches React.
 *
 * The rule this file exists to enforce: **no endpoint is exempt**. `request`
 * takes a validator as a required argument, so a new call cannot be written
 * without one - the compiler refuses the call site rather than letting a
 * `data as T` cast admit a document nobody checked. A lookup table keyed by
 * URL would not have that property: forget a row and the endpoint is silently
 * unvalidated again, which is exactly the defect this replaces.
 *
 * Three properties are deliberate:
 *
 * 1. **Depth.** Checks descend into nested objects and into every element of
 *    every list. The crash this was written for was `reading 'state'` on a
 *    nested field, so a guard that stopped at the top level would have passed
 *    the offending body straight through.
 * 2. **Presence, not truthiness.** A field must be there and hold the right
 *    kind of value. `null` passes only where the type says nullable, and a
 *    key whose value is `undefined` fails like a missing one.
 * 3. **Enums are checked; single-value literals are not.** A union with
 *    several members - a task state, a capture state, a drift state - is a
 *    closed vocabulary the UI switches on, so an unknown member is a
 *    malformed document. A field the mirror types as one literal (`false`,
 *    `1`, `"not_implemented"`) is checked for its *kind* instead. Pinning the
 *    value would turn a server that widened a field into a screen that
 *    refuses every response, which is the mistake `public_share_available`
 *    already recorded in `types.ts` - in the opposite direction.
 *
 * Unknown extra keys are allowed. A server that adds a field has not broken
 * this client, and refusing one would make every backend addition an outage.
 */

import type {
  ActivityDeleteResponse,
  ActivityListResponse,
  AgentSurfaceResponse,
  AgentTaskRunsResponse,
  AppStatus,
  AuditChainStatus,
  ComposeCapability,
  ComposeDraft,
  ComposeSendResult,
  ComposeSignature,
  ConformanceStatus,
  EvidenceCaptureResult,
  EvidenceList,
  IdentityStatus,
  ModelProposalResponse,
  OpenCodeStatus,
  ProofPrepareResult,
  ProofWorkspace,
  RecoveryInspectResult,
  SessionBootstrap,
  TaskListResponse,
  TaskStatusResponse,
  TechnocoreStatus,
  WorkScanStatus,
  WorkScanSuggestion,
  WriteGateStatus,
} from "./types";

/**
 * The proof a response carries the document its call site expects.
 *
 * `request` cannot be called without one, which is the whole mechanism: a
 * missing validator is a compile error, not an unchecked response.
 */
export type ResponseValidator<T> = (value: unknown) => value is T;

/** An anonymous predicate used to build the validators below. */
type Check = (value: unknown) => boolean;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const str: Check = (value) => typeof value === "string";
const bool: Check = (value) => typeof value === "boolean";
const num: Check = (value) => typeof value === "number" && Number.isFinite(value);
const int: Check = (value) => num(value) && Number.isInteger(value);

/** A closed vocabulary the UI switches on. An unknown member is malformed. */
function enumOf(...allowed: readonly string[]): Check {
  return (value) => typeof value === "string" && allowed.includes(value);
}

function nullOr(check: Check): Check {
  return (value) => value === null || check(value);
}

/** Deep by construction: every element is checked, not just the array. */
function listOf(check: Check): Check {
  return (value) => Array.isArray(value) && value.every((entry) => check(entry));
}

/**
 * An object whose every named field is present and passes its own check.
 *
 * `key in value` is asserted separately so an explicit `undefined` fails the
 * same way an absent key does.
 */
function shape(fields: Record<string, Check>): Check {
  return (value) =>
    isRecord(value) &&
    Object.entries(fields).every(([key, check]) => key in value && check(value[key]));
}

/** Bind a checked shape to the type it proves. The one cast in this file. */
function validator<T>(check: Check): ResponseValidator<T> {
  return (value): value is T => check(value);
}

// --- Session ---------------------------------------------------------------

export const isSessionBootstrap = validator<SessionBootstrap>(
  shape({ csrf_token: str, csrf_header: str }),
);

// --- Application status ----------------------------------------------------
//
// The three constants below are not enum members but structural claims the
// app makes about itself: the service reports one running state, the cookie is
// SameSite=Strict, and the transport is loopback HTTP. A response saying
// anything else is not the document this UI renders.

const appStatus = shape({
  service: shape({
    state: enumOf("running"),
    stage: int,
    mode: enumOf("production", "development"),
  }),
  database: shape({
    state: enumOf("ready", "unavailable"),
    journal_mode: str,
    foreign_keys: bool,
    schema_revision: str,
  }),
  session_security: shape({
    state: enumOf("active"),
    cookie_http_only: bool,
    cookie_same_site: enumOf("strict"),
    cookie_secure: bool,
    csrf_required: bool,
    transport: enumOf("loopback-http"),
  }),
  technocore: shape({
    state: enumOf("never_checked", "current", "drifted", "unavailable"),
    write_available_from_stage: num,
    detail: str,
  }),
});

export const isAppStatus = validator<AppStatus>(appStatus);

// --- Identity, recovery and the write gate ---------------------------------

const protection = enumOf("dpapi", "dpapi+passphrase");

const gateCheck = shape({
  key: str,
  state: enumOf("passed", "blocked", "not_implemented"),
  detail: str,
  stage: str,
});

const writeGate = shape({
  allowed: bool,
  identity_ready: bool,
  blocking_reasons: listOf(str),
  checks: listOf(gateCheck),
});

export const isWriteGateStatus = validator<WriteGateStatus>(writeGate);

export const isIdentityStatus = validator<IdentityStatus>(
  shape({
    state: enumOf(
      "no_identity",
      "creating",
      "recovery_pending",
      "ready",
      "revoked",
      "capability_error",
    ),
    identity: nullOr(
      shape({
        did: str,
        public_key: str,
        fingerprint: str,
        fingerprint_short: str,
        label: str,
        status: str,
        protection: nullOr(protection),
        created_at: str,
        revoked_at: nullOr(str),
      }),
    ),
    recovery: shape({
      exported_at: nullOr(str),
      verified_at: nullOr(str),
      file_fingerprint: nullOr(str),
      kdf: nullOr(str),
      kdf_time_cost: nullOr(num),
      kdf_memory_kib: nullOr(num),
      kdf_parallelism: nullOr(num),
    }),
    capability: shape({
      platform_supported: bool,
      dpapi_available: bool,
      aead_available: bool,
      usable: bool,
      detail: str,
    }),
    gate: writeGate,
    default_protection: protection,
    min_passphrase_chars: num,
    create_confirmation_text: str,
  }),
);

export const isRecoveryInspectResult = validator<RecoveryInspectResult>(
  shape({ did: str, fingerprint: str, fingerprint_short: str }),
);

// --- Conformance -----------------------------------------------------------

export const isConformanceStatus = validator<ConformanceStatus>(
  shape({
    passed: bool,
    checks: listOf(shape({ name: str, passed: bool, vectors: num, detail: str })),
    failures: listOf(str),
    capabilities: listOf(str),
    bundle_digest: str,
    bundle_digest_short: str,
    bundle_vectors: num,
    upstream_commit: str,
    upstream_commit_short: str,
    package_version: str,
    python_version: str,
    unicode_version: str,
    bundle_unicode_version: str,
    unicode_version_matches: bool,
  }),
);

// --- Read-only Technocore monitoring ---------------------------------------

export const isTechnocoreStatus = validator<TechnocoreStatus>(
  shape({
    state: enumOf("never_checked", "current", "drifted", "unavailable"),
    manifest_current: bool,
    checked_at: nullOr(str),
    last_attempt_at: nullOr(str),
    last_success_at: nullOr(str),
    reasons: listOf(str),
    sources: listOf(
      shape({
        source_id: str,
        url: str,
        authority: num,
        outcome: enumOf("ok", "fetch_error", "parse_error"),
        http_status: num,
        content_type: str,
        etag: str,
        last_modified: str,
        short_hash: str,
        byte_count: num,
        detail: str,
        rationale: str,
      }),
    ),
    fields: listOf(
      shape({
        key: str,
        label: str,
        source_id: str,
        json_path: str,
        severity: enumOf("critical", "warning"),
        expected: str,
        observed: str,
        matches: bool,
        outcome: enumOf("matched", "mismatch", "missing", "unsupported"),
        rationale: str,
        detail: str,
      }),
    ),
    critical_mismatch_count: num,
    critical_unevaluable_count: num,
    warning_count: num,
    origin: str,
  }),
);

// --- Composer --------------------------------------------------------------

export const isComposeCapability = validator<ComposeCapability>(
  shape({
    can_compose: bool,
    blocking_reasons: listOf(str),
    write_method: str,
    write_path_template: str,
    denied_rooms: listOf(str),
    room_class_markers: listOf(str),
    max_chars: num,
    min_chars: num,
    draft_ttl_seconds: num,
    approval_ttl_seconds: num,
    note_lane_available: bool,
    note_lane_detail: str,
  }),
);

export const isComposeDraft = validator<ComposeDraft>(
  shape({
    draft_id: str,
    room: str,
    room_classes: listOf(str),
    raw_text: str,
    swept_text: str,
    changed_by_sweep: bool,
    raw_chars: num,
    swept_chars: num,
    draft_digest: str,
    min_chars: num,
    max_chars: num,
    expires_in_seconds: num,
    target_notes: listOf(str),
  }),
);

export const isComposeSignature = validator<ComposeSignature>(
  shape({
    draft_id: str,
    room: str,
    did: str,
    nonce: str,
    canonical: str,
    canonical_digest: str,
    signature: str,
    changed_by_sweep: bool,
    send_token: str,
    expires_in_seconds: num,
  }),
);

export const isComposeSendResult = validator<ComposeSendResult>(
  shape({
    outcome: enumOf("accepted", "refused", "outcome_unknown"),
    room: str,
    did: str,
    nonce: str,
    canonical_digest: str,
    signature: str,
    http_status: num,
    detail: str,
    response_excerpt: str,
    reconciliation_required: bool,
  }),
);

// --- Evidence and audit ----------------------------------------------------

const captureState = enumOf(
  "line_captured",
  "line_not_found",
  "generation_changed",
  "stream_truncated",
  "parse_problem",
  "fetch_failed",
);

const chainState = enumOf("intact", "empty", "broken_link", "head_mismatch", "unavailable");

export const isEvidenceList = validator<EvidenceList>(
  shape({
    records: listOf(
      shape({
        id: str,
        reservation_id: str,
        room: str,
        did: str,
        nonce: str,
        canonical_sha256: str,
        signature: str,
        http_status: num,
        write_outcome: enumOf(
          "in_flight",
          "accepted",
          "refused",
          "outcome_unknown",
          "not_sent",
        ),
        // A record with no capture carries "", which is a state of its own.
        capture_state: (value) => value === "" || captureState(value),
        capture_detail: str,
        captured_at: nullOr(str),
        room_generation: str,
        capture_generation: str,
        generation_changed: bool,
        captured_line_offset: nullOr(num),
        captured_line_length: nullOr(num),
        stream_sha256: str,
        stream_bytes: num,
        stream_truncated: bool,
        unreadable_lines: num,
        request_sha256: str,
        response_sha256: str,
        recorded_at: str,
        external_anchor: nullOr(str),
        levels: listOf(shape({ level: num, name: str, present: bool, detail: str })),
      }),
    ),
    record_count: num,
    chain_state: chainState,
    chain_detail: str,
    chain_link_count: num,
  }),
);

export const isEvidenceCaptureResult = validator<EvidenceCaptureResult>(
  shape({
    evidence_id: str,
    state: captureState,
    detail: str,
    server_observation: bool,
    room_generation: str,
    line_offset: nullOr(num),
    line_length: nullOr(num),
    stream_sha256: str,
    scanned_bytes: num,
    stream_truncated: bool,
    read_retry_allowed: bool,
    write_retry_allowed: bool,
  }),
);

export const isAuditChainStatus = validator<AuditChainStatus>(
  shape({
    state: chainState,
    detail: str,
    link_count: num,
    head_count: nullOr(num),
    first_bad_seq: nullOr(num),
    claim: str,
  }),
);

// --- OpenCode Go connection ------------------------------------------------

export const isOpenCodeStatus = validator<OpenCodeStatus>(
  shape({
    configured: bool,
    fingerprint_short: str,
    configured_at: nullOr(str),
    updated_at: nullOr(str),
    check: shape({
      state: enumOf("not_configured", "never_checked", "key_saved_unverified"),
      reasons: listOf(str),
      detail: str,
    }),
    selected_model: str,
    auth_header_caveat: str,
    catalog: shape({
      state: enumOf("never_fetched", "ok", "fetch_error", "parse_error"),
      fetched_at: nullOr(str),
      models_fetched_at: nullOr(str),
      detail: str,
      http_status: num,
      models: listOf(
        shape({
          model_id: str,
          owned_by: str,
          selectable: bool,
          protocol: str,
          protocol_verification: enumOf("documented", "unverified"),
          reason: str,
          retention: str,
          training_use: enumOf("yes", "no", "unknown"),
          requires_training_acknowledgement: bool,
          privacy_source: str,
          privacy_read_on: str,
        }),
      ),
      model_count: num,
      selectable_count: num,
      unmapped_count: num,
      listing_caveat: str,
      table_provenance: str,
      drift_notice: str,
    }),
    spending: shape({
      budget_available: bool,
      limits: listOf(shape({ window: str, amount_usd: num, note: str })),
      limit_behaviour: str,
      use_balance: str,
      local_counter_caveat: str,
      unknown_cost_sentence: str,
    }),
    protocol_context: shape({
      protocols: listOf(str),
      streaming_supported: bool,
      // Checked for its *kind*, not its value. Pinning either of these would
      // turn a server that widened a field into a screen that refuses every
      // response - which is the mistake `tool_calls_supported` had already
      // recorded in `types.ts`, in the opposite direction: the mirror said
      // `false` while the wire said otherwise.
      tool_calls_supported: bool,
      deferral: str,
      shape_provenance: str,
      tool_call_provenance: str,
    }),
  }),
);

// --- Public-room work scan -------------------------------------------------

const workScanCapability = shape({
  module_id: str,
  module_state: str,
  module_available: bool,
  write_gate_open: bool,
  ready: bool,
  detail: str,
});

const workScanCandidate = shape({
  id: str,
  signal: str,
  source: shape({
    room: str,
    seq: num,
    ts: str,
    author: str,
    author_is_did_key: bool,
    author_detail: str,
    quote: str,
    reference: str,
    authority: num,
  }),
  benefit: str,
  deliverable: str,
  success_condition: str,
  test_method: str,
  capability: workScanCapability,
  effort: shape({ label: str, band: str, basis: str }),
  budget_state: str,
  budget_detail: str,
  permissions: listOf(str),
  risks: listOf(str),
  open_state: shape({ read_at: str, detail: str }),
  derivation: str,
});

const workScanAdapterFact = shape({
  key: str,
  detail: str,
  state: enumOf("verified", "not_verified"),
});

/**
 * The reading time and the service's own declared bound.
 *
 * One definition for the two snapshots that carry it - the room overview and
 * the discovery log - because two copies of the same shape are two things that
 * can disagree about what a staleness note is.
 */
const workScanStaleness = shape({
  read_at: str,
  declared_cache_seconds: num,
  declared_by: str,
  detail: str,
});

export const isWorkScanStatus = validator<WorkScanStatus>(
  shape({
    honesty: str,
    capability: workScanCapability,
    adapters: listOf(
      shape({
        id: str,
        name: str,
        support: str,
        authority: num,
        declared_origin: str,
        adapter_written: bool,
        contacted: bool,
        verified: listOf(workScanAdapterFact),
        unverified: listOf(workScanAdapterFact),
        self_description: str,
        self_description_source: str,
        score_self_description: str,
        score_caveat: str,
        provenance: str,
      }),
    ),
    room_index: nullOr(
      shape({
        rooms: listOf(
          shape({
            name: str,
            topic: str,
            authority: num,
            // The service's own aggregates, checked as their own list rather
            // than folded in beside `name`/`topic`: the whole point of the
            // two-field split is that a caller's string and a measurement
            // never arrive through the same door.
            measured: listOf(shape({ key: str, value: str })),
            measured_truncated: bool,
          }),
        ),
        total: num,
        kept_count: num,
        truncated: bool,
        staleness: workScanStaleness,
        sha256: str,
        room_name_caveat: str,
        topic_caveat: str,
        measured_caveat: str,
        unlisted_note: str,
        untrusted: shape({
          present: bool,
          fields: listOf(str),
          note: str,
          build_fields: listOf(str),
          extra_fields: listOf(str),
          missing_fields: listOf(str),
          detail: str,
        }),
      }),
    ),
    discovery: nullOr(
      shape({
        room: str,
        entries: listOf(
          shape({
            seq: num,
            ts: str,
            name: str,
            line: str,
            unusable_reason: str,
            selectable: bool,
            authority: num,
          }),
        ),
        since: nullOr(num),
        last_seq: num,
        first_seq: nullOr(num),
        lines_read: num,
        selectable: listOf(str),
        unusable_count: num,
        ring_drop: nullOr(
          shape({ since: num, expected_first: num, first_seq: num, detail: str }),
        ),
        staleness: workScanStaleness,
        sha256: str,
        room_name_caveat: str,
        unlisted_note: str,
        write_refusal: str,
      }),
    ),
    last_scan: nullOr(
      shape({
        started_at: str,
        completed_at: str,
        rooms: listOf(str),
        results: listOf(
          shape({
            room: str,
            candidates: listOf(workScanCandidate),
            refusals: listOf(shape({ room: str, seq: num, shape: str, detail: str })),
            lines_read: num,
          }),
        ),
        failures: listOf(shape({ room: str, reason: str, detail: str })),
        // A closed vocabulary the panel switches on when it picks a label, so
        // an unknown third kind is a malformed document rather than a room
        // note rendered under the wrong sentence.
        notes: listOf(
          shape({ room: str, kind: enumOf("unlisted", "ephemeral"), detail: str }),
        ),
        candidate_count: num,
        refusal_count: num,
      }),
    ),
    never_sent_params: listOf(str),
    polling_statement: str,
    prohibition_statement: str,
  }),
);

/**
 * The task one candidate opened, and what of it a model can read.
 *
 * `request_file` and `request_file_detail` are required rather than optional.
 * A document without them is one from a build that stored the request as a
 * digest and nothing else, and the surface would draw it as though the text
 * were there - so it is refused at the boundary instead.
 */
export const isWorkScanSuggestion = validator<WorkScanSuggestion>(
  shape({
    task_id: str,
    module_id: str,
    source_id: str,
    source_version_id: str,
    state: str,
    detail: str,
    request_file: str,
    request_file_detail: str,
  }),
);

// --- Tasks, runs and the Activity Desk -------------------------------------

const taskCheckState = enumOf("passed", "blocked", "not_implemented");

const evidenceFieldName = enumOf(
  "task_outcome",
  "test_result",
  "user_acceptance",
  "public_share",
);

const taskStateName = enumOf(
  "suggested",
  "awaiting_approval",
  "running",
  "paused",
  "blocked",
  "failed",
  "review_needed",
  "ready_to_publish",
  "published",
);

const taskStatus = shape({
  id: str,
  module_id: str,
  source_id: str,
  content_sha256: str,
  source_version_id: str,
  title: str,
  state: taskStateName,
  state_detail: str,
  created_at: str,
  updated_at: str,
  evidence_fields: listOf(
    shape({
      evidence_field: evidenceFieldName,
      state: taskCheckState,
      detail: str,
      ref_id: str,
    }),
  ),
  ready_to_publish: bool,
  blocking_fields: listOf(str),
  public_share_available: bool,
  public_share_detail: str,
  budget_available: bool,
  budget_detail: str,
});

export const isTaskStatusResponse = validator<TaskStatusResponse>(taskStatus);

export const isTaskListResponse = validator<TaskListResponse>(
  shape({
    tasks: listOf(taskStatus),
    task_count: num,
    producible_states: listOf(taskStateName),
    unproducible_states: listOf(taskStateName),
    unproducible_detail: str,
  }),
);

const toolScope = enumOf(
  "read_approved_input",
  "write_workspace",
  "deterministic_check",
  "read_run_state",
);

const toolParam = shape({
  name: str,
  type: enumOf("text", "file_name", "digest"),
  required: bool,
  detail: str,
});

/** The closed acceptance registry. A sixth member is a malformed document. */
const acceptanceKind = enumOf(
  "artifact_exists",
  "artifact_is_json",
  "artifact_has_json_keys",
  "artifact_contains",
  "artifact_digest_is",
);

/**
 * The run's verdict, checked as the closed vocabulary it became.
 *
 * It was a bare `str` while the mirror typed it as one literal. It is three
 * members now and the surface switches on all three - "the conditions held",
 * "at least one did not" and "the plan wrote none a machine could decide" get
 * three different renderings - so an unknown fourth is a document this client
 * cannot draw rather than one it draws wrongly.
 */
const testResultState = enumOf("passed", "failed", "not_implemented");

const agentRun = shape({
  id: str,
  task_id: str,
  phase: enumOf(
    "planned",
    "running",
    "paused",
    "completed",
    "cancelled",
    "tool_error",
    "budget_exhausted",
    "artifact_missing",
  ),
  created_at: str,
  started_at: nullOr(str),
  finished_at: nullOr(str),
  stop_requested: bool,
  plan_sha256: str,
  test_condition: str,
  acceptance: listOf(
    shape({ kind: acceptanceKind, label: str, satisfied: bool, detail: str }),
  ),
  test_result_state: testResultState,
  test_result_detail: str,
  expected_artifacts: listOf(str),
  steps: listOf(
    shape({
      ordinal: num,
      tool_id: str,
      scope: toolScope,
      arguments_sha256: str,
      phase: enumOf("planned", "ran", "refused", "failed", "skipped"),
      started_at: nullOr(str),
      finished_at: nullOr(str),
      artifact_name: str,
      artifact_sha256: str,
      detail: str,
    }),
  ),
  tool_calls_used: num,
  elapsed_ms: num,
  max_tool_calls: num,
  max_wall_clock_seconds: num,
  concurrency: num,
  detail: str,
});

export const isAgentSurfaceResponse = validator<AgentSurfaceResponse>(
  shape({
    execution: shape({
      arbitrary_execution_supported: bool,
      reason: str,
      detail: str,
      inventory: listOf(
        shape({
          facility: str,
          measured: enumOf("present", "absent", "not_measured"),
          measured_at: str,
          detail: str,
          relied_upon: bool,
        }),
      ),
    }),
    ceiling: shape({
      max_tool_calls: num,
      max_wall_clock_seconds: num,
      max_concurrency: num,
      units: listOf(str),
      refused_units: listOf(str),
      refused_units_detail: str,
      detail: str,
      agent_can_raise_ceiling: bool,
    }),
    tools: listOf(
      shape({
        id: str,
        scope: toolScope,
        purpose: str,
        params: listOf(toolParam),
        call_cost: num,
        produces_artifact: bool,
      }),
    ),
    acceptance_checks: listOf(
      shape({ kind: acceptanceKind, purpose: str, params: listOf(toolParam) }),
    ),
    honesty: str,
    stop_statement: str,
    interrupted_runs: listOf(agentRun),
    resumed_any: bool,
  }),
);

export const isAgentTaskRunsResponse = validator<AgentTaskRunsResponse>(
  shape({
    task: taskStatus,
    runs: listOf(agentRun),
    workspace_files: listOf(shape({ name: str, byte_count: num, sha256: str })),
    honesty: str,
  }),
);

/**
 * One model planning turn, and the run it did or did not record.
 *
 * `outcome` is an enum here because the surface renders a different finding
 * from each member - a plan waiting for approval, a model that chose to stop,
 * an answer that was cut off, a turn whose ending could not be read, a
 * proposal that named something unregistered, a session at its ceiling, and a
 * provider that failed - and a member this list does not name is a document
 * this client cannot draw.
 *
 * It says **seven** because the backend says seven. `truncated` and
 * `inconclusive` were added when a live turn came back `finish_reason:
 * "length"` and the product reported it as "the model stopped proposing
 * calls"; this list kept counting five for a while afterwards, which turned
 * every one of those answers into a `malformed` refusal at the boundary. The
 * person never saw the cut at all - the same over-claim the backend fix
 * removed, moved one layer outwards and made louder. A test drives both
 * members through this validator.
 *
 * `model_can_start_a_run` is checked for its *kind*: it is a structural
 * `false` on the wire, and pinning the value here would add a second place
 * the guarantee is written down.
 */
export const isModelProposalResponse = validator<ModelProposalResponse>(
  shape({
    outcome: enumOf(
      "planned",
      "finished",
      "truncated",
      "inconclusive",
      "refused",
      "budget_exhausted",
      "provider_failed",
    ),
    run_id: str,
    detail: str,
    model_calls_used: num,
    max_model_calls: num,
    usage_detail: str,
    closing_text: str,
    tool_call_provenance: str,
    task: taskStatus,
    runs: listOf(agentRun),
    model_can_start_a_run: bool,
  }),
);

export const isActivityListResponse = validator<ActivityListResponse>(
  shape({
    events: listOf(
      shape({
        id: str,
        recorded_at: str,
        run_id: str,
        task_id: str,
        actor: enumOf("user", "station_runner"),
        action: enumOf(
          "run_planned",
          "run_started",
          "tool_called",
          "artifact_produced",
          "check_recorded",
          "approval_awaited",
          "run_stopped",
          "run_resumed",
          "run_finished",
          "run_failed",
          "permission_denied",
          "budget_exhausted",
          "execution_unavailable",
          "activity_deleted",
          // The model planning lane's three (ADR-0012). The *actor* enum is
          // untouched: a model turn is recorded as something the station's
          // runner did, and there is still no `model` actor to write one with.
          "model_called",
          "model_plan_proposed",
          "model_session_ended",
        ),
        outcome: enumOf("ok", "refused", "failed", "pending"),
        duration_ms: num,
        artifact_sha256: str,
        check_sha256: str,
        detail: str,
        chain_referenced: bool,
      }),
    ),
    event_count: num,
    chain_referenced_count: num,
    retained_events: num,
    detail: str,
  }),
);

export const isActivityDeleteResponse = validator<ActivityDeleteResponse>(
  shape({
    deleted: num,
    kept_because_chain_referenced: num,
    recorded_in_audit_chain: bool,
    detail: str,
  }),
);

// --- The proof workspace ---------------------------------------------------

const proofWorkspace = shape({
  task: taskStatus,
  module: shape({
    id: str,
    name: str,
    purpose: str,
    state: enumOf("available", "planned"),
    available_from: str,
    owners: listOf(str),
    checks: listOf(
      shape({
        key: str,
        state: taskCheckState,
        detail: str,
        evidence_field: evidenceFieldName,
        stage: str,
        ref_id: str,
        policy_refused: bool,
      }),
    ),
    complete: bool,
    blocking_keys: listOf(str),
    not_implemented_keys: listOf(str),
  }),
  artifacts: listOf(shape({ name: str, byte_count: num, sha256: str })),
  file_count: num,
  total_bytes: num,
  artifact_set_sha256: str,
  bundle_sha256: str,
  missing: listOf(shape({ key: str, state: str, detail: str })),
  claims: listOf(shape({ key: str, state: str, detail: str })),
  formats: listOf(enumOf("json", "markdown")),
  hash_scope: str,
  bundle_scope: str,
  reproduction: str,
  approval_ttl_seconds: num,
});

export const isProofWorkspace = validator<ProofWorkspace>(proofWorkspace);

export const isProofPrepareResult = validator<ProofPrepareResult>(
  shape({ workspace: proofWorkspace, share_token: str, expires_in_seconds: num }),
);
