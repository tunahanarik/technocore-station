"""Why arbitrary code and shell execution stay closed, written as data.

ADR-0008 1 decides this and the decision is uncomfortable enough to be worth
carrying in the code rather than only in a document: **a sandbox was measured
on this machine and the product still refuses to rely on it.**

The measurement is below, in :data:`ISOLATION_INVENTORY`, with each finding's
state kept apart from whether the product trusts it. Docker Desktop is
recorded as *present and not relied upon* rather than quietly dropped - the
same shape ADR-0005 2 used for streaming: an absence is stated, never
invented, and a presence that changes nothing says so.

Three reasons, and none of them is "nobody got round to it"
------------------------------------------------------------
1. The only real sandboxes measured here are Docker/WSL2. There is no
   AppContainer or Job Object code in this repository and no library for
   either, and "a separate folder plus :mod:`subprocess`" is the thing the
   product charter refuses outright. This package therefore contains no
   ``subprocess``, ``exec``, ``eval`` or ``os.system`` - the product source
   has never had one and H2 does not introduce one.
2. Docker is a **user installation, not the product's**. Station installs
   under ``%LOCALAPPDATA%``, asks for no administrator right and listens on
   loopback only. Making "Docker is installed, running, and you are in the
   ``docker-users`` group" a precondition would rewrite the product's own
   installation contract, which is an architecture decision and not something
   H2 may assume in passing.
3. It could not be **tested**. A path that starts a container cannot be
   verified in CI or on a clean machine; a locally present image is a fact
   about this machine, and ``docker pull`` is an outbound request this
   package is forbidden to make. Code that was never run is not code that
   was tested, so it is not shipped.

What stays open is everything that does not need isolation: reading approved
input, producing text, code, reports and patches inside the workspace, and
running **deterministic checkers** over them. That is a smaller product than
"an agent that runs your build", and it is the honest one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from station_api.tasks.states import TransitionVerdict

#: The single machine-readable reason. Named once, so the route, the activity
#: log, the audit chain and the UI all quote the same string.
EXECUTION_UNAVAILABLE_REASON: Final = "execution_unavailable"

#: Structural, not a setting: there is no code path in this package that runs
#: a command, and no configuration value that could open one.
ARBITRARY_EXECUTION_SUPPORTED: Literal[False] = False


class IsolationFacility(StrEnum):
    """The facilities the exploration actually looked for."""

    DOCKER_DESKTOP = "docker_desktop"
    WSL2 = "wsl2"
    WINDOWS_SANDBOX = "windows_sandbox"
    HYPER_V_MANAGEMENT = "hyper_v_management"
    LOCAL_ADMIN_RIGHTS = "local_admin_rights"
    WINDOWS_OPTIONAL_FEATURES = "windows_optional_features"


class MeasuredState(StrEnum):
    """What the measurement established. ``NOT_MEASURED`` is not ``ABSENT``.

    The distinction is the whole point of having three values: a facility
    nobody could look at is not a facility that is missing, and reporting the
    first as the second would be a measurement this product never made.
    """

    PRESENT = "present"
    ABSENT = "absent"
    NOT_MEASURED = "not_measured"


@dataclass(frozen=True, slots=True)
class IsolationFinding:
    """One measured fact, and - separately - whether it is relied upon."""

    facility: IsolationFacility
    measured: MeasuredState
    #: The date the exploration read it, as a plain string. This is a record
    #: of a measurement, not a live probe: nothing here runs at import time.
    measured_at: str
    detail: str
    #: Always false. A field rather than a comment, so "measured but not
    #: relied upon" is a value a test can read and a screen can show.
    relied_upon: Literal[False] = False


#: The inventory, exactly as ADR-0008 1 records it. Nothing was installed and
#: no container was started to produce it.
ISOLATION_INVENTORY: tuple[IsolationFinding, ...] = (
    IsolationFinding(
        facility=IsolationFacility.DOCKER_DESKTOP,
        measured=MeasuredState.PRESENT,
        measured_at="2026-09-05",
        detail=(
            "Docker Desktop 4.89.0 kurulu ve daemon cevap veriyor. Buna "
            "ragmen kullanilmiyor: Docker kullanicinin kurulumudur, urunun "
            "degil, ve konteyner calistiran bir yol temiz bir makinede veya "
            "CI'da dogrulanamaz."
        ),
    ),
    IsolationFinding(
        facility=IsolationFacility.WSL2,
        measured=MeasuredState.PRESENT,
        measured_at="2026-09-05",
        detail=(
            "WSL2 mevcut. Ayni gerekce: varligi olculdu, urunun kurulum "
            "sozlesmesinin parcasi degil."
        ),
    ),
    IsolationFinding(
        facility=IsolationFacility.WINDOWS_SANDBOX,
        measured=MeasuredState.ABSENT,
        measured_at="2026-09-05",
        detail="Windows Sandbox bu makinede yok.",
    ),
    IsolationFinding(
        facility=IsolationFacility.HYPER_V_MANAGEMENT,
        measured=MeasuredState.ABSENT,
        measured_at="2026-09-05",
        detail="Hyper-V yonetim yuzeyi bu makinede yok.",
    ),
    IsolationFinding(
        facility=IsolationFacility.LOCAL_ADMIN_RIGHTS,
        measured=MeasuredState.ABSENT,
        measured_at="2026-09-05",
        detail=(
            "Kullanici local admin degil. Station zaten admin yetkisi "
            "istemez ve kendiliginden istemeyecektir."
        ),
    ),
    IsolationFinding(
        facility=IsolationFacility.WINDOWS_OPTIONAL_FEATURES,
        measured=MeasuredState.NOT_MEASURED,
        measured_at="2026-09-05",
        detail=(
            "Ozellik durumlari okunamadi: sorgu admin yetkisi istiyor. "
            "Olculemeyen bir sey 'yok' diye yazilmaz."
        ),
    ),
)

#: The one sentence the surface shows beside a refusal to run a command.
EXECUTION_UNAVAILABLE_DETAIL = (
    "Keyfi kod ve kabuk yurutmesi bu surumde kapalidir. Guvenilir bir "
    "izolasyon urunun kendi kurulumunun parcasi degildir; olculen sandbox "
    "kullanicinin kurulumudur ve temiz bir makinede dogrulanamaz. Onaylanmis "
    "girdiyi okuma, calisma alaninda metin/kod/rapor/yama uretme ve "
    "deterministik dogrulayicilar calismaya devam eder."
)


def execution_verdict() -> TransitionVerdict:
    """The refusal, in the shape every other policy decision in this product uses.

    A :class:`~station_api.tasks.states.TransitionVerdict` rather than an
    exception, for the reason that type exists: the decision is a **value**
    that can be tested, logged, put in an activity row and shown, and the
    caller decides what a refusal costs. ADR-0008 1 asks for
    ``execution_unavailable`` to be a state reason rather than a silence, and
    this is what makes it one.
    """
    return TransitionVerdict(
        allowed=False,
        reason=EXECUTION_UNAVAILABLE_REASON,
        detail=EXECUTION_UNAVAILABLE_DETAIL,
    )


def measured_facilities() -> tuple[IsolationFinding, ...]:
    """The findings whose facility was actually found. Never a trust list."""
    return tuple(
        finding
        for finding in ISOLATION_INVENTORY
        if finding.measured is MeasuredState.PRESENT
    )


__all__ = [
    "ARBITRARY_EXECUTION_SUPPORTED",
    "EXECUTION_UNAVAILABLE_DETAIL",
    "EXECUTION_UNAVAILABLE_REASON",
    "ISOLATION_INVENTORY",
    "IsolationFacility",
    "IsolationFinding",
    "MeasuredState",
    "execution_verdict",
    "measured_facilities",
]
