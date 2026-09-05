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


#: What Package H1 undertook to establish for the work-scan module, in the
#: order ADR-0007 argues them. The third is ``implemented=False`` and that is
#: the honest half again: a scan can propose work and this build cannot price
#: it, because there is no budget anywhere in the product yet (ADR-0007 8).
_WORK_SCAN_REQUIREMENTS: tuple[ModuleRequirement, ...] = (
    ModuleRequirement(
        key="scan_surface_closed",
        detail=(
            "Tarama yalnizca kapali bir adres registry'sinden okur, oda adi "
            "yazma yolunun politikasindan gecer ve zamanlayici yoktur."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H1",
        implemented=True,
    ),
    ModuleRequirement(
        key="candidate_carries_its_source",
        detail=(
            "Her aday birebir alinti ile oda, sira ve zaman referansini "
            "tasir; tasimayan aday uretilemez."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H1",
        implemented=True,
    ),
    ModuleRequirement(
        key="effort_budget_enforced",
        detail=(
            "Bir adayin calisma maliyeti olculur ve bir tavanla "
            "karsilastirilir. Paket H2 bir calisma tavani getirdi (arac "
            "cagrisi sayisi ve sure), fakat o tavan calismaya aittir: bir "
            "adayin maliyeti hala olculmuyor ve hicbir kod yolu bir aday "
            "tahminini tavanla karsilastirmiyor. Tahmin, tahmin olarak "
            "etiketlenir."
        ),
        evidence=EvidenceField.TEST_RESULT,
        stage="-",
        implemented=False,
    ),
)


#: What Package H2 undertook to establish for the agent working environment.
#:
#: One of the seven is ``implemented=False`` and it is the honest half.
#: ``run_test_result_recorded`` cannot be produced because running a check is
#: exactly the capability ADR-0008 1 closes - a run records what its plan said
#: would establish success and never a result, so the field reports
#: ``not_implemented`` and the task cannot reach ``ready_to_publish`` from a
#: run alone. It is deliberately **not** in
#: :data:`POLICY_REFUSED_REQUIREMENTS`: the lobby greeting is refused by a
#: policy this product intends to keep, while execution is closed by an
#: architecture decision a later package may revisit with real isolation.
#: Reporting the two identically would lose that difference, which is the
#: whole reason the separate list exists.
#:
#: The seventh, ``user_accepted_the_run_output``, was the second one until
#: Package H3. H2 wrote it ``implemented=False`` with stage ``H3`` because no
#: surface recorded a person's acceptance; H3 opened that route, so the flag
#: moved with the code rather than ahead of it (ADR-0009 8).
_AGENT_WORKSPACE_REQUIREMENTS: tuple[ModuleRequirement, ...] = (
    ModuleRequirement(
        key="execution_closed_and_stated",
        detail=(
            "Keyfi kod ve kabuk yurutmesi kapalidir ve bunun nedeni "
            "kullaniciya gorunur bir gerekce olarak sunulur: olculen "
            "izolasyon envanteri ve neden guvenilmedigi kayitlidir."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H2",
        implemented=True,
    ),
    ModuleRequirement(
        key="tool_registry_is_closed",
        detail=(
            "Araclar derleme zamaninda sabittir; agent kendisine arac "
            "ekleyemez ve kayitsiz bir kimlik gosterilebilir bir ret dondurur."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H2",
        implemented=True,
    ),
    ModuleRequirement(
        key="run_ceiling_enforced",
        detail=(
            "Her calisma bir tavan altinda kosar: arac cagrisi sayisi, duvar "
            "saati suresi ve eszamanlilik (=1). Tavan derleme zamaninda "
            "yazilir ve hicbir kod yolu onu degistirmez."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H2",
        implemented=True,
    ),
    ModuleRequirement(
        key="workspace_is_contained",
        detail=(
            "Her okuma ve yazma calisma alani icinde kalir: ad yeniden "
            "kurulur, yol cozulur ve kapsanma denetlenir, baglanti "
            "(symlink/junction) reddedilir ve arsiv acan bir yol hic yoktur."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H2",
        implemented=True,
    ),
    ModuleRequirement(
        key="activity_is_separate_from_the_chain",
        detail=(
            "Adim adim kayit ayri bir yalniz-ekleme tabloda kendi "
            "retention'i ile tutulur; audit zincirine yalnizca karar "
            "noktalari girer ve zincirin atifta bulundugu satir budanamaz."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H2",
        implemented=True,
    ),
    ModuleRequirement(
        key="run_test_result_recorded",
        detail=(
            "Calismanin urettigi ciktinin uzerinde bir denetim kosar ve "
            "sonucu kaydedilir. Bu surumde yurutme kapali oldugu icin hicbir "
            "kod yolu bu kaniti uretemez: plan basari olcutunu kaydeder, "
            "kosmaz, ve sonuc 'uygulanmadi' olarak raporlanir."
        ),
        evidence=EvidenceField.TEST_RESULT,
        stage="-",
        implemented=False,
    ),
    ModuleRequirement(
        key="user_accepted_the_run_output",
        detail=(
            "Kullanici ciktiyi acikca kabul eder. Kabul bir kisinin "
            "eylemidir ve Paket H3 onu kaydeden yuzeyi acti: kabul rotasi "
            "gorulen paket ozetine baglanir. Hicbir otomatik yol bu alani "
            "dolduramaz; kabul gecisin girdisidir, ciktisi degil."
        ),
        evidence=EvidenceField.USER_ACCEPTANCE,
        stage="H3",
        # Flipped by Package H3, which wrote the surface this requirement was
        # waiting for (ADR-0009 8). It is the same edit H1 made for
        # ``work_scan`` and H2 for ``agent_workspace``: the flag moves on the
        # commit that builds the thing, not before it.
        implemented=True,
    ),
)


#: What Package H3 undertook to establish for the proof workspace.
#:
#: Two of the nine are ``implemented=False`` and both are architectural
#: closures rather than queue items - the same distinction
#: ``run_test_result_recorded`` is written under, and for the same reason it
#: is deliberately **not** in :data:`POLICY_REFUSED_REQUIREMENTS`. The model
#: lane is closed (ADR-0008 2), so there is no second opinion to record and
#: presenting a run's own output as a third party's check would be the exact
#: lie ADR-0009 6 refuses; and arbitrary execution is closed (ADR-0008 1), so
#: there is no exit code to record and inventing one would be worse than
#: leaving the field empty (ADR-0009 7).
_PROOF_WORKSPACE_REQUIREMENTS: tuple[ModuleRequirement, ...] = (
    ModuleRequirement(
        key="artifact_set_is_hashed",
        detail=(
            "Her artifact kendi SHA-256 degerini tasir ve kume icin tek bir "
            "ozet uretilir; ozet kanonik JSON uzerinden hesaplanir, yani ayni "
            "dosya kumesi her kosuda ayni degeri verir."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H3",
        implemented=True,
    ),
    ModuleRequirement(
        key="hash_scope_is_stated",
        detail=(
            "Ozetin neyi gosterdigi yazilir: bir SHA-256 yalnizca dosyanin "
            "bayt bakimindan ayni kaldigini tanimlar. Icerigin dogru veya "
            "yararli oldugunu gostermez ve 'Kanit' basligi 'dogrulandi' diye "
            "okunmamalidir."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H3",
        implemented=True,
    ),
    ModuleRequirement(
        key="missing_pieces_are_named",
        detail=(
            "Eksik olan sey adiyla listelenir. Bir alanin bos olmasi, "
            "okuyucunun fark etmesine birakilmaz; her eksik kalem kendi "
            "cumlesiyle raporlanir."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H3",
        implemented=True,
    ),
    ModuleRequirement(
        key="bundle_is_never_written_to_a_path",
        detail=(
            "Paket hicbir yola yazilmaz; tarayiciya teslim edilir. Yeni bir "
            "dosya koku acilmaz ve arsiv uretilmez, bu yuzden yol asimi, "
            "baglanti ve uzerine yazma sorulari bu ozellikte hic dogmaz."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H3",
        implemented=True,
    ),
    ModuleRequirement(
        key="share_needs_a_single_use_approval",
        detail=(
            "Dis paylasim ayri ve tek kullanimlik bir onay ister. Onay paket "
            "ozetine baglidir: artifact degisirse ozet degisir ve eski onay "
            "duser."
        ),
        evidence=EvidenceField.TASK_OUTCOME,
        stage="H3",
        implemented=True,
    ),
    ModuleRequirement(
        key="user_acceptance_has_a_surface",
        detail=(
            "Kabul icin ayri bir rota vardir ve 'dogrulandi' yalnizca bir "
            "insanin eyleminden dogar. Kabul, yayima hazir gecisinin "
            "girdisidir; hicbir gecis kendi kabulunu yan etki olarak "
            "uretemez."
        ),
        evidence=EvidenceField.USER_ACCEPTANCE,
        stage="H3",
        implemented=True,
    ),
    ModuleRequirement(
        key="public_share_needs_a_real_send",
        detail=(
            "Dis paylasim alani yalnizca gerceklesmis bir gonderimin kanit "
            "kaydi kimligiyle doldurulabilir. Alan gorevin bitmesini "
            "engellemez: yayimlamadan da bir gorev tamamlanabilir."
        ),
        evidence=EvidenceField.PUBLIC_SHARE,
        stage="H3",
        implemented=True,
    ),
    ModuleRequirement(
        key="independent_check_recorded",
        detail=(
            "Bagimsiz kontrolun kim tarafindan ve hangi araci ile yapildigi "
            "kaydedilir. Bu surumde model yolu kapalidir (ADR-0008 2): "
            "ikinci bir model gorusu diye bir sey yoktur, ve ayni kosmanin "
            "kendi ciktisi ucuncu taraf onayi gibi sunulmaz. Alan "
            "'uygulanmadi' kalir ve nedenini soyler."
        ),
        evidence=EvidenceField.TEST_RESULT,
        stage="-",
        implemented=False,
    ),
    ModuleRequirement(
        key="real_exit_code_recorded",
        detail=(
            "Denetimin gercek cikis kodu kaydedilir. Keyfi yurutme kapali "
            "oldugu icin (ADR-0008 1) kosacak bir sey yoktur ve bir cikis "
            "kodu uretilmez. Plan basari olcutu ve yeniden uretme talimati "
            "metin olarak paketlenir; sayi uydurulmaz."
        ),
        evidence=EvidenceField.TEST_RESULT,
        stage="-",
        implemented=False,
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
        # Package H1 wrote the owning code, so the record stops saying it does
        # not exist. Flipping this is the deliberate half of opening a
        # ``planned`` module: the state, the owners and the requirements all
        # move together, and a reviewer sees one change rather than a record
        # that quietly disagrees with the tree beside it.
        state=ModuleState.AVAILABLE,
        owners=(
            "station_api.workscan.service",
            "station_api.workscan.client",
            "station_api.workscan.candidates",
            "station_api.workscan.targets",
        ),
        requirements=_WORK_SCAN_REQUIREMENTS,
    ),
    ModuleRecord(
        id=ModuleId.AGENT_WORKSPACE,
        name="Agent Calisma Ortami",
        purpose="Kullanicinin baslattigi sinirli gorevlerin yurutulmesi.",
        # Package H2 wrote the owning code, so the record stops saying it does
        # not exist. Flipping this is the deliberate half of opening a
        # ``planned`` module - the state, the owners and the requirements move
        # together, and a reviewer sees one change rather than a record that
        # quietly disagrees with the tree beside it. It is the same edit H1
        # made for ``work_scan``, and it carries the same honest half: two of
        # the seven requirements are ``implemented=False``.
        state=ModuleState.AVAILABLE,
        owners=(
            "station_api.agent.service",
            "station_api.agent.tools",
            "station_api.agent.budget",
            "station_api.agent.workspace",
            "station_api.agent.activity",
            "station_api.agent.isolation",
        ),
        requirements=_AGENT_WORKSPACE_REQUIREMENTS,
    ),
    ModuleRecord(
        id=ModuleId.PROOF_WORKSPACE,
        name="Kanit Calisma Alani",
        purpose="Artifact, hash, test kaniti ve eksikler; dis paylasim onayi.",
        # Package H3 wrote the owning code, so the record stops saying it does
        # not exist. The state, the owners, the requirements and
        # ``available_from`` move together, the way they did for ``work_scan``
        # (H1) and ``agent_workspace`` (H2), and the honest half travels with
        # them: two of the nine requirements are ``implemented=False`` because
        # the capabilities behind them are closed, not queued.
        #
        # This was the **last** ``planned`` record. The contract a planned
        # record has to satisfy is therefore no longer exercised by anything in
        # this tuple, and the test that used to loop over ``MODULES`` looking
        # for one would have gone quietly vacuous. It is now two assertions:
        # a named claim that nothing is planned any more, and the contract
        # itself driven over records built in the test (ADR-0009 2).
        state=ModuleState.AVAILABLE,
        owners=(
            "station_api.proof.service",
            "station_api.proof.bundle",
            "station_api.proof.approvals",
            "station_api.proof.language",
        ),
        requirements=_PROOF_WORKSPACE_REQUIREMENTS,
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
