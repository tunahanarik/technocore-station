"""The documented gate list has to be the set of gates CI actually runs.

A ``B007`` (unused loop variable) in ``tests/security/test_model_lane_claims.py``
passed the whole gate list in ``AGENTS.md`` 4 and then failed CI. Nothing was
wrong with the fix; what was wrong is that the documented list is a *subset*
of CI. Measured on 6 September 2026, four gates CI runs were named nowhere:

* ``ruff check apps/station-api/src packages/technocore-conform/src tests`` -
  the documented ruff runs with ``--directory apps/station-api`` and therefore
  never opens ``tests/``. That is the run which found the B007.
* ``mypy --config-file apps/station-api/pyproject.toml`` - the documented
  ``mypy src`` checks 140 files, CI's checks 142.
* ``npm --prefix apps/station-web run test:e2e``.
* ``python packaging/build_bundle.py`` and the two-file pytest that audits the
  artefact it produces.

This is the repository's own signature defect in new clothes: a check that
looks complete and does not cover everything. ADR-0011 1 diagnosed a sibling
- the gate command's ``-q`` on top of ``pytest.ini``'s, so ``-qq``, so no
summary line for anybody running the gate locally. This one is worse, because
a green local gate is what an agent reports as "geçti" before pushing: the
documentation was not merely stale, it was *load-bearing* and wrong.

Both sides are derived, neither is transcribed
------------------------------------------------
A guard holding its own copy of the command list would be a third place to
drift. So:

* the CI side is parsed out of **every** file in ``.github/workflows``, found
  by globbing the directory. A third workflow is covered the day it lands;
* the documented side is parsed out of the fenced blocks under the gate
  headings in ``AGENTS.md`` and ``CLAUDE.md``.

Gate, setup, CI-only - and why the distinction is enforced rather than noted
-----------------------------------------------------------------------------
Not every CI step is a gate. ``npm ci`` installs; ``uv python install 3.12``
installs; the PyInstaller ``print(__version__)`` step asserts nothing. Telling
an agent to run those before every change would be noise, and loosening the
comparison until it passed would be the same defect this file exists to close.

So every step is classified, and the classification is data the tests check:

* a **gate** must appear verbatim in the documented list;
* :data:`SETUP_STEPS` names the steps that install or publish and check
  nothing about this project's source;
* :data:`CI_ONLY_STEPS` names the steps that *do* assert, but have no local
  command form - both are pwsh scripts that need a GitHub runner (a PATH that
  can be stripped down to a clean-machine profile, ``$env:RUNNER_TEMP``).

A step in neither list and not in the documentation **fails**, so a gate added
to CI tomorrow cannot be quietly re-read as setup. Both lists are also checked
for staleness in the other direction, so neither can become a bucket that
outlives the steps it excuses.

What keeps the parser honest
------------------------------
There is no YAML library in the locked environment and this file does not add
one, so the workflow reader is a small indentation scanner. Two anchors stop
it from passing by reading nothing:

* :func:`test_the_workflow_reader_sees_every_named_step` compares the number
  of steps parsed with the number of ``- name:`` lines on disk. A scanner that
  silently drops a step - the exact failure mode that would make this whole
  file decorative - fails there.
* :func:`test_a_gate_planted_in_a_workflow_is_reported` and
  :func:`test_a_command_dropped_from_the_documentation_is_reported` run the
  comparison over synthetic text, so the deny side is proven in-process rather
  than asserted in a commit message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

#: The two rule files. ``AGENTS.md`` is canonical and ``CLAUDE.md`` says it
#: repeats the same invariants, so a difference between them is a defect on
#: its own - checked by
#: :func:`test_the_two_rule_files_carry_the_same_gate_list`.
DOC_FILES: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md")

#: The headings the two gate blocks live under, in both files. Matched
#: case-sensitively and as a substring of a markdown heading line: Turkish
#: case folding turns ``ı`` into ``I`` and back into ``i``, and a guard that
#: depends on that is a guard that breaks on a locale.
FAST_ANCHOR = "Hızlı kapı"
FULL_ANCHOR = "Tam kapı"

#: Steps that install a toolchain, a locked environment or a pinned browser,
#: or publish an artefact. None of them asserts anything about this
#: repository's source, so none belongs in a list of commands to run before a
#: change. The key is the step identity (see :func:`_identity`).
SETUP_STEPS: dict[str, str] = {
    "action:actions/checkout": "brings the tree onto the runner; runs no project code",
    "action:astral-sh/setup-uv": "installs the pinned uv; a developer already has one",
    "action:actions/setup-node": "installs Node 22; a developer already has one",
    "action:actions/upload-artifact": (
        "runs only on failure and publishes the Playwright artefacts; it asserts nothing"
    ),
    "command:uv python install 3.12": "interpreter install",
    "command:uv sync --locked --project apps/station-api": (
        "environment install from the lockfile. `uv run` syncs the same environment on a "
        "developer machine, so there is nothing extra to run locally. `--locked` does buy "
        "CI one assertion the local gate does not make - that uv.lock is current with "
        "pyproject.toml - and that is stated here rather than hidden: a stale lockfile is "
        "one of the things CI, not the local gate, will catch"
    ),
    "command:npm ci --prefix apps/station-web": (
        "node_modules install from package-lock.json; the same reasoning as uv sync"
    ),
    "command:npm --prefix apps/station-web exec -- playwright install chromium": (
        "downloads the Chromium build @playwright/test pins; a developer installs it once"
    ),
    'command:uv run --project apps/station-api python -c "import PyInstaller; '
    'print(PyInstaller.__version__)"': (
        "prints the packager version so a build by an unpinned PyInstaller is visible in "
        "the log; it has no failure branch of its own"
    ),
}

#: Steps that really do gate the merge but cannot be handed to a developer as
#: a command. Both are pwsh scripts against the runner itself.
CI_ONLY_STEPS: dict[str, str] = {
    "script:Verify the artefact and record its digest": (
        "hashes whatever archive packaging/artifacts holds and prints the digest with the "
        "unsigned-artefact note (ADR-0010 9). It is a few lines of pwsh over the CI "
        "working directory, not a command with a local spelling"
    ),
    "script:Run the artefact with uv and Node removed from PATH": (
        "starts the frozen binary on a runner whose PATH has been stripped of uv, python "
        "and node, then asserts loopback binding, an ephemeral port, 401 on the protected "
        "route, no _MEI unpack and the single-instance lock. A developer machine cannot "
        "be reduced to that profile by a documented one-liner, and $env:RUNNER_TEMP only "
        "exists on the runner"
    ),
}


@dataclass(frozen=True)
class Step:
    """One step of one job, reduced to what the classification needs."""

    workflow: str
    job: str
    name: str
    #: ``command:<normalised shell command>``, ``action:<owner/repo>`` or
    #: ``script:<step name>``. Commands are the identity that matters: the
    #: same command in two jobs is one gate, and a gate renamed in CI must
    #: still resolve to the documented command.
    identity: str

    @property
    def where(self) -> str:
        return f"{self.workflow}:{self.job}:{self.name}"


def _normalise(command: str) -> str:
    """Whitespace-insensitive form of a shell command.

    YAML folding and markdown both leave runs of spaces behind, and a gate
    that differs from its documentation by one space is not drift.
    """
    return " ".join(command.split())


def _step_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Slice a workflow into the raw lines of each ``steps:`` item.

    Returns the line number the item starts on with it, because step names
    repeat across jobs (four jobs check out the tree with the same name) and
    an error message naming the wrong job is worse than none.
    """
    blocks: list[tuple[int, list[str]]] = []
    index = 0
    while index < len(lines):
        header = re.match(r"^(?P<indent> *)steps:\s*$", lines[index])
        index += 1
        if header is None:
            continue
        steps_indent = len(header.group("indent"))
        item_indent: int | None = None
        current: list[str] | None = None
        while index < len(lines):
            raw = lines[index]
            if raw.strip():
                indent = len(raw) - len(raw.lstrip(" "))
                is_item = re.match(r"^ *- (?=\S)", raw) is not None
                starts_item = is_item and indent > steps_indent and (
                    item_indent is None or indent == item_indent
                )
                if starts_item:
                    item_indent = indent
                    current = []
                    blocks.append((index, current))
                elif current is None or item_indent is None or indent <= item_indent:
                    break
            if current is not None:
                current.append(raw)
            index += 1
    return blocks


def _step_fields(block: list[str], where: str) -> dict[str, tuple[str, list[str]]]:
    """The keys of one step, as ``key -> (style, lines)``.

    ``style`` is ``plain`` for an inline scalar, ``|`` or ``>`` for a block
    scalar, ``map`` for a nested mapping such as ``with:``. Anything this
    cannot read is an error rather than a silent drop - a step whose ``run:``
    is not understood is a gate that is not checked.
    """
    head = block[0]
    item_indent = len(head) - len(head.lstrip(" "))
    key_indent = item_indent + 2
    body = [" " * key_indent + head.lstrip(" ")[2:], *block[1:]]

    fields: dict[str, tuple[str, list[str]]] = {}
    index = 0
    while index < len(body):
        raw = body[index]
        if not raw.strip() or raw.strip().startswith("#"):
            index += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        assert indent == key_indent, f"{where}: unexpected indentation at {raw!r}"
        key_line = re.match(r"^ *(?P<key>[a-z][\w-]*):(?:\s+(?P<value>.*))?$", raw)
        assert key_line is not None, f"{where}: cannot read the step line {raw!r}"
        key = key_line.group("key")
        value = (key_line.group("value") or "").strip()
        index += 1

        nested: list[str] = []
        while index < len(body):
            follower = body[index]
            deeper = len(follower) - len(follower.lstrip(" ")) > key_indent
            if follower.strip() and not deeper:
                break
            nested.append(follower)
            index += 1

        if value in {"|", ">", "|-", ">-", "|+", ">+"}:
            fields[key] = (value[0], nested)
        elif value:
            assert not [line for line in nested if line.strip()], (
                f"{where}: `{key}` has an inline value and indented lines under it"
            )
            fields[key] = ("plain", [value])
        else:
            fields[key] = ("map", nested)
    return fields


def _identity(name: str, fields: dict[str, tuple[str, list[str]]], where: str) -> str:
    """The key a step is classified by."""
    if "uses" in fields:
        style, chunk = fields["uses"]
        assert style == "plain", f"{where}: `uses` is not an inline value"
        # `uses: owner/repo@<sha> # v1.2.3` - the pin belongs to the pinning
        # policy in the workflow header, not to this classification.
        reference = chunk[0].split("#", 1)[0].strip()
        return "action:" + reference.split("@", 1)[0]

    assert "run" in fields, f"{where}: the step neither runs a command nor uses an action"
    style, chunk = fields["run"]

    if style == "plain":
        command = chunk[0]
        # A YAML plain scalar ends at ` #`. No `run:` in this repository
        # carries one, and a future one must be noticed rather than truncated.
        assert " #" not in command, f"{where}: an inline `run` carries a YAML comment"
        return "command:" + _normalise(command)

    meaningful = [
        line.strip()
        for line in chunk
        if line.strip() and not line.strip().startswith("#")
    ]
    assert meaningful, f"{where}: the `run` block is empty"

    if style == ">":
        # Folded: the whole block is one command.
        assert len(meaningful) == len(
            [line for line in chunk if line.strip()]
        ), f"{where}: a folded `run` carries a line that reads as a comment"
        return "command:" + _normalise(" ".join(meaningful))

    if len(meaningful) == 1:
        # A literal block holding a single command is still a command; this
        # is what stops `run: |` from becoming a place to hide a gate.
        return "command:" + _normalise(meaningful[0])
    return "script:" + name


def workflow_steps(workflow: str, text: str) -> list[Step]:
    """Every step of one workflow file, in order."""
    lines = text.splitlines()
    jobs: dict[int, str] = {}
    for number, line in enumerate(lines):
        job_line = re.match(r"^ {2}(?P<job>[A-Za-z_][\w-]*):\s*$", line)
        if job_line is not None:
            jobs[number] = job_line.group("job")

    steps: list[Step] = []
    for start, block in _step_blocks(lines):
        job = next(
            (
                name
                for number, name in sorted(jobs.items(), reverse=True)
                if number < start
            ),
            "?",
        )
        where = f"{workflow}:{job}"
        fields = _step_fields(block, where)
        name_field = fields.get("name")
        assert name_field is not None and name_field[0] == "plain", (
            f"{where}: a step has no inline `name`, so the count anchor in "
            "test_the_workflow_reader_sees_every_named_step cannot hold"
        )
        name = name_field[1][0].strip()
        steps.append(
            Step(
                workflow=workflow,
                job=job,
                name=name,
                identity=_identity(name, fields, f"{where}:{name}"),
            )
        )
    return steps


@dataclass(frozen=True)
class Classified:
    """What a set of workflow steps turned into."""

    gates: dict[str, list[Step]]
    setup: list[Step]
    ci_only: list[Step]
    unclassified: list[Step]


def classify(steps: list[Step]) -> Classified:
    """Split steps into gates, allow-listed steps and the rest.

    A step is a gate by exclusion: everything that is not named in one of the
    two allow-lists has to be a command a developer can run, and therefore has
    to appear in the documentation.
    """
    gates: dict[str, list[Step]] = {}
    setup: list[Step] = []
    ci_only: list[Step] = []
    unclassified: list[Step] = []
    for step in steps:
        if step.identity in SETUP_STEPS:
            setup.append(step)
        elif step.identity in CI_ONLY_STEPS:
            ci_only.append(step)
        elif step.identity.startswith("command:"):
            gates.setdefault(step.identity[len("command:") :], []).append(step)
        else:
            unclassified.append(step)
    return Classified(gates, setup, ci_only, unclassified)


def documented_blocks(document: str, text: str) -> tuple[list[str], list[str]]:
    """The two documented command lists: the fast gate, then what the full
    gate adds to it."""
    return (
        _fenced_commands(document, text, FAST_ANCHOR),
        _fenced_commands(document, text, FULL_ANCHOR),
    )


def _fenced_commands(document: str, text: str, anchor: str) -> list[str]:
    lines = text.splitlines()
    heading = next(
        (
            number
            for number, line in enumerate(lines)
            if re.match(r"^#{1,6} ", line) and anchor in line
        ),
        None,
    )
    assert heading is not None, (
        f"{document} has no heading containing {anchor!r}; the gate list cannot be "
        "found, and a gate list that cannot be found is not a gate list"
    )

    opening = None
    for number in range(heading + 1, len(lines)):
        if lines[number].startswith("```"):
            opening = number
            break
        assert not re.match(r"^#{1,6} ", lines[number]), (
            f"{document}: the {anchor!r} heading is followed by another heading before "
            "any code block"
        )
    assert opening is not None, f"{document}: {anchor!r} is followed by no code block"
    assert lines[opening].strip() == "```bash", (
        f"{document}: the {anchor!r} block opens with {lines[opening]!r}; the gate list "
        "is shell, and a differently tagged block is probably not it"
    )

    closing = next(
        (
            number
            for number in range(opening + 1, len(lines))
            if lines[number].strip() == "```"
        ),
        None,
    )
    assert closing is not None, f"{document}: the {anchor!r} block is never closed"
    return [
        _normalise(line)
        for line in lines[opening + 1 : closing]
        if line.strip() and not line.strip().startswith("#")
    ]


# ---------------------------------------------------------------------------
# The repository's own files
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_files(repo_root: Path) -> list[Path]:
    directory = repo_root / ".github" / "workflows"
    assert directory.is_dir(), "there are no workflows, so there is no CI to compare to"
    found = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )
    assert found, "the workflow directory holds no workflow"
    return found


@pytest.fixture(scope="module")
def ci_steps(workflow_files: list[Path]) -> list[Step]:
    steps: list[Step] = []
    for path in workflow_files:
        steps.extend(workflow_steps(path.name, path.read_text(encoding="utf-8")))
    return steps


@pytest.fixture(scope="module")
def documented(repo_root: Path) -> dict[str, tuple[list[str], list[str]]]:
    return {
        document: documented_blocks(
            document, (repo_root / document).read_text(encoding="utf-8")
        )
        for document in DOC_FILES
    }


def test_the_workflow_reader_sees_every_named_step(
    workflow_files: list[Path], ci_steps: list[Step]
) -> None:
    """The anchor: parsed steps against ``- name:`` lines on disk.

    Everything else in this file compares two sets. A reader that quietly
    stopped at the first job would make every one of those comparisons pass
    while covering a third of CI.
    """
    on_disk = 0
    for path in workflow_files:
        on_disk += len(
            re.findall(r"^ *- name:", path.read_text(encoding="utf-8"), re.MULTILINE)
        )
    assert on_disk > 0, "no workflow step is named, so this anchor proves nothing"
    assert len(ci_steps) == on_disk, (
        f"the reader found {len(ci_steps)} steps and the files hold {on_disk} "
        "`- name:` lines; the workflow scan is incomplete"
    )


def test_every_ci_step_is_a_gate_a_setup_step_or_a_ci_only_step(
    ci_steps: list[Step],
) -> None:
    """No step may be unaccounted for.

    This is the half that stops the classification from being a comment: a
    step whose identity is not a command and is in neither allow-list has
    nowhere to go.
    """
    split = classify(ci_steps)
    assert split.unclassified == [], (
        "these CI steps are neither a command a developer can run nor named in "
        "SETUP_STEPS/CI_ONLY_STEPS: "
        + ", ".join(f"{step.where} ({step.identity})" for step in split.unclassified)
    )


def test_every_gate_ci_runs_is_documented(
    ci_steps: list[Step], documented: dict[str, tuple[list[str], list[str]]]
) -> None:
    """CI -> documentation. This is the direction the B007 escaped through."""
    split = classify(ci_steps)
    assert split.gates, "no gate was found in CI, so this comparison is vacuous"
    for document, (fast, extra) in documented.items():
        listed = set(fast) | set(extra)
        missing = sorted(set(split.gates) - listed)
        assert missing == [], (
            f"{document} does not name these gates, so a local run of its list can be "
            "green while CI is red: " + "; ".join(missing)
        )


def test_every_documented_command_is_a_gate_ci_runs(
    ci_steps: list[Step], documented: dict[str, tuple[list[str], list[str]]]
) -> None:
    """Documentation -> CI, so the list cannot grow a command nothing enforces."""
    split = classify(ci_steps)
    for document, (fast, extra) in documented.items():
        for command in [*fast, *extra]:
            assert command in split.gates, (
                f"{document} lists `{command}`, which no workflow runs; either CI lost a "
                "gate or the documentation invented one"
            )


def test_the_fast_gate_and_the_rest_do_not_overlap(
    documented: dict[str, tuple[list[str], list[str]]],
) -> None:
    """The second block is what the full gate *adds*, so the union is the
    whole gate set and a command deleted from either block is missing from
    it."""
    for document, (fast, extra) in documented.items():
        assert len(set(fast)) == len(fast), f"{document}: the fast block repeats a command"
        assert len(set(extra)) == len(extra), f"{document}: the full block repeats a command"
        overlap = sorted(set(fast) & set(extra))
        assert overlap == [], (
            f"{document}: these commands are in both blocks, so the second block is no "
            "longer 'what the full gate adds': " + "; ".join(overlap)
        )


def test_the_two_rule_files_carry_the_same_gate_list(
    documented: dict[str, tuple[list[str], list[str]]],
) -> None:
    """``CLAUDE.md`` says it repeats ``AGENTS.md``; this is where that is true."""
    canonical = documented["AGENTS.md"]
    for document, blocks in documented.items():
        assert blocks == canonical, (
            f"{document} and AGENTS.md give different gate lists. AGENTS.md is canonical "
            f"(AGENTS.md preamble, CLAUDE.md preamble): {canonical!r} vs {blocks!r}"
        )


def test_no_allow_listed_step_is_also_documented_as_a_gate(
    ci_steps: list[Step], documented: dict[str, tuple[list[str], list[str]]]
) -> None:
    """A step is one thing or the other.

    Without this, a gate could be excused in ``SETUP_STEPS`` *and* listed in
    the documentation, and the two halves would each look defensible.
    """
    excused = {
        step.identity[len("command:") :]
        for step in ci_steps
        if step.identity.startswith("command:")
        and step.identity in (SETUP_STEPS.keys() | CI_ONLY_STEPS.keys())
    }
    for document, (fast, extra) in documented.items():
        both = sorted(excused & (set(fast) | set(extra)))
        assert both == [], (
            f"{document} documents these as gates while this file excuses them as setup: "
            + "; ".join(both)
        )


def test_the_allow_lists_hold_no_stale_entry(ci_steps: list[Step]) -> None:
    """Neither list may outlive the steps it excuses.

    An allow-list nobody prunes is how a classification turns into a bucket
    (the same reasoning as ``_ROWS_WITHOUT_A_PYTHON_TEST`` in
    ``test_security_invariants_doc.py``).
    """
    present = {step.identity for step in ci_steps}
    for label, entries in (("SETUP_STEPS", SETUP_STEPS), ("CI_ONLY_STEPS", CI_ONLY_STEPS)):
        stale = sorted(set(entries) - present)
        assert stale == [], (
            f"{label} excuses steps no workflow has any more: " + "; ".join(stale)
        )
    for label, entries in (("SETUP_STEPS", SETUP_STEPS), ("CI_ONLY_STEPS", CI_ONLY_STEPS)):
        for identity, reason in entries.items():
            assert reason.strip(), f"{label}[{identity}] excuses a step without a reason"


# ---------------------------------------------------------------------------
# The deny side, proven in-process
# ---------------------------------------------------------------------------

#: A minimal workflow with one setup step and one gate. Small on purpose: the
#: planted-mutation tests below have to fail for the reason they name, not
#: because a large fixture drifted.
_PROBE_WORKFLOW = """\
name: probe

jobs:
  probe:
    runs-on: windows-latest
    steps:
      - name: Install Python 3.12
        run: uv python install 3.12

      - name: eslint
        run: npm --prefix apps/station-web run lint
"""

_PROBE_DOC = """\
## Kapılar

### Hızlı kapı (her değişiklikte)

```bash
npm --prefix apps/station-web run lint
```

### Tam kapı (push öncesi)

```bash
uv run --directory apps/station-api pytest ../../tests
```
"""


def _drift(workflow: str, document: str) -> tuple[list[str], list[str]]:
    """Both directions of the comparison, as plain lists."""
    split = classify(workflow_steps("probe.yml", workflow))
    fast, extra = documented_blocks("probe.md", document)
    listed = set(fast) | set(extra)
    undocumented = sorted(set(split.gates) - listed)
    unenforced = sorted(listed - set(split.gates))
    return undocumented, unenforced


def test_the_probe_pair_agrees_before_it_is_mutated() -> None:
    """The control. Without it a mutation could 'fail' because the fixture was
    broken to begin with."""
    workflow = _PROBE_WORKFLOW.replace(
        "        run: npm --prefix apps/station-web run lint",
        "        run: npm --prefix apps/station-web run lint\n\n"
        "      - name: pytest\n"
        "        run: uv run --directory apps/station-api pytest ../../tests",
    )
    assert _drift(workflow, _PROBE_DOC) == ([], [])


def test_a_gate_planted_in_a_workflow_is_reported() -> None:
    """A new CI gate the documentation does not mention."""
    workflow = _PROBE_WORKFLOW + (
        "\n      - name: a gate nobody wrote down\n"
        "        run: uv run --project apps/station-api ruff check tests\n"
    )
    undocumented, _ = _drift(workflow, _PROBE_DOC)
    assert "uv run --project apps/station-api ruff check tests" in undocumented


def test_a_one_line_block_scalar_is_still_read_as_a_command() -> None:
    """A gate written the two ways a block scalar could have hidden it."""
    for style in (">", "|"):
        workflow = _PROBE_WORKFLOW + (
            f"\n      - name: a gate in a block scalar\n"
            f"        run: {style}\n"
            "          uv run --directory apps/station-api pytest ../../tests\n"
        )
        undocumented, _ = _drift(workflow, _PROBE_DOC)
        assert undocumented == [], (
            f"style {style}: this command *is* documented and must not be reported"
        )
        steps = workflow_steps("probe.yml", workflow)
        assert steps[-1].identity == (
            "command:uv run --directory apps/station-api pytest ../../tests"
        ), f"style {style}: a block scalar hid a one-line command from the classification"


def test_a_command_dropped_from_the_documentation_is_reported() -> None:
    """The mutation that produced the defect: the documented list is narrower
    than CI."""
    workflow = _PROBE_WORKFLOW.replace(
        "        run: npm --prefix apps/station-web run lint",
        "        run: npm --prefix apps/station-web run lint\n\n"
        "      - name: pytest\n"
        "        run: uv run --directory apps/station-api pytest ../../tests",
    )
    thinned = _PROBE_DOC.replace(
        "uv run --directory apps/station-api pytest ../../tests\n", ""
    )
    undocumented, _ = _drift(workflow, thinned)
    assert undocumented == ["uv run --directory apps/station-api pytest ../../tests"]


def test_a_command_documented_but_never_run_is_reported() -> None:
    """The other direction: the documentation names a gate CI dropped."""
    _, unenforced = _drift(_PROBE_WORKFLOW, _PROBE_DOC)
    assert unenforced == ["uv run --directory apps/station-api pytest ../../tests"]


def test_a_missing_heading_is_an_error_rather_than_an_empty_list() -> None:
    """An empty gate list would make every comparison above pass."""
    with pytest.raises(AssertionError, match="Tam kapı"):
        documented_blocks("probe.md", _PROBE_DOC.replace(FULL_ANCHOR, "Bir şey"))
