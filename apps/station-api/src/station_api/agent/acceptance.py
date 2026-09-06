"""The closed acceptance-condition registry: how a plan says what "worked" means.

The seventh compile-time registry in this product, and the one that finally
lets a task finish.

===============================================  ==========================
:mod:`station_api.technocore.sources`            public document read
:mod:`station_api.technocore.write_targets`      explicit signed write
:mod:`station_api.technocore.evidence_targets`   evidence read
:mod:`station_api.workscan.targets`              work scan read
:mod:`station_api.opencode.registry`             provider endpoints + models
:mod:`station_api.agent.tools`                   agent tool schema
this module                                      **acceptance conditions**
===============================================  ==========================

What changed, and what deliberately did not
-------------------------------------------
Until this module existed a plan's ``test_condition`` was a **sentence**: it
was recorded, it was shown, and nothing ever looked at it. The run therefore
reported ``not_implemented`` for its test field always, no ``test_result``
evidence was ever written, and ``ready_to_publish`` was unreachable by
construction. That was honest, and it also meant the product could not finish
a single task.

The thing that was closed is **arbitrary execution** (ADR-0008 1), and it
stays closed: nothing here starts a process, reads a command or interprets a
string as code, and ``test_condition`` is *still* never run. What this module
adds is the other half - a small, closed set of conditions a machine can
actually decide by reading bytes that are already on disk. The same three
deterministic checkers the tool registry has always carried do the same kind
of work; they simply had no way of adding up to a verdict about the task.

So the rule is unchanged in the form that matters:

* free text is never executed. A condition is a **registry member** plus
  typed arguments, exactly like a tool call;
* the conditions are fixed at import in a tuple literal, and nothing computes
  one at runtime;
* a condition names a file by a bare name and nothing else. There is no
  ``path`` and no ``url`` parameter here for the same reason there is none in
  :mod:`station_api.agent.tools`, and the workspace re-derives every name
  through its own sanitiser before a byte is read.

Why the parameters are the tool registry's types
-------------------------------------------------
:class:`~station_api.agent.tools.ToolParam` and
:func:`~station_api.agent.tools.bind_params` are imported rather than copied.
Two validators that agree today is the duplication ADR-0004 2 named, and the
most expensive place to have it is the one that decides whether a task may be
called finished: a file-name rule that drifted between "what a tool may write"
and "what an acceptance condition may read" would let a plan promise a check
of something the run could never have produced.

A verdict is bound to the bytes it was computed from
-----------------------------------------------------
:func:`evaluate` reads the workspace as it stands **now**. It is never cached
and never stored, so a task whose output changed after the check ran does not
keep yesterday's verdict: the run re-derives it, and the evidence reference
the runner wrote is separately invalidated by the task service's output
binding. Two independent mechanisms, because a stale pass is the single most
expensive wrong answer this file could give.

``not_implemented`` did not disappear
--------------------------------------
It is still what a plan with no conditions reports, and it still carries a
reason. A plan whose author wrote only a sentence has not been checked, and
saying "not implemented" about it is the same true statement it always was -
it is simply no longer the *only* thing this product can say.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from station_api.agent.errors import ToolArgumentError, ToolRegistryError, WorkspaceError
from station_api.agent.tools import (
    ToolArgument,
    ToolParam,
    ToolParamType,
    argument_map,
    bind_params,
)
from station_api.agent.workspace import digest_of, list_files, read_text

#: Most conditions one plan may carry. A plan that needs more than this is a
#: plan whose success criterion nobody can read in one screen.
MAX_ACCEPTANCE_CONDITIONS = 8

#: Most keys one ``artifact_has_json_keys`` condition may name.
MAX_REQUIRED_KEYS = 24

#: Longest key list, before parsing. A bound on the text, not on the meaning.
MAX_KEY_LIST_CHARS = 500


class AcceptanceKind(StrEnum):
    """Every condition this build can decide - five - and never a sixth at runtime.

    Each one is answerable by reading files this task's own run produced. None
    of them runs anything, and none of them can be pointed outside the task's
    workspace.
    """

    #: The named file is in the workspace at all.
    ARTIFACT_EXISTS = "artifact_exists"
    #: The named file parses as JSON.
    ARTIFACT_IS_JSON = "artifact_is_json"
    #: The named file is a JSON **object** carrying every named top-level key.
    #: This build's "matches a schema": a shape check, deliberately smaller
    #: than JSON Schema, because a full validator is a dependency and a
    #: dependency here would be a new library deciding whether work is done.
    ARTIFACT_HAS_JSON_KEYS = "artifact_has_json_keys"
    #: The named file contains the given text.
    ARTIFACT_CONTAINS = "artifact_contains"
    #: The named file hashes to the given digest.
    ARTIFACT_DIGEST_IS = "artifact_digest_is"


class AcceptanceState(StrEnum):
    """What a plan's success criterion established. Three values, kept apart.

    ``NOT_IMPLEMENTED`` is not a quiet ``FAILED`` and not a quiet ``PASSED``.
    It means nobody wrote a condition a machine can decide, which is a
    different situation from a condition that was decided and came out false -
    one of them is a gap in the plan, the other is a gap in the output.
    """

    PASSED = "passed"
    FAILED = "failed"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    """One condition kind: what it asks, and the arguments it needs to ask it."""

    kind: AcceptanceKind
    purpose: str
    params: tuple[ToolParam, ...]


_NAME_PARAM = ToolParam(
    name="name",
    type=ToolParamType.FILE_NAME,
    required=True,
    detail="Denetlenecek calisma alani dosyasinin sade adi.",
)


#: The complete set. Adding a condition means editing this tuple, which is a
#: reviewable change; nothing computes a record at runtime.
ACCEPTANCE_CHECKS: tuple[AcceptanceCheck, ...] = (
    AcceptanceCheck(
        kind=AcceptanceKind.ARTIFACT_EXISTS,
        purpose=(
            "Adi verilen dosyanin calisma alaninda bulunup bulunmadigini "
            "soyler. Dosyanin varligi tek basina isin dogru yapildigi "
            "anlamina gelmez; plan bunu bir kosul olarak yazdigi icin olculur."
        ),
        params=(_NAME_PARAM,),
    ),
    AcceptanceCheck(
        kind=AcceptanceKind.ARTIFACT_IS_JSON,
        purpose=(
            "Adi verilen dosyanin gecerli bir JSON belgesi olup olmadigini "
            "soyler. Ayni girdi her kosuda ayni sonucu verir."
        ),
        params=(_NAME_PARAM,),
    ),
    AcceptanceCheck(
        kind=AcceptanceKind.ARTIFACT_HAS_JSON_KEYS,
        purpose=(
            "Adi verilen dosyanin bir JSON nesnesi oldugunu ve istenen ust "
            "duzey anahtarlarin hepsini tasidigini soyler. Bu bir sema "
            "dogrulayicisi degildir: yalnizca anahtarlarin varligina bakar."
        ),
        params=(
            _NAME_PARAM,
            ToolParam(
                name="keys",
                type=ToolParamType.TEXT,
                required=True,
                detail=(
                    "Virgulle ayrilmis ust duzey anahtar adlari, en cok "
                    f"{MAX_REQUIRED_KEYS} tane."
                ),
            ),
        ),
    ),
    AcceptanceCheck(
        kind=AcceptanceKind.ARTIFACT_CONTAINS,
        purpose=(
            "Adi verilen dosyanin istenen metni icerip icermedigini soyler. "
            "Metin aranir, yorumlanmaz."
        ),
        params=(
            _NAME_PARAM,
            ToolParam(
                name="text",
                type=ToolParamType.TEXT,
                required=True,
                detail="Dosyanin icermesi gereken metin.",
            ),
        ),
    ),
    AcceptanceCheck(
        kind=AcceptanceKind.ARTIFACT_DIGEST_IS,
        purpose=(
            "Adi verilen dosyanin SHA-256 ozetini beklenen degerle "
            "karsilastirir. Uyusmazlik gosterilir, sessizce gecilmez."
        ),
        params=(
            _NAME_PARAM,
            ToolParam(
                name="digest",
                type=ToolParamType.DIGEST,
                required=True,
                detail="Beklenen 64 karakterlik kucuk harf hex ozet.",
            ),
        ),
    ),
)

_BY_KIND: dict[AcceptanceKind, AcceptanceCheck] = {
    check.kind: check for check in ACCEPTANCE_CHECKS
}


def resolve_check(raw: str) -> AcceptanceCheck:
    """Turn a caller-supplied string into a registered condition, or refuse it.

    A **shown** refusal with a reason, exactly as
    :func:`station_api.agent.tools.resolve_tool` gives one: an unregistered
    condition name is an answer the user can read, not a ``KeyError`` that
    becomes an armoured 500.
    """
    try:
        kind = AcceptanceKind(raw)
    except ValueError as exc:
        raise ToolRegistryError(
            "Kayitli olmayan bir kabul kosulu istendi. Kosul kumesi derleme "
            "zamaninda sabittir; calisma zamaninda genisletilemez ve serbest "
            "metin bir kosul olarak kosulmaz.",
            reason="acceptance_condition_unknown",
        ) from exc
    return _BY_KIND[kind]


@dataclass(frozen=True, slots=True)
class AcceptanceCondition:
    """One validated condition, ready to be written into a plan."""

    kind: AcceptanceKind
    arguments: tuple[ToolArgument, ...]

    @property
    def argument_map(self) -> dict[str, str]:
        return argument_map(self.arguments)

    @property
    def label(self) -> str:
        """One safe sentence naming the condition and its operands."""
        joined = ", ".join(
            f"{name}={value}" for name, value in sorted(self.argument_map.items())
        )
        return f"{self.kind.value}({joined})"


def bind_condition(raw_kind: str, raw_arguments: dict[str, str]) -> AcceptanceCondition:
    """Resolve one condition and validate its arguments against the registry."""
    check = resolve_check(raw_kind)
    bound = bind_params(check.params, raw_arguments, owner=check.kind.value)
    condition = AcceptanceCondition(kind=check.kind, arguments=bound)
    if check.kind is AcceptanceKind.ARTIFACT_HAS_JSON_KEYS:
        # Parsed here rather than at evaluation time, so a key list nobody can
        # read is a refusal the plan's author sees *while planning* - the same
        # rule the tool registry follows, and the reason a recorded plan is
        # meaningful at all.
        parse_keys(condition.argument_map["keys"])
    return condition


def parse_keys(raw: str) -> tuple[str, ...]:
    """Split a comma-separated key list into bare key names, or refuse it.

    Bounded, de-duplicated, order-preserving. A key is text a plan's author
    typed; it is compared for equality against a JSON object's own keys and
    never used as anything else, so the only rules are that it is non-empty,
    that there are not too many of them and that the list is not longer than a
    person would write.
    """
    if len(raw) > MAX_KEY_LIST_CHARS:
        raise ToolArgumentError(
            f"Anahtar listesi en cok {MAX_KEY_LIST_CHARS} karakter olabilir; "
            "liste kisaltilmaz, reddedilir.",
            reason="acceptance_key_list_too_long",
        )
    keys = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    if not keys:
        raise ToolArgumentError(
            "Anahtar listesi bos olamaz.", reason="acceptance_key_list_empty"
        )
    if len(keys) > MAX_REQUIRED_KEYS:
        raise ToolArgumentError(
            f"Bir kosul en cok {MAX_REQUIRED_KEYS} anahtar isteyebilir.",
            reason="acceptance_too_many_keys",
        )
    return keys


@dataclass(frozen=True, slots=True)
class ConditionResult:
    """One condition, and what reading the workspace established about it."""

    kind: AcceptanceKind
    label: str
    satisfied: bool
    detail: str


@dataclass(frozen=True, slots=True)
class AcceptanceOutcome:
    """The verdict over one plan's conditions. Never a bare boolean.

    ``state`` is derived from :attr:`results` as a set property rather than as
    ``all(...)``: an empty ``all()`` is ``True``, and the one place in this
    product where a vacuous truth is most expensive is a test result. A plan
    with no conditions is :attr:`AcceptanceState.NOT_IMPLEMENTED`, which is
    what :func:`evaluate` builds and what this class refuses to turn into a
    pass.
    """

    state: AcceptanceState
    detail: str
    results: tuple[ConditionResult, ...] = ()

    @property
    def passed(self) -> bool:
        return self.state is AcceptanceState.PASSED

    @property
    def failing_labels(self) -> tuple[str, ...]:
        return tuple(item.label for item in self.results if not item.satisfied)


NOT_IMPLEMENTED_DETAIL = (
    "Test sonucu uygulanmadi: bu plan makinece degerlendirilebilir bir kabul "
    "kosulu yazmadi. Plan yalnizca bir cumle kaydetti ve cumle kosulmaz, bu "
    "yuzden kaydedilmis bir sonuc yoktur ve gorev yayima hazir sayilamaz."
)

PASSED_DETAIL = (
    "Kabul kosullarinin tamami calisma alanindaki mevcut baytlar uzerinde "
    "deterministik olarak dogrulandi. Bu bir kabuk komutunun ciktisi degil, "
    "dosyalarin okunmasiyla verilen bir hukumdur."
)

FAILED_DETAIL = "En az bir kabul kosulu saglanmadi; ayrinti kosul basina asagidadir."


#: The verdict for a plan that wrote no machine-checkable condition. A named
#: constant so a caller with nothing to read does not have to invent a path
#: just to be told there is nothing to decide.
NOT_IMPLEMENTED_OUTCOME = AcceptanceOutcome(
    state=AcceptanceState.NOT_IMPLEMENTED, detail=NOT_IMPLEMENTED_DETAIL
)


def evaluate(
    conditions: Sequence[AcceptanceCondition], directory: Path
) -> AcceptanceOutcome:
    """Decide every condition against the workspace as it stands right now.

    Reads and nothing else: no file is created, moved, removed or rewritten,
    and no process is started. A condition whose file is missing or unreadable
    is **not satisfied** rather than an exception - a check that could not be
    made is not a check that passed, and the reason travels with the result.
    """
    if not conditions:
        return NOT_IMPLEMENTED_OUTCOME

    results = tuple(_decide(condition, directory) for condition in conditions)
    satisfied = frozenset(index for index, item in enumerate(results) if item.satisfied)
    state = (
        AcceptanceState.PASSED
        if satisfied == frozenset(range(len(results)))
        else AcceptanceState.FAILED
    )
    return AcceptanceOutcome(
        state=state,
        detail=PASSED_DETAIL if state is AcceptanceState.PASSED else FAILED_DETAIL,
        results=results,
    )


def _decide(condition: AcceptanceCondition, directory: Path) -> ConditionResult:
    arguments = condition.argument_map
    label = condition.label
    try:
        satisfied, detail = _DECIDERS[condition.kind](arguments, directory)
    except WorkspaceError as exc:
        return ConditionResult(
            kind=condition.kind,
            label=label,
            satisfied=False,
            detail=f"Kosul degerlendirilemedi: {exc}",
        )
    return ConditionResult(
        kind=condition.kind, label=label, satisfied=satisfied, detail=detail
    )


def _artifact_exists(arguments: dict[str, str], directory: Path) -> tuple[bool, str]:
    name = arguments["name"]
    present = {item.name for item in list_files(directory)}
    if name in present:
        return True, f"'{name}' calisma alaninda bulundu."
    return False, f"'{name}' calisma alaninda yok."


def _artifact_is_json(arguments: dict[str, str], directory: Path) -> tuple[bool, str]:
    name = arguments["name"]
    body = read_text(directory, name)
    try:
        json.loads(body)
    except ValueError as exc:
        return False, f"'{name}' gecerli JSON degil: {exc.args[0]}"
    return True, f"'{name}' gecerli bir JSON belgesi."


def _artifact_has_json_keys(
    arguments: dict[str, str], directory: Path
) -> tuple[bool, str]:
    name = arguments["name"]
    wanted = parse_keys(arguments["keys"])
    body = read_text(directory, name)
    try:
        document = json.loads(body)
    except ValueError as exc:
        return False, f"'{name}' gecerli JSON degil: {exc.args[0]}"
    if not isinstance(document, dict):
        return False, f"'{name}' bir JSON nesnesi degil; anahtar aranamaz."
    missing = [key for key in wanted if key not in document]
    if missing:
        return False, f"'{name}' su anahtarlari tasimiyor: " + ", ".join(missing) + "."
    return True, f"'{name}' istenen {len(wanted)} anahtarin hepsini tasiyor."


def _artifact_contains(arguments: dict[str, str], directory: Path) -> tuple[bool, str]:
    name = arguments["name"]
    body = read_text(directory, name)
    if arguments["text"] in body:
        return True, f"'{name}' istenen metni iceriyor."
    return False, f"'{name}' istenen metni icermiyor."


def _artifact_digest_is(arguments: dict[str, str], directory: Path) -> tuple[bool, str]:
    name = arguments["name"]
    actual = digest_of(directory, name)
    if actual == arguments["digest"]:
        return True, f"'{name}' ozeti beklenen degerle ayni."
    return False, f"'{name}' ozeti beklenen degerle ayni degil: {actual}"


_DECIDERS: dict[
    AcceptanceKind, Callable[[dict[str, str], Path], tuple[bool, str]]
] = {
    AcceptanceKind.ARTIFACT_EXISTS: _artifact_exists,
    AcceptanceKind.ARTIFACT_IS_JSON: _artifact_is_json,
    AcceptanceKind.ARTIFACT_HAS_JSON_KEYS: _artifact_has_json_keys,
    AcceptanceKind.ARTIFACT_CONTAINS: _artifact_contains,
    AcceptanceKind.ARTIFACT_DIGEST_IS: _artifact_digest_is,
}


__all__ = [
    "ACCEPTANCE_CHECKS",
    "FAILED_DETAIL",
    "MAX_ACCEPTANCE_CONDITIONS",
    "MAX_KEY_LIST_CHARS",
    "MAX_REQUIRED_KEYS",
    "NOT_IMPLEMENTED_DETAIL",
    "NOT_IMPLEMENTED_OUTCOME",
    "PASSED_DETAIL",
    "AcceptanceCheck",
    "AcceptanceCondition",
    "AcceptanceKind",
    "AcceptanceOutcome",
    "AcceptanceState",
    "ConditionResult",
    "bind_condition",
    "evaluate",
    "parse_keys",
    "resolve_check",
]
