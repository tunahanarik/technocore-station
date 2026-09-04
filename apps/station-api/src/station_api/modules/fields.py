"""The four fields a result is recorded in, and why they are never summed.

ADR-0004 4. Task success, test result, user acceptance and public sharing are
**four separate fields**. They are not folded into one boolean, one "done"
flag or one percentage, for the same reason ``EvidenceRecord``'s four trust
levels are not: each answers a different question, and a reader who is handed
their conjunction cannot recover which of them was actually established.

* ``task_outcome``    the work itself produced what it said it would.
* ``test_result``     a check ran over that output and reported a verdict.
* ``user_acceptance`` a person looked at it and accepted it.
* ``public_share``    the proof was shared outside this machine.

The fourth is **always empty in this release**. External sharing is Package
H3's subject and it asks for its own single-use consent there; F opens the
field and never fills it (ADR-0004 4). A field that is defined but unfillable
is stated as unfillable rather than left looking available - the same rule
that keeps ``external_anchor`` written as ``null`` instead of omitted.

Nothing here is a claim about the evidence itself. An :class:`EvidenceRef` is
a *pointer plus a verdict about that pointer*: it carries ``verified``, which
the producer has to justify, precisely so that the existence of a row, a file
or a build output can never be mistaken for success on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EvidenceField(StrEnum):
    """One of the four, and never a fifth."""

    TASK_OUTCOME = "task_outcome"
    TEST_RESULT = "test_result"
    USER_ACCEPTANCE = "user_acceptance"
    PUBLIC_SHARE = "public_share"


#: One Turkish sentence per field, safe to show. None of them claims more than
#: the field establishes.
FIELD_DETAIL: dict[EvidenceField, str] = {
    EvidenceField.TASK_OUTCOME: (
        "Gorevin kendi ciktisi. Bir ciktinin var olmasi tek basina basari "
        "degildir; kayit, uretilen seyin denetlenmis oldugunu soylemek zorunda."
    ),
    EvidenceField.TEST_RESULT: (
        "Ciktinin uzerinde kosan denetimin sonucu. Kosmamis bir denetim "
        "'gecti' degil, 'uygulanmadi' olarak raporlanir."
    ),
    EvidenceField.USER_ACCEPTANCE: (
        "Kullanicinin acik kabulu. Otomatik hicbir yol bu alani dolduramaz; "
        "kabul bir kisinin eylemidir."
    ),
    EvidenceField.PUBLIC_SHARE: (
        "Kanitin bu makinenin disinda paylasilmasi. Bu surumde alan daima "
        "bostur: dis paylasim Paket H3'un konusudur ve orada ayri, tek "
        "kullanimlik bir onay ister."
    ),
}

#: The three fields that decide whether a task's own result is complete.
#:
#: ``public_share`` is deliberately absent. It is not "an optional check that
#: may be skipped": it is a *different* question - whether the finished proof
#: left this machine - and making it a precondition for finishing the work
#: would mean no task could ever be complete without publishing it, which is
#: the opposite of what this product wants to be true.
PUBLICATION_FIELDS: frozenset[EvidenceField] = frozenset(
    {
        EvidenceField.TASK_OUTCOME,
        EvidenceField.TEST_RESULT,
        EvidenceField.USER_ACCEPTANCE,
    }
)

#: Fields no code path in this release can fill. Named so that opening one is
#: a deliberate edit here rather than an accident somewhere else.
UNFILLABLE_FIELDS: frozenset[EvidenceField] = frozenset({EvidenceField.PUBLIC_SHARE})


class EvidenceFieldError(Exception):
    """A field was used in a way this release does not permit."""


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """A pointer at one piece of evidence, and what was established about it.

    ``verified`` is the load-bearing field and it has no default. A caller has
    to state whether the thing it points at was actually checked, because the
    alternative - inferring success from "the row is there" - is the failure
    this whole model exists to refuse (ADR-0004 4).

    ``source_version_id`` binds the evidence to the exact content version it
    was produced for. When the content changes the identity changes, and this
    reference stops matching: old evidence is not re-used for new content
    (ADR-0004 5).
    """

    field: EvidenceField
    #: What the evidence is: an evidence-record id, a test-run id, an audit
    #: subject. A public identifier; never a capability and never a secret.
    ref_id: str
    #: Whether the pointed-at evidence was *checked*, not merely found.
    verified: bool
    #: The content version this evidence was produced against.
    source_version_id: str
    #: One safe sentence about what was checked.
    detail: str = ""

    def __post_init__(self) -> None:
        if self.field in UNFILLABLE_FIELDS:
            raise EvidenceFieldError(
                f"'{self.field.value}' alani bu surumde doldurulamaz; "
                f"{FIELD_DETAIL[self.field]}"
            )
        if not self.ref_id:
            raise EvidenceFieldError("Kanit isaretcisi bos olamaz.")
        if not self.source_version_id:
            raise EvidenceFieldError(
                "Kanit bir icerik surumune baglanmadan kaydedilemez."
            )


__all__ = [
    "FIELD_DETAIL",
    "PUBLICATION_FIELDS",
    "UNFILLABLE_FIELDS",
    "EvidenceField",
    "EvidenceFieldError",
    "EvidenceRef",
]
