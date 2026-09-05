"""The Activity Desk: an append-only timeline, kept apart from the audit chain.

ADR-0008 6 refuses to merge two things that look alike. The audit chain is a
MAC-linked ledger that is **never pruned** (ADR-0003 7) - deleting a link
from the middle is the thing it exists to reveal. A step-by-step activity
timeline is voluminous by nature and needs a retention policy. Put the
timeline in the chain and one of those two properties has to give.

So there are two layers and the boundary is structural:

* **this table** holds every step. It has its own retention
  (:data:`RETAINED_EVENTS`, the ``RETAINED_CHECKS`` pattern), and its rows are
  not chain links - removing one cannot break any MAC.
* **the chain** gets the decision points only, as the five
  :class:`~station_api.evidence.audit.AuditEventName` members H2 added.

:attr:`~station_api.db.models.ActivityEvent.chain_referenced` is what keeps
the two compatible rather than merely adjacent. When a decision point is
written into the chain, the link's ``subject`` is this row's id and the row is
flagged. Retention **and** user-requested deletion both refuse to remove a
flagged row, so "no row the chain refers to may be pruned" is enforced by the
code rather than promised by a comment. A user deleting timeline rows is
itself a decision, and it is recorded as one.

What is never written here
--------------------------
A model's reasoning and a raw provider payload. Not "is redacted first" -
**never written**, because there is no model lane in this build to produce
either (ADR-0008 2) and this table has no column that could hold one. What is
written is a time, the run and task it belongs to, the actor, the kind of
action, the outcome, how long it took, the digest of the artifact or check it
concerns, and one safe sentence.

Five kinds of moment, kept as five actions
-------------------------------------------
ADR-0008 6 names them and they are separate members rather than one
``step_completed`` with a free-text detail: *planned*, *ran*, *check
recorded*, *artifact produced*, *awaiting approval*. Collapsing them is how a
timeline ends up unable to answer "did anything actually get checked?".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from station_api.agent.errors import ActivityError
from station_api.agent.language import assert_no_forbidden_claim
from station_api.db.models import ActivityEvent
from station_api.evidence.audit import AuditChain, AuditEventName
from station_api.evidence.audit_envelope import AuditEnvelopeError
from station_api.logging_setup import redact
from station_api.technocore.projection import safe_display
from station_api.vault.errors import VaultError

#: Rows kept by the retention pass, counting **only** the rows retention is
#: allowed to remove. Chain-referenced rows are kept regardless and are not
#: counted against this number: the policy trims the volume, it does not
#: decide what the chain may refer to.
#:
#: The second sentence used to be false. The keep query took the newest 500
#: rows of *any* kind, so flagged rows - which the delete then refused to
#: touch anyway - crowded out unflagged ones, and a timeline with 500 chain
#: links would have retained nothing else. The behaviour was safe and the
#: sentence was wrong; the query is what changed, because a retention bound
#: that shrinks as the audit chain grows is a bound nobody chose.
RETAINED_EVENTS = 500

#: Longest sentence one row carries. A detail is a sentence, not a payload -
#: ``AuditChain.MAX_DETAIL_CHARS``'s rule, at the same size.
MAX_DETAIL_CHARS = 500

#: Most rows one listing returns. A bound on the read; nothing is pruned by it.
MAX_LISTED_EVENTS = 200


class ActivityActor(StrEnum):
    """Who did the thing. There is deliberately no ``model`` member."""

    #: A person, through a route they invoked.
    USER = "user"
    #: This process, executing a step the person's plan already listed.
    STATION_RUNNER = "station_runner"


class ActivityAction(StrEnum):
    """The kinds of moment the timeline distinguishes."""

    RUN_PLANNED = "run_planned"
    RUN_STARTED = "run_started"
    TOOL_CALLED = "tool_called"
    ARTIFACT_PRODUCED = "artifact_produced"
    CHECK_RECORDED = "check_recorded"
    APPROVAL_AWAITED = "approval_awaited"
    RUN_STOPPED = "run_stopped"
    RUN_RESUMED = "run_resumed"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    #: A request for something outside the approved scope: an unregistered
    #: tool, a path outside the workspace, anything reaching for a secret.
    PERMISSION_DENIED = "permission_denied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXECUTION_UNAVAILABLE = "execution_unavailable"
    ACTIVITY_DELETED = "activity_deleted"
    #: One turn was spent asking the selected model for a plan. Carries what
    #: the provider reported it counted and charged, verbatim - and nothing
    #: about how the model got there: ``reasoning_content`` is discarded in
    #: the protocol adapter and this table has no column that could hold it
    #: (ADR-0008 6).
    MODEL_CALLED = "model_called"
    #: A model turn produced a plan and the plan was recorded. ``PENDING``,
    #: always: a recorded plan has not run, and the row that says a plan
    #: exists must not be readable as the row that says it happened.
    MODEL_PLAN_PROPOSED = "model_plan_proposed"
    #: The model stopped proposing calls, so the planning session is over.
    MODEL_SESSION_ENDED = "model_session_ended"


class ActivityOutcome(StrEnum):
    """What the moment established. ``PENDING`` is not ``OK``."""

    OK = "ok"
    REFUSED = "refused"
    FAILED = "failed"
    PENDING = "pending"


#: Which actions are decision points, and which chain member each becomes.
#:
#: A closed mapping rather than a rule, so adding an action does **not**
#: silently add a chain member: an action absent from this table stays in the
#: timeline only, which is the safe default for a chain that is never pruned.
DECISION_POINTS: dict[ActivityAction, AuditEventName] = {
    ActivityAction.PERMISSION_DENIED: AuditEventName.TOOL_CALL_REFUSED,
    ActivityAction.BUDGET_EXHAUSTED: AuditEventName.BUDGET_EXHAUSTED,
    ActivityAction.EXECUTION_UNAVAILABLE: AuditEventName.EXECUTION_UNAVAILABLE,
    ActivityAction.RUN_FAILED: AuditEventName.TASK_EXECUTION_REFUSED,
    ActivityAction.ACTIVITY_DELETED: AuditEventName.ACTIVITY_DELETED,
}


@dataclass(frozen=True, slots=True)
class ActivityView:
    """One row, detached from the session that read it."""

    id: str
    recorded_at: datetime
    run_id: str
    task_id: str
    actor: ActivityActor
    action: ActivityAction
    outcome: ActivityOutcome
    duration_ms: int
    artifact_sha256: str
    check_sha256: str
    detail: str
    chain_referenced: bool


@dataclass(frozen=True, slots=True)
class DeletionReport:
    """What a user-requested deletion actually did.

    Two counts, never summed. "Twelve rows removed" and "three rows kept
    because the audit chain refers to them" are different facts, and a single
    number would hide the second - which is the one a person needs in order
    to understand why their timeline is not empty.
    """

    deleted: int
    kept_because_chain_referenced: int
    detail: str


def _clean(text: str) -> str:
    """Redact, sweep, bound. **Not** neutralise, and that is the whole point.

    The first version of this function neutralised here as well, and it made
    the guard below a no-op: a forbidden phrase in *our own* sentence was
    masked out on the line before ``assert_no_forbidden_claim`` looked for it,
    so the refusal could never fire and the test that drove it failed. A guard
    placed after a laundering step is not a guard.

    Package E's split says where each half belongs, and this is it:

    * **a claim** - a sentence this product writes - fails closed. That is
      what :func:`assert_no_forbidden_claim` does in :meth:`ActivityLog.record`
      on the string this function returns.
    * **data** - a user's file name, an excerpt from an approved input - is
      neutralised **where it joins one of our sentences**, which is
      ``station_api.agent.service._clean``, before it is ever handed to this
      module. So a person who types the banned words into a file name still
      cannot make the product refuse to show them their own timeline, and our
      own wording is still checked.

    Redaction runs first because it is exact-match and anything that rewrites
    the string could break it; the bound runs last so it cannot cut a
    redaction marker in half.
    """
    return safe_display(redact(text))[:MAX_DETAIL_CHARS]


def _to_view(row: ActivityEvent) -> ActivityView:
    return ActivityView(
        id=row.id,
        recorded_at=row.recorded_at,
        run_id=row.run_id,
        task_id=row.task_id,
        actor=ActivityActor(row.actor),
        action=ActivityAction(row.action),
        outcome=ActivityOutcome(row.outcome),
        duration_ms=row.duration_ms,
        artifact_sha256=row.artifact_sha256,
        check_sha256=row.check_sha256,
        detail=row.detail,
        chain_referenced=row.chain_referenced,
    )


class ActivityLog:
    """Owns activity rows and their relationship with the audit chain."""

    def __init__(self, *, engine: Engine, chain: AuditChain | None) -> None:
        self._engine = engine
        #: ``None`` on a machine where the chain could not be opened - DPAPI
        #: is a Windows facility a self-test can find missing. The timeline
        #: still records; what it must never do is *claim* a decision reached
        #: the chain when it did not, which is why the flag is written only
        #: on the path that actually appended.
        self._chain = chain

    # --- writing -----------------------------------------------------------

    def record(
        self,
        *,
        action: ActivityAction,
        actor: ActivityActor,
        outcome: ActivityOutcome,
        run_id: str = "",
        task_id: str = "",
        duration_ms: int = 0,
        artifact_sha256: str = "",
        check_sha256: str = "",
        detail: str = "",
    ) -> ActivityView:
        """Append one row, and the chain link when the action is a decision.

        The row and its link land in **one transaction**, which is the same
        reason ``AuditChain.append`` takes a session rather than opening one:
        a decision that was recorded in the timeline and not in the chain, or
        the other way round, is a disagreement between two records of the
        same event.

        ``outcome`` has no default. A caller that wanted to log "something
        happened" and let the reader assume the rest would have to type
        ``ActivityOutcome.OK``, and that is then what the timeline shows.
        """
        safe_detail = _clean(detail)
        assert_no_forbidden_claim(safe_detail, where="activity detail")

        row_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        chain_member = DECISION_POINTS.get(action)

        with Session(self._engine) as session, session.begin():
            row = ActivityEvent(
                id=row_id,
                recorded_at=now,
                run_id=run_id,
                task_id=task_id,
                actor=actor.value,
                action=action.value,
                outcome=outcome.value,
                duration_ms=max(0, duration_ms),
                artifact_sha256=artifact_sha256,
                check_sha256=check_sha256,
                detail=safe_detail,
                chain_referenced=False,
            )
            session.add(row)
            session.flush()

            if chain_member is not None and self._chain is not None:
                self._chain.append(
                    session,
                    event=chain_member,
                    subject=row_id,
                    detail=safe_detail,
                )
                # Written only after the append succeeded. The flag is the
                # thing retention trusts, so it must never be set optimistically.
                row.chain_referenced = True

            view = _to_view(row)

        self._prune()
        return view

    def _prune(self) -> None:
        """Keep the newest :data:`RETAINED_EVENTS` rows and delete the rest.

        Chain-referenced rows are excluded from the deletion entirely, not
        merely counted among the survivors: a row an audit link names is a
        row the chain refers to, and ADR-0008 6 makes "nothing the chain
        refers to may be pruned" structural rather than aspirational.

        They are excluded from the **keep query** as well, which is the half
        that was missing. Counting them there would have made the bound mean
        "500 rows minus however many the chain happens to name", so a busy
        chain would have silently shortened the timeline it is meant to sit
        beside.

        Rows are deleted explicitly rather than left to a cascade, for
        ``snapshot._prune``'s reason: SQLite honours ``ON DELETE CASCADE``
        only while a pragma is on, and a retention policy that depends on a
        pragma is a leak waiting to happen.
        """
        with Session(self._engine) as session, session.begin():
            keep = session.scalars(
                select(ActivityEvent.id)
                .where(ActivityEvent.chain_referenced.is_(False))
                .order_by(ActivityEvent.recorded_at.desc(), ActivityEvent.id.desc())
                .limit(RETAINED_EVENTS)
            ).all()
            if not keep:
                # ``not_in(())`` renders as an always-true predicate, which
                # would turn an empty table's retention pass into "delete
                # everything". There is nothing to trim anyway.
                return
            session.execute(
                delete(ActivityEvent)
                .where(ActivityEvent.id.not_in(keep))
                .where(ActivityEvent.chain_referenced.is_(False))
            )

    # --- reading -----------------------------------------------------------

    def list_events(
        self, *, run_id: str = "", limit: int = MAX_LISTED_EVENTS
    ) -> tuple[ActivityView, ...]:
        """Newest first, bounded. A read; changes nothing."""
        bounded = max(1, min(limit, MAX_LISTED_EVENTS))
        with Session(self._engine) as session:
            statement = select(ActivityEvent).order_by(
                ActivityEvent.recorded_at.desc(), ActivityEvent.id.desc()
            )
            if run_id:
                statement = statement.where(ActivityEvent.run_id == run_id)
            rows = session.scalars(statement.limit(bounded)).all()
            return tuple(_to_view(row) for row in rows)

    def count(self) -> int:
        with Session(self._engine) as session:
            return int(session.scalar(select(func.count(ActivityEvent.id))) or 0)

    def count_chain_referenced(self) -> int:
        with Session(self._engine) as session:
            return int(
                session.scalar(
                    select(func.count(ActivityEvent.id)).where(
                        ActivityEvent.chain_referenced.is_(True)
                    )
                )
                or 0
            )

    # --- deletion, which is itself an event --------------------------------

    def delete_events(self, *, run_id: str = "") -> DeletionReport:
        """Remove timeline rows a person asked to remove, and record that.

        Three properties, in the order they matter:

        1. a chain-referenced row is **kept**, and the report says how many
           were kept and why. The alternative - deleting it and letting the
           chain point at nothing - is the silent corruption ADR-0003 7 and
           ADR-0008 6 both refuse.
        2. the deletion is written to the chain as
           :attr:`AuditEventName.ACTIVITY_DELETED`, so a timeline that is
           shorter than it was says who shortened it.
        3. the audit row is written **after** the delete and describes it, so
           a failed delete cannot leave a link claiming rows were removed.
        """
        with Session(self._engine) as session, session.begin():
            statement = select(ActivityEvent)
            if run_id:
                statement = statement.where(ActivityEvent.run_id == run_id)
            rows = session.scalars(statement).all()
            removable = [row.id for row in rows if not row.chain_referenced]
            kept = len(rows) - len(removable)
            if removable:
                session.execute(
                    delete(ActivityEvent).where(ActivityEvent.id.in_(removable))
                )

        detail = (
            f"{len(removable)} aktivite satiri kullanicinin istegiyle silindi; "
            f"{kept} satir audit zincirinin atifta bulundugu icin korundu. "
            "Zincirin atifta bulundugu bir satir hicbir kosulda silinmez."
        )
        try:
            self.record(
                action=ActivityAction.ACTIVITY_DELETED,
                actor=ActivityActor.USER,
                outcome=ActivityOutcome.OK,
                run_id=run_id,
                detail=detail,
            )
        except (AuditEnvelopeError, VaultError, OSError) as exc:
            # The rows are already gone. Refusing to report that would be the
            # worse outcome, so the failure is raised with a reason instead of
            # being swallowed - the caller turns it into a shown refusal.
            raise ActivityError(
                "Satirlar silindi fakat silme islemi audit zincirine "
                "yazilamadi. Bu makinede zincir acilamiyor.",
                reason="activity_deletion_not_chained",
            ) from exc

        return DeletionReport(
            deleted=len(removable),
            kept_because_chain_referenced=kept,
            detail=detail,
        )


__all__ = [
    "DECISION_POINTS",
    "MAX_DETAIL_CHARS",
    "MAX_LISTED_EVENTS",
    "RETAINED_EVENTS",
    "ActivityAction",
    "ActivityActor",
    "ActivityLog",
    "ActivityOutcome",
    "ActivityView",
    "DeletionReport",
]
