"""The task service. Owns task rows; owns nothing else.

What it reuses, and what it is forbidden to build (ADR-0004 2)
--------------------------------------------------------------
Its dependencies arrive through the constructor - the ``ComposeService``
pattern - and it creates none of them. Three duplications are ruled out by
name and this module honours all three:

* **no new HTTP client.** Nothing in :mod:`station_api.tasks` imports an HTTP
  client, opens a socket or reaches an outbound registry; the package has no
  outbound surface at all. (``OUTBOUND_CLIENT_MODULES`` was locked at three
  when this was written; Package G opened a fourth for the OpenCode
  connection and Package H1 a fifth for the work scan, so the count today is
  **five**. Each was opened deliberately, in its own package, and none of
  them from here.)
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

Two producers, and why the second one exists
--------------------------------------------
:meth:`TaskService.open_task` opens work the user described.
:meth:`TaskService.suggest_task` opens work a public-room scan proposed, born
in ``suggested``. They are separate methods rather than one method with a
flag, and each refuses the other's sources, so a scanned candidate cannot be
presented as an operator request and an operator request cannot be dressed up
as a finding (ADR-0007 7). Both delegate the row write to one private helper,
which is the only place a starting state is chosen.

What a task cannot do here
--------------------------
Reach ``running`` or ``paused`` **by request**: those belong to the runner in
:mod:`station_api.agent.service`, which records a plan, its promised
artifacts and its success criterion before it moves a task into ``running``.
:data:`~station_api.schemas.TaskUserTransitionName` omits both, so the route
refuses them before this service is entered. (This paragraph used to say the
two states "need an executor this release does not have" and that
``validate_transition`` refuses them by name. Package H2 wrote the executor:
:data:`~station_api.tasks.states.UNPRODUCIBLE_STATES` is empty today and that
function refuses nothing by name. The gate on those two states is now a
closed transition set on the surface, not an unproducible state.) Fill
``public_share`` **with a string somebody typed**: this paragraph used to say
the field could not be filled at all, and Package H3 changed that fact rather
than the sentence. The field is fillable now, and it is fillable only with the
identity of an evidence record that exists in this database - the constructor
checks the shape and :meth:`TaskService.record_evidence` checks the row
(ADR-0009 1). Become ``ready_to_publish`` by request: that state is derived
from three separately verified pieces of evidence, and asking for it without
them is refused.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from station_api.db.models import (
    AppMetadata,
    EvidenceRecord,
    TaskEvidenceOutcome,
    TaskRecord,
    TaskStateTransition,
)
from station_api.modules.completion import ModuleCompletion, evaluate_module
from station_api.modules.fields import (
    UNFILLABLE_FIELDS,
    EvidenceField,
    EvidenceFieldError,
    EvidenceRef,
)
from station_api.modules.registry import (
    ModuleId,
    ModuleRecord,
    ModuleRegistryError,
    get_module,
)
from station_api.tasks.gate import TaskGateInput, TaskGateStatus
from station_api.tasks.gate import evaluate as evaluate_gate
from station_api.tasks.sources import (
    SCAN_SOURCES,
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

#: Longest stored evidence pointer, and the width of every ``*_ref_id`` column.
#:
#: A pointer is not prose, but it is still a *caller-supplied string* that
#: reaches a stored row and, from there, ``TaskFieldStatus.ref_id``. It was the
#: one caller-supplied string on this surface that was neither swept nor
#: bounded: a bidi override, a NUL or a 406-character value went through
#: untouched, because SQLite does not enforce ``String(64)``. It is now swept
#: and bounded exactly like ``title`` and ``detail`` (F-6). There is no HTTP
#: route yet; H1/H2 inherit this surface, which is why it is closed now.
MAX_REF_ID_CHARS = 64


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
    #: At most one reference per field. ``public_share`` may be among them
    #: since Package H3, and only when it names an archived send.
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

    A field in :data:`UNFILLABLE_FIELDS` is skipped **before its columns are
    read**, so a row written straight into the database under a closed field
    is passed by rather than surfaced or raised over. Silence is the safe side
    there: nothing the release says is impossible becomes a reference.

    That set is empty since Package H3, so today the loop reads all four
    fields and ``public_share`` comes back like the rest - which is right,
    because the value in that column can no longer be arbitrary. It went
    through :class:`EvidenceRef`, whose constructor refuses anything that is
    not an evidence-record identity, and through
    :meth:`TaskService.record_evidence`, which refuses an identity with no row
    behind it.

    A column group that **cannot** form a valid reference is skipped for the
    same reason a closed field is: silence, not a raised exception. This half
    is new and it is not decoration. While ``public_share`` was unfillable the
    field was skipped before its columns were read, so a hand-edited row could
    not reach the constructor at all; opening the field pointed that path
    straight at a constructor that raises, and a task carrying one edited row
    would have failed *every* read of itself - a listing included - with an
    unhandled error. A direct database edit stays outside this product's
    threat model, and the answer to one is still to pass it by rather than to
    stop working.

    The closed-field skip stays because the *mechanism* is what a later closed
    field would need, and it is driven under a temporarily closed field rather
    than left unexecuted (ADR-0009 2).
    """
    if row is None:
        return ()
    refs: list[EvidenceRef] = []
    for field in EvidenceField:
        if field in UNFILLABLE_FIELDS:
            continue
        ref_id_column, verified_column, version_column, detail_column, _ = _field_columns(field)
        ref_id = str(getattr(row, ref_id_column))
        if not ref_id:
            continue
        try:
            refs.append(
                EvidenceRef(
                    field=field,
                    ref_id=ref_id,
                    verified=bool(getattr(row, verified_column)),
                    source_version_id=str(getattr(row, version_column)),
                    detail=str(getattr(row, detail_column)),
                )
            )
        except EvidenceFieldError:
            continue
    return tuple(refs)


def _module_or_refusal(module_id: ModuleId) -> ModuleRecord:
    """Look a module up, or refuse the way every other bad input is refused.

    ``open_task`` answered an invalid *source* with ``TaskError`` and an
    invalid *module* with a bare ``KeyError`` out of the registry (F-11). Two
    inputs of the same class, one shown refusal and one armoured 500: whichever
    surface H1 puts in front of this would have had to learn the difference by
    hitting it. Both are ``TaskError`` with a reason now.
    """
    try:
        return get_module(module_id)
    except ModuleRegistryError as exc:
        raise TaskError(str(exc), reason="module_unknown") from exc


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
        self._output_revision: Callable[[str], str] | None = None

    def bind_output_reader(self, reader: Callable[[str], str]) -> None:
        """The workspace owner supplies a read-only revision, never a verdict."""
        self._output_revision = reader

    def _current_refs(self, session: Session, view: TaskView) -> TaskView:
        if self._output_revision is None or not view.refs:
            return view
        revision = self._output_revision(view.id)
        if not revision:
            return view
        refs = []
        for ref in view.refs:
            if ref.field is not EvidenceField.PUBLIC_SHARE:
                binding = session.get(AppMetadata, f"output.{view.id}.{ref.field.value}")
                if binding is None or binding.value != revision:
                    ref = replace(
                        ref,
                        verified=False,
                        detail="Cikti veya plan surumu degisti; yeniden dogrulama gerekiyor.",
                    )
            refs.append(ref)
        return replace(view, refs=tuple(refs))

    # --- creation ----------------------------------------------------------

    def open_task(
        self,
        *,
        module_id: ModuleId,
        source: TaskSourceId,
        content: bytes,
        title: str = "",
    ) -> TaskView:
        """Open one task the user described, bound to a module and a version.

        The task starts in ``awaiting_approval``, and it starts there even now
        that ``suggested`` is producible. A scanned candidate has its own
        producer, :meth:`suggest_task`, and a source this method **refuses**:
        the two ways a task can come into existence are distinguishable by the
        row alone, not only by a column a view might forget to read
        (ADR-0007 7).
        """
        if source in SCAN_SOURCES:
            raise TaskError(
                "Bu kaynak yalnizca tarama ureticisiyle acilabilir; "
                "kullanicinin kendi yazdigi bir gorev bu kaynagi tasiyamaz.",
                reason="source_needs_the_scan_producer",
            )
        return self._create(
            module_id=module_id,
            source=source,
            content=content,
            title=title,
            state=INITIAL_STATE,
        )

    def suggest_task(
        self,
        *,
        module_id: ModuleId,
        source: TaskSourceId,
        content: bytes,
        title: str = "",
    ) -> TaskView:
        """Open one task a scan proposed. Born ``suggested``, never approved.

        The second producer, and the one ``tasks/states.py`` said Package H1
        would write. It differs from :meth:`open_task` in exactly two places
        and both are deliberate: the source must be one of
        :data:`~station_api.tasks.sources.SCAN_SOURCES`, and the row is born
        in ``suggested`` rather than ``awaiting_approval``.

        What it does **not** do is approve anything. ``suggested`` walks to
        ``awaiting_approval`` through :meth:`transition`, which is the user's
        action; nothing here shortens that path, so a scan cannot open work
        for itself and wave it through (ADR-0007 8).
        """
        if source not in SCAN_SOURCES:
            raise TaskError(
                "Oneri ureticisi yalnizca tarama kaynaklarini kabul eder; "
                "kullanicinin kendi istegi bir oneri olarak acilamaz.",
                reason="source_is_not_a_scan_source",
            )
        return self._create(
            module_id=module_id,
            source=source,
            content=content,
            title=title,
            state=TaskState.SUGGESTED,
        )

    def _create(
        self,
        *,
        module_id: ModuleId,
        source: TaskSourceId,
        content: bytes,
        title: str,
        state: TaskState,
    ) -> TaskView:
        """The row write both producers share. Private, so it takes a state.

        ``state`` is a parameter here and nowhere else. Neither public
        producer lets a caller choose it, which is what keeps "who decides the
        starting state" a question with two answers written in this file
        rather than an argument any caller can supply.
        """
        record = _module_or_refusal(module_id)
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
                    state=state.value,
                    detail=STATE_DETAIL[state],
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
                    to_state=state.value,
                    recorded_at=now,
                    detail=STATE_DETAIL[state],
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
            return self._current_refs(session, _to_view(row, outcome))

    def list_tasks(self, *, module_id: ModuleId | None = None) -> tuple[TaskView, ...]:
        with Session(self._engine) as session:
            statement = select(TaskRecord).order_by(TaskRecord.created_at.desc())
            if module_id is not None:
                statement = statement.where(TaskRecord.module_id == module_id.value)
            rows: Sequence[TaskRecord] = session.execute(statement.limit(MAX_TASKS)).scalars().all()
            return tuple(
                self._current_refs(session, _to_view(row, session.get(TaskEvidenceOutcome, row.id)))
                for row in rows
            )

    def gate(self, task_id: str) -> TaskGateStatus:
        """The four verdicts for one task. A read; decides nothing on its own."""
        view = self.get(task_id)
        return evaluate_gate(
            TaskGateInput(source_version_id=view.source_version_id, refs=view.refs)
        )

    def module_completion(self, task_id: str) -> ModuleCompletion:
        """Which of the module's requirements this task's evidence satisfies.

        A stored ``module_id`` that no longer resolves is refused the same way
        an unknown one passed to ``open_task`` is. ``ModuleId(...)`` raises
        ``ValueError`` for a value outside the enum and ``get_module`` raises
        for one inside it that was dropped from the registry; both are the same
        situation to a reader, so both get the same reason.
        """
        view = self.get(task_id)
        try:
            module_id = ModuleId(view.module_id)
        except ValueError as exc:
            raise TaskError(
                "Bu gorev kayitli olmayan bir modul kimligi tasiyor.",
                reason="module_unknown",
            ) from exc
        return evaluate_module(
            _module_or_refusal(module_id),
            refs=view.refs,
            source_version_id=view.source_version_id,
        )

    # --- evidence ----------------------------------------------------------

    def invalidate_output_evidence(self, task_id: str) -> None:
        """Retain old references for history, but revoke their current validity."""
        with Session(self._engine) as session, session.begin():
            row = session.get(TaskEvidenceOutcome, task_id)
            if row is None:
                raise TaskError("Gorev bulunamadi.", reason="task_missing")
            for field in (
                EvidenceField.TASK_OUTCOME,
                EvidenceField.TEST_RESULT,
                EvidenceField.USER_ACCEPTANCE,
            ):
                _, verified_column, _, _, _ = _field_columns(field)
                setattr(row, verified_column, False)

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

        ``ref_id`` is swept and bounded the same way ``detail`` is. A pointer
        that swept down to nothing is refused rather than stored: an empty
        pointer would be a reference to nowhere wearing a reference's shape.

        ``public_share`` gets a second refusal that no other field gets. The
        constructor has already required the pointer to *look* like an
        evidence-record identity; this requires the row to actually be there
        (ADR-0009 1). The two are separate on purpose: the shape check runs
        everywhere an :class:`EvidenceRef` is built, including where no
        database is at hand, and the existence check is the half that makes
        "a send that actually happened" a fact about this machine rather than
        about a string's spelling.
        """
        view = self.get(task_id)
        try:
            ref = EvidenceRef(
                field=field,
                ref_id=sweep_untrusted(ref_id).strip()[:MAX_REF_ID_CHARS].strip(),
                verified=verified,
                source_version_id=view.source_version_id,
                detail=sweep_untrusted(detail).strip()[:MAX_TITLE_CHARS],
            )
        except EvidenceFieldError as exc:
            raise TaskError(str(exc), reason="evidence_field_refused") from exc

        if ref.field is EvidenceField.PUBLIC_SHARE:
            self._assert_evidence_record_exists(ref.ref_id)

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
            if self._output_revision is not None and field is not EvidenceField.PUBLIC_SHARE:
                session.merge(
                    AppMetadata(
                        key=f"output.{task_id}.{field.value}",
                        value=self._output_revision(task_id),
                        updated_at=now,
                    )
                )

            task = session.get(TaskRecord, task_id)
            if task is not None:
                task.updated_at = now

        return self.get(task_id)

    def _assert_evidence_record_exists(self, evidence_id: str) -> None:
        """Refuse a public-share pointer that names no archived send.

        One ``SELECT`` against the archive's primary key. The task layer reads
        that table and writes nothing to it - it does not import
        :mod:`station_api.evidence`, does not build an
        :class:`~station_api.evidence.service.EvidenceService` and does not
        touch the audit chain - so this adds no second owner for the archive,
        only a lookup (ADR-0004 2, ADR-0009 1).

        The refusal names no id back to the caller. There is one user on this
        machine, so it is not a disclosure boundary; it is the same rule every
        other refusal here follows - a sentence a person can act on, with no
        value echoed into it.
        """
        with Session(self._engine) as session:
            if session.get(EvidenceRecord, evidence_id) is None:
                raise TaskError(
                    "Bu kimlikle arsivlenmis bir gonderim yok. Dis paylasim "
                    "yalnizca gerceklesmis bir gonderimin kanit kaydina "
                    "baglanabilir.",
                    reason="evidence_record_missing",
                )

    # --- the state machine -------------------------------------------------

    def transition(self, task_id: str, target: TaskState, *, detail: str = "") -> TaskView:
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
                TaskGateInput(source_version_id=view.source_version_id, refs=view.refs)
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
    "MAX_REF_ID_CHARS",
    "MAX_TASKS",
    "MAX_TITLE_CHARS",
    "TaskError",
    "TaskService",
    "TaskView",
    "TransitionView",
]
