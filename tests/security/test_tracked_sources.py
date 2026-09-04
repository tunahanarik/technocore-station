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
)

#: Extensions that are source rather than build output.
SOURCE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".css", ".json"})

#: Directories that are generated and are supposed to be absent from git.
#: Anything under a dot-directory counts too: no source in this repository
#: lives in one, and Playwright drops trace artefacts into ``e2e/.artifacts``.
GENERATED_NAMES = frozenset({"__pycache__", "node_modules", "dist"})


def _is_generated(relative: Path) -> bool:
    """True for build output rather than source a fresh clone would need."""
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
