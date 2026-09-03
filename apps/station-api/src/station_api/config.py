"""Runtime settings for the Station local core.

Security-relevant defaults are **fail closed**: development mode is off unless
explicitly and unambiguously enabled, and the bind host is a module constant
that is never read from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# The application binds here and nowhere else. This is deliberately a constant:
# it is not configurable, not read from the environment, and not overridable.
# Binding to a wildcard address would expose the local core to the LAN.
LOOPBACK_HOST = "127.0.0.1"

#: Lifetime of the single-use bootstrap token handed to the browser.
BOOTSTRAP_TOKEN_TTL_SECONDS = 30

#: Session cookie name. Deliberately unremarkable.
SESSION_COOKIE_NAME = "station_session"

#: Header carrying the per-session CSRF value on state-changing requests.
CSRF_HEADER_NAME = "X-Station-CSRF"

#: Header carrying the per-request correlation id on every response. The value
#: is a fresh ``uuid4().hex`` per request: random, meaningless and safe to show
#: anywhere, so a user can quote it when reporting a failure and the matching
#: server log line can be found without either side handling a secret.
REQUEST_ID_HEADER_NAME = "X-Station-Request-Id"

#: Default port used ONLY in development, so the Vite proxy has a fixed target.
#: Production always takes an ephemeral port from the operating system.
DEFAULT_DEV_PORT = 8787

#: Origin the Vite dev server runs on. Accepted ONLY when dev mode is enabled.
DEFAULT_DEV_ORIGIN = "http://127.0.0.1:5173"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_flag(name: str) -> bool:
    """Parse a boolean flag fail-closed.

    Anything that is not an explicit, recognised truthy value is False, so a
    typo can never accidentally enable a development affordance.
    """
    raw = os.environ.get(name)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY


def _default_data_dir() -> Path:
    """Per-user application data directory.

    The Windows production path is ``%LOCALAPPDATA%\\TechnocoreStation``. The
    POSIX branch exists so the test suite can run off-Windows; it is not a
    supported deployment target (ADR-008: Windows-only MVP).
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "TechnocoreStation"
    return Path.home() / ".local" / "share" / "TechnocoreStation"


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    dev_mode: bool = False
    data_dir: Path = field(default_factory=_default_data_dir)
    dev_port: int = DEFAULT_DEV_PORT
    dev_origin: str = DEFAULT_DEV_ORIGIN
    bootstrap_token_ttl_seconds: int = BOOTSTRAP_TOKEN_TTL_SECONDS

    @property
    def database_path(self) -> Path:
        """Absolute path to the SQLite database. Never exposed over HTTP."""
        return self.data_dir / "station.sqlite3"

    def ensure_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


def load_settings() -> Settings:
    """Build settings from the environment.

    Recognised variables:

    ``STATION_DEV``        enable development mode (default: off, fail closed)
    ``STATION_DATA_DIR``   override the application data directory
    ``STATION_DEV_PORT``   fixed backend port, development only
    ``STATION_DEV_ORIGIN`` Vite origin accepted, development only
    """
    data_dir_raw = os.environ.get("STATION_DATA_DIR")
    data_dir = Path(data_dir_raw) if data_dir_raw else _default_data_dir()

    dev_port_raw = os.environ.get("STATION_DEV_PORT")
    try:
        dev_port = int(dev_port_raw) if dev_port_raw else DEFAULT_DEV_PORT
    except ValueError:
        dev_port = DEFAULT_DEV_PORT

    return Settings(
        dev_mode=_env_flag("STATION_DEV"),
        data_dir=data_dir,
        dev_port=dev_port,
        dev_origin=os.environ.get("STATION_DEV_ORIGIN", DEFAULT_DEV_ORIGIN),
    )
