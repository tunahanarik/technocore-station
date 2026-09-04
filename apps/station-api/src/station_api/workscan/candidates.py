"""Deterministic candidate derivation. No model call, and none is reachable.

ADR-0007 2 settles the question this module exists to answer: candidates are
derived by **rule**, not by asking a language model. The constraint half of
the reasoning is easy to state - no code path in this build sends a
completion, the test session severs real egress at the socket, and so a model
call could not be verified by any test that exists. The load-bearing half is
different, and it is why the decision would stand even without the constraint:

    in a deterministic derivation there is no field left to invent.

Every value on a candidate comes from exactly one of two places, and which
one is visible in the type: it is either a raw field of the source line
(``room``, ``seq``, ``ts``, ``from``, ``text``) or a fixed template written
here and reviewed here. There is no third source. Output-schema validation and
a source-reference audit are then *additional* protection rather than the only
protection - which is the situation a generated candidate would have left us
in, checking a free-form answer against a shape and hoping the shape was
enough.

There is a second reason, and it is about identity. A task binds to
``source_version_id``, a digest over the source and the exact content bytes.
Rule-based derivation gives the same bytes for the same line every time, so
the identity is stable and de-duplication means something. A generated
candidate would differ on every run and the identity would name nothing.

The price, stated out loud
--------------------------
Pattern matching sees patterns. :data:`~station_api.workscan.language.
DERIVATION_HONESTY_SENTENCE` says so to the user, in the response, on every
scan - not in a design document a user never opens (ADR-0007 2).

The eight elements are enforced by construction
-----------------------------------------------
ADR-0007 8 lists eight things a candidate must carry. They are not validated
after the fact: :class:`WorkCandidate.__post_init__` refuses to build an
object that is missing any of them, the way ``EvidenceRef`` refuses to be
built for an unfillable field. A candidate that cannot carry all eight is not
produced at all, so there is no partially-formed candidate anywhere in the
system to be rendered, stored or turned into a task.

Prohibited work is refused before anything else runs
-----------------------------------------------------
Six shapes are named in :class:`ProhibitedShape` and matched **first**, before
any signal is considered, so a line that looks like one of them produces no
candidate on any path. The refusal is recorded and shown rather than dropped
silently: a line this build declined to act on is a fact about the scan, and
hiding it would make the scan look like it saw less than it did.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from station_api.digests import domain_digest
from station_api.evidence.language import fold
from station_api.identity.write_gate import CheckState
from station_api.modules.registry import ModuleId, ModuleState, get_module
from station_api.workscan.authority import CONTENT_AUTHORITY, AuthorityLevel
from station_api.workscan.errors import CandidateError
from station_api.workscan.language import (
    DERIVATION_HONESTY_SENTENCE,
    OPEN_STATE_SENTENCE,
    assert_no_forbidden_claim,
    neutralise,
)
from station_api.workscan.snapshot import RoomMessage, RoomMessagesSnapshot

#: Domain separation for a candidate's identity. Versioned: a change to what
#: goes into the identity gets a new domain rather than silently reusing this
#: one, so an old identity can never be read as a new-format one.
CANDIDATE_DOMAIN = b"technocore-station/work-scan-candidate/v1"

#: How a candidate was produced. One value today, and the field exists so a
#: later producer cannot be mistaken for this one.
DERIVATION_METHOD: Final = "rule_based_pattern_match"


# ---------------------------------------------------------------------------
# Prohibited work shapes, matched before anything else
# ---------------------------------------------------------------------------


class ProhibitedShape(StrEnum):
    """Work this product will not propose, whatever a room asks for."""

    #: Anything touching a wallet, a claim or a payment. The charter's
    #: hardest line and the one with the worst failure mode.
    WALLET_OR_PAYMENT = "wallet_or_payment"
    #: Producing volume for a score. The point of a number is the behaviour
    #: it causes, and this is the behaviour.
    POINT_FARMING = "point_farming"
    #: Repeated pings at a room or a person.
    SPAM_PING = "spam_ping"
    #: A content-free acknowledgement, posted so that something was posted.
    EMPTY_ACKNOWLEDGEMENT = "empty_acknowledgement"
    #: Opening work for oneself and then signing it off.
    SELF_APPROVAL = "self_approval"
    #: Delivering again what has already been delivered.
    DUPLICATE_DELIVERY = "duplicate_delivery"


#: Folded markers per shape. Matched against the folded message text, so the
#: Turkish and ASCII spellings of the same word are one entry.
#:
#: These are deliberately blunt. A marker that fires on an innocent line costs
#: one candidate that a person can still find by reading the room; a marker
#: that misses costs a proposal this product had promised never to make.
PROHIBITED_MARKERS: dict[ProhibitedShape, tuple[str, ...]] = {
    ProhibitedShape.WALLET_OR_PAYMENT: (
        "wallet",
        "cuzdan",
        "private key",
        "seed phrase",
        "mnemonic",
        "claim",
        "airdrop",
        "payout",
        "odeme",
        "para transfer",
        "token gonder",
        "send funds",
        "sign this transaction",
        "islem imzala",
    ),
    ProhibitedShape.POINT_FARMING: (
        "puan kasma",
        "puan topla",
        "farm points",
        "leaderboard",
        "siralamada yuksel",
        "boost my score",
        "skorumu yukselt",
    ),
    ProhibitedShape.SPAM_PING: (
        "spam",
        "herkesi etiketle",
        "tag everyone",
        "ping everyone",
        "tekrar tekrar yaz",
        "surekli mesaj at",
    ),
    ProhibitedShape.EMPTY_ACKNOWLEDGEMENT: (
        "just say done",
        "sadece done yaz",
        "tamam yazman yeter",
        "reply done",
        "type gm",
        "gm yaz",
    ),
    ProhibitedShape.SELF_APPROVAL: (
        "kendi isini onayla",
        "approve your own",
        "self approve",
        "kendine gorev ac",
    ),
    ProhibitedShape.DUPLICATE_DELIVERY: (
        "ayni seyi tekrar gonder",
        "resend the same",
        "duplicate submission",
        "tekrar teslim et",
    ),
}

#: One Turkish sentence per shape, safe to show. Shown on the refused line, so
#: the user learns what was skipped and why rather than seeing a shorter list.
PROHIBITION_DETAIL: dict[ProhibitedShape, str] = {
    ProhibitedShape.WALLET_OR_PAYMENT: (
        "Bu satir cuzdan, odeme veya hak talebi iceren bir is istiyor. Station "
        "boyle bir isi aday olarak uretmez; kimlik materyaline ve paraya "
        "dokunan islerin otomatik onerilmesi bu urunde kapalidir."
    ),
    ProhibitedShape.POINT_FARMING: (
        "Bu satir bir skoru yukseltmek icin hacim uretmeyi istiyor. Aday "
        "uretilmedi."
    ),
    ProhibitedShape.SPAM_PING: (
        "Bu satir tekrarlayan bildirim veya toplu etiketleme istiyor. Aday "
        "uretilmedi."
    ),
    ProhibitedShape.EMPTY_ACKNOWLEDGEMENT: (
        "Bu satir icerigi olmayan bir onay mesaji istiyor. Bir sey "
        "yazilmis olmasi bir sonuc degildir; aday uretilmedi."
    ),
    ProhibitedShape.SELF_APPROVAL: (
        "Bu satir kisinin kendi actigi isi kendi onaylamasini istiyor. Kabul "
        "bir baskasinin eylemidir; aday uretilmedi."
    ),
    ProhibitedShape.DUPLICATE_DELIVERY: (
        "Bu satir zaten teslim edilmis bir seyin yeniden gonderilmesini "
        "istiyor. Aday uretilmedi."
    ),
}

_FOLDED_PROHIBITIONS: dict[ProhibitedShape, tuple[str, ...]] = {
    shape: tuple(fold(marker) for marker in markers)
    for shape, markers in PROHIBITED_MARKERS.items()
}


def prohibited_shape(text: str) -> ProhibitedShape | None:
    """The first prohibited shape a line matches, or ``None``.

    Order follows :class:`ProhibitedShape`'s declaration, so the wallet and
    payment shape is tested first. A line that matches two is reported as the
    most serious one rather than as both: the outcome is identical - nothing
    is produced - and one sentence is easier to act on than two.
    """
    haystack = fold(text)
    for shape, needles in _FOLDED_PROHIBITIONS.items():
        if any(needle in haystack for needle in needles):
            return shape
    return None


# ---------------------------------------------------------------------------
# The signals, and the fixed templates each one produces
# ---------------------------------------------------------------------------


class SignalId(StrEnum):
    """The kinds of line this build recognises. Four, and never a fifth
    computed at runtime."""

    HELP_WANTED = "help_wanted"
    DEFECT_REPORT = "defect_report"
    REVIEW_REQUEST = "review_request"
    DOCUMENTATION_GAP = "documentation_gap"


@dataclass(frozen=True, slots=True)
class Signal:
    """One recogniser: what it matches, and the fixed sentences it produces.

    Every template below is a **constant with named substitutions**, and the
    only values substituted are the raw source fields. There is no free text
    anywhere in a produced candidate that did not come from one of these
    strings or from the message itself.
    """

    id: SignalId
    markers: tuple[str, ...]
    benefit: str
    deliverable: str
    success_condition: str
    test_method: str
    #: What a person would have to permit before this could be acted on.
    permissions: tuple[str, ...]
    #: What could go wrong, stated before anybody agrees to anything.
    risks: tuple[str, ...]
    #: A coarse effort band. A band and not a number, because a number
    #: implies a measurement nothing here performed.
    effort_band: str


#: The shared permission line. Every candidate carries it: acting on any of
#: them means writing to a public room, which is a separate, explicit,
#: per-message approval in the composer and is never implied by accepting a
#: suggestion.
_PERMISSION_WRITE = (
    "Sonucu paylasmak icin bir odaya imzali mesaj gonderilmesi gerekir; bu, "
    "composer'da ayri ve tek seferlik bir onaydir ve bir adayi kabul etmek "
    "onu vermez."
)

_PERMISSION_READ = (
    "Odanin devamini okumak icin bu tarama tekrar calistirilmalidir; Station "
    "kendiliginden yeniden okumaz."
)

_RISK_UNVERIFIED_AUTHOR = (
    "Talebi yazan kisi dogrulanmamistir; did:key olmayan bir yazar adi kendi "
    "beyanidir."
)

_RISK_PARTIAL_VIEW = (
    "Yalnizca okunan dilim gorulmustur. Oda halkasi eski mesajlari dusurur, "
    "yani daha once verilmis bir cevap bu taramada gorunmeyebilir."
)

_RISK_NO_SEMANTICS = (
    "Aday kalip eslesmesiyle cikarildi. Satirin gercek anlami farkli olabilir; "
    "kabul etmeden once alintiyi okuyun."
)


SIGNALS: tuple[Signal, ...] = (
    Signal(
        id=SignalId.HELP_WANTED,
        markers=(
            "yardim eden",
            "yardimci olabilir",
            "help wanted",
            "looking for someone",
            "kim yapabilir",
            "isteyen var mi",
            "birine ihtiyacim var",
            "need help with",
        ),
        benefit=(
            "'{room}' odasinda {author} bir yardim cagrisi yazdi. Isi yapan "
            "kisi o cagriyi karsilamis olur; baska kimse hakkinda bir fayda "
            "iddia edilmiyor."
        ),
        deliverable=(
            "Alintidaki istegin karsiligi olan tek bir somut cikti ve o "
            "ciktinin nerede oldugunu soyleyen tek bir mesaj."
        ),
        success_condition=(
            "Cikti var, alintidaki istegi karsiliyor ve istegi yazan kisi "
            "kabul ettigini yaziyor."
        ),
        test_method=(
            "Ciktinin kendisi acilir ve alintiyla yan yana okunur; kabul, "
            "odadaki yaniti gosteren bir kanit kaydiyla belgelenir."
        ),
        permissions=(_PERMISSION_WRITE, _PERMISSION_READ),
        risks=(_RISK_UNVERIFIED_AUTHOR, _RISK_PARTIAL_VIEW, _RISK_NO_SEMANTICS),
        effort_band="bir oturum veya daha az",
    ),
    Signal(
        id=SignalId.DEFECT_REPORT,
        markers=(
            "hata veriyor",
            "calismiyor",
            "bozuk",
            "is broken",
            "does not work",
            "doesn't work",
            "throws an error",
            "bug:",
        ),
        benefit=(
            "'{room}' odasinda {author} calismayan bir sey bildirdi. Sorunu "
            "yeniden uretip duzelten kisi o bildirimi karsilamis olur."
        ),
        deliverable=(
            "Sorunu yeniden ureten en kisa adimlar, tek bir duzeltme ve "
            "duzeltmenin isini gordugunu gosteren tek bir kanit."
        ),
        success_condition=(
            "Yeniden uretme adimlari duzeltmeden once basarisiz, sonra "
            "basarili sonuc veriyor."
        ),
        test_method=(
            "Ayni adimlar duzeltme oncesi ve sonrasi calistirilir; iki sonuc "
            "ayri ayri kaydedilir ve tek bir 'gecti' isaretine indirgenmez."
        ),
        permissions=(_PERMISSION_WRITE, _PERMISSION_READ),
        risks=(_RISK_UNVERIFIED_AUTHOR, _RISK_PARTIAL_VIEW, _RISK_NO_SEMANTICS),
        effort_band="bir oturum veya daha az",
    ),
    Signal(
        id=SignalId.REVIEW_REQUEST,
        markers=(
            "review eder misiniz",
            "gozden gecirir misiniz",
            "please review",
            "can someone review",
            "feedback almak istiyorum",
            "yorum bekliyorum",
        ),
        benefit=(
            "'{room}' odasinda {author} bir inceleme istedi. Inceleyen kisi o "
            "istegi karsilamis olur; inceleme tek basina bir basari isareti "
            "degildir."
        ),
        deliverable=(
            "Alintidaki seyin uzerine yazilmis, her maddesi kaynagi gosteren "
            "tek bir inceleme notu."
        ),
        success_condition=(
            "Inceleme notu istenen seyi kapsiyor ve isteyen kisi okudugunu "
            "yaziyor."
        ),
        test_method=(
            "Notun her maddesi incelenen seydeki bir konuma geri baglanir; "
            "baglanamayan madde nottan cikarilir."
        ),
        permissions=(_PERMISSION_WRITE, _PERMISSION_READ),
        risks=(_RISK_UNVERIFIED_AUTHOR, _RISK_PARTIAL_VIEW, _RISK_NO_SEMANTICS),
        effort_band="bir oturum veya daha az",
    ),
    Signal(
        id=SignalId.DOCUMENTATION_GAP,
        markers=(
            "belge yok",
            "dokuman yok",
            "nasil kullanilir",
            "no documentation",
            "undocumented",
            "how do i use",
            "ornek var mi",
        ),
        benefit=(
            "'{room}' odasinda {author} eksik bir aciklama bildirdi. Aciklamayi "
            "yazan kisi o eksigi kapatmis olur."
        ),
        deliverable=(
            "Alintidaki soruyu bastan sona cevaplayan tek bir yazi ve icinde "
            "calistirilabilir tek bir ornek."
        ),
        success_condition=(
            "Ornek, yaziyi ilk kez okuyan biri tarafindan degistirilmeden "
            "calistirilabiliyor."
        ),
        test_method=(
            "Ornek temiz bir ortamda oldugu gibi calistirilir; calismazsa "
            "yazi eksiktir ve sonuc 'gecti' sayilmaz."
        ),
        permissions=(_PERMISSION_WRITE, _PERMISSION_READ),
        risks=(_RISK_UNVERIFIED_AUTHOR, _RISK_PARTIAL_VIEW, _RISK_NO_SEMANTICS),
        effort_band="bir oturum veya daha az",
    ),
)

_FOLDED_SIGNALS: tuple[tuple[Signal, tuple[str, ...]], ...] = tuple(
    (signal, tuple(fold(marker) for marker in signal.markers)) for signal in SIGNALS
)


def matching_signal(text: str) -> Signal | None:
    """The first signal a line matches, in declaration order, or ``None``.

    First rather than best: "best" would need a score, a score would need a
    weighting, and a weighting is the first step towards the inference this
    package does not perform. Declaration order is a decision a reviewer can
    read.
    """
    haystack = fold(text)
    for signal, needles in _FOLDED_SIGNALS:
        if any(needle in haystack for needle in needles):
            return signal
    return None


# ---------------------------------------------------------------------------
# The eight elements
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceQuote:
    """Element 1: the verbatim line, and where it came from.

    Refuses to exist without all four coordinates. A quote with no ``seq`` is
    a sentence somebody could have typed anywhere.
    """

    room: str
    seq: int
    ts: str
    #: The ``from`` value as it arrived. A ``did:key`` or a nickname; the two
    #: are told apart by the flag below and never by the string's appearance.
    author: str
    #: True only for a value matching the published key shape.
    author_is_did_key: bool
    #: The one sentence :mod:`station_api.workscan.authority` permits about
    #: that value. Carried on the quote rather than re-derived at every
    #: display site, so no view can accidentally say more.
    author_detail: str
    #: The message body as it arrived, swept for display and not rewritten.
    quote: str

    def __post_init__(self) -> None:
        if not self.room:
            raise CandidateError("Aday bir oda adi olmadan uretilemez.")
        if self.seq < 0:
            raise CandidateError("Aday negatif bir sira numarasi tasiyamaz.")
        if not self.ts:
            raise CandidateError("Aday kaynak zaman damgasi olmadan uretilemez.")
        if not self.quote.strip():
            raise CandidateError("Aday birebir alinti olmadan uretilemez.")

    @property
    def authority(self) -> AuthorityLevel:
        return CONTENT_AUTHORITY

    @property
    def reference(self) -> str:
        """The machine-checkable pointer, in one string."""
        return f"{self.room}#{self.seq}@{self.ts}"


@dataclass(frozen=True, slots=True)
class EffortEstimate:
    """Element 6: an estimate, and it says so in its own type.

    ``label`` is fixed rather than a parameter. A caller cannot construct one
    that presents itself as a measurement, because there is no argument that
    would let it.
    """

    band: str
    basis: str
    label: str = "tahmin"

    def __post_init__(self) -> None:
        if self.label != "tahmin":
            raise CandidateError(
                "Calisma tahmini yalnizca tahmin olarak etiketlenebilir."
            )
        if not self.band.strip():
            raise CandidateError("Calisma tahmini bos olamaz.")


#: The one basis this build has. Named, so that its poverty is visible: the
#: band comes from the signal table, not from anything about this particular
#: line.
ESTIMATE_BASIS = (
    "Bu deger olculmedi. Taninan sinyal turune bagli sabit bir banttir ve "
    "satirin kendisi hakkinda hicbir sey soylemez."
)

#: Element 6's other half. There is no budget in this build; H2 owns it. The
#: state is ``not_implemented`` and never ``passed``, so a missing budget can
#: never read as an approved one.
BUDGET_STATE: Final = CheckState.NOT_IMPLEMENTED

BUDGET_DETAIL = (
    "Bu surumde butce yoktur. Bir maliyet tavani tanimlanmadi, olculmedi ve "
    "uygulanmadi; butce Paket H2'nin konusudur."
)


@dataclass(frozen=True, slots=True)
class CandidateCapability:
    """Element 5: whether this build has the tools and data for the work.

    Read from the compile-time module registry and the write gate's current
    verdict, never asserted. A candidate whose module is ``PLANNED`` says so,
    and a closed write gate says so, and both travel with the candidate rather
    than being resolved into one optimistic boolean.
    """

    module_id: str
    module_state: str
    #: Whether the module that would own this work is in this build.
    module_available: bool
    #: The composer's gate, as it stands. Not a permission this scan grants.
    write_gate_open: bool
    detail: str

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise CandidateError("Aday yetkinlik cumlesi olmadan uretilemez.")

    @property
    def ready(self) -> bool:
        """Both halves, and never one standing in for the other."""
        return self.module_available and self.write_gate_open


@dataclass(frozen=True, slots=True)
class OpenStateNote:
    """Element 8, and the one ADR-0007 8 forbids stating with certainty.

    There is no boolean here on purpose. A field named ``is_open`` would be
    read as an answer, and this surface cannot produce one: the room is a ring
    that drops history, the read is a bounded slice, and an answer may have
    been posted after it. What exists is the moment of the reading.
    """

    read_at: datetime
    detail: str

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise CandidateError("Aday durum cumlesi olmadan uretilemez.")


def open_state_note(read_at: datetime) -> OpenStateNote:
    """Build element 8 from the only permitted wording."""
    detail = OPEN_STATE_SENTENCE.format(read_at=read_at.isoformat())
    assert_no_forbidden_claim(detail, where="work_scan.open_state")
    return OpenStateNote(read_at=read_at, detail=detail)


@dataclass(frozen=True, slots=True)
class WorkCandidate:
    """One proposal, carrying all eight elements or not existing.

    ``__post_init__`` is the enforcement, not a validator somebody remembers
    to call. Anything that reaches a view, a response body or a task has
    already been through it.
    """

    id: str
    signal: SignalId
    #: 1
    source: SourceQuote
    #: 2
    benefit: str
    #: 3
    deliverable: str
    #: 4, both halves
    success_condition: str
    test_method: str
    #: 5
    capability: CandidateCapability
    #: 6, both halves
    effort: EffortEstimate
    budget_state: CheckState
    budget_detail: str
    #: 7, both halves
    permissions: tuple[str, ...]
    risks: tuple[str, ...]
    #: 8
    open_state: OpenStateNote
    #: How this candidate was produced. Fixed today; a field so that a later
    #: producer is distinguishable rather than assumed.
    derivation: str = DERIVATION_METHOD

    def __post_init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("benefit", self.benefit),
                ("deliverable", self.deliverable),
                ("success_condition", self.success_condition),
                ("test_method", self.test_method),
                ("budget_detail", self.budget_detail),
            )
            if not value.strip()
        ]
        if missing:
            raise CandidateError(
                "Aday su zorunlu ogeler olmadan uretilemez: " + ", ".join(missing)
            )
        if not self.permissions:
            raise CandidateError("Aday gereken izinler yazilmadan uretilemez.")
        if not self.risks:
            raise CandidateError("Aday riskler yazilmadan uretilemez.")
        if self.budget_state is not CheckState.NOT_IMPLEMENTED:
            raise CandidateError(
                "Bu surumde butce yoktur; aday baska bir butce durumu tasiyamaz."
            )
        if not self.id:
            raise CandidateError("Aday kimliksiz uretilemez.")

    @property
    def authority(self) -> AuthorityLevel:
        """What the quoted content is worth. Always community."""
        return CONTENT_AUTHORITY


@dataclass(frozen=True, slots=True)
class RefusedLine:
    """A line this build declined to turn into a candidate, and why.

    Kept and shown. A scan that silently skipped these would report a shorter
    list with no explanation, and the missing entries would look like lines
    nothing was found in.
    """

    room: str
    seq: int
    shape: ProhibitedShape
    detail: str


@dataclass(frozen=True, slots=True)
class DerivationResult:
    """Everything one room's snapshot produced, including what it refused."""

    room: str
    candidates: tuple[WorkCandidate, ...]
    refusals: tuple[RefusedLine, ...]
    #: How many lines were read to produce the above. Reported so an empty
    #: candidate list is distinguishable from an empty room.
    lines_read: int
    honesty: str = DERIVATION_HONESTY_SENTENCE


def candidate_id(room: str, seq: int) -> str:
    """The identity of one candidate, domain-separated and length-prefixed.

    Built from the room and the sequence number and nothing else, which is
    what makes it stable across scans: the same line yields the same identity,
    so a second scan of the same room proposes the same work once rather than
    twice. That is where "no duplicate delivery" is enforced structurally
    rather than by asking a producer to be careful.
    """
    return domain_digest(CANDIDATE_DOMAIN, room, str(seq))


def capability_for(
    module_id: ModuleId, *, write_gate_open: bool
) -> CandidateCapability:
    """Read element 5 off the registry and the gate. Asserts nothing.

    The module record is the compile-time one, so a module that is ``PLANNED``
    produces a candidate that says the owning code is not in this build -
    rather than a candidate that looks actionable and fails later.
    """
    record = get_module(module_id)
    available = record.state is ModuleState.AVAILABLE
    if available:
        module_sentence = "Bu isi ustlenecek modul bu surumde var."
    else:
        module_sentence = (
            "Bu isi ustlenecek modul bu surumde yok; kayit "
            f"{record.available_from or 'ilerideki bir paket'} icin acilmis "
            "durumda."
        )
    gate_sentence = (
        "Yazma kapisi su anda acik."
        if write_gate_open
        else "Yazma kapisi su anda kapali; sonuc paylasilamaz."
    )
    detail = f"{module_sentence} {gate_sentence}"
    assert_no_forbidden_claim(detail, where="work_scan.capability")
    return CandidateCapability(
        module_id=record.id.value,
        module_state=record.state.value,
        module_available=available,
        write_gate_open=write_gate_open,
        detail=detail,
    )


def _author_phrase(message: RoomMessage) -> str:
    """How a message's writer is named inside one of *our* sentences.

    A ``did:key`` is printed as itself. Anything else is a nickname the writer
    typed, so it is neutralised before it joins our sentence and it is
    introduced as what it is - the phrase never presents the value as an
    identity this build checked.
    """
    if message.author.is_did_key:
        return message.author.value
    if not message.author.value:
        return "adi bildirilmemis bir yazar"
    return f"kendi beyan ettigi adiyla '{neutralise(message.author.value)}'"


def derive_from_room(
    snapshot: RoomMessagesSnapshot,
    *,
    capability: CandidateCapability,
) -> DerivationResult:
    """Turn one room snapshot into candidates. Pure; contacts nobody.

    The order of the two checks is load-bearing: a prohibited shape is
    recognised **before** a signal is looked for, so there is no path on which
    a line that asks for a wallet action also happens to match a help marker
    and gets produced anyway.
    """
    candidates: dict[str, WorkCandidate] = {}
    refusals: list[RefusedLine] = []

    for message in snapshot.messages:
        shape = prohibited_shape(message.text)
        if shape is not None:
            refusals.append(
                RefusedLine(
                    room=snapshot.room,
                    seq=message.seq,
                    shape=shape,
                    detail=PROHIBITION_DETAIL[shape],
                )
            )
            continue

        signal = matching_signal(message.text)
        if signal is None:
            continue

        identity = candidate_id(snapshot.room, message.seq)
        if identity in candidates:
            # Structurally impossible on a well-formed reply, because ``seq``
            # is a total order within a room. Kept because the reply is
            # anonymous input: a document that repeated a sequence number
            # would otherwise produce the same proposal twice.
            continue

        substitutions = {
            "room": neutralise(snapshot.room),
            "author": _author_phrase(message),
        }
        benefit = signal.benefit.format(**substitutions)
        assert_no_forbidden_claim(signal.deliverable, where="work_scan.deliverable")
        assert_no_forbidden_claim(
            signal.success_condition, where="work_scan.success_condition"
        )
        assert_no_forbidden_claim(signal.test_method, where="work_scan.test_method")

        candidates[identity] = WorkCandidate(
            id=identity,
            signal=signal.id,
            source=SourceQuote(
                room=snapshot.room,
                seq=message.seq,
                ts=message.ts,
                author=message.author.value,
                author_is_did_key=message.author.is_did_key,
                author_detail=message.author.detail,
                quote=message.text,
            ),
            benefit=benefit,
            deliverable=signal.deliverable,
            success_condition=signal.success_condition,
            test_method=signal.test_method,
            capability=capability,
            effort=EffortEstimate(band=signal.effort_band, basis=ESTIMATE_BASIS),
            budget_state=BUDGET_STATE,
            budget_detail=BUDGET_DETAIL,
            permissions=signal.permissions,
            risks=signal.risks,
            open_state=open_state_note(snapshot.staleness.read_at),
        )

    return DerivationResult(
        room=snapshot.room,
        candidates=tuple(candidates.values()),
        refusals=tuple(refusals),
        lines_read=len(snapshot.messages),
    )


def candidate_content(candidate: WorkCandidate) -> bytes:
    """The exact bytes a task binds its content version to.

    Deterministic and ordered: the same line produces the same bytes on every
    scan, which is what makes ``source_version_id`` a stable identity rather
    than a per-run random value (ADR-0007 2). Every element that a person
    would have read before accepting is in here, so evidence recorded against
    one version stops matching if any of them changes.

    One element is included as its **template** rather than as its rendered
    text, and the exception is deliberate. Element 8's sentence carries the
    moment the snapshot was read, which is a fact about the *scan* and not
    about the proposal: folding it in would give the same line a new identity
    every time anybody looked at the room, and "evidence stops matching when
    the content changes" would degrade into "evidence stops matching when the
    clock moves". The reading time is not lost - it is on the note the user
    sees and on the task row's own timestamps; it is simply not part of what
    the content version means.
    """
    parts: Iterable[str] = (
        candidate.id,
        candidate.signal.value,
        candidate.source.reference,
        candidate.source.author,
        candidate.source.quote,
        candidate.benefit,
        candidate.deliverable,
        candidate.success_condition,
        candidate.test_method,
        candidate.capability.detail,
        candidate.effort.label,
        candidate.effort.band,
        candidate.budget_state.value,
        "\n".join(candidate.permissions),
        "\n".join(candidate.risks),
        OPEN_STATE_SENTENCE,
        candidate.derivation,
    )
    return "\x1f".join(parts).encode("utf-8")


__all__ = [
    "BUDGET_DETAIL",
    "BUDGET_STATE",
    "CANDIDATE_DOMAIN",
    "DERIVATION_METHOD",
    "ESTIMATE_BASIS",
    "PROHIBITED_MARKERS",
    "PROHIBITION_DETAIL",
    "SIGNALS",
    "CandidateCapability",
    "DerivationResult",
    "EffortEstimate",
    "OpenStateNote",
    "ProhibitedShape",
    "RefusedLine",
    "Signal",
    "SignalId",
    "SourceQuote",
    "WorkCandidate",
    "candidate_content",
    "candidate_id",
    "capability_for",
    "derive_from_room",
    "matching_signal",
    "open_state_note",
    "prohibited_shape",
]
