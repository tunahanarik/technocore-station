"""SI-210 .. SI-214, SI-230, SI-232 - the registry is closed, compiled in, honest.

ADR-0004 1 settles what a "module" is in this product: a registry record, not
a directory. These tests hold that decision in place from both sides. The
registry may not grow a loading path (charter ADR-017, AGENTS.md 2.9), and it
may not point at code that is not there - an allow-list entry whose target has
gone is a silent widening, which is the lesson
``test_every_reviewed_client_module_actually_exists`` already learned on the
outbound clients.

They also pin the part that is uncomfortable to write down: **three** of Proje
0's nine charter outputs cannot be produced by this build, and one of those
three is refused by policy rather than merely unbuilt. A registry that
reported the lobby greeting as "pending" would be describing a queue that will
never move.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect
from station_api.identity.write_gate import CheckState
from station_api.modules.completion import evaluate_module
from station_api.modules.fields import EvidenceField
from station_api.modules.registry import (
    MODULES,
    POLICY_REFUSED_REQUIREMENTS,
    ModuleId,
    ModuleState,
    get_module,
    requirement_keys,
)

pytestmark = pytest.mark.security

#: The two packages Package F added. Both are scanned as one surface: a
#: loading path that moved from the registry into the task service would be
#: the same hole in a different file.
PACKAGE_F_DIRS = ("modules", "tasks")

#: Modules that would turn a compile-time registry into a loader. ``builtins``
#: is here because it is the doorway to the attribute spelling of every banned
#: name: ``builtins.__import__`` and ``getattr(builtins, "ex" + "ec")`` are the
#: same decision as typing ``__import__``, and the first version of this scan
#: caught neither.
DYNAMIC_LOADING_IMPORTS = (
    "importlib",
    "pkgutil",
    "runpy",
    "imp",
    "pkg_resources",
    "builtins",
)

#: Builtins that turn text into code.
DYNAMIC_LOADING_BUILTINS = ("__import__", "exec", "eval", "compile")

#: The three of those whose *attribute* spelling is banned as well.
#: ``compile`` is deliberately absent, and only ``compile``: ``re.compile`` is
#: a pattern compiler with nothing to do with this rule, and banning
#: ``.compile`` would have failed the test for a reason with no security
#: content. Nothing else on the list has an innocent attribute spelling.
DYNAMIC_LOADING_ATTRIBUTE_BUILTINS = ("__import__", "exec", "eval")

#: The import machinery reachable without importing anything: poking
#: ``sys.modules`` replaces a module object in place, and ``__builtins__``
#: reaches the same namespace ``builtins`` does.
DYNAMIC_LOADING_NAMESPACES = ("sys.modules", "__builtins__", "builtins")

#: Loader entry points. Matched in either spelling: ``from importlib import
#: import_module`` and ``importlib.import_module`` are the same decision.
DYNAMIC_LOADING_FUNCTIONS = (
    "import_module",
    "load_module",
    "iter_modules",
    "walk_packages",
    "entry_points",
    "spec_from_file_location",
    "module_from_spec",
)

#: The schema stage every entry point must open the database at. Written out
#: rather than imported: the number says which release the file on disk was
#: written for, and a constant that derived it from one of the call sites
#: would agree with whichever one drifted (F-10).
CURRENT_SCHEMA_STAGE = 8

#: Proje 0's completion outputs, charter 7.2, in charter order. Written out
#: here rather than imported so a silent reordering or deletion in the
#: registry fails instead of agreeing with itself.
CHARTER_REQUIREMENT_KEYS = (
    "identity_local_only",
    "recovery_paths",
    "restore_test_verified",
    "profile_note_published",
    "lobby_greeting_sent",
    "writes_archived",
    "evidence_levels_shown",
    "module_marked_complete",
    "shared_security_core",
)


def _package_f_sources(api_source_root: Path) -> list[Path]:
    paths: list[Path] = []
    for name in PACKAGE_F_DIRS:
        paths.extend((api_source_root / "station_api" / name).rglob("*.py"))
    assert paths, "the Package F source tree should not be empty"
    return paths


def _dynamic_loading_offenders(source: str, label: str) -> list[str]:
    """Every dynamic-loading construct in one Python source string.

    Four spellings, because the first version of this scan only recognised
    two - a banned import and a banned *call* - and the reviewer walked past
    it three different ways (F-7):

    * a banned import, in either ``import x`` or ``from x import y`` form;
    * a banned **name**, wherever it appears. ``runner = __import__`` and
      ``runner(name)`` on the next line is not a call to ``__import__`` as far
      as the syntax tree is concerned;
    * a banned **attribute**: ``builtins.__import__``, ``mod.exec``,
      ``importlib.import_module``. ``compile`` is exempt here and nowhere
      else, so ``re.compile`` still passes;
    * a banned **namespace**: ``sys.modules[...] = ...`` swaps a module
      without importing anything, and ``getattr(builtins, "ex" + "ec")``
      builds the name at runtime. Both are matched on the unparsed
      expression, which is what makes the assembled-string spelling visible.
    """
    offenders: list[str] = []
    tree = ast.parse(source, filename=label)

    def banned_import(name: str) -> bool:
        return any(
            name == banned or name.startswith(f"{banned}.")
            for banned in DYNAMIC_LOADING_IMPORTS
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if banned_import(alias.name):
                    offenders.append(f"{label}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if banned_import(module):
                offenders.append(f"{label}: import {module}")
            for alias in node.names:
                if alias.name in (
                    DYNAMIC_LOADING_FUNCTIONS + DYNAMIC_LOADING_BUILTINS
                ):
                    offenders.append(f"{label}: import {module}.{alias.name}")
        elif isinstance(node, ast.Name):
            if node.id in DYNAMIC_LOADING_BUILTINS + DYNAMIC_LOADING_FUNCTIONS:
                offenders.append(f"{label}: name {node.id}")
            elif node.id in DYNAMIC_LOADING_NAMESPACES:
                offenders.append(f"{label}: namespace {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr in (
                DYNAMIC_LOADING_ATTRIBUTE_BUILTINS + DYNAMIC_LOADING_FUNCTIONS
            ):
                offenders.append(f"{label}: attribute .{node.attr}")
            else:
                unparsed = ast.unparse(node)
                if any(
                    unparsed == namespace or unparsed.startswith(f"{namespace}.")
                    for namespace in DYNAMIC_LOADING_NAMESPACES
                ):
                    offenders.append(f"{label}: namespace {unparsed}")

    return sorted(set(offenders))


# ---------------------------------------------------------------------------
# The registry is a closed, compile-time set
# ---------------------------------------------------------------------------


def test_the_registry_is_a_closed_set_with_unique_identifiers() -> None:
    identifiers = [record.id for record in MODULES]

    assert len(identifiers) == len(set(identifiers))
    assert set(identifiers) == set(ModuleId)


def test_an_unregistered_module_cannot_be_looked_up() -> None:
    """``get_module`` answers for registry members and raises for anything else.

    A ``StrEnum`` member hashes as its own string, so ``"project_zero"`` does
    resolve - the closed set is the enum, and a name outside it has nowhere to
    land.
    """
    for module_id in ModuleId:
        assert get_module(module_id).id is module_id

    for unknown in ("", "billing", "project_1", "Project_Zero"):
        with pytest.raises(KeyError):
            get_module(unknown)  # type: ignore[arg-type]


def test_no_module_is_ever_loaded_from_disk(api_source_root: Path) -> None:
    """The load-bearing one: there is no plugin path, in either package.

    A registry that can import by name is a registry an attacker can extend by
    writing a file. Charter ADR-017 forbids it and this is what forbidding it
    looks like in code.
    """
    offenders: list[str] = []

    for path in _package_f_sources(api_source_root):
        offenders.extend(
            _dynamic_loading_offenders(path.read_text(encoding="utf-8"), path.name)
        )

    assert offenders == [], f"dynamic module loading in the registry: {offenders}"


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("import-then-attribute", "import builtins\nbuiltins.__import__('os')\n"),
        ("assembled-name", "getattr(builtins, 'ex' + 'ec')('x = 1')\n"),
        ("module-table-poke", "import sys\nsys.modules['station_api.x'] = None\n"),
        ("module-table-read", "loaded = sys.modules['station_api.x']\n"),
        ("builtins-dunder", "__builtins__['exec']('x = 1')\n"),
        ("bare-reference", "runner = __import__\nrunner('os')\n"),
        ("aliased-import", "import importlib.util as u\nu.spec_from_file_location\n"),
        ("from-import", "from importlib import import_module\n"),
        ("attribute-eval", "value = helper.eval('1 + 1')\n"),
        ("plain-exec", "exec('x = 1')\n"),
    ],
)
def test_the_dynamic_loading_scan_catches_the_indirect_spellings(
    label: str, source: str
) -> None:
    """The scan, checked against the ways around it (F-7).

    The comment beside ``DYNAMIC_LOADING_BUILTINS`` used to justify matching
    bare names only by pointing at ``re.compile`` - true of ``compile`` and of
    nothing else on the list. ``builtins.__import__``, an assembled
    ``getattr``, a bare reference and a ``sys.modules`` poke all walked
    through. Each of them is a case here, so the claim the documents make
    about this test is a claim something checks.
    """
    assert _dynamic_loading_offenders(source, label), label


@pytest.mark.parametrize(
    "source",
    [
        "import re\nPATTERN = re.compile('a')\n",
        "from dataclasses import dataclass\n",
        "value = getattr(row, column_name)\n",
        "state = record.state\n",
    ],
)
def test_the_dynamic_loading_scan_leaves_the_innocent_spellings_alone(
    source: str,
) -> None:
    """A scan that flags everything is a scan somebody turns off.

    ``re.compile`` is the case that shaped the rule, and ``getattr`` with a
    computed column name is the pattern ``tasks/service.py`` is built on -
    already fenced by
    ``test_the_only_computed_attribute_names_come_from_the_field_enum``.
    """
    assert _dynamic_loading_offenders(source, "innocent") == []


def test_the_only_computed_attribute_names_come_from_the_field_enum(
    api_source_root: Path,
) -> None:
    """``getattr`` is used, and the names it is given are a closed set.

    The service reads and writes one field group by name, which is what keeps
    the four groups from being four copies of the same block. The names are
    built in ``_field_columns`` from an ``EvidenceField`` member, so the set is
    the enum's; nothing derives an attribute name from a request, a row or a
    file.
    """
    service = (
        api_source_root / "station_api" / "tasks" / "service.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(service)

    builders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_field_columns"
    ]
    assert len(builders) == 1, "exactly one place may build a column name"
    builder = builders[0]

    # Every interpolation in it is the same local, and that local is assigned
    # from the enum member. So the set of attribute names is the enum's.
    interpolated = {
        node.value.id
        for node in ast.walk(builder)
        if isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Name)
    }
    assert interpolated == {"prefix"}, interpolated

    sources = {
        ast.unparse(node.value)
        for node in ast.walk(builder)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "prefix"
            for target in node.targets
        )
    }
    assert sources == {"field.value"}, sources

    # And the resulting names really are the columns the model declares.
    from station_api.db.models import TaskEvidenceOutcome
    from station_api.tasks.service import _field_columns

    declared = set(TaskEvidenceOutcome.__table__.columns.keys())
    for field in EvidenceField:
        assert set(_field_columns(field)) <= declared, field


# ---------------------------------------------------------------------------
# Proje 0 is represented, not moved
# ---------------------------------------------------------------------------


def test_project_zero_is_represented_and_its_code_was_not_moved(
    api_source_root: Path,
) -> None:
    """The registry points; the owners stay where they have always been.

    Moving them would break at least six tests that pin module paths by name
    and would buy no behaviour (ADR-0004 1). So the record names them, and
    this proves each name still resolves to a file - a pointer at nothing is
    worse than no pointer.
    """
    record = get_module(ModuleId.PROJECT_ZERO)

    assert record.state is ModuleState.AVAILABLE
    assert record.owners, "an available module must name the code that owns it"

    for dotted in record.owners:
        path = api_source_root / Path(*dotted.split("."))
        assert path.with_suffix(".py").is_file(), f"{dotted} is registered but missing"


def test_no_module_record_moved_code_into_the_registry_package(
    api_source_root: Path,
) -> None:
    """The registry package holds records, not responsibilities.

    Four files, none of them a service: if identity, compose or evidence logic
    had been dragged in here, "nothing was moved" would have stopped being
    true while the record still said it was.
    """
    modules_dir = api_source_root / "station_api" / "modules"
    names = sorted(path.name for path in modules_dir.glob("*.py"))

    assert names == ["__init__.py", "completion.py", "fields.py", "registry.py"]

    for path in modules_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported = node.module or ""
                assert not imported.startswith("station_api.compose"), path.name
                assert not imported.startswith("station_api.evidence"), path.name
                assert not imported.startswith("station_api.vault"), path.name


def test_planned_modules_name_the_package_that_opens_them() -> None:
    """A registered-but-unbuilt module says so, the ``sections.ts`` way."""
    for record in MODULES:
        if record.state is ModuleState.PLANNED:
            assert record.available_from, record.id
            assert record.owners == (), "a planned module owns no code yet"
            assert record.requirements == ()
        else:
            assert record.available_from == ""


# ---------------------------------------------------------------------------
# The nine charter outputs, and the three that cannot be produced
# ---------------------------------------------------------------------------


def test_project_zero_carries_the_nine_charter_outputs_in_order() -> None:
    assert requirement_keys(ModuleId.PROJECT_ZERO) == CHARTER_REQUIREMENT_KEYS


def test_every_requirement_names_its_evidence_field_and_its_stage() -> None:
    for record in MODULES:
        for requirement in record.requirements:
            assert isinstance(requirement.evidence, EvidenceField)
            assert requirement.stage, requirement.key
            assert requirement.detail.strip(), requirement.key


def test_the_lobby_greeting_is_refused_by_policy_not_merely_unbuilt() -> None:
    """The uncomfortable one, written down.

    Charter output 5 asks for a signed greeting in the lobby. This product
    refuses to write to the lobby at all (``DENIED_ROOMS``, IMP-281, INV-05),
    so the requirement is not waiting for a package - it is closed. A status
    column that showed it as pending would be describing a queue that never
    moves.
    """
    from station_api.technocore.write_targets import DENIED_ROOMS

    assert "lobby" in DENIED_ROOMS
    assert sorted(POLICY_REFUSED_REQUIREMENTS) == ["lobby_greeting_sent"]

    record = get_module(ModuleId.PROJECT_ZERO)
    completion = evaluate_module(record, refs=(), source_version_id="v1")
    lobby = next(check for check in completion.checks if check.key == "lobby_greeting_sent")

    assert lobby.state is CheckState.NOT_IMPLEMENTED
    assert lobby.policy_refused is True
    assert completion.policy_refused_keys == ("lobby_greeting_sent",)


def test_the_unbuilt_requirements_are_exactly_the_three_that_are_unbuilt() -> None:
    """Named, so opening one is a deliberate edit rather than a drift."""
    record = get_module(ModuleId.PROJECT_ZERO)
    completion = evaluate_module(record, refs=(), source_version_id="v1")

    assert set(completion.not_implemented_keys) == {
        "profile_note_published",
        "lobby_greeting_sent",
        "module_marked_complete",
    }


def test_a_module_with_an_unbuilt_requirement_is_never_complete() -> None:
    """``complete`` is derived, and ``not_implemented`` is not a pass."""
    record = get_module(ModuleId.PROJECT_ZERO)
    completion = evaluate_module(record, refs=(), source_version_id="v1")

    assert completion.complete is False
    assert CheckState.NOT_IMPLEMENTED in {check.state for check in completion.checks}


# ---------------------------------------------------------------------------
# The task layer opens no new surface
# ---------------------------------------------------------------------------


def test_the_task_layer_has_no_outbound_surface(api_source_root: Path) -> None:
    """No new client, no socket, no outbound registry (ADR-0004 2).

    ``OUTBOUND_CLIENT_MODULES`` names every reviewed outbound module and the
    comment beside it says why: another entry means another outbound surface.
    This asserts the task packages did not quietly become one by another
    route - by importing a client rather than by importing httpx.

    Package G widened the banned list rather than the permission. The whole
    of ``station_api.opencode`` is here, not just its client module: the
    service reaches the network on the caller's behalf, so a task layer that
    imported *it* would have an outbound surface at one remove, which is
    exactly the shape this scan was written to catch.
    """
    banned = (
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "urllib.request",
        "http.client",
        "socket",
        "station_api.technocore.client",
        "station_api.technocore.write_client",
        "station_api.technocore.evidence_client",
        "station_api.opencode",
    )
    offenders: list[str] = []

    for path in _package_f_sources(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(name == item or name.startswith(f"{item}.") for item in banned):
                    offenders.append(f"{path.name}: {name}")

    assert offenders == [], f"the task layer grew an outbound surface: {offenders}"


def test_the_task_layer_reaches_no_vault_and_no_signer(api_source_root: Path) -> None:
    """No second vault stack (ADR-0004 2). Nothing here touches key material."""
    offenders: list[str] = []

    for path in _package_f_sources(api_source_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported = node.module or ""
                if imported.startswith(("station_api.vault", "station_api.compose")):
                    offenders.append(f"{path.name}: {imported}")

    assert offenders == [], f"the task layer reached the secret boundary: {offenders}"


def test_the_task_gate_reuses_the_write_gates_check_state(
    api_source_root: Path,
) -> None:
    """No second gate: the three-valued state is imported, not redeclared.

    Two enums that agree today is exactly the drift ADR-0004 2 named. The
    task gate follows ``write_gate.evaluate``'s shape and imports its
    ``CheckState``; declaring a parallel one here would be the copy.
    """
    from station_api.tasks import gate as task_gate

    assert task_gate.CheckState is CheckState

    source = (api_source_root / "station_api" / "tasks" / "gate.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    declared = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    assert "CheckState" not in declared


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def test_the_task_tables_have_no_secret_shaped_columns(engine: Engine) -> None:
    """Stricter than the schema-wide rule: ``key`` is refused here too."""
    forbidden = (
        "seed",
        "private",
        "secret",
        "mnemonic",
        "passphrase",
        "password",
        "key",
    )
    inspector = inspect(engine)
    tables = ("task_record", "task_evidence_outcome", "task_state_transition")
    offenders: list[str] = []

    for table in tables:
        assert table in inspector.get_table_names(), f"{table} was not migrated"
        for column in inspector.get_columns(table):
            name = str(column["name"]).lower()
            if any(fragment in name for fragment in forbidden):
                offenders.append(f"{table}.{name}")

    assert offenders == [], f"secret-shaped columns in the task tables: {offenders}"


#: The two calls that carry the release number: the one that stamps it into
#: ``app_metadata`` and the one that shows it to the user.
#:
#: Every root these are scanned in is named in the test below. Adding a new
#: place that opens the database means adding its root there; the browser
#: harness is the fifth such place and was invisible until it was.
STAGE_BEARING_CALLS = ("initialise_database", "ServiceStatus")


def _stage_call_sites(root: Path) -> dict[str, int]:
    """``<dir>/<file>`` to the stage number it names, for every such call."""
    sites: dict[str, int] = {}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func.id if isinstance(node.func, ast.Name) else ""
            if called not in STAGE_BEARING_CALLS:
                continue
            stages = [
                keyword.value.value
                for keyword in node.keywords
                if keyword.arg == "stage"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, int)
            ]
            if stages:
                sites[f"{path.parent.name}/{path.name}:{called}"] = stages[0]
    return sites


def test_every_entry_point_names_the_same_release_stage(
    api_source_root: Path, repo_root: Path
) -> None:
    """SI-232 (F-10). One release, one stage number, every call site.

    ``launcher.py``, ``routes/api.py`` and the test fixture all said ``6``;
    ``cli/__main__.py`` still opened the database at ``stage=3``, three
    releases behind, and nothing said so. The number is stamped into
    ``app_metadata`` and shown on ``/api/app/status``, so an application that
    presents itself as an older release than the one under test is a small lie
    - and this suite has already refused that shape of lie once, one file over.

    Package G adds a **fifth** call site and the scan had to grow with it.
    ``apps/station-web/e2e/harness/serve.py`` opens the same database for the
    browser suite, and it sat outside both roots this test read: four entry
    points were held consistent and the fifth was free to drift. A guard that
    covers all-but-one of a set is the shape of guard that gets believed and
    is not true, so the harness is scanned here rather than trusted.
    """
    application = _stage_call_sites(api_source_root / "station_api")
    harness = _stage_call_sites(repo_root / "apps" / "station-web" / "e2e")
    fixtures = _stage_call_sites(repo_root / "tests")

    assert len(application) >= 3, application
    assert harness, "the browser harness opens the database and must name a stage"
    assert fixtures, "the suite should migrate at the stage under test"
    assert set(application.values()) == {CURRENT_SCHEMA_STAGE}, application
    assert set(harness.values()) == {CURRENT_SCHEMA_STAGE}, harness
    assert CURRENT_SCHEMA_STAGE in set(fixtures.values()), fixtures


def test_migration_0007_changed_no_existing_table(engine: Engine) -> None:
    """Additive only (ADR-0004 11): every earlier table is still there."""
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
    ):
        assert table in names, f"{table} disappeared"


def test_migration_0008_changed_no_existing_table(engine: Engine) -> None:
    """Package G is additive too, and its three tables are named here.

    The same assertion the previous migration got, extended rather than
    replaced: every earlier table survives, and the new ones exist under the
    names the model layer expects.
    """
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
    ):
        assert table in names, f"{table} disappeared"

    for table in (
        "opencode_credential_metadata",
        "opencode_catalog_check",
        "opencode_model_snapshot",
    ):
        assert table in names, f"{table} was not created"


def test_the_opencode_tables_have_no_secret_shaped_columns(engine: Engine) -> None:
    """``key`` included, which is why the credential column is a *path*.

    A table that stores a provider credential's metadata is exactly where a
    column called ``api_key`` would look natural and be catastrophic, so the
    scan that already covers the task tables covers these by name too.
    """
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

    for table in (
        "opencode_credential_metadata",
        "opencode_catalog_check",
        "opencode_model_snapshot",
    ):
        for column in inspector.get_columns(table):
            name = str(column["name"]).lower()
            if any(fragment in name for fragment in forbidden):
                offenders.append(f"{table}.{name}")

    assert offenders == [], f"secret-shaped columns found: {offenders}"
