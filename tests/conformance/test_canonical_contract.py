"""Names, nonces and the canonical string.

The canonical string is built by concatenation with no escaping, so its
safety rests entirely on the structural fields being unable to contain the
separator. These tests pin that, and pin the patterns against the ones read
out of the pinned reference at run time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from technocore_conform import (
    MAX_NAME_LENGTH,
    MESSAGE_SEPARATORS,
    NAME_PATTERN,
    NOTE_SEPARATORS,
    SEPARATOR,
    InvalidNameError,
    InvalidNonceError,
    PayloadKind,
    canonical_message,
    canonical_message_from_swept,
    canonical_note,
    canonical_note_from_swept,
    is_valid_name,
    is_valid_nonce,
    validate_nonce,
)
from technocore_conform.names import OFFICIAL_NAME_PATTERN
from technocore_conform.nonce import OFFICIAL_NONCE_PATTERN

from tests.conformance.oracle import official_name_pattern, official_nonce_pattern

pytestmark = pytest.mark.conformance


# --- the patterns come from the reference ----------------------------------


def test_name_pattern_matches_the_pinned_reference(vendor_root: Path) -> None:
    assert official_name_pattern(vendor_root) == OFFICIAL_NAME_PATTERN


def test_nonce_pattern_matches_the_pinned_reference(vendor_root: Path) -> None:
    assert official_nonce_pattern(vendor_root) == OFFICIAL_NONCE_PATTERN


def test_our_unanchored_pattern_is_the_same_language() -> None:
    """``fullmatch`` on the unanchored pattern equals the anchored spelling.

    Worth pinning because the two spellings are *not* equivalent under
    ``re.match``: with a trailing ``$``, "room\\n" matches. Using fullmatch on
    an unanchored pattern removes that trap; this test proves the verdicts
    still agree everywhere.
    """
    anchored = re.compile(OFFICIAL_NAME_PATTERN)
    ours = re.compile(NAME_PATTERN)

    candidates = [
        "a",
        "room",
        "test-room",
        "a_b-c",
        "0",
        "a" * MAX_NAME_LENGTH,
        "a" * (MAX_NAME_LENGTH + 1),
        "",
        "-leading",
        "_leading",
        "Upper",
        "with space",
        "with.dot",
        "with/slash",
        "with|pipe",
        "türkçe",
        "room\n",
        "\nroom",
    ]
    for candidate in candidates:
        assert (anchored.fullmatch(candidate) is not None) == (
            ours.fullmatch(candidate) is not None
        ), candidate


# --- names -----------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["a", "0", "room", "test-room", "a_b", "a-b_c-0", "a" * MAX_NAME_LENGTH]
)
def test_valid_names_are_accepted(name: str) -> None:
    assert is_valid_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "a" * (MAX_NAME_LENGTH + 1),
        "-leading",
        "_leading",
        "Room",
        "ROOM",
        "with space",
        "with.dot",
        "with/slash",
        "with\\backslash",
        "with|pipe",
        "with\nnewline",
        "room\n",
        "..",
        "../etc",
        "a/../b",
        "türkçe",
        "\u043eda",
        "room​",
        "١٢٣",
    ],
)
def test_invalid_names_are_refused(name: str) -> None:
    assert not is_valid_name(name)
    with pytest.raises(InvalidNameError):
        canonical_message(room=name, nonce="1", text="hello")


def test_non_string_names_are_refused() -> None:
    assert not is_valid_name(None)
    assert not is_valid_name(7)


def test_name_error_names_the_field_that_failed() -> None:
    with pytest.raises(InvalidNameError, match="namespace"):
        canonical_note(namespace="BAD", key="k", nonce="1", value="v")
    with pytest.raises(InvalidNameError, match="key"):
        canonical_note(namespace="ns", key="BAD", nonce="1", value="v")


# --- nonces ----------------------------------------------------------------


@pytest.mark.parametrize("nonce", ["0", "1", "007", "9" * 19, "0" * 19])
def test_valid_nonces_are_accepted(nonce: str) -> None:
    assert is_valid_nonce(nonce)
    assert validate_nonce(nonce) == nonce


@pytest.mark.parametrize(
    "nonce",
    ["", "9" * 20, "-1", "1.0", "1e3", " 1", "1 ", "0x1", "١٢٣", "\uff11\uff12\uff13", "๑", "1\n"],
)
def test_invalid_nonces_are_refused(nonce: str) -> None:
    assert not is_valid_nonce(nonce)
    with pytest.raises(InvalidNonceError):
        validate_nonce(nonce)


def test_unicode_digits_are_refused_even_though_isdigit_accepts_them() -> None:
    """``str.isdigit()`` is true for these, and that is the trap."""
    for nonce in ("١٢٣", "\uff11\uff12\uff13"):
        assert nonce.isdigit()
        assert not is_valid_nonce(nonce)


def test_leading_zeros_survive_into_the_canonical_string() -> None:
    """``007`` and ``7`` are different wire values, so they must stay different."""
    padded = canonical_message(room="r", nonce="007", text="x")
    plain = canonical_message(room="r", nonce="7", text="x")

    assert padded.nonce == "007"
    assert padded.canonical == "r|007|x"
    assert padded.canonical != plain.canonical


# --- canonical strings -----------------------------------------------------


def test_message_canonical_shape() -> None:
    payload = canonical_message(room="lobby", nonce="42", text="  hello  ")
    assert payload.kind is PayloadKind.MESSAGE
    assert payload.canonical == "lobby|42|hello"
    assert payload.canonical_bytes == b"lobby|42|hello"
    assert payload.structural_separators == MESSAGE_SEPARATORS
    assert payload.changed_by_sweep is True


def test_note_canonical_shape() -> None:
    payload = canonical_note(namespace="profile", key="bio", nonce="1", value="merhaba")
    assert payload.kind is PayloadKind.NOTE
    assert payload.canonical == "profile|bio|1|merhaba"
    assert payload.structural_separators == NOTE_SEPARATORS
    assert payload.changed_by_sweep is False


def test_text_may_contain_pipes_without_ambiguity() -> None:
    """Only the last field is free-form, so extra pipes are content.

    Reading the structural fields from the left recovers them exactly,
    because no structural field can contain a separator.
    """
    payload = canonical_message(room="r", nonce="1", text="a|b|c")
    assert payload.canonical == "r|1|a|b|c"

    room, nonce, text = payload.canonical.split(SEPARATOR, MESSAGE_SEPARATORS)
    assert (room, nonce, text) == ("r", "1", "a|b|c")


def test_note_value_may_contain_pipes_without_ambiguity() -> None:
    payload = canonical_note(namespace="ns", key="k", nonce="1", value="a|b|c")
    namespace, key, nonce, value = payload.canonical.split(SEPARATOR, NOTE_SEPARATORS)
    assert (namespace, key, nonce, value) == ("ns", "k", "1", "a|b|c")


def test_canonical_carries_the_swept_text_not_the_raw_text() -> None:
    """The signature must cover what the server stores, never what was typed."""
    payload = canonical_message(room="r", nonce="1", text="gizli​metin\n")
    assert payload.raw_text == "gizli​metin\n"
    assert payload.swept_text == "gizli metin"
    assert payload.canonical.endswith("gizli metin")
    assert "​" not in payload.canonical


def test_changed_by_sweep_reports_trimming_too() -> None:
    """Trimming alone changes the stored text, so the user should see it."""
    assert canonical_message(room="r", nonce="1", text=" x ").changed_by_sweep is True
    assert canonical_message(room="r", nonce="1", text="x").changed_by_sweep is False


def test_canonical_has_no_trailing_byte() -> None:
    payload = canonical_message(room="r", nonce="1", text="x")
    assert not payload.canonical.endswith(("\n", " ", "\x00"))
    assert payload.canonical_bytes == payload.canonical.encode("utf-8")


# --- rebuilding from stored text -------------------------------------------


def test_rebuilding_from_stored_text_is_byte_identical() -> None:
    """A stored record must reconstruct exactly the bytes that were signed."""
    original = canonical_message(room="r", nonce="1", text="  merhaba\ndünya  ")
    rebuilt = canonical_message_from_swept(
        room="r", nonce="1", swept_text=original.swept_text
    )
    assert rebuilt.canonical_bytes == original.canonical_bytes


def test_rebuilding_a_note_from_stored_value_is_byte_identical() -> None:
    original = canonical_note(namespace="ns", key="k", nonce="9", value=" a\tb ")
    rebuilt = canonical_note_from_swept(
        namespace="ns", key="k", nonce="9", swept_value=original.swept_text
    )
    assert rebuilt.canonical_bytes == original.canonical_bytes


def test_rebuilding_refuses_text_that_was_never_swept() -> None:
    """Silently sweeping here would hide that the record is not stored form."""
    with pytest.raises(ValueError, match="swept form"):
        canonical_message_from_swept(room="r", nonce="1", swept_text="  padded  ")
    with pytest.raises(ValueError, match="swept form"):
        canonical_note_from_swept(
            namespace="ns", key="k", nonce="1", swept_value="has\nnewline"
        )


# --- the payload must not leak content -------------------------------------


def test_payload_repr_reports_lengths_not_content() -> None:
    """A payload in a traceback must not become a copy of the user's text."""
    text = "cok-gizli-kullanici-metni-12345"
    payload = canonical_message(room="r", nonce="1", text=text)
    rendered = repr(payload)

    assert text not in rendered
    assert "raw_chars=" in rendered
    # Structural fields are protocol-level and safe to show.
    assert "fields=[r, 1]" in rendered
