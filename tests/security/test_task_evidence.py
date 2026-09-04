"""SI-219 .. SI-225, SI-227 .. SI-229, SI-231 - four fields, real evidence,
a versioned identity, no writes.

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
import inspect
import socket
from collections.abc import Iterator
from dataclasses import fields
from datetime import UTC, datetime
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
from station_api.modules.registry import ModuleId, ModuleRegistryError, get_module
from station_api.tasks.gate import TaskGateInput, TaskGateStatus
from station_api.tasks.gate import evaluate as evaluate_gate
from station_api.tasks.reconciliation import (
    ReconciliationReport,
    scan_unfinished_writes,
)
from station_api.tasks.service import (
    MAX_REF_ID_CHARS,
    TaskError,
    TaskService,
    TaskView,
)
from station_api.tasks.sources import (
    TASK_SOURCE_DOMAIN,
    TaskSourceError,
    TaskSourceId,
    content_sha256,
    source_version_id,
)
from station_api.tasks.states import TaskState
from station_api.tasks.views import BUDGET_DETAIL, to_reconciliation, to_task_status

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


def test_an_evidence_pointer_is_swept_and_bounded_like_every_other_string(
    service: TaskService,
) -> None:
    """SI-227 (F-6). ``ref_id`` was the one caller string that went in raw.

    ``detail`` and ``title`` were swept and cut at 200; ``ref_id`` went
    untouched into the row and out again through ``TaskFieldStatus.ref_id``, so
    a right-to-left override, a NUL and a 406-character value all survived -
    ``String(64)`` is not enforced by SQLite. There is no route in front of
    this yet, which is exactly why it is closed before H1/H2 inherit it.
    """
    # A right-to-left override, a NUL and 406 characters, in one value.
    hostile = "TEST-ONLY\u202eref\x00" + "A" * 406
    assert len(hostile) > MAX_REF_ID_CHARS

    view = service.record_evidence(
        _open(service).id,
        field=EvidenceField.TASK_OUTCOME,
        ref_id=hostile,
        verified=True,
    )

    stored = view.refs[0].ref_id
    assert "\u202e" not in stored
    assert "\x00" not in stored
    assert stored.startswith("TEST-ONLY")
    assert len(stored) <= MAX_REF_ID_CHARS
    # And the swept value is what the response model would carry.
    payload = to_task_status(view, service.gate(view.id))
    outcome = next(
        field
        for field in payload.evidence_fields
        if field.evidence_field == "task_outcome"
    )
    assert outcome.ref_id == stored


def test_a_pointer_that_sweeps_down_to_nothing_is_refused(
    service: TaskService,
) -> None:
    """An empty pointer is a reference to nowhere wearing a reference's shape."""
    view = _open(service)

    with pytest.raises(TaskError) as caught:
        service.record_evidence(
            view.id,
            field=EvidenceField.TASK_OUTCOME,
            ref_id="\u200b  \u202e",
            verified=True,
        )

    assert caught.value.reason == "evidence_field_refused"
    assert service.get(view.id).refs == ()


def test_a_public_share_row_written_directly_is_passed_by(
    service: TaskService, engine: Engine
) -> None:
    """What ``_refs_from_row`` actually does with a column nothing writes (F-4).

    The docstring used to say such a row "would raise here". It would not: the
    field is skipped before its columns are read, so the row is passed by. The
    behaviour is the safe one - no reference this release calls impossible is
    ever built - and the sentence now says that instead of a louder thing that
    was not true.
    """
    from station_api.db.models import TaskEvidenceOutcome

    view = _open(service)
    with Session(engine) as session, session.begin():
        row = session.get(TaskEvidenceOutcome, view.id)
        assert row is not None
        row.public_share_ref_id = "TEST-ONLY-written-behind-the-service"
        row.public_share_verified = True
        row.public_share_version_id = view.source_version_id

    after = service.get(view.id)

    assert after.refs == ()
    assert [ref.field for ref in after.refs] == []
    # The gate is unmoved: the field is not implemented whatever the row holds.
    assert service.gate(view.id).check_for(EvidenceField.PUBLIC_SHARE).state is (
        CheckState.NOT_IMPLEMENTED
    )
    assert service.gate(view.id).ready_to_publish is False


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


def test_an_empty_gate_status_is_not_ready_to_publish() -> None:
    """The vacuous-truth hole, closed at the dataclass (F-9).

    ``evaluate`` never returns an empty status, but the type did not stop one
    being built, and ``ready_to_publish`` was an ``all()`` over the checks that
    happened to be present - so a status with no checks answered ``True``. Of
    all the properties in this product, that is the worst one to have a
    default of "yes". It now asks whether the three publication fields are
    each *present and passed*, so absence blocks exactly like failure.
    """
    empty = TaskGateStatus(checks=())

    assert empty.ready_to_publish is False
    assert empty.blocking_fields == (
        "task_outcome",
        "test_result",
        "user_acceptance",
    )


def test_a_gate_status_missing_one_field_entirely_still_blocks() -> None:
    """Not only the empty case: a partial status is partial, not finished."""
    full = evaluate_gate(
        TaskGateInput(
            source_version_id="v1",
            refs=tuple(
                EvidenceRef(
                    field=field,
                    ref_id="TEST-ONLY",
                    verified=True,
                    source_version_id="v1",
                )
                for field in sorted(PUBLICATION_FIELDS)
            ),
        )
    )
    assert full.ready_to_publish is True

    dropped = TaskGateStatus(
        checks=tuple(
            check
            for check in full.checks
            if check.field is not EvidenceField.USER_ACCEPTANCE
        )
    )

    assert dropped.ready_to_publish is False
    assert dropped.blocking_fields == ("user_acceptance",)


def test_a_module_check_refuses_evidence_bound_to_another_content_version() -> None:
    """``completion.py``'s stale-evidence branch, driven directly (F-3).

    ``tasks/gate.py`` had this covered and ``modules/completion.py`` did not:
    turning its version comparison into ``if False`` broke no test, because
    every case that reached it also had ``verified`` false or the same version.
    Here the reference is verified and bound to *another* version, so the
    version check is the only thing that can block it - and if it stopped
    checking, the requirement would report ``passed``.
    """
    record = get_module(ModuleId.PROJECT_ZERO)
    stale = EvidenceRef(
        field=EvidenceField.TASK_OUTCOME,
        ref_id="TEST-ONLY-stale",
        verified=True,
        source_version_id="TEST-ONLY-old-version",
        detail="TEST-ONLY eski surum icin uretildi.",
    )

    completion = evaluate_module(
        record, refs=(stale,), source_version_id="TEST-ONLY-new-version"
    )
    check = next(
        item for item in completion.checks if item.key == "identity_local_only"
    )

    assert check.state is CheckState.BLOCKED
    assert check.satisfied is False
    assert "identity_local_only" in completion.blocking_keys
    assert "baska bir icerik surumune ait" in check.detail
    # The pointer is still shown: a reader is told *which* evidence went stale.
    assert check.ref_id == "TEST-ONLY-stale"


def test_the_same_reference_passes_once_its_version_matches() -> None:
    """The other side of the same branch, so the test cannot pass vacuously."""
    record = get_module(ModuleId.PROJECT_ZERO)
    ref = EvidenceRef(
        field=EvidenceField.TASK_OUTCOME,
        ref_id="TEST-ONLY-stale",
        verified=True,
        source_version_id="TEST-ONLY-old-version",
    )

    completion = evaluate_module(
        record, refs=(ref,), source_version_id="TEST-ONLY-old-version"
    )
    check = next(
        item for item in completion.checks if item.key == "identity_local_only"
    )

    assert check.state is CheckState.PASSED


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


def test_an_unregistered_module_is_a_shown_refusal_and_not_a_bare_key_error(
    service: TaskService,
) -> None:
    """SI-231 (F-11). One class of bad input, one class of refusal.

    ``open_task`` refused an invalid *source* with ``TaskError`` and let an
    invalid *module* out as a bare ``KeyError`` from the registry dictionary.
    Same kind of mistake by the caller, two different fates: one shown, one an
    armoured 500 for whatever surface H1 puts in front of this.
    """
    with pytest.raises(TaskError) as unknown_module:
        service.open_task(
            module_id="billing",  # type: ignore[arg-type]
            source=TaskSourceId.OPERATOR_REQUEST,
            content=TEST_ONLY_CONTENT,
        )

    with pytest.raises(TaskError) as unknown_source:
        service.open_task(
            module_id=ModuleId.PROJECT_ZERO,
            source="operator_request",  # type: ignore[arg-type]
            content=TEST_ONLY_CONTENT,
        )

    assert unknown_module.value.reason == "module_unknown"
    assert unknown_source.value.reason == "source_invalid"
    # The sentence is safe to show: no path, no registry contents, no repr.
    message = str(unknown_module.value)
    assert message.startswith("Kayitli olmayan")
    assert "'" not in message and "billing" not in message


def test_the_registry_still_raises_a_key_error_for_an_unknown_identifier() -> None:
    """The named error is a ``KeyError``, so the older assertion still holds.

    ``get_module`` is a mapping lookup and reads like one; widening its type
    would have made ``test_an_unregistered_module_cannot_be_looked_up`` a
    weaker test. ``ModuleRegistryError`` subclasses ``KeyError`` instead, so
    the refusal gained a name without any assertion losing one.
    """
    assert issubclass(ModuleRegistryError, KeyError)

    with pytest.raises(ModuleRegistryError):
        get_module("billing")  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        get_module("billing")  # type: ignore[arg-type]


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


def test_resumed_any_cannot_be_constructed_as_true(engine: Engine) -> None:
    """SI-229 (F-5). "Structurally False" now means what it says.

    It was a dataclass field with a ``False`` default, so it was only a
    default: ``ReconciliationReport(..., resumed_any=True)`` constructed fine,
    and the ``Literal[False]`` that made the claim true lived on the Pydantic
    model, one layer away. It is a read-only property now - there is no
    constructor argument left to set.
    """
    with pytest.raises(TypeError):
        ReconciliationReport(
            scanned_at=datetime.now(UTC),
            unfinished=(),
            detail="TEST-ONLY",
            resumed_any=True,  # type: ignore[call-arg]
        )

    assert "resumed_any" not in {field.name for field in fields(ReconciliationReport)}


def test_the_projection_reads_resumed_any_rather_than_defaulting_it(
    engine: Engine,
) -> None:
    """The response says ``False`` because the scan said so, not by omission.

    ``to_reconciliation`` never mentioned ``resumed_any``; the model's own
    default filled it in. That is a weaker statement than the document made,
    and the two ends now hold each other up.
    """
    _seed_unfinished(engine)
    report = scan_unfinished_writes(engine)

    payload = to_reconciliation(report)

    assert payload.resumed_any is False
    assert payload.unfinished_count == report.unfinished_count

    source = inspect.getsource(to_reconciliation)
    assert "resumed_any=report.resumed_any" in source


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
