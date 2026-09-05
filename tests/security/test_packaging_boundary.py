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
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from station_api import launcher, resources, single_instance
from station_api.app import SHIPPED_WEB_DIST, create_app
from station_api.config import Settings
from station_api.db.migrations_runner import build_alembic_config
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

#: Banned as an attribute too. ``compile`` is absent for the reason the two
#: earlier boundary files give: ``re.compile`` has nothing to do with this
#: rule and banning it would fail the test for a reason with no security
#: content.
EXECUTION_ATTRIBUTES = ("exec", "eval", "__import__", "system", "popen")

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

#: Win32 entry points that start a program. None of them may be named by the
#: two files that are allowed to hold a ``ctypes`` handle.
PROCESS_CREATION_FRAGMENTS = (
    "CreateProcess",
    "ShellExecute",
    "WinExec",
    "CreateThread",
    "system(",
)

#: Directories under the scanned trees that hold generated bytes.
GENERATED_PARTS = frozenset({"__pycache__", "node_modules", "artifacts", "dist", "build"})


def _python_sources(repo_root: Path) -> list[Path]:
    """Every Python source the execution ban reads, as absolute paths."""
    found: list[Path] = []
    for tree in EXECUTION_SCANNED_TREES:
        base = repo_root / tree
        if not base.is_dir():
            continue
        for candidate in base.rglob("*.py"):
            relative = candidate.relative_to(base)
            if any(part in GENERATED_PARTS for part in relative.parts):
                continue
            found.append(candidate)
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


def test_the_execution_scan_opens_the_product_and_the_packaging_tree(
    repo_root: Path,
) -> None:
    """Guards the guard. Both trees must contribute, separately counted."""
    sources = _python_sources(repo_root)
    assert len(sources) > 80, "the scan found almost nothing, so it is not scanning"

    packaging_root = repo_root / "packaging"
    assert [path for path in sources if packaging_root in path.parents], (
        "the packaging tree contributed no file to the execution scan, so the "
        "hole ADR-0010 3 measured is still open"
    )

    api_root = repo_root / "apps" / "station-api" / "src"
    assert [path for path in sources if api_root in path.parents]


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

    assert _banned_import_offenders(scanned, EXECUTION_IMPORTS) == []
    assert _used_names(sources, EXECUTION_NAMES, EXECUTION_ATTRIBUTES) == []


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
