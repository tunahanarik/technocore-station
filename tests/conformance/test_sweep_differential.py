"""AC-02 and AC-03 - the sweep must equal the pinned reference, everywhere.

The oracle is the reference's own ``clean_text``, executed from its own AST
(see ``oracle.py``). Nothing here restates what the sweep *should* do; every
expectation is read from the reference at run time.

Two layers:

* An exhaustive differential over a deterministic Unicode corpus of more than
  ten thousand inputs, which is AC-02 stated literally.
* Hypothesis property tests for the invariants a fixed corpus cannot pin
  down: idempotence, no collapsing, no normalization, and agreement on
  refusals as well as on outputs.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from technocore_conform import (
    MAX_MESSAGE_CHARS,
    MAX_NOTE_VALUE_CHARS,
    MESSAGE_POLICY,
    NOTE_VALUE_POLICY,
    EmptyTextError,
    SweepError,
    TextTooLongError,
    sweep,
    sweep_message,
    sweep_note_value,
)

from tests.conformance.conftest import FORBIDDEN_CATEGORIES, category_counts

pytestmark = pytest.mark.conformance

#: AC-02's own number. Asserted, not assumed.
REQUIRED_DIFFERENTIAL_INPUTS = 10_000

OracleSweep = Callable[[str, int], str]


def _oracle_verdict(oracle: OracleSweep, text: str, limit: int) -> tuple[bool, str]:
    """``(accepted, output)`` from the reference, refusals included."""
    try:
        return True, oracle(text, limit)
    except Exception:
        return False, ""


def _our_verdict(text: str, limit: int) -> tuple[bool, str]:
    policy = MESSAGE_POLICY if limit == MAX_MESSAGE_CHARS else NOTE_VALUE_POLICY
    try:
        return True, sweep(text, policy)
    except SweepError:
        return False, ""


# --- AC-02: the exhaustive differential ------------------------------------


def test_corpus_is_large_enough_for_ac_02(unicode_corpus: list[str]) -> None:
    """The acceptance criterion is a number; this is that number."""
    assert len(unicode_corpus) >= REQUIRED_DIFFERENTIAL_INPUTS, (
        f"AC-02 requires at least {REQUIRED_DIFFERENTIAL_INPUTS} inputs, "
        f"the corpus has {len(unicode_corpus)}"
    )


def test_corpus_covers_every_forbidden_category(unicode_code_points: list[int]) -> None:
    """A corpus that missed a swept category would prove nothing about it."""
    counts = category_counts(unicode_code_points)
    for category in FORBIDDEN_CATEGORIES:
        assert counts.get(category, 0) > 0, f"corpus contains no {category} character"

    # And it must contain ordinary text too, or "everything becomes a space"
    # would pass.
    assert counts.get("Lu", 0) > 0
    assert counts.get("Ll", 0) > 0
    assert counts.get("Nd", 0) > 0


def test_corpus_includes_astral_and_unpaired_surrogates(
    unicode_code_points: list[int],
) -> None:
    assert any(point > 0xFFFF for point in unicode_code_points), "no astral code point"
    assert any(0xD800 <= point < 0xE000 for point in unicode_code_points), (
        "no unpaired surrogate"
    )


def test_sweep_matches_the_reference_across_the_unicode_range(
    unicode_corpus: list[str], official_sweep: OracleSweep
) -> None:
    """AC-02. Every input, compared character for character."""
    mismatches: list[str] = []
    for text in unicode_corpus:
        expected = _oracle_verdict(official_sweep, text, MAX_MESSAGE_CHARS)
        produced = _our_verdict(text, MAX_MESSAGE_CHARS)
        if produced != expected:
            point = ord(text[1])
            mismatches.append(
                f"U+{point:04X} ({unicodedata.category(chr(point))}): "
                f"reference={expected!r} ours={produced!r}"
            )
            if len(mismatches) >= 10:
                break

    assert not mismatches, "sweep diverged from the reference:\n" + "\n".join(mismatches)


def test_note_values_match_the_reference_too(
    unicode_corpus: list[str], official_sweep: OracleSweep
) -> None:
    """The same corpus under the 8192-character note limit."""
    for text in unicode_corpus:
        assert _our_verdict(text, MAX_NOTE_VALUE_CHARS) == _oracle_verdict(
            official_sweep, text, MAX_NOTE_VALUE_CHARS
        )


def test_swept_output_contains_no_forbidden_category(unicode_corpus: list[str]) -> None:
    """Whatever survives, none of it renders as nothing."""
    for text in unicode_corpus:
        accepted, produced = _our_verdict(text, MAX_MESSAGE_CHARS)
        if not accepted:
            continue
        for character in produced:
            assert unicodedata.category(character) not in FORBIDDEN_CATEGORIES


# --- AC-03: idempotence ----------------------------------------------------


def test_sweep_is_idempotent_across_the_corpus(unicode_corpus: list[str]) -> None:
    """AC-03, over the same corpus as AC-02."""
    for text in unicode_corpus:
        accepted, once = _our_verdict(text, MAX_MESSAGE_CHARS)
        if not accepted:
            continue
        assert sweep_message(once) == once


# --- the properties a fixed corpus cannot pin down -------------------------

_TEXT = st.text(
    alphabet=st.characters(min_codepoint=0, max_codepoint=0x10FFFF),
    min_size=0,
    max_size=120,
)

_SETTINGS = settings(
    max_examples=400,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@_SETTINGS
@given(text=_TEXT)
def test_property_agrees_with_the_reference(text: str, official_sweep: OracleSweep) -> None:
    assert _our_verdict(text, MAX_MESSAGE_CHARS) == _oracle_verdict(
        official_sweep, text, MAX_MESSAGE_CHARS
    )


@_SETTINGS
@given(text=_TEXT)
def test_property_is_idempotent(text: str) -> None:
    try:
        once = sweep_message(text)
    except SweepError:
        return
    assert sweep_message(once) == once


@_SETTINGS
@given(text=_TEXT)
def test_property_never_collapses_runs(text: str) -> None:
    """Replacement is one-for-one, so the length can only change by trimming.

    A collapsing implementation would shorten the middle of the string, and
    every signature over it would then fail against the server.
    """
    try:
        produced = sweep_message(text)
    except SweepError:
        return
    replaced = "".join(
        " " if unicodedata.category(character) in FORBIDDEN_CATEGORIES else character
        for character in text
    )
    assert produced == replaced.strip()
    assert len(produced) == len(replaced.strip())


@_SETTINGS
@given(text=_TEXT)
def test_property_does_not_normalize(text: str) -> None:
    """No NFC/NFD anywhere: surviving characters keep their exact code points."""
    try:
        produced = sweep_message(text)
    except SweepError:
        return
    for character in produced:
        if character == " ":
            continue
        assert character in text, "sweep introduced a character that was not in the input"


# --- boundaries ------------------------------------------------------------


def test_message_boundary_is_exact(official_sweep: OracleSweep) -> None:
    """4096 accepted, 4097 refused - and the reference agrees."""
    at_limit = "a" * MAX_MESSAGE_CHARS
    over_limit = "a" * (MAX_MESSAGE_CHARS + 1)

    assert sweep_message(at_limit) == official_sweep(at_limit, MAX_MESSAGE_CHARS)
    with pytest.raises(TextTooLongError):
        sweep_message(over_limit)
    assert not _oracle_verdict(official_sweep, over_limit, MAX_MESSAGE_CHARS)[0]


def test_note_boundary_is_exact(official_sweep: OracleSweep) -> None:
    """8192 accepted, 8193 refused."""
    at_limit = "b" * MAX_NOTE_VALUE_CHARS
    over_limit = "b" * (MAX_NOTE_VALUE_CHARS + 1)

    assert sweep_note_value(at_limit) == official_sweep(at_limit, MAX_NOTE_VALUE_CHARS)
    with pytest.raises(TextTooLongError):
        sweep_note_value(over_limit)


def test_the_limit_is_measured_after_the_sweep() -> None:
    """Padding that trims away must not count towards the cap.

    Measuring before the sweep would reject this, and measuring UTF-8 bytes
    would reject any long non-ASCII message. Both are real, plausible bugs.
    """
    padded = "  " + "c" * MAX_MESSAGE_CHARS + "\n\n"
    assert len(sweep_message(padded)) == MAX_MESSAGE_CHARS


def test_length_is_code_points_not_utf8_bytes() -> None:
    """A message of 4096 four-byte characters is 16 KiB and still legal."""
    astral = "\U0001f600" * MAX_MESSAGE_CHARS
    assert len(sweep_message(astral)) == MAX_MESSAGE_CHARS
    assert len(sweep_message(astral).encode("utf-8")) > MAX_MESSAGE_CHARS


def test_the_two_limits_do_not_leak_into_each_other() -> None:
    """A 4097-character value is a legal note and an illegal message."""
    long_value = "d" * (MAX_MESSAGE_CHARS + 1)
    assert len(sweep_note_value(long_value)) == MAX_MESSAGE_CHARS + 1
    with pytest.raises(TextTooLongError):
        sweep_message(long_value)


# --- refusals --------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["", "   ", "​", "​‌‍", "‮‬", "\n\t\r", "\u2028\u2029"],
)
def test_text_with_nothing_visible_is_refused(
    text: str, official_sweep: OracleSweep
) -> None:
    with pytest.raises(EmptyTextError):
        sweep_message(text)
    assert not _oracle_verdict(official_sweep, text, MAX_MESSAGE_CHARS)[0]


def test_error_types_are_distinguishable() -> None:
    """Empty, too long and wrong type are three different facts."""
    with pytest.raises(EmptyTextError):
        sweep_message("​")
    with pytest.raises(TextTooLongError):
        sweep_message("a" * (MAX_MESSAGE_CHARS + 1))
    with pytest.raises(SweepError):
        sweep_message(None)  # type: ignore[arg-type]


def test_error_messages_do_not_echo_user_content() -> None:
    """A traceback must not become a copy of the user's text."""
    secret_looking = "kullanici-metni-abcdef123456"
    with pytest.raises(TextTooLongError) as excinfo:
        sweep_message(secret_looking + "x" * MAX_MESSAGE_CHARS)
    assert secret_looking not in str(excinfo.value)


def test_no_break_space_is_kept_inside_and_trimmed_at_the_edges(
    official_sweep: OracleSweep,
) -> None:
    """A genuinely surprising behaviour, pinned so it cannot drift.

    U+00A0 is category Zs, so the replacement step ignores it - but
    ``str.strip()`` removes it, because it is whitespace. Interior no-break
    spaces therefore survive and edge ones do not.
    """
    text = "\u00a0a\u00a0b\u00a0"
    assert sweep_message(text) == "a\u00a0b"
    assert sweep_message(text) == official_sweep(text, MAX_MESSAGE_CHARS)
