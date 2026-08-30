"""The central write gate.

Every outbound write to Technocore must pass through this one policy object.
Stage 4 will add the actual write endpoints; they will call ``evaluate`` and
refuse when it says no, so the rule lives in one place rather than being
re-implemented per endpoint.

Two honesty rules govern this module:

1. A check that is **not implemented yet** reports ``NOT_IMPLEMENTED``. It is
   never counted as passed. Manifest-drift is exactly that today, which is
   why ``allowed`` is False even for a fully recovered identity whose
   conformance self-test passes: nothing yet detects the live server moving
   off the pinned protocol, so writing would be a guess.
2. There is no override flag, no environment escape hatch and no debug bypass.

Stage 2B made ``conformance_verified`` real. It now reflects an actual run of
the shipped conformance vectors, not a placeholder. Note carefully what that
check does and does not assert: it says this build reproduces the *pinned
reference commit's* behaviour. It says nothing about whether the live
Technocore server still speaks that protocol - that is ``manifest_current``,
and it remains closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Roadmap stage identifiers. These are strings, not numbers, because the
# roadmap itself has a "2B" stage - an int cannot name it, and forcing one
# made the UI badge disagree with the explanatory text beside it.
IDENTITY_STAGE = "2"
CONFORMANCE_STAGE = "2B"
MANIFEST_STAGE = "3"


class CheckState(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"
    #: The requirement is real but its implementation lands in a later stage.
    #: Deliberately distinct from BLOCKED so the UI can tell a user problem
    #: from a product gap, and distinct from PASSED so it never fakes success.
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True)
class GateCheck:
    key: str
    state: CheckState
    detail: str
    #: The roadmap stage that delivers this requirement, e.g. "2", "2B", "3".
    stage: str

    @property
    def satisfied(self) -> bool:
        return self.state is CheckState.PASSED


@dataclass(frozen=True)
class WriteGateStatus:
    """Whether an external write may proceed, and precisely why not."""

    checks: tuple[GateCheck, ...]

    @property
    def allowed(self) -> bool:
        return all(check.satisfied for check in self.checks)

    @property
    def identity_ready(self) -> bool:
        """The Stage 2 half: identity exists, vault is present, recovery tested."""
        return all(check.satisfied for check in self.checks if check.stage == IDENTITY_STAGE)

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        return tuple(check.key for check in self.checks if not check.satisfied)


@dataclass(frozen=True)
class WriteGateInput:
    """Everything the gate needs. Computed by the identity service."""

    has_identity: bool
    identity_revoked: bool
    vault_present: bool
    recovery_verified: bool
    #: Whether the runtime conformance self-test passed. Defaults to False so
    #: a caller that forgets to supply it gets a closed gate, never an open
    #: one.
    conformance_verified: bool = False


def evaluate(state: WriteGateInput) -> WriteGateStatus:
    """Apply the policy. Pure function: easy to test, impossible to bypass."""
    not_revoked = state.has_identity and not state.identity_revoked

    checks = [
        GateCheck(
            key="identity_present",
            state=CheckState.PASSED if state.has_identity else CheckState.BLOCKED,
            detail="Aktif bir kimlik gerekli.",
            stage=IDENTITY_STAGE,
        ),
        GateCheck(
            key="identity_not_revoked",
            state=CheckState.PASSED if not_revoked else CheckState.BLOCKED,
            detail="Kimlik revoke edilmis olmamali.",
            stage=IDENTITY_STAGE,
        ),
        GateCheck(
            key="vault_present",
            state=CheckState.PASSED if state.vault_present else CheckState.BLOCKED,
            detail="Secret kasasi bulunmali.",
            stage=IDENTITY_STAGE,
        ),
        GateCheck(
            key="recovery_verified",
            state=CheckState.PASSED if state.recovery_verified else CheckState.BLOCKED,
            detail="Recovery restore-test ile dogrulanmis olmali.",
            stage=IDENTITY_STAGE,
        ),
        GateCheck(
            key="conformance_verified",
            state=(
                CheckState.PASSED if state.conformance_verified else CheckState.BLOCKED
            ),
            detail="Sweep/canonical/imza uygunlugu self-test ile dogrulanmali.",
            stage=CONFORMANCE_STAGE,
        ),
        GateCheck(
            key="manifest_current",
            state=CheckState.NOT_IMPLEMENTED,
            detail="Resmi manifest surukleme kontrolu Asama 3 ile gelir.",
            stage=MANIFEST_STAGE,
        ),
    ]
    return WriteGateStatus(checks=tuple(checks))


__all__ = [
    "CONFORMANCE_STAGE",
    "IDENTITY_STAGE",
    "MANIFEST_STAGE",
    "CheckState",
    "GateCheck",
    "WriteGateInput",
    "WriteGateStatus",
    "evaluate",
]
