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

import os
import subprocess
import sys
from pathlib import Path

from station_api.agent.service import AgentService

#: ``mklink``'s host. Read from the environment rather than spelled, and with
#: the documented default when it is unset.
_COMSPEC = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")


def plant_a_real_reparse_point(link: Path, target: Path) -> bool:
    """Create a real link at ``link`` pointing at ``target``; say whether it worked.

    A symbolic link first, because it is the one the standard library can
    make. Where Windows refuses it - developer mode off, which is the common
    case for this product's users - an NTFS junction is created with
    ``mklink /J``, which needs no administrator right.

    It lives here rather than in ``test_agent_workspace.py`` because it is no
    longer that file's alone: an adversarial review of H3 found that a real
    junction inside a task workspace turned ``GET /api/proof/{id}`` into an
    unhandled 500, and driving that needs the same planted point. A helper two
    test files force a monkeypatch around instead of sharing is how a guard
    ends up never meeting a real reparse point - which is the measurement that
    produced this function in the first place.

    ``subprocess`` is forbidden in the **product source**, where
    ``test_agent_boundary.py`` reads the syntax tree to say so. A test may
    spawn one, and several in ``tests/conformance`` already do.
    """
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pass
    else:
        return True

    if sys.platform != "win32" or not target.is_dir():
        return False
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, tmp_path operands
        [_COMSPEC, "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    # Asserted rather than inferred from the exit code: a reparse point the
    # predicate does not recognise would not be driving the guard.
    return result.returncode == 0 and os.path.isjunction(link)

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
