"""Every shipped source file is actually in the repository.

Package G shipped a module named ``credentials.py``. The repository's own
``.gitignore`` carries ``credentials.*`` - a security rule, there to keep a
real credential file from ever being committed - and it swallowed the source
module without a word. Locally nothing noticed: the file was on disk, so the
imports resolved, mypy was happy and 1514 tests passed. CI, working from a
fresh checkout, failed with ``ModuleNotFoundError``.

The lesson is narrow and worth a test: a guard that protects the repository
from a file can also hide a file from the repository, and a suite that reads
the working tree cannot tell the difference. Only something that asks git
what it actually tracks can.

The module was renamed rather than exempted. Poking a hole in
``credentials.*`` to admit one source file is exactly the hole a real
credential file would later walk through.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: Trees whose sources ship inside the product. A file here that git does not
#: track is a file that exists on this machine and nowhere else.
SHIPPED_TREES = (
    Path("apps") / "station-api" / "src",
    Path("packages") / "technocore-conform" / "src",
    Path("apps") / "station-web" / "src",
    Path("apps") / "station-web" / "e2e",
    # ADR-0010 3. Package I is the first package whose sources are not ``.py``
    # and do not live under a ``src`` directory, and it is also the package
    # whose natural output directory names are the two the repository has
    # ignored since Stage 1.
    Path("packaging"),
)

#: Extensions that are source rather than build output.
#:
#: The five Package I adds are the ones a Windows packaging tree is written
#: in. ``.iss``, ``.nsi`` and ``.wxs`` are listed although ADR-0010 2
#: eliminated the installers that use them, for the reason every boundary
#: list in this repository is written wide: the file that escapes a scan is
#: the one somebody adds after the scan was written.
SOURCE_SUFFIXES = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".css",
        ".json",
        ".spec",
        ".ps1",
        ".psm1",
        ".bat",
        ".cmd",
        ".iss",
        ".nsi",
        ".wxs",
    }
)

#: Directories that are generated and are supposed to be absent from git.
#: Anything under a dot-directory counts too: no source in this repository
#: lives in one, and Playwright drops trace artefacts into ``e2e/.artifacts``.
#:
#: Note what is **not** here: ``build`` and ``out``. The repository's
#: .gitignore carries both as unanchored rules, so ``packaging/build/
#: helper.py`` would be invisible to git - and adding ``build`` here would
#: make it invisible to this scan as well, which is precisely the pair of
#: blind spots that turned ``credentials.py`` into a CI-only
#: ``ModuleNotFoundError`` in Package G. The Windows bundle is written to
#: ``packaging/artifacts`` instead, under its own anchored ignore rule, so
#: this list did not have to grow (ADR-0010 3).
GENERATED_NAMES = frozenset({"__pycache__", "node_modules", "dist"})

#: The one directory in the packaging tree that holds build output. Written
#: as a full relative path rather than a bare name, so it exempts exactly one
#: place and not every directory that happens to share its name.
ARTIFACT_DIR = Path("packaging") / "artifacts"


def _is_generated(relative: Path) -> bool:
    """True for build output rather than source a fresh clone would need."""
    if relative.is_relative_to(ARTIFACT_DIR):
        return True
    return any(
        part in GENERATED_NAMES or part.startswith(".") for part in relative.parts
    )


def _tracked_paths(repo_root: Path) -> frozenset[Path]:
    """What git says it is carrying, as paths relative to the repository."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607 - git is resolved from PATH on purpose
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    listed = completed.stdout.decode("utf-8").split("\0")
    return frozenset(Path(entry) for entry in listed if entry)


def _source_files_on_disk(repo_root: Path) -> list[Path]:
    """Source files a fresh clone would need, as paths relative to the root."""
    found: list[Path] = []
    for tree in SHIPPED_TREES:
        base = repo_root / tree
        if not base.is_dir():
            continue
        for candidate in base.rglob("*"):
            if not candidate.is_file():
                continue
            if candidate.suffix not in SOURCE_SUFFIXES:
                continue
            relative = candidate.relative_to(repo_root)
            if _is_generated(relative):
                continue
            found.append(relative)
    return found


def test_every_shipped_source_file_is_tracked_by_git(repo_root: Path) -> None:
    """A source file on disk but not in git runs here and fails everywhere else.

    This is the assertion that would have caught the ``credentials.py``
    exclusion before CI did.
    """
    tracked = _tracked_paths(repo_root)
    untracked = sorted(
        str(path) for path in _source_files_on_disk(repo_root) if path not in tracked
    )

    assert untracked == [], (
        "these source files exist on this machine but not in the repository, "
        "so a fresh clone would not have them: " + ", ".join(untracked)
    )


def test_the_tracking_scan_would_notice_a_missing_file(repo_root: Path) -> None:
    """Guards the guard: the comparison must be able to report an absence.

    Without this, a scan that silently found nothing to look at would pass
    forever and prove nothing - the same shape of vacuity the route-path scan
    in package D turned out to have.
    """
    on_disk = _source_files_on_disk(repo_root)
    assert len(on_disk) > 50, "the scan found almost nothing, so it is not scanning"

    tracked = _tracked_paths(repo_root)
    invented = Path("apps") / "station-api" / "src" / "station_api" / "not-here.py"
    assert invented not in tracked

    pretend_disk = [*on_disk, invented]
    missed = [path for path in pretend_disk if path not in tracked]
    assert missed == [invented]


def test_the_packaging_tree_contributes_files_and_not_only_python(
    repo_root: Path,
) -> None:
    """Guards the widening itself (ADR-0010 3).

    A suffix list that grew and never met a matching file is the H3 failure
    shape: an inventory of four where there were five. So the packaging tree
    must actually contribute, and it must contribute something that is not a
    ``.py`` - otherwise the five extensions Package I added have never been
    exercised by this scan.
    """
    on_disk = _source_files_on_disk(repo_root)
    from_packaging = [
        path for path in on_disk if path.parts[0] == "packaging"
    ]
    assert from_packaging, "the packaging tree contributed no source file"

    non_python = {path.suffix for path in from_packaging if path.suffix != ".py"}
    assert non_python, (
        "every packaging source is a .py, so the suffixes ADR-0010 3 added "
        "have never been opened by this scan"
    )


def test_a_source_file_in_a_pyinstaller_default_output_directory_is_not_exempt(
    repo_root: Path,
) -> None:
    """ADR-0010 3's named accident, driven rather than described.

    Both halves are measured. First, git really does refuse
    ``packaging/build/helper.py``: the ``build/`` rule is unanchored and
    matches at any depth, so a file there would exist on one machine and
    nowhere else. Second, this scan does **not** exempt it - if ``build``
    were added to :data:`GENERATED_NAMES` the file would become invisible to
    the scan as well and the pair of blind spots would be complete, which is
    exactly what happened to ``credentials.py``.

    The probe path is never created. It does not need to be: ``git
    check-ignore`` answers about a path, and the filter is a function.
    """
    probe = Path("packaging") / "build" / "helper.py"

    refused = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "check-ignore", "-q", str(probe)],  # noqa: S607 - resolved from PATH
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    assert refused.returncode == 0, (
        "git no longer ignores packaging/build/helper.py, so the hazard this "
        "test guards against has changed shape and the reasoning needs redoing"
    )

    assert not _is_generated(probe), (
        "the tracked-source scan exempts a PyInstaller default output "
        "directory name, so a source file placed there would be invisible to "
        "both git and this suite"
    )
    assert probe.suffix in SOURCE_SUFFIXES

    assert probe not in _tracked_paths(repo_root)


def test_the_only_exempt_packaging_directory_is_where_the_build_script_writes(
    repo_root: Path,
) -> None:
    """The exemption cannot drift away from the actual output location.

    ``packaging/artifacts`` is skipped by this scan. That is safe only for as
    long as it is also the directory ``build_bundle.py`` writes to; if the
    script were pointed back at PyInstaller's defaults the exemption would
    start covering a directory nothing produces and stop covering the one
    that fills up with build output.
    """
    source = (repo_root / "packaging" / "build_bundle.py").read_text(encoding="utf-8")

    assert 'ARTIFACT_ROOT: Final = PACKAGING_ROOT / "artifacts"' in source
    assert "BUNDLE_ROOT: Final = ARTIFACT_ROOT" in source
    assert "WORK_ROOT: Final = ARTIFACT_ROOT" in source
    assert str(ARTIFACT_DIR.as_posix()) == "packaging/artifacts"

    ignored = subprocess.run(
        # git is resolved from PATH on purpose, as everywhere else in this file.
        ["git", "check-ignore", "-q", "packaging/artifacts/bundle/x.exe"],  # noqa: S607
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    assert ignored.returncode == 0, "the build output directory is not ignored by git"


def test_the_credential_module_is_not_swallowed_by_the_ignore_rule(
    repo_root: Path,
) -> None:
    """The OpenCode credential module ships, and the ignore rule still bites.

    Both halves matter. The module must be in git, and ``credentials.*`` must
    still be refused - the fix was a rename, not an exemption.
    """
    tracked = _tracked_paths(repo_root)
    module = (
        Path("apps")
        / "station-api"
        / "src"
        / "station_api"
        / "opencode"
        / "credential_store.py"
    )
    assert module in tracked, "the OpenCode credential store is not in the repository"

    probe = repo_root / "apps" / "station-api" / "src" / "station_api" / "credentials.py"
    refused = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "check-ignore", "-q", str(probe)],  # noqa: S607 - resolved from PATH
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    assert refused.returncode == 0, (
        "the credentials.* ignore rule no longer refuses a file named "
        "credentials.py; the package G fix was a rename precisely so this "
        "rule could stay intact"
    )
