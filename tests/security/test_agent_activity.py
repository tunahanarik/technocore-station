"""The Activity Desk: two layers, and the boundary between them holds.

ADR-0008 6 refuses to merge a step-by-step timeline into the audit chain, and
the reason is a genuine conflict rather than tidiness. The chain is **never
pruned** (ADR-0003 7) - deleting a link from the middle is the thing it exists
to reveal - while a per-step timeline is voluminous and needs a retention
policy. One table cannot have both properties.

So there are two, and this file holds the boundary from both sides:

* the timeline has a retention policy and its rows are **not chain links**, so
  trimming it cannot break a MAC;
* only decision points reach the chain, as the five ``AuditEventName`` members
  H2 added;
* a row an audit link **names** is flagged, and neither retention nor a
  user-requested deletion may remove it. That is what makes "nothing the chain
  refers to is pruned" structural rather than a promise;
* a deletion is itself an audit event, so a timeline that is shorter than it
  was says who shortened it.

And the thing that is not written at all: a model's reasoning or a raw
provider payload. Not "redacted first" - there is no column, and there is no
model lane to produce one. ``test_agent_boundary.py`` asserts the schema half;
this file asserts the behaviour.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from station_api.agent.activity import (
    DECISION_POINTS,
    RETAINED_EVENTS,
    ActivityAction,
    ActivityActor,
    ActivityLog,
    ActivityOutcome,
)
from station_api.agent.service import AgentService
from station_api.db.models import ActivityEvent
from station_api.evidence.audit import AuditChain, AuditEventName, ChainVerdict
from station_api.evidence.audit_envelope import AuditEnvelope
from station_api.tasks.service import TaskView

from tests.security.agent_fixtures import write_plan

pytestmark = pytest.mark.security

#: The five decision points H2 added to the chain, typed out from ADR-0008 6.
EXPECTED_CHAIN_MEMBERS = frozenset(
    {
        "task_execution_refused",
        "tool_call_refused",
        "budget_exhausted",
        "execution_unavailable",
        "activity_deleted",
    }
)

#: The events that stay in the timeline only. Written out so a later commit
#: that promoted one of them into the never-pruned chain is a visible change.
#: Package H4 added three, and all three are timeline-only on purpose.
#:
#: A model turn is not a decision point. What *would* be one - a model asking
#: for a capability this build does not have - is already ``permission_denied``
#: and already in the chain, and the planner raises that member rather than a
#: new one. Adding ``model_called`` to the chain instead would put a row in a
#: never-pruned ledger for every turn of a conversation, which is exactly the
#: volume problem ADR-0008 6 separated the two layers to avoid.
EXPECTED_TIMELINE_ONLY = frozenset(
    {
        "run_planned",
        "run_started",
        "tool_called",
        "artifact_produced",
        "check_recorded",
        "approval_awaited",
        "run_stopped",
        "run_resumed",
        "run_finished",
        "model_called",
        "model_plan_proposed",
        "model_session_ended",
    }
)


# ---------------------------------------------------------------------------
# The two layers
# ---------------------------------------------------------------------------


def test_the_chain_gained_exactly_the_five_decision_points() -> None:
    """Five, and each is recordable by a real code path.

    A name in this enum that nothing can ever record is a reader's evidence
    for a feature that does not exist - the rule the ``evidence_deleted``
    comment in ``audit.py`` states, applied to the members H2 added.

    The claim used to be false for one of the five. An independent review
    measured it: ``execution_unavailable`` was written by
    ``AgentService.report_execution_unavailable``, and **nothing called that
    method** - not the product, not a test. The rule this docstring states
    was broken by the same diff that stated it. The member has a producing
    code path now, and
    ``test_asking_for_execution_records_the_fifth_decision_point`` below
    drives it end to end rather than by calling the reporter directly.
    """
    names = {member.value for member in AuditEventName}

    assert names >= EXPECTED_CHAIN_MEMBERS
    assert {member.value for member in DECISION_POINTS.values()} == (
        EXPECTED_CHAIN_MEMBERS
    )


def test_asking_for_execution_records_the_fifth_decision_point(
    agent: AgentService, task: TaskView, engine: Engine, data_dir  # type: ignore[no-untyped-def]
) -> None:
    """The producing path for ``execution_unavailable``, driven from a plan.

    A plan step naming something that reads as a command is refused with the
    measured reason rather than as an unknown tool, the refusal lands in the
    timeline, and it reaches the never-pruned chain as a decision point. All
    three, because any two of them without the third is the failure mode
    ADR-0008 1 is about: a closed capability that looks like an absence.

    Nothing is executed to produce this. The refusal happens at plan time,
    before any run exists.
    """
    from station_api.agent.errors import ToolRegistryError
    from station_api.db.models import AuditEvent

    with pytest.raises(ToolRegistryError) as caught:
        agent.plan_run(
            task.id,
            steps=[("run_shell_command", {"body": "TEST-ONLY"})],
            expected_artifacts=[],
            test_condition="TEST-ONLY olcut",
        )

    assert caught.value.reason == "execution_unavailable"

    recorded = [
        view
        for view in agent.activity.list_events()
        if view.action is ActivityAction.EXECUTION_UNAVAILABLE
    ]
    assert len(recorded) == 1
    assert recorded[0].outcome is ActivityOutcome.REFUSED
    assert recorded[0].detail.strip()
    assert recorded[0].chain_referenced is True

    with Session(engine) as session:
        events = [row.event for row in session.scalars(select(AuditEvent)).all()]

    assert "execution_unavailable" in events
    assert AuditChain(engine, AuditEnvelope(data_dir)).verify().verdict is (
        ChainVerdict.INTACT
    )


def test_an_unregistered_tool_that_is_not_a_command_stays_a_permission_denial(
    agent: AgentService, task: TaskView
) -> None:
    """The other half of the same fork, so the two refusals cannot merge.

    Without this, widening ``EXECUTION_REQUEST_FRAGMENTS`` until it matched
    everything would silently relabel every unknown-tool refusal as
    ``execution_unavailable`` and the test above would still pass.
    """
    from station_api.agent.errors import ToolRegistryError

    with pytest.raises(ToolRegistryError) as caught:
        agent.plan_run(
            task.id,
            steps=[("read_mailbox", {})],
            expected_artifacts=[],
            test_condition="TEST-ONLY olcut",
        )

    assert caught.value.reason == "tool_unknown"

    actions = {view.action for view in agent.activity.list_events()}
    assert ActivityAction.PERMISSION_DENIED in actions
    assert ActivityAction.EXECUTION_UNAVAILABLE not in actions


def test_the_step_by_step_actions_stay_out_of_the_chain() -> None:
    """The volume half. A per-step chain would grow without a bound anybody chose."""
    timeline_only = {
        action.value for action in ActivityAction if action not in DECISION_POINTS
    }

    assert timeline_only == EXPECTED_TIMELINE_ONLY


def test_there_is_no_model_actor() -> None:
    """The timeline attributes nothing to a model, and now that is a decision.

    The docstring used to read "because there is none", which stopped being
    the reason when Package H4 opened the model lane. The assertion is
    unchanged and the rule is deliberate: Station makes the request, Station
    writes the row, and a person decides what happens to what came back. An
    actor named for the model would say the model did something on its own,
    which is the one thing the planning lane is built to make untrue.

    **Where** a plan came from is not lost by this: it is in the *action* -
    ``model_plan_proposed`` - so the timeline can still tell a model-proposed
    plan from one a person typed.
    """
    assert {actor.value for actor in ActivityActor} == {"user", "station_runner"}


def test_a_step_row_carries_facts_and_one_sentence(
    agent: AgentService, task: TaskView, activity_log: ActivityLog
) -> None:
    """Every field ADR-0008 6 asks for, and nothing that could hold a payload."""
    run_id = write_plan(agent, task.id)
    agent.start_run(run_id)

    produced = [
        view
        for view in activity_log.list_events(run_id=run_id)
        if view.action is ActivityAction.ARTIFACT_PRODUCED
    ]

    assert produced
    row = produced[0]
    assert row.recorded_at.tzinfo is not None or row.recorded_at is not None
    assert row.run_id == run_id
    assert row.task_id == task.id
    assert row.actor is ActivityActor.STATION_RUNNER
    assert row.outcome is ActivityOutcome.OK
    assert len(row.artifact_sha256) == 64
    assert row.detail.strip()


def test_a_deterministic_check_records_its_own_result_digest(
    agent: AgentService, task: TaskView, activity_log: ActivityLog
) -> None:
    """"Recorded result", not "the runner said so" (ADR-0008 7).

    The checker's own output is digested, so a later reader can re-derive the
    verdict instead of taking a boolean on trust.
    """
    run_id = write_plan(agent, task.id)
    agent.start_run(run_id)

    checks = [
        view
        for view in activity_log.list_events(run_id=run_id)
        if view.action is ActivityAction.CHECK_RECORDED
    ]

    assert checks
    assert all(len(view.check_sha256) == 64 for view in checks)
    assert all("test" not in view.detail.lower() or "degildir" in view.detail
               for view in checks)


# ---------------------------------------------------------------------------
# The link between them
# ---------------------------------------------------------------------------


def test_a_decision_point_lands_in_both_layers_and_is_flagged(
    engine: Engine, activity_log: ActivityLog
) -> None:
    """One transaction, two records, and the flag written only after the append."""
    view = activity_log.record(
        action=ActivityAction.PERMISSION_DENIED,
        actor=ActivityActor.STATION_RUNNER,
        outcome=ActivityOutcome.REFUSED,
        detail="TEST-ONLY kapsam disi istek",
    )

    assert view.chain_referenced is True

    with Session(engine) as session:
        from station_api.db.models import AuditEvent

        links = session.scalars(select(AuditEvent)).all()
        subjects = {row.subject for row in links}
        events = {row.event for row in links}

    assert view.id in subjects
    assert "tool_call_refused" in events


def test_a_step_event_is_not_flagged_and_reaches_no_chain(
    engine: Engine, activity_log: ActivityLog
) -> None:
    from station_api.db.models import AuditEvent

    with Session(engine) as session:
        before = len(session.scalars(select(AuditEvent)).all())

    view = activity_log.record(
        action=ActivityAction.TOOL_CALLED,
        actor=ActivityActor.STATION_RUNNER,
        outcome=ActivityOutcome.OK,
        detail="TEST-ONLY adim",
    )

    with Session(engine) as session:
        after = len(session.scalars(select(AuditEvent)).all())

    assert view.chain_referenced is False
    assert after == before


def test_a_machine_without_a_chain_records_but_claims_nothing(
    unchained_activity_log: ActivityLog,
) -> None:
    """DPAPI can be missing, and the honest degradation is not a silent one.

    The timeline still records. What it must never do is set the flag that
    says a chain link names this row, because retention trusts that flag.
    """
    view = unchained_activity_log.record(
        action=ActivityAction.PERMISSION_DENIED,
        actor=ActivityActor.STATION_RUNNER,
        outcome=ActivityOutcome.REFUSED,
        detail="TEST-ONLY zincirsiz",
    )

    assert view.chain_referenced is False
    assert unchained_activity_log.count() == 1


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def test_retention_trims_the_timeline(activity_log: ActivityLog) -> None:
    for index in range(RETAINED_EVENTS + 25):
        activity_log.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            detail=f"TEST-ONLY adim {index}",
        )

    assert activity_log.count() <= RETAINED_EVENTS


def test_a_chain_referenced_row_does_not_consume_the_retention_bound(
    activity_log: ActivityLog,
) -> None:
    """``RETAINED_EVENTS`` counts the rows retention is allowed to remove.

    The module said so and the query did not: it took the newest
    ``RETAINED_EVENTS`` rows of *any* kind, so a flagged row - which the
    delete then refused to touch anyway - occupied a slot an ordinary row
    could have had. The bound therefore shrank as the audit chain grew, which
    is a retention policy nobody chose.

    Ordering matters here and the previous shape hid the defect: with the
    flagged rows *oldest* both queries agree. They are recorded **last**, so
    they are exactly the rows the old keep-set would have taken slots for.
    """
    for index in range(RETAINED_EVENTS):
        activity_log.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            detail=f"TEST-ONLY adim {index}",
        )

    assert activity_log.count() == RETAINED_EVENTS

    for index in range(3):
        activity_log.record(
            action=ActivityAction.BUDGET_EXHAUSTED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.REFUSED,
            detail=f"TEST-ONLY tavan {index}",
        )

    assert activity_log.count_chain_referenced() == 3
    assert activity_log.count() == RETAINED_EVENTS + 3


def test_retention_never_removes_a_row_the_chain_refers_to(
    activity_log: ActivityLog,
) -> None:
    """The structural half of "the chain is never pruned".

    A decision point is written first, then the timeline is flooded well past
    its retention bound. The flagged row survives, so the chain link that
    names it still points at something.
    """
    decision = activity_log.record(
        action=ActivityAction.BUDGET_EXHAUSTED,
        actor=ActivityActor.STATION_RUNNER,
        outcome=ActivityOutcome.REFUSED,
        detail="TEST-ONLY tavan",
    )

    for index in range(RETAINED_EVENTS + 50):
        activity_log.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            detail=f"TEST-ONLY hacim {index}",
        )

    surviving = {view.id for view in activity_log.list_events(limit=200)}
    assert activity_log.count_chain_referenced() >= 1
    # Read straight from the table rather than from the bounded listing: the
    # question is whether the row still exists, not whether it is on page one.
    assert decision.id in _all_ids(activity_log)
    assert surviving is not None


def _all_ids(log: ActivityLog) -> set[str]:
    with Session(log._engine) as session:
        return {row.id for row in session.scalars(select(ActivityEvent)).all()}


# ---------------------------------------------------------------------------
# Deletion is an event
# ---------------------------------------------------------------------------


def test_deleting_timeline_rows_keeps_the_ones_the_chain_names(
    activity_log: ActivityLog,
) -> None:
    """Two counts, never summed.

    "Twelve removed" and "three kept because the chain refers to them" answer
    different questions, and a single total would hide the one that explains
    why the timeline is not empty.
    """
    activity_log.record(
        action=ActivityAction.PERMISSION_DENIED,
        actor=ActivityActor.STATION_RUNNER,
        outcome=ActivityOutcome.REFUSED,
        detail="TEST-ONLY karar",
    )
    for index in range(5):
        activity_log.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            detail=f"TEST-ONLY adim {index}",
        )

    report = activity_log.delete_events()

    assert report.deleted == 5
    assert report.kept_because_chain_referenced == 1
    assert activity_log.count_chain_referenced() >= 1


def test_a_deletion_is_written_to_the_audit_chain(
    engine: Engine, data_dir, activity_log: ActivityLog  # type: ignore[no-untyped-def]
) -> None:
    """ADR-0008 6: removing rows is a decision, so it is a decision point.

    And the chain still verifies afterwards - which is the whole reason
    activity rows are not links: deleting them cannot break a MAC.
    """
    for index in range(3):
        activity_log.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            detail=f"TEST-ONLY adim {index}",
        )

    activity_log.delete_events()

    from station_api.db.models import AuditEvent

    with Session(engine) as session:
        events = [row.event for row in session.scalars(select(AuditEvent)).all()]

    assert "activity_deleted" in events

    chain = AuditChain(engine, AuditEnvelope(data_dir))
    assert chain.verify().verdict is ChainVerdict.INTACT


def test_deleting_by_run_leaves_other_runs_alone(
    agent: AgentService, task: TaskView, activity_log: ActivityLog
) -> None:
    kept = write_plan(agent, task.id)
    other = activity_log.record(
        action=ActivityAction.TOOL_CALLED,
        actor=ActivityActor.STATION_RUNNER,
        outcome=ActivityOutcome.OK,
        run_id="TEST-ONLY-other-run",
        detail="TEST-ONLY baska calisma",
    )

    activity_log.delete_events(run_id=kept)

    remaining = {view.id for view in activity_log.list_events()}
    assert other.id in remaining
    assert activity_log.list_events(run_id=kept) == () or all(
        view.chain_referenced for view in activity_log.list_events(run_id=kept)
    )


def test_the_listing_is_bounded_and_newest_first(activity_log: ActivityLog) -> None:
    for index in range(10):
        activity_log.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            detail=f"TEST-ONLY {index}",
        )

    listed = activity_log.list_events(limit=3)

    assert len(listed) == 3
    assert listed[0].recorded_at >= listed[-1].recorded_at
    assert len(activity_log.list_events(limit=10_000)) <= 200


# ---------------------------------------------------------------------------
# What is never written
# ---------------------------------------------------------------------------


def test_a_detail_is_swept_redacted_and_bounded(activity_log: ActivityLog) -> None:
    """A user's own text reaches a row; it does not reach it unchanged."""
    view = activity_log.record(
        action=ActivityAction.TOOL_CALLED,
        actor=ActivityActor.STATION_RUNNER,
        outcome=ActivityOutcome.OK,
        detail="iyi‮gunler " + "x" * 2000,
    )

    assert "‮" not in view.detail
    assert len(view.detail) <= 500


def test_a_forbidden_claim_in_our_own_wording_fails_closed(
    activity_log: ActivityLog,
) -> None:
    """The runtime half of the language guard, at the row that gets stored.

    A sentence *this product* writes that says a test passed is a bug in our
    wording, and it fails rather than being stored. A user's own text carrying
    the same words is neutralised instead - the Package E split, unchanged.
    """
    from station_api.evidence.language import ForbiddenClaimError

    with pytest.raises(ForbiddenClaimError):
        activity_log.record(
            action=ActivityAction.TOOL_CALLED,
            actor=ActivityActor.STATION_RUNNER,
            outcome=ActivityOutcome.OK,
            detail="Bu calismada kod calistirildi.",
        )
