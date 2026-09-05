"""Where this build finds the files it ships with.

ADR-0010 1 is the reason this module exists, and it exists because a line
that had worked since Stage 1 only ever worked by accident::

    REPO_ROOT = Path(__file__).resolve().parents[4]

That is four directories up from ``station_api/app.py``, which is the
repository root **only** when the package is imported out of
``apps/station-api/src``. This machine's ``.venv`` carries
``_editable_impl_station_api.pth``, so it always was. Installed from a wheel
into ``site-packages``, ``parents[4]`` lands above the virtual environment,
``apps/station-web/dist`` is not there, and the application answers a **503
"Arayuz derlenmemis"** page - a silent, well-formatted failure that no test
in this repository looked at. Frozen by PyInstaller, ``__file__`` points into
a ``_MEIxxxx`` path that the loader synthesises and the same thing happens
one layer deeper.

Two rules follow, and both are ADR-0010 1 rather than taste.

**The path is never read from the environment.** ``LOOPBACK_HOST`` is a
constant for a reason and this is the same reason: pointing the packaged SPA
at another directory is exactly how somebody serves arbitrary JavaScript from
this origin, and it would run under a CSP whose ``script-src`` is ``'self'``.
So there is no ``STATION_WEB_DIST``, and a test asserts this module reads no
environment variable at all.

**A packaged run may not degrade quietly.** Where a development checkout with
no ``npm run build`` gets the 503 page - which is what that page is for - a
frozen build with no SPA beside it is a broken artefact, and this module says
so by raising :class:`PackagedLayoutError` at startup instead of serving a
page that looks like a build instruction to a user who has no build to run.
"""

from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path
from typing import Final

#: The attribute PyInstaller sets on :mod:`sys` in a frozen process. It names
#: the directory the bundle was unpacked into - for a ``onedir`` build, the
#: ``_internal`` folder beside the executable, which is not a temporary
#: directory and is not under ``%TEMP%`` (ADR-0010 2).
FROZEN_ROOT_ATTRIBUTE: Final = "_MEIPASS"

#: Where the built SPA sits inside a frozen bundle. Named here, once, so the
#: PyInstaller spec and this resolver cannot drift apart; a test reads the
#: spec and compares it against this constant.
BUNDLED_WEB_DIR: Final = "station_web"

#: Where the Alembic migration tree sits inside a frozen bundle. Alembic
#: reads ``env.py`` and every ``versions/*.py`` **as files**, not as modules,
#: so the tree has to exist on disk under the bundle root.
BUNDLED_MIGRATIONS_PARTS: Final = ("station_api", "db", "migrations")

#: The file whose presence means "this really is the built SPA".
WEB_INDEX_NAME: Final = "index.html"

#: The file whose presence means "this really is the migration tree".
MIGRATIONS_ENV_NAME: Final = "env.py"


class PackagedLayoutError(RuntimeError):
    """A packaged build is missing a file it was supposed to carry.

    Raised rather than returned. Every caller of this module needs a real
    directory to keep working, and the alternative to raising is the failure
    ADR-0010 1 was written about: an application that starts, looks healthy
    and serves a page saying the interface was not built to somebody holding
    a build that was supposed to contain it.
    """


def is_frozen() -> bool:
    """True inside a PyInstaller bundle.

    Both halves are required. ``sys.frozen`` alone is set by other freezers
    that do not provide the unpack root, and the root alone would be a
    surprising attribute to find on a normal interpreter.
    """
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, FROZEN_ROOT_ATTRIBUTE)


def frozen_root() -> Path | None:
    """The directory this bundle was unpacked into, or ``None`` if not frozen."""
    if not is_frozen():
        return None
    return Path(str(getattr(sys, FROZEN_ROOT_ATTRIBUTE))).resolve()


def package_dir() -> Path:
    """The ``station_api`` package directory, wherever it actually lives.

    ``importlib.resources`` rather than ``__file__`` arithmetic: it asks the
    import system where the package it already loaded came from, so an
    editable install, a wheel in ``site-packages`` and a relocated checkout
    all answer correctly and none of them is a directory count.
    """
    return Path(str(resources.files("station_api"))).resolve()


def source_checkout_root() -> Path | None:
    """The repository root when this build is running out of a checkout.

    Recognised by the two directories a checkout has and an installed package
    does not. Returning ``None`` is a real answer: a wheel installed into
    ``site-packages`` has no repository above it, and inventing one is how
    ``parents[4]`` came to point at the parent of a virtual environment.
    """
    parents = package_dir().parents
    if len(parents) < 4:
        return None
    candidate = parents[3]
    if (candidate / "apps" / "station-web").is_dir() and (
        candidate / "apps" / "station-api" / "pyproject.toml"
    ).is_file():
        return candidate
    return None


def migrations_dir() -> Path:
    """The Alembic script location for this build.

    Frozen builds get the copy the spec placed under the bundle root; every
    other build gets the one inside the installed package. A frozen build
    that is missing it raises rather than letting Alembic report a script
    location that does not exist as some later, less obvious error.
    """
    root = frozen_root()
    if root is not None:
        bundled = root.joinpath(*BUNDLED_MIGRATIONS_PARTS)
        if not (bundled / MIGRATIONS_ENV_NAME).is_file():
            raise PackagedLayoutError(
                "Bu paket veritabani surum dosyalarini tasimiyor. Paket "
                "eksik uretilmis; yeniden paketlenmesi gerekir."
            )
        return bundled
    return package_dir() / "db" / "migrations"


def shipped_web_dist() -> Path | None:
    """The built SPA this process should serve, or ``None`` if it ships none.

    Three answers, and the difference between them is the whole point:

    * **Frozen.** The copy inside the bundle, or :class:`PackagedLayoutError`
      if it is not there. A packaged run never reaches the "no build" page
      (ADR-0010 1).
    * **Checkout.** ``apps/station-web/dist``, which may legitimately be
      absent - a developer who has not run ``npm run build`` yet gets the 503
      page telling them to, which is the one situation that page describes
      truthfully.
    * **Neither.** ``None``. A wheel installed on its own carries no SPA, and
      saying so is better than naming a directory that was never going to be
      there.
    """
    root = frozen_root()
    if root is not None:
        bundled = root / BUNDLED_WEB_DIR
        if not (bundled / WEB_INDEX_NAME).is_file():
            raise PackagedLayoutError(
                "Bu paket derlenmis arayuzu tasimiyor. Paket eksik "
                "uretilmis; yeniden paketlenmesi gerekir."
            )
        return bundled

    checkout = source_checkout_root()
    if checkout is None:
        return None
    return checkout / "apps" / "station-web" / "dist"


__all__ = [
    "BUNDLED_MIGRATIONS_PARTS",
    "BUNDLED_WEB_DIR",
    "FROZEN_ROOT_ATTRIBUTE",
    "MIGRATIONS_ENV_NAME",
    "WEB_INDEX_NAME",
    "PackagedLayoutError",
    "frozen_root",
    "is_frozen",
    "migrations_dir",
    "package_dir",
    "shipped_web_dist",
    "source_checkout_root",
]
