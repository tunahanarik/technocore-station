"""Canonical strings - the exact bytes a signature covers.

    message:  <room>|<nonce>|<swept_text>
    note:     <namespace>|<key>|<nonce>|<swept_value>

Encoded as UTF-8. No normalization, no trailing newline, no padding byte.

Why this is a type and not a formatted string
---------------------------------------------
Signing takes a ``CanonicalPayload``, never a free-form string. That single
choice removes a whole class of bug: it is not possible to sign raw text by
accident, because raw text cannot be a payload - only ``sweep`` produces the
``swept_text`` a payload is built from. The reference is explicit that signing
the raw text earns a 403, and the failure would otherwise surface only against
the live server.

The separator and free-form text
--------------------------------
A message canonical string contains **exactly two** structural separators and
a note **exactly three**. The swept text after the last one may itself contain
any number of ``|`` characters, and that is safe: room, namespace and key are
restricted to ``[a-z0-9_-]`` (see ``names``), and the nonce to ASCII digits,
so no structural field can ever contain a separator. Fields are therefore read
from the left and only the final field is free-form. Nothing is escaped.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from technocore_conform.names import validate_name
from technocore_conform.nonce import validate_nonce
from technocore_conform.sweep import (
    MESSAGE_POLICY,
    NOTE_VALUE_POLICY,
    SweepPolicy,
    is_swept,
    sweep,
)

#: The one field separator. U+007C.
SEPARATOR = "|"

#: Structural separator counts, excluding any ``|`` inside the swept text.
MESSAGE_SEPARATORS = 2
NOTE_SEPARATORS = 3


class PayloadKind(StrEnum):
    MESSAGE = "message"
    NOTE = "note"


class _NotSweptError(ValueError):
    """Internal: raised when text handed to a ``_from_swept`` builder is not swept."""


@dataclass(frozen=True, slots=True)
class CanonicalPayload:
    """A validated payload, ready to sign or verify.

    Immutable, and carries **no key material** - a payload is public data
    describing what will be written. It holds the raw text alongside the swept
    text so a UI can show the user the difference before they approve it.
    """

    kind: PayloadKind
    nonce: str
    raw_text: str
    swept_text: str
    room: str | None = None
    namespace: str | None = None
    key: str | None = None

    @property
    def structural_fields(self) -> tuple[str, ...]:
        """The fields before the free-form text, in canonical order."""
        if self.kind is PayloadKind.MESSAGE:
            assert self.room is not None
            return (self.room, self.nonce)
        assert self.namespace is not None
        assert self.key is not None
        return (self.namespace, self.key, self.nonce)

    @property
    def canonical(self) -> str:
        """The exact string that is signed.

        Computed rather than stored: one source of truth means the canonical
        form cannot drift out of step with the fields it is built from.
        """
        return SEPARATOR.join((*self.structural_fields, self.swept_text))

    @property
    def canonical_bytes(self) -> bytes:
        """The canonical string as UTF-8 - the bytes handed to Ed25519."""
        return self.canonical.encode("utf-8")

    @property
    def structural_separators(self) -> int:
        """How many separators are structural, as opposed to text content."""
        return len(self.structural_fields)

    @property
    def changed_by_sweep(self) -> bool:
        """Whether the sweep altered what the user typed.

        True for trimming alone, not only for removed invisible characters:
        anything that makes the stored text differ from the raw text is
        something the user should see before approving.
        """
        return self.raw_text != self.swept_text

    def __repr__(self) -> str:
        """Lengths, not content.

        A payload can end up in a traceback or a debugger. The structural
        fields are protocol-level and safe to show; the user's text is not
        ours to spill into a log line.
        """
        fields = ", ".join(self.structural_fields)
        return (
            f"CanonicalPayload(kind={self.kind.value}, fields=[{fields}], "
            f"raw_chars={len(self.raw_text)}, swept_chars={len(self.swept_text)}, "
            f"changed_by_sweep={self.changed_by_sweep})"
        )


def canonical_message(*, room: str, nonce: str, text: str) -> CanonicalPayload:
    """Build a message payload from raw user text.

    The text is swept here, so the caller cannot skip it.
    """
    return CanonicalPayload(
        kind=PayloadKind.MESSAGE,
        room=validate_name(room, field="room"),
        nonce=validate_nonce(nonce),
        raw_text=text,
        swept_text=sweep(text, MESSAGE_POLICY),
    )


def canonical_note(*, namespace: str, key: str, nonce: str, value: str) -> CanonicalPayload:
    """Build a note payload from a raw user value."""
    return CanonicalPayload(
        kind=PayloadKind.NOTE,
        namespace=validate_name(namespace, field="namespace"),
        key=validate_name(key, field="key"),
        nonce=validate_nonce(nonce),
        raw_text=value,
        swept_text=sweep(value, NOTE_VALUE_POLICY),
    )


def _require_swept(text: str, policy: SweepPolicy) -> str:
    """Accept text only if it is already exactly what the sweep produces."""
    if not is_swept(text, policy):
        raise _NotSweptError(
            f"stored {policy.name} text is not in swept form, so a canonical string "
            "rebuilt from it would not match the signed bytes"
        )
    return text


def canonical_message_from_swept(
    *, room: str, nonce: str, swept_text: str
) -> CanonicalPayload:
    """Rebuild a message payload from text the server has already stored.

    This is the re-verification path: given a stored record, reconstruct the
    exact bytes that were signed. The text must already be swept - if it is
    not, it was never the stored form and rebuilding would be meaningless.
    """
    return CanonicalPayload(
        kind=PayloadKind.MESSAGE,
        room=validate_name(room, field="room"),
        nonce=validate_nonce(nonce),
        raw_text=swept_text,
        swept_text=_require_swept(swept_text, MESSAGE_POLICY),
    )


def canonical_note_from_swept(
    *, namespace: str, key: str, nonce: str, swept_value: str
) -> CanonicalPayload:
    """Rebuild a note payload from a value the server has already stored."""
    return CanonicalPayload(
        kind=PayloadKind.NOTE,
        namespace=validate_name(namespace, field="namespace"),
        key=validate_name(key, field="key"),
        nonce=validate_nonce(nonce),
        raw_text=swept_value,
        swept_text=_require_swept(swept_value, NOTE_VALUE_POLICY),
    )


__all__ = [
    "MESSAGE_SEPARATORS",
    "NOTE_SEPARATORS",
    "SEPARATOR",
    "CanonicalPayload",
    "PayloadKind",
    "canonical_message",
    "canonical_message_from_swept",
    "canonical_note",
    "canonical_note_from_swept",
]
