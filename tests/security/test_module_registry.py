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
import dataclasses
from collections.abc import Sequence
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
    ModuleRecord,
    ModuleRequirement,
    ModuleState,
    get_module,
    requirement_keys,
)

pytestmark = pytest.mark.security

#: The three rules :func:`_registry_sources` scopes, named so a call site has
#: to say which one it is scanning for.
#:
#: They used to share one directory list, which is why they shared one hole:
#: widening the helper widened all three, and *not* widening it narrowed all
#: three at once, invisibly. A package can genuinely be outside one of these
#: and inside the other two - ``planner`` is exactly that - and a single list
#: cannot say so, so it said the most permissive thing instead and left the
#: package out of all three.
DYNAMIC_LOADING = "dynamic-loading"
OUTBOUND = "outbound"
SECRET_BOUNDARY = "secret-boundary"
REGISTRY_RULES = (DYNAMIC_LOADING, OUTBOUND, SECRET_BOUNDARY)

#: Every package under ``station_api``, written out.
#:
#: This was three names - ``modules``, ``tasks``, ``proof`` - and the comment
#: that used to sit here explained, correctly and at length, that a scan
#: scoped to a hand-written list stops covering the code it was written for
#: the moment somebody adds a directory. It then left the list at three.
#: ADR-0012 added ``planner`` and ``opencode``, and the hole **was measured**:
#: a file doing ``import importlib`` and ``loader = importlib.import_module``,
#: planted in each of those two packages, left all thirty-seven tests in this
#: file green. That is a plugin loading path in the newest code, which is the
#: single thing charter ADR-017 exists to forbid.
#:
#: So the list is the whole tree now, and the interesting artefact moved to
#: :data:`PACKAGES_OUTSIDE_A_REGISTRY_SCAN` - which says, per rule, which
#: package is outside it and why. ``planner`` is outside **one** of the three;
#: under the old arrangement it was outside all three and nothing said so.
#:
#: Typed out rather than read off the tree, because this is the oracle
#: :func:`test_every_package_is_scanned_or_is_a_written_down_registry_exception`
#: compares the tree against. A tuple derived from ``iterdir`` would agree
#: with whatever it found.
REGISTRY_SCANNED_DIRS = (
    "agent",
    "cli",
    "compose",
    "conformance",
    "db",
    "evidence",
    "identity",
    "modules",
    "opencode",
    "planner",
    "proof",
    "recovery",
    "routes",
    "security",
    "tasks",
    "technocore",
    "vault",
    "workscan",
)

#: Every loose module directly under ``station_api``, written out.
#:
#: The tuple above fixed the eighth and ninth instances of this repository's
#: signature defect and recorded the tenth in prose instead of closing it: the
#: scan unit was the *package*, so a rule violation written into a ``.py`` file
#: sitting directly in ``station_api`` was outside all three rules and outside
#: the budget rule next door, and nothing said so. A note in a comment is not a
#: guard, and **the hole was measured**: four loose modules - one carrying
#: ``import importlib`` and ``importlib.import_module``, one ``import
#: requests``, one ``from station_api.vault.service import VaultService`` and
#: one ``estimated_budget = 10`` - left all 175 tests in this file and in
#: ``test_task_evidence.py`` green.
#:
#: So the loose modules are scan units too. There is no whole-module
#: equivalent of :data:`PACKAGES_OUTSIDE_A_REGISTRY_SCAN`, deliberately: a
#: module is one file, and an exemption keyed to a file name would hand that
#: file every spelling of every rule at once - the shape this tuple exists to
#: close, moved down one level. What a module gets instead is
#: :data:`MODULE_ALLOWANCES`, which permits *named offenders* and nothing else.
#:
#: Typed out rather than read off the tree, for the same reason as the tuple
#: above: this is the oracle
#: :func:`test_every_loose_module_is_scanned_and_every_scanned_module_exists`
#: compares the tree against, and a tuple derived from ``glob`` would agree
#: with whatever it found.
REGISTRY_SCANNED_MODULES = (
    "__init__.py",
    "__main__.py",
    "app.py",
    "config.py",
    "dependencies.py",
    "digests.py",
    "downloads.py",
    "launcher.py",
    "logging_setup.py",
    "resources.py",
    "schemas.py",
    "seed_import.py",
    "single_instance.py",
    "strict_json.py",
)

#: Which loose module may produce which *named* offender, under which rule,
#: and why. A **counted list, not a pattern**, one level narrower than
#: :data:`PACKAGES_OUTSIDE_A_REGISTRY_SCAN`: a package exemption switches a
#: rule off for a directory, an entry here permits one exact string and leaves
#: every other spelling of the same rule red in the same file.
#:
#: That narrowness is the whole design, and ``resources.py`` is why. It calls
#: ``importlib.resources.files("station_api")`` to find the data files this
#: build ships with (ADR-0010 1), which is not the plugin-loading path charter
#: ADR-017 forbids - ``resources`` reads packaged bytes and cannot load
#: arbitrary code. A module-shaped exemption would have said "``resources.py``
#: is outside the dynamic-loading rule" and would then have permitted
#: ``importlib.import_module`` in the same file. This permits the reader and
#: refuses the loader, and
#: :func:`test_the_importlib_allowance_is_the_data_reader_and_not_a_loader`
#: plants the loader in a throwaway copy of that module to prove it.
#:
#: Every entry is driven in both directions by
#: :func:`test_every_module_allowance_is_used_and_is_scoped`: an allowance the
#: module does not use is a permission nobody re-reads, and it is reported.
MODULE_ALLOWANCES: dict[str, dict[str, dict[str, str]]] = {
    "app.py": {
        OUTBOUND: {
            "station_api.technocore.write_client": (
                "The composition root builds the write client and hands it to "
                "``ComposeService``; it is one of the five reviewed outbound "
                "modules and the only one that can send. Constructing the "
                "object the reviewed ``compose`` package is allowed to use is "
                "the wiring, not a sixth surface - ``app.py`` opens no client "
                "of its own and imports no HTTP library, which "
                "``test_the_reviewed_outbound_modules_are_still_five`` below "
                "and ``test_write_gate.py::"
                "test_httpx_is_imported_only_by_the_reviewed_clients`` hold "
                "from the other side."
            ),
            "station_api.opencode.service": (
                "Same sentence for the metered provider connection: this "
                "constructs ``OpenCodeService`` and puts it on ``app.state`` "
                "so the planner and the routes are handed one. The client "
                "underneath it, ``station_api.opencode.client``, is **not** "
                "allowed here - the exact distinction ``planner`` is written "
                "down for above."
            ),
        },
        SECRET_BOUNDARY: {
            "station_api.vault": (
                "``DpapiVault`` is constructed here, once, and handed to "
                "``VaultMessageSigner``. Somebody has to build the vault the "
                "boundary is drawn around, and the assembly point is the one "
                "place that can do it without a second package learning how."
            ),
            "station_api.vault.errors": (
                "``VaultError`` in an ``except`` clause, so a locked or "
                "missing vault degrades to a startup answer instead of a "
                "traceback. The exception type carries no key material - the "
                "same reason ``agent`` is allowed this exact module."
            ),
            "station_api.compose.signer": (
                "``MessageSigner`` for the injection type and "
                "``VaultMessageSigner`` for the default. ``app.py`` is one of "
                "the two modules in the whole tree permitted to name the "
                "signer, and that pair is asserted by "
                ":func:`test_the_signer_is_named_by_exactly_the_modules_"
                "written_down_here` rather than only written here."
            ),
            "station_api.compose.service": (
                "``ComposeService`` is instantiated and registered here. The "
                "composer is the signer's owner; assembling it is what a "
                "composition root is."
            ),
            "station_api.compose.nonce": (
                "``NonceReserver`` is built from the same engine and passed "
                "in, so the composer does not open its own database handle. "
                "It reserves a message nonce and holds no key."
            ),
        },
    },
    "launcher.py": {
        OUTBOUND: {
            "socket": (
                "The **listening** socket, which is the opposite of an "
                "outbound surface. ``reserve_loopback_socket`` binds "
                "``LOOPBACK_HOST`` on port 0 so the operating system picks "
                "the port and uvicorn inherits an already-bound socket - "
                "INV-02 and SI-02, held by ``test_bind.py``. Nothing here "
                "connects anywhere: ``socket.connect`` in this module would "
                "be a different string and would be reported."
            ),
        },
    },
    "resources.py": {
        DYNAMIC_LOADING: {
            "import importlib.resources": (
                "``resources.files(\"station_api\")`` asks the import system "
                "where the package it **already loaded** came from, which is "
                "how ADR-0010 1 replaced ``Path(__file__).parents[4]`` - a "
                "line that resolved correctly only under an editable install "
                "and served a 503 page from a wheel. ``importlib.resources`` "
                "reads packaged data; it has no entry point that turns bytes "
                "into a module, so it is not the loading path ADR-017 "
                "forbids. Every other spelling in this file stays red: plain "
                "``import importlib``, ``importlib.util``, "
                "``import_module`` and ``spec_from_file_location`` are each a "
                "different offender string and none of them is written here."
            ),
        },
    },
}

#: Which package is outside which rule, and why. A **counted list, not a
#: pattern**, and read per rule rather than per package.
#:
#: The dynamic-loading rule has no entry at all, and that is a measurement
#: rather than an omission: no package in this tree loads code from disk, so
#: the strongest form of charter ADR-017 - *nothing here has a loading path* -
#: is what the scan asserts. An entry appearing here later is somebody
#: arguing for one in writing.
#:
#: The other two are layering rules, and a package legitimately outside one is
#: normal. What was not normal is a package outside all three by default.
PACKAGES_OUTSIDE_A_REGISTRY_SCAN: dict[str, dict[str, str]] = {
    "agent": {
        SECRET_BOUNDARY: (
            "Two vault modules and no others: ``vault.errors`` for the "
            "exception type and ``vault.windows_acl`` for the directory ACL "
            "the workspace is created with. Neither carries key material, and "
            "the pair is pinned as an exact allow-list by "
            "``test_agent_boundary.py::"
            "test_the_only_vault_imports_are_the_two_that_carry_no_secret``."
        ),
    },
    "cli": {
        SECRET_BOUNDARY: (
            "Seed import from the command line. Writing the vault is the one "
            "thing this entry point does, so a rule that forbade it would "
            "forbid the package."
        ),
    },
    "compose": {
        OUTBOUND: (
            "The write path. ``service.py`` imports "
            "``technocore.write_client`` - one of the five reviewed outbound "
            "modules, and the only one that can send - because sending an "
            "approved message is what this package is."
        ),
        SECRET_BOUNDARY: (
            "It **is** the signer. ``signer.py`` opens the vault to sign, and "
            "``station_api.compose`` is on the banned prefix list precisely "
            "so nothing else does."
        ),
    },
    "conformance": {},
    "db": {},
    "evidence": {
        OUTBOUND: (
            "``service.py`` imports ``technocore.evidence_client``, a "
            "reviewed read client, to fetch the archived send a "
            "``public_share`` record points at (ADR-0009 1). It reads; it "
            "opens no client of its own."
        ),
        SECRET_BOUNDARY: (
            "``audit_envelope.py`` seals the audit chain with the vault-held "
            "key. An audit trail anybody could rewrite is not one, so this is "
            "the package's purpose rather than a reach past its boundary."
        ),
    },
    "identity": {
        SECRET_BOUNDARY: (
            "The seed lifecycle. It creates the vault, opens it with a "
            "passphrase and closes it; it is the package the boundary is "
            "drawn around."
        ),
    },
    "modules": {},
    "opencode": {
        OUTBOUND: (
            "The provider connection itself. ``client.py`` is one of the five "
            "modules ``OUTBOUND_CLIENT_MODULES`` names, and this scan exists "
            "to stop a *sixth* appearing - not to forbid the five. Everything "
            "else on the offender list for this package is "
            "``station_api.opencode`` importing itself."
        ),
        SECRET_BOUNDARY: (
            "``credential_store.py`` keeps the provider key in DPAPI, which "
            "is the reason ADR-0012 could authorise a metered call at all. "
            "The key is read inside the service's redaction window and never "
            "leaves it; ``test_opencode_leakage.py`` is what holds that."
        ),
    },
    "planner": {
        OUTBOUND: (
            "The one entry here that is a *permission* rather than a "
            "description of a package's job, so it is the narrowest. The "
            "model lane may **ask** the reviewed connection for a turn "
            "through ``opencode.service``; it may not assemble a request "
            "beside it. ``station_api.opencode.client`` is banned even though "
            "``station_api.opencode`` is not, and "
            "``test_planner_boundary.py::"
            "test_the_outbound_exemption_is_an_exact_list_and_is_used`` holds "
            "the exemption to an exact list and requires it to be used. "
            "``OUTBOUND_CLIENT_MODULES`` stays at five (ADR-0012 4), pinned "
            "below by :func:`test_the_reviewed_outbound_modules_are_still_"
            "five`. This package is inside the other two rules, which is the "
            "whole reason the rules were separated."
        ),
    },
    "proof": {},
    "recovery": {
        SECRET_BOUNDARY: (
            "``format.py`` needs ``vault.passphrase`` for the KDF policy a "
            "``.tcrec`` file is encrypted under. Reusing the vault's own "
            "derivation is the alternative to writing a second one, which is "
            "the failure ADR-0004 2 names."
        ),
    },
    "routes": {
        OUTBOUND: (
            "The HTTP surface. A route hands a request to whichever service "
            "owns a connection and serialises the answer; the layering that "
            "keeps it from holding one itself is pinned elsewhere."
        ),
        SECRET_BOUNDARY: (
            "``identity.py`` and ``compose.py`` take a passphrase or an "
            "approval off a request and pass it straight down. The value is "
            "not stored, logged or returned - ``test_no_secret_fields.py`` "
            "and ``test_seed_leakage.py`` are what hold that, and they are "
            "stronger than an import ban."
        ),
    },
    "security": {},
    "tasks": {},
    "technocore": {
        OUTBOUND: (
            "The read-only Technocore client. Three of the five reviewed "
            "outbound modules live here; forbidding them would forbid the "
            "package."
        ),
        SECRET_BOUNDARY: (
            "``service.py`` reads ``compose.approvals`` to answer whether a "
            "write was approved. It reads the approval record, not the key: "
            "``compose.signer`` is imported by exactly two modules in the "
            "tree and this is not one of them, pinned below."
        ),
    },
    "vault": {
        SECRET_BOUNDARY: (
            "It **is** the vault. Every offender in this package is "
            "``station_api.vault`` importing its own modules, and "
            "``station_api.vault`` is on the banned prefix list so that "
            "nothing outside it does. Scanning the package the boundary is "
            "drawn around would report the boundary as a breach of itself."
        ),
    },
    "workscan": {
        OUTBOUND: (
            "``client.py`` is the fifth reviewed outbound module - the "
            "read-only public room scan. Same reason as ``technocore``: the "
            "rule bans a sixth client, not the five that were reviewed."
        ),
    },
}

#: The five reviewed outbound modules, as ``httpx`` importers.
#:
#: Every ``outbound`` reason above reduces to "this package's outbound reach
#: is one of the five, and the scan exists to stop a sixth". That sentence is
#: pinned here rather than only written: ADR-0012 4 says
#: ``OUTBOUND_CLIENT_MODULES`` stays at five, and a sixth module importing
#: ``httpx`` anywhere in the tree fails this file as well as
#: ``test_write_gate.py``, which is where the constant itself lives.
MODULES_THAT_OPEN_A_CONNECTION = (
    "opencode/client.py",
    "technocore/client.py",
    "technocore/evidence_client.py",
    "technocore/write_client.py",
    "workscan/client.py",
)

#: Every module that imports the signer.
#:
#: The ``secret-boundary`` reasons say, one way or another, that an exempt
#: package touches the vault for a named purpose and none of them signs. That
#: is the half a sentence cannot keep true on its own, so it is asserted:
#: ``compose.signer`` is named by the composer that owns it and by the
#: application wiring that hands it in, and by nothing else.
MODULES_THAT_NAME_THE_SIGNER = ("app.py", "compose/service.py")

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
CURRENT_SCHEMA_STAGE = 11

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


def _registry_sources(api_source_root: Path, rule: str) -> list[Path]:
    """Every file one registry-boundary rule opens.

    ``rule`` is required rather than defaulted: the three rules have
    different, written-down exceptions, and a call site that did not have to
    name one would silently get whichever scope was widest.

    Two kinds of scan unit, because the tree has two: a package, which a rule
    can be switched off for with a written reason, and a loose module, which
    it cannot - a loose module is always opened and gets named allowances
    instead. ``is_file`` rather than a bare append so a throwaway tree that
    contains only packages scans cleanly; the tuple is checked against the
    real tree by
    :func:`test_every_loose_module_is_scanned_and_every_scanned_module_exists`.
    """
    assert rule in REGISTRY_RULES, rule
    root = api_source_root / "station_api"
    paths: list[Path] = []
    for name in REGISTRY_SCANNED_DIRS:
        if rule in PACKAGES_OUTSIDE_A_REGISTRY_SCAN.get(name, {}):
            continue
        paths.extend((root / name).rglob("*.py"))
    paths.extend(root / name for name in REGISTRY_SCANNED_MODULES if (root / name).is_file())
    assert paths, "the scanned source tree should not be empty"
    return paths


def _scope_of(api_source_root: Path, path: Path) -> str:
    """The scan unit a file belongs to: a package name, or a module file name.

    ``station_api/tasks/service.py`` is ``tasks``; ``station_api/schemas.py``
    is ``schemas.py``. One helper for both because an allowance is looked up
    the same way whichever kind of unit granted it.
    """
    return path.relative_to(api_source_root / "station_api").parts[0]


def _allowances(api_source_root: Path, path: Path, rule: str) -> frozenset[str]:
    """The named offenders one file may produce under one rule."""
    return frozenset(MODULE_ALLOWANCES.get(_scope_of(api_source_root, path), {}).get(rule, {}))


def _loose_modules(api_source_root: Path) -> set[str]:
    """Every ``.py`` file directly under ``station_api``.

    Read off the tree rather than listed, for the reason :func:`_packages`
    gives: a guard built out of the list cannot see what the list omits.
    """
    root = api_source_root / "station_api"
    return {entry.name for entry in root.glob("*.py") if entry.is_file()}


def _packages(api_source_root: Path) -> set[str]:
    """Every Python package directly under ``station_api``.

    Read off the tree rather than listed, because the whole point of the
    guard below is that a list is what went wrong. Same helper, same reason,
    as ``test_task_states.py``'s.
    """
    root = api_source_root / "station_api"
    return {
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "__init__.py").is_file()
    }


def _modules_importing(api_source_root: Path, module: str) -> list[str]:
    """Every module under ``station_api`` that imports ``module``, by name.

    Read off the syntax tree rather than by searching the text, for the reason
    ``test_task_states.py`` gives about ``TaskRecord``: a *comment* naming a
    module is not a reference to it, and a test that cannot tell the
    difference teaches people to stop writing the comments.
    """
    naming: list[str] = []
    root = api_source_root / "station_api"
    package, _, member = module.rpartition(".")
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = _imported_names(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == package:
                names.extend(
                    module for alias in node.names if alias.name == member
                )
        if any(name == module or name.startswith(f"{module}.") for name in names):
            naming.append(str(path.relative_to(root)).replace("\\", "/"))
    return naming


#: Imports that would give a scanned package an outbound surface, at one
#: remove or none. The whole of ``station_api.opencode``, not just its client:
#: the service reaches the network on a caller's behalf, so importing *it*
#: would be an outbound surface with an extra function call in the way.
OUTBOUND_IMPORTS = (
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
    "station_api.workscan.client",
    "station_api.opencode",
)

#: Prefixes no scanned package may import: the vault stack and the signer.
SECRET_BOUNDARY_PREFIXES = ("station_api.vault", "station_api.compose")


def _imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def _outbound_offenders(root: Path) -> list[str]:
    offenders: list[str] = []
    for path in _registry_sources(root, OUTBOUND):
        allowed = _allowances(root, path, OUTBOUND)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imported_names(tree):
            if name in allowed:
                continue
            if any(
                name == item or name.startswith(f"{item}.")
                for item in OUTBOUND_IMPORTS
            ):
                offenders.append(f"{path.name}: {name}")
    return offenders


def _secret_boundary_offenders(root: Path) -> list[str]:
    offenders: list[str] = []
    for path in _registry_sources(root, SECRET_BOUNDARY):
        allowed = _allowances(root, path, SECRET_BOUNDARY)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imported_names(tree):
            if name in allowed:
                continue
            if name.startswith(SECRET_BOUNDARY_PREFIXES):
                offenders.append(f"{path.name}: {name}")
    return offenders


def _dynamic_loading_offenders(
    source: str, label: str, allowed: frozenset[str] = frozenset()
) -> list[str]:
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

    ``from x import y`` is reported **member by member** - ``import
    importlib.resources``, not ``import importlib`` - so an allowance can name
    one member of a banned package without covering the package. That is a
    refinement of the label, never of the verdict: a banned module still
    produces at least one offender per ``from`` statement, and ``import x``
    still reports the module it names.

    ``allowed`` is the set of offender strings, minus the ``label`` prefix,
    one file may produce. It is empty by default, so a call site that does not
    ask for a permission does not get one.
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
                offenders.extend(
                    f"{label}: import {module}.{alias.name}" for alias in node.names
                )
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

    prefix = f"{label}: "
    return sorted(
        offender
        for offender in set(offenders)
        if offender.removeprefix(prefix) not in allowed
    )


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

    for path in _registry_sources(api_source_root, DYNAMIC_LOADING):
        offenders.extend(
            _dynamic_loading_offenders(
                path.read_text(encoding="utf-8"),
                path.name,
                _allowances(api_source_root, path, DYNAMIC_LOADING),
            )
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


def _planned_contract_offenders(records: Sequence[ModuleRecord]) -> list[str]:
    """Every record that breaks the planned/available contract.

    Extracted from the test below by Package H3, and the extraction is the
    point. ``proof_workspace`` was the last ``planned`` record; opening it
    left the ``if record.state is ModuleState.PLANNED`` branch with nothing to
    match, so three assertions stopped executing and the test went on passing.
    That is the ``HIDDEN_SECTIONS`` shape and it gets the ADR-0009 2 answer:
    the contract becomes a function, the registry is checked against it, and
    the function is **driven** over records built in the test - including a
    valid planned one, so a checker that rejected everything would fail too.
    """
    offenders: list[str] = []
    for record in records:
        if record.state is ModuleState.PLANNED:
            if not record.available_from:
                offenders.append(f"{record.id}: planned without available_from")
            if record.owners:
                offenders.append(f"{record.id}: a planned module owns no code yet")
            if record.requirements:
                offenders.append(f"{record.id}: a planned module has no requirements")
        elif record.available_from:
            offenders.append(f"{record.id}: available but names an opening package")
    return offenders


def test_the_registry_satisfies_the_planned_module_contract() -> None:
    """A registered-but-unbuilt module says so, the ``sections.ts`` way."""
    assert _planned_contract_offenders(MODULES) == []


def test_no_module_is_registered_as_planned_any_more() -> None:
    """The named claim, so the empty branch above is stated rather than implied.

    Package H1 opened ``work_scan``, H2 opened ``agent_workspace`` and H3
    opened ``proof_workspace`` - the last one. A reader of the test above
    would otherwise have no way to tell "every planned record satisfies the
    contract" from "there are no planned records", and those are very
    different sentences. This is the second one, said out loud.

    A package that registers a new planned module makes this test red on
    purpose: the assertion is then updated, and updating it is the moment
    somebody re-reads the contract.
    """
    planned = [record.id for record in MODULES if record.state is ModuleState.PLANNED]

    assert planned == [], planned
    assert {record.state for record in MODULES} == {ModuleState.AVAILABLE}
    assert all(record.available_from == "" for record in MODULES)
    assert all(record.owners for record in MODULES)
    assert all(record.requirements for record in MODULES)


def test_the_planned_module_contract_would_catch_a_record_that_breaks_it() -> None:
    """The mechanism, driven on records built here so no probe ever ships.

    The permitted case is checked **first**. Without it a contract function
    that reported every record as an offender would pass the four refusals
    below and prove nothing - the way a driven mutation goes quietly wrong.
    """
    valid_planned = ModuleRecord(
        id=ModuleId.PROOF_WORKSPACE,
        name="TEST-ONLY",
        purpose="TEST-ONLY",
        state=ModuleState.PLANNED,
        owners=(),
        requirements=(),
        available_from="TEST-ONLY-package",
    )
    assert _planned_contract_offenders([valid_planned]) == []

    requirement = ModuleRequirement(
        key="test_only",
        detail="TEST-ONLY",
        evidence=EvidenceField.TASK_OUTCOME,
        stage="-",
        implemented=False,
    )
    broken = {
        "planned without available_from": dataclasses.replace(
            valid_planned, available_from=""
        ),
        "planned but owns code": dataclasses.replace(
            valid_planned, owners=("station_api.proof.service",)
        ),
        "planned but carries requirements": dataclasses.replace(
            valid_planned, requirements=(requirement,)
        ),
        "available but names an opening package": dataclasses.replace(
            valid_planned, state=ModuleState.AVAILABLE
        ),
    }
    for label, record in broken.items():
        assert _planned_contract_offenders([record]) != [], label


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
    offenders = _outbound_offenders(api_source_root)

    assert offenders == [], f"the scanned layer grew an outbound surface: {offenders}"


def test_the_task_layer_reaches_no_vault_and_no_signer(api_source_root: Path) -> None:
    """No second vault stack (ADR-0004 2). Nothing here touches key material."""
    offenders = _secret_boundary_offenders(api_source_root)

    assert offenders == [], f"the scanned layer reached the secret boundary: {offenders}"


def test_the_registry_scans_reach_the_proof_package(
    api_source_root: Path, tmp_path: Path
) -> None:
    """The H3 extension of :data:`REGISTRY_SCANNED_DIRS`, driven (ADR-0009 5).

    ``proof`` is inside all three rules and stays inside all three, so this
    still proves the widening is real in both directions: the scans open files
    under ``station_api/proof``, and a planted violation in a throwaway
    ``proof`` directory is reported rather than walked past.

    Without this, "the scan covers proof" would rest on a tuple literal that
    nothing checks - which is exactly how ``PACKAGE_F_DIRS`` came to exclude
    the package that mattered, and how the tuple this replaced came to exclude
    ``planner`` and ``opencode``.
    """
    for rule in REGISTRY_RULES:
        scanned = _registry_sources(api_source_root, rule)
        proof_files = [path for path in scanned if path.parent.name == "proof"]

        assert len(proof_files) >= 4, (rule, proof_files)
        assert {"service.py", "bundle.py"} <= {path.name for path in proof_files}

    planted_dir = tmp_path / "station_api" / "proof"
    planted_dir.mkdir(parents=True)
    for name in ("modules", "tasks"):
        (tmp_path / "station_api" / name).mkdir(parents=True)
    (planted_dir / "planted.py").write_text(
        "import importlib\n"
        "import httpx\n"
        "from station_api.vault.service import VaultService\n"
        "loader = importlib.import_module\n",
        encoding="utf-8",
    )

    dynamic = _dynamic_loading_offenders(
        (planted_dir / "planted.py").read_text(encoding="utf-8"), "planted.py"
    )
    assert dynamic != [], "the dynamic-loading scan cannot see a planted loader"
    assert _outbound_offenders(tmp_path) != []
    assert _secret_boundary_offenders(tmp_path) != []


@pytest.mark.parametrize("rule", REGISTRY_RULES)
def test_the_newest_packages_are_inside_the_rules_that_apply_to_them(
    rule: str, api_source_root: Path
) -> None:
    """ADR-0012's two packages, per rule, measured rather than asserted once.

    ``planner`` and ``opencode`` were outside all three rules for a whole
    release. They are now inside every rule they are not written down as an
    exception to, and this reads the scan's own file list to say so - a tuple
    entry that is misspelled, or a package later renamed, opens zero files and
    would otherwise leave every assertion in this file green.
    """
    opened = {
        path.relative_to(api_source_root / "station_api").parts[0]
        for path in _registry_sources(api_source_root, rule)
    }
    for package in ("planner", "opencode"):
        exempt = rule in PACKAGES_OUTSIDE_A_REGISTRY_SCAN.get(package, {})
        assert (package in opened) is not exempt, (
            f"{package} is {'exempt from' if exempt else 'inside'} {rule} but "
            f"the scan {'opened' if package in opened else 'opened no'} files "
            "for it"
        )
    assert "planner" in opened or rule == OUTBOUND
    assert "modules" in opened and "tasks" in opened and "proof" in opened


def _rule_offenders(rule: str, root: Path) -> list[str]:
    """One rule's offenders over a tree, addressed by rule name."""
    if rule == DYNAMIC_LOADING:
        return [
            offender
            for path in _registry_sources(root, DYNAMIC_LOADING)
            for offender in _dynamic_loading_offenders(
                path.read_text(encoding="utf-8"),
                path.name,
                _allowances(root, path, DYNAMIC_LOADING),
            )
        ]
    if rule == OUTBOUND:
        return _outbound_offenders(root)
    return _secret_boundary_offenders(root)


@pytest.mark.parametrize("package", REGISTRY_SCANNED_DIRS)
@pytest.mark.parametrize("rule", REGISTRY_RULES)
def test_a_planted_violation_is_reported_from_every_scanned_package(
    rule: str, package: str, tmp_path: Path
) -> None:
    """Each rule, driven once per directory it claims to cover.

    The proof test above plants in one directory and that is the directory
    nobody was ever going to forget. ``rglob`` on a directory that does not
    exist returns nothing rather than raising, so an entry typed wrongly in
    :data:`REGISTRY_SCANNED_DIRS` widens the scan by exactly zero files and
    nothing says so.

    So every package gets its own planted violation of every rule, in its own
    throwaway tree, and the verdict has to match what the exemption table
    claims: reported where the package is scanned, and **silently walked past
    where it is exempt**. The second half is what makes an exemption a
    measured fact rather than a dictionary entry - a reason written for a rule
    the scan applies anyway would fail here.
    """
    planted = {
        DYNAMIC_LOADING: "import importlib\nloader = importlib.import_module\n",
        OUTBOUND: "import httpx\n",
        SECRET_BOUNDARY: "from station_api.vault.service import VaultService\n",
    }[rule]
    for name in REGISTRY_SCANNED_DIRS:
        directory = tmp_path / "station_api" / name
        directory.mkdir(parents=True, exist_ok=True)
        # One innocent file everywhere, so an exempt package produces an empty
        # result because the scan skipped it rather than because the throwaway
        # tree had nothing in it. ``_registry_sources`` refuses to report on an
        # empty tree at all, which is the guard that would otherwise be doing
        # the work here.
        (directory / "benign.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "station_api" / package / "planted.py").write_text(
        planted, encoding="utf-8"
    )

    exempt = rule in PACKAGES_OUTSIDE_A_REGISTRY_SCAN.get(package, {})
    offenders = _rule_offenders(rule, tmp_path)

    if exempt:
        assert offenders == [], (
            f"{package} is written down as outside the {rule} scan, but the "
            f"scan opened it anyway: {offenders}"
        )
    else:
        assert offenders != [], (
            f"the {rule} scan claims to cover {package} and did not report a "
            "violation planted there"
        )


def test_every_scanned_registry_directory_is_a_real_package(
    api_source_root: Path,
) -> None:
    """The tuple, checked against the tree it names.

    Half of the failure above: a directory in the tuple that is not a package
    in the repository is a scan of nothing, reported as a scan.
    """
    missing = sorted(set(REGISTRY_SCANNED_DIRS) - _packages(api_source_root))

    assert not missing, (
        "REGISTRY_SCANNED_DIRS names directories that are not packages under "
        f"station_api; the scans open nothing for them: {missing}"
    )


def test_every_package_is_scanned_or_is_a_written_down_registry_exception(
    api_source_root: Path,
) -> None:
    """The guard that does not read the list it is guarding.

    Every other test in this section iterates :data:`REGISTRY_SCANNED_DIRS`,
    so every one of them is blind in exactly the way that let ``planner`` and
    ``opencode`` sit outside all three registry rules for a whole release. A
    guard built out of the list cannot see what the list omits.

    This one walks ``apps/station-api/src/station_api`` instead, and it checks
    the pair in both directions:

    * a package the tuple does not name is the growth case - the next model
      lane, arriving with nobody remembering to widen anything;
    * a package the tuple names that is not in the tree, or an exception
      written for a package that no longer exists, or for a rule that is not
      one of the three, is the staleness case.

    The per-rule exemptions are checked against the tree too: an exemption
    whose reason is blank, or which is written for a package outside the
    scanned tuple, is a permission nobody can find.
    """
    packages = _packages(api_source_root)
    scanned = set(REGISTRY_SCANNED_DIRS)

    unexplained = sorted(packages - scanned)
    assert not unexplained, (
        "these packages are outside every registry-boundary scan and nobody "
        f"wrote down why: {unexplained}. Add them to REGISTRY_SCANNED_DIRS, "
        "and if one of the three rules genuinely does not apply, say so in "
        "PACKAGES_OUTSIDE_A_REGISTRY_SCAN with the reason."
    )

    gone = sorted(scanned - packages)
    assert not gone, (
        "REGISTRY_SCANNED_DIRS names packages that no longer exist; the "
        f"scans open nothing for them: {gone}"
    )

    stale = sorted(set(PACKAGES_OUTSIDE_A_REGISTRY_SCAN) - packages)
    assert not stale, (
        "these packages are written down as registry-scan exceptions but no "
        f"longer exist: {stale}"
    )

    for package, exemptions in PACKAGES_OUTSIDE_A_REGISTRY_SCAN.items():
        assert package in scanned, package
        for rule, reason in exemptions.items():
            assert rule in REGISTRY_RULES, (package, rule)
            assert reason.strip(), (package, rule)


@pytest.mark.parametrize("rule", REGISTRY_RULES)
def test_no_exemption_is_written_for_a_package_that_does_not_need_one(
    rule: str, api_source_root: Path
) -> None:
    """The staleness half, and the one a reason decays into a name through.

    An exemption is a hole somebody argued for. A hole nobody needs any more
    is a hole nobody re-reads, and it stays open for the next import that
    happens to land in that package. So each exemption is driven: the package
    is scanned *as if it were not exempt*, and it has to actually offend.

    ``dynamic-loading`` has no exemptions at all, which makes this a
    parametrised test with an empty inner loop for one of its three cases -
    and that is stated rather than hidden: the assertion below requires the
    rule with no exemptions to have none, so emptying the other two would
    fail here instead of quietly passing.
    """
    exempt = sorted(
        package
        for package, rules in PACKAGES_OUTSIDE_A_REGISTRY_SCAN.items()
        if rule in rules
    )
    if rule is DYNAMIC_LOADING:
        assert exempt == [], (
            "somebody has written down a package that may load code from "
            f"disk: {exempt}. That is charter ADR-017's one prohibition."
        )
        return

    assert exempt, f"{rule} claims exemptions it does not have"
    for package in exempt:
        root = api_source_root / "station_api" / package
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for name in _imported_names(tree):
                if rule is OUTBOUND and any(
                    name == item or name.startswith(f"{item}.")
                    for item in OUTBOUND_IMPORTS
                ):
                    offenders.append(f"{path.name}: {name}")
                if rule is SECRET_BOUNDARY and name.startswith(
                    SECRET_BOUNDARY_PREFIXES
                ):
                    offenders.append(f"{path.name}: {name}")
        assert offenders, (
            f"{package} is written down as outside the {rule} scan but no "
            "longer offends it; delete the exemption and let the scan cover "
            "the package"
        )


def _unfiltered_offenders(api_source_root: Path, path: Path, rule: str) -> set[str]:
    """One rule's offenders in one file **before** its allowances apply.

    The allowance tests need to see what a permission is actually permitting;
    a set computed after filtering would be empty by construction and would
    agree with any allowance at all.
    """
    source = path.read_text(encoding="utf-8")
    if rule == DYNAMIC_LOADING:
        prefix = f"{path.name}: "
        return {
            offender.removeprefix(prefix)
            for offender in _dynamic_loading_offenders(source, path.name)
        }
    names = _imported_names(ast.parse(source, filename=str(path)))
    if rule == OUTBOUND:
        return {
            name
            for name in names
            if any(
                name == item or name.startswith(f"{item}.")
                for item in OUTBOUND_IMPORTS
            )
        }
    return {name for name in names if name.startswith(SECRET_BOUNDARY_PREFIXES)}


def test_every_loose_module_is_scanned_and_every_scanned_module_exists(
    api_source_root: Path,
) -> None:
    """The tenth instance, closed: the guard that does not read its own list.

    :func:`test_every_package_is_scanned_or_is_a_written_down_registry_exception`
    walks the tree for *directories* and was written because a list cannot see
    what it omits. It left the same defect one level up. The fourteen loose
    modules - ``app.py``, ``schemas.py``, ``resources.py`` and the rest - sat
    directly under ``station_api`` and were therefore outside all three
    registry rules and outside the budget rule next door, and the previous
    version of this file said so in a comment instead of checking it.

    So this walks ``apps/station-api/src/station_api`` for ``*.py`` and
    checks the pair in both directions:

    * a module the tuple does not name is the growth case - the next helper
      dropped beside ``app.py``, with nobody remembering to widen anything;
    * a name in the tuple with no file behind it is the staleness case, and
      it matters more here than for packages: :func:`_registry_sources` uses
      ``is_file`` for modules exactly as ``rglob`` swallows a missing
      directory, so a misspelling widens the scan by zero files and says
      nothing.

    There is deliberately no whole-module exemption table to check. A module
    is one file, so switching a rule off for it would grant that file every
    spelling of the rule at once; what a module can have is a named allowance
    in :data:`MODULE_ALLOWANCES`, and that is driven separately below.
    """
    modules = _loose_modules(api_source_root)
    scanned = set(REGISTRY_SCANNED_MODULES)

    unexplained = sorted(modules - scanned)
    assert not unexplained, (
        "these loose modules sit directly under station_api and are outside "
        f"every registry-boundary scan: {unexplained}. Add them to "
        "REGISTRY_SCANNED_MODULES, and if the module legitimately produces an "
        "offender under one of the three rules, permit that exact offender in "
        "MODULE_ALLOWANCES with the reason."
    )

    gone = sorted(scanned - modules)
    assert not gone, (
        "REGISTRY_SCANNED_MODULES names modules that no longer exist; the "
        f"scans open nothing for them: {gone}"
    )

    for rule in REGISTRY_RULES:
        opened = {
            path.name
            for path in _registry_sources(api_source_root, rule)
            if path.parent == api_source_root / "station_api"
        }
        assert opened == scanned, (rule, sorted(scanned - opened))


@pytest.mark.parametrize("module", REGISTRY_SCANNED_MODULES)
@pytest.mark.parametrize("rule", REGISTRY_RULES)
def test_a_planted_violation_is_reported_from_every_scanned_loose_module(
    rule: str, module: str, tmp_path: Path
) -> None:
    """Each rule, driven once per loose module it claims to cover.

    The package version of this test is what proved
    :data:`REGISTRY_SCANNED_DIRS` was real rather than decorative. This is the
    same measurement for the fourteen files the package version cannot see,
    and it is the test that would have failed on the day the tenth instance of
    this defect was written down instead of fixed.

    No module is exempt from any rule, so every case here has to report. The
    planted violation is chosen to be outside every allowance the real module
    holds - ``httpx`` is not ``app.py``'s reviewed write client,
    ``station_api.vault.service`` is not ``station_api.vault``, and
    ``importlib.import_module`` is not ``importlib.resources`` - so a
    permission that had quietly widened into a module-shaped exemption fails
    here.
    """
    planted = {
        DYNAMIC_LOADING: "import importlib\nloader = importlib.import_module\n",
        OUTBOUND: "import httpx\n",
        SECRET_BOUNDARY: "from station_api.vault.service import VaultService\n",
    }[rule]
    root = tmp_path / "station_api"
    root.mkdir(parents=True)
    # One innocent file per loose module, so an empty result would mean the
    # scan skipped the planted one rather than that the tree was empty.
    for name in REGISTRY_SCANNED_MODULES:
        (root / name).write_text("value = 1\n", encoding="utf-8")
    (root / module).write_text(planted, encoding="utf-8")

    offenders = _rule_offenders(rule, tmp_path)

    assert offenders != [], (
        f"the {rule} scan claims to cover the loose module {module} and did "
        "not report a violation planted there"
    )
    assert all(offender.startswith(f"{module}: ") for offender in offenders), offenders


def test_every_module_allowance_is_used_and_is_scoped(
    api_source_root: Path,
) -> None:
    """The named allowances, checked in both directions.

    An allowance nobody uses is a permission sitting open for whoever needs
    one next, and it reads as a rule while being a hole - the way a list of
    reasons decays into a list of names. So each allowance has to be a string
    the module really produces, each module has to be one the scan opens, each
    rule has to be one of the three, and each reason has to be written.

    This is ``test_task_evidence.py``'s
    ``test_every_package_budget_allowance_is_used_and_is_scoped``, applied to
    the scan unit that test could not see either.
    """
    for module, rules in MODULE_ALLOWANCES.items():
        assert module in REGISTRY_SCANNED_MODULES, (
            f"{module} has registry allowances but is not scanned; an "
            "allowance in an unscanned module permits nothing and hides that "
            "it permits nothing"
        )
        path = api_source_root / "station_api" / module
        assert path.is_file(), module
        for rule, names in rules.items():
            assert rule in REGISTRY_RULES, (module, rule)
            assert names, (module, rule)
            produced = _unfiltered_offenders(api_source_root, path, rule)
            stale = sorted(set(names) - produced)
            assert not stale, (
                f"{module} no longer produces these {rule} offenders, so the "
                f"allowance is open for nothing: {stale}"
            )
            for reason in names.values():
                assert reason.strip(), (module, rule)


def test_the_importlib_allowance_is_the_data_reader_and_not_a_loader(
    api_source_root: Path, tmp_path: Path
) -> None:
    """The one decision widening the scan forced, made narrowly and pinned.

    ``dynamic-loading`` admitted no package at all, and the commit that made
    it so said the rule that admits none is the rule that had them by
    accident. Bringing the loose modules in put a real case in front of it:
    ``resources.py`` calls ``importlib.resources.files`` to locate the data
    files this build ships with. That is not the plugin path ADR-017 forbids -
    ``resources`` reads packaged bytes and has no entry point that turns them
    into a module - so it is permitted, and permitted as **one member of one
    package in one file**:

    * exactly one allowance exists for this rule in the whole table, and it is
      the member, not the package. ``import importlib`` on its own is a
      different offender string and is refused;
    * the package-level table still holds zero ``dynamic-loading`` entries, so
      nothing anywhere is *outside* the rule;
    * and it is driven. A throwaway ``resources.py`` carrying the real import
      scans clean; the same file with ``importlib.import_module`` beside it
      does not.

    Without the third bullet this would be a paragraph asserting its own
    conclusion.
    """
    allowance = MODULE_ALLOWANCES["resources.py"][DYNAMIC_LOADING]
    assert set(allowance) == {"import importlib.resources"}

    holders = {
        (module, name)
        for module, rules in MODULE_ALLOWANCES.items()
        for name in rules.get(DYNAMIC_LOADING, {})
    }
    assert holders == {("resources.py", "import importlib.resources")}, holders
    assert [
        package
        for package, rules in PACKAGES_OUTSIDE_A_REGISTRY_SCAN.items()
        if DYNAMIC_LOADING in rules
    ] == []

    # The permission is for the reader, and the reader is what the module uses.
    real = (api_source_root / "station_api" / "resources.py").read_text(
        encoding="utf-8"
    )
    calls = {
        ast.unparse(node.func)
        for node in ast.walk(ast.parse(real))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "resources.files" in calls, calls

    root = tmp_path / "station_api"
    root.mkdir(parents=True)
    reader = "from importlib import resources\nD = resources.files('station_api')\n"
    (root / "resources.py").write_text(reader, encoding="utf-8")
    allowed = frozenset(allowance)
    assert _dynamic_loading_offenders(reader, "resources.py", allowed) == []

    loader = reader + "runner = importlib.import_module\n"
    assert _dynamic_loading_offenders(loader, "resources.py", allowed) != []
    for widened in (
        "from importlib import import_module\n",
        "import importlib\n",
        "from importlib import util\nutil.spec_from_file_location\n",
    ):
        assert _dynamic_loading_offenders(widened, "resources.py", allowed) != [], widened


def test_the_reviewed_outbound_modules_are_still_five(
    api_source_root: Path,
) -> None:
    """The ``outbound`` reasons, held up by something other than the prose.

    Every one of them says "this package's reach is one of the five reviewed
    modules, and the scan exists to stop a sixth". ADR-0012 4 says the same
    thing as a rule. So the five are counted here, where the exemptions are
    written, rather than only in ``test_write_gate.py`` where the constant
    lives: a sixth module importing ``httpx`` anywhere in this tree turns the
    exemptions above into claims about something that has changed.
    """
    assert (
        _modules_importing(api_source_root, "httpx")
        == list(MODULES_THAT_OPEN_A_CONNECTION)
    )
    assert len(MODULES_THAT_OPEN_A_CONNECTION) == 5

    for module in MODULES_THAT_OPEN_A_CONNECTION:
        package = module.split("/")[0]
        assert OUTBOUND in PACKAGES_OUTSIDE_A_REGISTRY_SCAN.get(package, {}), (
            f"{module} opens a connection but {package} is not written down "
            "as an exception to the outbound scan"
        )


def test_the_signer_is_named_by_exactly_the_modules_written_down_here(
    api_source_root: Path,
) -> None:
    """The ``secret-boundary`` reasons, held up the same way.

    Ten packages are written down as reaching the vault or the composer, each
    for a named purpose, and not one of those purposes is *signing*. That is
    the half a paragraph cannot keep true on its own, so it is asserted: the
    signer is imported by the composer that owns it and the application wiring
    that hands it in, and by nothing else.

    An exempt package that started importing the signer fails here long before
    anybody re-reads the paragraph that says it does not.
    """
    naming = _modules_importing(api_source_root, "station_api.compose.signer")

    assert naming == list(MODULES_THAT_NAME_THE_SIGNER)


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
