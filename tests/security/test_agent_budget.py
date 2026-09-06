"""The run ceiling: four measurable units, and no code path that raises it.

ADR-0008 4 makes two decisions and this file holds both.

**The units are the ones this build can measure.** Tool calls, model calls,
wall-clock seconds, concurrency of one.

The fourth unit is new in Package H4 and the file was rewritten around it
rather than having an assertion relaxed. The reason the ceiling had three
units was that the model lane was closed; the model lane is open now, so
**model-call count** is something this process can count for itself - Station
makes the request, so Station knows how many it made.

What did **not** change is the refusal of tokens and currency, and its reason
got stronger rather than weaker. The provider now does send a ``usage``
object and a ``cost`` member, and neither is a ceiling here: a limit
denominated in a number the counterparty supplies is a limit the counterparty
sets. Both are recorded beside the call they came from and neither is read by
``check``, which ``test_there_is_no_token_and_no_currency_unit`` still holds
in place. A ceiling denominated in something the product cannot count is a
ceiling that becomes "unlimited" the first time anybody needs a number out of
it.

**"The agent cannot raise its own ceiling" is structural.** Three independent
things make it so and each is checked here: the ceiling is a frozen dataclass
built from literals at import; it is not represented as a tool, so there is
nothing to call; and no code path writes it, which an AST scan pins the way
``test_only_the_transition_method_writes_a_task_state`` pins the state writer.
The scan is then driven against a planted writer, because a structural test
that has never fired is a structural test nobody has verified.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from station_api.agent.budget import (
    BUDGET_UNITS,
    CEILING,
    MODEL_CALLS_EXHAUSTED,
    REFUSED_UNITS,
    TOOL_CALLS_EXHAUSTED,
    WALL_CLOCK_EXHAUSTED,
    RunCeiling,
    RunUsage,
    check,
    describe_ceiling,
)
from station_api.agent.tools import TOOLS

pytestmark = pytest.mark.security

#: The four units, typed out rather than imported. An oracle read out of the
#: constant under test proves only that the code agrees with itself.
EXPECTED_UNITS = (
    "tool_call_count",
    "model_call_count",
    "wall_clock_seconds",
    "concurrency",
)

#: The units this product refuses to denominate a ceiling in.
EXPECTED_REFUSED_UNITS = ("token", "currency")

#: Names that would be a ceiling field. Used by the AST scan below.
#:
#: ``max_model_calls`` joined the list on the commit that added the field.
#: A scan that knew three of four names would have let the newest ceiling -
#: the one guarding the only lane that spends the user's money - be written
#: from anywhere, which is precisely the hole this scan exists to close.
CEILING_FIELDS = (
    "max_tool_calls",
    "max_model_calls",
    "max_wall_clock_seconds",
    "max_concurrency",
)


def _package(api_source_root: Path) -> list[Path]:
    paths = sorted((api_source_root / "station_api" / "agent").rglob("*.py"))
    assert paths, "the agent package should not be empty"
    return paths


def _ceiling_writers(paths: list[Path]) -> list[str]:
    """Every assignment to ``CEILING`` or to a ceiling field, with its file.

    Four spellings, for ``_StateWriteFinder``'s reason: plain assignment,
    annotated assignment, augmented assignment and ``setattr`` with a literal
    name. A scan that only knew the first would miss ``CEILING.max_tool_calls
    += 10`` and ``setattr(CEILING, "max_tool_calls", 999)``.

    The module-level definition in ``budget.py`` is excluded by *position*, not
    by name: it is the one assignment at module scope in that file, and
    everything else is an offender.
    """
    offenders: list[str] = []

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_level = {
            id(node)
            for node in tree.body
            if isinstance(node, ast.AnnAssign | ast.Assign)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign | ast.Assign | ast.AugAssign):
                if id(node) in module_level and path.name == "budget.py":
                    continue
                targets = (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else [node.target]
                )
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == "CEILING":
                        offenders.append(f"{path.name}:{node.lineno} CEILING")
                    if isinstance(target, ast.Attribute) and target.attr in (
                        *CEILING_FIELDS,
                        "CEILING",
                    ):
                        offenders.append(f"{path.name}:{node.lineno} .{target.attr}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "setattr"
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in (*CEILING_FIELDS, "CEILING")
            ):
                offenders.append(f"{path.name}:{node.lineno} setattr")
    return offenders


# ---------------------------------------------------------------------------
# The units
# ---------------------------------------------------------------------------


def test_the_units_are_the_ones_this_build_can_measure() -> None:
    """Four now, and the fourth is here because it became measurable.

    It said *three* until Package H4 and the change is a change of fact: a
    unit is allowed here when this process can count it without asking
    anybody, and model calls became such a unit the moment Station started
    making them. The test is rewritten rather than loosened - the tuple is
    still written out by hand and still compared for equality, so a fifth
    unit is a change somebody reviews.
    """
    assert BUDGET_UNITS == EXPECTED_UNITS


def test_there_is_no_token_and_no_currency_unit() -> None:
    """Stated as a refusal with a reason, not left as an absence.

    An absent field is something a reader has to notice. A named refusal is
    something they are told - and the reason it carries is now the stronger
    one. It used to be "there is no usage figure to read"; the model lane is
    open and the provider reports both a token count and a cost, so the
    reason is that a ceiling enforced in a number the counterparty supplies
    is a ceiling the counterparty sets. SI-250's rule - never invent a figure
    the provider did not send - is unchanged and sits beside it.
    """
    assert REFUSED_UNITS == EXPECTED_REFUSED_UNITS
    for refused in REFUSED_UNITS:
        assert refused not in BUDGET_UNITS


def test_concurrency_is_one_and_typed_as_a_literal() -> None:
    """One tool call at a time, so a run is replayable and a stop is complete."""
    assert CEILING.max_concurrency == 1
    assert RunUsage(tool_calls=0, model_calls=0, elapsed_seconds=0.0).concurrency == 1


# ---------------------------------------------------------------------------
# The ceiling cannot be raised
# ---------------------------------------------------------------------------


def test_the_ceiling_is_frozen_at_runtime() -> None:
    with pytest.raises(FrozenInstanceError):
        CEILING.max_tool_calls = 10_000  # type: ignore[misc]


def test_the_ceiling_is_not_represented_as_a_tool() -> None:
    """There is nothing to call, which is the first of the three locks.

    A ceiling exposed as a tool would be a ceiling the plan can name, and a
    plan is written by a person who might be persuaded. It is simply not in
    the registry, and no tool's parameters mention one.
    """
    for record in TOOLS:
        haystack = f"{record.id.value} {record.purpose}".lower()
        for field in CEILING_FIELDS:
            assert field not in haystack, record.id
        for word in ("tavan", "ceiling", "limit"):
            assert word not in {param.name for param in record.params}, record.id


def test_no_code_path_writes_the_ceiling(api_source_root: Path) -> None:
    """The structural lock, read off the syntax tree.

    ``frozen=True`` refuses the write at runtime; this refuses it in review,
    which is where a reviewer meets it first. The only assignment permitted is
    the module-level definition in ``budget.py``.
    """
    assert _ceiling_writers(_package(api_source_root)) == []


def test_the_ceiling_write_scan_would_see_a_planted_writer(tmp_path: Path) -> None:
    """Guards the guard, on a throwaway tree, in all four spellings."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def raise_it():\n"
        "    CEILING = RunCeiling(max_tool_calls=9999)\n"
        "    CEILING.max_tool_calls = 9999\n"
        "    CEILING.max_tool_calls += 1\n"
        '    setattr(CEILING, "max_tool_calls", 9999)\n',
        encoding="utf-8",
    )

    offenders = _ceiling_writers([planted])

    assert len(offenders) == 4, offenders


def test_the_ceiling_default_is_never_supplied_by_a_call_site(
    api_source_root: Path,
) -> None:
    """``check(usage, ceiling=...)`` exists for tests and for nothing else.

    The keyword is there so a test can drive a small ceiling without the
    product having a way to supply one. This asserts the product never does:
    no call inside the package passes ``ceiling``, so no request body, row or
    environment value can reach it.
    """
    offenders: list[str] = []
    for path in _package(api_source_root):
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
            if name in {"check", "describe_ceiling"}:
                offenders.extend(
                    f"{path.name}:{node.lineno}"
                    for keyword in node.keywords
                    if keyword.arg == "ceiling"
                )
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def test_a_run_under_the_ceiling_is_permitted() -> None:
    verdict = check(RunUsage(tool_calls=0, model_calls=0, elapsed_seconds=0.0))

    assert verdict.allowed is True
    assert verdict.reason == ""


def test_the_tool_call_ceiling_refuses_by_name() -> None:
    verdict = check(
        RunUsage(
            tool_calls=CEILING.max_tool_calls, model_calls=0, elapsed_seconds=0.0
        )
    )

    assert verdict.allowed is False
    assert verdict.reason == TOOL_CALLS_EXHAUSTED
    assert str(CEILING.max_tool_calls) in verdict.detail


def test_the_wall_clock_ceiling_refuses_by_name() -> None:
    """A separate reason from the call ceiling. Two limits, two sentences.

    A run that stopped because it took too long and a run that stopped because
    it made too many calls need different answers - one of them means "split
    the work", the other means "your input is slow".
    """
    verdict = check(
        RunUsage(
            tool_calls=0,
            model_calls=0,
            elapsed_seconds=float(CEILING.max_wall_clock_seconds),
        )
    )

    assert verdict.allowed is False
    assert verdict.reason == WALL_CLOCK_EXHAUSTED


def test_the_model_call_ceiling_refuses_by_name() -> None:
    """A third reason, because a third thing can run out.

    "You have asked the model as often as this task may" is neither "your
    plan is too long" nor "your input is slow", and a person who cannot tell
    the three apart cannot act on any of them. The refusal names the count
    and the ceiling, and it says what is still possible: a plan that is
    already recorded can still be run by hand.
    """
    verdict = check(
        RunUsage(
            tool_calls=0,
            model_calls=CEILING.max_model_calls,
            elapsed_seconds=0.0,
        )
    )

    assert verdict.allowed is False
    assert verdict.reason == MODEL_CALLS_EXHAUSTED
    assert verdict.reason != TOOL_CALLS_EXHAUSTED
    assert str(CEILING.max_model_calls) in verdict.detail


def test_the_call_ceiling_is_checked_before_the_clock() -> None:
    """Order matters when several are exhausted: the count is the actionable one.

    All three limits are driven at once, so the order is pinned rather than
    inferred from two of them. A build that reported the clock first would
    tell a person to wait when the answer is that their plan is too long.
    """
    verdict = check(
        RunUsage(
            tool_calls=CEILING.max_tool_calls,
            model_calls=CEILING.max_model_calls,
            elapsed_seconds=float(CEILING.max_wall_clock_seconds),
        )
    )

    assert verdict.reason == TOOL_CALLS_EXHAUSTED


def test_a_smaller_ceiling_can_be_driven_without_the_product_having_one() -> None:
    tiny = RunCeiling(
        max_tool_calls=1,
        max_model_calls=1,
        max_wall_clock_seconds=1,
        max_concurrency=1,
    )
    nothing_spent = RunUsage(tool_calls=0, model_calls=0, elapsed_seconds=0.0)

    assert check(nothing_spent, ceiling=tiny).allowed
    assert not check(
        RunUsage(tool_calls=1, model_calls=0, elapsed_seconds=0.0), ceiling=tiny
    ).allowed
    assert not check(
        RunUsage(tool_calls=0, model_calls=1, elapsed_seconds=0.0), ceiling=tiny
    ).allowed


def test_the_ceiling_sentence_names_every_unit_and_no_refused_one() -> None:
    """Every limit the ceiling has appears in the sentence a person reads.

    A limit that is enforced and not printed is a limit somebody meets by
    surprise, which is how the model-call ceiling would have arrived if the
    sentence had been left at three numbers.
    """
    sentence = describe_ceiling()

    assert str(CEILING.max_tool_calls) in sentence
    assert str(CEILING.max_model_calls) in sentence
    assert str(CEILING.max_wall_clock_seconds) in sentence
    assert "eszamanlilik" in sentence
    for refused in ("token", "dolar", "usd", "para"):
        assert refused not in sentence.lower()
    assert not set(sentence) & set("çğıöşüÇĞİÖŞÜ")
