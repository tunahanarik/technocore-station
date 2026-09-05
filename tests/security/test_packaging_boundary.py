"""The Package I trust boundary, and the blocker ADR-0010 1 measured.

Three separate things live here because they are three halves of one
decision: how a packaged build finds its own files, what the packaging tree
is allowed to contain, and what a packaged run may never do.

**The resolver.** ``REPO_ROOT = Path(__file__).resolve().parents[4]`` worked
for nine packages and worked by accident: it is the repository root only
under an editable install. From a wheel it lands above the virtual
environment, ``apps/station-web/dist`` is not there, and the application
serves a 503 page saying the interface was not built - to a user holding a
build that was supposed to contain it. Nothing in this suite looked at that
page, which is why the failure was silent for nine packages. It is looked at
here, from both sides: a development checkout still gets it, and a frozen
build can no longer reach it.

**The tree.** ADR-0010 3 measured two holes in the existing boundary scans
and this file closes the second one. The ``subprocess``/``exec`` ban lived in
``test_agent_boundary.py`` and ``test_proof_boundary.py``, scoped to
``station_api/agent`` and ``station_api/proof``. Everything the product says
about execution is product-wide - ``arbitrary_execution_supported:
Literal[False]``, ``execution_unavailable``, the sentence on screen - so an
installer or an updater that grew a ``subprocess`` call would have made all
three false and no test would have opened the file. The scan is product-wide
here, and the packaging tree is inside it.

**The exemptions are exact and are driven.** ``ctypes`` is genuinely needed
by two modules - the DPAPI envelope and the Windows ACL helper - so it is an
allow-list of two paths rather than a prefix ban with a hole in it, and those
two files are separately checked for the process-creating Win32 entry points
they must not name.

Every scan asserts it actually scanned something, and every rule is driven
against a planted violation. A scan that silently found no files passes
forever and proves nothing.
"""

from __future__ import annotations

import ast
import hashlib
import os
import signal
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from station_api import launcher, resources, single_instance
from station_api.app import SHIPPED_WEB_DIST, create_app
from station_api.config import Settings
from station_api.db.migrations_runner import SchemaAheadError, build_alembic_config
from station_api.digests import domain_digest_bytes, file_digest
from station_api.resources import PackagedLayoutError

pytestmark = pytest.mark.security

# ---------------------------------------------------------------------------
# The product-wide execution ban (ADR-0010 3)
# ---------------------------------------------------------------------------

#: Every tree whose Python sources are the product or produce the product.
EXECUTION_SCANNED_TREES = (
    Path("apps") / "station-api" / "src",
    Path("packages") / "technocore-conform" / "src",
    Path("apps") / "station-web" / "e2e" / "harness",
    Path("packaging"),
)

#: Anything that runs a program. Deliberately **not** the same list the two
#: package-scoped boundary files use: ``importlib`` and ``pkgutil`` are on
#: theirs because a task package has no business loading code by name, while
#: ``importlib.resources`` is exactly how ADR-0010 1 says a packaged build
#: should find its own data - and ``technocore_conform.selftest`` has read
#: its pinned vectors that way since Stage 2B.
EXECUTION_IMPORTS = (
    "subprocess",
    "multiprocessing",
    "pty",
    "ctypes",
    "runpy",
    "imp",
    "os.system",
)

#: Banned as a bare name, wherever it appears.
EXECUTION_NAMES = ("exec", "eval", "__import__", "system", "popen")

#: Banned as an attribute too.
#:
#: ``compile`` is absent for the reason the two earlier boundary files give:
#: ``re.compile`` has nothing to do with this rule and banning it would fail
#: the test for a reason with no security content.
#:
#: The Package I review measured what the first five missed: ``popen`` is
#: lower case and therefore never matched ``subprocess.Popen``, and none of
#: the other process-starting entry points were named at all. They are here
#: now. ``run`` and ``call`` are deliberately **not**, and that is a
#: measurement rather than an oversight: ``uvicorn.Server(config).run(...)``
#: in ``launcher.py``, ``PyInstaller.__main__.run(...)`` in
#: ``build_bundle.py`` and eight ``run`` bindings in ``proof/bundle.py`` are
#: ordinary calls, so banning the bare word would turn this test red for a
#: reason with no security content - ``compile``'s case exactly. Little is
#: lost: a ``run``/``call`` that starts a program has to come from a module
#: :data:`EXECUTION_IMPORTS` bans in every file, exemptions included.
EXECUTION_ATTRIBUTES = (
    "exec",
    "eval",
    "__import__",
    "system",
    "popen",
    "Popen",
    "check_output",
    "check_call",
    "getoutput",
    "getstatusoutput",
    "startfile",
    "spawnl",
    "spawnle",
    "spawnv",
    "spawnve",
    "execl",
    "execle",
    "execv",
    "execve",
    "posix_spawn",
)

#: The only two modules that may import ``ctypes``, by exact path.
#:
#: Both call Win32 through it and neither creates a process: ``dpapi.py``
#: wraps ``CryptProtectData``/``CryptUnprotectData`` and ``windows_acl.py``
#: wraps the ACL API. An allow-list rather than a prefix hole, so a third
#: file that reaches for ``ctypes`` fails here.
CTYPES_ALLOWED = frozenset(
    {
        Path("apps") / "station-api" / "src" / "station_api" / "vault" / "dpapi.py",
        Path("apps")
        / "station-api"
        / "src"
        / "station_api"
        / "vault"
        / "windows_acl.py",
    }
)

#: What the two allowed modules are exempted from: ``ctypes``, and nothing
#: else.
#:
#: The Package I review measured the difference. The exemption used to be
#: written as "these two files are not scanned", which took them out of
#: :data:`EXECUTION_IMPORTS` **entirely**: an ``import subprocess`` plus a
#: ``subprocess.Popen`` planted in ``vault/dpapi.py`` left ruff, mypy and the
#: whole suite green. ``dpapi.py`` is the module that opens the DPAPI
#: envelope around the seed, so it is the worst file in the product for code
#: execution to reach. The exemption is now subtracted symbol by symbol, and
#: the rest of the ban applies to those two files like everywhere else.
EXECUTION_IMPORTS_MINUS_CTYPES = tuple(
    name for name in EXECUTION_IMPORTS if name != "ctypes"
)

#: Win32 entry points that start a program. None of them may be named by the
#: two files that are allowed to hold a ``ctypes`` handle.
PROCESS_CREATION_FRAGMENTS = (
    "CreateProcess",
    "ShellExecute",
    "WinExec",
    "CreateThread",
    "system(",
)

#: Directory *names* under the scanned trees that never hold a hand-written
#: file.
#:
#: ``artifacts``, ``dist`` and ``build`` used to be here and are not any
#: more. ``dist`` is PyInstaller's default distpath and ``build`` its default
#: workpath, and the repository's .gitignore matches both at any depth, so
#: excusing them here completed the pair of blind spots ADR-0010 3 named:
#: measured, a ``packaging/dist/helper.py`` carrying ``subprocess.Popen`` was
#: read by nothing and broke no test. ``test_bind.py`` had already dropped
#: the same two names, so the two lists had silently diverged.
GENERATED_PARTS = frozenset({"__pycache__", "node_modules"})

#: The Python this repository holds that the execution ban is **not** about,
#: each with the reason it is not, because an exclusion without a reason is
#: how a scan quietly stops covering the product.
#:
#: * ``tests`` plants the very imports and calls the ban forbids - that is
#:   what its deny-side probes are - so scanning it would make the suite fail
#:   on its own evidence.
#: * ``vendor`` is the Technocore reference implementation, read by the
#:   conformance differential as an oracle. The product never imports it and
#:   the bundle never carries it.
UNSCANNED_PYTHON_ROOTS: dict[Path, str] = {
    Path("tests"): "the suite plants the calls it forbids",
    Path("vendor"): "a differential oracle the product never imports",
}

#: The one place under a scanned tree that holds produced bytes, named by its
#: **full relative path** rather than by a bare directory name.
#:
#: This is where ``build_bundle.py`` writes, and a built bundle carries a
#: whole CPython standard library, so it has to be skipped - but skipping it
#: by the name ``artifacts`` would have excused every directory anywhere that
#: happens to share the name. One exact location, excused once.
ARTIFACT_DIR = Path("packaging") / "artifacts"


def _python_sources(repo_root: Path) -> list[Path]:
    """Every Python source the execution ban reads, as absolute paths."""
    found: list[Path] = []
    for tree in EXECUTION_SCANNED_TREES:
        base = repo_root / tree
        if not base.is_dir():
            continue
        for candidate in base.rglob("*.py"):
            relative = candidate.relative_to(repo_root)
            if relative.is_relative_to(ARTIFACT_DIR):
                continue
            if any(part in GENERATED_PARTS for part in relative.parts):
                continue
            found.append(candidate)
    return found


def _all_repository_python(repo_root: Path) -> list[Path]:
    """Every hand-written Python file in the repository, pruned as it walks.

    Deliberately **not** derived from :data:`EXECUTION_SCANNED_TREES`: this is
    the independent side of the guard below, and a list cannot vouch for
    itself.
    """
    found: list[Path] = []
    for base, directories, files in os.walk(repo_root):
        directories[:] = [
            name
            for name in directories
            if name not in GENERATED_PARTS and not name.startswith(".")
        ]
        current = Path(base)
        if current.relative_to(repo_root).is_relative_to(ARTIFACT_DIR):
            directories[:] = []
            continue
        found.extend(current / name for name in files if name.endswith(".py"))
    return found


def _banned_import_offenders(paths: list[Path], banned: tuple[str, ...]) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _matches(alias.name, banned):
                        offenders.append(f"{path.name}:{node.lineno} {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _matches(module, banned):
                    offenders.append(f"{path.name}:{node.lineno} {module}")
    return offenders


def _matches(module: str, banned: tuple[str, ...]) -> bool:
    return any(module == name or module.startswith(f"{name}.") for name in banned)


def _used_names(
    paths: list[Path],
    banned: tuple[str, ...],
    attributes: tuple[str, ...] | None = None,
) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in banned:
                offenders.append(f"{path.name}:{node.lineno} {node.id}")
            elif (
                attributes is not None
                and isinstance(node, ast.Attribute)
                and node.attr in attributes
            ):
                offenders.append(f"{path.name}:{node.lineno} .{node.attr}")
    return offenders


def _code_lines(source: str) -> str:
    """The spec with its whole-line comments removed.

    The spec explains at length *why* it is not a onefile build and why the
    console stays, and those explanations contain the very strings the rules
    below forbid. Scanning prose for a rule about code is how a test starts
    failing for a reason with no security content - the same exemption
    ``test_frontend_bundle.py`` draws when it strips TypeScript comments.
    """
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


def _without_comments(path: Path) -> str:
    """The same, for a Python module, with docstrings dropped as well."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body.pop(0)
    return ast.unparse(tree)


def test_every_named_tree_actually_contributes_to_the_execution_scan(
    repo_root: Path,
) -> None:
    """Half one: no entry on the list may be dead.

    The Package I review measured what a hand count buys: this test named two
    of the four trees, so :data:`EXECUTION_SCANNED_TREES` could be cut from
    four entries to two with **nothing** going red - H3's "the inventory said
    four and there were five" in a new place. Iterating the constant fixes
    that half: a tree that is renamed, emptied or misspelled is now named in
    the failure.

    It fixes only that half, and the other half is the test below. Iterating
    the list cannot notice a tree **deleted from the list** - measured: with
    this loop in place and nothing else, cutting the tuple from four entries
    to two was still green, because the loop shrank with it. A guard read off
    the thing it guards is not a guard.
    """
    sources = _python_sources(repo_root)
    assert len(sources) > 80, "the scan found almost nothing, so it is not scanning"

    for tree in EXECUTION_SCANNED_TREES:
        base = repo_root / tree
        assert base.is_dir(), f"the execution scan names a tree that is gone: {tree}"
        assert [path for path in sources if base in path.parents], (
            f"{tree} contributed no file to the execution scan, so the ban is "
            "not actually applied there"
        )


def test_no_python_file_in_this_repository_escapes_the_execution_scan(
    repo_root: Path,
) -> None:
    """Half two: the anchor, read off the repository and not off the list.

    ADR-0010 3's claim is about the product as a whole -
    ``arbitrary_execution_supported: Literal[False]`` is a statement about
    everything that ships, not about four directories somebody typed. So the
    expected set comes from walking the repository, and the only Python
    allowed to be outside the scan is Python with a written reason in
    :data:`UNSCANNED_PYTHON_ROOTS`.

    This is what deleting a tree from :data:`EXECUTION_SCANNED_TREES` runs
    into, and it is also what a *new* product tree runs into on the day it is
    added - which is the case a hand-written inventory always loses to.
    """
    scanned = set(_python_sources(repo_root))
    escaped: list[str] = []

    for candidate in _all_repository_python(repo_root):
        relative = candidate.relative_to(repo_root)
        if any(relative.is_relative_to(root) for root in UNSCANNED_PYTHON_ROOTS):
            continue
        if candidate not in scanned:
            escaped.append(str(relative))

    assert escaped == [], (
        "these Python files are in the repository but outside the execution "
        "ban, and none of them has a recorded reason to be: "
        + ", ".join(sorted(escaped))
    )

    # And the exclusions are real directories with real content, so the
    # reasons cannot rot into names of things that no longer exist.
    for root, reason in UNSCANNED_PYTHON_ROOTS.items():
        assert (repo_root / root).is_dir(), f"{root} is gone; its exemption reads: {reason}"
        assert reason


def test_no_product_source_runs_a_program(repo_root: Path) -> None:
    """ADR-0010 3. The ban that makes ``execution_unavailable`` a fact.

    Scoped to two packages before Package I, which meant an installer or an
    updater could have brought ``subprocess`` into the product while the
    agent package's own scan stayed green and the wire kept saying
    ``arbitrary_execution_supported: false``.
    """
    sources = _python_sources(repo_root)
    allowed = {repo_root / relative for relative in CTYPES_ALLOWED}
    scanned = [path for path in sources if path not in allowed]
    exempted = [path for path in sources if path in allowed]

    assert _banned_import_offenders(scanned, EXECUTION_IMPORTS) == []

    # The exemption is subtracted symbol by symbol, not file by file: the two
    # DPAPI/ACL modules lose ``ctypes`` from the ban and keep every other
    # entry. Before the Package I review they were skipped outright, and a
    # planted ``import subprocess`` + ``subprocess.Popen`` in ``dpapi.py``
    # passed ruff, mypy and 2184 tests.
    assert exempted, "the ctypes allow-list matched no scanned file"
    assert _banned_import_offenders(exempted, EXECUTION_IMPORTS_MINUS_CTYPES) == []

    assert _used_names(sources, EXECUTION_NAMES, EXECUTION_ATTRIBUTES) == []


def test_the_ctypes_exemption_subtracts_one_symbol_and_not_the_whole_ban(
    tmp_path: Path,
) -> None:
    """The deny side of the narrowed exemption, on a throwaway file.

    A file standing in for ``vault/dpapi.py`` imports both ``ctypes`` and
    ``subprocess``. Exactly one of them may be forgiven. Written against the
    tuple rather than against the real module because planting an import in
    the product to prove a point is how a planted import gets committed.
    """
    planted = tmp_path / "pretend_dpapi.py"
    planted.write_text("import ctypes\nimport subprocess\n", encoding="utf-8")

    offenders = _banned_import_offenders([planted], EXECUTION_IMPORTS_MINUS_CTYPES)

    assert [entry for entry in offenders if "subprocess" in entry], (
        "the exemption swallowed subprocess as well as ctypes, which is the "
        "shape that let a planted subprocess.Popen sit in dpapi.py"
    )
    assert [entry for entry in offenders if "ctypes" in entry] == []
    assert "ctypes" not in EXECUTION_IMPORTS_MINUS_CTYPES
    assert set(EXECUTION_IMPORTS_MINUS_CTYPES) | {"ctypes"} == set(EXECUTION_IMPORTS)


def test_the_attribute_ban_names_the_process_starting_entry_points() -> None:
    """``popen`` is lower case, and that is why ``Popen`` had to be added.

    Measured during the Package I review: ``subprocess.Popen`` matched
    nothing on the old five-name list. The two words are asserted apart so
    that removing either one is a red test rather than a silent narrowing.
    """
    assert "popen" in EXECUTION_ATTRIBUTES
    assert "Popen" in EXECUTION_ATTRIBUTES
    for entry_point in ("check_output", "startfile", "execv", "posix_spawn"):
        assert entry_point in EXECUTION_ATTRIBUTES

    # And the two that are deliberately absent, with their reason asserted
    # rather than only written down: the product really does call them.
    assert "run" not in EXECUTION_ATTRIBUTES
    assert "call" not in EXECUTION_ATTRIBUTES


def test_the_two_ctypes_modules_exist_and_start_no_process(repo_root: Path) -> None:
    """The exemption is exact, present, and does not cover process creation."""
    for relative in CTYPES_ALLOWED:
        path = repo_root / relative
        assert path.is_file(), f"the ctypes allow-list names a file that is gone: {path}"
        text = path.read_text(encoding="utf-8")
        assert "ctypes" in text, (
            f"{path.name} is exempted from the ctypes ban but does not use "
            "ctypes; the exemption has outlived its reason"
        )
        for fragment in PROCESS_CREATION_FRAGMENTS:
            assert fragment not in text, f"{path.name} names {fragment}"


@pytest.mark.parametrize(
    ("label", "source", "banned"),
    [
        ("subprocess", "import subprocess\n", EXECUTION_IMPORTS),
        ("subprocess-from", "from subprocess import run\n", EXECUTION_IMPORTS),
        ("multiprocessing", "import multiprocessing\n", EXECUTION_IMPORTS),
        ("ctypes", "import ctypes\n", EXECUTION_IMPORTS),
        ("runpy", "import runpy\n", EXECUTION_IMPORTS),
    ],
)
def test_the_execution_import_scan_reports_a_planted_import(
    tmp_path: Path, label: str, source: str, banned: tuple[str, ...]
) -> None:
    """The deny side, one probe per import family, on a throwaway tree."""
    planted = tmp_path / f"planted_{label}.py"
    planted.write_text(source, encoding="utf-8")

    assert _banned_import_offenders([planted], banned) != [], label


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("bare-exec", "runner = exec\n"),
        ("bare-eval", "value = eval\n"),
        ("os-system", "import os\nos.system('echo TEST-ONLY')\n"),
        ("popen", "import os\nos.popen('echo TEST-ONLY')\n"),
        # The four the Package I review found missing. ``Popen`` is the one
        # that mattered: the list held ``popen`` and Python is case sensitive.
        ("Popen", "handle = subprocess.Popen\n"),
        ("check-output", "text = subprocess.check_output\n"),
        ("startfile", "opener = os.startfile\n"),
        ("execv", "replacement = os.execv\n"),
    ],
)
def test_the_execution_name_scan_reports_a_planted_call(
    tmp_path: Path, label: str, source: str
) -> None:
    planted = tmp_path / f"planted_{label}.py"
    planted.write_text(source, encoding="utf-8")

    assert _used_names([planted], EXECUTION_NAMES, EXECUTION_ATTRIBUTES) != [], label


def test_the_execution_scan_leaves_the_products_real_imports_alone(
    repo_root: Path,
) -> None:
    """A scan that flagged everything would be a scan somebody turns off.

    ``importlib.resources`` is the specific thing that must stay legal: it is
    how ADR-0010 1 asks the resolver to find package data, and it is how the
    conformance package has read its pinned vectors since Stage 2B.
    """
    resolver = repo_root / "apps" / "station-api" / "src" / "station_api" / "resources.py"
    assert resolver.is_file()
    assert "from importlib import resources" in resolver.read_text(encoding="utf-8")
    assert _banned_import_offenders([resolver], EXECUTION_IMPORTS) == []


# ---------------------------------------------------------------------------
# ADR-0010 1: a packaged run can never serve the "no build" page
# ---------------------------------------------------------------------------


def _pretend_frozen(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Make :mod:`station_api.resources` believe it is inside a bundle."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, resources.FROZEN_ROOT_ATTRIBUTE, str(root), raising=False)


def test_a_frozen_run_serves_the_spa_the_bundle_carries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path / resources.BUNDLED_WEB_DIR
    bundled.mkdir()
    (bundled / resources.WEB_INDEX_NAME).write_text("<!doctype html>", encoding="utf-8")
    _pretend_frozen(monkeypatch, tmp_path)

    assert resources.is_frozen() is True
    assert resources.shipped_web_dist() == bundled


def test_a_frozen_run_with_no_spa_refuses_instead_of_serving_the_no_build_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """ADR-0010 1's extra condition, at both layers.

    The resolver refuses to name a directory that is not there, and the mount
    refuses to mount one - so a packaged build cannot reach the 503 even by
    being handed an explicit ``web_dist``. Two refusals, because one of them
    is the one somebody edits.
    """
    _pretend_frozen(monkeypatch, tmp_path)

    with pytest.raises(PackagedLayoutError):
        resources.shipped_web_dist()

    with pytest.raises(PackagedLayoutError):
        create_app(settings=settings, port=49731, engine=None, web_dist=tmp_path)

    with pytest.raises(PackagedLayoutError):
        create_app(settings=settings, port=49731, engine=None, web_dist=SHIPPED_WEB_DIST)


def test_a_development_checkout_still_gets_the_no_build_page(
    tmp_path: Path, settings: Settings
) -> None:
    """The 503 page is right exactly once, and that case is unchanged.

    A developer who has not run ``npm run build`` has a build command to run,
    and the page names it. The frozen refusal above is a different situation
    with the same symptom, which is why the two are asserted apart.
    """
    app = create_app(settings=settings, port=49731, engine=None, web_dist=tmp_path)
    with TestClient(app) as client:
        response = client.get("/", headers={"Host": "127.0.0.1:49731"})

    assert response.status_code == 503
    assert "npm --prefix apps/station-web run build" in response.text


def test_a_frozen_run_finds_the_migration_tree_in_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path.joinpath(*resources.BUNDLED_MIGRATIONS_PARTS)
    bundled.mkdir(parents=True)
    (bundled / resources.MIGRATIONS_ENV_NAME).write_text("", encoding="utf-8")
    _pretend_frozen(monkeypatch, tmp_path)

    assert resources.migrations_dir() == bundled
    config = build_alembic_config(tmp_path / "station.sqlite3")
    assert config.get_main_option("script_location") == str(bundled)


def test_a_frozen_run_with_no_migration_tree_refuses_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alembic reads ``env.py`` as a file, so a missing tree is fatal.

    Without this the failure is a ``script_location`` that does not exist,
    surfacing much later as an Alembic error about a directory - which is a
    crash, but not one that says the artefact was built wrong.
    """
    _pretend_frozen(monkeypatch, tmp_path)

    with pytest.raises(PackagedLayoutError):
        resources.migrations_dir()


def test_the_resolver_no_longer_counts_directories_from_dunder_file(
    repo_root: Path,
) -> None:
    """The blocker itself: the line ADR-0010 1 is about must be gone.

    ``parents[4]`` is not a bug you can see by reading it. It is a bug you
    see by installing the wheel, so the assertion is that the shape cannot
    come back rather than that the current value happens to be right.
    """
    api = repo_root / "apps" / "station-api" / "src" / "station_api"
    for name in ("app.py", Path("db") / "migrations_runner.py"):
        text = (api / name).read_text(encoding="utf-8")
        assert "Path(__file__)" not in text, (
            f"{name} derives a path from __file__ again; ADR-0010 1 replaced "
            "that with station_api.resources for a measured reason"
        )


def test_no_path_in_the_resolver_is_read_from_the_environment(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0010 1 rejects an environment override, for ``LOOPBACK_HOST``'s reason.

    Pointing the packaged SPA at another directory is how somebody serves
    arbitrary JavaScript from this origin, under a CSP whose ``script-src``
    is ``'self'``. Asserted twice: the module names no environment reader,
    and the plausible variable names do nothing when set.
    """
    resolver = repo_root / "apps" / "station-api" / "src" / "station_api" / "resources.py"
    code = _without_comments(resolver)
    assert resolver.is_file()
    for reader in ("os.environ", "getenv", "environb", "import os"):
        assert reader not in code, f"the resolver reads {reader}"

    before = resources.shipped_web_dist()
    for name in ("STATION_WEB_DIST", "STATION_DIST", "STATION_SPA_DIR"):
        monkeypatch.setenv(name, str(tmp_path))
    assert resources.shipped_web_dist() == before


# ---------------------------------------------------------------------------
# ADR-0010 2 and 7: what the spec is, read off the spec
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spec_source() -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / "packaging" / "station.spec").read_text(encoding="utf-8")


def test_the_spec_is_onedir_and_not_onefile(spec_source: str) -> None:
    """ADR-0010 2. onefile unpacks to ``%TEMP%`` on every launch.

    The product writes to ``%TEMP%`` nowhere today, so onefile would break a
    property that is currently true - which is a strange thing to do to
    obtain a single file.
    """
    code = _code_lines(spec_source)
    assert "COLLECT(" in code, "no COLLECT: this is not a onedir build"
    assert "exclude_binaries=True" in code
    assert "onefile" not in code
    assert "TEMP" not in code


def test_the_spec_keeps_the_console(spec_source: str) -> None:
    """ADR-0010 7. ``console=False`` sends start-up failures nowhere.

    Every refusal this package added - a claimed data directory, a database
    from a newer build, a bundle with no SPA - is printed on stderr, and in a
    windowed frozen build stderr has no destination at all.
    """
    code = _code_lines(spec_source)
    assert "console=True" in code
    assert "console=False" not in code
    assert "noconsole" not in code
    # ``disable_windowed_traceback`` is a PyInstaller keyword that only has an
    # effect in a windowed build, so it is named and left alone; what must be
    # absent is the switch that *makes* the build windowed.
    assert "--windowed" not in code
    assert "windowed=True" not in code


def test_the_spec_carries_the_migration_tree_and_the_pinned_vectors(
    spec_source: str,
) -> None:
    """Both are read as *files* at run time and neither is an importable module."""
    assert "MIGRATIONS_SOURCE" in spec_source
    assert "MIGRATIONS_TARGET" in spec_source
    assert "VECTORS_SOURCE" in spec_source
    for part in resources.BUNDLED_MIGRATIONS_PARTS:
        assert f'"{part}"' in spec_source


def test_the_spec_names_no_signing_identity(spec_source: str) -> None:
    """ADR-0010 9: the artefact is unsigned and says so rather than pretending."""
    assert "codesign_identity=None" in spec_source


def test_the_spec_excludes_the_test_only_signature_library(spec_source: str) -> None:
    """PyNaCl is a test dependency; SI-63 keeps it out of the product graph."""
    assert '"nacl"' in spec_source


def test_the_repository_packaging_directory_does_not_shadow_the_distribution(
    repo_root: Path,
) -> None:
    """A directory called ``packaging`` beside a package called ``packaging``.

    The repository root is on ``sys.path`` during this suite, and
    ``packaging`` is also a real installed distribution that build tooling
    imports. Our directory has no ``__init__.py`` deliberately, so it is at
    most a namespace portion and a regular package later on the path wins.
    Asserted rather than assumed, because getting it wrong would break tools
    in a way that has nothing to do with packaging Station.
    """
    assert not (repo_root / "packaging" / "__init__.py").exists()

    import packaging

    assert Path(packaging.__file__).resolve().parent != repo_root / "packaging"


# ---------------------------------------------------------------------------
# What the shipped archive carries that nobody asked for
#
# The ZIP is the only thing a user receives, and nothing in this repository
# had ever read it. The Package I review did, and found eleven files carrying
# the building developer's Windows account name and home directory: the
# ``__pycache__`` trees that came along when ``station.spec`` handed
# PyInstaller two source *directories* to copy. A ``.pyc`` stores the
# absolute path it was compiled from in ``co_filename``. The exe and the PYZ
# were clean.
# ---------------------------------------------------------------------------

#: Where ``build_bundle.py`` leaves the archive, and how it names it.
ARCHIVE_GLOB = "TechnocoreStation-*-windows-x64.zip"


def _built_archive(repo_root: Path) -> Path | None:
    """The archive a build produced, or ``None`` if nobody has built one."""
    archives = sorted((repo_root / ARTIFACT_DIR).glob(ARCHIVE_GLOB))
    return archives[-1] if archives else None


def _local_path_needles() -> dict[str, bytes]:
    """Byte strings that must not appear inside a file anybody receives.

    The home directory rather than only the account name: it is the longer
    and more specific of the two, so it is the one that cannot match by
    accident inside a binary. The account name is checked as well because it
    is the part that actually identifies a person, and it is checked in the
    two separator spellings a Windows path can be written in.
    """
    home = Path.home()
    return {
        "home-directory": str(home).encode("utf-8"),
        "home-directory-posix": home.as_posix().encode("utf-8"),
        "account-name": home.name.encode("utf-8"),
    }


def _leaking_entries(archive: Path, needles: dict[str, bytes]) -> list[str]:
    """Every archive member whose *content* carries one of the needles."""
    offenders: list[str] = []
    with zipfile.ZipFile(archive) as opened:
        for member in opened.infolist():
            if member.is_dir():
                continue
            body = opened.read(member)
            found = sorted(label for label, needle in needles.items() if needle in body)
            if found:
                offenders.append(f"{member.filename} ({', '.join(found)})")
    return offenders


def test_the_leak_scan_reports_a_planted_path(tmp_path: Path) -> None:
    """The deny side, on a throwaway archive.

    Driven against a planted leak rather than against the real artefact,
    because the way to make the real artefact leak is to break the spec, and
    a broken spec is not something to leave lying in a test.
    """
    needles = _local_path_needles()
    planted = tmp_path / "planted.zip"
    with zipfile.ZipFile(planted, "w") as archive:
        archive.writestr("clean.txt", b"nothing to see")
        archive.writestr(
            "pretend.pyc", b"\x00\x00" + str(Path.home()).encode("utf-8") + b"\x00"
        )

    offenders = _leaking_entries(planted, needles)

    assert [entry for entry in offenders if entry.startswith("pretend.pyc")], (
        "the scan does not report a file that literally contains the home "
        "directory, so it would not have reported the eleven that did"
    )
    assert [entry for entry in offenders if entry.startswith("clean.txt")] == []


def test_the_shipped_archive_names_no_developer_and_no_home_directory(
    repo_root: Path,
) -> None:
    """The property, on the real thing, when there is a real thing to read.

    Measured before the fix: eleven of the archive's 152 members carried the
    account name and the home directory - ``db/migrations/__pycache__/env``,
    the nine ``versions/__pycache__/000*`` modules and
    ``technocore_conform/vectors/__pycache__/__init__``. After it, none, and
    the archive has no ``__pycache__`` member at all.

    Like ``test_the_shipped_spa_is_byte_for_byte_the_audited_dist``, this
    cannot compare anything when nobody has built a bundle - and, like it, an
    archive that exists is read rather than waved through. The packaging
    workflow runs this file after its build so that the case with an archive
    is the case CI exercises.
    """
    archive = _built_archive(repo_root)
    if archive is None:
        assert not (repo_root / ARTIFACT_DIR / "bundle").exists(), (
            "a bundle was built but no archive sits beside it, so the bytes "
            "a user would receive are not the bytes anything here has read"
        )
        return

    names = [member.filename for member in zipfile.ZipFile(archive).infolist()]
    assert len(names) > 100, "the archive is implausibly small"

    cached = [name for name in names if "__pycache__" in name or name.endswith(".pyc")]
    assert cached == [], (
        "the archive carries compiled bytecode copied from a source tree; "
        "every one of those files names the machine it was built on, and a "
        "stale one can be loaded ahead of the .py beside it: "
        + ", ".join(cached)
    )

    assert _leaking_entries(archive, _local_path_needles()) == [], (
        "the shipped archive names the account that built it"
    )


# ---------------------------------------------------------------------------
# ADR-0010 8: one Station per data directory
# ---------------------------------------------------------------------------


def test_a_second_instance_is_refused_while_the_first_holds_the_lock(
    tmp_path: Path,
) -> None:
    first = single_instance.acquire(tmp_path)
    try:
        with pytest.raises(single_instance.AlreadyRunningError):
            single_instance.acquire(tmp_path)
    finally:
        first.release()


def test_the_refusal_names_the_file_to_delete(tmp_path: Path) -> None:
    """A refusal a user cannot clear gets cleared by deleting the data directory.

    That directory holds the seed envelope, the audit chain key and every
    evidence record, and ADR-0010 5 spends a section keeping people away from
    it. So the message carries the one path that actually needs removing.
    """
    first = single_instance.acquire(tmp_path)
    try:
        with pytest.raises(single_instance.AlreadyRunningError) as caught:
            single_instance.acquire(tmp_path)
    finally:
        first.release()

    message = str(caught.value)
    assert str(tmp_path / single_instance.LOCK_FILENAME) in message
    assert "sil" in message.lower()


def test_releasing_the_lock_lets_the_next_start_succeed(tmp_path: Path) -> None:
    single_instance.acquire(tmp_path).release()
    second = single_instance.acquire(tmp_path)
    second.release()

    assert not (tmp_path / single_instance.LOCK_FILENAME).exists()


def test_two_data_directories_do_not_block_each_other(tmp_path: Path) -> None:
    """The lock is per data directory, which is what is being protected."""
    one = single_instance.acquire(tmp_path / "a")
    two = single_instance.acquire(tmp_path / "b")
    one.release()
    two.release()


def test_the_lock_file_carries_no_secret(tmp_path: Path) -> None:
    """It is diagnostic text: a process id and a timestamp, nothing else."""
    lock = single_instance.acquire(tmp_path)
    try:
        body = (tmp_path / single_instance.LOCK_FILENAME).read_text(encoding="utf-8")
    finally:
        lock.release()

    assert body.split()[0].isdigit()
    for forbidden in ("token", "seed", "did:", "passphrase", "secret"):
        assert forbidden not in body.lower()


def test_the_lock_lives_in_the_data_directory_and_not_in_temp(tmp_path: Path) -> None:
    """The product writes nothing to ``%TEMP%`` and this did not change that."""
    lock = single_instance.acquire(tmp_path)
    try:
        assert lock.path.parent == tmp_path
    finally:
        lock.release()


def test_releasing_twice_is_not_an_error(tmp_path: Path) -> None:
    """The launcher releases in a ``finally``; a double release must be silent."""
    lock = single_instance.acquire(tmp_path)
    lock.release()
    lock.release()


def test_the_launcher_claims_the_lock_before_it_opens_the_database(
    repo_root: Path,
) -> None:
    """Order is the whole control here, so it is pinned rather than trusted.

    Claiming after the database is opened leaves exactly the window the lock
    exists to close: two processes both reach ``initialise_database`` and
    both migrate.
    """
    source = (
        repo_root / "apps" / "station-api" / "src" / "station_api" / "launcher.py"
    ).read_text(encoding="utf-8")

    claim = source.index("single_instance.acquire")
    database = source.index("initialise_database(settings.database_path")
    listen = source.index("reserve_loopback_socket(settings)")

    assert claim < database < listen


def test_the_launcher_releases_the_lock_when_the_server_stops(
    repo_root: Path,
) -> None:
    """A ``finally``, not an ``atexit``: Ctrl-C and an exception count too."""
    source = (
        repo_root / "apps" / "station-api" / "src" / "station_api" / "launcher.py"
    ).read_text(encoding="utf-8")

    assert "finally:\n        lock.release()" in source


# ---------------------------------------------------------------------------
# ADR-0010 7 and 8: stopping Station has to look like stopping Station
#
# Measured on the real artefact and recorded in
# ``docs/verification/paket-i.md`` 13.3: Ctrl+C released the lock and merged
# the WAL - and then exited **1** with ``KeyboardInterrupt`` and PyInstaller's
# ``Failed to execute script`` on the console, while Ctrl+Break ended the
# process at exit code **3** without unwinding, leaving ``station.lock``
# behind so the next launch was refused by a lock nobody was holding.
#
# Both come from one mechanism: ``uvicorn.Server.capture_signals`` re-raises
# the signal it caught **after** restoring the handler that was in place
# before it. So whichever handler surrounds ``Server.run`` decides what a
# clean shutdown looks like, and the tests below drive exactly that.
# ---------------------------------------------------------------------------


def _uvicorn_signal_dance(signalnum: int) -> None:
    """Replay what ``uvicorn.Server.capture_signals`` does, in miniature.

    Save the handler, install one that only records, take the signal, put the
    saved handler back, then ``raise_signal`` the same signal again - that
    last line is uvicorn's, and its comment says it is there to "trigger the
    expected behaviour now". Reproducing the shape rather than starting a
    real server keeps the test on the handler, which is the part this
    repository owns.
    """
    caught: list[int] = []
    original = signal.signal(signalnum, lambda number, frame: caught.append(number))
    try:
        signal.raise_signal(signalnum)
    finally:
        signal.signal(signalnum, original)
    assert caught == [signalnum], "the stand-in never actually took the signal"
    signal.raise_signal(signalnum)


def test_the_absorbed_signal_set_covers_both_console_stop_keys() -> None:
    """Ctrl+C and Ctrl+Break, because both were measured and both were wrong.

    ``SIGBREAK`` exists on Windows only, and Windows is the product's
    platform (ADR-008), so it is required there rather than merely tolerated.
    """
    assert signal.SIGINT in launcher.SHUTDOWN_SIGNALS
    assert signal.SIGTERM in launcher.SHUTDOWN_SIGNALS
    if sys.platform == "win32":
        assert signal.SIGBREAK in launcher.SHUTDOWN_SIGNALS

    assert tuple(dict.fromkeys(launcher.SHUTDOWN_SIGNALS)) == launcher.SHUTDOWN_SIGNALS


def test_a_re_raised_interrupt_inside_the_window_does_not_reach_the_process() -> None:
    """The Ctrl+C half of the defect, driven rather than described."""
    with launcher.absorbing_shutdown_signals():
        _uvicorn_signal_dance(signal.SIGINT)


@pytest.mark.skipif(sys.platform != "win32", reason="SIGBREAK exists on Windows only")
def test_a_re_raised_break_inside_the_window_does_not_reach_the_process() -> None:
    """The Ctrl+Break half.

    Only the absorbed direction is driven in-process, and deliberately: the
    unabsorbed direction is the CRT default, which ends the process without
    unwinding and would take the test session with it. Its "before" state is
    measured on the real artefact in ``docs/verification/paket-i.md`` 13.3
    instead, which is where a process-ending observation belongs.
    """
    with launcher.absorbing_shutdown_signals():
        _uvicorn_signal_dance(signal.SIGBREAK)


def test_without_the_window_the_same_re_raise_is_a_keyboard_interrupt() -> None:
    """Guards the guard: the replay above has to be capable of failing.

    Without this, the absorbing test would pass just as happily against a
    stand-in that raised nothing at all - the vacuity this suite keeps
    finding in its own scans.
    """
    original = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        with pytest.raises(KeyboardInterrupt):
            _uvicorn_signal_dance(signal.SIGINT)
    finally:
        signal.signal(signal.SIGINT, original)


def test_the_window_puts_back_the_handlers_it_found() -> None:
    """Absorbing is scoped. Outside it, Ctrl+C is Python's Ctrl+C again.

    A launcher that absorbed for the whole process would make a slow
    migration uninterruptible, which trades one bad shutdown for another.
    """
    before = {sig: signal.getsignal(sig) for sig in launcher.SHUTDOWN_SIGNALS}

    with launcher.absorbing_shutdown_signals():
        inside = {sig: signal.getsignal(sig) for sig in launcher.SHUTDOWN_SIGNALS}

    after = {sig: signal.getsignal(sig) for sig in launcher.SHUTDOWN_SIGNALS}

    assert after == before
    for sig in launcher.SHUTDOWN_SIGNALS:
        assert inside[sig] is launcher.absorb_shutdown_signal
        assert inside[sig] is not before[sig]


def test_the_window_is_a_no_op_off_the_main_thread() -> None:
    """``signal.signal`` refuses elsewhere, so the context manager must not.

    A launcher that raised ``ValueError: signal only works in main thread``
    would turn an embedder's start-up into a crash; on that thread the
    ``except KeyboardInterrupt`` in ``main`` is what keeps the exit honest.
    """
    failure: list[BaseException] = []

    def body() -> None:
        try:
            with launcher.absorbing_shutdown_signals():
                assert threading.current_thread() is not threading.main_thread()
        except BaseException as exc:  # recorded and re-asserted, not swallowed
            failure.append(exc)

    worker = threading.Thread(target=body)
    worker.start()
    worker.join()

    assert failure == []


class _StubTokens:
    def issue(self) -> str:
        return "TEST-ONLY-bootstrap-token"


class _StubState:
    bootstrap_tokens = _StubTokens()


class _StubApp:
    state = _StubState()


class _ReRaisingServer:
    """A server that stops cleanly and then re-raises, the way uvicorn does."""

    signalnum: int = signal.SIGINT

    def __init__(self, config: Any) -> None:
        self.config = config

    def run(self, sockets: list[Any] | None = None) -> None:
        _uvicorn_signal_dance(_ReRaisingServer.signalnum)


class _CrashingServer:
    """A server that fails for a reason that has nothing to do with signals."""

    def __init__(self, config: Any) -> None:
        self.config = config

    def run(self, sockets: list[Any] | None = None) -> None:
        raise RuntimeError("the server actually broke")


def _stub_launcher_dependencies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Everything ``main`` needs except the part under test.

    The lock, the socket and the data directory are real and temporary; the
    database, the application and the browser are stood in for, because none
    of them is what these tests are about.
    """
    data_dir = tmp_path / "station-data"
    monkeypatch.setattr(
        launcher, "load_settings", lambda: Settings(dev_mode=False, data_dir=data_dir)
    )
    monkeypatch.setattr(launcher, "initialise_database", lambda path, stage: None)
    monkeypatch.setattr(launcher, "create_app", lambda **kwargs: _StubApp())
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: True)
    return data_dir


def test_a_clean_stop_exits_zero_and_leaves_no_lock_behind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The defect at the level the user meets it.

    Exit code 0 is the assertion that matters: a frozen build turns anything
    escaping ``main`` into ``Failed to execute script`` on the console
    ADR-0010 7 deliberately left visible.
    """
    data_dir = _stub_launcher_dependencies(monkeypatch, tmp_path)
    _ReRaisingServer.signalnum = signal.SIGINT
    monkeypatch.setattr(launcher.uvicorn, "Server", _ReRaisingServer)

    # Caught rather than allowed to propagate: ``KeyboardInterrupt`` is what
    # the defect produced, and letting it out of a test aborts the whole
    # pytest session instead of failing one case. A red test says more than a
    # dead run.
    try:
        exit_code = launcher.main()
    except KeyboardInterrupt:
        pytest.fail(
            "the interrupt uvicorn re-raised escaped main(); a frozen build "
            "turns that into exit code 1 and 'Failed to execute script'"
        )

    assert exit_code == 0
    assert not (data_dir / single_instance.LOCK_FILENAME).exists()


@pytest.mark.skipif(sys.platform != "win32", reason="SIGBREAK exists on Windows only")
def test_a_break_stop_also_exits_zero_and_releases_the_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ctrl+Break was the worse of the two: the lock outlived the process.

    This test cannot fail politely. If the absorbing window is removed, the
    re-raised ``SIGBREAK`` reaches the CRT default, which ends the *test*
    process the same way it used to end the packaged one - the run dies at
    exit code 3 with no report. That is still a detection, and it is written
    down here so nobody mistakes the crater for an unrelated crash.
    """
    data_dir = _stub_launcher_dependencies(monkeypatch, tmp_path)
    monkeypatch.setattr(_ReRaisingServer, "signalnum", signal.SIGBREAK)
    monkeypatch.setattr(launcher.uvicorn, "Server", _ReRaisingServer)

    assert launcher.main() == 0
    assert not (data_dir / single_instance.LOCK_FILENAME).exists()


def test_a_real_crash_is_still_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The absorbing window must not turn a failure into a quiet success.

    This is the assertion that keeps the fix from becoming a blanket
    ``except Exception``: a server that dies for its own reasons still
    propagates, and the lock is still released on the way out.
    """
    data_dir = _stub_launcher_dependencies(monkeypatch, tmp_path)
    monkeypatch.setattr(launcher.uvicorn, "Server", _CrashingServer)

    with pytest.raises(RuntimeError, match="the server actually broke"):
        launcher.main()

    assert not (data_dir / single_instance.LOCK_FILENAME).exists()


@pytest.mark.parametrize(
    ("label", "target", "failure"),
    [
        ("interrupt-during-migration", "initialise_database", KeyboardInterrupt()),
        ("socket-cannot-be-reserved", "reserve_loopback_socket", OSError("no port")),
        ("bundle-without-an-spa", "create_app", PackagedLayoutError("no SPA")),
    ],
)
def test_a_failure_during_start_up_does_not_strand_the_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    label: str,
    target: str,
    failure: BaseException,
) -> None:
    """ADR-0010 8, over the whole start-up rather than over the server run.

    The ``finally`` used to begin at ``uvicorn.Server.run``, so every step
    between claiming the lock and starting the server could exit with
    ``station.lock`` still on disk. Three of those steps are driven here
    because each is a situation this repository has already written down:

    * an interrupt during a migration - ``absorbing_shutdown_signals``'s own
      docstring says a slow migration must stay interruptible, so this is the
      documented path, not an exotic one, and it produced exactly the stale
      lock that 13.3 was about;
    * a port that cannot be reserved;
    * ``PackagedLayoutError`` - the refusal ADR-0010 1 exists to raise. A
      user with a bundle built wrong got the right message once and then, on
      the next launch, "Station is already running": a false second
      diagnosis stacked on the true first one.

    Each failure is asserted to propagate as itself. A lock released by
    swallowing the error would pass an "is the lock gone" check and be a
    worse bug than the one being fixed.
    """
    data_dir = _stub_launcher_dependencies(monkeypatch, tmp_path)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise failure

    monkeypatch.setattr(launcher, target, fail)

    with pytest.raises(type(failure)):
        launcher.main()

    assert not (data_dir / single_instance.LOCK_FILENAME).exists(), (
        f"{label}: start-up failed and left the single-instance lock behind, "
        "so the next launch is refused for the wrong reason"
    )


def test_a_database_from_a_newer_build_still_releases_the_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR-0010 6's refusal keeps working once its manual release is gone.

    The ``SchemaAheadError`` branch used to call ``lock.release()`` itself.
    With the whole body inside the ``finally`` that call became redundant and
    was removed, so the exit code and the released lock are asserted together
    - a removal is only safe if the property it used to provide is still
    measured somewhere.
    """
    data_dir = _stub_launcher_dependencies(monkeypatch, tmp_path)

    def ahead(*args: Any, **kwargs: Any) -> Any:
        raise SchemaAheadError("the database was written by a newer Station")

    monkeypatch.setattr(launcher, "initialise_database", ahead)

    assert launcher.main() == 5
    assert not (data_dir / single_instance.LOCK_FILENAME).exists()


def test_the_lock_release_covers_the_whole_start_up_and_not_only_the_server(
    repo_root: Path,
) -> None:
    """Span is the mechanism here, so it is pinned rather than trusted.

    ``initialise_database``, the socket reservation and ``create_app`` must
    all sit *after* the ``try`` that the release belongs to. Reading the
    order off the source is what the sister tests in this file do for the
    lock claim and the absorbing window, for the same reason: a ``finally``
    that is present but starts three statements too late is invisible to a
    test that only asks whether a ``finally`` exists.
    """
    source = (
        repo_root / "apps" / "station-api" / "src" / "station_api" / "launcher.py"
    ).read_text(encoding="utf-8")

    claim = source.index("lock = single_instance.acquire")
    guard = source.index("try:", claim)
    database = source.index("initialise_database(settings.database_path")
    listen = source.index("reserve_loopback_socket(settings)")
    build = source.index("create_app(settings=settings")
    release = source.index("finally:\n        lock.release()")

    assert claim < guard < database < listen < build < release

    # And the branch that used to release by hand no longer does: two
    # releases were harmless, but the second one existing at all is what
    # makes somebody believe the first is the only one that runs.
    assert source.count("lock.release()") == 1


def test_the_launcher_wraps_the_server_run_in_the_absorbing_window(
    repo_root: Path,
) -> None:
    """Placement is the mechanism, so it is pinned rather than trusted.

    ``capture_signals`` restores whatever handler was installed *before*
    ``Server.run``. Installing the absorbing handler anywhere else - after
    the call, or in a helper uvicorn never sees - restores the default
    instead and the defect comes back without a test noticing.
    """
    source = (
        repo_root / "apps" / "station-api" / "src" / "station_api" / "launcher.py"
    ).read_text(encoding="utf-8")

    window = source.index("with absorbing_shutdown_signals():")
    run = source.index("uvicorn.Server(config).run(sockets=[sock])")
    release = source.index("finally:\n        lock.release()")

    assert window < run < release


# ---------------------------------------------------------------------------
# The build script tells the truth about what it did
# ---------------------------------------------------------------------------


def _run_build_script(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(repo_root / "packaging" / "build_bundle.py"), *arguments],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_build_script_reports_every_precondition_and_agrees_with_its_exit_code(
    repo_root: Path,
) -> None:
    """ADR-0010 2's honesty requirement, measured rather than described.

    PyInstaller is not a dependency of this repository, so on most machines
    this reports one missing precondition and exits 2. On a machine that has
    been given PyInstaller it reports three satisfied ones and exits 0. Both
    are asserted, from the same output, so the test does not quietly become a
    one-branch test on either kind of machine.
    """
    result = _run_build_script(repo_root, "--check")
    lines = [line for line in result.stdout.splitlines() if line.startswith("[")]

    assert {line.split(":")[0].split("]")[0].strip("[ ") for line in lines} <= {
        "OK",
        "EKSIK",
    }
    assert len(lines) == 3, result.stdout

    missing = [line for line in lines if line.startswith("[EKSIK")]
    assert result.returncode == (2 if missing else 0), result.stdout


def test_the_build_script_never_claims_an_artefact_it_did_not_produce(
    repo_root: Path,
) -> None:
    """The build path refuses loudly when a precondition is missing.

    Only exercised when a precondition really is missing, because the
    alternative on a machine with PyInstaller is a full build inside the test
    suite. The check above is what runs everywhere; this is the half that
    proves the refusal is a refusal.
    """
    check = _run_build_script(repo_root, "--check")
    if check.returncode == 0:
        assert "EKSIK" not in check.stdout
        return

    result = _run_build_script(repo_root)
    assert result.returncode == 2
    assert "URETILMEDI" in result.stderr
    assert not (repo_root / "packaging" / "artifacts").exists()


def test_the_build_script_publishes_the_unsigned_sentence(repo_root: Path) -> None:
    """ADR-0010 9. The hash sentence, and the half that is only true unsigned.

    Also the sentence that must **not** be there: telling a user to turn
    SmartScreen off is advice this product does not give.
    """
    source = (repo_root / "packaging" / "build_bundle.py").read_text(encoding="utf-8")

    assert "yalnizca dosya butunlugunu tanimlar" in source
    assert "IMZASIZDIR" in source
    assert "kimin urettigini de kanitlamaz" in source
    assert "SmartScreen" in source

    lowered = source.lower()
    for advice in ("smartscreen'i kapat", "smartscreen kapat", "devre disi birak"):
        assert advice not in lowered


def test_the_artefact_digest_is_the_plain_sha256_a_user_can_reproduce(
    tmp_path: Path,
) -> None:
    """ADR-0010 9. The published number has to match ``Get-FileHash``.

    Every other digest in this product is domain-separated and
    length-prefixed, deliberately, so a digest built for one binding cannot be
    presented as another. This one must not be: a release hash whose only
    checker is this repository is not a release hash. So the exemption is
    asserted rather than left to a docstring - if ``file_digest`` ever grew a
    domain prefix, the value would stop matching the tool the user has.
    """
    payload = b"TEST-ONLY bundle bytes\n" * 4096
    artefact = tmp_path / "bundle.zip"
    artefact.write_bytes(payload)

    assert file_digest(artefact) == hashlib.sha256(payload).hexdigest()

    # And it is not the domain-separated helper wearing a different name.
    assert file_digest(artefact) != domain_digest_bytes(b"anything", payload)


def test_the_build_script_reuses_the_products_own_digest_module(
    repo_root: Path,
) -> None:
    """ADR-0010 9: no second hash helper anywhere in this repository."""
    source = (repo_root / "packaging" / "build_bundle.py").read_text(encoding="utf-8")

    assert "from station_api.digests import file_digest" in source
    assert "hashlib" not in source
