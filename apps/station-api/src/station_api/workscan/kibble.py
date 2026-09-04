"""The Kibble adapter record: opened, described, and deliberately not built.

This module contains **no client, no endpoint constant that anything fetches
and no request**. It is a record of what was verified about a third-party
service, what was not, and why the answer to "should we integrate it" is
"not until the unverified column is empty" (ADR-0007 1).

Why a record at all, if nothing calls it
----------------------------------------
The alternative to a record is silence, and silence about a service the
product's own subject matter points at reads as "we did not look". This is
``ModuleState.PLANNED`` applied to an external dependency: registering the
target keeps the intended shape reviewable, and the marker is what stops it
being rendered as though it were a feature.

The split is Package G's ``TABLE_PROVENANCE`` pattern
-----------------------------------------------------
G had a compile-time model table whose age was shown **unconditionally**,
beside a pinned count of what it did not cover, so that a source page growing
became a sentence rather than an invisible drift. The same shape is used here
for a different kind of gap: two lists, one of things a person read and one of
things nobody could, with the date of the reading carried on both. A record
that only listed what worked would be the "reporting an absence as full
support" failure the charter names.

The service's own words are quoted, not summarised
---------------------------------------------------
:data:`SELF_DESCRIPTION` and :data:`SCORE_SELF_DESCRIPTION` are what the
service says about itself. They are stronger than anything this product would
be entitled to say on its behalf, and paraphrasing them would have softened
them - which is the direction a paraphrase always drifts when the paraphraser
would like the integration to happen.

Why writing an adapter today would mean inventing things
---------------------------------------------------------
The field names of the ``job`` object were not published. An adapter needs
them, so writing one means guessing them, and a guess here fails the way a
guess always fails on a foreign API: the request is refused upstream and the
error reads like the user's mistake. Pagination was likewise not published,
and the one listing endpoint that was tried did not answer inside sixty
seconds with roughly seventy-seven thousand records behind it - so even a
correct adapter would not have worked.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from station_api.workscan.authority import AuthorityLevel

#: The adapter's stable identifier. Never derived from input.
ADAPTER_ID: Final = "kibble"

ADAPTER_NAME: Final = "Kibble"

#: The origin the ADR recorded. Kept as **text in a record**, never as an
#: address: nothing in this package imports an HTTP client, no registry entry
#: is built from it and no code path turns it into a request. It is here so
#: that a reader can check the finding, and a test asserts it appears in no
#: outbound client module.
DECLARED_ORIGIN: Final = "https://flop-kibble.onrender.com"

#: When the verification below was performed, and by whom in the process
#: sense. Carried into every view, so the age of the claim is visible.
READ_ON: Final = "2026-09-04"

READ_BY: Final = "ADR-0007 1 kesif turu"


class AdapterSupport(StrEnum):
    """How far an external service has been taken.

    Three values and no fourth. There is deliberately no ``SUPPORTED``
    member: this build supports no third-party job board, and an enum that
    offered the word would invite a row to claim it.
    """

    #: A record exists. The contract is not established well enough to write
    #: an adapter, and none is written.
    SUPPORT_UNVERIFIED = "support_unverified"
    #: Looked at and ruled out. No row is in this state today.
    DECLINED = "declined"
    #: Named in a roadmap and not yet examined at all.
    UNEXAMINED = "unexamined"


class VerificationState(StrEnum):
    """Whether one line of the table was actually established."""

    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"


@dataclass(frozen=True, slots=True)
class AdapterFact:
    """One thing about the service, and whether anybody confirmed it."""

    key: str
    #: A Turkish sentence, safe to show, stating the fact or the gap.
    detail: str
    state: VerificationState


#: What the exploration confirmed. Each entry is something a person observed,
#: not something inferred from a name or a family resemblance.
VERIFIED_FACTS: tuple[AdapterFact, ...] = (
    AdapterFact(
        key="service_exists",
        detail="Servis calisiyor ve acilis sayfasi okunabildi.",
        state=VerificationState.VERIFIED,
    ),
    AdapterFact(
        key="read_endpoints_documented",
        detail=(
            "Dort okuma uc noktasi belgelenmis ve kimlik dogrulamasi "
            "istemiyor: /api/board, /api/stats, /api/score, /api/status."
        ),
        state=VerificationState.VERIFIED,
    ),
    AdapterFact(
        key="lifecycle",
        detail="Is yasam dongusu yayimlanmis: JOB -> CLAIM -> RESULT -> ATTEST.",
        state=VerificationState.VERIFIED,
    ),
    AdapterFact(
        key="stats_shape",
        detail="/api/stats yanitinin sekli gozlendi.",
        state=VerificationState.VERIFIED,
    ),
    AdapterFact(
        key="self_description",
        detail=(
            "Servis kendi acilis sayfasinda resmi kaynak olmadigini "
            "soyluyor; ifadesi oldugu gibi tasinir."
        ),
        state=VerificationState.VERIFIED,
    ),
)

#: What nobody could establish. This list is the reason there is no adapter,
#: and it is shown beside the list above rather than under a "details" fold.
UNVERIFIED_FACTS: tuple[AdapterFact, ...] = (
    AdapterFact(
        key="job_schema",
        detail=(
            "'job' nesnesinin alan adlari yayimlanmamis. Adapter yazmak bu "
            "adlari uydurmak demektir; uydurulmadi."
        ),
        state=VerificationState.NOT_VERIFIED,
    ),
    AdapterFact(
        key="pagination",
        detail=(
            "Sayfalama yok. Denenen listeleme uc noktasi altmis saniyede "
            "yanit vermedi; arkasinda yaklasik yetmis yedi bin kayit var."
        ),
        state=VerificationState.NOT_VERIFIED,
    ),
    AdapterFact(
        key="rate_limit",
        detail="Istek hizi siniri belgelenmemis.",
        state=VerificationState.NOT_VERIFIED,
    ),
    AdapterFact(
        key="terms",
        detail="Kullanim kosullari ve lisans bulunamadi; robots.txt 404 verdi.",
        state=VerificationState.NOT_VERIFIED,
    ),
    AdapterFact(
        key="operator",
        detail="Servisi kimin islettigi belirlenemedi.",
        state=VerificationState.NOT_VERIFIED,
    ),
)

#: The service's own sentence about what it is not. Quoted, in its own
#: language, because a translation of a disclaimer is a weaker disclaimer.
SELF_DESCRIPTION: Final = (
    "Kibble is not FLOP Network and not Technocore. It settles nothing."
)

#: The service's own sentence about what its score is.
SCORE_SELF_DESCRIPTION: Final = "Advisory IOU from the public tape. Nothing is paid."

#: Turkish rendering shown beside the quotations, so a reader who does not
#: read English still gets the disclaimer rather than only the number.
SELF_DESCRIPTION_TR: Final = (
    "Servis kendini soyle tarif ediyor: FLOP Network degil, Technocore degil "
    "ve hicbir seyi kesinlestirmiyor. Skorunu da 'kamuya acik kayittan "
    "cikarilmis, tavsiye niteliginde ve hicbir odeme yapilmayan' bir deger "
    "olarak tanimliyor."
)

#: What may never be said about a ``score`` or ``rank`` field from this or any
#: other third party. Shown with the record, not buried in a comment: the
#: charter forbids the claim (8.3, AC-18) and the service itself refuses it.
SCORE_CAVEAT: Final = (
    "Ucuncu tarafin 'score' veya 'rank' alani o tarafin kendi hesabidir. "
    "Station bu sayiyi kendi cumlesine bir olcut olarak katmaz ve onu bir "
    "odul, bir hak ya da bir guvenilirlik gostergesi diye sunmaz."
)

#: Always shown with the record, whatever else is on the screen. Not
#: conditional on anything: the record's age is a fact about every reading of
#: it, and a provenance line that only appears when something goes wrong is a
#: provenance line nobody ever sees (Package G's rule, ADR-0005 5.1).
TABLE_PROVENANCE: Final = (
    f"Bu kayit {READ_ON} tarihinde, {READ_BY} sirasinda yazildi: "
    f"{len(VERIFIED_FACTS)} madde dogrulandi, {len(UNVERIFIED_FACTS)} madde "
    "dogrulanamadi. Station bu servise hicbir istek gondermez ve sayfayi "
    "kendiliginden yeniden okumaz; kayit o tarihten sonra bayatlamis olabilir."
)


@dataclass(frozen=True, slots=True)
class AdapterRecord:
    """One external service, and how far this build has taken it."""

    id: str
    name: str
    support: AdapterSupport
    #: Community, and not negotiable: the content is a third party's own
    #: arithmetic over anonymous public writes.
    authority: AuthorityLevel
    declared_origin: str
    verified: tuple[AdapterFact, ...]
    unverified: tuple[AdapterFact, ...]
    self_description: str
    score_caveat: str
    provenance: str

    @property
    def adapter_written(self) -> bool:
        """Always false in this build, and structurally so.

        Derived from the support level rather than stored, so there is no
        field to flip: an adapter exists only when the support level says
        something this enum cannot currently say.
        """
        return False

    @property
    def contacted(self) -> bool:
        """Whether this build has ever made a request to the service.

        Also always false, and also derived. Nothing in this package imports
        an HTTP client; a test reads the syntax tree and asserts it.
        """
        return False


#: The complete set. One entry. Adding a second means a second review.
ADAPTERS: tuple[AdapterRecord, ...] = (
    AdapterRecord(
        id=ADAPTER_ID,
        name=ADAPTER_NAME,
        support=AdapterSupport.SUPPORT_UNVERIFIED,
        authority=AuthorityLevel.COMMUNITY,
        declared_origin=DECLARED_ORIGIN,
        verified=VERIFIED_FACTS,
        unverified=UNVERIFIED_FACTS,
        self_description=SELF_DESCRIPTION_TR,
        score_caveat=SCORE_CAVEAT,
        provenance=TABLE_PROVENANCE,
    ),
)

_BY_ID: dict[str, AdapterRecord] = {record.id: record for record in ADAPTERS}


def get_adapter(adapter_id: str) -> AdapterRecord:
    """Look up an adapter record. Raises ``KeyError`` for anything else."""
    return _BY_ID[adapter_id]


__all__ = [
    "ADAPTERS",
    "ADAPTER_ID",
    "ADAPTER_NAME",
    "DECLARED_ORIGIN",
    "READ_BY",
    "READ_ON",
    "SCORE_CAVEAT",
    "SCORE_SELF_DESCRIPTION",
    "SELF_DESCRIPTION",
    "SELF_DESCRIPTION_TR",
    "TABLE_PROVENANCE",
    "UNVERIFIED_FACTS",
    "VERIFIED_FACTS",
    "AdapterFact",
    "AdapterRecord",
    "AdapterSupport",
    "VerificationState",
    "get_adapter",
]
