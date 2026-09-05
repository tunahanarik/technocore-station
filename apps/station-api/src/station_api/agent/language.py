"""The claims the agent runtime may not make, and the ones it makes instead.

Package E built this control for the evidence layer and H1 extended it to the
work scan (ADR-0007 10). Both scans are scoped to their own directory, so a
new package's wording is covered by nothing at all until it brings its own -
and a rule that does not cover the text being written is not a rule. ADR-0008
9 asks H2 for the same two halves over its own tree: a runtime guard on the
sentences this package writes, and a static scan over **every string literal
in the package**, plus a mutation control that proves the guard is
load-bearing.

Reused rather than reimplemented
--------------------------------
:func:`station_api.evidence.language.fold` does the comparison and the
evidence layer's six phrases are inherited whole, exactly as
:mod:`station_api.workscan.language` inherits them. H1's seven are inherited
too: a scan report and a run report are shown on the same screen, and a
phrase this product refuses in one place it refuses in the other.

What H2 adds, and why each one
-------------------------------
``"izole calisma ortami"``, ``"guvenli sanal makine"``
    There is no isolation. ADR-0008 1 measured a sandbox on this machine and
    decided not to rely on it, so any sentence promising an isolated or
    virtualised environment describes something this build does not have.
    The permitted wording is
    :data:`station_api.agent.isolation.EXECUTION_UNAVAILABLE_DETAIL`.

``"kod calistirildi"``, ``"komut calistirildi"``
    Nothing in this package runs a command. Saying so would be the single
    most expensive false sentence the product could print.

``"test gecti"``, ``"testler gecti"``
    A test result is a **recorded** result, and this build records none: the
    executor that would produce one is exactly the thing that is closed. The
    run reports ``not_implemented`` for its test condition, which is why a
    task cannot reach ``ready_to_publish`` from a run.

``"otomatik onaylandi"``
    Approval is a person's act. A run begins because a user asked for it, and
    a run finishing does not accept its own output (ADR-0008 6, 7).

The claim/data split is Package E's, unchanged
-----------------------------------------------
A **claim** is a sentence this product writes; a forbidden phrase in one is a
bug in our wording and fails closed. **Data** is text that passed through us -
a file name a user typed, an excerpt from an approved input - and it is
neutralised where it joins one of our sentences, never a reason to refuse a
run. A user who types the banned words into a file name must not be able to
make the product refuse to show them their own workspace.
"""

from __future__ import annotations

from station_api.evidence.language import (
    ForbiddenClaimError,
    fold,
)
from station_api.workscan.language import FORBIDDEN_PHRASES as SCAN_FORBIDDEN_PHRASES
from station_api.workscan.language import neutralise as neutralise_scan_phrases

#: The phrases H2 adds, in folded form - which is what they are compared as.
AGENT_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "izole calisma ortami",
    "guvenli sanal makine",
    "kod calistirildi",
    "komut calistirildi",
    "test gecti",
    "testler gecti",
    "otomatik onaylandi",
)

#: Everything this package refuses: the evidence layer's six, H1's seven and
#: H2's seven. Composed rather than copied, so a phrase added in either of the
#: earlier registries is refused here on the same commit.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    *SCAN_FORBIDDEN_PHRASES,
    *AGENT_FORBIDDEN_PHRASES,
)

#: What to say instead of each H2 phrase, in the same order.
PERMITTED_ALTERNATIVES: tuple[str, ...] = (
    "izolasyon yok; yurutme kapali (execution_unavailable)",
    "izolasyon yok; yurutme kapali (execution_unavailable)",
    "arac cagrisi yapildi (kod yurutulmedi)",
    "arac cagrisi yapildi (kabuk komutu yurutulmedi)",
    "test sonucu: uygulanmadi (not_implemented)",
    "test sonucu: uygulanmadi (not_implemented)",
    "kullanicinin acik onayi bekleniyor",
)

#: The sentence shown beside every run. ADR-0008 1 and 7 both require the
#: cost of a closed executor to be stated to the user rather than left in a
#: design document.
RUN_HONESTY_SENTENCE = (
    "Bu surumde arac zinciri deterministiktir: model cagrisi, kabuk komutu ve "
    "keyfi kod yurutmesi yoktur. Uretilen dosyalar uzerinde yalnizca "
    "deterministik dogrulayicilar kosar; test sonucu 'uygulanmadi' kalir ve "
    "gorev bu nedenle yayima hazir sayilamaz."
)

#: The second half, about what a stop actually stops.
STOP_HONESTY_SENTENCE = (
    "Durdur, sonraki arac cagrisini engeller. Baslamis bir cagri kendi "
    "adimini bitirir; iptalden sonra donen sonucu kaydedilmez ve urettigi "
    "dosya calisma alanindan kaldirilir."
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

    Called on strings this package authors: activity details, step details,
    refusal sentences. A refusal here is a bug in our wording, and there is
    nothing a user can type that causes one - their text goes through
    :func:`neutralise` instead.
    """
    found = find_forbidden_phrases(text)
    if found:
        raise ForbiddenClaimError(
            f"{where}: agent dili yasak bir ifade tasiyor: {', '.join(found)}"
        )


#: What replaces a phrase found inside imported text.
NEUTRALISED_MARK = "[yasakli ifade cikarildi]"


def neutralise(text: str) -> str:
    """Make user-supplied text safe to fold into one of our sentences.

    Delegates the two earlier layers first - they already know the thirteen
    phrases between them - then removes H2's own additions the same way.
    Losing a fragment of a file name costs a sentence; refusing the run would
    let a keyboard decide what this product may display.
    """
    return _mask_agent_phrases(neutralise_scan_phrases(text))


def _mask_agent_phrases(text: str) -> str:
    """Remove H2's own phrases from imported text.

    The narrow version of the evidence layer's masker, exactly as
    ``workscan.language`` writes it: fold candidate windows over the original
    string so the replacement lands on the original characters. The input is
    a bounded name or excerpt, so simplicity beats speed here.
    """
    needles = tuple(fold(phrase) for phrase in AGENT_FORBIDDEN_PHRASES)
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
    "AGENT_FORBIDDEN_PHRASES",
    "FORBIDDEN_PHRASES",
    "NEUTRALISED_MARK",
    "PERMITTED_ALTERNATIVES",
    "RUN_HONESTY_SENTENCE",
    "STOP_HONESTY_SENTENCE",
    "ForbiddenClaimError",
    "assert_no_forbidden_claim",
    "find_forbidden_phrases",
    "neutralise",
]
