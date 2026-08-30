"""Nonce wire format.

This module validates the *format* of a nonce and nothing else. Monotonicity,
per-``(did, room)`` counters, reservation inside a transaction and replay
refusal are Stage 4 concerns and are deliberately absent here: a conformance
package that silently allocated nonces would be keeping state, and this
package keeps none.

Two rules carry real weight:

* **ASCII digits only.** ``str.isdigit()`` also accepts Unicode digits such as
  U+0661 ARABIC-INDIC DIGIT ONE. A signer that accepted those would sign a
  nonce the server then refuses, telling the caller a signature was good when
  it was not.
* **Leading zeros are preserved.** ``"007"`` and ``"7"`` are different wire
  values because they are different bytes inside the canonical string, and
  the signature covers bytes. Parsing a nonce to ``int`` anywhere in the
  signing path would silently rewrite ``"007"`` to ``"7"`` and break it.
"""

from __future__ import annotations

import re

from technocore_conform.errors import InvalidNonceError

#: The official pattern: 1 to 19 ASCII digits.
NONCE_PATTERN = r"[0-9]{1,19}"

#: The reference's literal source spelling, kept for provenance and asserted
#: against the pinned ``sign.py`` at test time.
#:
#: The reference writes it unanchored and applies ``re.fullmatch``, which is
#: the same language as the anchored ``^[0-9]{1,19}$`` spelling the protocol
#: notes use, and avoids the trailing-newline trap ``$`` carries.
OFFICIAL_NONCE_PATTERN = r"[0-9]{1,19}"

_NONCE_RE = re.compile(NONCE_PATTERN)

MIN_NONCE_DIGITS = 1
MAX_NONCE_DIGITS = 19


def is_valid_nonce(value: object) -> bool:
    """Whether ``value`` is a well-formed nonce string."""
    return isinstance(value, str) and _NONCE_RE.fullmatch(value) is not None


def validate_nonce(value: object) -> str:
    """Return the nonce **unchanged**, or raise ``InvalidNonceError``.

    Returning the input verbatim is the point: no normalization, no int
    round-trip, no stripping of leading zeros.
    """
    if not isinstance(value, str):
        raise InvalidNonceError("nonce must be a string")
    if _NONCE_RE.fullmatch(value) is None:
        raise InvalidNonceError(
            f"nonce must be {MIN_NONCE_DIGITS}-{MAX_NONCE_DIGITS} ASCII digits"
        )
    return value


__all__ = [
    "MAX_NONCE_DIGITS",
    "MIN_NONCE_DIGITS",
    "NONCE_PATTERN",
    "OFFICIAL_NONCE_PATTERN",
    "is_valid_nonce",
    "validate_nonce",
]
