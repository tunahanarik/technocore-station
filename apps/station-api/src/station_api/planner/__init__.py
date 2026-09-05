"""The model planning lane: a model proposes, a person approves, the runner runs.

Package H4. This package is the join between two things that already existed
and had never been connected: the reviewed provider client
(:mod:`station_api.opencode`) and the deterministic tool runner
(:mod:`station_api.agent`). Until now the runner could only carry out a step
list a human had typed, and the client could only fetch a public catalog and
store a key it never used.

Why it is its own package rather than a method on either side
--------------------------------------------------------------
Because of what each side is forbidden to become.

``station_api.agent`` may not acquire an outbound surface. That is not a
convention: ``test_agent_boundary.py`` reads the syntax tree of every file in
that package and of the route in front of it, and refuses an import of
``httpx``, of any reviewed client, and of ``station_api.opencode`` in full -
the last one explicitly, because a service that reaches the network on a
caller's behalf is an outbound surface with one function call in the way. Put
the model call there and the scan is red, and the only way to make it green
would be to weaken the scan.

``station_api.opencode`` may not acquire a task, a run or a workspace. It is
the module that carries the only credential in the application, and every rule
about it - one attempt per metered call, redaction held around the whole
window, no substitution of the chosen model - is easier to hold in a package
that does not also own state.

So the join lives here, in a third package that owns neither, and the
dependency runs one way into each: this package imports both, and neither
imports it. The same shape ``station_api.proof`` has, for the same reason.

What this package is allowed to do, and what it is not
-------------------------------------------------------
* it may **ask** the model for a turn, through
  :meth:`station_api.opencode.service.OpenCodeService.propose_plan`. It opens
  no socket of its own and builds no URL: ``OUTBOUND_CLIENT_MODULES`` stays at
  five, and ``test_planner_boundary.py`` scans this tree the way
  ``test_agent_boundary.py`` scans the agent's;
* it may **translate** what came back into plan steps, by looking every
  proposed call up in the closed tool registry and binding its arguments
  against that tool's declared parameter types. A call the registry does not
  have is a shown refusal, recorded as a permission denial, and the whole
  proposal is dropped - a *partial* plan is not the plan the model proposed
  and approving one would mean approving something nobody wrote;
* it may **record** the result as a plan, through
  :meth:`station_api.agent.service.AgentService.plan_run`, which is the same
  function a person's own plan goes through and which leaves the run in
  ``planned``. **Nothing runs.** Starting is a separate request a person
  makes, exactly as it was before this package existed;
* it may not execute anything, write a task state, record evidence, touch the
  vault, the signer, the recovery format or the credential store, or schedule
  a single thing. There is no timer here and no background task: a turn
  happens inside the request that asked for it.

The loop, and where it stops
-----------------------------
One turn at a time. The tool results of the run a person approved go back as
``role: "tool"`` messages, the model proposes again, and the session ends when
the model **chooses** to stop - ``finish_reason: "stop"``, and nothing else.
Three separate things can stop it earlier, and each says so: the model-call
ceiling (:data:`station_api.agent.budget.CEILING`), the run's own stop flag,
and a provider failure.

A turn can also propose nothing **without** the session ending, and telling
those apart is what :class:`~station_api.planner.service.ProposalOutcome`'s
``truncated`` and ``inconclusive`` members exist for. Every no-call turn used
to be reported as the model having stopped, and the session was closed on the
strength of it; a live run then answered ``finish_reason: "length"`` with the
output ceiling spent to the token, so the model had been cut off rather than
finished - and the person was told it was done and left unable to ask again.

Nothing about the model's reasoning is kept. The only field the measured
response carried that could hold any -``reasoning_content`` - is discarded in
:func:`station_api.opencode.planner.parse_plan_response` before this package
sees the turn, and there is no database column anywhere in this application it
could have been written to.
"""

from station_api.planner.service import (
    MAX_INSTRUCTION_CHARS,
    ModelPlannerService,
    ProposalOutcome,
    ProposalView,
    SessionState,
)

__all__ = [
    "MAX_INSTRUCTION_CHARS",
    "ModelPlannerService",
    "ProposalOutcome",
    "ProposalView",
    "SessionState",
]
