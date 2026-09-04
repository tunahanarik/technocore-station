"""The task service. Owns task rows; owns nothing else.

What it reuses, and what it is forbidden to build (ADR-0004 2)
--------------------------------------------------------------
Its dependencies arrive through the constructor - the ``ComposeService``
pattern - and it creates none of them. Three duplications are ruled out by
name and this module honours all three:

* **no new HTTP client.** ``OUTBOUND_CLIENT_MODULES`` is locked at three, and
  nothing in :mod:`station_api.tasks` imports an HTTP client, opens a socket
  or reaches an outbound registry. The package has no outbound surface at all.
* **no second vault or signer.** Nothing here touches key material. The
  service stores identifiers and verdicts, never bytes that were signed.
* **no second gate.** :mod:`station_api.tasks.gate` follows
  ``write_gate.evaluate``'s pure-function shape and reuses its ``CheckState``;
  the write gate itself is untouched and still runs at every composer step.

The registry is imported, not injected
--------------------------------------
``ModuleId`` and ``TaskSourceId`` come from compile-time modules. Passing them
in as data would be the first half of a plugin loader: once the set of modules
is a constructor argument, something has to produce it, and the obvious
something is a file. There is no such path (charter ADR-017).

What a task cannot do here
--------------------------
Reach ``suggested``, ``running`` or ``paused``: those need producers this
release does not have, and :func:`~station_api.tasks.states.validate_transition`
refuses them by name. Fill ``public_share``: that field belongs to Package H3
and :class:`~station_api.modules.fields.EvidenceRef` refuses to be constructed
for it. Become ``ready_to_publish`` by request: that state is derived from
three separately verified pieces of evidence, and asking for it without them
is refused.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from station_api.db.models import TaskEvidenceOutcome, TaskRecord, TaskStateTransition
from station_api.modules.completion import ModuleCompletion, evaluate_module
from station_api.modules.fields import (
    UNFILLABLE_FIELDS,
    EvidenceField,
    EvidenceFieldError,
    EvidenceRef,
)
from station_api.modules.registry import ModuleId, get_module
from station_api.tasks.gate import TaskGateInput, TaskGateStatus
from station_api.tasks.gate import evaluate as evaluate_gate
from station_api.tasks.sources import (
    TaskSourceError,
    TaskSourceId,
    content_sha256,
    source_version_id,
)
from station_api.tasks.states import (
    EVIDENCE_DERIVED_STATES,
    INITIAL_STATE,
    STATE_DETAIL,
    TaskState,
    validate_transition,
)
from station_api.technocore.projection import sweep_untrusted

#: Most tasks one listing returns. A bound on the read; nothing is pruned.
MAX_TASKS = 500

#: Longest stored title. The text is the user's own, so it is swept rather
#: than rejected: control and bidi characters become spaces and the rest is
#: kept, then bounded to what the column holds.
MAX_TITLE_CHARS = 200


class TaskError(Exception):
    """A task operation was refused. The message is safe to show a user."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class TaskView:
    """One task, as far as anything outside this service is allowed to know."""

    id: str
    module_id: str
    source_id: str
    content_sha256: str
    source_version_id: str
    title: str
    state: TaskState
    detail: str
    created_at: datetime
    updated_at: datetime
    #: At most one reference per field, and never one for ``public_share``.
    refs: tuple[EvidenceRef, ...]

    @property
    def state_detail(self) -> str:
        return STATE_DETAIL[self.state]


@dataclass(frozen=True, slots=True)
class TransitionView:
    """One accepted state change, detached from the session that read it."""

    id: str
    task_id: str
    from_state: str
    to_state: str
    recorded_at: datetime
    detail: str


def _field_columns(field: EvidenceField) -> tuple[str, str, str, str, str]:
    """The five column names of one field's group."""
    prefix = field.value
    return (
        f"{prefix}_ref_id",
        f"{prefix}_verified",
        f"{prefix}_version_id",
        f"{prefix}_detail",
        f"{prefix}_recorded_at",
    )


def _refs_from_row(row: TaskEvidenceOutcome | None) -> tuple[EvidenceRef, ...]:
    """Rebuild the references one task recorded.

    ``public_share`` is skipped structurally rather than filtered afterwards:
    :class:`EvidenceRef` refuses to be constructed for it, so a row that
    somehow carried one would raise here instead of quietly becoming a
    reference this release says cannot exist.
    """
    if row is None:
        return ()
    refs: list[EvidenceRef] = []
    for field in EvidenceField:
        if field in UNFILLABLE_FIELDS:
            continue
        ref_id_column, verified_column, version_column, detail_column, _ = (
            _field_columns(field)
        )
        ref_id = str(getattr(row, ref_id_column))
        if not ref_id:
            continue
        refs.append(
            EvidenceRef(
                field=field,
                ref_id=ref_id,
                verified=bool(getattr(row, verified_column)),
                source_version_id=str(getattr(row, version_column)),
                detail=str(getattr(row, detail_column)),
            )
        )
    return tuple(refs)


def _to_view(row: TaskRecord, outcome: TaskEvidenceOutcome | None) -> TaskView:
    return TaskView(
        id=row.id,
        module_id=row.module_id,
        source_id=row.source_id,
        content_sha256=row.content_sha256,
        source_version_id=row.source_version_id,
        title=row.title,
        state=TaskState(row.state),
        detail=row.detail,
        created_at=row.created_at,
        updated_at=row.updated_at,
        refs=_refs_from_row(outcome),
    )


class TaskService:
    """Owns task rows and their state machine. One instance per process."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    # --- creation ----------------------------------------------------------

    def open_task(
        self,
        *,
        module_id: ModuleId,
        source: TaskSourceId,
        content: bytes,
        title: str = "",
    ) -> TaskView:
        """Open one task, bound to a module and a content version.

        The task starts in ``awaiting_approval``. It deliberately does not
        start in ``suggested``: nothing in this release suggests anything, and
        a task that opened in a state no producer can reach would be the first
        lie the state machine told.
        """
        record = get_module(module_id)
        content_hash = content_sha256(content)
        try:
            version_id = source_version_id(source, content_hash)
        except TaskSourceError as exc:
            raise TaskError(str(exc), reason="source_invalid") from exc

        task_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        swept_title = sweep_untrusted(title).strip()[:MAX_TITLE_CHARS]

        with Session(self._engine) as session, session.begin():
            session.add(
                TaskRecord(
                    id=task_id,
                    module_id=record.id.value,
                    source_id=source.value,
                    content_sha256=content_hash,
                    source_version_id=version_id,
                    title=swept_title,
                    state=INITIAL_STATE.value,
                    detail=STATE_DETAIL[INITIAL_STATE],
                    created_at=now,
                    updated_at=now,
                )
            )
            # Flushed before its two children. Without a ``relationship`` the
            # unit of work orders mappers by table name, which puts
            # ``task_evidence_outcome`` ahead of ``task_record`` and trips the
            # foreign key. Declaring the ordering here is cheaper than
            # declaring relationships this layer has no other use for.
            session.flush()
            session.add(TaskEvidenceOutcome(task_id=task_id))
            session.add(
                TaskStateTransition(
                    id=uuid.uuid4().hex,
                    task_id=task_id,
                    from_state="",
                    to_state=INITIAL_STATE.value,
                    recorded_at=now,
                    detail=STATE_DETAIL[INITIAL_STATE],
                )
            )

        return self.get(task_id)

    # --- reads -------------------------------------------------------------

    def get(self, task_id: str) -> TaskView:
        with Session(self._engine) as session:
            row = session.get(TaskRecord, task_id)
            if row is None:
                raise TaskError("Gorev bulunamadi.", reason="task_missing")
            outcome = session.get(TaskEvidenceOutcome, task_id)
            return _to_view(row, outcome)

    def list_tasks(self, *, module_id: ModuleId | None = None) -> tuple[TaskView, ...]:
        with Session(self._engine) as session:
            statement = select(TaskRecord).order_by(TaskRecord.created_at.desc())
            if module_id is not None:
                statement = statement.where(TaskRecord.module_id == module_id.value)
            rows: Sequence[TaskRecord] = (
                session.execute(statement.limit(MAX_TASKS)).scalars().all()
            )
            return tuple(
                _to_view(row, session.get(TaskEvidenceOutcome, row.id)) for row in rows
            )

    def gate(self, task_id: str) -> TaskGateStatus:
        """The four verdicts for one task. A read; decides nothing on its own."""
        view = self.get(task_id)
        return evaluate_gate(
            TaskGateInput(source_version_id=view.source_version_id, refs=view.refs)
        )

    def module_completion(self, task_id: str) -> ModuleCompletion:
        """Which of the module's requirements this task's evidence satisfies."""
        view = self.get(task_id)
        return evaluate_module(
            get_module(ModuleId(view.module_id)),
            refs=view.refs,
            source_version_id=view.source_version_id,
        )

    # --- evidence ----------------------------------------------------------

    def record_evidence(
        self,
        task_id: str,
        *,
        field: EvidenceField,
        ref_id: str,
        verified: bool,
        detail: str = "",
    ) -> TaskView:
        """Record one field. One field, never four, and never a summary.

        ``verified`` has no default here either. A caller that wanted to say
        "something was produced" and let the reader assume the rest would have
        to type ``verified=False``, which is what the gate then reports.
        """
        view = self.get(task_id)
        try:
            ref = EvidenceRef(
                field=field,
                ref_id=ref_id,
                verified=verified,
                source_version_id=view.source_version_id,
                detail=sweep_untrusted(detail).strip()[:MAX_TITLE_CHARS],
            )
        except EvidenceFieldError as exc:
            raise TaskError(str(exc), reason="evidence_field_refused") from exc

        ref_column, verified_column, version_column, detail_column, recorded_column = (
            _field_columns(ref.field)
        )
        now = datetime.now(UTC)

        with Session(self._engine) as session, session.begin():
            row = session.get(TaskEvidenceOutcome, task_id)
            if row is None:  # pragma: no cover - written with the task
                raise TaskError("Gorev kanit satiri yok.", reason="task_missing")
            setattr(row, ref_column, ref.ref_id)
            setattr(row, verified_column, ref.verified)
            setattr(row, version_column, ref.source_version_id)
            setattr(row, detail_column, ref.detail)
            setattr(row, recorded_column, now)

            task = session.get(TaskRecord, task_id)
            if task is not None:
                task.updated_at = now

        return self.get(task_id)

    # --- the state machine -------------------------------------------------

    def transition(
        self, task_id: str, target: TaskState, *, detail: str = ""
    ) -> TaskView:
        """Move a task, or refuse and say why.

        Two refusals in addition to the table's own: a state no producer can
        reach is refused by name, and ``ready_to_publish`` is refused unless
        the three publication fields have each been separately verified
        against this task's content version. That is what "derived from real
        evidence" means here - the state cannot be asked for, only earned.
        """
        view = self.get(task_id)
        verdict = validate_transition(view.state, target)
        if not verdict.allowed:
            raise TaskError(verdict.detail, reason=verdict.reason)

        if target in EVIDENCE_DERIVED_STATES:
            status = evaluate_gate(
                TaskGateInput(
                    source_version_id=view.source_version_id, refs=view.refs
                )
            )
            if not status.ready_to_publish:
                raise TaskError(
                    "Gorev su alanlar kanitlanmadan yayima hazir sayilamaz: "
                    + ", ".join(status.blocking_fields)
                    + ".",
                    reason="evidence_incomplete",
                )

        now = datetime.now(UTC)
        sentence = sweep_untrusted(detail).strip()[:MAX_TITLE_CHARS] or verdict.detail

        with Session(self._engine) as session, session.begin():
            row = session.get(TaskRecord, task_id)
            if row is None:  # pragma: no cover - read one statement earlier
                raise TaskError("Gorev bulunamadi.", reason="task_missing")
            if row.state != view.state.value:  # pragma: no cover - single process
                raise TaskError(
                    "Gorev durumu bu istegin okudugu degerden farkli.",
                    reason="state_changed",
                )
            row.state = target.value
            row.detail = sentence
            row.updated_at = now
            session.add(
                TaskStateTransition(
                    id=uuid.uuid4().hex,
                    task_id=task_id,
                    from_state=view.state.value,
                    to_state=target.value,
                    recorded_at=now,
                    detail=sentence,
                )
            )

        return self.get(task_id)

    def transitions(self, task_id: str) -> tuple[TransitionView, ...]:
        """The append-only ledger of one task's accepted state changes."""
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(TaskStateTransition)
                    .where(TaskStateTransition.task_id == task_id)
                    .order_by(TaskStateTransition.recorded_at)
                )
                .scalars()
                .all()
            )
            return tuple(
                TransitionView(
                    id=row.id,
                    task_id=row.task_id,
                    from_state=row.from_state,
                    to_state=row.to_state,
                    recorded_at=row.recorded_at,
                    detail=row.detail,
                )
                for row in rows
            )


__all__ = [
    "MAX_TASKS",
    "MAX_TITLE_CHARS",
    "TaskError",
    "TaskService",
    "TaskView",
    "TransitionView",
]
