"""The package version, in one place.

A separate module so ``selftest`` can report the version without importing
``__init__``, which imports ``selftest``. Keeping it here breaks that cycle
without resorting to a deferred import inside a function.
"""

from __future__ import annotations

__version__ = "0.3.0"

__all__ = ["__version__"]
