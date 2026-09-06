"""The claims this package may not make, and the ones it makes instead.

Package E built a forbidden-phrase registry for the evidence layer and proved
it two ways: at runtime, on the sentences the product writes, and statically,
over **every string literal in the package**. The static half is why this
module exists at all: a rule that does not cover the text being written is
not a rule (ADR-0007 10).

So H1 gets the same two halves, over its own tree, with its own additions.

Package scope is no longer what decides coverage
-------------------------------------------------
This paragraph used to say that Package E's scan was scoped to
``station_api/evidence``, so a new package's wording was outside it - a true
sentence with nothing behind it, and the twelfth instance of this
repository's signature defect. It was measured: the same three phrases that
turn one package's scan red sat in ``opencode/service.py`` with the whole
security suite green.

What covers a package now is not that somebody wrote it a test file.
``tests/security/test_language_scope.py`` walks ``station_api`` and applies
the **union** registry to every string literal in it - eighteen packages,
fourteen loose modules, every route - and the four registries are the only
files outside. The per-package scan below still runs and still applies this
package's own registry; it is no longer the only thing between a new
package's wording and a user.

Reused rather than reimplemented
--------------------------------
:func:`station_api.evidence.language.fold` does the comparison - case-folded,
diacritics stripped, dotless ``i`` mapped onto ``i`` - and the six phrases
that layer already refuses are inherited whole. A second folding
implementation would be a second thing to get wrong in the same way IMP-384
records it being got wrong once already: ``casefold`` does not map the
Turkish dotless letter, so a guard written in ASCII was blind to the language
the product is written in.

What H1 adds, and why each one
-------------------------------
``"hala acik"``
    A scan reads a bounded slice of a ring buffer that drops history. There is
    no observation available on this surface that establishes a work item is
    still open - only that nothing in **what was read** looked like a closing
    signal. ADR-0007 8 forbids the certain wording outright and names the
    replacement, which is :data:`OPEN_STATE_SENTENCE`.

``"dogrulanmis itibar"``, ``"itibar puani"``, ``"uygunluk puani"``,
``"airdrop uygunlugu"``
    A third party's ``score`` or ``rank`` is that third party's arithmetic
    over a public tape. Folding it into one of this product's own sentences
    as reputation or eligibility is the claim the charter forbids (8.3,
    AC-18) - and the one service that publishes such a number says of itself
    that it settles nothing.

``"dogrulanmis talep sahibi"``
    A ``from`` value that is not a ``did:key`` is a nickname its writer typed.
    A sentence calling that person a verified claimant says more than the
    field supports.

``"resmi oda"``
    A room name and a topic are caller-written strings. Neither is an
    endorsement, and calling a room official because of what its topic says
    would be believing a world-writable note.

The split between a claim and data is the one Package E drew
-------------------------------------------------------------
A **claim** is a sentence this product writes; a forbidden phrase in one is a
bug in our wording and fails closed (:func:`assert_no_forbidden_claim`).
**Data** is text that passed through us - a message body, a topic, a room
name - and it is neutralised where it joins one of our sentences and never a
reason to refuse anything. A remote writer who types the banned words into a
public room must not be able to make this product refuse to show a scan.
"""

from __future__ import annotations

from station_api.evidence.language import (
    FORBIDDEN_PHRASES as EVIDENCE_FORBIDDEN_PHRASES,
)
from station_api.evidence.language import (
    ForbiddenClaimError,
    fold,
    neutralise_forbidden_claims,
)

#: The phrases H1 adds, in folded form - which is what they are compared as.
WORK_SCAN_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "hala acik",
    "dogrulanmis itibar",
    "itibar puani",
    "uygunluk puani",
    "airdrop uygunlugu",
    "dogrulanmis talep sahibi",
    "resmi oda",
)

#: Everything this package refuses: the evidence layer's six plus H1's seven.
#: Composed rather than copied, so a phrase added there is refused here on the
#: same commit.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    *EVIDENCE_FORBIDDEN_PHRASES,
    *WORK_SCAN_FORBIDDEN_PHRASES,
)

#: What to say instead of each H1 phrase, in the same order.
PERMITTED_ALTERNATIVES: tuple[str, ...] = (
    "su ana kadar okunanda kapanis isareti gorulmedi (anlik goruntu ...)",
    "ucuncu tarafin kendi hesapladigi sayi (bir itibar olcusu degildir)",
    "ucuncu tarafin kendi hesapladigi sayi (bir itibar olcusu degildir)",
    "ucuncu tarafin kendi hesapladigi sayi (bir uygunluk olcusu degildir)",
    "(karsiligi yoktur - uretilmez)",
    "kendi beyan ettigi takma ad",
    "adi ve basligi yabancilarin yazdigi bir oda",
)

#: The only wording permitted about whether a work item is still open.
#:
#: A template, not a sentence: it cannot be used without substituting the
#: moment the snapshot was read, which is the fact that makes the claim
#: honest. A caller that had only the sentence would be tempted to show it
#: alone (ADR-0007 8).
OPEN_STATE_SENTENCE = (
    "Su ana kadar okunanda kapanis isareti gorulmedi (anlik goruntu: {read_at}). "
    "Bu, isin acik oldugu anlamina gelmez; yalnizca okunan dilimde bir kapanis "
    "isareti bulunmadigi anlamina gelir."
)

#: The sentence the product must show beside every scan result. ADR-0007 2
#: required the cost of the derivation to be stated to the user rather than
#: left in a design document, and ADR-0014 changed what the cost **is**.
#:
#: It used to say *"anlamsal cikarim yoktur"* - no semantic inference - and
#: that sentence was true for exactly as long as candidates came out of a
#: phrase list. It stopped being true the moment a model started reading the
#: lines, and a promise that has quietly become false is worse than one that
#: was never made: a user who read it would think a wrong candidate was
#: impossible rather than merely uncommon.
#:
#: So the sentence names the new cost instead of the old one. A model can be
#: wrong about a line, and the answer to that is the quote - which is on every
#: candidate, verbatim, from the snapshot rather than from anything the model
#: said.
DERIVATION_HONESTY_SENTENCE = (
    "Bu surum adaylari, odadan okunan satirlari bir dil modeline okutarak "
    "cikarir; model yanilabilir ve bir satiri yanlis siniflandirabilir, bu "
    "yuzden bir adayi kabul etmeden once alintiyi kendiniz okuyun."
)

#: What a scan costs, said **before** it is spent (ADR-0014 6).
#:
#: A template rather than a sentence, for :data:`OPEN_STATE_SENTENCE`'s reason:
#: it cannot be shown without the two numbers that make it a statement rather
#: than a warning, and a caller holding only the prose would be tempted to show
#: it alone. The numbers come from the one place each is decided -
#: ``reading.MAX_LINES_PER_TURN`` and ``budget.CEILING.max_model_calls`` - so
#: the screen and the request cannot drift apart.
#:
#: The second half is the part a person needs and would not guess: a ceiling
#: that runs out mid-scan does not fail the scan, it leaves lines unread, and
#: those lines are listed with their reason rather than dropped.
MODEL_READING_COST_SENTENCE = (
    "Bu tarama model cagrisi harcar: her tur en cok {lines} satir tasir ve bir "
    "tarama en cok {calls} tur harcayabilir. Tavan dolarsa kalan satirlar "
    "okunmaz ve gerekcesiyle listelenir; harcanan tur sayisi sonucun yaninda "
    "gosterilir."
)

#: The second half of the same honesty, about the *refusals* rather than the
#: proposals.
#:
#: ADR-0007 8 and this package's own documentation described the six
#: prohibited work shapes as "structurally blocked". They are not: the
#: ordering is structural - a prohibition is matched before any signal, on
#: every path - but the matching itself is a list of patterns, and a review
#: walked nineteen lines past it by spelling a listed word with an inserted
#: space or by naming the same act with a noun the list did not carry. The
#: list is stronger now and it is still a list.
#:
#: Written as a separate constant rather than folded into
#: :data:`DERIVATION_HONESTY_SENTENCE`, on purpose: that sentence is pinned
#: byte-for-byte in the frontend tests, the end-to-end suite and the package's
#: verification record, and rewriting a sentence three files quote is how a
#: quotation stops being one. This is a second sentence beside it, on the same
#: surface, on every read.
PROHIBITION_HONESTY_SENTENCE = (
    "Yasakli is bicimleri de ayni yontemle, kalip eslesmesiyle reddedilir. "
    "Yasak listede olmayan bir sozcukle istenirse aday uretilebilir; bu "
    "yuzden bir adayi kabul etmeden once alintiyi okuyun."
)

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


def assert_no_forbidden_claim(text: str, *, where: str) -> None:
    """Fail closed rather than publish an over-claim of our own.

    Called on strings this package authors. A refusal here is a bug in our
    wording, and there is nothing a user or a remote writer can do to cause
    one - imported text goes through :func:`neutralise` instead.
    """
    found = find_forbidden_phrases(text)
    if found:
        raise ForbiddenClaimError(
            f"{where}: tarama dili yasak bir ifade tasiyor: {', '.join(found)}"
        )


def neutralise(text: str) -> str:
    """Make imported room text safe to fold into one of our sentences.

    Delegates the evidence layer's neutralisation for the six phrases it
    knows, then removes H1's own additions the same way. Losing an excerpt
    costs a sentence; refusing the scan would let a stranger with a keyboard
    decide what this product may display.
    """
    result = neutralise_forbidden_claims(text)
    return _mask_work_scan_phrases(result)


#: What replaces a phrase found inside imported text. Says that something was
#: removed rather than removing it silently, and carries no forbidden phrase
#: of its own.
NEUTRALISED_MARK = "[yasakli ifade cikarildi]"


def _mask_work_scan_phrases(text: str) -> str:
    """Remove H1's own phrases from imported text, character by character.

    The evidence layer's masker walks a span map so a match can be removed
    from the *original* string rather than from a normalised copy. That
    machinery is private to it, so this does the narrow version: it folds each
    candidate slice and replaces the ones that match. Slower and simpler;
    the input is a bounded excerpt, and correctness matters more than speed on
    a path that runs once per displayed line.
    """
    needles = tuple(fold(phrase) for phrase in WORK_SCAN_FORBIDDEN_PHRASES)
    folded = fold(text)
    if not any(needle in folded for needle in needles):
        return text

    result = text
    for needle in needles:
        result = _mask_one(result, needle)
    return result


def _mask_one(text: str, needle: str) -> str:
    """Replace every folded occurrence of ``needle`` in ``text``.

    Walks candidate windows over the original string, so the replacement lands
    on the original characters. A window is any slice whose folded form equals
    the needle; the search restarts after each hit, so overlapping matches
    cannot double-replace.
    """
    if needle not in fold(text):
        return text

    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        matched = 0
        # A folded phrase can be shorter or longer than its source, so the
        # window is scanned outwards rather than fixed at len(needle).
        for width in range(len(needle), min(len(needle) * 2 + 2, length - index) + 1):
            if fold(text[index : index + width]) == needle:
                matched = width
                break
        if matched:
            out.append(NEUTRALISED_MARK)
            index += matched
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


__all__ = [
    "DERIVATION_HONESTY_SENTENCE",
    "FORBIDDEN_PHRASES",
    "MODEL_READING_COST_SENTENCE",
    "NEUTRALISED_MARK",
    "OPEN_STATE_SENTENCE",
    "PERMITTED_ALTERNATIVES",
    "PROHIBITION_HONESTY_SENTENCE",
    "WORK_SCAN_FORBIDDEN_PHRASES",
    "ForbiddenClaimError",
    "assert_no_forbidden_claim",
    "find_forbidden_phrases",
    "neutralise",
]
