"""The run ceiling: four measurable units, written at compile time, never written to.

ADR-0008 4. The units are **tool-call count**, **model-call count**,
**wall-clock seconds** and **concurrency (=1)**.

There is still no token count and no currency, and the reason is now stronger
than it was rather than weaker. The model lane is open (Package H4), the
provider does send a ``usage`` object and it does send a ``cost`` member - and
neither becomes a ceiling here. ``usage`` is a count of somebody else's
tokenisation, ``cost`` is a string this build cannot verify, and a limit
expressed in either is a limit whose enforcement depends on the party being
limited. SI-250 says a figure the provider did not send is never invented;
this says a figure the provider *did* send is still not a control. Both are
recorded, beside the call they came from, and neither is read by
:func:`check`.

**Model-call count** is the unit that was added instead, and it is added
because it is the one this process can count on its own: Station makes the
request, so Station knows how many it made, and the number means the same
thing to the user as it does to the code. That is the whole test a unit has to
pass to be here.

A ceiling denominated in something the product cannot measure is a ceiling
that gets rounded to "unlimited" the first time anybody needs a number.

Why this lives in ``agent/`` and not in ``tasks/``
--------------------------------------------------
``test_the_task_layer_opens_no_budget_field`` refuses every identifier
containing ``budget``, ``cost``, ``spend``, ``quota`` or ``credit`` anywhere
in ``station_api/tasks`` and ``station_api/modules``, and SI-225's claim -
"the task layer has no budget field" - is meant to stay **literally** true
rather than becoming a sentence about where the field moved. So the task
layer keeps none, this package owns the ceiling, and the two statements are
both true at once.

"The agent cannot raise its own ceiling" is structural
------------------------------------------------------
Three separate things make it so, and each is checked:

* :data:`CEILING` is a frozen dataclass built once, at import, from literals.
  There is no constructor argument, no environment variable and no row.
* it is **not represented as a tool**. The registry in
  :mod:`station_api.agent.tools` has no entry that reads or writes a ceiling,
  and it cannot grow one at runtime because it is a tuple literal.
* **no code path writes it.** An AST scan over this package requires that
  ``CEILING`` is assigned exactly once, at module level here, and that no
  attribute of a ceiling is ever an assignment target. ``frozen=True`` refuses
  the write at runtime; the scan refuses it in review, which is where a
  reviewer sees it first.

What a verdict is
-----------------
:func:`check` is a pure function returning a value, the shape
``write_gate.evaluate`` and ``validate_transition`` both use. The runner asks
it **before** every tool call, so the count that matters is the one that would
result from making the call rather than the one already spent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

#: The three units, named once so a surface can print them and a test can
#: assert that a fourth - a token, a currency - never appears.
BUDGET_UNITS: Final[tuple[str, ...]] = (
    "tool_call_count",
    "model_call_count",
    "wall_clock_seconds",
    "concurrency",
)

#: Units this product refuses to denominate a ceiling in, and the reason
#: travels with them. It used to be "neither is measurable here"; the model
#: lane is open now and the provider reports both, so the reason is the
#: sharper one: a ceiling enforced in a number the counterparty supplies is a
#: ceiling the counterparty sets.
REFUSED_UNITS: Final[tuple[str, ...]] = ("token", "currency")

REFUSED_UNITS_DETAIL = (
    "Token ve para birimi tavan olarak kullanilmaz. Saglayici bir kullanim "
    "ve maliyet degeri bildirdiginde bu deger cagrinin yaninda oldugu gibi "
    "kaydedilir; ne uydurulur ne de sinir olarak okunur. Sinir, Station'in "
    "kendi sayabildigi birimlerle ifade edilir: arac cagrisi sayisi, model "
    "cagrisi sayisi, duvar saati suresi ve eszamanlilik (=1)."
)


@dataclass(frozen=True, slots=True)
class RunCeiling:
    """One run's limits. Constructed once, at import, and only read after."""

    max_tool_calls: int
    #: Most model turns one task's planning session may spend. Deliberately
    #: small: every turn produces a plan a person has to read before it can
    #: run, so a large number here would be a promise of work nobody has time
    #: to approve.
    max_model_calls: int
    max_wall_clock_seconds: int
    #: Typed as a literal so widening it is a type error at every call site
    #: rather than a runtime surprise at one of them - the ``SCAN_METHOD``
    #: pattern. One tool call at a time is what makes a run replayable and
    #: what makes "stop blocks the next call" a complete sentence.
    max_concurrency: Literal[1]


#: The ceiling. A module-level literal: the only place in this build where a
#: limit is decided, and there is no second one.
CEILING: Final[RunCeiling] = RunCeiling(
    max_tool_calls=32,
    max_model_calls=8,
    max_wall_clock_seconds=120,
    max_concurrency=1,
)


@dataclass(frozen=True, slots=True)
class RunUsage:
    """What a run has spent so far, in the units above and no others."""

    tool_calls: int
    #: Model turns spent by this task's planning session. No default: a
    #: caller has to state it, so the runner's "I made no model call" and the
    #: planner's count are both deliberate rather than one of them being
    #: whatever the constructor happened to fill in.
    model_calls: int
    elapsed_seconds: float

    @property
    def concurrency(self) -> Literal[1]:
        """Always one. There is no code path that runs two tools at once."""
        return 1


@dataclass(frozen=True, slots=True)
class BudgetVerdict:
    """Whether one more tool call is permitted, and precisely why not."""

    allowed: bool
    reason: str
    detail: str


#: The machine-readable reasons, named once.
TOOL_CALLS_EXHAUSTED = "tool_calls_exhausted"
MODEL_CALLS_EXHAUSTED = "model_calls_exhausted"
WALL_CLOCK_EXHAUSTED = "wall_clock_exhausted"


def check(usage: RunUsage, *, ceiling: RunCeiling | None = None) -> BudgetVerdict:
    """May one more tool call be made? Pure function; the runner calls it.

    ``ceiling`` is a keyword argument so a test can drive a small ceiling
    without the product having a way to supply one: no route, no request body
    and no row reaches this parameter, and a test asserts that every call site
    inside the package omits it.

    It defaults to ``None`` and resolves :data:`CEILING` **inside the body**
    rather than taking the constant as a default value. A default is bound
    once, when the function is defined, which would have made the constant
    unobservable to a test that replaced it - and a ceiling nobody can vary is
    a ceiling whose exhaustion path is never executed. Resolving it here keeps
    the product's single source of truth while leaving the refusal reachable.
    """
    ceiling = CEILING if ceiling is None else ceiling
    if usage.tool_calls >= ceiling.max_tool_calls:
        return BudgetVerdict(
            allowed=False,
            reason=TOOL_CALLS_EXHAUSTED,
            detail=(
                f"Arac cagrisi tavanina ulasildi ({usage.tool_calls}/"
                f"{ceiling.max_tool_calls}). Calisma durduruldu; yeni cagri "
                "yapilmaz."
            ),
        )
    if usage.model_calls >= ceiling.max_model_calls:
        return BudgetVerdict(
            allowed=False,
            reason=MODEL_CALLS_EXHAUSTED,
            detail=(
                f"Model cagrisi tavanina ulasildi ({usage.model_calls}/"
                f"{ceiling.max_model_calls}). Bu gorev icin yeni bir model "
                "cagrisi yapilmaz; kaydedilmis bir plan elle surdurulebilir."
            ),
        )
    if usage.elapsed_seconds >= ceiling.max_wall_clock_seconds:
        return BudgetVerdict(
            allowed=False,
            reason=WALL_CLOCK_EXHAUSTED,
            detail=(
                f"Sure tavanina ulasildi ({int(usage.elapsed_seconds)}/"
                f"{ceiling.max_wall_clock_seconds} saniye). Calisma "
                "durduruldu; yeni cagri yapilmaz."
            ),
        )
    return BudgetVerdict(allowed=True, reason="", detail="")


def describe_ceiling(ceiling: RunCeiling | None = None) -> str:
    """One safe sentence about the limits, for a screen and an activity row."""
    ceiling = CEILING if ceiling is None else ceiling
    return (
        f"Tavan: en cok {ceiling.max_tool_calls} arac cagrisi, en cok "
        f"{ceiling.max_model_calls} model cagrisi, en cok "
        f"{ceiling.max_wall_clock_seconds} saniye, eszamanlilik "
        f"{ceiling.max_concurrency}. Tavan derleme zamaninda yazilir; hicbir "
        "kod yolu onu degistirmez ve arac registry'sinde onu degistiren bir "
        "arac yoktur."
    )


__all__ = [
    "BUDGET_UNITS",
    "CEILING",
    "MODEL_CALLS_EXHAUSTED",
    "REFUSED_UNITS",
    "REFUSED_UNITS_DETAIL",
    "TOOL_CALLS_EXHAUSTED",
    "WALL_CLOCK_EXHAUSTED",
    "BudgetVerdict",
    "RunCeiling",
    "RunUsage",
    "check",
    "describe_ceiling",
]
