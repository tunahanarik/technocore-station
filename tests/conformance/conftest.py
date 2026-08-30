"""Fixtures shared by the conformance suite.

The Unicode corpus is built once per session. It is deterministic - no random
sampling - so a failure is reproducible from the reported code point alone,
which matters when the failing input is an invisible character.
"""

from __future__ import annotations

import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.conformance.oracle import load_official_sweep

#: Categories the sweep replaces. Duplicated here on purpose: the corpus must
#: be able to prove it covers them without importing the code under test.
FORBIDDEN_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Zl", "Zp")

#: Every code point below this is enumerated exhaustively. It covers the whole
#: of Cc, Zl, Zp, most of Cf, and a wide spread of ordinary scripts.
_DENSE_LIMIT = 0x3000


@pytest.fixture(scope="session")
def vendor_root(repo_root: Path) -> Path:
    return repo_root / "vendor" / "technocore-reference"


@pytest.fixture(scope="session")
def official_sweep(vendor_root: Path) -> Callable[[str, int], str]:
    """The pinned ``clean_text``, executed from its own AST."""
    return load_official_sweep(vendor_root)


def _interesting_code_points() -> list[int]:
    """Code points chosen to hit every hazard the sweep exists for."""
    points = list(range(_DENSE_LIMIT))

    # The surrogate range: never valid alone in stored text, and the one
    # region a naive UTF-8 round-trip would corrupt rather than sweep.
    points += list(range(0xD800, 0xE000, 7))

    # Private use, BMP and both astral planes.
    points += list(range(0xE000, 0xF900, 23))
    points += list(range(0xF0000, 0xF0100))
    points += list(range(0x100000, 0x100080))

    # Unicode tag characters: the invisible-instruction smuggling vector.
    points += list(range(0xE0000, 0xE0080))

    # Variation selectors and other format characters above the BMP.
    points += list(range(0xE0100, 0xE0140))

    # A spread of ordinary astral text: music, CJK extension B, emoji.
    points += list(range(0x1D100, 0x1D180, 3))
    points += list(range(0x20000, 0x20080, 5))
    points += list(range(0x1F300, 0x1F600, 7))

    # Line and paragraph separators, plus the Zs family that strip() touches
    # but the replacement step does not.
    points += [0x2028, 0x2029, 0x00A0, 0x1680, 0x202F, 0x205F, 0x3000]

    return sorted(set(points))


@pytest.fixture(scope="session")
def unicode_code_points() -> list[int]:
    return _interesting_code_points()


@pytest.fixture(scope="session")
def unicode_corpus(unicode_code_points: list[int]) -> list[str]:
    """One input string per code point, each with visible text either side.

    The surrounding ``a``/``b`` guarantee something survives the sweep, so a
    difference shows up as different output rather than as a shared refusal.
    """
    return [f"a{chr(point)}b" for point in unicode_code_points]


def category_counts(code_points: list[int]) -> dict[str, int]:
    """How many corpus code points fall in each general category."""
    counts: dict[str, int] = {}
    for point in code_points:
        category = unicodedata.category(chr(point))
        counts[category] = counts.get(category, 0) + 1
    return counts


@pytest.fixture(scope="session")
def python_executable() -> str:
    """The interpreter running the tests, for CLI subprocess calls."""
    return sys.executable
