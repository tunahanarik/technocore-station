"""Strict JSON and canonical encodings for security-relevant envelopes.

``json.loads`` is too permissive for a file an attacker may hand us: it
silently keeps the *last* of duplicate keys, which lets one document mean two
different things to two readers. Everything here is fail-closed.

The base64url convention is fixed and documented once: **unpadded**, and
canonical. A padded or differently-re-encodable value is rejected rather than
normalised, so a single byte string has exactly one accepted spelling.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any


class StrictJsonError(ValueError):
    """The document is not acceptable under the strict rules."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("document contains a duplicate key")
        result[key] = value
    return result


def _reject_non_finite(constant: str) -> Any:
    """Refuse ``NaN``, ``Infinity`` and ``-Infinity``.

    ``json.loads`` accepts all three by default even though none is valid
    JSON. They survive a round-trip through most parsers and NaN compares
    unequal to itself, which is exactly the wrong property for a document
    whose fields are compared one by one against an expected contract.
    """
    raise StrictJsonError(f"document contains the non-finite value {constant}")


def loads_strict(payload: bytes | str, *, max_bytes: int | None = None) -> dict[str, Any]:
    """Parse a JSON object, refusing duplicates, oversize input and non-objects."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload

    if max_bytes is not None and len(raw) > max_bytes:
        raise StrictJsonError("document is larger than the permitted maximum")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJsonError("document is not valid UTF-8") from exc

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except json.JSONDecodeError as exc:
        raise StrictJsonError("document is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise StrictJsonError("document must be a JSON object")
    return parsed


def require_exact_keys(document: dict[str, Any], expected: frozenset[str]) -> None:
    """Refuse a document with missing or unexpected top-level keys."""
    present = frozenset(document)
    missing = expected - present
    if missing:
        raise StrictJsonError(f"document is missing required fields: {sorted(missing)}")
    unexpected = present - expected
    if unexpected:
        raise StrictJsonError(f"document has unexpected fields: {sorted(unexpected)}")


def require_str(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        raise StrictJsonError(f"field {key} must be a string")
    return value


def require_int(document: dict[str, Any], key: str) -> int:
    value = document.get(key)
    # bool is a subclass of int; a boolean here is a type error, not a number.
    if not isinstance(value, int) or isinstance(value, bool):
        raise StrictJsonError(f"field {key} must be an integer")
    return value


def canonical_json_bytes(document: dict[str, Any]) -> bytes:
    """The AAD v1 canonicalization.

    Keys sorted by Unicode code point, separators exactly ``,`` and ``:`` with
    no whitespace, non-ASCII left as-is (the ``ensure_ascii=false``
    equivalent), encoded UTF-8. Specified in the project brief and pinned by a
    byte-exact test vector.
    """
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def b64u_encode(data: bytes) -> str:
    """Unpadded base64url."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64u_decode(text: str) -> bytes:
    """Decode unpadded base64url, rejecting padded and non-canonical spellings."""
    if not isinstance(text, str):
        raise StrictJsonError("expected a base64url string")
    if "=" in text:
        raise StrictJsonError("base64url values must be unpadded")

    padding = "=" * (-len(text) % 4)
    try:
        decoded = base64.urlsafe_b64decode(text + padding)
    except (binascii.Error, ValueError) as exc:
        raise StrictJsonError("value is not valid base64url") from exc

    # Canonicality: trailing bits must be zero, i.e. re-encoding round-trips.
    if b64u_encode(decoded) != text:
        raise StrictJsonError("base64url value is not canonical")
    return decoded


__all__ = [
    "StrictJsonError",
    "b64u_decode",
    "b64u_encode",
    "canonical_json_bytes",
    "loads_strict",
    "require_exact_keys",
    "require_int",
    "require_str",
]
