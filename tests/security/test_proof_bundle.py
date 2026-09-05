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
from station_api.agent.workspace import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    ensure_workspace,
    list_files,
    task_workspace,
)
from station_api.compose.nonce import NonceReserver
from station_api.db.models import EvidenceRecord
from station_api.identity.write_gate import CheckState
from station_api.modules.fields import EvidenceField, EvidenceFieldError, EvidenceRef
from station_api.proof import artifacts as artifacts_module
from station_api.proof.approvals import SHARE_TOKEN_TTL_SECONDS, ShareApproval
from station_api.proof.artifacts import (
    BODY_EMBEDDED,
    BODY_EXCLUDED,
    EXCLUSION_DETAIL,
    MAX_EMBEDDED_FILE_BYTES,
    MAX_EMBEDDED_FILES,
    MAX_EMBEDDED_TOTAL_BYTES,
    REASON_COUNT_EXHAUSTED,
    REASON_DIGEST_MISMATCH,
    REASON_FILE_TOO_LARGE,
    REASON_NOT_TEXT,
    REASON_SECRET_PATTERN,
    REASON_TOTAL_EXHAUSTED,
)
from station_api.proof.bundle import (
    BUNDLE_FORMATS,
    BUNDLE_KIND,
    BUNDLE_MEDIA_TYPE,
    BUNDLE_SUFFIX,
    BUNDLE_VERSION,
    EXIT_CODE_DETAIL,
    INDEPENDENT_CHECK_DETAIL,
    MAX_BUNDLE_TEXT_CHARS,
    NOT_IMPLEMENTED,
    BundleFormatError,
    artifact_set_sha256,
    render,
    render_json,
    render_markdown,
    verify_body_digests,
)
from station_api.proof.language import (
    BODY_SCOPE_SENTENCE,
    HASH_SCOPE_SENTENCE,
    PROOF_FORBIDDEN_PHRASES,
)
from station_api.proof.service import ProofError, ProofService
from station_api.security.tokens import MAX_PENDING_TOKENS, SingleUseStore
from station_api.strict_json import loads_strict
from station_api.tasks.service import TaskError
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
    tasks, agent, task, data_dir  # type: ignore[no-untyped-def]
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
    service = ProofService(
        tasks=tasks, agent=agent, data_dir=data_dir, approvals=store
    )
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
    tasks, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """The TTL, driven on a controlled clock rather than waited out."""
    clock = {"now": 0.0}
    store: SingleUseStore[ShareApproval] = SingleUseStore(
        ttl_seconds=SHARE_TOKEN_TTL_SECONDS, clock=lambda: clock["now"]
    )
    service = ProofService(
        tasks=tasks, agent=agent, data_dir=data_dir, approvals=store
    )
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


def test_the_share_approval_ttl_is_the_documented_three_minutes() -> None:
    """Pinned, because the number is a decision (ADR-0009 4), not a default.

    Its twin in ``test_compose_flow.py`` has been pinned since Package C; this
    one was not, and an adversarial review moved ``SHARE_TOKEN_TTL_SECONDS``
    from 180 to 86400 without turning anything red. Every other use of the
    constant in this file is *relative* - a fake clock is advanced to
    ``TTL + 1`` - so a day-long window expires exactly as promptly as a
    three-minute one and every one of those tests still passes.

    Three minutes is written down as a deliberate window in
    ``docs/proof-workspace.md`` 3 and SI-305, and the frontend shows the
    literal text "180 saniye". A constant three documents describe and no test
    reads is a constant anybody can change.
    """
    assert SHARE_TOKEN_TTL_SECONDS == 180


def test_ending_a_session_discards_its_pending_approvals(
    proof: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """The composer's ``discard_session`` shape, for the same reason."""
    proof.prepare_share(task.id, session_id=TEST_ONLY_SESSION)
    proof.prepare_share(task.id, session_id=TEST_ONLY_OTHER_SESSION)

    assert proof.pending_approvals == 2
    assert proof.discard_session(TEST_ONLY_SESSION) == 1
    assert proof.pending_approvals == 1


def test_abandoned_share_approvals_stop_occupying_memory(
    tasks, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """A TTL that only decides validity is not a TTL that frees anything.

    Measured before it was fixed: fifty prepares left fifty pending entries,
    and five more prepares taken *after* the clock had passed the TTL left
    fifty-five - none of them spendable, all of them still in the dictionary.
    ``purge_expired`` existed and was called from nowhere in the product, and
    ``consume`` only ever reaches the one token it is handed, which is the one
    thing an abandoned approval never has happen to it.

    ``SingleUseStore.issue`` now purges first, exactly as ``DraftStore.put``
    does. Driven on a controlled clock rather than waited out, and the count
    is read before and after so a store that dropped everything would fail the
    first half.
    """
    clock = {"now": 0.0}
    store: SingleUseStore[ShareApproval] = SingleUseStore(
        ttl_seconds=SHARE_TOKEN_TTL_SECONDS, clock=lambda: clock["now"]
    )
    service = ProofService(
        tasks=tasks, agent=agent, data_dir=data_dir, approvals=store
    )

    for _ in range(50):
        service.prepare_share(task.id, session_id=TEST_ONLY_SESSION)
    assert service.pending_approvals == 50

    clock["now"] = SHARE_TOKEN_TTL_SECONDS + 1
    for _ in range(5):
        service.prepare_share(task.id, session_id=TEST_ONLY_SESSION)

    assert service.pending_approvals == 5


def test_the_share_approval_store_has_a_ceiling_and_the_shipped_one_uses_it(
    tasks, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """Purging is not enough on its own; an unexpired flood is still a flood.

    The composer's ``DraftStore`` has enforced ``MAX_OPEN_DRAFTS`` since
    Package C and this store enforced nothing, so approvals that had **not**
    expired grew without limit. The cap is driven with a small explicit
    ceiling - a loop of ten is a measurement, a loop of sixty-five is a wait -
    and the ceiling the product actually ships with is read off the service
    rather than assumed, because a bounded store and an unbounded one look
    identical from outside until somebody counts.

    The oldest entry is dropped rather than the newest refused, as the drafts
    do: the person is in front of the newest one.
    """
    store: SingleUseStore[ShareApproval] = SingleUseStore(
        ttl_seconds=SHARE_TOKEN_TTL_SECONDS, capacity=4
    )
    service = ProofService(
        tasks=tasks, agent=agent, data_dir=data_dir, approvals=store
    )

    tokens = [
        service.prepare_share(task.id, session_id=TEST_ONLY_SESSION)[0]
        for _ in range(10)
    ]

    assert service.pending_approvals == 4
    # The newest four survive and the oldest were dropped, so the person who
    # is actually waiting on a bundle can still take it.
    assert store.consume(tokens[-1])[0] is True
    assert store.consume(tokens[0])[0] is False

    # And the store the application builds is bounded too - the default, not
    # the one this test constructed.
    shipped = ProofService(tasks=tasks, agent=agent, data_dir=data_dir)
    assert shipped.approval_capacity == MAX_PENDING_TOKENS


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
    """Both shapes of wrong pointer, and the **one** reason both get.

    The docstring here used to say "the two different reasons", and the two
    assertions underneath it have always read the same one. An adversarial
    review of H3 measured why: on this path the archive read is the gate.
    ``EvidenceService.get`` runs before anything else can, because the
    record's own ``write_outcome`` decides ``verified``, so a well-formed id
    that names nothing and a sentence somebody typed are the same fact to it -
    there is no such row - and both come back
    ``evidence_record_missing``.

    That is the honest description of the mechanism, and the assertions are
    unchanged: what a caller cannot do is mark this field with a string they
    wrote. What they get told is that no archived send has that identity. The
    two deeper refusals - the shape check in ``EvidenceRef`` and the
    row-existence check in ``TaskService`` - are driven in the test below, at
    the level where they actually fire.
    """
    with pytest.raises(ProofError) as invented:
        proof.record_public_share(task.id, evidence_id="0" * 32)
    assert invented.value.reason == "evidence_record_missing"

    with pytest.raises(ProofError) as typed:
        proof.record_public_share(task.id, evidence_id="paylasildi")
    assert typed.value.reason == "evidence_record_missing"


def test_the_two_shadowed_public_share_refusals_are_driven_where_they_fire(
    tasks, engine: Engine, task  # type: ignore[no-untyped-def]
) -> None:
    """The depth defences, exercised by the callers they exist for.

    ``TaskService.record_evidence`` is public and it is the only function in
    this product that writes these columns; ``EvidenceRef`` is constructed in
    places where no database is at hand. Neither can rely on
    ``ProofService.record_public_share`` having run first, and behind that
    method neither can ever be the refusal a caller sees. So each is driven
    here, against the layer it belongs to:

    * a **well-formed** id that names no archived row reaches the task
      service's ``SELECT`` and is refused there - the shape check has already
      passed, so this is the row-existence check on its own;
    * a **badly-shaped** id never reaches a database at all: the constructor
      refuses it, which is what covers the callers that have none.

    The permitted case is read first in both halves, so a service that refused
    every pointer would fail rather than pass.
    """
    archived = _archive_a_send(engine)

    # Permitted first: a real archived id goes all the way through.
    tasks.record_evidence(
        task.id,
        field=EvidenceField.PUBLIC_SHARE,
        ref_id=archived,
        verified=True,
    )
    assert tasks.gate(task.id).check_for(EvidenceField.PUBLIC_SHARE).ref_id == archived

    # The row-existence check, alone: thirty-two hex characters that name
    # nothing. ``uuid4().hex``'s shape, so the constructor is satisfied.
    absent = uuid.uuid4().hex
    with pytest.raises(TaskError) as missing_row:
        tasks.record_evidence(
            task.id,
            field=EvidenceField.PUBLIC_SHARE,
            ref_id=absent,
            verified=True,
        )
    assert missing_row.value.reason == "evidence_record_missing"

    # The shape check, alone: no database is consulted, and the refusal comes
    # from the constructor every caller passes through.
    with pytest.raises(EvidenceFieldError):
        EvidenceRef(
            field=EvidenceField.PUBLIC_SHARE,
            ref_id="paylasildi",
            verified=True,
            source_version_id="v1",
        )

    # And the shape check is not the row check wearing another name: the same
    # badly-shaped pointer refused through the service reports the *field*
    # refusal, not the missing row.
    with pytest.raises(TaskError) as bad_shape:
        tasks.record_evidence(
            task.id,
            field=EvidenceField.PUBLIC_SHARE,
            ref_id="paylasildi",
            verified=True,
        )
    assert bad_shape.value.reason == "evidence_field_refused"


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


# ---------------------------------------------------------------------------
# The bundle carries the work, not a description of it
# ---------------------------------------------------------------------------
#
# An independent review measured what a person actually received:
#
#     {"contains_filename": true, "contains_artifact_body": false}
#
# The artifact entries held a name, a byte count and a SHA-256, and the file
# the run had produced stayed on disk. Everything in this block is about that
# measurement and about the four ways carrying a body could go wrong: a body
# that does not match its digest, a body that is too big to carry, a body that
# is not ours to hand out, and a body that closes its own code fence.


#: A body a substring search can find, so "the file is in the package" is a
#: measurement rather than an impression.
TEST_ONLY_MARKER = "TEST-ONLY-artifact-body-marker-8f2a"

#: 64 hex characters: the shape ``secret_scan`` refuses as a seed or a private
#: key. Not a real key and never used as one - it is the canary that proves the
#: scan is looking at artifact bodies now that artifact bodies are delivered.
TEST_ONLY_CANARY = "a1b2c3d4" * 8


def _run_with_body(agent, task, body: str, *, name: str = "rapor.json") -> str:  # type: ignore[no-untyped-def]
    """One completed run whose single artifact has exactly ``body`` in it."""
    run_id = write_plan(agent, task.id, name=name, body=body, expected=(name,))
    agent.start_run(run_id)
    return run_id


def _filler(size: int) -> bytes:
    """``size`` bytes the secret scan has no reason to look at twice.

    Not ``b"T" * size``: the deny rules match a run of 43 or more base64url
    characters, and half a megabyte of one letter is exactly that. The scan is
    right to fire - it cannot tell padding from a padded seed, which is why it
    matches runs of *at least* the secret length - so a ceiling test has to
    fill with something that has boundaries in it, or it measures the scan
    instead of the ceiling. Measured: the first version of this test filled
    with one repeated letter and every body came back excluded as a
    secret-pattern hit.
    """
    unit = b"TEST-ONLY "
    return (unit * (size // len(unit) + 1))[:size]


def _plant(data_dir, task_id: str, name: str, payload: bytes) -> None:  # type: ignore[no-untyped-def]
    """Put bytes into a task workspace that the product's own writer refuses.

    Every ceiling below is about a file this product could not have written -
    too large, not UTF-8, one file too many - so the test has to write it
    another way. Straight to the directory, from the test, with no product
    code involved: the point is what the *reader* does with a file it did not
    make.
    """
    directory = ensure_workspace(data_dir, task_id)
    (directory / name).write_bytes(payload)


def _entry(document, name: str):  # type: ignore[no-untyped-def]
    return next(
        item for item in document["artifacts"]["files"] if item["name"] == name
    )


def test_the_bundle_carries_the_produced_file_and_not_only_its_name(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """The measured defect, as a test.

    Before the bodies were carried this read ``contains_artifact_body: false``
    in both formats: a person who downloaded their proof received an inventory
    of their work and the digests to check it against, and not the work. Both
    formats are asserted because delivering the file in one of them and a
    description in the other would be two documents wearing one name.
    """
    body = f'{{"TEST_ONLY": "{TEST_ONLY_MARKER}"}}'
    _run_with_body(agent, task, body)

    document = proof.build(task.id).document
    entry = _entry(document, "rapor.json")

    assert entry["content_state"] == BODY_EMBEDDED
    assert entry["content"] == body
    assert entry["content_encoding"] == "utf-8"
    for bundle_format in BUNDLE_FORMATS:
        payload = render(document, bundle_format=bundle_format).decode("utf-8")
        assert TEST_ONLY_MARKER in payload, bundle_format


def test_every_embedded_body_hashes_to_the_digest_beside_it(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """The hash contract, and the mutation that has to break it.

    An entry is a body and a digest of that body. If the two can drift the
    entry is worse than useless: a reader who checks their saved copy against
    the printed number and gets a match has been told something false about
    which bytes they hold. One character is changed in the carried text and the
    check has to name that file.
    """
    _run_with_body(agent, task, f'{{"TEST_ONLY": "{TEST_ONLY_MARKER}"}}')
    document = proof.build(task.id).document

    assert verify_body_digests(document) == ()

    entry = _entry(document, "rapor.json")
    entry["content"] = str(entry["content"]).replace("TEST", "TSET", 1)

    assert verify_body_digests(document) == ("rapor.json",)


def test_a_file_that_changes_between_the_listing_and_the_read_is_excluded(
    proof: ProofService, agent, task, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    """The window between two reads, and why the digest is taken twice.

    The listing hashes the bytes it read; the body is read again a moment
    later, and a file can change in between - a run in another process, a
    person with an editor open. Whatever caused it, the digest from the first
    read and the text from the second describe different files, and shipping
    them in one entry would be the exact lie the entry exists to prevent.

    Driven by making the second read return something else, because a real race
    cannot be scheduled deterministically. That is stated rather than hidden:
    what is being asserted is the *comparison*, and the comparison cannot tell
    why the two reads disagreed.
    """
    _run_with_body(agent, task, f'{{"TEST_ONLY": "{TEST_ONLY_MARKER}"}}')

    monkeypatch.setattr(
        artifacts_module,
        "read_text",
        lambda directory, name: '{"TEST_ONLY": "something else entirely"}',
    )
    document = proof.build(task.id).document
    entry = _entry(document, "rapor.json")

    assert entry["content_state"] == BODY_EXCLUDED
    assert entry["content"] is None
    assert entry["content_detail"] == EXCLUSION_DETAIL[REASON_DIGEST_MISMATCH]
    assert verify_body_digests(document) == ()


def test_a_body_is_carried_whole_or_not_at_all(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """No truncation anywhere, at any size.

    ``safe_text`` cuts imported text at five hundred characters, which is right
    for a title in a sentence and catastrophic for a file: a body cut at five
    hundred characters under a digest describing the whole file is a document
    that lies in exactly the way a digest is supposed to prevent.
    """
    body = "TEST-ONLY " * 400  # comfortably past MAX_BUNDLE_TEXT_CHARS
    _run_with_body(agent, task, body, name="uzun.txt")
    document = proof.build(task.id).document
    entry = _entry(document, "uzun.txt")

    assert len(body) > MAX_BUNDLE_TEXT_CHARS
    assert entry["content"] == body
    assert entry["byte_count"] == len(body.encode("utf-8"))
    assert verify_body_digests(document) == ()


def test_the_package_ceilings_are_the_workspaces_own_three(
    proof: ProofService, task  # type: ignore[no-untyped-def]
) -> None:
    """Referenced, not restated.

    A second set of numbers would drift, and the drift would be silent in the
    worst direction: a package ceiling below the workspace's would start
    excluding bodies of files this product itself wrote, and a person would be
    told their own report was too big to hand back to them.
    """
    assert MAX_EMBEDDED_FILES == MAX_FILES
    assert MAX_EMBEDDED_FILE_BYTES == MAX_FILE_BYTES
    assert MAX_EMBEDDED_TOTAL_BYTES == MAX_TOTAL_BYTES
    assert proof.build(task.id).document["version"] == BUNDLE_VERSION


def test_a_file_over_the_per_file_ceiling_is_named_rather_than_cut(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """The refusal is shown, and the rest of the proof survives it.

    Two halves, and the second is the one that is easy to get wrong. The body
    has to be absent with the ceiling named - in the entry and again in the
    document's ``missing`` list - and the *other* file's body has to still be
    there. A bundle that refused itself because one file somebody dropped into
    the directory was too big would let a stray file lock a person out of the
    proof of everything else they did.
    """
    _run_with_body(agent, task, f'{{"TEST_ONLY": "{TEST_ONLY_MARKER}"}}')
    _plant(data_dir, task.id, "buyuk.txt", b"T" * (MAX_EMBEDDED_FILE_BYTES + 1))

    document = proof.build(task.id).document
    oversized = _entry(document, "buyuk.txt")

    assert oversized["content_state"] == BODY_EXCLUDED
    assert oversized["content"] is None
    assert oversized["content_detail"] == EXCLUSION_DETAIL[REASON_FILE_TOO_LARGE]
    assert str(MAX_EMBEDDED_FILE_BYTES) in oversized["content_detail"]
    assert oversized["sha256"] and oversized["byte_count"] > MAX_EMBEDDED_FILE_BYTES

    keys = {item["key"] for item in document["missing"]}
    assert "artifact_body.buyuk.txt" in keys

    assert _entry(document, "rapor.json")["content_state"] == BODY_EMBEDDED
    assert TEST_ONLY_MARKER in render_json(document).decode("utf-8")


def test_the_total_ceiling_is_reached_with_real_files_and_named_when_crossed(
    proof: ProofService, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """The package total, driven at its real value rather than a patched one.

    Nine files of exactly the per-file ceiling: eight fit inside four
    megabytes, the ninth would cross it. Written as real bytes on disk because
    a ceiling that has only ever been tested against a monkeypatched constant
    is a ceiling nobody has watched work.
    """
    per_file = MAX_EMBEDDED_FILE_BYTES
    count = MAX_EMBEDDED_TOTAL_BYTES // per_file + 1
    for index in range(count):
        _plant(data_dir, task.id, f"dosya-{index:02d}.txt", _filler(per_file))

    document = proof.build(task.id).document
    states = [item["content_state"] for item in document["artifacts"]["files"]]
    last = document["artifacts"]["files"][-1]

    assert states.count(BODY_EMBEDDED) == MAX_EMBEDDED_TOTAL_BYTES // per_file
    assert last["content_state"] == BODY_EXCLUDED
    assert last["content_detail"] == EXCLUSION_DETAIL[REASON_TOTAL_EXHAUSTED]
    assert document["artifacts"]["embedded_bytes"] <= MAX_EMBEDDED_TOTAL_BYTES
    assert f"artifact_body.{last['name']}" in {
        item["key"] for item in document["missing"]
    }


def test_the_file_count_ceiling_leaves_the_extra_bodies_out_by_name(
    proof: ProofService, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """One more file than the workspace's own count ceiling."""
    for index in range(MAX_EMBEDDED_FILES + 1):
        _plant(data_dir, task.id, f"k-{index:03d}.txt", b"TEST-ONLY")

    document = proof.build(task.id).document
    entries = document["artifacts"]["files"]
    last = entries[-1]

    assert len(entries) == MAX_EMBEDDED_FILES + 1
    assert document["artifacts"]["embedded_file_count"] == MAX_EMBEDDED_FILES
    assert last["content_state"] == BODY_EXCLUDED
    assert last["content_detail"] == EXCLUSION_DETAIL[REASON_COUNT_EXHAUSTED]


def test_a_file_that_is_not_utf8_is_named_rather_than_refusing_the_bundle(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """The binary case, measured rather than assumed away.

    This product writes no binary artifact - the only writer takes a ``str``
    and encodes UTF-8 - so there is nothing to base64. A file that arrived some
    other way is still a file in the person's workspace, and the answer is the
    workspace's own: name it, say what is wrong, keep going.
    """
    _run_with_body(agent, task, f'{{"TEST_ONLY": "{TEST_ONLY_MARKER}"}}')
    _plant(data_dir, task.id, "ikili.bin", b"\xff\xfe\x00\x01TEST-ONLY")

    document = proof.build(task.id).document
    entry = _entry(document, "ikili.bin")

    assert entry["content_state"] == BODY_EXCLUDED
    assert entry["content"] is None
    assert entry["content_detail"] == EXCLUSION_DETAIL[REASON_NOT_TEXT]
    assert _entry(document, "rapor.json")["content_state"] == BODY_EMBEDDED


def test_a_canary_in_a_workspace_file_is_caught_before_the_body_is_delivered(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """The leak test, and the reason the scan had to be extended at all.

    ``evidence/secret_scan.py`` ran on evidence rows, which stay on this
    machine. The proof bundle is the one document in this product built to be
    handed to somebody else, so the moment bodies started travelling inside it
    the bundle became the most likely leak surface there is.

    Refused, not redacted: the body is left out entire and the rule is named.
    Redacting would hand over a file whose bytes no longer match the digest
    printed beside it, which is the one thing an artifact entry may never do.
    """
    _run_with_body(agent, task, f'{{"TEST_ONLY_canary": "{TEST_ONLY_CANARY}"}}')

    bundle = proof.build(task.id)
    entry = _entry(bundle.document, "rapor.json")

    assert entry["content_state"] == BODY_EXCLUDED
    assert entry["content"] is None
    assert EXCLUSION_DETAIL[REASON_SECRET_PATTERN] in entry["content_detail"]
    assert TEST_ONLY_CANARY not in entry["content_detail"]

    for bundle_format in BUNDLE_FORMATS:
        payload = render(bundle.document, bundle_format=bundle_format).decode("utf-8")
        assert TEST_ONLY_CANARY not in payload, bundle_format

    # The file is still listed. What is refused is its contents, not its
    # existence - a proof that silently dropped the file would be hiding the
    # very thing the reader needs to go and look at.
    assert entry["sha256"] and entry["byte_count"] > 0
    assert "artifact_body.rapor.json" in {
        item["key"] for item in bundle.document["missing"]
    }


def test_a_forbidden_phrase_inside_a_file_is_reported_and_left_alone(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """Package E's claim/data split, at the one place it collides with a digest.

    A body is data: it may not refuse the bundle, and a person who typed a
    banned phrase into their own report must still be able to take that report.
    It also may not be *neutralised*, which is what every other imported string
    here goes through - masking a phrase would change the bytes underneath a
    digest that describes the file, and the entry would stop being checkable.

    So the guard runs and **reports**. The phrase is named beside the body and
    the body is delivered exactly as it is on disk.
    """
    phrase = PROOF_FORBIDDEN_PHRASES[0]
    body = f"TEST-ONLY rapor. {phrase}."
    _run_with_body(agent, task, body, name="rapor.txt")

    document = proof.build(task.id).document
    entry = _entry(document, "rapor.txt")

    assert entry["content"] == body
    assert entry["content_claim_phrases"] == [phrase]
    assert verify_body_digests(document) == ()
    assert phrase in render_markdown(document).decode("utf-8")


def test_a_body_cannot_close_the_code_fence_that_carries_it(
    proof: ProofService, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """Markdown injection out of an artifact this product did not write.

    A fenced block ends at the first line whose fence is at least as long as
    the opening one. A body containing three backticks on a line of its own
    would end the block, and everything after it in that file would be read as
    Markdown in a document a person is about to forward. The fence is computed
    from the body rather than fixed, and escaping is not an option here: an
    escaped body is a different body and would not hash.

    Planted straight into the directory rather than written through a plan:
    the runner sweeps its tool arguments, so a multi-line body handed to it
    arrives on disk with its newlines replaced by spaces and there would be no
    line left to close a fence with. Measured while writing this test.
    """
    body = "TEST-ONLY\n```\n# baslik degil\n````\nson"
    _plant(data_dir, task.id, "fence.md", body.encode("utf-8"))

    document = proof.build(task.id).document
    text = render_markdown(document).decode("utf-8")

    assert "`````" in text
    assert "# baslik degil" in text
    assert _entry(document, "fence.md")["content"] == body
    assert verify_body_digests(document) == ()


def test_the_bundle_never_becomes_an_input_to_its_own_digest(
    proof: ProofService, agent, task, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """No self-reference, now that the document carries the files.

    The artifact set digest covers every file in ``workspace/v1/<task_id>``, so
    a bundle written there would be inside its own hash - and with the bodies
    embedded it would also be inside its own *body*. Nothing writes it
    anywhere, and the document does not carry its own digest either: an
    approval binds to ``bundle_sha256`` from outside, and a digest printed
    inside the thing it describes could never be right.
    """
    _run_with_body(agent, task, f'{{"TEST_ONLY": "{TEST_ONLY_MARKER}"}}')
    directory = task_workspace(data_dir, task.id)
    before = [(item.name, item.sha256) for item in list_files(directory)]

    bundle = proof.build(task.id)
    rendered = {
        bundle_format: render(bundle.document, bundle_format=bundle_format)
        for bundle_format in BUNDLE_FORMATS
    }

    assert bundle.sha256 not in render_json(bundle.document).decode("utf-8")
    for payload in rendered.values():
        assert bundle.sha256.encode("ascii") not in payload
    assert [(item.name, item.sha256) for item in list_files(directory)] == before
    assert before


def test_the_document_states_what_a_carried_body_is_and_is_not(
    proof: ProofService, agent, task  # type: ignore[no-untyped-def]
) -> None:
    """ADR-0009 11's sentence has a third half now.

    A document that started carrying somebody else's text had to say so. The
    reader is told the bodies are the run's output rather than this product's
    words, that each digest describes the body beside it, and that an absent
    body is named - all three in both formats, because a person reads one of
    them and a checker reads the other.
    """
    _run_with_body(agent, task, f'{{"TEST_ONLY": "{TEST_ONLY_MARKER}"}}')
    document = proof.build(task.id).document

    assert document["notes"]["body_scope"] == BODY_SCOPE_SENTENCE
    assert BODY_SCOPE_SENTENCE in render_json(document).decode("utf-8")
    markdown = render_markdown(document).decode("utf-8")
    assert "Dosya govdeleri" in markdown
    for fragment in ("Govde kosmanin urettigi metindir", "kendi ozetidir"):
        assert fragment in markdown
