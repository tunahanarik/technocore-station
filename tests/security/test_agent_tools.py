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
    MAX_NAME_CHARS,
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

    ``json_text`` was here and is gone. It was declared by no tool, so its
    validator branch was unreachable in production and a review measured that
    deleting the branch changed nothing. A published parameter type is a
    claim that some tool takes one.
    """
    assert {member.value for member in ToolParamType} == {
        "text",
        "file_name",
        "digest",
    }


def test_every_parameter_type_is_declared_by_a_real_tool() -> None:
    """The rule that removal enforces, stated so it cannot rot back.

    A type nothing declares is a validator nothing runs and a capability a
    reader would infer and not find. Adding a member to the enum without a
    tool that takes it fails here.
    """
    declared = {param.type for record in TOOLS for param in record.params}

    assert declared == set(ToolParamType), set(ToolParamType) - declared


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
    """The rule the import-time check applies, asserted over the real registry.

    ``purpose`` is in the haystack. ``tools.py``'s own docstring said the
    check covered "every registered identifier **and purpose**" while both
    the check and this test read only the id and the scope - a review read
    both and found the gap. The purpose is the sentence the surface shows
    beside a tool, so a record that *describes itself* as committing to git
    is as much a crossing as one named for it.
    """
    offenders: list[str] = []
    for record in TOOLS:
        haystack = (
            f"{record.id.value} {record.scope.value} {record.purpose}".lower()
        )
        offenders.extend(
            f"{record.id.value}: {fragment}"
            for fragment in FORBIDDEN_CAPABILITY_FRAGMENTS
            if fragment in haystack
        )

    assert offenders == [], offenders


def test_the_import_time_check_reads_the_purpose_and_not_only_the_name() -> None:
    """Driven with a record whose *only* crossing is in its purpose.

    The id and the scope are both innocent here, so the refusal can only come
    from the purpose being scanned. Before the fix this record was accepted.
    """
    planted = ToolRecord(
        id="summarise_workspace",  # type: ignore[arg-type]
        scope=ToolScope.DETERMINISTIC_CHECK,
        purpose="TEST-ONLY: uretilen yamayi git ile commit eder.",
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


def test_the_import_time_check_is_actually_called_at_import(
    api_source_root: Path,
) -> None:
    """The guard runs because a module-level statement calls it, and that
    statement is what this test pins.

    The behavioural test above proves the function refuses a planted record;
    it says nothing about whether anything invokes it. A review commented the
    call out and the whole suite stayed green - so the protection was one
    deleted line away from being a function nobody runs, in a module whose
    docstring promises "the application refusing to start".

    Read off the syntax tree, at module level only: a call nested inside a
    function would not run at import.
    """
    path = api_source_root / "station_api" / "agent" / "tools.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    call_sites = [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "_assert_within_the_trust_boundary"
    ]

    assert len(call_sites) == 1, call_sites

    # And it runs before the lookup table is built, so an application
    # carrying a forbidden tool never gets one.
    lookup = [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "_BY_ID"
    ]
    assert lookup and call_sites[0] < lookup[0]


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

    offenders: list[str] = []
    for scanned in _registry_scope(api_source_root):
        offenders.extend(_registry_writers(scanned, allow_module_level=scanned == path))

    assert offenders == [], offenders


#: Every write a registry could take, modelled the way ``test_agent_budget``
#: models the four writes to the ceiling. Three of these were missing until an
#: independent review fed the scan a source it called CLEAN:
#:
#:     _BY_ID[record.id] = record             # subscript assignment
#:     globals()["TOOLS"] = (*TOOLS, record)  # rebinding through globals()
#:
#: and ``setattr(tools, "TOOLS", ...)`` beside them. The scan also read only
#: ``tools.py`` while its docstring said "nothing anywhere in the package",
#: so ``service.py`` and ``routes/agent.py`` could have written the registry
#: without anything noticing.
_REGISTRY_NAMES = frozenset({"TOOLS", "_BY_ID"})

_REGISTRY_MUTATORS = frozenset(
    {"append", "extend", "insert", "update", "setdefault", "pop", "clear"}
)


def _registry_scope(api_source_root: Path) -> list[Path]:
    """Every file that could write the registry: the whole package, and the route."""
    package = api_source_root / "station_api" / "agent"
    files = sorted(package.rglob("*.py"))
    files.append(api_source_root / "station_api" / "routes" / "agent.py")
    assert len(files) >= 8, files
    return files


def _registry_writers(path: Path, *, allow_module_level: bool) -> list[str]:
    """Offending writes to ``TOOLS`` or ``_BY_ID`` in one file.

    ``allow_module_level`` exempts the two literal definitions in ``tools.py``
    itself, which the caller has already counted; everything else - a
    subscript, an attribute, an augmented assignment, ``globals()``,
    ``setattr`` and the container mutators - is an offence wherever it is.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_level = set(tree.body)
    offenders: list[str] = []

    def _report(node: ast.AST, what: str) -> None:
        offenders.append(f"{path.name}:{getattr(node, 'lineno', 0)} {what}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            for target in targets:
                if isinstance(target, ast.Name) and target.id in _REGISTRY_NAMES:
                    if allow_module_level and node in module_level and (
                        not isinstance(node, ast.AugAssign)
                    ):
                        continue
                    _report(node, f"rebinds {target.id}")
                elif isinstance(target, ast.Attribute) and (
                    target.attr in _REGISTRY_NAMES
                ):
                    _report(node, f"assigns .{target.attr}")
                elif isinstance(target, ast.Subscript):
                    inner = target.value
                    if isinstance(inner, ast.Name) and inner.id in _REGISTRY_NAMES:
                        _report(node, f"writes into {inner.id}")
                    elif isinstance(inner, ast.Call) and isinstance(
                        inner.func, ast.Name
                    ) and inner.func.id in {"globals", "vars"}:
                        _report(node, f"rebinds through {inner.func.id}()")
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Name)
                and func.id == "setattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in _REGISTRY_NAMES
            ):
                _report(node, f"setattr {node.args[1].value}")
            elif (
                isinstance(func, ast.Attribute)
                and func.attr in _REGISTRY_MUTATORS
                and isinstance(func.value, ast.Name)
                and func.value.id in _REGISTRY_NAMES
            ):
                _report(node, f"{func.value.id}.{func.attr}()")

    return offenders


def test_the_registry_scan_catches_every_shape_of_write(tmp_path: Path) -> None:
    """The scan, fed the source a review called CLEAN, plus the rest.

    Every line here is a real way to add a tool at runtime, and the scan is
    required to see all of them. Without this the previous scan happily
    passed a module that rebuilt ``TOOLS`` through ``globals()`` and wrote
    straight into ``_BY_ID``.
    """
    planted = tmp_path / "planted.py"
    planted.write_text(
        "TOOLS = ()\n"
        "_BY_ID = {}\n"
        "def add_tool(record):\n"
        "    _BY_ID[record.id] = record\n"
        '    globals()["TOOLS"] = (*TOOLS, record)\n'
        '    setattr(mod, "TOOLS", ())\n'
        "    TOOLS += (record,)\n"
        "    mod.TOOLS = ()\n"
        "    _BY_ID.update({})\n",
        encoding="utf-8",
    )

    offenders = _registry_writers(planted, allow_module_level=True)

    assert len(offenders) == 6, offenders
    joined = " ".join(offenders)
    for shape in (
        "writes into _BY_ID",
        "rebinds through globals()",
        "setattr TOOLS",
        "rebinds TOOLS",
        "assigns .TOOLS",
        "_BY_ID.update()",
    ):
        assert shape in joined, (shape, offenders)


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
    ],
)
def test_a_file_name_parameter_refuses_anything_that_is_not_a_bare_name(
    hostile: str,
) -> None:
    """The first of the two layers. The workspace applies the second.

    Neither layer is trusted alone: this one refuses a name carrying syntax,
    and ``workspace.resolve_within`` rebuilds the name from an allow-list and
    then checks containment on the resolved path.

    ``"a" * 200`` used to be in this list, and it was the weakest entry: it
    is refused for being *long*, not for carrying syntax, and both refusals
    answered the same reason so the test could not tell them apart. It has
    its own test below, with its own reason.
    """
    record = get_tool(ToolId.READ_WORKSPACE_FILE)

    with pytest.raises(ToolArgumentError) as caught:
        bind_arguments(record, {"name": hostile})

    assert caught.value.reason == "argument_not_a_bare_name"


def test_an_over_long_file_name_is_refused_as_a_length_and_not_as_a_shape() -> None:
    """The length branch, driven by its own reason.

    A review found that deleting this branch left the suite green: the name
    regex refuses the same input one line later with the same reason, so the
    only test covering it could not see which branch had fired. The two
    refusals now say different things, and a name that is *only* too long -
    every character allowed, nothing but the length wrong - proves the length
    check is the one doing the work.
    """
    record = get_tool(ToolId.READ_WORKSPACE_FILE)
    only_too_long = "a" * (MAX_NAME_CHARS + 1)

    assert only_too_long.strip("abcdefghijklmnopqrstuvwxyz") == ""

    with pytest.raises(ToolArgumentError) as caught:
        bind_arguments(record, {"name": only_too_long})

    assert caught.value.reason == "argument_name_too_long"
    assert str(MAX_NAME_CHARS) in str(caught.value)


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
