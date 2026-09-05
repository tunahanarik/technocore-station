"""Shared helpers for the Package H2 tests.

The **fixtures** live in ``conftest.py`` beside the ones for the application
and the client, so a test file uses them by name rather than importing them -
importing a fixture and then naming it as a parameter is a redefinition, and
the linter is right about that. What stays here is the data and the one
builder several files share.

Everything the fixtures build is real: a real database, a real temporary data
directory, real files on disk and real MACs. Nothing is mocked out that could
hide a defect, because containment, retention and the chain link are all
properties of actually doing those things.
"""

from __future__ import annotations

from station_api.agent.service import AgentService

#: Content a task is opened for. Marked so a stray artefact is recognisable.
TEST_ONLY_CONTENT = b"TEST-ONLY task content for the agent runtime, not real work."

#: A plan's recorded success criterion. Recorded, never run - which is the
#: property most of these tests exist to hold in place.
TEST_ONLY_CONDITION = "TEST-ONLY olcut: uretilen rapor JSON olarak ayristirilabilmeli."


def write_plan(
    agent: AgentService,
    task_id: str,
    *,
    name: str = "rapor.json",
    body: str = '{"TEST_ONLY": true}',
    expected: tuple[str, ...] = ("rapor.json",),
) -> str:
    """Record a two-step plan that writes a file and then validates it."""
    view = agent.plan_run(
        task_id,
        steps=[
            ("write_workspace_file", {"name": name, "body": body}),
            ("validate_json_file", {"name": name}),
        ],
        expected_artifacts=list(expected),
        test_condition=TEST_ONLY_CONDITION,
    )
    return view.id
