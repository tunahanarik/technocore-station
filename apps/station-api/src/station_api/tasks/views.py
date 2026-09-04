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
from station_api.modules.fields import FIELD_DETAIL, EvidenceField
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

#: Why the three unreachable states are listed at all. Shown beside them so a
#: reader never has to discover the gap by trying to reach one.
UNPRODUCIBLE_DETAIL = (
    "Bu durumlar tanimlidir ve gecis tablosunda yer alir, fakat bu surumde "
    "hicbir kod yolu onlari uretemez: 'suggested' bir oneri ureticisi (H1), "
    "'running' ve 'paused' bir yurutucu (H2) ister. Gecis istegi reddedilir."
)

#: The budget sentence. ADR-0004 7: F opens no budget field and does not
#: behave as though one existed; the half-requirement is deferred visibly.
BUDGET_DETAIL = (
    "Bu surumde butce kavrami yoktur ve butce varmis gibi davranilmaz. "
    "Devam kararinin butce/izin yarisi Paket G ve H2'ye ertelenmistir; onay "
    "ve izin yarisi bu pakette karsilanir."
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
