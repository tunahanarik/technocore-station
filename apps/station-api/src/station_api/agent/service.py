"""The agent service: plan a run, execute registered tools, stop, report.

Package H2's centre. What it is allowed to be is narrower than the phrase
"agent runtime" usually implies, and the narrowness is the design:

* **no arbitrary execution.** Nothing here starts a process. There is no
  ``subprocess``, ``exec``, ``eval`` or ``os.system`` in this package - the
  product source has never had one - and ADR-0008 1 records the measured
  isolation inventory and why the product still refuses to rely on it.
  :mod:`station_api.agent.isolation` carries that as a *value*.
* **no model.** The provider lane stays closed (ADR-0008 2), so a "step" is
  not something a model proposed. It is an entry a person wrote, naming a
  tool from a compile-time registry, with arguments validated against that
  tool's declared parameter types.
* **no second gate, no second vault, no outbound surface.** SI-213's rule,
  carried into this package by ADR-0008 7.

The plan is written down before anything runs
----------------------------------------------
:meth:`AgentService.plan_run` records the ordered steps, the artifacts the
plan promises and the check that would establish success, and digests all
three into ``plan_sha256``. :meth:`AgentService.start_run` refuses a run
whose plan digest no longer matches what was stored, and
:meth:`AgentService.plan_run` refuses to re-plan a run that has started. So
"changing the plan cannot quietly loosen the success criterion" is a property
of the rows rather than a rule somebody remembers.

The test field stays honest
---------------------------
A plan's ``test_condition`` is **recorded, never run** - running it is
exactly the closed capability. The run therefore reports its test result as
``not_implemented`` and the runner never writes a ``test_result`` evidence
reference, so :func:`station_api.tasks.gate.evaluate` keeps blocking and the
task cannot reach ``ready_to_publish``. Code that was never run is not code
that was tested, and the product says so instead of inferring a pass from a
file having appeared.

Four endings, kept apart
------------------------
The ceiling being reached, a tool failing, the user stopping the run and a
run interrupted by a restart are four different things and produce four
different phases, four different sentences and - for three of them - a
different audit decision point. Collapsing them into "failed" is how a user
ends up unable to tell "you ran out of budget" from "your input was broken".
"""

from __future__ import annotations

import difflib
import hashlib
import json
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from station_api.agent import budget, isolation, workspace
from station_api.agent.activity import (
    ActivityAction,
    ActivityActor,
    ActivityLog,
    ActivityOutcome,
)
from station_api.agent.errors import (
    AgentError,
    RunError,
    ToolArgumentError,
    ToolRegistryError,
    WorkspaceError,
)
from station_api.agent.language import (
    RUN_HONESTY_SENTENCE,
    STOP_HONESTY_SENTENCE,
    assert_no_forbidden_claim,
    neutralise,
)
from station_api.agent.tools import (
    ToolArgument,
    ToolId,
    ToolRecord,
    argument_map,
    bind_arguments,
    resolve_tool,
)
from station_api.db.models import AgentRun, AgentRunStep
from station_api.modules.fields import EvidenceField
from station_api.strict_json import canonical_json_bytes
from station_api.tasks.service import TaskError, TaskService, TaskView
from station_api.tasks.states import TaskState
from station_api.technocore.projection import sweep_untrusted

#: Most steps one plan may carry. Smaller than the tool-call ceiling on
#: purpose: a plan longer than the ceiling could never finish, and offering
#: to record one would be offering to record a run that cannot succeed.
MAX_PLAN_STEPS = budget.CEILING.max_tool_calls

#: Most artifacts a plan may promise.
MAX_EXPECTED_ARTIFACTS = 16

#: Longest recorded success criterion.
MAX_TEST_CONDITION_CHARS = 500

#: Longest sentence stored on a run or a step.
MAX_DETAIL_CHARS = 500

#: What the run reports for its test field, always, in this release.
TEST_RESULT_STATE = "not_implemented"

TEST_RESULT_DETAIL = (
    "Test sonucu bu surumde uygulanmadi. Plan bir basari olcutu kaydeder, "
    "fakat onu kosacak yurutme kapalidir (execution_unavailable), bu yuzden "
    "kaydedilmis bir sonuc yoktur ve gorev yayima hazir sayilamaz."
)


class RunPhase(StrEnum):
    """Where a run is, and - for the endings - which ending it was."""

    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    #: Every step ran and every promised artifact is present.
    COMPLETED = "completed"
    #: The user pressed stop and did not resume.
    CANCELLED = "cancelled"
    #: A tool refused or failed. Distinct from the ceiling and from a stop.
    TOOL_ERROR = "tool_error"
    #: The ceiling was reached before the plan finished.
    BUDGET_EXHAUSTED = "budget_exhausted"
    #: Every step ran, and a promised artifact is not there. A plan that
    #: promised something it did not produce did not succeed, and saying so
    #: is the whole point of writing the promise down first.
    ARTIFACT_MISSING = "artifact_missing"


class StepPhase(StrEnum):
    """What became of one planned step."""

    PLANNED = "planned"
    RAN = "ran"
    REFUSED = "refused"
    FAILED = "failed"
    #: Never reached: the run stopped, or its result arrived after a stop and
    #: was discarded.
    SKIPPED = "skipped"


#: Run phases that are finished. Nothing continues from these.
TERMINAL_RUN_PHASES: frozenset[RunPhase] = frozenset(
    {
        RunPhase.COMPLETED,
        RunPhase.CANCELLED,
        RunPhase.TOOL_ERROR,
        RunPhase.BUDGET_EXHAUSTED,
        RunPhase.ARTIFACT_MISSING,
    }
)


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """One validated step, before it is written down."""

    tool: ToolRecord
    arguments: tuple[ToolArgument, ...]

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "arguments": argument_map(self.arguments),
                    "tool": self.tool.id.value,
                }
            )
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class RunStepView:
    """One step, detached from the session that read it."""

    ordinal: int
    tool_id: str
    scope: str
    arguments_sha256: str
    phase: StepPhase
    started_at: datetime | None
    finished_at: datetime | None
    artifact_name: str
    artifact_sha256: str
    detail: str


@dataclass(frozen=True, slots=True)
class RunView:
    """One run, as far as anything outside this service is allowed to know."""

    id: str
    task_id: str
    phase: RunPhase
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    stop_requested: bool
    plan_sha256: str
    test_condition: str
    expected_artifacts: tuple[str, ...]
    tool_calls_used: int
    elapsed_ms: int
    max_tool_calls: int
    max_wall_clock_seconds: int
    concurrency: int
    detail: str
    steps: tuple[RunStepView, ...]

    @property
    def finished(self) -> bool:
        return self.phase in TERMINAL_RUN_PHASES

    @property
    def test_result_state(self) -> str:
        """Always ``not_implemented``. A property, not a stored column.

        Storing it would invite a code path that writes something else. The
        executor that could produce a real result is the closed one, so this
        is derived from that fact rather than from a row.
        """
        return TEST_RESULT_STATE


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """What one tool call established. Never a boolean on its own."""

    detail: str
    artifact_name: str = ""
    artifact_sha256: str = ""
    #: Digest of the checker's own output, when a deterministic checker ran.
    #: This is the "recorded result" half of ADR-0008 7: a verdict a later
    #: reader can re-derive, rather than a claim the runner made.
    check_sha256: str = ""


def _clean(text: str) -> str:
    """Sweep user text, neutralise a forbidden phrase inside it, bound it."""
    return neutralise(sweep_untrusted(text)).strip()[:MAX_DETAIL_CHARS]


def _digest_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AgentService:
    """Owns runs, their steps and the workspace. One instance per process."""

    def __init__(
        self,
        *,
        engine: Engine,
        data_dir: Path,
        tasks: TaskService,
        activity: ActivityLog,
    ) -> None:
        self._engine = engine
        self._data_dir = data_dir
        self._tasks = tasks
        self._activity = activity

    # --- the surface, read-only -------------------------------------------

    @property
    def activity(self) -> ActivityLog:
        return self._activity

    def workspace_files(self, task_id: str) -> tuple[workspace.WorkspaceFile, ...]:
        """What one task's workspace holds. A read; creates nothing."""
        return workspace.list_files(
            workspace.task_workspace(self._data_dir, task_id)
        )

    def interrupted_runs(self) -> tuple[RunView, ...]:
        """Runs left in ``running`` by a restart. A read, and only a read.

        SI-224's rule, applied to this package: after a crash the plan can be
        loaded and looked at, and **nothing resumes on its own**. There is no
        startup hook that calls this and no code path that continues a run
        without a person invoking the resume route.
        """
        with Session(self._engine) as session:
            rows = session.scalars(
                select(AgentRun).where(AgentRun.phase == RunPhase.RUNNING.value)
            ).all()
            return tuple(self._to_view(session, row) for row in rows)

    # --- planning ----------------------------------------------------------

    def plan_run(
        self,
        task_id: str,
        *,
        steps: Sequence[tuple[str, dict[str, str]]],
        expected_artifacts: Sequence[str],
        test_condition: str,
    ) -> RunView:
        """Write down the whole plan, before anything runs.

        Everything is validated here rather than at execution time, which is
        what makes the recorded plan meaningful: an unregistered tool, a bad
        argument or an unacceptable artifact name is a refusal the user sees
        *while planning*, and the row that gets written is a plan that could
        in principle be carried out.

        A refusal for something outside the approved scope is recorded as
        ``permission_denied`` and the task is **not** redirected at some other
        target - ADR-0008 7 is explicit that a blocked run stops rather than
        finding itself something else to do.
        """
        task = self._task_or_refusal(task_id)
        if task.state is not TaskState.AWAITING_APPROVAL:
            raise RunError(
                "Calisma yalnizca onay bekleyen bir gorev icin planlanabilir; "
                f"bu gorev '{task.state.value}' durumunda.",
                reason="task_not_awaiting_approval",
            )
        if not steps:
            raise RunError(
                "Plan en az bir adim icermeli.", reason="plan_empty"
            )
        if len(steps) > MAX_PLAN_STEPS:
            raise RunError(
                f"Plan en cok {MAX_PLAN_STEPS} adim tasiyabilir; tavan bu "
                "sayidan fazla arac cagrisina zaten izin vermez.",
                reason="plan_too_long",
            )

        planned = tuple(self._plan_step(task_id, raw) for raw in steps)
        artifacts = self._plan_artifacts(task_id, expected_artifacts)
        condition = _clean(test_condition)[:MAX_TEST_CONDITION_CHARS]
        if not condition:
            raise RunError(
                "Plan, basarinin nasil olculecegini yazmadan kaydedilemez. "
                "Bu surumde olcut kaydedilir fakat kosulmaz.",
                reason="plan_has_no_test_condition",
            )

        run_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        digest = _plan_digest(planned, artifacts, condition)

        with Session(self._engine) as session, session.begin():
            session.add(
                AgentRun(
                    id=run_id,
                    task_id=task_id,
                    phase=RunPhase.PLANNED.value,
                    created_at=now,
                    stop_requested=False,
                    plan_sha256=digest,
                    test_condition=condition,
                    expected_artifacts=json.dumps(list(artifacts)),
                    tool_calls_used=0,
                    elapsed_ms=0,
                    max_tool_calls=budget.CEILING.max_tool_calls,
                    max_wall_clock_seconds=budget.CEILING.max_wall_clock_seconds,
                    concurrency=budget.CEILING.max_concurrency,
                    detail=budget.describe_ceiling(),
                )
            )
            session.flush()
            for ordinal, step in enumerate(planned, start=1):
                session.add(
                    AgentRunStep(
                        id=uuid.uuid4().hex,
                        run_id=run_id,
                        ordinal=ordinal,
                        tool_id=step.tool.id.value,
                        scope=step.tool.scope.value,
                        arguments_json=json.dumps(
                            argument_map(step.arguments), sort_keys=True
                        ),
                        arguments_sha256=step.digest,
                        phase=StepPhase.PLANNED.value,
                    )
                )

        # The workspace is created at plan time, restricted, so a later write
        # never has to create a directory in the middle of a run.
        workspace.ensure_workspace(self._data_dir, task_id)

        detail = (
            f"{len(planned)} adimlik plan kaydedildi. Beklenen ciktilar: "
            f"{len(artifacts)}. Basari olcutu kaydedildi ve kosulmayacak."
        )
        assert_no_forbidden_claim(detail, where="run plan detail")
        self._activity.record(
            action=ActivityAction.RUN_PLANNED,
            actor=ActivityActor.USER,
            outcome=ActivityOutcome.OK,
            run_id=run_id,
            task_id=task_id,
            detail=detail,
        )
        return self.get_run(run_id)

    def _plan_step(
        self, task_id: str, raw: tuple[str, dict[str, str]]
    ) -> PlannedStep:
        """Resolve one step, or record the right refusal and raise it.

        Two refusals, not one, and the difference is what the user is told.
        An unregistered identifier is "there is no such tool". An identifier
        that *names arbitrary execution* - ``run_shell_command``,
        ``exec_script``, anything :func:`isolation.names_arbitrary_execution`
        recognises - is a different question, and ADR-0008 1 requires it to
        get ``execution_unavailable`` with the measured reason rather than
        being folded into "unknown tool".

        That distinction is also what makes
        :attr:`~station_api.evidence.audit.AuditEventName.EXECUTION_UNAVAILABLE`
        producible. An independent review found it was not: the enum member
        and :meth:`report_execution_unavailable` existed and **nothing called
        either**, in a package whose own comment says a chain member nothing
        can record is a reader's evidence for a feature that does not exist.
        This is the code path that records it.
        """
        tool_name, arguments = raw
        try:
            record = resolve_tool(tool_name)
            bound = bind_arguments(record, arguments)
        except ToolRegistryError as exc:
            if isolation.names_arbitrary_execution(tool_name):
                self.report_execution_unavailable(task_id=task_id)
                raise ToolRegistryError(
                    isolation.EXECUTION_UNAVAILABLE_DETAIL,
                    reason=isolation.EXECUTION_UNAVAILABLE_REASON,
                ) from exc
            self._deny(
                task_id=task_id,
                detail=(
                    f"Kapsam disi arac istegi reddedildi: {exc}. Gorev baska "
                    "bir hedefe kaydirilmadi."
                ),
            )
            raise
        except ToolArgumentError as exc:
            self._deny(
                task_id=task_id,
                detail=(
                    f"Kapsam disi arac istegi reddedildi: {exc}. Gorev baska "
                    "bir hedefe kaydirilmadi."
                ),
            )
            raise
        return PlannedStep(tool=record, arguments=bound)

    def _plan_artifacts(
        self, task_id: str, names: Sequence[str]
    ) -> tuple[str, ...]:
        if len(names) > MAX_EXPECTED_ARTIFACTS:
            raise RunError(
                f"Plan en cok {MAX_EXPECTED_ARTIFACTS} cikti soz verebilir.",
                reason="plan_too_many_artifacts",
            )
        cleaned: list[str] = []
        for name in names:
            try:
                cleaned.append(workspace.safe_name(name))
            except WorkspaceError as exc:
                self._deny(
                    task_id=task_id,
                    detail=f"Kapsam disi cikti adi reddedildi: {exc}",
                )
                raise
        return tuple(dict.fromkeys(cleaned))

    # --- running -----------------------------------------------------------

    def start_run(self, run_id: str) -> RunView:
        """Move the task into ``running`` and carry the plan out.

        The task transition goes through :meth:`TaskService.transition`, which
        is the only function in this product that writes a task state
        (SI-226). This package has no state writer of its own and could not
        acquire one without failing the scan that says so.
        """
        view = self.get_run(run_id)
        if view.phase is not RunPhase.PLANNED:
            raise RunError(
                f"Calisma '{view.phase.value}' asamasinda; yalnizca "
                "planlanmis bir calisma baslatilabilir.",
                reason="run_not_planned",
            )
        self._assert_plan_intact(view)
        self._transition(view.task_id, TaskState.RUNNING, detail=RUN_HONESTY_SENTENCE)
        self._set_phase(run_id, RunPhase.RUNNING, started=True)

        detail = f"Calisma baslatildi. {RUN_HONESTY_SENTENCE}"
        assert_no_forbidden_claim(detail, where="run start detail")
        self._activity.record(
            action=ActivityAction.RUN_STARTED,
            actor=ActivityActor.USER,
            outcome=ActivityOutcome.OK,
            run_id=run_id,
            task_id=view.task_id,
            detail=detail,
        )
        return self._execute(run_id)

    def resume_run(self, run_id: str) -> RunView:
        """Continue a paused run, within the scope already approved.

        Only from ``paused``, and only because a person asked. Nothing on
        startup calls this: a run interrupted by a restart is *listed* by
        :meth:`interrupted_runs` and continues when - and only when - the
        user says so (SI-224, ADR-0008 10).
        """
        view = self.get_run(run_id)
        if view.phase is not RunPhase.PAUSED:
            raise RunError(
                f"Calisma '{view.phase.value}' asamasinda; yalnizca "
                "duraklatilmis bir calisma devam ettirilebilir.",
                reason="run_not_paused",
            )
        self._assert_plan_intact(view)
        self._clear_stop(run_id)
        self._transition(
            view.task_id,
            TaskState.RUNNING,
            detail="Kullanici onayli kapsamda devam edildi.",
        )
        self._set_phase(run_id, RunPhase.RUNNING, started=False)
        self._activity.record(
            action=ActivityAction.RUN_RESUMED,
            actor=ActivityActor.USER,
            outcome=ActivityOutcome.OK,
            run_id=run_id,
            task_id=view.task_id,
            detail="Calisma kullanicinin istegiyle kaldigi yerden surduruldu.",
        )
        return self._execute(run_id)

    def request_stop(self, run_id: str) -> RunView:
        """Set the stop flag. The runner reads it before every tool call.

        A flag rather than an interruption, because there is nothing to
        interrupt: one tool call at a time, synchronously. What "stop" means
        here is exactly :data:`STOP_HONESTY_SENTENCE` - the next call does not
        happen, and a result that arrives after the flag was set is discarded
        along with anything it wrote.
        """
        view = self.get_run(run_id)
        if view.finished:
            raise RunError(
                "Bitmis bir calisma durdurulamaz.", reason="run_finished"
            )
        with Session(self._engine) as session, session.begin():
            row = self._row(session, run_id)
            row.stop_requested = True
        self._activity.record(
            action=ActivityAction.RUN_STOPPED,
            actor=ActivityActor.USER,
            outcome=ActivityOutcome.OK,
            run_id=run_id,
            task_id=view.task_id,
            detail=STOP_HONESTY_SENTENCE,
        )
        return self.get_run(run_id)

    def _execute(self, run_id: str) -> RunView:
        """Carry out the remaining steps, one at a time, under the ceiling."""
        view = self.get_run(run_id)
        task = self._task_or_refusal(view.task_id)
        directory = workspace.ensure_workspace(self._data_dir, view.task_id)
        began = time.monotonic()
        carried_ms = view.elapsed_ms
        calls = view.tool_calls_used

        for step in view.steps:
            if step.phase is not StepPhase.PLANNED:
                continue

            elapsed_ms = carried_ms + int((time.monotonic() - began) * 1000)
            if self._stop_requested(run_id):
                self._store_usage(run_id, calls, elapsed_ms)
                return self._pause(view, "Kullanici durdurdu.")

            verdict = budget.check(
                budget.RunUsage(
                    tool_calls=calls, elapsed_seconds=elapsed_ms / 1000
                )
            )
            if not verdict.allowed:
                self._store_usage(run_id, calls, elapsed_ms)
                return self._exhaust(view, verdict.reason, verdict.detail)

            outcome, phase = self._run_step(view, step, task, directory)
            calls += 1
            elapsed_ms = carried_ms + int((time.monotonic() - began) * 1000)

            # The late-reply rule. A call that was in flight when the user
            # pressed stop must not leave anything behind, so its result is
            # discarded and any file it produced is removed. Checked *after*
            # the call, which is the only place a late reply can be seen.
            if self._stop_requested(run_id):
                self._discard(directory, outcome)
                self._store_step(
                    run_id,
                    step.ordinal,
                    StepPhase.SKIPPED,
                    ToolOutcome(
                        detail=(
                            "Iptalden sonra donen sonuc kaydedilmedi ve "
                            "urettigi dosya calisma alanindan kaldirildi."
                        )
                    ),
                )
                self._store_usage(run_id, calls, elapsed_ms)
                return self._pause(view, "Kullanici durdurdu.")

            self._store_step(run_id, step.ordinal, phase, outcome)
            self._store_usage(run_id, calls, elapsed_ms)
            self._record_step_activity(view, step, phase, outcome)

            if phase is not StepPhase.RAN:
                return self._fail(view, outcome.detail)

        return self._finish(view, directory)

    def _run_step(
        self,
        view: RunView,
        step: RunStepView,
        task: TaskView,
        directory: Path,
    ) -> tuple[ToolOutcome, StepPhase]:
        """One tool call. Returns what it established and how it ended.

        The arguments are re-resolved from the recorded plan rather than
        carried in memory, so a run resumed after a restart executes what was
        written down and not what somebody rebuilt from a request.
        """
        try:
            record = resolve_tool(step.tool_id)
            arguments = self._recorded_arguments(view.id, step, record)
        except (ToolRegistryError, ToolArgumentError) as exc:
            return ToolOutcome(detail=str(exc)), StepPhase.REFUSED

        try:
            return self._call(record, arguments, task, directory), StepPhase.RAN
        except (WorkspaceError, ToolArgumentError, ToolRegistryError) as exc:
            self._deny(task_id=view.task_id, run_id=view.id, detail=str(exc))
            return ToolOutcome(detail=str(exc)), StepPhase.REFUSED
        except OSError as exc:  # pragma: no cover - filesystem dependent
            return (
                ToolOutcome(detail=f"Arac hatasi: {type(exc).__name__}."),
                StepPhase.FAILED,
            )

    def _call(
        self,
        record: ToolRecord,
        arguments: dict[str, str],
        task: TaskView,
        directory: Path,
    ) -> ToolOutcome:
        """The tool runner. Typed tools and validated arguments; no shell.

        There is no command string anywhere on this path and no place one
        could be assembled: each branch calls a Python function with values
        that were type-checked against the tool's declared parameters.
        """
        if record.id is ToolId.READ_APPROVED_SNAPSHOT:
            report = (
                f"Onaylanmis icerik surumu: {task.source_version_id}; icerik "
                f"ozeti: {task.content_sha256}."
            )
            return ToolOutcome(detail=report, check_sha256=_digest_of_text(report))

        if record.id is ToolId.READ_WORKSPACE_FILE:
            body = workspace.read_text(directory, arguments["name"])
            return ToolOutcome(
                detail=(
                    f"'{arguments['name']}' okundu: {len(body)} karakter, "
                    f"ozet {_digest_of_text(body)[:12]}."
                ),
                check_sha256=_digest_of_text(body),
            )

        if record.id in (ToolId.WRITE_WORKSPACE_FILE, ToolId.UPDATE_WORKSPACE_FILE):
            produced = workspace.write_text(
                directory,
                arguments["name"],
                arguments["body"],
                replace_existing=record.id is ToolId.UPDATE_WORKSPACE_FILE,
            )
            return ToolOutcome(
                detail=(
                    f"'{produced.name}' uretildi: {produced.byte_count} bayt. "
                    "Uretilen dosya uygulanmadi ve calistirilmadi."
                ),
                artifact_name=produced.name,
                artifact_sha256=produced.sha256,
            )

        if record.id is ToolId.VALIDATE_JSON_FILE:
            body = workspace.read_text(directory, arguments["name"])
            try:
                json.loads(body)
            except ValueError as exc:
                report = f"'{arguments['name']}' gecerli JSON degil: {exc.args[0]}"
            else:
                report = f"'{arguments['name']}' gecerli bir JSON belgesi."
            return ToolOutcome(
                detail=_clean(report), check_sha256=_digest_of_text(report)
            )

        if record.id is ToolId.DIFF_WORKSPACE_FILES:
            left = workspace.read_text(directory, arguments["left"])
            right = workspace.read_text(directory, arguments["right"])
            diff = "\n".join(
                difflib.unified_diff(
                    left.splitlines(),
                    right.splitlines(),
                    fromfile=arguments["left"],
                    tofile=arguments["right"],
                    lineterm="",
                )
            )
            report = (
                "Iki dosya ayni."
                if not diff
                else f"Fark bulundu: {len(diff.splitlines())} satir."
            )
            return ToolOutcome(detail=report, check_sha256=_digest_of_text(diff))

        if record.id is ToolId.VERIFY_FILE_DIGEST:
            actual = workspace.digest_of(directory, arguments["name"])
            matched = actual == arguments["digest"]
            report = (
                f"'{arguments['name']}' ozeti beklenen degerle ayni."
                if matched
                else (
                    f"'{arguments['name']}' ozeti beklenen degerle ayni degil: "
                    f"{actual}"
                )
            )
            return ToolOutcome(detail=report, check_sha256=actual)

        # READ_RUN_STATUS. The only remaining member; an unregistered id
        # never reaches this function, because ``resolve_tool`` refused it.
        report = (
            f"Calisma asamasi okundu. Tavan: {budget.CEILING.max_tool_calls} "
            f"arac cagrisi, {budget.CEILING.max_wall_clock_seconds} saniye."
        )
        return ToolOutcome(detail=report, check_sha256=_digest_of_text(report))

    def _recorded_arguments(
        self, run_id: str, step: RunStepView, record: ToolRecord
    ) -> dict[str, str]:
        """Read one step's arguments back out of the plan the user approved.

        Read from the row rather than from the request that started the run,
        and re-validated and re-digested before use. Two things follow, and
        both are ADR-0008 7's:

        * a run interrupted by a restart can be **loaded** - the plan is on
          disk, not in a process that died - and continues only when a person
          resumes it;
        * a row edited underneath a run does not change what runs. The
          recomputed digest is compared against the one written at plan time,
          and a mismatch is a refusal, not a best effort.
        """
        with Session(self._engine) as session:
            row = session.scalars(
                select(AgentRunStep)
                .where(AgentRunStep.run_id == run_id)
                .where(AgentRunStep.ordinal == step.ordinal)
            ).one()
            raw = row.arguments_json

        try:
            stored = json.loads(raw)
        except ValueError as exc:
            raise ToolArgumentError(
                "Adim argumanlari okunamadi; calisma reddedildi.",
                reason="plan_arguments_unreadable",
            ) from exc
        if not isinstance(stored, dict):
            raise ToolArgumentError(
                "Adim argumanlari bir nesne degil; calisma reddedildi.",
                reason="plan_arguments_unreadable",
            )

        bound = bind_arguments(record, stored)
        if PlannedStep(tool=record, arguments=bound).digest != step.arguments_sha256:
            raise ToolArgumentError(
                "Adim argumanlari kaydedilen plandan farkli; basari olcutu "
                "sessizce gevsetilemez, bu yuzden calisma reddedildi.",
                reason="plan_arguments_changed",
            )
        return argument_map(bound)

    # --- endings -----------------------------------------------------------

    def _finish(self, view: RunView, directory: Path) -> RunView:
        """Every step ran. Were the promised artifacts actually produced?"""
        present = {item.name for item in workspace.list_files(directory)}
        missing = [name for name in view.expected_artifacts if name not in present]
        if missing:
            return self._fail(
                view,
                "Plan su ciktilari soz verdi ve uretilmedi: "
                + ", ".join(missing)
                + ". Uretilmeyen bir cikti basari sayilmaz.",
                phase=RunPhase.ARTIFACT_MISSING,
            )

        digest = _artifact_set_digest(workspace.list_files(directory))
        detail = (
            f"Plan tamamlandi: {len(view.steps)} adim, {len(present)} dosya. "
            + TEST_RESULT_DETAIL
        )
        assert_no_forbidden_claim(detail, where="run finish detail")

        self._close(view.id, RunPhase.COMPLETED, detail)
        # The task's own output is recorded as evidence; the **test** field is
        # deliberately never written, so the gate keeps blocking and the task
        # cannot reach ``ready_to_publish`` (ADR-0008 3, SI-222).
        self._record_outcome_evidence(view, digest, len(present))
        self._transition(view.task_id, TaskState.REVIEW_NEEDED, detail=detail)
        self._activity.record(
            action=ActivityAction.RUN_FINISHED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            run_id=view.id,
            task_id=view.task_id,
            artifact_sha256=digest,
            detail=detail,
        )
        self._activity.record(
            action=ActivityAction.APPROVAL_AWAITED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.PENDING,
            run_id=view.id,
            task_id=view.task_id,
            detail=(
                "Cikti incelenmeyi bekliyor. Kabul bir kisinin eylemidir; "
                "hicbir otomatik yol bu alani dolduramaz."
            ),
        )
        return self.get_run(view.id)

    def _record_outcome_evidence(
        self, view: RunView, digest: str, file_count: int
    ) -> None:
        try:
            self._tasks.record_evidence(
                view.task_id,
                field=EvidenceField.TASK_OUTCOME,
                ref_id=view.id,
                verified=True,
                detail=f"{file_count} dosya uretildi; kume ozeti {digest[:12]}.",
            )
        except TaskError:  # pragma: no cover - the task was read one call ago
            return

    def _pause(self, view: RunView, detail: str) -> RunView:
        self._close(view.id, RunPhase.PAUSED, detail, finished=False)
        self._transition(view.task_id, TaskState.PAUSED, detail=STOP_HONESTY_SENTENCE)
        return self.get_run(view.id)

    def _exhaust(self, view: RunView, reason: str, detail: str) -> RunView:
        self._close(view.id, RunPhase.BUDGET_EXHAUSTED, detail)
        self._transition(view.task_id, TaskState.BLOCKED, detail=detail)
        self._activity.record(
            action=ActivityAction.BUDGET_EXHAUSTED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.REFUSED,
            run_id=view.id,
            task_id=view.task_id,
            detail=f"{reason}: {detail}",
        )
        return self.get_run(view.id)

    def _fail(
        self, view: RunView, detail: str, *, phase: RunPhase = RunPhase.TOOL_ERROR
    ) -> RunView:
        safe = _clean(detail)
        assert_no_forbidden_claim(safe, where="run failure detail")
        self._close(view.id, phase, safe)
        self._transition(view.task_id, TaskState.BLOCKED, detail=safe)
        self._activity.record(
            action=ActivityAction.RUN_FAILED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.FAILED,
            run_id=view.id,
            task_id=view.task_id,
            detail=safe,
        )
        return self.get_run(view.id)

    def _deny(self, *, task_id: str, detail: str, run_id: str = "") -> None:
        """Record a request for something outside the approved scope.

        A decision point: it reaches the audit chain through
        ``DECISION_POINTS``. The task is not moved and not re-pointed at
        another target - ADR-0008 7 is explicit that an out-of-scope request
        is recorded, not worked around.
        """
        self._activity.record(
            action=ActivityAction.PERMISSION_DENIED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.REFUSED,
            run_id=run_id,
            task_id=task_id,
            detail=_clean(detail),
        )

    def report_execution_unavailable(self, *, task_id: str) -> str:
        """Record that arbitrary execution was asked for and is closed.

        The user-visible half of ADR-0008 1: the refusal is a reason with a
        sentence, it lands in the timeline, and it reaches the audit chain as
        a decision point rather than being a silence somebody has to infer
        from a missing button.

        Called from :meth:`_plan_step`, when a plan names a tool that reads as
        a request to run something. For a long time it was called from
        nowhere at all, which made the chain member it writes unproducible;
        that is measured in ``test_agent_runtime.py``.
        """
        verdict = isolation.execution_verdict()
        self._activity.record(
            action=ActivityAction.EXECUTION_UNAVAILABLE,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.REFUSED,
            task_id=task_id,
            detail=verdict.detail,
        )
        return verdict.reason

    # --- reads and small writes -------------------------------------------

    def get_run(self, run_id: str) -> RunView:
        with Session(self._engine) as session:
            row = session.get(AgentRun, run_id)
            if row is None:
                raise RunError("Calisma bulunamadi.", reason="run_missing")
            return self._to_view(session, row)

    def list_runs(self, task_id: str) -> tuple[RunView, ...]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(AgentRun)
                .where(AgentRun.task_id == task_id)
                .order_by(AgentRun.created_at.desc())
            ).all()
            return tuple(self._to_view(session, row) for row in rows)

    def _to_view(self, session: Session, row: AgentRun) -> RunView:
        steps = session.scalars(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == row.id)
            .order_by(AgentRunStep.ordinal)
        ).all()
        return RunView(
            id=row.id,
            task_id=row.task_id,
            phase=RunPhase(row.phase),
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            stop_requested=row.stop_requested,
            plan_sha256=row.plan_sha256,
            test_condition=row.test_condition,
            expected_artifacts=tuple(json.loads(row.expected_artifacts)),
            tool_calls_used=row.tool_calls_used,
            elapsed_ms=row.elapsed_ms,
            max_tool_calls=row.max_tool_calls,
            max_wall_clock_seconds=row.max_wall_clock_seconds,
            concurrency=row.concurrency,
            detail=row.detail,
            steps=tuple(
                RunStepView(
                    ordinal=step.ordinal,
                    tool_id=step.tool_id,
                    scope=step.scope,
                    arguments_sha256=step.arguments_sha256,
                    phase=StepPhase(step.phase),
                    started_at=step.started_at,
                    finished_at=step.finished_at,
                    artifact_name=step.artifact_name,
                    artifact_sha256=step.artifact_sha256,
                    detail=step.detail,
                )
                for step in steps
            ),
        )

    def _row(self, session: Session, run_id: str) -> AgentRun:
        row = session.get(AgentRun, run_id)
        if row is None:  # pragma: no cover - read one statement earlier
            raise RunError("Calisma bulunamadi.", reason="run_missing")
        return row

    def _task_or_refusal(self, task_id: str) -> TaskView:
        try:
            return self._tasks.get(task_id)
        except TaskError as exc:
            raise RunError(str(exc), reason=exc.reason) from exc

    def _transition(self, task_id: str, target: TaskState, *, detail: str) -> None:
        """Move the task through the one function permitted to write a state."""
        try:
            self._tasks.transition(task_id, target, detail=detail[:200])
        except TaskError as exc:
            raise RunError(str(exc), reason=exc.reason) from exc

    def _assert_plan_intact(self, view: RunView) -> None:
        """Refuse a run whose stored plan no longer digests to what it did."""
        with Session(self._engine) as session:
            steps = session.scalars(
                select(AgentRunStep)
                .where(AgentRunStep.run_id == view.id)
                .order_by(AgentRunStep.ordinal)
            ).all()
            recomputed = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "artifacts": list(view.expected_artifacts),
                        "steps": [
                            {"arguments": step.arguments_sha256, "tool": step.tool_id}
                            for step in steps
                        ],
                        "test_condition": view.test_condition,
                        "v": 1,
                    }
                )
            ).hexdigest()
        if recomputed != view.plan_sha256:
            raise RunError(
                "Kaydedilen plan degismis; basari olcutu sessizce "
                "gevsetilemez, bu yuzden calisma reddedildi.",
                reason="plan_changed",
            )

    def _stop_requested(self, run_id: str) -> bool:
        with Session(self._engine) as session:
            return bool(self._row(session, run_id).stop_requested)

    def _clear_stop(self, run_id: str) -> None:
        with Session(self._engine) as session, session.begin():
            self._row(session, run_id).stop_requested = False

    def _set_phase(self, run_id: str, phase: RunPhase, *, started: bool) -> None:
        with Session(self._engine) as session, session.begin():
            row = self._row(session, run_id)
            row.phase = phase.value
            if started:
                row.started_at = datetime.now(UTC)

    def _close(
        self, run_id: str, phase: RunPhase, detail: str, *, finished: bool = True
    ) -> None:
        with Session(self._engine) as session, session.begin():
            row = self._row(session, run_id)
            row.phase = phase.value
            row.detail = _clean(detail)
            if finished:
                row.finished_at = datetime.now(UTC)

    def _store_usage(self, run_id: str, calls: int, elapsed_ms: int) -> None:
        with Session(self._engine) as session, session.begin():
            row = self._row(session, run_id)
            row.tool_calls_used = calls
            row.elapsed_ms = elapsed_ms

    def _store_step(
        self, run_id: str, ordinal: int, phase: StepPhase, outcome: ToolOutcome
    ) -> None:
        with Session(self._engine) as session, session.begin():
            row = session.scalars(
                select(AgentRunStep)
                .where(AgentRunStep.run_id == run_id)
                .where(AgentRunStep.ordinal == ordinal)
            ).one()
            row.phase = phase.value
            row.finished_at = datetime.now(UTC)
            if row.started_at is None:
                row.started_at = row.finished_at
            row.artifact_name = outcome.artifact_name
            row.artifact_sha256 = outcome.artifact_sha256
            row.detail = _clean(outcome.detail)

    def _record_step_activity(
        self,
        view: RunView,
        step: RunStepView,
        phase: StepPhase,
        outcome: ToolOutcome,
    ) -> None:
        """Three separate moments, never one ``step_completed`` row."""
        self._activity.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=(
                ActivityOutcome.OK
                if phase is StepPhase.RAN
                else ActivityOutcome.REFUSED
            ),
            run_id=view.id,
            task_id=view.task_id,
            check_sha256=outcome.check_sha256,
            detail=f"{step.tool_id}: {outcome.detail}",
        )
        if outcome.artifact_name:
            self._activity.record(
                action=ActivityAction.ARTIFACT_PRODUCED,
                actor=ActivityActor.STATION_RUNNER,
                outcome=ActivityOutcome.OK,
                run_id=view.id,
                task_id=view.task_id,
                artifact_sha256=outcome.artifact_sha256,
                detail=f"'{outcome.artifact_name}' calisma alaninda olusturuldu.",
            )
        if outcome.check_sha256 and not outcome.artifact_name:
            self._activity.record(
                action=ActivityAction.CHECK_RECORDED,
                actor=ActivityActor.STATION_RUNNER,
                outcome=ActivityOutcome.OK,
                run_id=view.id,
                task_id=view.task_id,
                check_sha256=outcome.check_sha256,
                detail=(
                    "Deterministik dogrulayicinin sonucu kaydedildi. Bu bir "
                    "test sonucu degildir."
                ),
            )

    @staticmethod
    def _discard(directory: Path, outcome: ToolOutcome) -> None:
        """Remove what a late reply produced. Best effort, and stated as such."""
        if not outcome.artifact_name:
            return
        try:
            workspace.remove_file(directory, outcome.artifact_name)
        except WorkspaceError:  # pragma: no cover - the name passed once already
            return


def _plan_digest(
    steps: tuple[PlannedStep, ...],
    artifacts: tuple[str, ...],
    test_condition: str,
) -> str:
    """The digest a later start re-derives. Canonical JSON, as everywhere else."""
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "artifacts": list(artifacts),
                "steps": [
                    {"arguments": step.digest, "tool": step.tool.id.value}
                    for step in steps
                ],
                "test_condition": test_condition,
                "v": 1,
            }
        )
    ).hexdigest()


def _artifact_set_digest(files: tuple[workspace.WorkspaceFile, ...]) -> str:
    """One digest over the whole produced set, so a review has a single anchor."""
    return hashlib.sha256(
        canonical_json_bytes(
            {"files": [{"name": item.name, "sha256": item.sha256} for item in files]}
        )
    ).hexdigest()


__all__ = [
    "MAX_EXPECTED_ARTIFACTS",
    "MAX_PLAN_STEPS",
    "TERMINAL_RUN_PHASES",
    "TEST_RESULT_DETAIL",
    "TEST_RESULT_STATE",
    "AgentError",
    "AgentService",
    "PlannedStep",
    "RunPhase",
    "RunStepView",
    "RunView",
    "StepPhase",
    "ToolOutcome",
]
