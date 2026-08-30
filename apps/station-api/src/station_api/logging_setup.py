"""Logging with mandatory redaction.

The bootstrap token and the per-session CSRF value must never reach a log
sink (SI-07, SI-23). Two independent mechanisms enforce this:

1. A regex that scrubs ``/session/<token>`` shaped paths, so an access log
   line can never carry a live token even if one is enabled by accident.
2. A registry of exact secret strings, populated when a token or CSRF value
   is minted and cleared when it dies.

The launcher additionally disables the uvicorn access log entirely; this
module is defence in depth, not the only barrier.
"""

from __future__ import annotations

import logging
import re
import threading

# Matches the one-shot session handoff URL. The token alphabet is that of
# secrets.token_urlsafe: base64url without padding.
_SESSION_PATH_RE = re.compile(r"(/session/)[A-Za-z0-9_-]{8,}")

_REDACTED = "<redacted>"

# Exact secret values to scrub. Bounded: at most a handful are ever live.
_secret_registry: set[str] = set()
_registry_lock = threading.Lock()

# Never register a value shorter than this; scrubbing a short common string
# would corrupt unrelated log lines.
_MIN_REGISTERABLE_LENGTH = 16


def register_secret(value: str) -> None:
    """Mark an exact string as never-loggable."""
    if len(value) < _MIN_REGISTERABLE_LENGTH:
        return
    with _registry_lock:
        _secret_registry.add(value)


def forget_secret(value: str) -> None:
    """Drop a secret from the registry once it can no longer appear."""
    with _registry_lock:
        _secret_registry.discard(value)


def clear_secret_registry() -> None:
    """Test helper: empty the registry."""
    with _registry_lock:
        _secret_registry.clear()


def redact(text: str) -> str:
    """Remove every known secret shape from ``text``."""
    scrubbed = _SESSION_PATH_RE.sub(rf"\1{_REDACTED}", text)
    with _registry_lock:
        secrets_snapshot = tuple(_secret_registry)
    for secret in secrets_snapshot:
        if secret in scrubbed:
            scrubbed = scrubbed.replace(secret, _REDACTED)
    return scrubbed


class RedactingFilter(logging.Filter):
    """Scrub secrets from every record passing through a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        scrubbed = redact(message)
        if scrubbed != message:
            record.msg = scrubbed
            record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Install a single redacting handler on the root logger.

    ``force=True`` replaces any handler another library may have installed, so
    there is no unfiltered path to stderr. Library loggers propagate to root
    and are therefore filtered too.
    """
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=level, handlers=[handler], force=True)
