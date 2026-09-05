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

The fourth was **always empty** until Package H3. F opened the field and never
filled it, and stated the emptiness rather than leaving it to be inferred -
the same rule that keeps ``external_anchor`` written as ``null`` instead of
omitted (ADR-0004 4).

H3 fills it, under the condition ADR-0009 1 sets: ``public_share`` accepts a
pointer **only** when that pointer is the identity of a real evidence record,
so the sentence "the proof was shared" always rests on a send that actually
happened. A hand-written string is refused by :class:`EvidenceRef`'s own
constructor.

``PUBLICATION_FIELDS`` stays at three. Moving ``public_share`` into it would
mean no task could ever be finished without publishing it externally, which
ADR-0004 4 rejected on purpose and ADR-0009 1 keeps rejecting.

:data:`UNFILLABLE_FIELDS` is empty as a result, and is written out as an empty
set rather than deleted. It is the oracle for "this release closes nothing",
and the four branches that consult it are the refusal machinery a later
package relies on the day it defines a fifth field it cannot fill. Those
branches are **driven** under a temporarily closed field rather than left to
rot unexecuted (ADR-0009 2) - an empty set nothing ever iterates is how a
guard stops being one without anybody noticing.

Nothing here is a claim about the evidence itself. An :class:`EvidenceRef` is
a *pointer plus a verdict about that pointer*: it carries ``verified``, which
the producer has to justify, precisely so that the existence of a row, a file
or a build output can never be mistaken for success on its own.
"""

from __future__ import annotations

import re
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
        "Kanitin bu makinenin disinda paylasilmasi. Alan doldurulabilir, "
        "fakat yalnizca gerceklesmis bir gonderimin kanit kaydi kimligiyle: "
        "elle yazilan bir dize kabul edilmez. Bu alan bir gorevin bitmesi icin "
        "aranmaz; yayimlamadan da bir gorev tamamlanabilir."
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

#: Fields no code path in this release can fill. **Empty since Package H3**,
#: and written out as an empty set rather than removed.
#:
#: Emptying it is the deliberate half of ADR-0009 1, exactly as emptying
#: ``UNPRODUCIBLE_STATES`` was the deliberate half of ADR-0008 3. The constant
#: stays because four branches consult it - the task gate, the task service's
#: row reader, the module completion check and the constructor below - and
#: those four branches *are* the refusal machinery. A package that defines a
#: fifth field it cannot fill edits this one line and gets all four refusals
#: back; deleting the constant would mean writing them again from memory.
#:
#: The branches are not left unexecuted. ``tests/security`` closes one
#: genuinely fillable field for the duration of a test and drives each of the
#: four, having first checked that the same path is *permitted* with nothing
#: closed - without that first half a function that refused everything would
#: pass the second half too (ADR-0009 2).
UNFILLABLE_FIELDS: frozenset[EvidenceField] = frozenset()

#: The number of characters in an evidence-record identity: ``uuid4().hex``.
EVIDENCE_RECORD_ID_CHARS = 32

#: The shape of that identity, written here rather than imported.
#:
#: This module is inside ``station_api.modules``, which
#: ``test_no_module_record_moved_code_into_the_registry_package`` forbids from
#: importing ``station_api.evidence`` at all - the registry holds records, not
#: responsibilities. So the *shape* is checked here and the *existence* of the
#: row is checked where a database is at hand, in
#: :meth:`station_api.tasks.service.TaskService.record_evidence`. Two
#: independent refusals, and neither is the whole claim alone: the shape would
#: admit any thirty-two hex characters, and the existence check sits behind a
#: service whose other callers would have to remember it.
_EVIDENCE_RECORD_ID_RE = re.compile(rf"\A[0-9a-f]{{{EVIDENCE_RECORD_ID_CHARS}}}\Z")


def is_evidence_record_id(value: str) -> bool:
    """Whether ``value`` has the shape an evidence record's id has.

    Lower-case hex, exactly thirty-two characters, nothing else.
    ``uuid.uuid4().hex`` produces nothing else either, so an upper-case
    spelling, a truncated id or a sentence somebody typed is refused rather
    than normalised - normalising a pointer is how a pointer to nothing
    acquires a plausible shape.
    """
    return _EVIDENCE_RECORD_ID_RE.fullmatch(value) is not None


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
        if self.field is EvidenceField.PUBLIC_SHARE and not is_evidence_record_id(
            self.ref_id
        ):
            # ADR-0009 1. The field is fillable, and this is the condition it
            # is fillable under: the pointer has to be an evidence record's own
            # identity, so "the proof was shared" always rests on a send that
            # actually happened. A sentence somebody typed has the wrong shape
            # and stops here - in the constructor, where every caller passes -
            # rather than at whichever caller remembered to check.
            raise EvidenceFieldError(
                "Dis paylasim yalnizca gerceklesmis bir gonderimin kanit "
                "kaydi kimligiyle isaretlenebilir; elle yazilan bir dize "
                "kabul edilmez."
            )
        if not self.source_version_id:
            raise EvidenceFieldError(
                "Kanit bir icerik surumune baglanmadan kaydedilemez."
            )


__all__ = [
    "EVIDENCE_RECORD_ID_CHARS",
    "FIELD_DETAIL",
    "PUBLICATION_FIELDS",
    "UNFILLABLE_FIELDS",
    "EvidenceField",
    "EvidenceFieldError",
    "EvidenceRef",
    "is_evidence_record_id",
]
