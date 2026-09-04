"""SI-219 .. SI-225 - four fields, real evidence, a versioned identity, no writes.

Four rules from ADR-0004, each with the failure it exists to prevent:

* **4.** Task success, test result, user acceptance and public sharing stay
  four fields. Public sharing is always empty in this release, and an unbuilt
  check reports ``not_implemented`` - never ``passed``. The existence of a
  result is not the success of one.
* **5.** A task is bound to ``domain_digest(task-source/v1, source_id,
  content_sha256)``. Change the content and the identity changes, so evidence
  produced for the old bytes stops matching.
* **6.** The startup scan reads. The number of requests that leave this
  process during one is zero, the ledger is byte-for-byte unchanged, and
  nothing is continued.
* **7.** There is no budget, and nothing behaves as though there were one.
"""

from __future__ import annotations

import ast
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from station_api.compose.nonce import NonceReserver
from station_api.config import Settings
from station_api.db.models import MessageNonceReservation
from station_api.digests import domain_digest
from station_api.identity.write_gate import CheckState
from station_api.modules.completion import evaluate_module
from station_api.modules.fields import (
    PUBLICATION_FIELDS,
    UNFILLABLE_FIELDS,
    EvidenceField,
    EvidenceFieldError,
    EvidenceRef,
)
from station_api.modules.registry import ModuleId, get_module
from station_api.tasks.gate import TaskGateInput
from station_api.tasks.gate import evaluate as evaluate_gate
from station_api.tasks.reconciliation import scan_unfinished_writes
from station_api.tasks.service import TaskError, TaskService, TaskView
from station_api.tasks.sources import (
    TASK_SOURCE_DOMAIN,
    TaskSourceError,
    TaskSourceId,
    content_sha256,
    source_version_id,
)
from station_api.tasks.states import TaskState
from station_api.tasks.views import BUDGET_DETAIL, to_task_status

from tests.conftest import TEST_PORT

pytestmark = pytest.mark.security

TEST_ONLY_CONTENT = b"TEST-ONLY task content, not a real work item."
TEST_ONLY_CHANGED = b"TEST-ONLY task content, edited."
TEST_ONLY_DID = "did:key:zTESTONLYnotarealdidkeyvalue"
TEST_ONLY_ROOM = "mb-station-test-only"


@pytest.fixture
def service(engine: Engine) -> TaskService:
    return TaskService(engine=engine)


def _open(service: TaskService, *, content: bytes = TEST_ONLY_CONTENT) -> TaskView:
    return service.open_task(
        module_id=ModuleId.PROJECT_ZERO,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=content,
        title="TEST-ONLY gorev",
    )


def _verify_all(service: TaskService, view: TaskView) -> TaskView:
    for index, field in enumerate(sorted(PUBLICATION_FIELDS)):
        view = service.record_evidence(
            view.id,
            field=field,
            ref_id=f"TEST-ONLY-ref-{index}",
            verified=True,
            detail="TEST-ONLY dogrulandi.",
        )
    return view


# ---------------------------------------------------------------------------
# ADR-0004 4 - four fields, never summed
# ---------------------------------------------------------------------------


def test_there_are_exactly_four_fields_and_three_decide_publication() -> None:
    assert {field.value for field in EvidenceField} == {
        "task_outcome",
        "test_result",
        "user_acceptance",
        "public_share",
    }
    assert set(PUBLICATION_FIELDS) == set(EvidenceField) - UNFILLABLE_FIELDS
    assert set(UNFILLABLE_FIELDS) == {EvidenceField.PUBLIC_SHARE}


def test_the_four_fields_are_four_column_groups_and_not_one_flag() -> None:
    """Stored the way ``EvidenceRecord`` stores its four trust levels.

    One column that meant "done" would be the whole failure in a single word,
    so each field gets its own reference, its own ``verified`` verdict, its
    own content version and its own timestamp.
    """
    from station_api.db.models import TaskEvidenceOutcome

    columns = set(TaskEvidenceOutcome.__table__.columns.keys())
    for field in EvidenceField:
        for suffix in ("ref_id", "verified", "version_id", "detail", "recorded_at"):
            assert f"{field.value}_{suffix}" in columns

    for collapsed in ("done", "success", "completed", "passed", "score"):
        assert collapsed not in columns


def test_a_public_share_reference_cannot_be_constructed_at_all() -> None:
    """Unrepresentable, not merely unwritten (ADR-0004 4).

    The field exists so the absence can be *stated*; a release that could
    build a reference for it would be a release that could fill it by
    accident.
    """
    with pytest.raises(EvidenceFieldError):
        EvidenceRef(
            field=EvidenceField.PUBLIC_SHARE,
            ref_id="TEST-ONLY",
            verified=True,
            source_version_id="v1",
        )


def test_the_service_refuses_to_record_public_share(service: TaskService) -> None:
    view = _open(service)

    with pytest.raises(TaskError) as caught:
        service.record_evidence(
            view.id,
            field=EvidenceField.PUBLIC_SHARE,
            ref_id="TEST-ONLY",
            verified=True,
        )

    assert caught.value.reason == "evidence_field_refused"


def test_public_share_is_always_not_implemented_and_never_passed(
    service: TaskService,
) -> None:
    view = _verify_all(service, _open(service))
    status = service.gate(view.id)

    share = status.check_for(EvidenceField.PUBLIC_SHARE)

    assert share.state is CheckState.NOT_IMPLEMENTED
    assert share.satisfied is False
    assert share.ref_id == ""


def test_public_share_does_not_block_a_finished_task(service: TaskService) -> None:
    """It is a different question, not a skipped check.

    Making external sharing a precondition for finishing would mean no task
    could ever be complete without publishing it, which inverts the property
    this product wants to be true.
    """
    view = _verify_all(service, _open(service))
    status = service.gate(view.id)

    assert status.ready_to_publish is True
    assert status.blocking_fields == ()
    assert status.check_for(EvidenceField.PUBLIC_SHARE).state is (
        CheckState.NOT_IMPLEMENTED
    )


def test_a_record_that_merely_exists_is_not_success(service: TaskService) -> None:
    """The rule in one test: presence is not a pass.

    "The existence of a result file is not success on its own" has precedents
    in this repository - ``test_frontend_bundle.py`` does not leave a build
    output standing alone - and here it is structural: ``verified`` has no
    default, so a caller has to say whether anything checked the thing it is
    pointing at.
    """
    view = _open(service)
    for field in sorted(PUBLICATION_FIELDS):
        view = service.record_evidence(
            view.id, field=field, ref_id="TEST-ONLY-present", verified=False
        )

    status = service.gate(view.id)

    assert status.ready_to_publish is False
    assert sorted(status.blocking_fields) == sorted(
        field.value for field in PUBLICATION_FIELDS
    )
    for field in PUBLICATION_FIELDS:
        check = status.check_for(field)
        assert check.state is CheckState.BLOCKED
        assert check.ref_id == "TEST-ONLY-present"
        assert "varligi tek basina basari degildir" in check.detail


def test_ready_to_publish_cannot_be_asked_for_without_the_evidence(
    service: TaskService,
) -> None:
    """The state is derived. Requesting it without evidence is refused."""
    view = _open(service)
    service.transition(view.id, TaskState.REVIEW_NEEDED)

    with pytest.raises(TaskError) as caught:
        service.transition(view.id, TaskState.READY_TO_PUBLISH)

    assert caught.value.reason == "evidence_incomplete"
    assert service.get(view.id).state is TaskState.REVIEW_NEEDED


def test_one_missing_field_is_enough_to_refuse(service: TaskService) -> None:
    """Three separate fields, and the conjunction is not negotiable."""
    view = _open(service)
    view = service.record_evidence(
        view.id, field=EvidenceField.TASK_OUTCOME, ref_id="TEST-ONLY", verified=True
    )
    view = service.record_evidence(
        view.id, field=EvidenceField.TEST_RESULT, ref_id="TEST-ONLY", verified=True
    )
    service.transition(view.id, TaskState.REVIEW_NEEDED)

    with pytest.raises(TaskError):
        service.transition(view.id, TaskState.READY_TO_PUBLISH)

    assert service.gate(view.id).blocking_fields == ("user_acceptance",)


def test_unimplemented_requirements_are_never_counted_as_passed(
    service: TaskService,
) -> None:
    """The module-level statement of the same rule.

    Even with every producible field verified, Proje 0 is not complete: three
    of its charter outputs have no implementation, and an unbuilt requirement
    is not a satisfied one.
    """
    view = _verify_all(service, _open(service))
    completion = service.module_completion(view.id)

    assert completion.complete is False
    assert set(completion.not_implemented_keys) == {
        "profile_note_published",
        "lobby_greeting_sent",
        "module_marked_complete",
    }
    for check in completion.checks:
        if check.state is CheckState.NOT_IMPLEMENTED:
            assert check.satisfied is False


def test_a_module_check_passes_only_on_verified_evidence() -> None:
    """The pure function, exercised directly on both sides of the rule."""
    record = get_module(ModuleId.PROJECT_ZERO)
    unverified = EvidenceRef(
        field=EvidenceField.TASK_OUTCOME,
        ref_id="TEST-ONLY",
        verified=False,
        source_version_id="v1",
    )
    verified = EvidenceRef(
        field=EvidenceField.TASK_OUTCOME,
        ref_id="TEST-ONLY",
        verified=True,
        source_version_id="v1",
    )

    blocked = evaluate_module(record, refs=(unverified,), source_version_id="v1")
    passed = evaluate_module(record, refs=(verified,), source_version_id="v1")

    assert "identity_local_only" in blocked.blocking_keys
    assert "identity_local_only" not in passed.blocking_keys


# ---------------------------------------------------------------------------
# ADR-0004 5 - deduplication and the versioned identity
# ---------------------------------------------------------------------------


def test_the_same_source_and_content_produce_the_same_identity() -> None:
    first = source_version_id(
        TaskSourceId.OPERATOR_REQUEST, content_sha256(TEST_ONLY_CONTENT)
    )
    second = source_version_id(
        TaskSourceId.OPERATOR_REQUEST, content_sha256(TEST_ONLY_CONTENT)
    )

    assert first == second


def test_changed_content_produces_a_different_identity() -> None:
    same_source = TaskSourceId.OPERATOR_REQUEST

    assert source_version_id(
        same_source, content_sha256(TEST_ONLY_CONTENT)
    ) != source_version_id(same_source, content_sha256(TEST_ONLY_CHANGED))


def test_the_same_content_from_a_different_source_is_a_different_identity() -> None:
    digest = content_sha256(TEST_ONLY_CONTENT)

    assert source_version_id(
        TaskSourceId.OPERATOR_REQUEST, digest
    ) != source_version_id(TaskSourceId.PROJECT_MODULE, digest)


def test_the_identity_is_domain_separated_and_length_prefixed() -> None:
    """A digest built for a task source can never be presented as another."""
    digest = content_sha256(TEST_ONLY_CONTENT)
    ours = source_version_id(TaskSourceId.OPERATOR_REQUEST, digest)

    assert TASK_SOURCE_DOMAIN == b"technocore-station/task-source/v1"
    assert ours == domain_digest(
        TASK_SOURCE_DOMAIN, TaskSourceId.OPERATOR_REQUEST.value, digest
    )
    assert ours != domain_digest(
        b"technocore-station/task-source/v2",
        TaskSourceId.OPERATOR_REQUEST.value,
        digest,
    )
    # Length prefixes: the split between the two fields cannot be moved.
    assert ours != domain_digest(
        TASK_SOURCE_DOMAIN, TaskSourceId.OPERATOR_REQUEST.value + digest[:1], digest[1:]
    )


def test_a_source_identifier_must_come_from_the_registry() -> None:
    """A ``StrEnum`` passes every ``isinstance(value, str)`` check, so the
    enum check is the only thing keeping a free string out of an identity."""
    with pytest.raises(TaskSourceError):
        source_version_id(
            "operator_request",  # type: ignore[arg-type]
            content_sha256(TEST_ONLY_CONTENT),
        )


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-hex",
        "AB" * 32,
        "ab" * 31,
        "ab" * 33,
        " " + "ab" * 32,
    ],
)
def test_a_malformed_content_digest_is_refused(bad: str) -> None:
    with pytest.raises(TaskSourceError):
        source_version_id(TaskSourceId.OPERATOR_REQUEST, bad)


def test_evidence_for_the_old_content_does_not_match_the_new_content(
    service: TaskService,
) -> None:
    """The point of the whole identity: old evidence is not reused.

    The task is re-opened for edited content, which gives it a new
    ``source_version_id``. The reference that satisfied the previous version
    is offered to the gate unchanged and is refused - not ignored, refused,
    with the reason shown.
    """
    original = _verify_all(service, _open(service))
    assert service.gate(original.id).ready_to_publish is True

    reopened = _open(service, content=TEST_ONLY_CHANGED)
    assert reopened.source_version_id != original.source_version_id

    stale = evaluate_gate(
        TaskGateInput(
            source_version_id=reopened.source_version_id, refs=original.refs
        )
    )

    assert stale.ready_to_publish is False
    for field in PUBLICATION_FIELDS:
        check = stale.check_for(field)
        assert check.state is CheckState.BLOCKED
        assert "baska bir icerik surumune ait" in check.detail


def test_recorded_evidence_is_bound_to_the_tasks_own_content_version(
    service: TaskService,
) -> None:
    """The service does not let a caller choose the binding."""
    view = _verify_all(service, _open(service))

    assert view.refs
    for ref in view.refs:
        assert ref.source_version_id == view.source_version_id


# ---------------------------------------------------------------------------
# ADR-0004 6 - the startup scan reads, and only reads
# ---------------------------------------------------------------------------


def _seed_unfinished(engine: Engine) -> str:
    """One send that was committed to and never settled."""
    reserver = NonceReserver(engine)
    reservation = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ONLY_ROOM)
    reserver.commit_to_send(reservation.id)
    return reservation.id


def _ledger_rows(engine: Engine) -> list[tuple[str, str, str, str]]:
    with Session(engine) as session:
        rows = session.execute(select(MessageNonceReservation)).scalars().all()
        return sorted(
            (row.id, row.state, row.outcome, row.nonce) for row in rows
        )


class _OutboundCounter:
    """Counts every attempt to leave this process, at both guarded layers."""

    def __init__(self) -> None:
        self.attempts = 0


@pytest.fixture
def outbound_counter(monkeypatch: pytest.MonkeyPatch) -> Iterator[_OutboundCounter]:
    """Wrap the layers the suite's own guard already patches.

    Counting here rather than asserting "no exception was raised" matters:
    the guard raises only for a *foreign* host, so a loopback request would
    pass it silently. This counts attempts, which is the claim being made.
    """
    counter = _OutboundCounter()
    real_sync = httpx.HTTPTransport.handle_request
    real_connect = socket.socket.connect

    def counting_request(
        self: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        counter.attempts += 1
        return real_sync(self, request)

    def counting_connect(self: socket.socket, address: Any) -> None:
        counter.attempts += 1
        real_connect(self, address)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", counting_request)
    monkeypatch.setattr(socket.socket, "connect", counting_connect)
    yield counter


def test_the_startup_scan_lists_unfinished_sends(engine: Engine) -> None:
    """The gap ADR-0004 6 found: ``in_flight`` was written and never read."""
    reservation_id = _seed_unfinished(engine)

    report = scan_unfinished_writes(engine)

    assert report.unfinished_count == 1
    assert report.unfinished[0].reservation_id == reservation_id
    assert report.unfinished[0].room == TEST_ONLY_ROOM


def test_the_startup_scan_makes_zero_outbound_requests(
    engine: Engine, outbound_counter: _OutboundCounter
) -> None:
    """The number that has to be zero, measured rather than asserted in prose."""
    _seed_unfinished(engine)

    report = scan_unfinished_writes(engine)

    assert report.unfinished_count == 1
    assert outbound_counter.attempts == 0


def test_building_the_application_makes_zero_outbound_requests(
    settings: Settings, engine: Engine, outbound_counter: _OutboundCounter
) -> None:
    """The scan runs at application build, and building still contacts nobody."""
    from station_api.app import create_app

    _seed_unfinished(engine)
    app = create_app(settings=settings, port=TEST_PORT, engine=engine, web_dist=None)

    assert app.state.task_reconciliation.unfinished_count == 1
    assert outbound_counter.attempts == 0


def test_the_startup_scan_changes_no_row(engine: Engine) -> None:
    _seed_unfinished(engine)
    before = _ledger_rows(engine)

    scan_unfinished_writes(engine)

    assert _ledger_rows(engine) == before
    assert before[0][2] == "in_flight", "the row is still unsettled afterwards"


def test_the_scan_resumes_nothing_and_says_so(engine: Engine) -> None:
    """A report, not a decision. Continuing is the user's call (ADR-0004 6)."""
    _seed_unfinished(engine)

    report = scan_unfinished_writes(engine)

    assert report.resumed_any is False
    assert "Hicbir istek gonderilmedi" in report.detail
    assert "Devam karari kullanicinindir" in report.detail


def test_an_empty_ledger_scans_to_an_empty_report(engine: Engine) -> None:
    report = scan_unfinished_writes(engine)

    assert report.unfinished == ()
    assert report.resumed_any is False


def test_a_settled_send_is_not_reported_as_unfinished(engine: Engine) -> None:
    """Only ``spent`` + ``in_flight``. A recorded outcome is not half-finished."""
    from station_api.db.models import WriteOutcomeValue

    reserver = NonceReserver(engine)
    reservation = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ONLY_ROOM)
    reserver.commit_to_send(reservation.id)
    reserver.record_outcome(
        reservation.id, outcome=WriteOutcomeValue.ACCEPTED, detail="TEST-ONLY"
    )

    assert scan_unfinished_writes(engine).unfinished == ()


def test_the_reconciliation_module_can_reach_no_write_path(
    api_source_root: Path,
) -> None:
    """Structural, beside the behavioural test.

    A scan that could call ``commit_to_send``, ``record_outcome`` or a client's
    ``send`` would be one edit away from resuming a write. It can call none of
    them: the module imports the ORM models and nothing else.
    """
    source = (
        api_source_root / "station_api" / "tasks" / "reconciliation.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for forbidden in ("send", "commit_to_send", "record_outcome", "cancel", "commit"):
        assert forbidden not in called, forbidden

    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not any("client" in name for name in imported)
    assert not any("compose" in name for name in imported)


def test_a_scan_with_no_database_is_an_empty_report_rather_than_a_crash() -> None:
    report = scan_unfinished_writes(None)

    assert report.unfinished == ()
    assert report.resumed_any is False


# ---------------------------------------------------------------------------
# ADR-0004 7 - no budget, and no pretending
# ---------------------------------------------------------------------------


def test_the_task_layer_opens_no_budget_field(api_source_root: Path) -> None:
    """No budget column, no budget attribute, no budget arithmetic.

    The requirement's budget half is deferred to G/H2 and recorded visibly
    (``docs/task-modules.md``, ``PROJECT_STATUS.md``). What must not happen is
    a field that looks like one and is never enforced.
    """
    from station_api.db.models import TaskEvidenceOutcome, TaskRecord

    for table in (TaskRecord.__table__, TaskEvidenceOutcome.__table__):
        for column in table.columns:
            for fragment in ("budget", "cost", "spend", "quota", "credit"):
                assert fragment not in column.name.lower(), f"{table.name}.{column.name}"

    # The one permitted name is the sentence that records the deferral. It is
    # a string constant and nothing reads a number out of it; anything else
    # budget-shaped would be a field pretending a budget exists.
    allowed = {"BUDGET_DETAIL"}
    offenders: list[str] = []
    for directory in ("modules", "tasks"):
        for path in (api_source_root / "station_api" / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Name)
                    and "budget" in node.id.lower()
                    and node.id not in allowed
                ):
                    offenders.append(f"{path.name}: {node.id}")
                if isinstance(node, ast.Attribute) and "budget" in node.attr.lower():
                    offenders.append(f"{path.name}: .{node.attr}")

    assert offenders == [], f"a budget-shaped identifier appeared: {offenders}"
    assert isinstance(BUDGET_DETAIL, str)


def test_the_deferred_budget_is_stated_rather_than_dropped(
    service: TaskService,
) -> None:
    """Visible, the way ``note_lane_available`` is visible on the composer."""
    view = _open(service)
    payload = to_task_status(view, service.gate(view.id))

    assert payload.budget_available is False
    assert payload.budget_detail == BUDGET_DETAIL
    assert "Paket G ve H2'ye ertelenmistir" in payload.budget_detail
    assert payload.public_share_available is False


def test_the_deferral_is_recorded_in_the_documents(repo_root: Path) -> None:
    """A deferral nobody can find is a requirement that was dropped."""
    notes = (repo_root / "docs" / "task-modules.md").read_text(encoding="utf-8")

    assert "butce" in notes.lower() or "bütçe" in notes.lower()
    assert "H2" in notes
