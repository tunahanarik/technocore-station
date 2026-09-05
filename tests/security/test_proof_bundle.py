"""ADR-0009 1, 3, 4, 6, 7, 8 and 11 - the proof bundle, and what it refuses.

Seven decisions, each with the failure it exists to prevent:

* **1.** ``public_share`` is fillable and can only ever point at an archived
  send, whose own outcome decides whether the reference is verified.
* **3.** The bundle is never written to a path. Two plain-text formats, handed
  to the browser, no archive and no new file root.
* **4.** Delivery needs a **single-use** approval bound to the bundle digest,
  the task, the content version and the session. ``ExportConsent`` is not that
  shape, so the ``SendApproval`` pattern is reused.
* **6, 7.** "Independent check" and "real exit code" stay ``not_implemented``
  and say why. The model lane is closed, so there is no second opinion; and
  arbitrary execution is closed, so there is no exit code. Neither is
  invented.
* **8.** ``user_acceptance`` comes only from a person's act, is bound to the
  exact bundle they read, and **moves no state**.
* **11.** What a digest establishes is written into the document.

Nothing in this file contacts anything. The runs are the deterministic tool
runner's, the files are real files in a temporary workspace, and the one
evidence record is written straight into the archive from a fixture.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from station_api.agent.service import _artifact_set_digest
from station_api.agent.workspace import list_files, task_workspace
from station_api.compose.nonce import NonceReserver
from station_api.db.models import EvidenceRecord
from station_api.identity.write_gate import CheckState
from station_api.modules.fields import EvidenceField
from station_api.proof.approvals import SHARE_TOKEN_TTL_SECONDS, ShareApproval
from station_api.proof.bundle import (
    BUNDLE_FORMATS,
    BUNDLE_KIND,
    BUNDLE_MEDIA_TYPE,
    BUNDLE_SUFFIX,
    BUNDLE_VERSION,
    EXIT_CODE_DETAIL,
    INDEPENDENT_CHECK_DETAIL,
    NOT_IMPLEMENTED,
    BundleFormatError,
    artifact_set_sha256,
    render,
    render_json,
    render_markdown,
)
from station_api.proof.language import HASH_SCOPE_SENTENCE
from station_api.proof.service import ProofError, ProofService
from station_api.security.tokens import SingleUseStore
from station_api.strict_json import loads_strict
from station_api.tasks.states import TaskState

from tests.security.agent_fixtures import write_plan

pytestmark = pytest.mark.security

TEST_ONLY_SESSION = "TEST-ONLY-session-0001"
TEST_ONLY_OTHER_SESSION = "TEST-ONLY-session-0002"
TEST_ONLY_DID = "did:key:zTESTONLYnotarealdidkeyvalue"
TEST_ONLY_ROOM = "mb-station-test-only"


def _finished_run(agent, task) -> str:  # type: ignore[no-untyped-def]
    """A task with one completed run and one real file in its workspace."""
    run_id = write_plan(agent, task.id)
    agent.start_run(run_id)
    return run_id


def _archive_a_send(engine: Engine, *, outcome: str = "accepted") -> str:
    """One TEST-ONLY row in the evidence archive. Returns its id.

    Written into the table directly rather than through a real send, because a
    real send is exactly what no automated test may perform (INV-05). The
    nonce reservation goes through the real reserver so the foreign key is
    honest.
    """
    reserver = NonceReserver(engine)
    reservation = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ONLY_ROOM)
    reserver.commit_to_send(reservation.id)

    evidence_id = uuid.uuid4().hex
    with Session(engine) as session, session.begin():
        session.add(
            EvidenceRecord(
                id=evidence_id,
                reservation_id=reservation.id,
                did=TEST_ONLY_DID,
                room=TEST_ONLY_ROOM,
                nonce=reservation.nonce,
                canonical="TEST-ONLY canonical",
                canonical_sha256="0" * 64,
                signature="TEST-ONLY-signature",
                signature_verified=True,
                request_body=b"TEST-ONLY request",
                request_sha256="1" * 64,
                response_body=b"TEST-ONLY response",
                response_sha256="2" * 64,
                http_status=200,
                write_outcome=outcome,
                recorded_at=datetime.now(UTC),
                external_anchor=None,
            )
        )
    return evidence_id


# ---------------------------------------------------------------------------
# ADR-0009 3 - deterministic, two formats, written nowhere
# ---------------------------------------------------------------------------


def test_two_exports_of_an_unchanged_bundle_are_byte_identical(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """Determinism, unconditionally - and here it is load-bearing.

    The evidence export earned this claim by moving ``exported_at`` into a
    header. The proof bundle has the same rule for the same reason, plus one
    the export does not have: the single-use approval is bound to the digest,
    so an unchanged bundle *must* hash the same or every approval would expire
    the instant it was minted.
    """
    _finished_run(agent, task)

    first = proof.build(task.id)
    second = proof.build(task.id)

    assert first.sha256 == second.sha256
    for bundle_format in BUNDLE_FORMATS:
        assert render(first.document, bundle_format=bundle_format) == render(
            second.document, bundle_format=bundle_format
        )


def test_no_document_carries_the_moment_the_copy_was_made(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """The footnote the evidence export removed, removed here as well.

    Every timestamp in the document is a fact about the *task* or the *run* -
    when it was opened, started, finished. There is no key describing when the
    bundle was assembled, because that is a fact about the copy; it travels in
    a response header instead.
    """
    _finished_run(agent, task)
    document = proof.build(task.id).document

    for key in ("prepared_at", "built_at", "exported_at", "generated_at"):
        assert key not in document
    assert "delivered_at" not in document


def test_the_two_formats_are_the_closed_set_and_a_third_is_refused(
    proof: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """A third writer would be a third determinism problem and a third escaper."""
    document = proof.build(task.id).document

    assert BUNDLE_FORMATS == ("json", "markdown")
    assert set(BUNDLE_SUFFIX) == set(BUNDLE_FORMATS)
    assert set(BUNDLE_MEDIA_TYPE) == set(BUNDLE_FORMATS)
    assert "charset=utf-8" in BUNDLE_MEDIA_TYPE["markdown"]

    with pytest.raises(BundleFormatError):
        render(document, bundle_format="csv")  # type: ignore[arg-type]


def test_the_json_document_is_canonical_and_re_readable(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """The format a checker reads, parsed back with the strict reader."""
    _finished_run(agent, task)
    payload = render_json(proof.build(task.id).document)
    parsed = loads_strict(payload)

    assert parsed["kind"] == BUNDLE_KIND
    assert parsed["version"] == BUNDLE_VERSION
    assert parsed["task"]["id"] == task.id
    assert parsed["notes"]["hash_scope"] == HASH_SCOPE_SENTENCE


def test_the_markdown_document_carries_the_digests_it_summarises(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """A summary nothing can be re-derived from is decoration.

    The Markdown format is for a person to read, so it may leave the raw
    bytes out - but it may not leave out the numbers the JSON format's claims
    rest on, or the two would be different documents wearing one name.
    """
    _finished_run(agent, task)
    bundle = proof.build(task.id)
    text = render_markdown(bundle.document).decode("utf-8")

    assert bundle.document["artifacts"]["set_sha256"] in text
    for item in bundle.document["artifacts"]["files"]:
        assert item["sha256"] in text
    assert "\r\n" not in text


def test_nothing_is_written_to_the_workspace_when_a_bundle_is_built(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """ADR-0009 3, measured: the bundle is not an input to its own hash.

    ``_artifact_set_digest`` covers every file in ``workspace/v1/<task_id>``,
    so a bundle written there would change the digest that the bundle itself
    reports. The check is not "we did not mean to write it" - it is that the
    directory listing and the workspace's own digest are unchanged across a
    build, a render of both formats and a delivery.
    """
    _finished_run(agent, task)
    directory = task_workspace(data_dir, task.id)
    before = [(item.name, item.sha256) for item in list_files(directory)]

    bundle = proof.build(task.id)
    for bundle_format in BUNDLE_FORMATS:
        render(bundle.document, bundle_format=bundle_format)
    token, _ = proof.prepare_share(task.id, session_id=TEST_ONLY_SESSION)
    proof.deliver_share(
        task.id,
        session_id=TEST_ONLY_SESSION,
        share_token=token,
        bundle_format="json",
    )

    after = [(item.name, item.sha256) for item in list_files(directory)]

    assert after == before
    assert before, "the run should have produced at least one file to guard"


def test_the_artifact_set_digest_is_the_same_number_the_run_recorded(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """Two computations of one fact, pinned to agree.

    ``station_api.agent.service`` cannot import the proof package - the proof
    package imports *it* - so the set digest is computed in two places. That
    is a drift risk, and the answer is to assert the agreement rather than to
    hope: a review that saw two different anchors for one artifact set would
    have no way to tell which one a claim referred to.
    """
    _finished_run(agent, task)
    files = list_files(task_workspace(data_dir, task.id))

    assert artifact_set_sha256(files) == _artifact_set_digest(files)
    assert proof.build(task.id).document["artifacts"]["set_sha256"] == (
        _artifact_set_digest(files)
    )


# ---------------------------------------------------------------------------
# ADR-0009 4 - the single-use approval
# ---------------------------------------------------------------------------


def test_a_share_approval_is_spent_exactly_once(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """The property ``ExportConsent`` does not have, and the reason it is used.

    ``ExportConsent`` is a per-request boolean: presenting it twice is two
    valid exports. The prompt asks for a single-use approval, so the
    ``SendApproval`` pattern is reused - and this is the assertion that makes
    the choice mean something rather than being a note in an ADR.
    """
    _finished_run(agent, task)
    token, _ = proof.prepare_share(task.id, session_id=TEST_ONLY_SESSION)

    first = proof.deliver_share(
        task.id,
        session_id=TEST_ONLY_SESSION,
        share_token=token,
        bundle_format="json",
    )
    assert first.payload

    with pytest.raises(ProofError) as caught:
        proof.deliver_share(
            task.id,
            session_id=TEST_ONLY_SESSION,
            share_token=token,
            bundle_format="json",
        )

    assert caught.value.reason == "approval_invalid"


def test_an_approval_from_another_session_is_refused(
    proof: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """An approval belongs to the browser session that read the bundle."""
    token, _ = proof.prepare_share(task.id, session_id=TEST_ONLY_SESSION)

    with pytest.raises(ProofError) as caught:
        proof.deliver_share(
            task.id,
            session_id=TEST_ONLY_OTHER_SESSION,
            share_token=token,
            bundle_format="json",
        )

    assert caught.value.reason == "approval_foreign_session"


def test_an_approval_for_another_task_is_refused(
    proof: ProofService, tasks, task  # type: ignore[no-untyped-def]
) -> None:
    """One approval, one task. Otherwise a token could deliver the wrong proof."""
    from station_api.modules.registry import ModuleId
    from station_api.tasks.sources import TaskSourceId

    other = tasks.open_task(
        module_id=ModuleId.AGENT_WORKSPACE,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=b"TEST-ONLY second task",
        title="TEST-ONLY ikinci gorev",
    )
    token, _ = proof.prepare_share(task.id, session_id=TEST_ONLY_SESSION)

    with pytest.raises(ProofError) as caught:
        proof.deliver_share(
            other.id,
            session_id=TEST_ONLY_SESSION,
            share_token=token,
            bundle_format="json",
        )

    assert caught.value.reason == "approval_foreign_task"


def test_an_approval_falls_when_the_artifact_set_changes(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """ADR-0009 4's sentence, turned into a comparison.

    "If the artifact changes, the hash, the check and the old approval are
    re-evaluated" is the prompt's requirement. Here it is structural: the
    approval carries the digest of the document the person read, a changed
    artifact changes that digest, and the delivery refuses rather than handing
    over a bundle nobody approved.
    """
    _finished_run(agent, task)
    token, prepared = proof.prepare_share(task.id, session_id=TEST_ONLY_SESSION)

    # A file appears in the workspace after the approval was given. This is
    # the real path a second run takes, done directly so the test is about the
    # binding rather than about the runner.
    (task_workspace(data_dir, task.id) / "sonradan.json").write_text(
        '{"TEST_ONLY": 2}', encoding="utf-8"
    )

    changed = proof.build(task.id)
    assert changed.sha256 != prepared.sha256

    with pytest.raises(ProofError) as caught:
        proof.deliver_share(
            task.id,
            session_id=TEST_ONLY_SESSION,
            share_token=token,
            bundle_format="json",
        )

    assert caught.value.reason == "bundle_changed"


def test_an_approval_bound_to_another_content_version_is_refused(
    tasks, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """The fourth binding, driven rather than left as a dead branch.

    The content version is *inside* the document, so in ordinary use a change
    to it already changes the digest and the comparison above fires first.
    That makes this branch unreachable through the service's own
    ``prepare_share`` - and an unreachable branch nothing drives is exactly
    the shape this repository keeps finding.

    It is kept because the two facts are separable: a later restructure could
    move the version out of the hashed body, and a binding that holds only
    transitively is a binding nobody notices breaking (ADR-0004 5). So the
    approval is minted by hand with the **right** digest and a **wrong**
    content version, which is the only way to reach it.
    """
    store: SingleUseStore[ShareApproval] = SingleUseStore(
        ttl_seconds=SHARE_TOKEN_TTL_SECONDS
    )
    service = ProofService(tasks=tasks, agent=agent, approvals=store)
    bundle = service.build(task.id)
    token = store.issue(
        ShareApproval(
            task_id=task.id,
            session_id=TEST_ONLY_SESSION,
            bundle_sha256=bundle.sha256,
            source_version_id="TEST-ONLY-another-content-version",
        )
    )

    with pytest.raises(ProofError) as caught:
        service.deliver_share(
            task.id,
            session_id=TEST_ONLY_SESSION,
            share_token=token,
            bundle_format="json",
        )

    assert caught.value.reason == "content_version_changed"


def test_a_refused_delivery_still_spends_the_approval(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """Single-use means spent on **every** outcome, not only on success.

    An approval that survived its own refusal could be retried until the
    bundle happened to match again, which is a replay window with extra
    steps. ``SingleUseStore.consume`` removes the entry under its own lock, so
    the second attempt fails as "invalid" rather than as "changed".
    """
    _finished_run(agent, task)
    token, _ = proof.prepare_share(task.id, session_id=TEST_ONLY_SESSION)
    (task_workspace(data_dir, task.id) / "sonradan.json").write_text(
        '{"TEST_ONLY": 2}', encoding="utf-8"
    )

    with pytest.raises(ProofError) as first:
        proof.deliver_share(
            task.id,
            session_id=TEST_ONLY_SESSION,
            share_token=token,
            bundle_format="json",
        )
    assert first.value.reason == "bundle_changed"

    with pytest.raises(ProofError) as second:
        proof.deliver_share(
            task.id,
            session_id=TEST_ONLY_SESSION,
            share_token=token,
            bundle_format="json",
        )
    assert second.value.reason == "approval_invalid"


def test_an_expired_approval_is_refused(
    tasks, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """The TTL, driven on a controlled clock rather than waited out."""
    clock = {"now": 0.0}
    store: SingleUseStore[ShareApproval] = SingleUseStore(
        ttl_seconds=SHARE_TOKEN_TTL_SECONDS, clock=lambda: clock["now"]
    )
    service = ProofService(tasks=tasks, agent=agent, approvals=store)
    token, _ = service.prepare_share(task.id, session_id=TEST_ONLY_SESSION)

    clock["now"] = SHARE_TOKEN_TTL_SECONDS + 1

    with pytest.raises(ProofError) as caught:
        service.deliver_share(
            task.id,
            session_id=TEST_ONLY_SESSION,
            share_token=token,
            bundle_format="json",
        )

    assert caught.value.reason == "approval_invalid"
    assert service.approval_ttl_seconds == SHARE_TOKEN_TTL_SECONDS


def test_ending_a_session_discards_its_pending_approvals(
    proof: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """The composer's ``discard_session`` shape, for the same reason."""
    proof.prepare_share(task.id, session_id=TEST_ONLY_SESSION)
    proof.prepare_share(task.id, session_id=TEST_ONLY_OTHER_SESSION)

    assert proof.pending_approvals == 2
    assert proof.discard_session(TEST_ONLY_SESSION) == 1
    assert proof.pending_approvals == 1


# ---------------------------------------------------------------------------
# ADR-0009 6 and 7 - what is not produced, and why
# ---------------------------------------------------------------------------


def test_the_independent_check_and_the_exit_code_stay_not_implemented(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """Both fields report ``not_implemented`` and both say the reason.

    Neither is a policy refusal. The model lane is closed by ADR-0008 2 and
    execution by ADR-0008 1; a later package with real isolation could revisit
    either, and reporting them like the lobby greeting would lose that
    difference. What must never happen is a number or a verdict appearing
    where the build has none.
    """
    _finished_run(agent, task)
    claims = proof.build(task.id).document["claims"]

    assert claims["independent_check"]["state"] == NOT_IMPLEMENTED
    assert claims["exit_code"]["state"] == NOT_IMPLEMENTED
    assert claims["test_result"]["state"] == NOT_IMPLEMENTED

    assert claims["independent_check"]["detail"] == INDEPENDENT_CHECK_DETAIL
    assert claims["exit_code"]["detail"] == EXIT_CODE_DETAIL
    assert "Model yolu kapalidir" in INDEPENDENT_CHECK_DETAIL
    assert "kabuk yurutmesi kapalidir" in EXIT_CODE_DETAIL


def test_the_success_criterion_is_packaged_as_text_and_never_as_a_result(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """ADR-0009 7: the plan's criterion and the instruction travel; no verdict does.

    The criterion the plan recorded is in the document, so a reader can see
    what would have established success - and beside it the run's own
    ``test_result_state``, which is ``not_implemented`` because nothing ran.
    A document that carried the criterion without the state would read as a
    passed check.
    """
    _finished_run(agent, task)
    document = proof.build(task.id).document
    run = document["runs"][0]

    assert run["test_condition"]
    assert run["test_result_state"] == NOT_IMPLEMENTED
    assert "kosulmaz" in document["notes"]["reproduction"]
    assert "SHA-256" in document["notes"]["reproduction"]


def test_a_finished_run_still_leaves_the_task_short_of_ready_to_publish(
    proof: ProofService, agent, tasks, task  # type: ignore[no-untyped-def]
) -> None:
    """The end-to-end consequence of the two closed capabilities.

    A run that produced every promised artifact records ``task_outcome`` and
    nothing else. ``test_result`` has no producer, so the gate keeps blocking
    and the bundle names the gap - which is the whole point of building a
    proof workspace over a build that cannot run tests.
    """
    _finished_run(agent, task)
    document = proof.build(task.id).document

    assert tasks.get(task.id).state is TaskState.REVIEW_NEEDED
    assert document["ready_to_publish"] is False
    assert "test_result" in document["blocking_fields"]
    assert any(
        entry["key"] == "evidence.test_result" for entry in document["missing"]
    )


# ---------------------------------------------------------------------------
# Named gaps, never a score
# ---------------------------------------------------------------------------


def test_every_gap_is_named_rather_than_counted(
    proof: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """Absence is stated. A task with no run at all says so, by name."""
    document = proof.build(task.id).document
    keys = {entry["key"] for entry in document["missing"]}

    assert "run.none" in keys
    assert any(key.startswith("evidence.") for key in keys)
    assert any(key.startswith("requirement.") for key in keys)
    for entry in document["missing"]:
        assert entry["detail"].strip(), entry["key"]

    # No score, no percentage, no single number that stands for the set.
    for forbidden in ("score", "percent", "completeness", "grade", "rating"):
        assert forbidden not in render_json(document).decode("utf-8").lower()


def test_a_promised_artifact_that_is_gone_is_named_in_the_bundle(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """The gap a reader would otherwise have to find by comparing two lists."""
    _finished_run(agent, task)
    (task_workspace(data_dir, task.id) / "rapor.json").unlink()

    document = proof.build(task.id).document
    keys = {entry["key"] for entry in document["missing"]}

    assert "artifact.rapor.json" in keys


def test_the_hash_scope_sentence_is_in_both_formats(
    proof: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """ADR-0009 11. The sentence travels with the number, in both documents."""
    bundle = proof.build(task.id)

    assert bundle.document["notes"]["hash_scope"] == HASH_SCOPE_SENTENCE
    assert HASH_SCOPE_SENTENCE in render_json(bundle.document).decode("utf-8")
    # Markdown escapes metacharacters, so the sentence is compared on a
    # distinctive fragment that survives escaping rather than verbatim.
    assert "bayt bakimindan ayni kaldigini tanimlar" in render_markdown(
        bundle.document
    ).decode("utf-8")


# ---------------------------------------------------------------------------
# ADR-0009 8 - acceptance is a person's act and moves nothing
# ---------------------------------------------------------------------------


def test_an_acceptance_records_the_field_and_moves_no_state(
    proof: ProofService, tasks, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """SI-222, held from the other side.

    The acceptance is the **input** to a publication decision. A route that
    also transitioned the task would make ``ready_to_publish`` something a
    request produces rather than something three verified fields derive, so
    the state before and after is compared explicitly.
    """
    _finished_run(agent, task)
    before = tasks.get(task.id).state
    bundle = proof.build(task.id)

    after = proof.record_acceptance(task.id, bundle_sha256=bundle.sha256)

    assert after.state is before
    assert tasks.get(task.id).state is before
    check = tasks.gate(task.id).check_for(EvidenceField.USER_ACCEPTANCE)
    assert check.state is CheckState.PASSED
    assert check.ref_id == bundle.sha256


def test_an_acceptance_for_a_bundle_that_has_since_changed_is_refused(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """Accepting something else is not accepting this.

    The digest a person saw is required, and it is compared against the bundle
    as it stands. Without that, an acceptance recorded minutes after an
    artifact changed would attach a person's name to output they never read.
    """
    _finished_run(agent, task)
    stale = proof.build(task.id).sha256
    (task_workspace(data_dir, task.id) / "sonradan.json").write_text(
        '{"TEST_ONLY": 2}', encoding="utf-8"
    )

    with pytest.raises(ProofError) as caught:
        proof.record_acceptance(task.id, bundle_sha256=stale)

    assert caught.value.reason == "bundle_changed"
    assert proof.build(task.id).document["evidence_fields"]


def test_no_automatic_path_fills_user_acceptance(
    proof: ProofService, tasks, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """A run finishing does not accept its own output (ADR-0008 6, ADR-0009 8).

    Driven rather than asserted about the code: the run is carried out in
    full, every promised artifact is produced, and the field is still blocked
    afterwards.
    """
    _finished_run(agent, task)

    check = tasks.gate(task.id).check_for(EvidenceField.USER_ACCEPTANCE)

    assert check.state is CheckState.BLOCKED
    assert check.ref_id == ""
    assert proof.build(task.id).document["ready_to_publish"] is False


# ---------------------------------------------------------------------------
# ADR-0009 1 - the fourth field, from an archived send and nothing else
# ---------------------------------------------------------------------------


def test_public_share_is_marked_from_an_archived_send(
    proof: ProofService, tasks, engine: Engine, task  # type: ignore[no-untyped-def]
) -> None:
    """The permitted case: a real row, an accepted outcome, a verified mark."""
    evidence_id = _archive_a_send(engine)

    proof.record_public_share(task.id, evidence_id=evidence_id)
    check = tasks.gate(task.id).check_for(EvidenceField.PUBLIC_SHARE)

    assert check.state is CheckState.PASSED
    assert check.ref_id == evidence_id


def test_a_send_whose_outcome_is_unknown_is_recorded_but_not_verified(
    proof: ProofService, tasks, engine: Engine, task  # type: ignore[no-untyped-def]
) -> None:
    """The three-valued send result survives into the fourth field.

    ``outcome_unknown`` means the server may or may not have stored the
    message (ADR-0002 3). Marking that as a verified public share would be the
    "presence of a row is success" mistake in its most expensive form, so the
    verdict is read off the archived record rather than taken from the caller.
    """
    evidence_id = _archive_a_send(engine, outcome="outcome_unknown")

    proof.record_public_share(task.id, evidence_id=evidence_id)
    check = tasks.gate(task.id).check_for(EvidenceField.PUBLIC_SHARE)

    assert check.state is CheckState.BLOCKED
    assert check.ref_id == evidence_id
    # The gate writes its own sentence for an unverified reference, so the
    # stored one is read off the row: that is where the *reason* lives, and a
    # reader who only saw "recorded but not checked" would not learn that the
    # send itself came back unknown.
    stored = next(
        ref for ref in tasks.get(task.id).refs if ref.field is EvidenceField.PUBLIC_SHARE
    )
    assert "outcome_unknown" in stored.detail
    assert "dogrulanmamis" in stored.detail


def test_a_public_share_pointer_that_names_no_send_is_refused(
    proof: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """Both shapes of wrong pointer, with the two different reasons."""
    with pytest.raises(ProofError) as invented:
        proof.record_public_share(task.id, evidence_id="0" * 32)
    assert invented.value.reason == "evidence_record_missing"

    with pytest.raises(ProofError) as typed:
        proof.record_public_share(task.id, evidence_id="paylasildi")
    assert typed.value.reason == "evidence_record_missing"


def test_a_machine_without_an_archive_refuses_rather_than_pretending(
    proof_without_archive: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """Honest degradation, the way a missing evidence layer is handled elsewhere.

    The bundle still assembles on a machine where the audit envelope did not
    open. The one operation that needs the archive says so instead of marking
    the field on trust.
    """
    assert proof_without_archive.build(task.id).sha256

    with pytest.raises(ProofError) as caught:
        proof_without_archive.record_public_share(task.id, evidence_id="0" * 32)

    assert caught.value.reason == "evidence_unavailable"


def test_a_public_share_does_not_make_a_task_ready_to_publish(
    proof: ProofService, tasks, engine: Engine, task  # type: ignore[no-untyped-def]
) -> None:
    """ADR-0004 4 and ADR-0009 1 together: fillable is not required.

    ``public_share`` passing changes nothing about whether the work is
    finished, because publishing is a different question from finishing. The
    three publication fields are still the three that decide.
    """
    proof.record_public_share(task.id, evidence_id=_archive_a_send(engine))
    status = tasks.gate(task.id)

    assert status.check_for(EvidenceField.PUBLIC_SHARE).state is CheckState.PASSED
    assert status.ready_to_publish is False
    assert "public_share" not in status.blocking_fields
