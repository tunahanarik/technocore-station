# PyInstaller spec for Technocore Station (ADR-0010 2).
#
# onedir, console, ZIP. Not an installer, not onefile, not MSIX, not Tauri -
# every one of those was eliminated with a measurement in ADR-0010 2, and the
# two that matter here are worth repeating beside the code they shape:
#
#   * **onefile is refused.** It unpacks to %TEMP%\_MEIxxxx on every launch.
#     This product writes to %TEMP% nowhere today (its only tempfile use is
#     `dir=target.parent`, inside the data directory), so onefile would break
#     a property that is currently true.
#   * **the console stays.** `console=False` sends stderr nowhere at all in a
#     frozen build, and start-up failures - a claimed data directory, a
#     database from a newer Station, a bundle missing its SPA - are exactly
#     what a user would then never see. ADR-0010 7 keeps it visible rather
#     than adding a file log outside the redaction chain to compensate.
#
# Nothing here binds an address, runs a program or reads an environment
# variable. tests/security/test_bind.py and
# tests/security/test_packaging_boundary.py scan this file for all three.

import os

REPO_ROOT = os.path.dirname(SPECPATH)  # noqa: F821 - PyInstaller injects SPECPATH

# The entry point. `station_api/__main__.py` is the same module
# `python -m station_api` runs, so the packaged and the source launch paths
# are one code path rather than two that can drift.
ENTRY_SCRIPT = os.path.join(
    REPO_ROOT, "apps", "station-api", "src", "station_api", "__main__.py"
)

# The audited SPA, verbatim. This is the *only* source of the shipped
# frontend, and tests/security/test_frontend_bundle.py reads this file to
# check that: the six bundle audits inspect apps/station-web/dist, so
# shipping anything else would be shipping bytes nothing looked at
# (ADR-0010 4).
WEB_DIST_SOURCE = os.path.join(REPO_ROOT, "apps", "station-web", "dist")
WEB_DIST_TARGET = "station_web"  # station_api.resources.BUNDLED_WEB_DIR

# Alembic reads env.py and every versions/*.py as *files*, not as modules, so
# the tree is carried as data and found through
# station_api.resources.migrations_dir() under sys._MEIPASS.
MIGRATIONS_SOURCE = os.path.join(
    REPO_ROOT, "apps", "station-api", "src", "station_api", "db", "migrations"
)
MIGRATIONS_TARGET = os.path.join("station_api", "db", "migrations")

# The pinned conformance vectors. technocore_conform.selftest reads them
# through importlib.resources, and a build that dropped them would fail the
# self-test at run time - which closes the write gate rather than crashing,
# i.e. exactly the quiet degradation this package is here to remove.
VECTORS_SOURCE = os.path.join(
    REPO_ROOT,
    "packages",
    "technocore-conform",
    "src",
    "technocore_conform",
    "vectors",
)
VECTORS_TARGET = os.path.join("technocore_conform", "vectors")


def tree_datas(source, target):
    """Every file under `source`, as PyInstaller (file, target-dir) pairs.

    Handing PyInstaller a *directory* copies whatever is in it, and what was
    in these two was `__pycache__`. A `.pyc` stores the absolute path of the
    source it was compiled from in `co_filename`, so the shipped ZIP carried
    the building developer's user name and home directory in eleven files -
    ten migration modules and the vectors package marker. The exe and the PYZ
    were clean; the ZIP is the only thing anybody receives.

    Stale bytecode is the second reason. A `.pyc` whose mtime matches can be
    used ahead of the `.py` beside it, and the `.py` beside it is what
    Alembic is meant to read.

    So the tree is enumerated file by file and the caches are left behind.
    `tests/security/test_packaging_boundary.py` scans the produced artefact
    for both.
    """
    collected = []
    for base, directories, files in os.walk(source):
        directories[:] = [name for name in directories if name != "__pycache__"]
        relative = os.path.relpath(base, source)
        destination = target if relative == os.curdir else os.path.join(target, relative)
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")):
                continue
            collected.append((os.path.join(base, name), destination))
    return sorted(collected)


APP_NAME = "TechnocoreStation"

analysis = Analysis(  # noqa: F821 - injected by PyInstaller
    [ENTRY_SCRIPT],
    pathex=[
        os.path.join(REPO_ROOT, "apps", "station-api", "src"),
        os.path.join(REPO_ROOT, "packages", "technocore-conform", "src"),
    ],
    binaries=[],
    datas=[
        # The SPA is a build output and has no caches in it, so it is copied
        # as a directory. The two Python trees are not: see tree_datas.
        (WEB_DIST_SOURCE, WEB_DIST_TARGET),
        *tree_datas(MIGRATIONS_SOURCE, MIGRATIONS_TARGET),
        *tree_datas(VECTORS_SOURCE, VECTORS_TARGET),
    ],
    # Imported by string somewhere in the dependency graph and therefore
    # invisible to the static analysis: alembic loads env.py, and uvicorn
    # picks its loop and protocol implementations by name.
    hiddenimports=[
        "alembic",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # PyNaCl is a *test* dependency (see apps/station-api/pyproject.toml) and
    # a security test asserts it is absent from the production import graph.
    # Excluding it here keeps that true of the shipped artefact too.
    excludes=["nacl", "pytest", "hypothesis", "mypy", "ruff"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)  # noqa: F821 - injected by PyInstaller

exe = EXE(  # noqa: F821 - injected by PyInstaller
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,  # onedir: the binaries are COLLECTed beside the exe
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # ADR-0010 7. Do not set this to False.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    # No code signing: there is no certificate on this machine and none in
    # CI, and ADR-0010 9 asks for the absence to be *stated* rather than
    # worked around. docs/packaging.md says it in the user's own words.
    codesign_identity=None,
    entitlements_file=None,
)

collected = COLLECT(  # noqa: F821 - injected by PyInstaller
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
