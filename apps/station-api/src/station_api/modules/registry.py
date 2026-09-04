"""The closed set of project modules. Fixed at build time, never loaded.

Why a registry and not a directory move
---------------------------------------
The roadmap sentence "Proje 0 has been moved behind a module boundary" and the
task's own sentence "existing record identities and migration history must not
break" pull in opposite directions, and the exploration priced the physical
move: at least six tests break (``OUTBOUND_CLIENT_MODULES`` pinned the
``technocore/`` directory by name at the time, and pins the full source-root
relative path of every outbound client today; ``test_write_gate.py`` uses
literal module paths; three places audit the route set), and no behaviour is
bought with them. So ADR-0004 1 settles it: a module is a record here, the responsible
code stays where it is, and **Proje 0 is not moved** - it is represented.

What a record is allowed to claim
---------------------------------
Four things, and each one is checkable:

* which code owns it (``owners`` - dotted paths that a test proves exist);
* what it is for (``purpose``);
* which evidence each of its requirements is bound to
  (:class:`~station_api.modules.fields.EvidenceField`);
* whether this build can produce that evidence at all (``implemented``).

The fourth is the honest half. **Three** of Proje 0's nine charter outputs
cannot be produced by this product as built - ``profile_note_published``,
``lobby_greeting_sent`` and ``module_marked_complete`` - and one of those three
cannot be produced *ever* under the current policy: output 5 asks for a signed
greeting in the lobby, and the lobby is in ``DENIED_ROOMS`` (IMP-281, INV-05).
A registry that reported that requirement as merely "not done yet" would be
describing a queue; it is a refusal, and it says so.

No dynamic loading
------------------
There is no plugin path, no entry-point group, no import by name and no
evaluation of anything. ``MODULES`` is a tuple literal. A security test walks
this package's syntax tree and fails if a dynamic-loading construct appears in
it (charter ADR-017, AGENTS.md 2.9).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from station_api.modules.fields import EvidenceField


class ModuleRegistryError(KeyError):
    """An identifier that is not in the compile-time registry.

    A ``KeyError`` subclass, so the older assertion that an unregistered name
    "raises ``KeyError``" still holds, and a *named* exception, so a caller can
    turn it into a shown refusal instead of letting a bare ``KeyError`` become
    an armoured 500. The message is safe to show: it names no path, no input
    and no registry contents.

    ``KeyError.__str__`` reprs its argument (``"'...'"``), which would put
    stray quotes into a user-visible sentence, so it is overridden.
    """

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


class ModuleId(StrEnum):
    """Stable module identifiers. Never derived from user input."""

    PROJECT_ZERO = "project_zero"
    WORK_SCAN = "work_scan"
    AGENT_WORKSPACE = "agent_workspace"
    PROOF_WORKSPACE = "proof_workspace"


class ModuleState(StrEnum):
    """Whether the code behind a record is in this build.

    Two values on purpose. ``sections.ts`` proved the shape works: registering
    a target module keeps the intended layout visible in review, and the
    ``planned`` marker is what stops it being rendered as though it were a
    feature. An empty module pretending to be one is exactly what this
    application refuses to show.
    """

    #: The owning code is in this build and its requirements are evaluable.
    AVAILABLE = "available"
    #: Registered so the target layout stays reviewable. No code path exists.
    PLANNED = "planned"


@dataclass(frozen=True, slots=True)
class ModuleRequirement:
    """One thing a module has to establish, and what would establish it."""

    key: str
    #: A Turkish sentence, safe to show, that states the requirement.
    detail: str
    #: Which of the four fields carries the evidence for this requirement.
    evidence: EvidenceField
    #: The package or roadmap stage that delivers the evidence. A string
    #: because the roadmap has non-numeric stages ("2B", "H2").
    stage: str
    #: False when **no code path in this build can produce** the evidence. The
    #: check then reports ``not_implemented`` - never ``passed``, and never
    #: ``blocked``, which would blame the user for a product gap.
    implemented: bool


@dataclass(frozen=True, slots=True)
class ModuleRecord:
    """One module. A pointer at code that lives elsewhere, plus its contract."""

    id: ModuleId
    #: Turkish, diacritic-free, like every user-visible string in this product.
    name: str
    purpose: str
    state: ModuleState
    #: Dotted paths of the modules that already own this responsibility. They
    #: are **not** moved here; a test proves each one exists, so a record that
    #: outlives its code fails loudly instead of pointing at nothing.
    owners: tuple[str, ...]
    requirements: tuple[ModuleRequirement, ...]
    #: The package that opens a ``planned`` module. Empty for available ones.
    available_from: str = ""


#: Requirements that are not merely unbuilt but **refused by policy**. Naming
#: them separately means the difference survives: "nobody has written it yet"
#: and "this product will not do it" read identically in a status column, and
#: only one of them is a queue item.
POLICY_REFUSED_REQUIREMENTS: frozenset[str] = frozenset({"lobby_greeting_sent"})


#: Proje 0's completion outputs, verbatim from charter 7.2, in charter order.
_PROJECT_ZERO_REQUIREMENTS: tuple[ModuleRequirement, ...] = (
    ModuleRequirement(
        key="identity_local_only",
        detail=(
            "Kullanicinin yalniz kendisinde bulunan bir DID/seed cifti vardir; "
            "secret kasadan disari cikmaz."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="2",
        implemented=True,
    ),
    ModuleRequirement(
        key="recovery_paths",
        detail=(
            "Seed iki bagimsiz yolla korunur: makineye bagli DPAPI kasasi ve "
            "parolayla sifrelenmis tasinabilir .tcrec dosyasi."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="2",
        implemented=True,
    ),
    ModuleRequirement(
        key="restore_test_verified",
        detail="Recovery dosyasi restore-test ile dogrulanmistir.",
        evidence=EvidenceField.TEST_RESULT,
        stage="2",
        implemented=True,
    ),
    ModuleRequirement(
        key="profile_note_published",
        detail=(
            "DID profili/note kaydi kullanici onayiyla yayimlanir. Note lane "
            "bu surumde yoktur (ADR-0002 1); hicbir kod yolu bu kaniti uretemez."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H2",
        implemented=False,
    ),
    ModuleRequirement(
        key="lobby_greeting_sent",
        detail=(
            "Lobby'ye tek bir signed tanisma mesaji gonderilir. Bu urun "
            "lobby'ye yazmayi reddeder (DENIED_ROOMS, INV-05): eksik degil, "
            "politika geregi kapali."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="-",
        implemented=False,
    ),
    ModuleRequirement(
        key="writes_archived",
        detail=(
            "Her yazmanin canonical verisi, imzasi ve sunucu yaniti kanit "
            "defterinde arsivlenmistir."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="5",
        implemented=True,
    ),
    ModuleRequirement(
        key="evidence_levels_shown",
        detail=(
            "Dort guven seviyesi ayri ayri gosterilir; hicbiri tek bir yesil "
            "rozete indirgenmez."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="5",
        implemented=True,
    ),
    ModuleRequirement(
        key="module_marked_complete",
        detail=(
            "Proje 0 dashboard uzerinde tamamlandi olarak isaretlenir. Gorevler "
            "bolumu bu surumde kapali (ADR-0004 9); gorunur bir yuzey yok."
        ),
        evidence=EvidenceField.USER_ACCEPTANCE,
        stage="H1",
        implemented=False,
    ),
    ModuleRequirement(
        key="shared_security_core",
        detail=(
            "Sonraki moduller ayni guvenlik cekirdegini kullanir: kapi, kasa, "
            "giden istemciler ve kanit defteri kopyalanmaz, yeniden kullanilir."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="F",
        implemented=True,
    ),
)


#: The complete set. Adding a module means editing this tuple, which is a
#: reviewable change; nothing computes a record at runtime.
MODULES: tuple[ModuleRecord, ...] = (
    ModuleRecord(
        id=ModuleId.PROJECT_ZERO,
        name="Proje 0",
        purpose=(
            "Kullanicinin kendi kimligini kurmasi, korumasi ve ilk imzali "
            "yazmasini kanitlariyla birlikte arsivlemesi."
        ),
        state=ModuleState.AVAILABLE,
        owners=(
            "station_api.identity.service",
            "station_api.identity.write_gate",
            "station_api.recovery.format",
            "station_api.conformance.service",
            "station_api.technocore.service",
            "station_api.compose.service",
            "station_api.evidence.service",
        ),
        requirements=_PROJECT_ZERO_REQUIREMENTS,
    ),
    ModuleRecord(
        id=ModuleId.WORK_SCAN,
        name="Is Tara",
        purpose="Kapali kaynak registry'sinden salt okunur is/firsat taramasi.",
        state=ModuleState.PLANNED,
        owners=(),
        requirements=(),
        available_from="H1",
    ),
    ModuleRecord(
        id=ModuleId.AGENT_WORKSPACE,
        name="Agent Calisma Ortami",
        purpose="Kullanicinin baslattigi sinirli gorevlerin yurutulmesi.",
        state=ModuleState.PLANNED,
        owners=(),
        requirements=(),
        available_from="H2",
    ),
    ModuleRecord(
        id=ModuleId.PROOF_WORKSPACE,
        name="Kanit Calisma Alani",
        purpose="Artifact, hash, test kaniti ve eksikler; dis paylasim onayi.",
        state=ModuleState.PLANNED,
        owners=(),
        requirements=(),
        available_from="H3",
    ),
)

_BY_ID: dict[ModuleId, ModuleRecord] = {record.id: record for record in MODULES}


def get_module(module_id: ModuleId) -> ModuleRecord:
    """Look up a module, or refuse by name.

    Raises :class:`ModuleRegistryError` - a ``KeyError`` - for anything that is
    not in the compile-time set, including an unhashable value. The named type
    is what lets :mod:`station_api.tasks.service` answer an unknown module the
    same way it answers an unknown source: one shown refusal with a reason,
    rather than one refusal and one uncaught exception (ADR-0004 2).
    """
    try:
        return _BY_ID[module_id]
    except (KeyError, TypeError) as exc:
        raise ModuleRegistryError(
            "Kayitli olmayan bir modul kimligi istendi. Modul kumesi derleme "
            "zamaninda sabittir ve calisma zamaninda genisletilemez."
        ) from exc


def requirement_keys(module_id: ModuleId) -> tuple[str, ...]:
    """The requirement keys of one module, in charter order."""
    return tuple(requirement.key for requirement in get_module(module_id).requirements)


__all__ = [
    "MODULES",
    "POLICY_REFUSED_REQUIREMENTS",
    "ModuleId",
    "ModuleRecord",
    "ModuleRegistryError",
    "ModuleRequirement",
    "ModuleState",
    "get_module",
    "requirement_keys",
]
