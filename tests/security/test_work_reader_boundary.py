"""The ADR-0014 trust boundary, read off the syntax tree.

``test_planner_boundary.py`` opens with the reason a file like this exists: a
rule scoped to a directory stops covering the code it was written for the
moment somebody adds a directory. ``station_api/workreader`` is the directory
ADR-0014 added, and it is the second one in this product that can reach the
network - so every scan the planning package lives under runs here too, with
the same single exemption and the same exact allow-list.

Why the package exists at all
------------------------------
``test_work_scan_candidates.py::test_the_package_calls_no_model_and_imports_no_completion_path``
says ``station_api/workscan`` imports nothing that can reach a provider. That
test is **unchanged** by ADR-0014 and the sentence it states is still true: the
scan package parses documents, sweeps text, applies the prohibition registry
and builds candidates, and none of that should be able to spend money. So the
money is spent in a package of its own and the scan names only a Protocol.
That is ADR-0013 2's pattern - the rule is not edited to fit the code, the new
fact moves into its own house.

What is load-bearing here
--------------------------
``test_the_reader_cannot_act_on_anything``. Everything else about this package
is the promise that a model **classifies** rather than acts, and that promise
is worth what the syntax tree says it is worth: there is no reference to a
runner entry point, a task producer, a workspace write or an evidence record
anywhere in the tree, so a verdict cannot become anything without going back
through code a person already reviewed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

READER_DIR = "workreader"

#: Imports that would give this package an outbound surface of its **own**.
#:
#: ``station_api.opencode`` is deliberately absent and everything under it that
#: is not the service, the protocol adapter or the errors is deliberately
#: present. The distinction is the same one the planning package draws: this
#: tree may *ask the reviewed connection for a turn*, and may not assemble a
#: request beside it - which is why ``OUTBOUND_CLIENT_MODULES`` stays at five.
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

#: The modules outside its own package this tree may reach for the network,
#: written as an exact allow-list so the exemption cannot widen.
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

#: SI-272, carried into ADR-0014: a turn happens inside the request that asked
#: for it. A scan that scheduled its own next turn would spend the user's money
#: without anybody asking, and the scan surface's whole "no polling" claim
#: would become a claim about the half of the code that does not cost anything.
SCHEDULING_IMPORTS = ("asyncio", "threading", "sched", "concurrent", "signal")
SCHEDULING_NAMES = ("create_task", "Timer", "Thread", "Process", "call_later")

#: The secret boundary. ADR-0008 7's list, unchanged, and
#: ``opencode.credential_store`` is the sharpest item again: this package is a
#: reason a credential gets used, and it still may not touch the envelope.
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

#: Names that would let a verdict do something instead of meaning something.
#:
#: A runner entry point, the two task producers, the workspace writers and the
#: evidence recorder. Each one is a different sentence: a reader that could
#: ``start_run`` would run work nobody approved; one that could ``suggest_task``
#: would open a task from a stranger's line with no person in between; one that
#: could ``write_text`` would put a stranger's line on disk under a name it
#: chose; one that could ``record_evidence`` would let a model attest to its
#: own reading.
ACTION_NAMES = (
    "start_run",
    "resume_run",
    "request_stop",
    "plan_run",
    "suggest_task",
    "open_task",
    "write_text",
    "ensure_workspace",
    "record_evidence",
    "transition",
)

#: File-system access of any kind. There is none, and there is no reason for
#: any: this package turns bytes into two integers.
FILESYSTEM_IMPORTS = ("pathlib", "os", "tempfile", "io", "sqlite3", "sqlalchemy")


def _reader_sources(api_source_root: Path) -> list[Path]:
    paths = sorted((api_source_root / "station_api" / READER_DIR).rglob("*.py"))
    assert paths, "the reader package should not be empty"
    assert len(paths) >= 4, paths
    return paths


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
# The model classifies; it cannot act
# ---------------------------------------------------------------------------


def test_the_reader_cannot_act_on_anything(api_source_root: Path) -> None:
    """The load-bearing one. A verdict is a value, not a consequence.

    Ten names, and none of them appears anywhere in the package - as a call, as
    an attribute on a held service, or as a bare name assigned to a variable
    and invoked later. A test that only checked behaviour would pass on a build
    where any of these sat behind a flag nobody set today.
    """
    offenders = _used_names(_reader_sources(api_source_root), ACTION_NAMES)

    assert offenders == [], f"the reading lane grew a way to act: {offenders}"


def test_the_action_scan_would_see_a_planted_call(tmp_path: Path) -> None:
    """Guards the guard, in the three spellings it needs.

    A direct call, an attribute on a held service, and the bare name held in a
    variable and invoked later - the last is the one a scan that only looked at
    ``ast.Call`` would walk straight past.
    """
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def go(agent, tasks, run_id):\n"
        "    agent.start_run(run_id)\n"
        "    later = suggest_task\n"
        "    tasks.record_evidence(run_id)\n"
        "    return later(run_id)\n",
        encoding="utf-8",
    )

    offenders = _used_names([planted], ACTION_NAMES)

    assert {item.split()[-1] for item in offenders} == {
        ".start_run",
        "suggest_task",
        ".record_evidence",
    }, offenders


def test_the_reader_writes_no_state_and_touches_no_disk(
    api_source_root: Path,
) -> None:
    """Two capabilities a classification lane must not acquire.

    No filesystem and no database import, so a stranger's line cannot be
    written anywhere by this package; and no assignment to a ``.state``
    attribute, so this does not become the second state writer in a product
    whose task machine rests on there being one (SI-226).
    """
    paths = _reader_sources(api_source_root)
    assert _banned_import_offenders(paths, FILESYSTEM_IMPORTS) == []

    writers: list[str] = []
    for path in paths:
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
# The scans the planning package lives under, over this tree
# ---------------------------------------------------------------------------


def test_the_reader_opens_no_outbound_surface_of_its_own(
    api_source_root: Path,
) -> None:
    """It may ask the reviewed connection; it may not become a sixth one."""
    offenders = _banned_import_offenders(
        _reader_sources(api_source_root), OUTBOUND_IMPORTS
    )

    assert offenders == [], f"the reader grew its own outbound surface: {offenders}"


def test_the_outbound_exemption_is_an_exact_list_and_is_used(
    api_source_root: Path,
) -> None:
    """The exemption cannot widen quietly, and it is not a rule about nothing."""
    found: set[str] = set()
    for path in _reader_sources(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imported_names(tree):
            if name.startswith("station_api.opencode"):
                found.add(name)

    assert found <= ALLOWED_OUTBOUND_MODULES, sorted(found - ALLOWED_OUTBOUND_MODULES)
    assert "station_api.opencode.service" in found


def test_the_reader_cannot_run_a_program(api_source_root: Path) -> None:
    """ADR-0008 1, over the newest tree. A verdict is data, never a command."""
    paths = _reader_sources(api_source_root)

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
    assert _banned_import_offenders(_reader_sources(api_source_root), ARCHIVE_IMPORTS) == []


def test_the_reader_never_creates_a_link(api_source_root: Path) -> None:
    assert _used_names(_reader_sources(api_source_root), LINK_NAMES) == []


def test_nothing_here_schedules_a_second_turn(api_source_root: Path) -> None:
    """SI-272, over the lane most likely to break it.

    A reading loop that scheduled its own next turn would spend the user's
    money without anybody asking. The loop this package has is a ``for`` over a
    fixed list of batches with a ceiling check in front of it, and there is no
    import here that could make it anything else.
    """
    paths = _reader_sources(api_source_root)

    assert _banned_import_offenders(paths, SCHEDULING_IMPORTS) == []
    assert _used_names(paths, SCHEDULING_NAMES) == []


def test_the_reader_reaches_no_signer_vault_or_credential_store(
    api_source_root: Path,
) -> None:
    """The credential is opened by the service, inside its redaction window.

    This package is a reason a provider credential is used and it still may not
    touch the envelope: it hands a request to
    ``OpenCodeService.propose_plan`` and gets a parsed answer back.
    """
    offenders = _banned_import_offenders(_reader_sources(api_source_root), SECRET_IMPORTS)

    assert offenders == [], f"the reader reached for a secret: {offenders}"


def test_the_scan_package_still_reaches_no_model(api_source_root: Path) -> None:
    """The property this package exists to preserve, asserted from this side.

    ``test_work_scan_candidates.py`` asserts it over the scan tree. Here it is
    again with the reason attached: if ADR-0014 had been implemented inside
    ``station_api/workscan``, that test would have had to be edited, and
    editing a security test to fit a change is the move this repository has
    spent twelve recorded defects learning not to make.
    """
    offenders = _banned_import_offenders(
        sorted((api_source_root / "station_api" / "workscan").rglob("*.py")),
        ("station_api.opencode", "station_api.workreader"),
    )

    assert offenders == [], f"the scan package can reach a model: {offenders}"
