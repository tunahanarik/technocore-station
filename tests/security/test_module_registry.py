"""SI-210 .. SI-214 - the module registry is closed, compiled in, and honest.

ADR-0004 1 settles what a "module" is in this product: a registry record, not
a directory. These tests hold that decision in place from both sides. The
registry may not grow a loading path (charter ADR-017, AGENTS.md 2.9), and it
may not point at code that is not there - an allow-list entry whose target has
gone is a silent widening, which is the lesson
``test_every_reviewed_client_module_actually_exists`` already learned on the
outbound clients.

They also pin the part that is uncomfortable to write down: two of Proje 0's
nine charter outputs cannot be produced by this build, and one of them is
refused by policy rather than merely unbuilt. A registry that reported the
lobby greeting as "pending" would be describing a queue that will never move.
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

#: Names that would turn a compile-time registry into a loader. Imports and
#: call targets are both checked, because ``from importlib import
#: import_module`` and ``importlib.import_module`` are the same decision.
DYNAMIC_LOADING_IMPORTS = ("importlib", "pkgutil", "runpy", "imp", "pkg_resources")

#: Builtins that turn text into code. Matched as *bare* names only, because
#: ``re.compile`` is a pattern compiler and has nothing to do with this rule -
#: banning the attribute spelling too would have made the test unrunnable for
#: a reason that has no security content.
DYNAMIC_LOADING_BUILTINS = ("__import__", "exec", "eval", "compile")

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


def _forbidden_call(node: ast.Call) -> str:
    """The banned name this call uses, or "" when it uses none."""
    target = node.func
    if isinstance(target, ast.Name):
        if target.id in DYNAMIC_LOADING_BUILTINS + DYNAMIC_LOADING_FUNCTIONS:
            return target.id
    elif isinstance(target, ast.Attribute) and target.attr in DYNAMIC_LOADING_FUNCTIONS:
        return target.attr
    return ""


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
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Call):
                found = _forbidden_call(node)
                if found:
                    offenders.append(f"{path.name}: call {found}")
                continue
            else:
                continue
            for name in names:
                if any(
                    name == banned or name.startswith(f"{banned}.")
                    for banned in DYNAMIC_LOADING_IMPORTS
                ):
                    offenders.append(f"{path.name}: import {name}")

    assert offenders == [], f"dynamic module loading in the registry: {offenders}"


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
# The nine charter outputs, and the two that cannot be produced
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
    """No fourth client, no socket, no outbound registry (ADR-0004 2).

    ``OUTBOUND_CLIENT_MODULES`` is locked at three and the comment beside it
    says why: a fourth entry means a fourth outbound surface. This asserts the
    new packages did not quietly become one by another route.
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
