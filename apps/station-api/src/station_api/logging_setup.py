"""Logging with mandatory redaction.

The bootstrap token and the per-session CSRF value must never reach a log
sink (SI-07, SI-23). Two independent mechanisms enforce this:

1. A regex that scrubs ``/session/<token>`` shaped paths, so an access log
   line can never carry a live token even if one is enabled by accident.
2. A registry of exact secret strings, populated when a token or CSRF value
   is minted and cleared when it dies.

Both are applied to **every** text surface of a log record, not just the
formatted message: a traceback and a stack dump are rendered by
``logging.Formatter`` long after any filter has run, and an exception's own
``repr`` routinely embeds the value that caused it (SI-127).

The launcher additionally disables the uvicorn access log entirely; this
module is defence in depth, not the only barrier.
"""

from __future__ import annotations

import logging
import re
import threading
import traceback
from types import TracebackType

#: What ``LogRecord.exc_info`` holds: exactly ``sys.exc_info()``'s shape.
type ExcInfo = (
    tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
)

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
    """Scrub secrets from every text surface of a record (SI-07, SI-23, SI-127).

    A log record carries three independent pieces of text, and redacting only
    the first is a bypass:

    ``message``
        ``record.msg`` interpolated with ``record.args``.
    ``exc_text``
        the traceback. ``logging.Formatter.format`` renders it from
        ``record.exc_info`` *after* every filter has run, so a filter that
        leaves ``exc_info`` alone never sees it. This matters because an
        exception's ``repr`` is written by whoever raised it: a validation
        error embeds the offending value, and that value can be a live token
        or a whole response body. The traceback is therefore rendered *here*
        and stored in ``exc_text``, which ``Formatter.format`` reuses instead
        of re-rendering (the standard-library contract for that attribute).
    ``stack_info``
        the ``stack_info=True`` dump, appended by the formatter verbatim.

    An ``exc_text`` that arrives already populated - another formatter ran
    first - is scrubbed too, so the cached value can never be the raw one.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = None
        if message is not None:
            scrubbed = redact(message)
            if scrubbed != message:
                record.msg = scrubbed
                record.args = ()

        exc_text = record.exc_text
        if exc_text is None and record.exc_info is not None:
            exc_text = _format_exception(record.exc_info)
        if exc_text is not None:
            record.exc_text = redact(exc_text)

        if record.stack_info is not None:
            record.stack_info = redact(record.stack_info)

        return True


def _format_exception(exc_info: ExcInfo) -> str:
    """Render a traceback, never raising and never returning the raw text.

    If rendering fails the caller still gets a string, so ``exc_text`` is set
    either way and the formatter is left with nothing to render itself. A lost
    traceback is an operational annoyance; an unredacted one is a leak.
    """
    try:
        return "".join(traceback.format_exception(*exc_info))
    except Exception:  # pragma: no cover - defensive: a hostile __repr__
        return "<traceback unavailable: it could not be rendered safely>"


#: Loggers that must carry the filter themselves rather than merely inherit
#: it from the root handler. Starlette's ServerErrorMiddleware re-raises every
#: unhandled exception after the application handler has run, and uvicorn
#: logs that second copy through ``uvicorn.error``. Today those records
#: propagate to root (the launcher passes ``log_config=None``), but a filter
#: bound to the logger keeps them scrubbed even if uvicorn ever gains its own
#: handler - which is the right place for it, rather than replacing handlers
#: this project does not own.
FILTERED_LOGGER_NAMES = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")


def _install_filter_once(target: logging.Logger | logging.Handler) -> None:
    """Add a ``RedactingFilter`` unless one is already attached."""
    if not any(isinstance(existing, RedactingFilter) for existing in target.filters):
        target.addFilter(RedactingFilter())


def configure_logging(level: int = logging.INFO) -> None:
    """Install a single redacting handler on the root logger.

    ``force=True`` replaces any handler another library may have installed, so
    there is no unfiltered path to stderr. Library loggers propagate to root
    and are therefore filtered too; the loggers named above are additionally
    filtered at the source, so they stay scrubbed even off the root path.
    """
    handler = logging.StreamHandler()
    _install_filter_once(handler)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    for name in FILTERED_LOGGER_NAMES:
        _install_filter_once(logging.getLogger(name))
