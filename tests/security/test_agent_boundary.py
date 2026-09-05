"""The Package H2 trust boundary, read off the syntax tree.

ADR-0008 7 asks for one thing in several spellings: the authority a developer
gave a coding assistant during development is **not** inherited by the runtime
agent. SI-213 already said the task layer opens no fourth outbound surface, no
second vault and no second gate, and the scan behind it reads
``station_api/modules`` and ``station_api/tasks``. A new package is outside
that scan, so a new package would have been exempt - which is the way a rule
stops covering the code it was written for.

So the same scans run here over ``station_api/agent`` and over the route file
that sits in front of it, plus three the earlier packages never needed:

* **no execution.** There is no ``subprocess``, no ``os.system``, no ``exec``,
  no ``eval``. The product source has never had one and ADR-0008 1 decides it
  does not acquire one here. This is the assertion that makes
  "``execution_unavailable`` is structural" checkable rather than a claim.
* **no archive path.** No ``zipfile``, ``tarfile``, ``shutil.unpack_archive``
  or ``gzip``. Zip-slip is a bug class you cannot have if you never unpack
  anything, and ADR-0008 5 chose not to have it rather than to defend it.
* **no link creation.** No ``symlink_to``, ``os.symlink``, ``os.link`` or
  ``hardlink_to``. The workspace *refuses* to traverse a reparse point; this
  says it also never makes one.

Every scan asserts it actually scanned something. A scan that silently found
no files passes forever and proves nothing, which is the shape of vacuity
Package D's route-path scan turned out to have.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect

pytestmark = pytest.mark.security

#: The package H2 added, and the route file in front of it. Both, because the
#: layer closest to the screen is the one a rule scoped to a package misses.
AGENT_DIR = "agent"
AGENT_ROUTE = Path("routes") / "agent.py"

#: Imports that would give this package an outbound surface, at one remove or
#: none. ``station_api.opencode`` in full, not just its client: the service
#: reaches the network on a caller's behalf, so importing *it* would be an
#: outbound surface with an extra function call in the way.
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

#: Anything that runs a program or turns text into code.
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
#: with this rule, and banning ``.compile`` would fail the test for a reason
#: with no security content. That is the exemption
#: ``test_module_registry.py`` already draws, drawn the same way here rather
#: than re-argued.
EXECUTION_ATTRIBUTES = ("exec", "eval", "__import__", "system", "popen")

#: Archive handling. Absent by decision, so zip-slip has no surface at all.
ARCHIVE_IMPORTS = ("zipfile", "tarfile", "shutil", "gzip", "bz2", "lzma", "zlib")

#: Link creation. The workspace refuses to *follow* one; this refuses to make
#: one.
LINK_NAMES = ("symlink", "symlink_to", "hardlink_to", "link")

#: Scheduling. SI-272's rule, carried into this package: a run happens inside
#: the request that asked for it and nothing schedules a follow-up.
SCHEDULING_IMPORTS = ("asyncio", "threading", "sched", "concurrent", "signal")
SCHEDULING_NAMES = ("create_task", "Timer", "Thread", "Process", "call_later")

#: The only ``station_api.vault`` modules this package may import.
#:
#: ``windows_acl`` is a filesystem helper that happens to live in the vault
#: directory - it touches no key material - and ``vault.errors`` is exception
#: classes. Written as an exact allow-list rather than a prefix ban with a
#: hole in it, so a later import of ``vault.service`` fails here.
ALLOWED_VAULT_MODULES = frozenset(
    {"station_api.vault.windows_acl", "station_api.vault.errors"}
)

#: The secret boundary proper. None of these may be imported at all.
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

#: The schema stage every entry point opens the database at. Written out
#: rather than imported, for ``CURRENT_SCHEMA_STAGE``'s reason.
#:
#: ``0009`` until Package H4, which added ``0010``: one additive column,
#: ``agent_run.acceptance_json``, carrying the plan's machine-checkable
#: acceptance conditions. Bumping this constant is the point of writing it
#: out - a migration is a change a reviewer has to see, and a head read off
#: the script directory would have agreed with whatever the directory said.
CURRENT_MIGRATION_HEAD = "0010"


def _agent_sources(api_source_root: Path) -> list[Path]:
    paths = sorted((api_source_root / "station_api" / AGENT_DIR).rglob("*.py"))
    assert paths, "the agent package should not be empty"
    assert len(paths) >= 8, paths
    return paths


def _scanned(api_source_root: Path) -> list[Path]:
    """The agent package plus the route in front of it."""
    return [*_agent_sources(api_source_root), api_source_root / "station_api" / AGENT_ROUTE]


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
    ``attributes`` defaults to ``banned`` and exists so one name can be banned
    bare and permitted as an attribute.
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
# Execution is closed, structurally
# ---------------------------------------------------------------------------


def test_the_agent_package_cannot_run_a_program(api_source_root: Path) -> None:
    """The load-bearing one. ``execution_unavailable`` is a fact, not a flag.

    ADR-0008 1 measured Docker Desktop on this machine and decided not to rely
    on it. That decision is only worth anything if the code has no other way
    to run something, so this reads the syntax tree rather than trusting the
    absence of a feature.
    """
    paths = _scanned(api_source_root)

    assert _banned_import_offenders(paths, EXECUTION_IMPORTS) == []
    assert _used_names(paths, EXECUTION_NAMES, EXECUTION_ATTRIBUTES) == []


def test_the_innocent_spelling_of_compile_is_left_alone(
    api_source_root: Path,
) -> None:
    """The exemption is real and is checked, not asserted in a comment.

    ``re.compile`` appears in this package. If ``.compile`` were banned as an
    attribute the scan above would be red for a reason with no security
    content, and the usual repair - deleting the assertion - would take the
    other five names with it.
    """
    offenders = _used_names(_scanned(api_source_root), ("compile",), ("compile",))

    assert offenders, "re.compile should appear, or this exemption is moot"
    assert _used_names(_scanned(api_source_root), (), EXECUTION_ATTRIBUTES) == []


def test_the_execution_scan_would_catch_a_planted_call(tmp_path: Path) -> None:
    """Guards the guard, on a throwaway tree so the probe never ships.

    Four spellings, because a scan that only recognised a direct call would
    walk past three of them: an import, a bare name held in a variable, an
    attribute, and the assembled form.
    """
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import subprocess\n"
        "runner = exec\n"
        "import os\n"
        "os.system('echo TEST-ONLY')\n",
        encoding="utf-8",
    )

    assert _banned_import_offenders([planted], EXECUTION_IMPORTS) != []
    assert _used_names([planted], EXECUTION_NAMES, EXECUTION_ATTRIBUTES) != []


def test_no_archive_is_ever_unpacked(api_source_root: Path) -> None:
    """ADR-0008 5: there is no zip-slip surface because nothing is unpacked."""
    assert _banned_import_offenders(_scanned(api_source_root), ARCHIVE_IMPORTS) == []


def test_the_package_never_creates_a_link(api_source_root: Path) -> None:
    """The other half of the reparse-point defence.

    ``workspace`` refuses to read or write *through* a symlink or a junction.
    This says the package also never makes one - a defence that refuses to
    follow links while happily creating them would be defending against
    somebody else's mistake and not its own.
    """
    assert _used_names(_scanned(api_source_root), LINK_NAMES) == []


def test_nothing_here_schedules_anything(api_source_root: Path) -> None:
    """SI-272's rule, carried into H2.

    A run happens inside the request that asked for it. There is no timer, no
    thread, no task and no long poll, so "nothing continues after you close
    the window" is a property of the code rather than a promise.
    """
    paths = _scanned(api_source_root)

    assert _banned_import_offenders(paths, SCHEDULING_IMPORTS) == []
    assert _used_names(paths, SCHEDULING_NAMES) == []


# ---------------------------------------------------------------------------
# The surfaces SI-213 closed, closed again over the new tree
# ---------------------------------------------------------------------------


def test_the_agent_package_has_no_outbound_surface(api_source_root: Path) -> None:
    """SI-213, over the package that would otherwise have been exempt.

    ``OUTBOUND_CLIENT_MODULES`` stays at five. Nothing here opens a socket,
    imports an HTTP client or reaches one of the reviewed clients at one
    remove.
    """
    offenders = _banned_import_offenders(_scanned(api_source_root), OUTBOUND_IMPORTS)

    assert offenders == [], f"the agent package grew an outbound surface: {offenders}"


def test_the_agent_package_reaches_no_signer_vault_or_credential(
    api_source_root: Path,
) -> None:
    """The secret boundary, by name.

    ADR-0008 7 lists what the runtime agent may not touch: the signer, the
    vault, recovery, a provider credential. Each is refused as an import
    here, so the claim is not "no code path happens to call it today".
    """
    offenders = _banned_import_offenders(_scanned(api_source_root), SECRET_IMPORTS)

    assert offenders == [], f"the agent package reached the secret boundary: {offenders}"


def test_the_only_vault_imports_are_the_two_that_carry_no_secret(
    api_source_root: Path,
) -> None:
    """An exact allow-list, so the exemption cannot widen.

    The workspace needs the Windows ACL helper, which lives under
    ``station_api/vault`` because that is where the vault first needed it. A
    blanket ban would have forced either a duplicate of that ctypes code or a
    quiet prefix exemption; this is the third option - name the two modules
    that are allowed and fail on a third.
    """
    found: set[str] = set()
    for path in _scanned(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imported_names(tree):
            if name.startswith("station_api.vault"):
                found.add(name)

    assert found <= ALLOWED_VAULT_MODULES, sorted(found - ALLOWED_VAULT_MODULES)
    # And the allow-list is used, so this is not a rule about nothing.
    assert "station_api.vault.windows_acl" in found


def test_the_agent_package_declares_no_second_gate(api_source_root: Path) -> None:
    """No parallel ``CheckState``, no parallel write gate, no second policy.

    ADR-0004 2 ruled the duplication out by name and the failure mode it named
    was two enums that agree today. The agent reports its own run phases -
    which are about a run, not about whether anything may leave this machine -
    and declares nothing shaped like the gate.
    """
    declared: set[str] = set()
    for path in _agent_sources(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        declared |= {
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

    assert "CheckState" not in declared
    assert "WriteGateStatus" not in declared
    assert "WriteGateInput" not in declared


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def test_migration_0009_changed_no_existing_table(engine: Engine) -> None:
    """Additive only: every earlier table survives and the three new ones exist."""
    names = set(inspect(engine).get_table_names())

    for table in (
        "app_metadata",
        "identity",
        "secret_metadata",
        "manifest_check",
        "official_source_snapshot",
        "message_nonce_reservation",
        "evidence_record",
        "audit_event",
        "audit_chain_metadata",
        "recovery_record",
        "task_record",
        "task_evidence_outcome",
        "task_state_transition",
        "opencode_credential_metadata",
        "opencode_catalog_check",
        "opencode_model_snapshot",
    ):
        assert table in names, f"{table} disappeared"

    for table in ("agent_run", "agent_run_step", "activity_event"):
        assert table in names, f"{table} was not created"


def test_migration_0010_only_added_a_column(engine: Engine) -> None:
    """H4's revision is one column on one table, and it changed nothing else.

    ``agent_run.acceptance_json`` is where a plan's machine-checkable
    acceptance conditions live, inside ``plan_sha256`` so they cannot be
    loosened after approval. Asserted as *additive*: every column ``0009``
    created is still there with the name it had, and exactly one is new.
    """
    columns = {
        str(column["name"]) for column in inspect(engine).get_columns("agent_run")
    }
    before = {
        "id",
        "task_id",
        "phase",
        "created_at",
        "started_at",
        "finished_at",
        "stop_requested",
        "plan_sha256",
        "test_condition",
        "expected_artifacts",
        "tool_calls_used",
        "elapsed_ms",
        "max_tool_calls",
        "max_wall_clock_seconds",
        "concurrency",
        "detail",
    }

    assert before <= columns, sorted(before - columns)
    assert columns - before == {"acceptance_json"}, sorted(columns - before)


def test_the_agent_tables_have_no_secret_shaped_columns(engine: Engine) -> None:
    """``key`` and ``token`` included, as on the task and OpenCode tables."""
    forbidden = (
        "seed",
        "private",
        "secret",
        "mnemonic",
        "passphrase",
        "password",
        "key",
        "token",
    )
    inspector = inspect(engine)
    offenders: list[str] = []

    for table in ("agent_run", "agent_run_step", "activity_event"):
        assert table in inspector.get_table_names(), f"{table} was not migrated"
        for column in inspector.get_columns(table):
            name = str(column["name"]).lower()
            if any(fragment in name for fragment in forbidden):
                offenders.append(f"{table}.{name}")

    assert offenders == [], f"secret-shaped columns found: {offenders}"


def test_no_agent_table_can_hold_a_model_reasoning_trace(engine: Engine) -> None:
    """ADR-0008 6, as a schema property rather than a redaction promise.

    "The timeline never shows a model's hidden reasoning" is a much weaker
    statement when it means "we strip it before writing" than when it means
    "there is nowhere to put it". This is the second one: adding such a column
    needs a migration a reviewer reads.
    """
    forbidden = (
        "reasoning",
        "thought",
        "prompt",
        "completion",
        "payload",
        "message",
        "content",
        "response_body",
    )
    inspector = inspect(engine)
    offenders: list[str] = []

    for table in ("agent_run", "agent_run_step", "activity_event"):
        for column in inspector.get_columns(table):
            name = str(column["name"]).lower()
            if any(fragment in name for fragment in forbidden):
                offenders.append(f"{table}.{name}")

    assert offenders == [], f"a model-output-shaped column appeared: {offenders}"


def test_the_migration_chain_head_is_the_one_this_package_added() -> None:
    """One head, and it is the one this constant names. A branch would make
    the order ambiguous."""
    from station_api.db.migrations_runner import script_directory

    heads = list(script_directory().get_heads())

    assert heads == [CURRENT_MIGRATION_HEAD], heads
