"""The sixth closed registry: compile-time, typed, and unreachable at runtime.

ADR-0008 2 decides that the *wire format* a provider would use to call a tool
stays unclaimed - it is unpublished, and ADR-0005 1.2 forbids inventing an
external contract - while the tool's **own schema** is Station's and may
therefore exist. This file holds both halves.

The half that is easy to get wrong is "the agent cannot add a tool to
itself". It is not enough for there to be no registration function today; the
registry has to be a shape that cannot acquire one quietly. So:

* :data:`TOOLS` is a tuple literal of frozen dataclasses, and an AST scan
  requires the lookup table to be built once and never mutated;
* an unregistered identifier produces a **shown refusal** with a reason, not a
  ``KeyError`` that becomes an armoured 500 - the F-11 lesson, applied to the
  one surface where a caller supplies a capability name;
* the trust boundary is checked **at import**, so an application carrying a
  ``git_commit`` tool does not start. The check is then driven against a
  planted entry, because a guard nobody has watched fail is a guard nobody
  has tested.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from station_api.agent import tools as tools_module
from station_api.agent.errors import ToolArgumentError, ToolRegistryError
from station_api.agent.tools import (
    FORBIDDEN_CAPABILITY_FRAGMENTS,
    MAX_TEXT_CHARS,
    TOOLS,
    ToolId,
    ToolParam,
    ToolParamType,
    ToolRecord,
    ToolScope,
    argument_map,
    bind_arguments,
    get_tool,
    resolve_tool,
    scopes_of,
)

pytestmark = pytest.mark.security

#: The tools this release has, typed out rather than imported. An oracle read
#: out of the constant under test proves only that the code agrees with
#: itself; this is what makes "a tool was added" a change somebody reviews.
EXPECTED_TOOL_IDS = frozenset(
    {
        "read_approved_snapshot",
        "read_workspace_file",
        "write_workspace_file",
        "update_workspace_file",
        "validate_json_file",
        "diff_workspace_files",
        "verify_file_digest",
        "read_run_status",
    }
)

#: Capabilities ADR-0008 7 names as inherited-authority and refuses. Typed out
#: in the spelling somebody would actually reach for.
CAPABILITIES_THE_AGENT_MUST_NOT_HAVE = (
    "git_commit",
    "open_pull_request",
    "merge_branch",
    "install_package",
    "edit_settings",
    "edit_permission_list",
    "load_plugin",
    "run_shell_command",
    "read_home_directory",
    "read_station_repo",
)


# ---------------------------------------------------------------------------
# The registry is closed
# ---------------------------------------------------------------------------


def test_the_registry_is_exactly_the_tools_this_release_has() -> None:
    assert {record.id.value for record in TOOLS} == EXPECTED_TOOL_IDS
    assert {member.value for member in ToolId} == EXPECTED_TOOL_IDS
    assert len({record.id for record in TOOLS}) == len(TOOLS)


def test_every_tool_declares_a_scope_a_purpose_and_a_cost() -> None:
    for record in TOOLS:
        assert isinstance(record.scope, ToolScope), record.id
        assert record.purpose.strip(), record.id
        # One call, one unit. A per-tool cost is a cost nobody can add up
        # ahead of time, and the ceiling exists to be predictable.
        assert record.call_cost == 1, record.id
        assert not set(record.purpose) & set("çğıöşüÇĞİÖŞÜ"), record.id


def test_every_parameter_is_typed_and_explained() -> None:
    for record in TOOLS:
        names = [param.name for param in record.params]
        assert len(names) == len(set(names)), record.id
        for param in record.params:
            assert isinstance(param.type, ToolParamType), (record.id, param.name)
            assert param.detail.strip(), (record.id, param.name)


def test_no_parameter_type_can_carry_an_address() -> None:
    """There is no ``path`` and no ``url``, and that is the design.

    A tool cannot be handed an address. A file is named, and the name goes
    through the workspace's own sanitiser and containment check afterwards -
    two layers, neither of which a caller reaches around.
    """
    assert {member.value for member in ToolParamType} == {
        "text",
        "file_name",
        "digest",
        "json_text",
    }


def test_a_tool_record_cannot_be_mutated() -> None:
    with pytest.raises(FrozenInstanceError):
        TOOLS[0].call_cost = 99  # type: ignore[misc]


def test_an_unregistered_identifier_gets_a_shown_refusal(
) -> None:
    """Not a ``KeyError``. The user asked for a capability; they get an answer.

    ``ToolRegistryError`` carries a reason and a Turkish sentence that names
    the actual rule - the set is fixed at build time - rather than leaking a
    lookup failure into a 500.
    """
    with pytest.raises(ToolRegistryError) as caught:
        resolve_tool("run_shell_command")

    assert caught.value.reason == "tool_unknown"
    assert "derleme zamaninda" in str(caught.value)
    assert "run_shell_command" not in str(caught.value)


def test_get_tool_refuses_an_unhashable_value() -> None:
    """The ``get_module`` shape: a ``TypeError`` is the same refusal."""
    with pytest.raises(ToolRegistryError):
        get_tool(["not-a-tool-id"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The trust boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("capability", CAPABILITIES_THE_AGENT_MUST_NOT_HAVE)
def test_the_authority_a_developer_had_is_not_inherited(capability: str) -> None:
    """ADR-0008 7, one name at a time.

    Each of these is something a coding assistant is routinely given during
    development. None of them is a tool the runtime agent has, and each is
    refused by the same shown refusal an unregistered name gets.
    """
    assert capability not in EXPECTED_TOOL_IDS

    with pytest.raises(ToolRegistryError):
        resolve_tool(capability)


def test_no_registered_tool_crosses_the_forbidden_capability_list() -> None:
    """The rule the import-time check applies, asserted over the real registry."""
    offenders: list[str] = []
    for record in TOOLS:
        haystack = f"{record.id.value} {record.scope.value}".lower()
        offenders.extend(
            f"{record.id.value}: {fragment}"
            for fragment in FORBIDDEN_CAPABILITY_FRAGMENTS
            if fragment in haystack
        )

    assert offenders == [], offenders


def test_the_import_time_check_actually_refuses_a_planted_tool() -> None:
    """Guards the guard: the check is driven, not trusted.

    An import-time guard that has only ever seen a registry which satisfies it
    has not been shown to refuse anything. This feeds it the shape it exists
    to catch - a git tool - and requires the refusal.
    """
    planted = ToolRecord(
        id="git_commit",  # type: ignore[arg-type]
        scope=ToolScope.WRITE_WORKSPACE,
        purpose="TEST-ONLY",
        params=(),
        call_cost=1,
        produces_artifact=False,
    )

    original = tools_module.TOOLS
    try:
        tools_module.TOOLS = (*original, planted)
        with pytest.raises(ToolRegistryError) as caught:
            tools_module._assert_within_the_trust_boundary()
    finally:
        tools_module.TOOLS = original

    assert caught.value.reason == "tool_outside_trust_boundary"


def test_the_registry_is_never_written_at_runtime(api_source_root: Path) -> None:
    """The structural half of "the agent cannot add a tool to itself".

    The behavioural tests can only find a registration path they know how to
    call. This one reads the syntax tree and requires that ``TOOLS`` and the
    lookup table are each assigned exactly once, at module level, and that
    nothing anywhere in the package calls a mutator on either.
    """
    path = api_source_root / "station_api" / "agent" / "tools.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    assignments = [
        target.id
        for node in tree.body
        if isinstance(node, ast.AnnAssign | ast.Assign)
        for target in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets)
        if isinstance(target, ast.Name)
    ]
    assert assignments.count("TOOLS") == 1
    assert assignments.count("_BY_ID") == 1

    mutators = {"append", "extend", "insert", "update", "setdefault", "pop", "clear"}
    offenders = [
        f"{node.lineno}: {ast.unparse(node.func)}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in mutators
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"TOOLS", "_BY_ID"}
    ]
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# Typed arguments, never a command string
# ---------------------------------------------------------------------------


def test_arguments_are_bound_to_declared_parameters() -> None:
    record = get_tool(ToolId.WRITE_WORKSPACE_FILE)
    bound = bind_arguments(record, {"name": "rapor.md", "body": "TEST-ONLY"})

    assert [argument.param.name for argument in bound] == ["name", "body"]
    assert argument_map(bound) == {"name": "rapor.md", "body": "TEST-ONLY"}


def test_an_undeclared_argument_is_refused() -> None:
    """Not ignored. An argument the tool does not know is a caller mistake or
    an attempt to reach a parameter that does not exist, and both deserve an
    answer rather than silence."""
    record = get_tool(ToolId.VALIDATE_JSON_FILE)

    with pytest.raises(ToolArgumentError) as caught:
        bind_arguments(record, {"name": "a.json", "shell": "cmd.exe"})

    assert caught.value.reason == "argument_unknown"


def test_a_missing_required_argument_is_refused() -> None:
    record = get_tool(ToolId.VERIFY_FILE_DIGEST)

    with pytest.raises(ToolArgumentError) as caught:
        bind_arguments(record, {"name": "a.json"})

    assert caught.value.reason == "argument_missing"


@pytest.mark.parametrize(
    "hostile",
    [
        "../escape.txt",
        "..\\escape.txt",
        "sub/dir.txt",
        "C:\\Windows\\system32\\drivers\\etc\\hosts",
        "\\\\server\\share\\file.txt",
        "..",
        "",
        "a" * 200,
    ],
)
def test_a_file_name_parameter_refuses_anything_that_is_not_a_bare_name(
    hostile: str,
) -> None:
    """The first of the two layers. The workspace applies the second.

    Neither layer is trusted alone: this one refuses a name carrying syntax,
    and ``workspace.resolve_within`` rebuilds the name from an allow-list and
    then checks containment on the resolved path.
    """
    record = get_tool(ToolId.READ_WORKSPACE_FILE)

    with pytest.raises(ToolArgumentError) as caught:
        bind_arguments(record, {"name": hostile})

    assert caught.value.reason == "argument_not_a_bare_name"


def test_a_digest_parameter_refuses_anything_that_is_not_one() -> None:
    record = get_tool(ToolId.VERIFY_FILE_DIGEST)

    for bad in ("", "abc", "A" * 64, "0" * 63, "0" * 65):
        with pytest.raises(ToolArgumentError) as caught:
            bind_arguments(record, {"name": "a.json", "digest": bad})
        assert caught.value.reason == "argument_not_a_digest"

    bound = bind_arguments(record, {"name": "a.json", "digest": "0" * 64})
    assert argument_map(bound)["digest"] == "0" * 64


def test_a_text_argument_is_swept_and_bounded() -> None:
    """Control and bidi characters go; the length is capped."""
    record = get_tool(ToolId.WRITE_WORKSPACE_FILE)
    bound = bind_arguments(
        record, {"name": "a.md", "body": "iyi\u202egunler" + "x" * MAX_TEXT_CHARS}
    )
    body = argument_map(bound)["body"]

    assert "\u202e" not in body
    assert len(body) <= MAX_TEXT_CHARS


def test_an_empty_text_argument_is_refused() -> None:
    record = get_tool(ToolId.WRITE_WORKSPACE_FILE)

    with pytest.raises(ToolArgumentError) as caught:
        bind_arguments(record, {"name": "a.md", "body": "   "})

    assert caught.value.reason == "argument_empty"


def test_the_scopes_a_plan_needs_are_reported_in_registry_order() -> None:
    """A permission is a thing to approve before a run, not to discover after."""
    wanted = scopes_of((ToolId.WRITE_WORKSPACE_FILE, ToolId.VALIDATE_JSON_FILE))

    assert wanted == (ToolScope.WRITE_WORKSPACE, ToolScope.DETERMINISTIC_CHECK)


def test_the_tool_runner_takes_no_command_string(api_source_root: Path) -> None:
    """There is no place a shell string could be assembled, let alone run.

    Read off the **syntax tree** rather than off the file text. A substring
    scan over the source would trip on this package's own docstrings - which
    say the words ``os.system`` and ``subprocess`` precisely because they are
    explaining that neither is here - and a test that fails on its own
    explanation gets deleted rather than fixed.

    So: no call to a runner-shaped name anywhere in the package, and no
    ``shell=`` keyword on any call. The executor is a chain of
    ``if record.id is ToolId...`` branches calling Python functions with
    type-checked values, and the boundary test beside this one proves the
    imports that would make a runner possible are absent.
    """
    runners = {"system", "popen", "Popen", "spawn", "spawnv", "execv", "call"}
    offenders: list[str] = []

    for path in sorted(
        (api_source_root / "station_api" / "agent").rglob("*.py")
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if name in runners:
                offenders.append(f"{path.name}:{node.lineno} {name}")
            offenders.extend(
                f"{path.name}:{node.lineno} shell="
                for keyword in node.keywords
                if keyword.arg == "shell"
            )

    assert offenders == [], offenders


def test_a_tool_param_is_frozen() -> None:
    param = ToolParam(
        name="name", type=ToolParamType.FILE_NAME, required=True, detail="TEST-ONLY"
    )

    with pytest.raises(FrozenInstanceError):
        param.required = False  # type: ignore[misc]
