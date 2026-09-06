"""The Package H4 trust boundary, read off the syntax tree.

``test_agent_boundary.py`` opens with the reason this file exists: a rule
scoped to a directory stops covering the code it was written for the moment
somebody adds a directory. H2 learned it when the state-write scan had to grow
to reach ``agent/``; H3 learned it again for ``proof/``; this is H4's turn, and
the package it adds is the one with the strongest motive to be exempt - it is
the only one that reaches the network.

So every scan the agent package lives under runs here too, over
``station_api/planner`` and ``routes/planner.py``, with **one** difference:
the outbound import is permitted, and permitted by name.

The exemption, stated precisely
--------------------------------
``station_api.opencode`` and nothing else. Not ``httpx``, not any of the five
reviewed clients directly, not ``socket``, not ``ssl``. What this package may
do is *ask the reviewed connection for a turn*; what it may not do is open a
connection of its own, which is why ``OUTBOUND_CLIENT_MODULES`` stays at five
and why ``station_api.opencode.client`` is on the banned list here even though
``station_api.opencode`` is not. A module that imported the client directly
would be building its own request outside the service that holds the
credential, the redaction window and the one-attempt rule.

The load-bearing test in this file is
``test_the_planner_cannot_start_a_run``. Everything else about this package is
a promise that a model proposes rather than acts, and that promise is worth
what the syntax tree says it is worth: there is no reference to ``start_run``
or ``resume_run`` anywhere in the package or its route, so a model-proposed
plan cannot begin without the route a person invokes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

PLANNER_DIR = "planner"
PLANNER_ROUTE = Path("routes") / "planner.py"

#: Imports that would give this package an outbound surface of its **own**.
#:
#: ``station_api.opencode`` is deliberately absent and everything under it that
#: is not the service is deliberately present: the package may ask the
#: reviewed connection, and may not assemble a request beside it.
OUTBOUND_IMPORTS = (
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "urllib.request",
    "http.client",
    "socket",
    "ssl",
    "station_api.technocore.client",
    "station_api.technocore.write_client",
    "station_api.technocore.evidence_client",
    "station_api.workscan.client",
    "station_api.opencode.client",
)

#: The one module outside its own package that this tree may reach for the
#: network, written as an exact allow-list so the exemption cannot widen.
ALLOWED_OUTBOUND_MODULES = frozenset(
    {
        "station_api.opencode.service",
        "station_api.opencode.planner",
        "station_api.opencode.errors",
    }
)

EXECUTION_IMPORTS = (
    "subprocess",
    "multiprocessing",
    "pty",
    "ctypes",
    "importlib",
    "pkgutil",
    "runpy",
    "imp",
    "pkg_resources",
    "builtins",
)

EXECUTION_NAMES = ("exec", "eval", "compile", "__import__", "system", "popen")
EXECUTION_ATTRIBUTES = ("exec", "eval", "__import__", "system", "popen")

ARCHIVE_IMPORTS = ("zipfile", "tarfile", "shutil", "gzip", "bz2", "lzma", "zlib")

LINK_NAMES = ("symlink", "symlink_to", "hardlink_to", "link")

#: SI-272, carried into H4: one turn happens inside the request that asked for
#: it. There is no timer, no thread and no follow-up turn scheduled.
SCHEDULING_IMPORTS = ("asyncio", "threading", "sched", "concurrent", "signal")
SCHEDULING_NAMES = ("create_task", "Timer", "Thread", "Process", "call_later")

#: The secret boundary. ADR-0008 7's list, unchanged - and
#: ``opencode.credential_store`` is on it, which is the sharpest item here:
#: this package is the reason a credential gets used at all, and it still may
#: not touch the envelope. The service opens it, inside its own redaction
#: window, and hands back a parsed answer.
SECRET_IMPORTS = (
    "station_api.vault.service",
    "station_api.vault.dpapi",
    "station_api.vault.passphrase",
    "station_api.vault.paths",
    "station_api.compose",
    "station_api.recovery",
    "station_api.seed_import",
    "station_api.opencode.credential_store",
)

#: Names that would let a model-proposed plan run itself.
RUNNER_ENTRY_POINTS = ("start_run", "resume_run", "request_stop")


def _planner_sources(api_source_root: Path) -> list[Path]:
    paths = sorted((api_source_root / "station_api" / PLANNER_DIR).rglob("*.py"))
    assert paths, "the planner package should not be empty"
    return paths


def _scanned(api_source_root: Path) -> list[Path]:
    return [
        *_planner_sources(api_source_root),
        api_source_root / "station_api" / PLANNER_ROUTE,
    ]


def _imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def _banned_import_offenders(paths: list[Path], banned: tuple[str, ...]) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imported_names(tree):
            if any(name == item or name.startswith(f"{item}.") for item in banned):
                offenders.append(f"{path.name}: {name}")
    return offenders


def _used_names(
    paths: list[Path],
    banned: tuple[str, ...],
    attributes: tuple[str, ...] | None = None,
) -> list[str]:
    attribute_set = banned if attributes is None else attributes
    offenders: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in banned:
                offenders.append(f"{path.name}:{node.lineno} {node.id}")
            if isinstance(node, ast.Attribute) and node.attr in attribute_set:
                offenders.append(f"{path.name}:{node.lineno} .{node.attr}")
    return offenders


# ---------------------------------------------------------------------------
# The model proposes; it cannot act
# ---------------------------------------------------------------------------


def test_the_planner_cannot_start_a_run(api_source_root: Path) -> None:
    """The load-bearing one. A model cannot approve its own plan.

    "A recorded plan waits for a person" is the whole product claim of this
    package, and it is worth exactly what the syntax tree says: there is no
    reference to ``start_run``, ``resume_run`` or ``request_stop`` anywhere in
    the package or in the route in front of it, as a call, as an attribute or
    as a bare name held in a variable.

    A test that only checked *behaviour* would pass on a build where the call
    existed behind a flag nobody set today.
    """
    offenders = _used_names(_scanned(api_source_root), RUNNER_ENTRY_POINTS)

    assert offenders == [], f"the planner grew a way to run its own plan: {offenders}"


def test_the_run_starter_scan_would_see_a_planted_call(tmp_path: Path) -> None:
    """Guards the guard, on a throwaway tree, in the three spellings it needs.

    A direct call, an attribute on a held service, and the bare name assigned
    to a variable and invoked later - the last is the one a scan that only
    looked at ``ast.Call`` would walk straight past.
    """
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def go(agent, run_id):\n"
        "    agent.start_run(run_id)\n"
        "    go_on = resume_run\n"
        "    agent.request_stop(run_id)\n"
        "    return go_on(run_id)\n",
        encoding="utf-8",
    )

    offenders = _used_names([planted], RUNNER_ENTRY_POINTS)

    # The distinct spellings are asserted rather than a count: a scan that saw
    # one name three times would otherwise pass while being blind to the other
    # two, which is the exact shape of vacuity these probes exist to catch.
    assert {item.split()[-1] for item in offenders} == {
        ".start_run",
        "resume_run",
        ".request_stop",
    }, offenders


def test_nothing_here_records_evidence_or_writes_a_state(
    api_source_root: Path,
) -> None:
    """Two capabilities a planning lane must not acquire.

    ``record_evidence`` would let a model's turn assert that its own output
    was checked. A ``.state`` assignment would make this the second state
    writer in a product whose whole task machine rests on there being one
    (SI-226). Neither name appears.
    """
    offenders = _used_names(_scanned(api_source_root), ("record_evidence",))
    assert offenders == [], offenders

    writers: list[str] = []
    for path in _scanned(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    if isinstance(target, ast.Attribute) and target.attr == "state":
                        writers.append(f"{path.name}:{node.lineno}")
    assert writers == [], writers


# ---------------------------------------------------------------------------
# The scans the agent package lives under, over this tree
# ---------------------------------------------------------------------------


def test_the_planner_opens_no_outbound_surface_of_its_own(
    api_source_root: Path,
) -> None:
    """It may ask the reviewed connection; it may not become a sixth one.

    ``station_api.opencode.client`` is banned even though
    ``station_api.opencode`` is not, and that is the whole distinction: a
    module that imported the client directly would assemble its own request
    outside the service that holds the credential, the redaction window and
    the exactly-one-attempt rule.
    """
    offenders = _banned_import_offenders(_scanned(api_source_root), OUTBOUND_IMPORTS)

    assert offenders == [], f"the planner grew its own outbound surface: {offenders}"


def test_the_outbound_exemption_is_an_exact_list_and_is_used(
    api_source_root: Path,
) -> None:
    """The exemption cannot widen quietly, and it is not a rule about nothing."""
    found: set[str] = set()
    for path in _scanned(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imported_names(tree):
            if name.startswith("station_api.opencode"):
                found.add(name)

    assert found <= ALLOWED_OUTBOUND_MODULES, sorted(found - ALLOWED_OUTBOUND_MODULES)
    assert "station_api.opencode.service" in found


def test_the_planner_cannot_run_a_program(api_source_root: Path) -> None:
    """ADR-0008 1, over the newest tree. A proposal is data, never a command."""
    paths = _scanned(api_source_root)

    assert _banned_import_offenders(paths, EXECUTION_IMPORTS) == []
    assert _used_names(paths, EXECUTION_NAMES, EXECUTION_ATTRIBUTES) == []


def test_the_execution_scan_would_catch_a_planted_call(tmp_path: Path) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import subprocess\nrunner = exec\nimport os\nos.system('echo TEST-ONLY')\n",
        encoding="utf-8",
    )

    assert _banned_import_offenders([planted], EXECUTION_IMPORTS) != []
    assert _used_names([planted], EXECUTION_NAMES, EXECUTION_ATTRIBUTES) != []


def test_no_archive_is_ever_unpacked_here(api_source_root: Path) -> None:
    assert _banned_import_offenders(_scanned(api_source_root), ARCHIVE_IMPORTS) == []


def test_the_planner_never_creates_a_link(api_source_root: Path) -> None:
    assert _used_names(_scanned(api_source_root), LINK_NAMES) == []


def test_nothing_here_schedules_a_second_turn(api_source_root: Path) -> None:
    """SI-272, and it is the rule a planning loop is most likely to break.

    A loop that scheduled its own next turn would spend the user's money
    without anybody asking for it, which is the difference between a bounded
    tool and a runaway one.
    """
    paths = _scanned(api_source_root)

    assert _banned_import_offenders(paths, SCHEDULING_IMPORTS) == []
    assert _used_names(paths, SCHEDULING_NAMES) == []


def test_the_planner_reaches_no_signer_vault_or_credential_store(
    api_source_root: Path,
) -> None:
    """The sharpest item on the list is the credential store.

    This package is the reason a provider credential is used at all, and it
    still may not open the envelope. The service does that, inside its own
    redaction window, and hands back a parsed answer.
    """
    offenders = _banned_import_offenders(_scanned(api_source_root), SECRET_IMPORTS)

    assert offenders == [], f"the planner reached the secret boundary: {offenders}"


def test_the_planner_declares_no_second_gate(api_source_root: Path) -> None:
    declared: set[str] = set()
    for path in _planner_sources(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        declared |= {
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

    assert "CheckState" not in declared
    assert "WriteGateStatus" not in declared
    assert "RunCeiling" not in declared


# ---------------------------------------------------------------------------
# Wording
# ---------------------------------------------------------------------------


def test_no_string_literal_in_the_planner_carries_a_forbidden_phrase(
    api_source_root: Path,
) -> None:
    """H2's language rule, over H4's tree.

    The system prompt lives in this package, so this is not a formality: a
    prompt that told the model Station "runs code" would be the product
    over-claiming in the one place a model would then repeat it back.
    """
    from station_api.agent.language import find_forbidden_phrases

    offenders: list[str] = []
    for path in _scanned(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            found = find_forbidden_phrases(node.value)
            if found:
                offenders.append(f"{path.name}:{node.lineno} {found}")

    assert offenders == [], f"forbidden phrases in planner strings: {offenders}"


def test_the_language_scan_is_actually_scanning_something(
    api_source_root: Path,
) -> None:
    """Guards the guard: a scan that found no files would pass forever."""
    scanned = _scanned(api_source_root)

    assert len(scanned) >= 3, scanned
    literals = 0
    for path in scanned:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        literals += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    assert literals > 100, literals


def test_the_system_prompt_states_the_closed_capabilities(
    api_source_root: Path,
) -> None:
    """The prompt has to tell the model the truth about this build.

    Not because a model can be trusted to obey it - the registry is what
    enforces every one of these - but because a prompt that described a
    capability this product does not have would produce proposals that are
    refused for reasons the user then has to decode.
    """
    del api_source_root
    from station_api.planner.service import SYSTEM_PROMPT

    for claim in ("yurutulmez", "arac listesindeki", "insan"):
        assert claim in SYSTEM_PROMPT, claim
    assert not set(SYSTEM_PROMPT) & set("çğıöşüÇĞİÖŞÜ")
