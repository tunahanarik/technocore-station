"""Whether a module's requirements are met. One pure function, no second gate.

ADR-0004 2 forbids a second gate, and this is not one: it does not decide
whether anything may leave the machine. It follows ``write_gate.evaluate``'s
*shape* - a frozen input, a pure function, a status object whose ``complete``
is derived rather than stored - and it reuses that module's
:class:`~station_api.identity.write_gate.CheckState` rather than declaring a
parallel three-valued enum that would drift from it.

The three states carry the same meanings they carry there, and the third is
the reason this file exists:

``passed``           the requirement's evidence was supplied **and verified**,
                     against the content version the task is bound to.
``blocked``          the requirement is real and evaluable, and its evidence is
                     missing, unverified, or bound to different content.
``not_implemented``  no code path in this build can produce that evidence.
                     Never counted as passed
                     (``test_unimplemented_requirements_are_never_counted_as_passed``).

The rule the whole file exists for is in :func:`_check`: a reference that
merely *exists* produces ``blocked``. Presence of a result row, a file or a
build output is not success; the reference has to say it was checked, and
``EvidenceRef.verified`` is where the producer has to say it.

The ``UNFILLABLE_FIELDS`` half of that first condition is not taken by any
field in this build - the set is empty since Package H3 - and it stays because
it is the refusal a later closed field would rely on. It is driven under a
temporarily closed field rather than left unexecuted (ADR-0009 2). The other
half, ``not requirement.implemented``, is very much live: two of the proof
workspace's nine requirements and one of the agent workspace's seven report
``not_implemented`` because the capability behind them is closed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from station_api.identity.write_gate import CheckState
from station_api.modules.fields import UNFILLABLE_FIELDS, EvidenceField, EvidenceRef
from station_api.modules.registry import (
    POLICY_REFUSED_REQUIREMENTS,
    ModuleRecord,
    ModuleRequirement,
)


@dataclass(frozen=True, slots=True)
class ModuleCheck:
    """One requirement, its verdict, and what would change the verdict."""

    key: str
    state: CheckState
    detail: str
    #: Which of the four fields this requirement's evidence belongs to.
    field: EvidenceField
    #: The package or stage that delivers the evidence.
    stage: str
    #: The evidence that was actually consulted, or "" when none was.
    ref_id: str = ""
    #: True when the requirement is refused by policy rather than unbuilt.
    policy_refused: bool = False

    @property
    def satisfied(self) -> bool:
        return self.state is CheckState.PASSED


@dataclass(frozen=True, slots=True)
class ModuleCompletion:
    """A module's requirements and their verdicts. ``complete`` is derived."""

    module_id: str
    checks: tuple[ModuleCheck, ...]

    @property
    def complete(self) -> bool:
        """Every requirement passed.

        False while any check is ``not_implemented``, exactly as
        ``WriteGateStatus.allowed`` is: an unbuilt requirement is not a
        satisfied one, and a module that reported itself complete because a
        requirement had no implementation would be the clearest possible
        example of the mistake this product is about.
        """
        return bool(self.checks) and all(check.satisfied for check in self.checks)

    @property
    def blocking_keys(self) -> tuple[str, ...]:
        return tuple(
            check.key for check in self.checks if check.state is CheckState.BLOCKED
        )

    @property
    def not_implemented_keys(self) -> tuple[str, ...]:
        return tuple(
            check.key
            for check in self.checks
            if check.state is CheckState.NOT_IMPLEMENTED
        )

    @property
    def policy_refused_keys(self) -> tuple[str, ...]:
        return tuple(check.key for check in self.checks if check.policy_refused)


def _index(refs: Iterable[EvidenceRef]) -> Mapping[EvidenceField, EvidenceRef]:
    """Latest reference per field. At most one field is consulted per check."""
    return {ref.field: ref for ref in refs}


def _check(
    requirement: ModuleRequirement,
    *,
    refs: Mapping[EvidenceField, EvidenceRef],
    source_version_id: str,
) -> ModuleCheck:
    policy_refused = requirement.key in POLICY_REFUSED_REQUIREMENTS

    if not requirement.implemented or requirement.evidence in UNFILLABLE_FIELDS:
        return ModuleCheck(
            key=requirement.key,
            state=CheckState.NOT_IMPLEMENTED,
            detail=requirement.detail,
            field=requirement.evidence,
            stage=requirement.stage,
            policy_refused=policy_refused,
        )

    ref = refs.get(requirement.evidence)
    if ref is None:
        return ModuleCheck(
            key=requirement.key,
            state=CheckState.BLOCKED,
            detail=f"{requirement.detail} Bu gereksinim icin kanit yok.",
            field=requirement.evidence,
            stage=requirement.stage,
        )

    if ref.source_version_id != source_version_id:
        # ADR-0004 5. The content moved; this evidence was produced for the
        # old bytes. Reporting it as satisfying the new ones would be reading
        # a stale verdict as a current one - the mistake ``verdict_id``
        # already exists to prevent on the protocol side.
        return ModuleCheck(
            key=requirement.key,
            state=CheckState.BLOCKED,
            detail=(
                f"{requirement.detail} Eldeki kanit baska bir icerik surumune "
                "ait; icerik degistiginde eski kanit eslesmez."
            ),
            field=requirement.evidence,
            stage=requirement.stage,
            ref_id=ref.ref_id,
        )

    if not ref.verified:
        # The rule this module exists for: a record that is merely there is
        # not a pass. Something has to have checked it.
        return ModuleCheck(
            key=requirement.key,
            state=CheckState.BLOCKED,
            detail=(
                f"{requirement.detail} Kanit kaydi var fakat dogrulanmadi; "
                "bir kaydin varligi tek basina basari degildir."
            ),
            field=requirement.evidence,
            stage=requirement.stage,
            ref_id=ref.ref_id,
        )

    return ModuleCheck(
        key=requirement.key,
        state=CheckState.PASSED,
        detail=ref.detail or requirement.detail,
        field=requirement.evidence,
        stage=requirement.stage,
        ref_id=ref.ref_id,
    )


def evaluate_module(
    record: ModuleRecord,
    *,
    refs: Iterable[EvidenceRef] = (),
    source_version_id: str,
) -> ModuleCompletion:
    """Apply the policy. Pure function: easy to test, impossible to bypass."""
    indexed = _index(refs)
    return ModuleCompletion(
        module_id=record.id.value,
        checks=tuple(
            _check(
                requirement, refs=indexed, source_version_id=source_version_id
            )
            for requirement in record.requirements
        ),
    )


__all__ = ["ModuleCheck", "ModuleCompletion", "evaluate_module"]
