"""Projection from the task layer's dataclasses to the response models.

The models themselves stay in :mod:`station_api.schemas` (ADR-0004 8); this is
the pure function that fills them. It exists so the models are exercised by
the same tests that exercise the service rather than sitting unused until a
surface package arrives - an unused model is a model nobody has checked.

Nothing here computes anything. Every verdict was decided by
:mod:`station_api.tasks.gate` or :mod:`station_api.modules.completion`; this
file copies values and reads enum members' string spellings.
"""

from __future__ import annotations

from station_api.modules.completion import ModuleCompletion
from station_api.modules.fields import (
    FIELD_DETAIL,
    UNFILLABLE_FIELDS,
    EvidenceField,
)
from station_api.modules.registry import ModuleRecord
from station_api.schemas import (
    ModuleCheckStatus,
    ProjectModuleStatus,
    TaskFieldStatus,
    TaskListResponse,
    TaskReconciliationResponse,
    TaskStatusResponse,
    UnfinishedWriteStatus,
)
from station_api.tasks.gate import TaskGateStatus
from station_api.tasks.reconciliation import ReconciliationReport
from station_api.tasks.service import TaskView
from station_api.tasks.states import (
    PRODUCIBLE_STATES,
    STATE_DETAIL,
    UNPRODUCIBLE_STATES,
    TaskState,
)

#: What the unreachable-state list means now that it is empty.
#:
#: The field stays on the response and the sentence changed, rather than the
#: field being removed: a client that showed three names here last release is
#: told the set is empty, instead of being left to notice a key went away.
UNPRODUCIBLE_DETAIL = (
    "Bu surumde uretilemeyen durum yoktur: 'suggested' oneri ureticisiyle "
    "(H1), 'running' ve 'paused' deterministik arac kosucusuyla (H2) acildi. "
    "Liste bos; tanimlanacak yeni bir durum once burada reddedilmis olarak "
    "gorunur."
)

#: The budget sentence, updated by H2 and still saying the same thing about
#: **this** layer.
#:
#: ADR-0004 7 deferred the budget half of the continue decision to G and H2.
#: H2 built it - in :mod:`station_api.agent.budget`, denominated in tool
#: calls, wall-clock seconds and a concurrency of one - and deliberately
#: **not here**. The task layer still has no budget field, no budget column
#: and no budget-shaped identifier, which is what keeps SI-225 literally true
#: rather than turning it into a sentence about where the field moved; the
#: run is what carries a ceiling, and a task is not a run.
#:
#: The old wording said the half was "deferred to G and H2". Leaving that
#: after H2 shipped would have been a deferral notice for something that
#: exists, so it was rewritten (ADR-0008 4).
BUDGET_DETAIL = (
    "Gorev katmaninda butce alani yoktur ve olmayacaktir. Tavan calismanin "
    "kendisine aittir: arac cagrisi sayisi, duvar saati suresi ve "
    "eszamanlilik (=1). Token ve para birimi sayilmaz; model yolu kapali "
    "oldugu icin saglayicidan gelen bir kullanim degeri yoktur ve "
    "uydurulmaz."
)


def to_module_status(
    record: ModuleRecord, completion: ModuleCompletion
) -> ProjectModuleStatus:
    """One registry record and the verdicts for its requirements."""
    return ProjectModuleStatus(
        id=record.id.value,
        name=record.name,
        purpose=record.purpose,
        state=record.state.value,
        available_from=record.available_from,
        owners=list(record.owners),
        checks=[
            ModuleCheckStatus(
                key=check.key,
                state=check.state.value,
                detail=check.detail,
                evidence_field=check.field.value,
                stage=check.stage,
                ref_id=check.ref_id,
                policy_refused=check.policy_refused,
            )
            for check in completion.checks
        ],
        complete=completion.complete,
        blocking_keys=list(completion.blocking_keys),
        not_implemented_keys=list(completion.not_implemented_keys),
    )


def to_task_status(view: TaskView, status: TaskGateStatus) -> TaskStatusResponse:
    """One task, with its four fields reported separately."""
    return TaskStatusResponse(
        id=view.id,
        module_id=view.module_id,
        source_id=view.source_id,
        content_sha256=view.content_sha256,
        source_version_id=view.source_version_id,
        title=view.title,
        state=view.state.value,
        state_detail=view.state_detail,
        created_at=view.created_at,
        updated_at=view.updated_at,
        evidence_fields=[
            TaskFieldStatus(
                evidence_field=check.field.value,
                state=check.state.value,
                detail=check.detail,
                ref_id=check.ref_id,
            )
            for check in status.checks
        ],
        ready_to_publish=status.ready_to_publish,
        blocking_fields=list(status.blocking_fields),
        # Derived from the constant rather than written out. It was a
        # hard-coded ``False`` on the model until Package H3 made the field
        # fillable, and a second hard-coded value would have been a claim with
        # no link to the fact - the mistake ``arbitrary_execution_supported``
        # was fixed for one package earlier.
        public_share_available=EvidenceField.PUBLIC_SHARE not in UNFILLABLE_FIELDS,
        public_share_detail=FIELD_DETAIL[EvidenceField.PUBLIC_SHARE],
        budget_detail=BUDGET_DETAIL,
    )


def to_task_list(
    pairs: list[tuple[TaskView, TaskGateStatus]],
) -> TaskListResponse:
    """The listing, plus the inventory of what this release can produce."""
    return TaskListResponse(
        tasks=[to_task_status(view, status) for view, status in pairs],
        task_count=len(pairs),
        producible_states=sorted(state.value for state in PRODUCIBLE_STATES),
        unproducible_states=sorted(
            state.value for state in UNPRODUCIBLE_STATES
        ),
        unproducible_detail=UNPRODUCIBLE_DETAIL,
    )


def to_reconciliation(report: ReconciliationReport) -> TaskReconciliationResponse:
    """The read-only scan's result.

    ``resumed_any`` is **copied from the report** rather than defaulted here.
    Letting the response model's own ``Literal[False]`` default fill it in
    would have meant the field was ``False`` because this function never set
    it, which is a different - and weaker - statement than "the scan said so".
    On the report it is a property with no constructor argument, so the two
    ends of the claim now hold each other up.
    """
    return TaskReconciliationResponse(
        scanned_at=report.scanned_at,
        unfinished_count=report.unfinished_count,
        resumed_any=report.resumed_any,
        entries=[
            UnfinishedWriteStatus(
                reservation_id=entry.reservation_id,
                did=entry.did,
                room=entry.room,
                nonce=entry.nonce,
                reserved_at=entry.reserved_at,
            )
            for entry in report.unfinished
        ],
        detail=report.detail,
    )


def state_detail(state: TaskState) -> str:
    """The one sentence that describes a state, for callers outside this file."""
    return STATE_DETAIL[state]


__all__ = [
    "BUDGET_DETAIL",
    "UNPRODUCIBLE_DETAIL",
    "state_detail",
    "to_module_status",
    "to_reconciliation",
    "to_task_list",
    "to_task_status",
]
