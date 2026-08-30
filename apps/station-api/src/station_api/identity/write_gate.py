"""The central write gate.

Every outbound write to Technocore must pass through this one policy object.
Stage 4 will add the actual write endpoints; they will call ``evaluate`` and
refuse when it says no, so the rule lives in one place rather than being
re-implemented per endpoint.

Two honesty rules govern this module:

1. A check that is **not implemented yet** reports ``NOT_IMPLEMENTED``. It is
   never counted as passed. No check is in that state as of Stage 3; the
   state is kept because later stages will need it, and because a gate that
   cannot express "unbuilt" ends up expressing it as "passed".
2. There is no override flag, no environment escape hatch and no debug bypass.

Stage 2B made ``conformance_verified`` real, and Stage 3 did the same for
``manifest_current``. The two answer different questions and are deliberately
kept apart:

* ``conformance_verified`` - does *this build* reproduce the pinned reference
  commit's sweep, canonicalization and signature encoding?
* ``manifest_current`` - does the *live service*, checked just now by the
  user, still publish that same protocol contract?

A build can be perfectly conformant with a reference the server has since
moved away from. Collapsing the two into one check would hide exactly that
case, which is the one that produces a valid signature over bytes the server
will refuse.

``manifest_current`` reflects an in-process verdict that starts at
``never_checked`` on every launch. It is never restored from the database: a
successful check recorded yesterday says nothing about the protocol now.
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
    #: Whether a user-initiated live check found the official protocol
    #: contract unchanged. Same default, same reason. This is a *different*
    #: question from conformance: conformance asks "does this build match the
    #: pinned reference", manifest asks "does the live service still speak
    #: that protocol". Both must hold before anything is written.
    manifest_current: bool = False


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
            state=(CheckState.PASSED if state.manifest_current else CheckState.BLOCKED),
            detail="Resmi kaynaklar bu oturumda denetlenmis ve guncel olmali.",
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
