"""The closed tool registry. The sixth compile-time registry in this product.

===============================================  ==========================
:mod:`station_api.technocore.sources`            public document read
:mod:`station_api.technocore.write_targets`      explicit signed write
:mod:`station_api.technocore.evidence_targets`   evidence read
:mod:`station_api.workscan.targets`              work scan read
:mod:`station_api.opencode.registry`             provider endpoints + models
this module                                      **agent tool schema**
===============================================  ==========================

ADR-0008 2 settled what a "tool" is here, and what it settled has outlived
the fact it rested on. The wire format a provider would use to *call* one was
unpublished, so this build claimed none. What was defined instead is the
tool's **own schema** - its name, its typed parameters, its permission scope
and what one call costs against the run ceiling - and that is Station's, not
a provider's. It invents no external contract, which is exactly why it was
allowed to exist while the lane was closed.

ADR-0012 then measured the contract, so the schema has a consumer:
:func:`json_schema` projects a record into plain JSON Schema and
:mod:`station_api.opencode.planner` wraps that in the provider's envelope.
The direction of that dependency is the point - nothing here knows about any
provider, and nothing here changes if the envelope does.
``OUTBOUND_CLIENT_MODULES`` stayed at five.

The consequence is worth restating, because its *form* survived the change:
"model output is never executed directly" is still a structural fact rather
than a promise. It used to be structural because there was no model output;
it is structural now because every proposed call is looked up in this tuple
and every argument is bound against a declared type, one unregistered name
drops the whole proposal, and what comes out the other side is a recorded
plan a **person** starts.

The agent cannot add a tool to itself
--------------------------------------
:data:`TOOLS` is a tuple literal built at import from frozen dataclasses.
There is no registration function, no plugin path, no entry-point group and
nothing that mutates the lookup table. An unregistered identifier gets a
**shown refusal** with a reason - :class:`ToolRegistryError` - rather than a
``KeyError`` that becomes an armoured 500 (the F-11 lesson).

The trust boundary, enforced at import
---------------------------------------
ADR-0008 7: the commit/PR/merge authority a developer gave Claude during
development is **not** inherited by the runtime agent. There is no git tool,
no package installation, no settings editor, no permission-list editor and no
plugin loader, and :data:`FORBIDDEN_CAPABILITY_FRAGMENTS` is checked against
every registered identifier and purpose *when this module is imported*, so a
tool named ``git_commit`` cannot be added without the application refusing to
start. A test proves the check fires on a planted entry rather than trusting
that it would.

The runner takes typed arguments, never a command string
---------------------------------------------------------
:func:`bind_arguments` turns a mapping of raw strings into a tuple of
:class:`ToolArgument`, validating each against the parameter's declared type
and refusing an unknown key. Nothing anywhere assembles a shell string; there
is no shell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from station_api.agent.errors import ToolArgumentError, ToolRegistryError
from station_api.technocore.projection import sweep_untrusted


class ToolId(StrEnum):
    """Every tool this build has - eight - and never a ninth at runtime."""

    #: Read the identity of the snapshot the user approved for this task.
    READ_APPROVED_SNAPSHOT = "read_approved_snapshot"
    #: Read one file the user placed in this task's workspace.
    READ_WORKSPACE_FILE = "read_workspace_file"
    #: Produce a text, code, report or patch file in the workspace.
    WRITE_WORKSPACE_FILE = "write_workspace_file"
    #: Replace a file this run already produced.
    UPDATE_WORKSPACE_FILE = "update_workspace_file"
    #: Deterministic checker: is this file well-formed JSON?
    VALIDATE_JSON_FILE = "validate_json_file"
    #: Deterministic checker: unified diff between two workspace files.
    DIFF_WORKSPACE_FILES = "diff_workspace_files"
    #: Deterministic checker: does this file hash to the expected digest?
    VERIFY_FILE_DIGEST = "verify_file_digest"
    #: Read this run's own phase, steps and usage.
    READ_RUN_STATUS = "read_run_status"


class ToolScope(StrEnum):
    """The permission a tool needs. Four, and none of them leaves the machine."""

    #: Reads what the user already approved for this task.
    READ_APPROVED_INPUT = "read_approved_input"
    #: Writes inside this task's workspace directory and nowhere else.
    WRITE_WORKSPACE = "write_workspace"
    #: Reads workspace files and reports a deterministic verdict about them.
    DETERMINISTIC_CHECK = "deterministic_check"
    #: Reads the run's own bookkeeping.
    READ_RUN_STATE = "read_run_state"


class ToolParamType(StrEnum):
    """The parameter types. Each one has a validator, and each one is used.

    There is deliberately no ``PATH`` and no ``URL``: a tool cannot be handed
    an address. A :attr:`FILE_NAME` is a bare name inside one task's
    workspace, checked by :mod:`station_api.agent.workspace` a second time
    before any byte is read or written.

    There was a fourth member, ``JSON_TEXT``, and it is gone. No registered
    tool declared a parameter of that type, so its branch in :func:`_validate`
    could not be reached in production - an independent review measured that
    deleting the branch changed nothing. It is removed rather than left
    standing, for the same reason an audit event nothing can record is
    removed: a published type says "a tool may take one of these", and one
    that no tool takes is a capability a reader would infer and not find.
    Re-adding it is a tuple edit in :data:`TOOLS` plus a validator, which is
    a reviewable change and not a large one.
    """

    TEXT = "text"
    FILE_NAME = "file_name"
    DIGEST = "digest"


@dataclass(frozen=True, slots=True)
class ToolParam:
    """One typed parameter of one tool."""

    name: str
    type: ToolParamType
    required: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ToolRecord:
    """One tool: what it is, what it needs, what it costs, what it produces."""

    id: ToolId
    scope: ToolScope
    purpose: str
    params: tuple[ToolParam, ...]
    #: What one call spends against the run ceiling, in tool-call units. One,
    #: for every tool: a unit that varies per tool is a unit nobody can count
    #: ahead of time, and the ceiling exists to be predictable.
    call_cost: int
    #: Whether a successful call leaves a file behind. Read by the runner to
    #: decide whether an artifact digest is expected, never by the tool.
    produces_artifact: bool


#: Names that may never be a tool, in any spelling, checked at import time.
#:
#: ADR-0008 7 lists them and the list is deliberately blunt: a deny-list of
#: capabilities somebody thought of is cheap here, because the allow-list -
#: :data:`TOOLS` - is the real control and this is the second lock on it.
FORBIDDEN_CAPABILITY_FRAGMENTS: Final[tuple[str, ...]] = (
    "git",
    "commit",
    "push",
    "pull_request",
    "merge",
    "branch",
    "install",
    "pip",
    "npm",
    "package",
    "setting",
    "config",
    "permission",
    "allowlist",
    "plugin",
    "shell",
    "command",
    "exec",
    "subprocess",
    "network",
    "http",
    "fetch",
    "download",
    "upload",
    "signer",
    "sign",
    "vault",
    "recovery",
    "credential",
    "env",
    "home",
    "repo",
)

#: The complete set. Adding a tool means editing this tuple, which is a
#: reviewable change; nothing computes a record at runtime.
TOOLS: tuple[ToolRecord, ...] = (
    ToolRecord(
        id=ToolId.READ_APPROVED_SNAPSHOT,
        scope=ToolScope.READ_APPROVED_INPUT,
        purpose=(
            "Gorevin baglandigi onaylanmis icerik surumunu okur: icerik "
            "ozeti ve surum kimligi. Yeni bir sey getirmez, yalnizca gorevin "
            "kendi kaydini okur."
        ),
        params=(),
        call_cost=1,
        produces_artifact=False,
    ),
    ToolRecord(
        id=ToolId.READ_WORKSPACE_FILE,
        scope=ToolScope.READ_APPROVED_INPUT,
        purpose=(
            "Kullanicinin bu gorevin calisma alanina koydugu bir dosyayi "
            "okur. Calisma alani disinda hicbir yol okunmaz."
        ),
        params=(
            ToolParam(
                name="name",
                type=ToolParamType.FILE_NAME,
                required=True,
                detail="Calisma alanindaki dosyanin sade adi.",
            ),
        ),
        call_cost=1,
        produces_artifact=False,
    ),
    ToolRecord(
        id=ToolId.WRITE_WORKSPACE_FILE,
        scope=ToolScope.WRITE_WORKSPACE,
        purpose=(
            "Calisma alaninda metin, kod, rapor veya yama dosyasi uretir. "
            "Uretilen yama uygulanmaz: bu surumde hicbir sey calistirilmaz."
        ),
        params=(
            ToolParam(
                name="name",
                type=ToolParamType.FILE_NAME,
                required=True,
                detail="Uretilecek dosyanin sade adi.",
            ),
            ToolParam(
                name="body",
                type=ToolParamType.TEXT,
                required=True,
                detail="Dosyanin icerigi.",
            ),
        ),
        call_cost=1,
        produces_artifact=True,
    ),
    ToolRecord(
        id=ToolId.UPDATE_WORKSPACE_FILE,
        scope=ToolScope.WRITE_WORKSPACE,
        purpose=(
            "Calisma alaninda var olan bir dosyayi bastan yazar. Olmayan bir "
            "dosya guncellenmez; ret gosterilir."
        ),
        params=(
            ToolParam(
                name="name",
                type=ToolParamType.FILE_NAME,
                required=True,
                detail="Guncellenecek dosyanin sade adi.",
            ),
            ToolParam(
                name="body",
                type=ToolParamType.TEXT,
                required=True,
                detail="Dosyanin yeni icerigi.",
            ),
        ),
        call_cost=1,
        produces_artifact=True,
    ),
    ToolRecord(
        id=ToolId.VALIDATE_JSON_FILE,
        scope=ToolScope.DETERMINISTIC_CHECK,
        purpose=(
            "Bir calisma alani dosyasinin gecerli JSON olup olmadigini "
            "soyler. Ayni girdi her koda ayni sonucu verir."
        ),
        params=(
            ToolParam(
                name="name",
                type=ToolParamType.FILE_NAME,
                required=True,
                detail="Denetlenecek dosyanin sade adi.",
            ),
        ),
        call_cost=1,
        produces_artifact=False,
    ),
    ToolRecord(
        id=ToolId.DIFF_WORKSPACE_FILES,
        scope=ToolScope.DETERMINISTIC_CHECK,
        purpose=(
            "Iki calisma alani dosyasi arasindaki farki uretir. Fark "
            "hesaplanir, uygulanmaz."
        ),
        params=(
            ToolParam(
                name="left",
                type=ToolParamType.FILE_NAME,
                required=True,
                detail="Karsilastirmanin ilk dosyasi.",
            ),
            ToolParam(
                name="right",
                type=ToolParamType.FILE_NAME,
                required=True,
                detail="Karsilastirmanin ikinci dosyasi.",
            ),
        ),
        call_cost=1,
        produces_artifact=False,
    ),
    ToolRecord(
        id=ToolId.VERIFY_FILE_DIGEST,
        scope=ToolScope.DETERMINISTIC_CHECK,
        purpose=(
            "Bir calisma alani dosyasinin SHA-256 ozetini beklenen degerle "
            "karsilastirir. Uyusmazlik gosterilir, sessizce gecilmez."
        ),
        params=(
            ToolParam(
                name="name",
                type=ToolParamType.FILE_NAME,
                required=True,
                detail="Ozetlenecek dosyanin sade adi.",
            ),
            ToolParam(
                name="digest",
                type=ToolParamType.DIGEST,
                required=True,
                detail="Beklenen 64 karakterlik kucuk harf hex ozet.",
            ),
        ),
        call_cost=1,
        produces_artifact=False,
    ),
    ToolRecord(
        id=ToolId.READ_RUN_STATUS,
        scope=ToolScope.READ_RUN_STATE,
        purpose=(
            "Calismanin kendi asamasini, adimlarini ve tavana gore "
            "kullanimini okur. Hicbir seyi degistirmez."
        ),
        params=(),
        call_cost=1,
        produces_artifact=False,
    ),
)


def _assert_within_the_trust_boundary() -> None:
    """Refuse at import if a registered tool crosses ADR-0008 7's line.

    Run once, here, rather than left to a test: a test proves the rule holds
    in this commit, and this makes an application carrying a forbidden tool
    fail to start at all. The two are complementary and the cheap one is the
    import-time check.
    """
    for record in TOOLS:
        # ``str()`` rather than ``.value``: the check has to survive a record
        # whose id is not a registry member, because that is exactly what a
        # planted entry looks like, and a guard that raises ``AttributeError``
        # on the shape it exists to catch has not caught anything.
        # ``purpose`` is in the haystack because this module's own docstring
        # promises it is - "every registered identifier **and purpose**". It
        # was not, until a review read both. The purpose is what a user sees
        # beside a tool on the surface, so a record that *describes itself*
        # as committing to git is as much a boundary crossing as one named
        # for it.
        haystack = f"{record.id!s} {record.scope!s} {record.purpose!s}".lower()
        for fragment in FORBIDDEN_CAPABILITY_FRAGMENTS:
            if fragment in haystack:
                raise ToolRegistryError(
                    "Arac registry'si guven sinirini asan bir kayit tasiyor: "
                    f"'{record.id!s}'. Git, paket kurulumu, ayar, izin "
                    "listesi ve plugin bu urunde bir arac olamaz.",
                    reason="tool_outside_trust_boundary",
                )


_assert_within_the_trust_boundary()

_BY_ID: dict[ToolId, ToolRecord] = {record.id: record for record in TOOLS}


def get_tool(tool_id: ToolId) -> ToolRecord:
    """Look a tool up, or refuse by name.

    Raises :class:`ToolRegistryError` for anything outside the compile-time
    set, including an unhashable value, so a caller turns it into a shown
    refusal instead of letting a bare ``KeyError`` become a 500.
    """
    try:
        return _BY_ID[tool_id]
    except (KeyError, TypeError) as exc:
        raise ToolRegistryError(
            "Kayitli olmayan bir arac istendi. Arac kumesi derleme zamaninda "
            "sabittir; calisma zamaninda genisletilemez ve agent kendisine "
            "arac ekleyemez.",
            reason="tool_unknown",
        ) from exc


def resolve_tool(raw: str) -> ToolRecord:
    """Turn a caller-supplied string into a registered tool, or refuse it.

    The one place a string becomes a capability. It is a *shown* refusal:
    ADR-0008 2 requires an unregistered identifier to produce an answer the
    user can read, not a silence and not a stack trace.
    """
    try:
        tool_id = ToolId(raw)
    except ValueError as exc:
        raise ToolRegistryError(
            "Kayitli olmayan bir arac istendi. Arac kumesi derleme zamaninda "
            "sabittir; calisma zamaninda genisletilemez ve agent kendisine "
            "arac ekleyemez.",
            reason="tool_unknown",
        ) from exc
    return get_tool(tool_id)


# ---------------------------------------------------------------------------
# Typed arguments, never a command string
# ---------------------------------------------------------------------------

#: Longest text a tool may be handed. A body is a document, not a payload.
MAX_TEXT_CHARS = 20_000

#: Longest file name accepted before the workspace sanitiser sees it. One
#: shorter than :data:`_FILE_NAME_RE`'s own bound would allow, so the length
#: refusal is the branch a too-long name actually takes and not a formality
#: the regex reaches first.
MAX_NAME_CHARS = 120

_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")

#: A bare name: letters, digits, dot, dash, underscore. No separator, no
#: drive letter, no ``..``. The workspace re-derives the name through the
#: download sanitiser afterwards, so this is the first of two layers.
_FILE_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")


@dataclass(frozen=True, slots=True)
class ToolArgument:
    """One validated argument, bound to the parameter it satisfies."""

    param: ToolParam
    value: str


def _validate(param: ToolParam, raw: str) -> str:
    """Apply one parameter's type. Returns the value the tool will receive."""
    if not isinstance(raw, str):  # pragma: no cover - the schema types it
        raise ToolArgumentError(
            f"'{param.name}' bir metin olmali.", reason="argument_type"
        )

    if param.type is ToolParamType.TEXT:
        value = sweep_untrusted(raw)[:MAX_TEXT_CHARS]
        if not value.strip():
            raise ToolArgumentError(
                f"'{param.name}' bos olamaz.", reason="argument_empty"
            )
        return value

    if param.type is ToolParamType.FILE_NAME:
        value = sweep_untrusted(raw).strip()
        # Length is refused, never truncated. A silently shortened name is a
        # file the plan did not ask for, and the digest the run later verifies
        # would then be of something else - the same reason
        # ``workspace.safe_name`` refuses a rewrite rather than accepting one.
        if len(value) > MAX_NAME_CHARS:
            # Its own reason, not the shape refusal's. Both branches used to
            # answer ``argument_not_a_bare_name``, which meant a test could
            # not tell which one had fired - and a review found that deleting
            # this branch entirely left the suite green, because the regex
            # refused the same input with the same reason one line later.
            # Two different refusals now say two different things.
            raise ToolArgumentError(
                f"'{param.name}' en cok {MAX_NAME_CHARS} karakter olabilir; "
                "ad kisaltilmaz, reddedilir.",
                reason="argument_name_too_long",
            )
        if not _FILE_NAME_RE.match(value) or ".." in value:
            raise ToolArgumentError(
                f"'{param.name}' yalnizca sade bir dosya adi olabilir: yol "
                "ayraci, surucu harfi ve '..' kabul edilmez.",
                reason="argument_not_a_bare_name",
            )
        return value

    # DIGEST. The last member; every branch above returned, and there is no
    # fall-through case left to write, which is the point of the enum having
    # exactly as many members as there are validators.
    value = raw.strip()
    if not _DIGEST_RE.match(value):
        raise ToolArgumentError(
            f"'{param.name}' 64 karakterlik kucuk harf hex ozet olmali.",
            reason="argument_not_a_digest",
        )
    return value


def bind_params(
    params: tuple[ToolParam, ...], raw: dict[str, str], *, owner: str
) -> tuple[ToolArgument, ...]:
    """Validate a mapping against one declared parameter list.

    Three refusals, in the order they matter: an argument the owner does not
    declare, a required argument that is missing, and a value that does not
    match its declared type. The result is a tuple of typed arguments in the
    owner's own parameter order - never a string a shell could read, because
    there is no shell.

    ``owner`` is the identifier quoted back in a refusal. The function is
    written against a parameter tuple rather than against a
    :class:`ToolRecord` because :mod:`station_api.agent.acceptance` declares
    a second closed registry with the same parameter types, and it must be
    validated by **this** function rather than by a second copy of it: two
    validators that agree today is the duplication ADR-0004 2 named, and the
    one place it would be most expensive is the one that decides whether a
    task may be called finished.
    """
    declared = {param.name for param in params}
    unknown = sorted(set(raw) - declared)
    if unknown:
        raise ToolArgumentError(
            f"'{owner}' su parametreleri tanimiyor: " + ", ".join(unknown) + ".",
            reason="argument_unknown",
        )

    bound: list[ToolArgument] = []
    for param in params:
        if param.name not in raw:
            if param.required:
                raise ToolArgumentError(
                    f"'{owner}' icin '{param.name}' zorunlu.",
                    reason="argument_missing",
                )
            continue
        bound.append(ToolArgument(param=param, value=_validate(param, raw[param.name])))
    return tuple(bound)


def bind_arguments(
    record: ToolRecord, raw: dict[str, str]
) -> tuple[ToolArgument, ...]:
    """Validate a mapping against one tool's declared parameters."""
    return bind_params(record.params, raw, owner=record.id.value)


def argument_map(arguments: tuple[ToolArgument, ...]) -> dict[str, str]:
    """The validated arguments as a plain mapping, for the executor."""
    return {argument.param.name: argument.value for argument in arguments}


#: How each parameter type is described in JSON Schema. A mapping rather than
#: a formatter, so a type added to the enum without a description here is a
#: ``KeyError`` at import of the projection rather than a parameter that
#: quietly reaches a model with no shape at all.
_SCHEMA_TYPES: dict[ToolParamType, dict[str, object]] = {
    ToolParamType.TEXT: {"maxLength": MAX_TEXT_CHARS, "type": "string"},
    ToolParamType.FILE_NAME: {
        "maxLength": MAX_NAME_CHARS,
        "pattern": _FILE_NAME_RE.pattern.replace("\\A", "^").replace("\\Z", "$"),
        "type": "string",
    },
    ToolParamType.DIGEST: {
        "maxLength": 64,
        "minLength": 64,
        "pattern": "^[0-9a-f]{64}$",
        "type": "string",
    },
}


def json_schema(record: ToolRecord) -> dict[str, object]:
    """One tool's parameters as JSON Schema. **Station's schema, exported.**

    ADR-0008 2 drew the line here and the line has not moved: what this
    registry owns is the tool's *own* schema - its name, its typed parameters,
    what one call costs - and that was always Station's rather than a
    provider's. What was missing was a consumer for it, because the wire
    format a provider would use to call one was unpublished.

    That format has since been measured (see
    :mod:`station_api.opencode.planner`), so the schema now has a consumer -
    and the direction of the dependency is worth stating: this function
    returns plain JSON Schema and knows nothing about any provider's envelope.
    The envelope is built in the adapter, which is where a provider-shaped
    thing belongs. Nothing here changes if the envelope does.

    ``additionalProperties`` is ``False`` because the binder refuses an
    undeclared argument anyway (``argument_unknown``); saying so in the schema
    turns a refusal a model would have discovered into one it can avoid.
    """
    properties = {
        param.name: {**_SCHEMA_TYPES[param.type], "description": param.detail}
        for param in record.params
    }
    return {
        "additionalProperties": False,
        "properties": properties,
        "required": [param.name for param in record.params if param.required],
        "type": "object",
    }


def scopes_of(tool_ids: tuple[ToolId, ...]) -> tuple[ToolScope, ...]:
    """The distinct scopes a plan asks for, in registry order.

    Shown to the user before a run starts: the permission a plan needs is a
    thing to approve, not a thing to discover afterwards.
    """
    wanted = {get_tool(tool_id).scope for tool_id in tool_ids}
    return tuple(scope for scope in ToolScope if scope in wanted)


__all__ = [
    "FORBIDDEN_CAPABILITY_FRAGMENTS",
    "MAX_NAME_CHARS",
    "MAX_TEXT_CHARS",
    "TOOLS",
    "ToolArgument",
    "ToolId",
    "ToolParam",
    "ToolParamType",
    "ToolRecord",
    "ToolScope",
    "argument_map",
    "bind_arguments",
    "bind_params",
    "get_tool",
    "json_schema",
    "resolve_tool",
    "scopes_of",
]
