"""SI-01, SI-02, SI-03 - the application listens on loopback, on an OS-chosen port."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from station_api.config import LOOPBACK_HOST, Settings
from station_api.launcher import reserve_loopback_socket

pytestmark = pytest.mark.security

# Safe to name directly: the scans below never read tests/, so this file can
# hold the literal it forbids elsewhere.
WILDCARD_IPV4 = "0.0.0.0"  # noqa: S104 - the literal under test, never bound

#: Suffixes the packaging tree is opened with.
#:
#: ADR-0010 3 measured the hole this closes: until Package I the wildcard scan
#: read ``*.py`` under ``apps/station-api/src`` and nothing else, so a
#: ``0.0.0.0`` in a PyInstaller ``.spec``, an Inno Setup ``.iss``, a ``.bat``
#: or a ``.ps1`` was invisible - and Package I is precisely the package that
#: introduces files with those extensions. ``.iss``, ``.nsi`` and ``.wxs`` are
#: on the list although ADR-0010 2 eliminated the installers that use them:
#: the point of a boundary scan is to cover the file somebody adds later.
PACKAGING_SUFFIXES = frozenset(
    {
        ".py",
        ".spec",
        ".ps1",
        ".psm1",
        ".bat",
        ".cmd",
        ".iss",
        ".nsi",
        ".wxs",
        ".xml",
        ".json",
        ".yml",
        ".yaml",
        ".toml",
        ".cfg",
    }
)

#: Directory names that never hold a hand-written file.
#:
#: Note what is **not** here any more: ``build``, ``dist`` and ``out``.
#: Excluding those by *name* is the blind spot ADR-0010 3 refused in the
#: sister scan - the repository's .gitignore already matches all three at any
#: depth, so a ``packaging/build/helper.py`` is invisible to git, and a scan
#: that skipped the name too would make the pair of blind spots complete.
#: ``tests/security/test_tracked_sources.py`` has always kept them off its
#: list for that reason; this file now agrees with it.
GENERATED_DIR_NAMES = frozenset({"__pycache__", "node_modules"})

#: The one place under a scanned tree that holds produced files.
#:
#: Written as a full relative path rather than a bare directory name, and
#: that distinction is the whole fix. Package I measured the alternative: with
#: a bundle on disk the scan below opened **fourteen** files under
#: ``packaging/``, twelve of them copies of sources it had already read, so
#: the same test examined a different set of files on a developer's machine
#: than in CI. Adding ``artifacts`` to :data:`GENERATED_DIR_NAMES` would have
#: fixed the count and bought the blindness back - every directory anywhere
#: called ``artifacts`` would stop being read. Naming one exact location
#: excuses one exact location, and the test below pins it to where
#: ``packaging/build_bundle.py`` actually writes.
ARTIFACT_DIR = Path("packaging") / "artifacts"

#: Every tree the wildcard scan reads, and the suffixes it opens in each.
#:
#: The workflow directory is here because ADR-0010 10 puts an artefact run in
#: CI: the job that starts the packaged application and checks what it bound
#: is itself a place a wildcard address could be written.
SCANNED_TREES: tuple[tuple[Path, frozenset[str]], ...] = (
    (Path("apps") / "station-api" / "src", frozenset({".py"})),
    (Path("packages") / "technocore-conform" / "src", frozenset({".py"})),
    (Path("apps") / "station-web" / "e2e" / "harness", frozenset({".py"})),
    (Path("packaging"), PACKAGING_SUFFIXES),
    (Path(".github") / "workflows", frozenset({".yml", ".yaml"})),
)


def _is_generated(path: Path, tree_root: Path) -> bool:
    """Caches and vendored trees, by directory name, within one scanned tree.

    Relative to the tree rather than to the repository on purpose: one of the
    scanned trees *is* ``.github/workflows``, and a dot-directory rule applied
    from the repository root would skip the CI lane ADR-0010 3 added.
    """
    relative = path.relative_to(tree_root)
    return any(
        part in GENERATED_DIR_NAMES or part.startswith(".")
        for part in relative.parts[:-1]
    )


def _is_produced_copy(path: Path, repo_root: Path) -> bool:
    """True for a file a build wrote, as opposed to one a person wrote.

    The subject of this rule is source. A ``.py`` inside the bundle is a copy
    of a ``.py`` the scan already opened under ``apps/station-api/src``, so
    reading it adds no coverage and makes the scan's size depend on whether
    somebody has run a build.
    """
    return path.relative_to(repo_root).is_relative_to(ARTIFACT_DIR)


def _scanned_files(repo_root: Path) -> list[Path]:
    """Every file the wildcard scan opens, as absolute paths."""
    found: list[Path] = []
    for tree, suffixes in SCANNED_TREES:
        base = repo_root / tree
        if not base.is_dir():
            continue
        for candidate in base.rglob("*"):
            if not candidate.is_file() or candidate.suffix not in suffixes:
                continue
            if _is_generated(candidate, base) or _is_produced_copy(candidate, repo_root):
                continue
            found.append(candidate)
    return found


def _wildcard_offenders(paths: list[Path]) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if WILDCARD_IPV4 in text or "INADDR_ANY" in text:
            offenders.append(str(path))
    return offenders


def test_loopback_host_constant_is_the_literal_loopback_address() -> None:
    assert LOOPBACK_HOST == "127.0.0.1"


def test_launcher_binds_only_loopback(tmp_path: Path) -> None:
    settings = Settings(dev_mode=False, data_dir=tmp_path)
    sock, port = reserve_loopback_socket(settings)
    try:
        bound_host, bound_port = sock.getsockname()
        assert bound_host == "127.0.0.1"
        assert bound_port == port
    finally:
        sock.close()


def test_port_is_ephemeral(tmp_path: Path) -> None:
    """The operating system chooses the port, not the application.

    Three sockets are held open at once, so the ports are necessarily
    distinct. A hardcoded port would collide and could not produce three
    different values.
    """
    settings = Settings(dev_mode=False, data_dir=tmp_path)
    sockets: list[socket.socket] = []
    ports: list[int] = []
    try:
        for _ in range(3):
            sock, port = reserve_loopback_socket(settings)
            sockets.append(sock)
            ports.append(port)
    finally:
        for sock in sockets:
            sock.close()

    assert len(set(ports)) == 3
    for port in ports:
        assert 1024 < port < 65536


def test_bound_port_is_not_reachable_on_a_non_loopback_address(tmp_path: Path) -> None:
    """A wildcard bind would also answer on a LAN address. This one must not."""
    settings = Settings(dev_mode=False, data_dir=tmp_path)
    sock, port = reserve_loopback_socket(settings)
    try:
        for address in _non_loopback_addresses():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                with pytest.raises(OSError):
                    probe.connect((address, port))
    finally:
        sock.close()


def test_no_wildcard_bind_in_source(repo_root: Path) -> None:
    """SI-02, widened by ADR-0010 3 past the ``.py`` files it used to read."""
    assert _wildcard_offenders(_scanned_files(repo_root)) == []


def test_the_wildcard_scan_opens_the_packaging_tree(repo_root: Path) -> None:
    """Guards the guard, in the half that was actually missing.

    A scan that grew a suffix list but never met a file carrying one of those
    suffixes is the ADR-0009 5 failure shape: an inventory of four where
    there were five, and the fifth stayed silent. So this counts the files
    the scan opened, separately for the extensions ADR-0010 3 added, and
    fails if the packaging tree contributed only ``.py``.
    """
    opened = _scanned_files(repo_root)
    assert len(opened) > 50, "the scan found almost nothing, so it is not scanning"

    packaging_root = repo_root / "packaging"
    from_packaging = [path for path in opened if packaging_root in path.parents]
    assert from_packaging, "the packaging tree contributed no file to the scan"

    non_python = {path.suffix for path in from_packaging if path.suffix != ".py"}
    assert non_python, (
        "every file the packaging tree contributed is a .py, so the extensions "
        "ADR-0010 3 added have never been opened by this scan"
    )

    workflows = [path for path in opened if path.suffix in {".yml", ".yaml"}]
    assert workflows, "no workflow file was opened; the CI lane is unscanned"


@pytest.mark.parametrize(
    "filename",
    ["planted.spec", "planted.ps1", "planted.bat", "planted.iss", "planted.yml"],
)
def test_the_wildcard_scan_reports_a_planted_violation(
    tmp_path: Path, filename: str
) -> None:
    """The deny side, once per extension family ADR-0010 3 named.

    One combined probe would pass as soon as a single suffix fired and the
    others could be missing from the list for a release without anybody
    noticing.
    """
    planted = tmp_path / filename
    planted.write_text(f'host = "{WILDCARD_IPV4}"\n', encoding="utf-8")

    assert planted.suffix in PACKAGING_SUFFIXES
    assert _wildcard_offenders([planted]) == [str(planted)]


def _synthetic_packaging_tree(root: Path) -> None:
    """A repository-shaped tree: one packaging source, one produced bundle.

    Built rather than borrowed so the assertions below hold on a machine that
    has never run a build and on one that has - which is the property the
    real tree lost.
    """
    packaging = root / "packaging"
    packaging.mkdir(parents=True)
    (packaging / "station.spec").write_text('host = "127.0.0.1"\n', encoding="utf-8")

    copied = packaging / "artifacts" / "bundle" / "TechnocoreStation" / "_internal"
    copied.mkdir(parents=True)
    (copied / "0001_initial_schema.py").write_text("revision = '0001'\n", encoding="utf-8")
    (copied / "conformance-v1.json").write_text("{}\n", encoding="utf-8")


def test_the_scan_reads_the_packaging_sources_and_not_the_bundle_beside_them(
    tmp_path: Path,
) -> None:
    """The count must not depend on whether anybody has built anything.

    Package I measured two files here before a build and fourteen after
    (``docs/verification/paket-i.md`` 13.5). Twelve of those fourteen were
    copies of sources the scan had already opened elsewhere, so the extra
    reading bought no coverage and cost determinism: the same test inspected
    a different set of files on a developer's machine than in CI.
    """
    _synthetic_packaging_tree(tmp_path)

    scanned = _scanned_files(tmp_path)

    assert [path.name for path in scanned] == ["station.spec"]


def test_the_bundle_the_scan_skips_really_did_contain_readable_files(
    tmp_path: Path,
) -> None:
    """Guards the guard: the exclusion has to have had something to exclude.

    Without this, the test above would pass just as well against a scan that
    found nothing at all, or against suffix lists that never matched the
    planted copies in the first place.
    """
    _synthetic_packaging_tree(tmp_path)

    inside = [
        path
        for path in (tmp_path / "packaging" / "artifacts").rglob("*")
        if path.is_file() and path.suffix in PACKAGING_SUFFIXES
    ]

    assert len(inside) == 2
    assert all(_is_produced_copy(path, tmp_path) for path in inside)


def test_a_wildcard_in_a_pyinstaller_default_output_directory_is_still_reported(
    tmp_path: Path,
) -> None:
    """The deny side of the same change, and the one that could have gone wrong.

    ``build``, ``dist`` and ``out`` used to be skipped by name. They are
    PyInstaller's default output names, which is exactly why ADR-0010 3 moved
    the real output somewhere else instead of exempting them - and why a file
    left in one of them must still be read rather than assumed generated.
    """
    for directory in ("build", "dist", "out"):
        planted = tmp_path / "packaging" / directory / "planted.spec"
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(f'host = "{WILDCARD_IPV4}"\n', encoding="utf-8")

    offenders = _wildcard_offenders(_scanned_files(tmp_path))

    assert len(offenders) == 3
    assert all("planted.spec" in offender for offender in offenders)


def test_no_file_the_real_scan_opens_lives_in_the_build_output_directory(
    repo_root: Path,
) -> None:
    """The same property, asserted against the repository as it stands.

    Passes with a bundle on disk and without one, which is the point.
    """
    inside = [
        str(path)
        for path in _scanned_files(repo_root)
        if _is_produced_copy(path, repo_root)
    ]

    assert inside == []


def test_the_exempt_directory_is_the_one_the_build_script_writes_to(
    repo_root: Path,
) -> None:
    """The exemption cannot drift away from the actual output location.

    Same reasoning, and deliberately the same assertion, as
    ``test_tracked_sources.py::test_the_only_exempt_packaging_directory_is_where_the_build_script_writes``:
    skipping ``packaging/artifacts`` is safe only for as long as that is
    where the build script puts its output. The two scans are held to one
    definition rather than two that can drift apart.
    """
    from tests.security.test_tracked_sources import ARTIFACT_DIR as TRACKED_ARTIFACT_DIR

    assert ARTIFACT_DIR == TRACKED_ARTIFACT_DIR
    assert ARTIFACT_DIR.as_posix() == "packaging/artifacts"

    source = (repo_root / "packaging" / "build_bundle.py").read_text(encoding="utf-8")
    assert 'ARTIFACT_ROOT: Final = PACKAGING_ROOT / "artifacts"' in source
    assert "BUNDLE_ROOT: Final = ARTIFACT_ROOT" in source
    assert "WORK_ROOT: Final = ARTIFACT_ROOT" in source


def test_vite_dev_server_is_loopback_only(repo_root: Path) -> None:
    config = (repo_root / "apps" / "station-web" / "vite.config.ts").read_text(
        encoding="utf-8"
    )
    assert 'host: "127.0.0.1"' in config
    assert WILDCARD_IPV4 not in config
    assert "host: true" not in config


def _non_loopback_addresses() -> list[str]:
    """Best-effort list of this machine's non-loopback IPv4 addresses.

    An empty list is fine: the getsockname assertion above already proves the
    bind address, and this check is an additional, opportunistic probe.
    """
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = str(info[4][0])
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        return []
    return sorted(addresses)
