"""The Package H3 trust boundary, read off the syntax tree.

ADR-0009 5 is the binding half of this file, and it is binding because the
repository has now made the same mistake in two consecutive packages. SI-213
scoped its scan to ``station_api/modules`` and ``station_api/tasks``; H2 wrote
its executor in ``station_api/agent`` and the scan walked past it. H2 then
wrote :mod:`tests.security.test_agent_boundary` for its own tree, scoped the
same way - so ``station_api/proof`` would have been outside **every** boundary
scan in the suite on the day it was created.

The worst version of that is concrete rather than theoretical: a method in
``proof/`` that wrote ``row.state`` would have broken
``THE_ONLY_STATE_WRITER`` silently, and an acceptance route that moved a task
to ``ready_to_publish`` is exactly the method somebody would write. Three
existing scans were widened for that (``test_task_states``,
``test_task_evidence``'s budget scan and ``test_module_registry``'s registry
scans); this file is the fourth item ADR-0009 5 names - a mirror of the agent
package's own boundary scan, over ``station_api/proof`` and the route file in
front of it.

Every scan asserts it actually scanned something, and every scan is driven
against a planted violation. A scan that silently found no files passes
forever and proves nothing, which is the shape of vacuity Package D's
route-path scan turned out to have.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: The package H3 added, and the route file in front of it. Both, because the
#: layer closest to the screen is the one a rule scoped to a package misses.
PROOF_DIR = "proof"
PROOF_ROUTE = Path("routes") / "proof.py"

#: Imports that would give this package an outbound surface, at one remove or
#: none. ``OUTBOUND_CLIENT_MODULES`` stays at five (ADR-0009 11): external
#: sharing goes out through the composer's chain and its reviewed write
#: client, and a proof bundle is handed to the browser rather than posted
#: anywhere.
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
    "station_api.opencode",
)

#: Anything that runs a program or turns text into code. ADR-0009 7 keeps the
#: exit-code field at ``not_implemented``, and this is what makes that a fact
#: about the code rather than a decision somebody could quietly revisit.
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

#: Banned as a **bare name**, wherever it appears.
EXECUTION_NAMES = ("exec", "eval", "compile", "__import__", "system", "popen")

#: Banned as an **attribute** too. ``compile`` is deliberately absent, and
#: only ``compile``: ``re.compile`` is a pattern compiler with nothing to do
#: with this rule. The same exemption the two earlier boundary files draw,
#: drawn the same way here rather than re-argued.
EXECUTION_ATTRIBUTES = ("exec", "eval", "__import__", "system", "popen")

#: Archive handling. ADR-0009 3 records the distinction the repository is
#: entitled to make - zip-slip arises from *unpacking*, not from packing - and
#: then declines to produce an archive anyway, because a zip buys no behaviour
#: here. Producing none means the surface never exists to be argued about.
ARCHIVE_IMPORTS = ("zipfile", "tarfile", "shutil", "gzip", "bz2", "lzma", "zlib")

#: Link creation, and the whole filesystem-writing surface with it.
#:
#: This is stricter than the agent package's rule and deliberately so. The
#: agent *has* a workspace and writes files into it under a containment check;
#: the proof package writes nothing at all (ADR-0009 3), so the honest scan is
#: not "no links" but "no writes" - the bundle exists as bytes in a response
#: and never as a path.
LINK_NAMES = ("symlink", "symlink_to", "hardlink_to", "link")

WRITE_NAMES = (
    "write_text",
    "write_bytes",
    "mkdir",
    "touch",
    "unlink",
    "rmdir",
    "rename",
    "replace",
    "open",
)

#: Scheduling. SI-272's rule, carried into this package: a bundle is built
#: inside the request that asked for it and nothing schedules a follow-up.
SCHEDULING_IMPORTS = ("asyncio", "threading", "sched", "concurrent", "signal")
SCHEDULING_NAMES = ("create_task", "Timer", "Thread", "Process", "call_later")

#: Building or walking a path. Banned even though this package now **reads**
#: artifact bodies, and banned *because* it does.
#:
#: The reading goes through :func:`station_api.agent.workspace.read_text`,
#: which is where the reparse-point walk over the unresolved path, the
#: allow-list rebuild of the name, the containment check and the per-file
#: ceiling live. A second reader here - a ``Path`` joined and opened, a
#: directory iterated, a path resolved - would be a way into a workspace with
#: none of that in front of it, and it would look completely ordinary in a
#: diff. ``read_text`` itself cannot be banned by name (``Path.read_text`` and
#: the workspace's own function are the same word to a syntax tree), so the
#: rule is written on the verbs that would have to appear *around* it.
DIRECT_FILESYSTEM_NAMES = (
    "read_bytes",
    "iterdir",
    "scandir",
    "listdir",
    "glob",
    "rglob",
    "walk",
    "resolve",
    "is_symlink",
    "isjunction",
    "is_dir",
    "is_file",
    "stat",
)

#: The secret boundary. None of these may be imported at all: no signer, no
#: vault, no recovery file, no seed import, no provider credential.
SECRET_IMPORTS = (
    "station_api.vault",
    "station_api.compose",
    "station_api.recovery",
    "station_api.seed_import",
    "station_api.opencode.credential_store",
)


def _proof_sources(api_source_root: Path) -> list[Path]:
    paths = sorted((api_source_root / "station_api" / PROOF_DIR).rglob("*.py"))
    assert paths, "the proof package should not be empty"
    assert len(paths) >= 5, paths
    return paths


def _scanned(api_source_root: Path) -> list[Path]:
    """The proof package plus the route in front of it."""
    return [
        *_proof_sources(api_source_root),
        api_source_root / "station_api" / PROOF_ROUTE,
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
    """Every banned bare name or attribute, wherever it appears.

    Names **and** attributes, because ``runner = exec`` on one line and
    ``runner(text)`` on the next is not a call to ``exec`` as far as the
    syntax tree is concerned, and ``os.system`` is not a bare name at all.
    """
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
# The scan is scanning something
# ---------------------------------------------------------------------------


def test_the_boundary_scan_opens_the_package_and_its_route(
    api_source_root: Path,
) -> None:
    """Guards the guard: a scan that found no files would pass forever.

    Named files rather than a count alone, because a count is satisfied by any
    five files and the point is that *these* are read - the service that could
    grow a writer and the route that sits closest to the screen.
    """
    scanned = _scanned(api_source_root)
    names = {path.name for path in scanned}

    assert {
        "service.py",
        "bundle.py",
        "approvals.py",
        "language.py",
        # The module that reads artifact bodies. It is the one file here that
        # touches a workspace at all, so a scan that did not open it would be
        # missing the only place these rules could be broken.
        "artifacts.py",
    } <= names
    assert scanned[-1].name == "proof.py"
    assert scanned[-1].is_file(), "the route file the scan claims to read is missing"


# ---------------------------------------------------------------------------
# Nothing here runs, packs, links or writes
# ---------------------------------------------------------------------------


def test_the_proof_package_cannot_run_a_program(api_source_root: Path) -> None:
    """ADR-0009 7's structural half.

    The bundle reports ``exit_code`` as ``not_implemented`` and says the
    reason is that nothing runs a check. That sentence is only worth
    something if the package has no way to run one, so this reads the syntax
    tree rather than trusting the absence of a feature.
    """
    paths = _scanned(api_source_root)

    assert _banned_import_offenders(paths, EXECUTION_IMPORTS) == []
    assert _used_names(paths, EXECUTION_NAMES, EXECUTION_ATTRIBUTES) == []


def test_no_archive_is_produced_or_unpacked(api_source_root: Path) -> None:
    """ADR-0009 3: two plain-text formats, and no packing surface at all."""
    assert _banned_import_offenders(_scanned(api_source_root), ARCHIVE_IMPORTS) == []


def test_the_package_writes_no_file_and_creates_no_link(
    api_source_root: Path,
) -> None:
    """The load-bearing one for ADR-0009 3.

    ``downloads.py`` records why the whole product hands files to the browser:
    doing so removes path traversal, symlinks, reparse points and overwrite
    questions from the feature rather than defending against them. That is
    only true of the proof bundle if the package genuinely never writes - so
    the file-writing verbs are refused by name, not just the linking ones.
    """
    paths = _scanned(api_source_root)

    assert _used_names(paths, LINK_NAMES) == []
    assert _used_names(paths, WRITE_NAMES) == []


def test_a_workspace_is_reached_only_through_the_agent_packages_reader(
    api_source_root: Path,
) -> None:
    """The rule that had to be written the day bodies started being carried.

    Before that, "the proof package touches no filesystem" was true and the
    ban on write verbs was the whole story. It reads now - a bundle that
    described a person's report instead of containing it was the defect - and
    the honest question stopped being *whether* it reads and became *through
    what*.

    Two halves. The import has to be the agent package's workspace module,
    which is where containment, the reparse-point walk and the ceilings are;
    and no path-building or path-walking verb may appear anywhere in the
    package, because a second reader assembled here would bypass every one of
    them and would read as unremarkable code.
    """
    paths = _scanned(api_source_root)
    imported: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported |= {name for name in _imported_names(tree) if name}

    assert "station_api.agent.workspace" in imported
    assert _used_names(paths, DIRECT_FILESYSTEM_NAMES) == []
    # Still nothing writes, which is what makes the read the *only* contact.
    assert _used_names(paths, WRITE_NAMES) == []


def test_nothing_here_schedules_anything(api_source_root: Path) -> None:
    """SI-272's rule, carried into H3.

    A bundle is built inside the request that asked for it. There is no timer,
    no thread, no task and no long poll, so "nothing continues after you close
    the window" is a property of the code rather than a promise.
    """
    paths = _scanned(api_source_root)

    assert _banned_import_offenders(paths, SCHEDULING_IMPORTS) == []
    assert _used_names(paths, SCHEDULING_NAMES) == []


# ---------------------------------------------------------------------------
# The surfaces SI-213 closed, closed again over the new tree
# ---------------------------------------------------------------------------


def test_the_proof_package_has_no_outbound_surface(api_source_root: Path) -> None:
    """ADR-0009 11: ``OUTBOUND_CLIENT_MODULES`` stays at five.

    A "share" feature is the most plausible place in this product for a sixth
    outbound client to appear, which is precisely why the ban is written down
    here rather than assumed. Nothing in this package opens a socket, imports
    an HTTP client or reaches one of the five reviewed clients at one remove.
    """
    offenders = _banned_import_offenders(_scanned(api_source_root), OUTBOUND_IMPORTS)

    assert offenders == [], f"the proof package grew an outbound surface: {offenders}"


def test_the_proof_package_reaches_no_signer_vault_or_credential(
    api_source_root: Path,
) -> None:
    """The secret boundary, by name and as a whole prefix.

    Unlike the agent package there is no allow-listed exception here: the
    proof workspace touches no filesystem, so it needs no ACL helper and the
    ``station_api.vault`` prefix is refused entire.
    """
    offenders = _banned_import_offenders(_scanned(api_source_root), SECRET_IMPORTS)

    assert offenders == [], f"the proof package reached the secret boundary: {offenders}"


def test_the_proof_package_declares_no_second_gate(api_source_root: Path) -> None:
    """No parallel ``CheckState``, no parallel write gate, no second policy.

    Every verdict a bundle carries was decided by ``tasks/gate.py`` or
    ``modules/completion.py``. A proof workspace that computed its own would
    be two policies that agree today and drift quietly, which ADR-0004 2 ruled
    out by name.
    """
    declared: set[str] = set()
    for path in _proof_sources(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        declared |= {
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

    assert "CheckState" not in declared
    assert "WriteGateStatus" not in declared
    assert "WriteGateInput" not in declared
    assert "TaskGateStatus" not in declared


def test_the_module_has_no_archive_or_link_creating_helper(
    api_source_root: Path,
) -> None:
    """A test that reads names, which ADR-0009 3 explicitly relies on.

    The ADR's reasoning is that producing no archive means the surface never
    exists. That reasoning is only checkable if something looks at the names
    the package defines, so this does: no function or class here is called
    anything archive-shaped or link-shaped.
    """
    forbidden = ("zip", "archive", "tar", "symlink", "hardlink", "shortcut")
    offenders: list[str] = []
    for path in _scanned(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                lowered = node.name.lower()
                if any(fragment in lowered for fragment in forbidden):
                    offenders.append(f"{path.name}:{node.lineno} {node.name}")

    assert offenders == [], f"an archive- or link-shaped helper appeared: {offenders}"


# ---------------------------------------------------------------------------
# The scans, driven against planted violations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "source", "banned", "attributes"),
    [
        (
            "execution",
            "import subprocess\nrunner = exec\nimport os\nos.system('echo TEST-ONLY')\n",
            EXECUTION_NAMES,
            EXECUTION_ATTRIBUTES,
        ),
        (
            "link-creation",
            "from pathlib import Path\nPath('a').symlink_to('b')\n",
            LINK_NAMES,
            None,
        ),
        (
            "file-write",
            "from pathlib import Path\nPath('a').write_text('TEST-ONLY')\n",
            WRITE_NAMES,
            None,
        ),
        (
            "scheduling",
            "import threading\nthreading.Timer(1, None)\n",
            SCHEDULING_NAMES,
            None,
        ),
        (
            "second-reader",
            "from pathlib import Path\n"
            "body = (Path('root') / 'rapor.json').resolve().read_bytes()\n",
            DIRECT_FILESYSTEM_NAMES,
            None,
        ),
    ],
)
def test_the_name_scans_would_catch_a_planted_call(
    tmp_path: Path,
    label: str,
    source: str,
    banned: tuple[str, ...],
    attributes: tuple[str, ...] | None,
) -> None:
    """Guards the guards, on a throwaway tree so no probe ever ships.

    Four separate rules, four separate probes. A single combined probe would
    pass as soon as *one* of the four scans fired, and the other three could
    have been broken for a release without anybody noticing.
    """
    planted = tmp_path / f"planted_{label}.py"
    planted.write_text(source, encoding="utf-8")

    assert _used_names([planted], banned, attributes) != [], label


@pytest.mark.parametrize(
    ("label", "source", "banned"),
    [
        ("outbound", "import httpx\n", OUTBOUND_IMPORTS),
        (
            "outbound-at-one-remove",
            "from station_api.technocore.write_client import SignedWriteClient\n",
            OUTBOUND_IMPORTS,
        ),
        ("execution", "import subprocess\n", EXECUTION_IMPORTS),
        ("archive", "import zipfile\n", ARCHIVE_IMPORTS),
        ("scheduling", "import asyncio\n", SCHEDULING_IMPORTS),
        (
            "secret",
            "from station_api.vault.service import VaultService\n",
            SECRET_IMPORTS,
        ),
        (
            "credential",
            "from station_api.opencode.credential_store import Store\n",
            SECRET_IMPORTS,
        ),
    ],
)
def test_the_import_scans_would_catch_a_planted_import(
    tmp_path: Path, label: str, source: str, banned: tuple[str, ...]
) -> None:
    """The deny side of every import rule in this file, one probe each."""
    planted = tmp_path / f"planted_{label}.py"
    planted.write_text(source, encoding="utf-8")

    assert _banned_import_offenders([planted], banned) != [], label


def test_the_import_scans_leave_the_packages_real_imports_alone(
    api_source_root: Path,
) -> None:
    """A scan that flagged everything would be a scan somebody turns off.

    The package legitimately imports the agent runtime, the task layer, the
    evidence export's escaper and the single-use token store. None of those is
    an outbound client, an executor, an archive or a secret, and this states
    that the rules above draw the line where it was meant to be drawn rather
    than simply everywhere.
    """
    imported: set[str] = set()
    for path in _proof_sources(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported |= {name for name in _imported_names(tree) if name}

    assert "station_api.agent.service" in imported
    assert "station_api.tasks.service" in imported
    assert "station_api.security.tokens" in imported
    assert _banned_import_offenders(_proof_sources(api_source_root), OUTBOUND_IMPORTS) == []


def test_no_new_migration_was_added_by_this_package() -> None:
    """H3 adds no table, and this asserts *that* rather than a head number.

    Stated rather than left implicit: an acceptance and a share approval are
    the two things this package records, and one goes into a column that has
    existed since migration ``0007`` while the other never leaves process
    memory. A package that quietly added a table would have added a revision
    file.

    The assertion used to read ``get_heads() == ["0009"]``, which said "H3
    added nothing" only for as long as *nobody else* added anything either -
    and H4 then added ``0010`` for the acceptance column, which is a change in
    the agent package and has nothing to do with this one. Naming the
    revisions H3 could have written keeps the claim about H3: a proof-shaped
    revision appearing here is a failure whatever the head happens to be, and
    the head itself is pinned by ``test_agent_boundary`` and
    ``test_database``, which is where a schema-stage decision belongs.
    """
    from station_api.db.migrations_runner import script_directory

    revisions = {
        script.revision: (script.doc or "").lower()
        for script in script_directory().walk_revisions()
    }

    assert len(list(script_directory().get_heads())) == 1, "the chain forked"
    for revision, doc in revisions.items():
        for word in ("proof", "bundle", "share", "approval", "acceptance_record"):
            assert word not in doc, f"{revision} looks like a proof migration: {word}"
