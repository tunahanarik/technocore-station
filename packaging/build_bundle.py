"""Produce the Technocore Station Windows bundle (ADR-0010 2).

    uv run --project apps/station-api python packaging/build_bundle.py

Output: ``packaging/artifacts/bundle/TechnocoreStation/`` (PyInstaller
``onedir``) and ``packaging/artifacts/TechnocoreStation-<version>-windows-
x64.zip`` beside it. The
user unzips that into ``%LOCALAPPDATA%\\Programs\\TechnocoreStation\\``. There
is no installer, no registry write, no service, no scheduled task and no
administrator prompt anywhere in this file or in what it produces.

**This script reports its own preconditions and refuses rather than
approximating.** PyInstaller is not a dependency of this repository: it is
not in ``apps/station-api/pyproject.toml`` and not in ``uv.lock``, so on a
machine that has not been given it this script exits with code 2 and says
which precondition failed. It does not fetch it, and it never prints
"built" for something it did not build - which is the failure mode this
whole package exists to remove.

Two things this file deliberately does **not** contain:

* **No ``subprocess``.** PyInstaller is driven through its Python API. A
  packaging tree that grew a ``subprocess`` call would make
  ``arbitrary_execution_supported: Literal[False]`` and the
  ``execution_unavailable`` reason a false statement about the product as a
  whole, and until ADR-0010 3 nothing scanned this tree for it.
  ``tests/security/test_packaging_boundary.py`` does now.
* **No new hash helper.** The artefact digest comes from
  :func:`station_api.digests.file_digest` (ADR-0010 9).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "station-api" / "src"))

from station_api.digests import file_digest  # noqa: E402 - after the path fix above
from station_api.resources import BUNDLED_WEB_DIR  # noqa: E402 - same

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PACKAGING_ROOT: Final = REPO_ROOT / "packaging"
SPEC_PATH: Final = PACKAGING_ROOT / "station.spec"

#: Every byte this script produces goes under one directory, and that
#: directory is **not** called ``dist`` or ``build``.
#:
#: PyInstaller's defaults are exactly those two names, and the repository's
#: .gitignore has carried ``dist/`` and ``build/`` since Stage 1 as
#: unanchored rules that match at any depth. Accepting the defaults would
#: have meant exempting ``packaging/build`` from the tracked-source scan, and
#: ADR-0010 3 names the file that exemption swallows: ``packaging/build/
#: helper.py``, present on one machine, ``ModuleNotFoundError`` in CI - the
#: same accident ``credentials.py`` had in Package G. One narrow, anchored
#: ignore rule for one output directory removes the exemption instead of
#: documenting it.
ARTIFACT_ROOT: Final = PACKAGING_ROOT / "artifacts"
BUNDLE_ROOT: Final = ARTIFACT_ROOT / "bundle"
WORK_ROOT: Final = ARTIFACT_ROOT / "work"

APP_NAME: Final = "TechnocoreStation"
BUNDLE_VERSION: Final = "0.1.0"
ZIP_NAME: Final = f"{APP_NAME}-{BUNDLE_VERSION}-windows-x64.zip"

WEB_DIST: Final = REPO_ROOT / "apps" / "station-web" / "dist"

#: Printed beside every digest this script emits. ADR-0010 9 carries H3's
#: sentence forward and adds the half that only applies to an unsigned file.
UNSIGNED_NOTICE: Final = (
    "Bu ozet yalnizca dosya butunlugunu tanimlar: icerigin dogru veya "
    "yararli oldugunu kanitlamaz. Artefakt IMZASIZDIR, bu yuzden ozet onu "
    "kimin urettigini de kanitlamaz - ozetin kendisi dosyayla ayni kanaldan "
    "gelir. Windows SmartScreen imzasiz bir indirmeyi uyaracaktir; bu "
    "beklenen ve normal davranistir."
)


@dataclass(frozen=True, slots=True)
class Precondition:
    """One thing that has to be true, and whether it is."""

    name: str
    satisfied: bool
    detail: str


def _pyinstaller_precondition() -> Precondition:
    """Is PyInstaller importable in this environment?

    An import in a try, not a version probe against a package index: this
    script contacts nothing.
    """
    try:
        import PyInstaller  # the probe is the point
    except ImportError:
        return Precondition(
            name="pyinstaller",
            satisfied=False,
            detail=(
                "PyInstaller bu ortamda yok. Bu depoda bagimlilik degildir "
                "(apps/station-api/pyproject.toml ve uv.lock icinde yer "
                "almaz); eklemek bir bagimlilik karari ve kilit dosyasi "
                "guncellemesi gerektirir. Bu betik onu kendiliginden "
                "kurmaz."
            ),
        )
    return Precondition(
        name="pyinstaller",
        satisfied=True,
        detail=f"PyInstaller {PyInstaller.__version__}",
    )


def _frontend_precondition() -> Precondition:
    """Is there a production SPA build to ship?

    Checked here as well as in the spec because the spec's failure is a
    PyInstaller error deep in an analysis log, and this one is a sentence.
    """
    index = WEB_DIST / "index.html"
    if not index.is_file():
        return Precondition(
            name="frontend-build",
            satisfied=False,
            detail=(
                f"{WEB_DIST} icinde derlenmis arayuz yok. Once calistirin: "
                "npm --prefix apps/station-web run build"
            ),
        )
    return Precondition(name="frontend-build", satisfied=True, detail=str(WEB_DIST))


def _spec_precondition() -> Precondition:
    if not SPEC_PATH.is_file():
        return Precondition(
            name="spec", satisfied=False, detail=f"{SPEC_PATH} bulunamadi."
        )
    return Precondition(name="spec", satisfied=True, detail=str(SPEC_PATH))


def preconditions() -> tuple[Precondition, ...]:
    """Every precondition, evaluated. Nothing is skipped once one fails."""
    return (
        _spec_precondition(),
        _frontend_precondition(),
        _pyinstaller_precondition(),
    )


def report(checks: tuple[Precondition, ...]) -> None:
    for check in checks:
        mark = "OK  " if check.satisfied else "EKSIK"
        print(f"[{mark}] {check.name}: {check.detail}")


def _bundle_files(root: Path) -> Iterator[Path]:
    """Every file in the produced bundle, in a stable order.

    Sorted rather than ``rglob`` order so two runs on the same inputs write
    the archive's entries in the same sequence - the determinism discipline
    the proof bundle already follows.
    """
    yield from sorted(path for path in root.rglob("*") if path.is_file())


def make_zip(bundle_root: Path, destination: Path) -> Path:
    """Archive the onedir bundle, with the app directory as the top entry."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _bundle_files(bundle_root):
            arcname = Path(bundle_root.name) / path.relative_to(bundle_root)
            archive.write(path, arcname.as_posix())
    return destination


def build() -> int:
    checks = preconditions()
    report(checks)
    if not all(check.satisfied for check in checks):
        print()
        print("Artefakt URETILMEDI. Yukaridaki eksik on kosullari giderin.", file=sys.stderr)
        return 2

    import PyInstaller.__main__  # only after the check

    if WORK_ROOT.exists():
        shutil.rmtree(WORK_ROOT)
    bundle_root = BUNDLE_ROOT / APP_NAME
    if bundle_root.exists():
        shutil.rmtree(bundle_root)

    PyInstaller.__main__.run(
        [
            str(SPEC_PATH),
            "--noconfirm",
            "--distpath",
            str(BUNDLE_ROOT),
            "--workpath",
            str(WORK_ROOT),
        ]
    )

    if not (bundle_root / f"{APP_NAME}.exe").is_file():
        print("Artefakt URETILMEDI: beklenen exe olusmadi.", file=sys.stderr)
        return 3

    shipped_spa = bundle_root / "_internal" / BUNDLED_WEB_DIR
    if not (shipped_spa / "index.html").is_file():
        print(
            "Artefakt URETILDI fakat derlenmis arayuzu tasimiyor; "
            "yayimlanmamalidir.",
            file=sys.stderr,
        )
        return 3

    archive = make_zip(bundle_root, ARTIFACT_ROOT / ZIP_NAME)

    print()
    print(f"Bundle : {bundle_root}")
    print(f"Arsiv  : {archive}")
    print(f"Boyut  : {archive.stat().st_size} bayt")
    print(f"SHA-256: {file_digest(archive)}")
    print()
    print(UNSIGNED_NOTICE)
    print()
    print(
        "Kurulum: arsivi su dizine acin -> "
        + os.path.join("%LOCALAPPDATA%", "Programs", APP_NAME)
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_bundle",
        description="Technocore Station Windows paketini uretir (ADR-0010).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Yalnizca on kosullari raporla, hicbir sey uretme.",
    )
    arguments = parser.parse_args(argv)

    if arguments.check:
        checks = preconditions()
        report(checks)
        return 0 if all(check.satisfied for check in checks) else 2

    return build()


if __name__ == "__main__":
    raise SystemExit(main())
