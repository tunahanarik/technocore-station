"""The task gate: may this task's result be called finished?

ADR-0004 2 is explicit that there is **no second gate**. This is not one, and
the distinction is worth stating precisely: ``identity/write_gate.py`` decides
whether anything may leave this machine, and nothing here can widen that - the
composer still re-runs the write gate at all three of its steps, and no code
path in :mod:`station_api.tasks` reaches an outbound client. What this file
decides is a *local* question: whether the four fields a task records add up
to a result that may be moved to ``ready_to_publish``.

It follows the write gate's shape deliberately - a frozen input, a pure
function, a status whose ``ready_to_publish`` is derived - and reuses its
``CheckState`` rather than copying a parallel enum. Copying was the failure
mode ADR-0004 2 named: two gates that agree today and drift quietly.

Why ``public_share`` does not block
-----------------------------------
It is always ``not_implemented``, and it is deliberately **not** one of
:data:`~station_api.modules.fields.PUBLICATION_FIELDS`. Making it a
precondition would mean no task could ever be finished without publishing it
externally, which inverts the property this product wants. It is reported at
full volume instead, so a reader is never told a task is finished *and* left
to assume its proof went somewhere.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from station_api.identity.write_gate import CheckState
from station_api.modules.fields import (
    FIELD_DETAIL,
    PUBLICATION_FIELDS,
    UNFILLABLE_FIELDS,
    EvidenceField,
    EvidenceRef,
)


@dataclass(frozen=True, slots=True)
class TaskCheck:
    """One of the four fields, and what this task established for it."""

    field: EvidenceField
    state: CheckState
    detail: str
    #: The evidence consulted, or "" when none was.
    ref_id: str = ""

    @property
    def satisfied(self) -> bool:
        return self.state is CheckState.PASSED


@dataclass(frozen=True, slots=True)
class TaskGateInput:
    """Everything the gate needs. Computed by the task service."""

    #: The content version this task is bound to. Evidence carrying a
    #: different one is not this task's evidence (ADR-0004 5).
    source_version_id: str
    refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskGateStatus:
    """The four verdicts, kept apart. Never summed into one boolean."""

    checks: tuple[TaskCheck, ...]

    @property
    def ready_to_publish(self) -> bool:
        """All three publication fields passed. Derived, never stored."""
        return all(
            check.satisfied
            for check in self.checks
            if check.field in PUBLICATION_FIELDS
        )

    @property
    def blocking_fields(self) -> tuple[str, ...]:
        return tuple(
            check.field.value
            for check in self.checks
            if check.field in PUBLICATION_FIELDS and not check.satisfied
        )

    def check_for(self, field: EvidenceField) -> TaskCheck:
        for check in self.checks:
            if check.field is field:
                return check
        raise KeyError(field)  # pragma: no cover - every field is built below


def evaluate(state: TaskGateInput) -> TaskGateStatus:
    """Apply the policy. Pure function: easy to test, impossible to bypass."""
    by_field = {ref.field: ref for ref in state.refs}

    checks: list[TaskCheck] = []
    for field in EvidenceField:
        if field in UNFILLABLE_FIELDS:
            checks.append(
                TaskCheck(
                    field=field,
                    state=CheckState.NOT_IMPLEMENTED,
                    detail=FIELD_DETAIL[field],
                )
            )
            continue

        ref = by_field.get(field)
        if ref is None:
            checks.append(
                TaskCheck(
                    field=field,
                    state=CheckState.BLOCKED,
                    detail=f"{FIELD_DETAIL[field]} Henuz kanit kaydedilmedi.",
                )
            )
            continue
        if ref.source_version_id != state.source_version_id:
            checks.append(
                TaskCheck(
                    field=field,
                    state=CheckState.BLOCKED,
                    detail=(
                        "Kanit baska bir icerik surumune ait; icerik "
                        "degistiginde eski kanit eslesmez."
                    ),
                    ref_id=ref.ref_id,
                )
            )
            continue
        if not ref.verified:
            checks.append(
                TaskCheck(
                    field=field,
                    state=CheckState.BLOCKED,
                    detail=(
                        "Kanit kaydi var fakat dogrulanmadi; bir kaydin "
                        "varligi tek basina basari degildir."
                    ),
                    ref_id=ref.ref_id,
                )
            )
            continue
        checks.append(
            TaskCheck(
                field=field,
                state=CheckState.PASSED,
                detail=ref.detail or FIELD_DETAIL[field],
                ref_id=ref.ref_id,
            )
        )

    return TaskGateStatus(checks=tuple(checks))


def refs_from(pairs: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    """Latest reference per field, as a tuple the gate input accepts."""
    latest: dict[EvidenceField, EvidenceRef] = {ref.field: ref for ref in pairs}
    return tuple(latest[field] for field in EvidenceField if field in latest)


__all__ = [
    "TaskCheck",
    "TaskGateInput",
    "TaskGateStatus",
    "evaluate",
    "refs_from",
]
