"""The phrases this product may not use, and the ones it uses instead.

The charter names four (15.1) and ``docs/evidence-model.md`` 2 repeats them.
Until Package E they were enforced on the frontend only, which covered the
surface a user reads and none of the surfaces a user *exports*, greps or
pastes into a bug report. An export file, an API body and a log line say the
same things to the same person; a rule applied to one of the three is a
convention, not a rule.

Package E adds truncation to the list. The audit chain's head lives in a
separate DPAPI envelope, which detects a truncated tail against an attacker
who is not running as this Windows user - and detects nothing against one who
is, because that attacker can recompute both the chain and its head. Calling
that "tamper-proof" would be the same over-claim in a new place, so the words
that would make it are refused here rather than left to good intentions
(ADR-0003 5).

Why the registry is written in ASCII-folded Turkish
---------------------------------------------------
The charter spells these phrases with Turkish letters and this codebase
writes runtime strings ASCII-folded (AGENTS.md 3), so the same claim has two
spellings and a registry in either one would miss the other. Both sides of
every comparison go through :func:`fold` - case-folded, diacritics stripped,
dotless i mapped onto ``i`` - which maps the two spellings onto one. The
entries below are therefore written in the folded form: it is what they are
compared as, and storing the pretty spelling would only hide that.

A claim is refused; data carrying the same words is neutralised
---------------------------------------------------------------
The first version of this module applied :func:`assert_no_forbidden_claim` to
whole export payloads, on the reasoning that "none of these phrases is
Technocore's". That reasoning was wrong, and wrong in the worst direction: a
remote error body is excerpted into ``capture_detail``, a user's own message
text is archived verbatim, and either one can contain the words. The result
was a record that refused **both** export formats for good, on every retry,
with no route that could remove it - a remote server, or the user's own
sentence, deciding that the archive may never leave the machine again.

The distinction the module now draws is the one that was always meant:

* a **claim** is a sentence this product writes. Those are fixed strings, and
  a forbidden phrase in one of them is a bug in our wording, so it fails
  closed (:func:`assert_no_forbidden_claim`).
* **data** is text that merely passed through us - a remote excerpt, a message
  body. It is escaped and swept where it is rendered, and where it is folded
  into one of *our* sentences it is neutralised first
  (:func:`neutralise_forbidden_claims`), so a remote server cannot put words
  in this product's mouth. It is never a reason to refuse a file.
"""

from __future__ import annotations

import re
import unicodedata

#: The four forbidden claims plus the two Package E adds, in folded form.
#: ``"degismez kayit"`` matches the charter's own spelling as well, because
#: the text being searched is folded the same way.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "sunucu kaniti",
    "degismez kayit",
    "guvenilir zaman kaniti",
    "airdrop uygunluk kaniti",
    # Package E. The same over-claim, about the audit chain's head.
    "degistirilemez kayit",
    "kurcalanamaz kayit",
)

#: What to say instead, in the same order.
PERMITTED_ALTERNATIVES: tuple[str, ...] = (
    "sunucu gozlemi / yakalanan kayit",
    "yerel arsiv kaydi",
    "yerel kayit zamani",
    "(karsiligi yoktur - uretilmez)",
    "cevrimdisi degisiklige karsi tespit edici",
    "cevrimdisi degisiklige karsi tespit edici",
)

#: The only sentence permitted about what the audit chain provides.
AUDIT_CHAIN_CLAIM = "cevrimdisi degisiklige karsi tespit edici"

#: U+0131 LATIN SMALL LETTER DOTLESS I. It has no Unicode decomposition, so
#: stripping combining marks leaves it as its own letter and it has to be
#: mapped explicitly; the dotted capital does decompose and is handled by the
#: mark stripping above it. Written as an escape rather than as the character
#: because the linter's confusables rule is right to be suspicious of a bare
#: dotless i in source, and this is the one place that is deliberate.
_DOTLESS_I = "\u0131"

#: Latin letters a Cyrillic or Greek letter is visually identical to, mapped
#: onto the Latin one before anything is compared.
#:
#: NFKD does not touch these: ``U+0430 CYRILLIC SMALL LETTER A`` has no
#: decomposition to ``a``, because as far as Unicode is concerned it is a
#: different letter that happens to be drawn the same way. That is exactly
#: what makes it useful to somebody who wants a marker list to miss a word,
#: and it costs one keystroke: ``cl\u0430im`` with one Cyrillic ``\u0430`` reads as
#: ``claim`` to every human and matches nothing at all.
#:
#: Only the unambiguous lookalikes are listed. A map that guessed would fold
#: real Russian or Greek text into nonsense, and the point here is to close a
#: spoofing route, not to transliterate.
_CONFUSABLES: dict[str, str] = {
    # Cyrillic
    "\u0430": "a",
    "\u0432": "b",
    "\u0435": "e",
    "\u043a": "k",
    "\u043c": "m",
    "\u043d": "h",
    "\u043e": "o",
    "\u0440": "p",
    "\u0441": "c",
    "\u0442": "t",
    "\u0443": "y",
    "\u0445": "x",
    "\u0455": "s",
    "\u0456": "i",
    "\u0458": "j",
    # Greek
    "\u03b1": "a",
    "\u03b5": "e",
    "\u03b9": "i",
    "\u03ba": "k",
    "\u03bd": "v",
    "\u03bf": "o",
    "\u03c1": "p",
    "\u03c4": "t",
    "\u03c5": "u",
    "\u03c7": "x",
}

_CONFUSABLE_TABLE = str.maketrans(_CONFUSABLES)

def _drop_format_characters(text: str) -> str:
    """Delete every zero-width and formatting character.

    The zero-width space, joiner and non-joiner, the soft hyphen, the
    byte-order mark and the bidi controls all occupy no width and carry no
    meaning inside a word. They share Unicode category ``Cf``, so the
    *category* is deleted rather than a list of code points maintained by
    hand - a hand-maintained list is a list somebody adds a character to.

    Deleted rather than replaced with a space, deliberately: ``w<ZWSP>allet``
    is one word to a reader and has to be one word to a matcher.
    """
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def fold(text: str) -> str:
    """Case-fold and strip diacritics, so one entry covers every spelling.

    ``"sunucu kaniti"`` and its dotted-and-dotless Turkish spelling are the
    same claim, and a checker that caught only one of them would be a checker
    anybody could pass by accident.

    Two further normalisations exist for the same reason and were added when a
    review found the work-scan prohibition list could be walked past with
    them: invisible **format characters** are deleted, and a handful of
    Cyrillic and Greek **lookalike letters** are mapped onto the Latin ones
    they are drawn as. Both are strictly widening - a string that matched
    before still matches - and both close a route that costs an attacker one
    keystroke and a reader nothing at all.
    """
    lowered = _drop_format_characters(text).casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    mapped = stripped.replace(_DOTLESS_I, "i").translate(_CONFUSABLE_TABLE)
    return re.sub(r"\s+", " ", mapped)


#: Characters that separate letters without separating words when somebody is
#: trying to get past a marker list: spaces, every kind of dash, the dot, the
#: underscore, the middle dot and the apostrophes.
_SEPARATORS = re.compile(r"[\s\-\u2010-\u2015_.\u00b7'\u2018\u2019\u02bc]+")


def tighten(text: str) -> str:
    """:func:`fold`, and then every intra-word separator removed.

    ``w a l l e t``, ``wal-let`` and ``w.a.l.l.e.t`` are one word to a reader
    and three different strings to a substring search. This collapses all of
    them onto ``wallet`` so that a *prohibition* list is matched on what a
    person sees rather than on what they typed.

    It is deliberately **not** what :func:`fold` does, and the split is the
    whole design. Removing separators loses word boundaries, so a tightened
    haystack matches across them: it is the right trade where the cost of a
    false positive is one refused line with a stated reason, and the wrong
    trade everywhere a match *removes* text from a user's own words
    (:func:`neutralise_forbidden_claims`) or refuses one of our own sentences.
    Callers therefore opt in, and today the only caller is the work scan's
    prohibited-shape gate.
    """
    return _SEPARATORS.sub("", fold(text))


#: Precomputed once. Each entry is the folded form of a forbidden phrase.
_FOLDED = tuple(fold(phrase) for phrase in FORBIDDEN_PHRASES)


def find_forbidden_phrases(text: str) -> tuple[str, ...]:
    """Every forbidden claim present in ``text``, in registry order."""
    haystack = fold(text)
    return tuple(
        phrase
        for phrase, needle in zip(FORBIDDEN_PHRASES, _FOLDED, strict=True)
        if needle in haystack
    )


class ForbiddenClaimError(ValueError):
    """One of *this product's own* sentences carries a forbidden claim.

    Never raised because of imported text. A remote excerpt or a message body
    is data: it is neutralised by :func:`neutralise_forbidden_claims` before
    it can join one of our sentences, and it never refuses a write or an
    export. See the module docstring for why that split exists.
    """


def assert_no_forbidden_claim(text: str, *, where: str) -> None:
    """Fail closed rather than publish an over-claim of our own.

    Called on strings this product authors - the audit-chain sentence, the
    capture sentences, the level names, an audit detail assembled from fixed
    words and a room name. A refusal here is a bug in our wording and there
    is nothing a user or a server can do to cause one.
    """
    found = find_forbidden_phrases(text)
    if found:
        raise ForbiddenClaimError(
            f"{where}: kanit dili yasak bir ifade tasiyor: {', '.join(found)}"
        )


#: What replaces a forbidden phrase found inside imported text. It says that
#: something was removed rather than removing it silently, and it carries no
#: forbidden phrase of its own.
NEUTRALISED_MARK = "[yasakli ifade cikarildi]"

#: Used when the precise replacement below cannot be trusted to have removed
#: every occurrence. Dropping the whole excerpt is the fail-closed answer: the
#: excerpt is an explanatory courtesy, and losing it costs a sentence.
NEUTRALISED_ALL = "(uzak metin yasakli ifade tasiyordu; tamami cikarildi)"


def _fold_spans(text: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    """Fold ``text`` while remembering where each folded character came from.

    :func:`fold` normalises in ways that change length - NFKD expands, case
    folding can expand, combining marks disappear, whitespace runs collapse -
    so an offset in the folded string says nothing about the original. This
    walks the source one character at a time and records the source span each
    folded character was produced from, which is what makes it possible to
    remove a matched phrase from the **original** text rather than from a
    normalised copy nobody would want to read.
    """
    folded: list[str] = []
    spans: list[tuple[int, int]] = []
    for index, character in enumerate(text):
        for produced in fold(character):
            if produced == " " and folded and folded[-1] == " ":
                # A collapsed whitespace run: extend the span of the space
                # already emitted rather than emitting a second one.
                start, _ = spans[-1]
                spans[-1] = (start, index + 1)
                continue
            folded.append(produced)
            spans.append((index, index + 1))
    return "".join(folded), tuple(spans)


def _mask_forbidden_spans(text: str) -> str:
    """Replace every folded match with :data:`NEUTRALISED_MARK`."""
    folded, spans = _fold_spans(text)
    hits: list[tuple[int, int]] = []
    for needle in _FOLDED:
        start = 0
        while (index := folded.find(needle, start)) >= 0:
            hits.append((spans[index][0], spans[index + len(needle) - 1][1]))
            start = index + len(needle)

    result = text
    for begin, end in sorted(hits, reverse=True):
        result = result[:begin] + NEUTRALISED_MARK + result[end:]
    return result


def neutralise_forbidden_claims(text: str) -> str:
    """Make imported text safe to fold into one of this product's sentences.

    Returns ``text`` unchanged when it carries no forbidden phrase, which is
    the overwhelmingly common case and costs one folded scan.

    When it does carry one, the phrase is replaced in place. The replacement
    is then **re-checked with the authoritative scanner**: the span-tracking
    fold above and :func:`fold` are two implementations of one normalisation,
    and if they ever disagreed the precise pass could leave a phrase standing.
    In that case the whole excerpt is dropped. Neutralising imported text can
    lose an explanatory sentence; it can never refuse a write or an export.
    """
    if not find_forbidden_phrases(text):
        return text
    masked = _mask_forbidden_spans(text)
    if find_forbidden_phrases(masked):  # pragma: no cover - defensive
        return NEUTRALISED_ALL
    return masked


__all__ = [
    "AUDIT_CHAIN_CLAIM",
    "FORBIDDEN_PHRASES",
    "NEUTRALISED_ALL",
    "NEUTRALISED_MARK",
    "PERMITTED_ALTERNATIVES",
    "ForbiddenClaimError",
    "assert_no_forbidden_claim",
    "find_forbidden_phrases",
    "fold",
    "neutralise_forbidden_claims",
    "tighten",
]
