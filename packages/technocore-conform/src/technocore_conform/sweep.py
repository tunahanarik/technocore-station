"""The single-line sweep.

Every write to Technocore passes through this before storage, and the server
verifies signatures over what it stored - not over what the caller typed. So
the sweep is not cosmetic: getting it wrong by one character produces a
signature the server refuses, or worse, one it accepts over different bytes.

The contract, specified in ``docs/protocol-contract.md`` §2.1 and implemented
here independently of the Apache-2.0 reference:

1. Every character whose Unicode category is ``Cc``, ``Cf``, ``Cs``, ``Co``,
   ``Zl`` or ``Zp`` is replaced by **one** ASCII space (U+0020).
2. The result is trimmed with ``str.strip()``.
3. Nothing else happens.

Three things this deliberately does **not** do, each of which would be a
plausible-looking bug:

* **No collapsing.** Three consecutive control characters become three
  spaces, not one. A collapsing sweep would produce a shorter string than the
  server stores and every signature would fail.
* **No Unicode normalization.** NFC/NFD would rewrite the caller's text into
  different code points. The server does not normalize, so neither do we.
* **No case folding.**

A subtlety worth naming: step 2 uses ``str.strip()``, which trims every
character where ``str.isspace()`` is true. That includes ``Zs`` characters
such as U+00A0 (no-break space), which step 1 does *not* replace. So a
no-break space is preserved in the middle of the text and removed at the
ends. That asymmetry is the reference's behaviour and it is deliberate here.

Length is measured in Python code points **after** the sweep, because that is
what the server measures. Counting before, or counting UTF-8 bytes, would
disagree at exactly the boundary cases that matter.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from technocore_conform.errors import (
    EmptyTextError,
    InvalidTextError,
    TextTooLongError,
)

#: Unicode general categories replaced by a space, in the reference's order.
#:
#: Cc control      - would break the one-record-per-line storage invariant.
#: Cf format       - the invisible-instruction smuggling vector: Unicode tag
#:                   characters, bidi overrides (Trojan Source) and
#:                   zero-width joiners all render as nothing.
#: Cs surrogate    - never valid on its own in stored text.
#: Co private use  - renders as whatever the reader's font decides.
#: Zl / Zp         - U+2028 / U+2029 read as line breaks to enough consumers
#:                   that one stored value would render as two lines.
INVISIBLE_CATEGORIES: tuple[str, ...] = ("Cc", "Cf", "Cs", "Co", "Zl", "Zp")

#: Membership set. Same contents as the tuple above; a set only to make the
#: per-character lookup O(1) on long text.
_INVISIBLE: frozenset[str] = frozenset(INVISIBLE_CATEGORIES)

#: The character every swept-away character becomes.
REPLACEMENT = " "

#: Maximum code points in a swept message, from the pinned reference.
MAX_MESSAGE_CHARS = 4096

#: Maximum code points in a swept note value, from the pinned reference.
MAX_NOTE_VALUE_CHARS = 8192


@dataclass(frozen=True, slots=True)
class SweepPolicy:
    """Which limit applies, named so it cannot be passed by accident.

    Messages and note values have different caps (4096 vs 8192). Taking a
    bare ``int`` here would make swapping them a silent, signature-breaking
    mistake that type-checks; a named policy makes it visible at the call
    site and in the traceback.
    """

    name: str
    limit: int


MESSAGE_POLICY = SweepPolicy(name="message", limit=MAX_MESSAGE_CHARS)
NOTE_VALUE_POLICY = SweepPolicy(name="note_value", limit=MAX_NOTE_VALUE_CHARS)


def sweep(text: str, policy: SweepPolicy) -> str:
    """Return the text exactly as the server would store it.

    Raises rather than repairing: ``InvalidTextError`` if this is not a
    string, ``EmptyTextError`` if nothing visible survives, and
    ``TextTooLongError`` if the swept result is over the policy limit.
    """
    if not isinstance(text, str):
        raise InvalidTextError("text must be a string")

    swept = "".join(
        REPLACEMENT if unicodedata.category(character) in _INVISIBLE else character
        for character in text
    ).strip()

    if not swept:
        raise EmptyTextError(
            "nothing visible remains after the single-line sweep, which replaces every "
            "control, format, surrogate, private-use and line-separator character with a "
            "space and then trims the ends"
        )

    # Code points after the sweep: the same unit the server counts.
    if len(swept) > policy.limit:
        raise TextTooLongError(
            f"{len(swept)} characters after the sweep, over the {policy.limit}-character "
            f"limit for {policy.name}"
        )

    return swept


def sweep_message(text: str) -> str:
    """Sweep a room message under the 4096-code-point limit."""
    return sweep(text, MESSAGE_POLICY)


def sweep_note_value(value: str) -> str:
    """Sweep a note value under the 8192-code-point limit."""
    return sweep(value, NOTE_VALUE_POLICY)


def is_swept(text: str, policy: SweepPolicy) -> bool:
    """Whether ``text`` is already exactly what the sweep would produce.

    Used when rebuilding a canonical string from text the server has already
    stored: if this is false, the value was never swept (or was altered), and
    signing it would produce a record that cannot be re-verified.
    """
    try:
        return sweep(text, policy) == text
    except (EmptyTextError, InvalidTextError, TextTooLongError):
        return False


def contains_invisible(text: str) -> bool:
    """Whether any character would be replaced by the sweep.

    A reporting helper for the UI diff. It answers "would this change?", not
    "is this allowed?" - trimming alone also changes text without any
    invisible character being present.
    """
    return any(unicodedata.category(character) in _INVISIBLE for character in text)


__all__ = [
    "INVISIBLE_CATEGORIES",
    "MAX_MESSAGE_CHARS",
    "MAX_NOTE_VALUE_CHARS",
    "MESSAGE_POLICY",
    "NOTE_VALUE_POLICY",
    "REPLACEMENT",
    "SweepPolicy",
    "contains_invisible",
    "is_swept",
    "sweep",
    "sweep_message",
    "sweep_note_value",
]
