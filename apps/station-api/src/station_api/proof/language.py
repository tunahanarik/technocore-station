"""The claims the proof workspace may not make, and the ones it makes instead.

Package E built this control for the evidence layer, H1 extended it to the
work scan and H2 to the agent runtime. Every one of those scans is scoped to
its own directory, so a new package's wording is covered by **nothing at all**
until it brings its own - and a rule that does not cover the text being
written is not a rule (ADR-0007 10, ADR-0008 9, ADR-0009 5).

Reused rather than reimplemented
--------------------------------
:func:`station_api.evidence.language.fold` does the comparison, and the three
earlier registries are inherited whole through
:mod:`station_api.agent.language`, which already composes evidence's six with
H1's seven and H2's seven. A phrase added in any of them is refused here on
the same commit.

What H3 adds, and why each one
-------------------------------
This package's whole subject is a word - *proof* - that a reader is entitled
to misread as *proven*. Every phrase below is a sentence somebody would
reasonably write in a proof workspace and that this build cannot support.

``"bagimsiz olarak dogrulandi"``, ``"ucuncu taraf onayi"``
    There is no independent check in this release. The model lane is closed
    (ADR-0008 2), so there is no second opinion, and a run's own output
    presented as a third party's verdict is the specific dishonesty ADR-0009 6
    refuses. The field says ``not_implemented`` and says why.

``"ozet icerigi dogrular"``, ``"kanitlanmis cikti"``
    A SHA-256 fixes the bytes of a file. It says nothing about whether those
    bytes are correct, complete or useful, and ADR-0009 11 requires that
    difference to be written down rather than left to a reader who sees the
    word *proof* in a heading. :data:`HASH_SCOPE_SENTENCE` is the permitted
    wording.

``"denetim basariyla kosuldu"``, ``"cikis kodu 0"``
    Nothing here runs a check, so there is no exit code (ADR-0008 1,
    ADR-0009 7). The plan's success criterion and the instruction for
    re-deriving it are packaged as **text**, and a number is not invented to
    fill the space where a result would go.

``"paylasim dogrulandi"``
    Handing a file to the browser is not a publication and not a verification.
    ``public_share`` is filled only from an archived send (ADR-0009 1), and
    even then it carries that send's own outcome rather than a verdict this
    package computed.

The claim/data split is Package E's, unchanged
-----------------------------------------------
A **claim** is a sentence this product writes; a forbidden phrase in one of
them is a bug in our wording and fails closed. **Data** is text that passed
through us - a task title a person typed, a file name, a plan's success
criterion - and it is neutralised where it joins one of our sentences, never a
reason to refuse a bundle. A user who types the banned words into a task title
must not be able to make the product refuse to show them their own proof.
"""

from __future__ import annotations

from station_api.agent.language import FORBIDDEN_PHRASES as AGENT_FORBIDDEN_PHRASES
from station_api.agent.language import neutralise as neutralise_agent_phrases
from station_api.evidence.language import ForbiddenClaimError, fold

#: The phrases H3 adds, in folded form - which is what they are compared as.
PROOF_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "bagimsiz olarak dogrulandi",
    "ucuncu taraf onayi",
    "ozet icerigi dogrular",
    "kanitlanmis cikti",
    "denetim basariyla kosuldu",
    "cikis kodu 0",
    "paylasim dogrulandi",
)

#: Everything this package refuses: the twenty inherited from E, H1 and H2,
#: plus H3's seven. Composed rather than copied, so a phrase added in any
#: earlier registry is refused here without a second edit.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    *AGENT_FORBIDDEN_PHRASES,
    *PROOF_FORBIDDEN_PHRASES,
)

#: What to say instead of each H3 phrase, in the same order.
PERMITTED_ALTERNATIVES: tuple[str, ...] = (
    "bagimsiz kontrol: uygulanmadi (not_implemented)",
    "bagimsiz kontrol: uygulanmadi (not_implemented)",
    "ozet yalnizca dosyanin ayni kaldigini tanimlar",
    "uretilen cikti (dogrulugu hakkinda bir iddia degildir)",
    "denetim sonucu: uygulanmadi (not_implemented)",
    "cikis kodu uretilmez; olcut metin olarak paketlenir",
    "gonderim arsivlendi (sonucu kaydin kendi alanindadir)",
)

#: The sentence ADR-0009 11 requires, and the only wording permitted for it.
#:
#: It is deliberately written so that it does **not** trip the registry above:
#: it says what a digest does define and then what it does not, without ever
#: putting "verifies" next to "content". A guard that its own permitted
#: wording could not pass would be a guard somebody edits the guard for.
HASH_SCOPE_SENTENCE = (
    "Bir SHA-256 ozeti yalnizca dosyanin bayt bakimindan ayni kaldigini "
    "tanimlar. Icerigin ne kadar dogru, eksiksiz veya yararli oldugu hakkinda "
    "hicbir sey soylemez; ozetler esit diye cikti kabul edilmis sayilmaz. "
    "Bu bolumun adindaki 'kanit' kelimesi bir sonuc degil, toplanmis "
    "malzemedir."
)

#: The second half, about what the bundle itself is and is not.
BUNDLE_SCOPE_SENTENCE = (
    "Paket bu makinede toplanan malzemenin bir kopyasidir ve hicbir yola "
    "yazilmaz; tarayiciya teslim edilir. Iceriginin bir kismi eksiktir ve "
    "eksik olan her kalem adiyla listelenir."
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

    Called on strings this package authors: the bundle's own sentences, the
    reasons a field is empty, the refusals. A failure here is a bug in our
    wording, and there is nothing a user can type that causes one - their text
    goes through :func:`neutralise` instead.
    """
    found = find_forbidden_phrases(text)
    if found:
        raise ForbiddenClaimError(
            f"{where}: kanit dili yasak bir ifade tasiyor: {', '.join(found)}"
        )


#: What replaces a phrase found inside imported text.
NEUTRALISED_MARK = "[yasakli ifade cikarildi]"


def neutralise(text: str) -> str:
    """Make user-supplied text safe to fold into one of our sentences.

    Delegates the three earlier layers first - they already know twenty
    phrases between them - then removes H3's own additions the same way.
    Losing a fragment of a title costs a sentence; refusing the bundle would
    let a keyboard decide whether a person may see their own work.
    """
    return _mask_proof_phrases(neutralise_agent_phrases(text))


def _mask_proof_phrases(text: str) -> str:
    """Remove H3's own phrases from imported text.

    The narrow masker ``workscan.language`` and ``agent.language`` both write:
    fold candidate windows over the original string so the replacement lands
    on the original characters. The input is a bounded title or file name, so
    simplicity beats speed here.
    """
    needles = tuple(fold(phrase) for phrase in PROOF_FORBIDDEN_PHRASES)
    folded = fold(text)
    if not any(needle in folded for needle in needles):
        return text

    result = text
    for needle in needles:
        result = _mask_one(result, needle)
    return result


def _mask_one(text: str, needle: str) -> str:
    """Replace every folded occurrence of ``needle`` in ``text``."""
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
    "BUNDLE_SCOPE_SENTENCE",
    "FORBIDDEN_PHRASES",
    "HASH_SCOPE_SENTENCE",
    "NEUTRALISED_MARK",
    "PERMITTED_ALTERNATIVES",
    "PROOF_FORBIDDEN_PHRASES",
    "ForbiddenClaimError",
    "assert_no_forbidden_claim",
    "find_forbidden_phrases",
    "neutralise",
]
