"""``technocore-conform`` builds on its own, and ships only what it should.

Two things are being protected here. The package must stay independently
buildable, because that is what "portable, no application dependency" means
in practice. And the Apache-2.0 vendor reference must never end up inside an
MIT-licensed artefact.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.conformance

#: Building is slow enough to deserve a module-scoped fixture.
_BUILD_TIMEOUT = 600


@pytest.fixture(scope="module")
def built_artifacts(repo_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel and sdist into a temporary directory."""
    uv = shutil.which("uv")
    if uv is None:  # pragma: no cover - uv is the project's build tool
        pytest.fail("uv is not on PATH; it is the project's build tool")

    out_dir = tmp_path_factory.mktemp("conform-dist")
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            uv,
            "build",
            str(repo_root / "packages" / "technocore-conform"),
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"technocore-conform failed to build:\n{result.stderr[-2000:]}")
    return out_dir


def _wheel(out_dir: Path) -> Path:
    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected one wheel, found {wheels}"
    return wheels[0]


def _sdist(out_dir: Path) -> Path:
    sdists = list(out_dir.glob("*.tar.gz"))
    assert len(sdists) == 1, f"expected one sdist, found {sdists}"
    return sdists[0]


def test_the_package_builds_a_wheel_and_an_sdist(built_artifacts: Path) -> None:
    assert _wheel(built_artifacts).is_file()
    assert _sdist(built_artifacts).is_file()


def test_the_wheel_ships_the_conformance_vectors(built_artifacts: Path) -> None:
    """Without them the runtime self-test cannot run, and the gate stays shut."""
    with zipfile.ZipFile(_wheel(built_artifacts)) as archive:
        names = archive.namelist()
    assert "technocore_conform/vectors/conformance-v1.json" in names


def test_the_wheel_declares_the_cli_entry_point(built_artifacts: Path) -> None:
    with zipfile.ZipFile(_wheel(built_artifacts)) as archive:
        entry_points = next(
            (name for name in archive.namelist() if name.endswith("entry_points.txt")),
            None,
        )
        assert entry_points is not None
        content = archive.read(entry_points).decode()
    assert "technocore-conform" in content
    assert "technocore_conform.cli:main" in content


def test_the_vendor_reference_is_absent_from_both_artifacts(built_artifacts: Path) -> None:
    """AC-19. Apache-2.0 code must not travel inside an MIT wheel."""
    with zipfile.ZipFile(_wheel(built_artifacts)) as archive:
        wheel_names = archive.namelist()
    with tarfile.open(_sdist(built_artifacts)) as archive:
        sdist_names = archive.getnames()

    for names, label in ((wheel_names, "wheel"), (sdist_names, "sdist")):
        for name in names:
            lowered = name.lower()
            assert "vendor" not in lowered, f"vendor path in the {label}: {name}"
            assert "technocore-reference" not in lowered, f"vendor path in {label}: {name}"
            assert not lowered.endswith("sign.py"), f"reference signer in the {label}"
            assert not lowered.endswith("store.py"), f"reference store in the {label}"


def test_no_test_code_is_shipped(built_artifacts: Path) -> None:
    """The oracle lives under tests/ and must stay there."""
    with zipfile.ZipFile(_wheel(built_artifacts)) as archive:
        for name in archive.namelist():
            assert "oracle" not in name
            assert "vector_builder" not in name
            assert not name.startswith("tests/")


def test_the_wheel_declares_only_cryptography_as_a_runtime_dependency(
    built_artifacts: Path,
) -> None:
    """PyNaCl is a test tool; it must not enter the production import graph."""
    with zipfile.ZipFile(_wheel(built_artifacts)) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith("METADATA")
        )
        metadata = archive.read(metadata_name).decode()

    requires = [
        line.split(":", 1)[1].strip().lower()
        for line in metadata.splitlines()
        if line.startswith("Requires-Dist:")
    ]

    assert any(entry.startswith("cryptography") for entry in requires)
    for forbidden in ("pynacl", "fastapi", "sqlalchemy", "alembic", "uvicorn", "station-api"):
        assert not any(entry.startswith(forbidden) for entry in requires), (
            f"{forbidden} is a runtime dependency of technocore-conform"
        )


def test_the_wheel_is_pure_python(built_artifacts: Path) -> None:
    """Platform independence is the point of the package boundary."""
    assert "py3-none-any" in _wheel(built_artifacts).name
