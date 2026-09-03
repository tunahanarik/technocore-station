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


def fold(text: str) -> str:
    """Case-fold and strip diacritics, so one entry covers every spelling.

    ``"sunucu kaniti"`` and its dotted-and-dotless Turkish spelling are the
    same claim, and a checker that caught only one of them would be a checker
    anybody could pass by accident.
    """
    lowered = text.casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.replace(_DOTLESS_I, "i"))


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
    """Text carrying a forbidden claim was about to leave this process."""


def assert_no_forbidden_claim(text: str, *, where: str) -> None:
    """Fail closed rather than publish an over-claim.

    Used on the surfaces a person keeps: the export file and the audit
    detail. A refusal here is a bug in this product's own wording, never
    something a remote document can trigger - remote text is swept and
    excerpted, and none of these phrases is Technocore's.
    """
    found = find_forbidden_phrases(text)
    if found:
        raise ForbiddenClaimError(
            f"{where}: kanit dili yasak bir ifade tasiyor: {', '.join(found)}"
        )


__all__ = [
    "AUDIT_CHAIN_CLAIM",
    "FORBIDDEN_PHRASES",
    "PERMITTED_ALTERNATIVES",
    "ForbiddenClaimError",
    "assert_no_forbidden_claim",
    "find_forbidden_phrases",
    "fold",
]
