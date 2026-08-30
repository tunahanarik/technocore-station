"""Room, namespace and key names.

The allow-list is narrow on purpose, and it is what makes the canonical string
safe to build by concatenation. Because a name can never contain ``|``, the
separator in ``room|nonce|text`` is unambiguous even though the text after it
may contain any number of pipes: the structural fields are read from the left,
and only the last field is free-form.

Widening this pattern - to uppercase, to Unicode letters, to a dot - would
reintroduce separator injection or path traversal through a name. It is
copied from the pinned reference's ``NAME_RE`` and must not drift.
"""

from __future__ import annotations

import re

from technocore_conform.errors import InvalidNameError

#: The official pattern, exactly as the reference spells it.
#:
#: The reference compiles it with ``^``/``$`` and applies ``fullmatch``. We
#: apply ``fullmatch`` to the unanchored pattern, which is the same language
#: and avoids a real trap: with ``re.search`` or ``re.match``, a trailing
#: ``$`` would also match just *before* a final newline, so "room\n" would be
#: accepted. A test pins both spellings to the same verdicts.
NAME_PATTERN = r"[a-z0-9][a-z0-9_-]{0,47}"

#: The reference's literal source spelling, kept for provenance and asserted
#: against ``NAME_PATTERN`` in the differential tests.
OFFICIAL_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,47}$"

_NAME_RE = re.compile(NAME_PATTERN)

#: 1 to 48 characters: one leading character plus at most 47 more.
MIN_NAME_LENGTH = 1
MAX_NAME_LENGTH = 48


def is_valid_name(value: object) -> bool:
    """Whether ``value`` is an acceptable room, namespace or key."""
    return isinstance(value, str) and _NAME_RE.fullmatch(value) is not None


def validate_name(value: object, *, field: str) -> str:
    """Return the name unchanged, or raise ``InvalidNameError``.

    ``field`` names the structural position ("room", "namespace", "key") so a
    traceback says which one failed. The offending value is not echoed.
    """
    if not isinstance(value, str):
        raise InvalidNameError(f"{field} must be a string")
    if _NAME_RE.fullmatch(value) is None:
        raise InvalidNameError(
            f"{field} must be {MIN_NAME_LENGTH}-{MAX_NAME_LENGTH} characters of lowercase "
            "ASCII letters, digits, '-' or '_', starting with a letter or digit"
        )
    return value


__all__ = [
    "MAX_NAME_LENGTH",
    "MIN_NAME_LENGTH",
    "NAME_PATTERN",
    "OFFICIAL_NAME_PATTERN",
    "is_valid_name",
    "validate_name",
]
