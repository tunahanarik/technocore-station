"""Shipped TEST-ONLY conformance vectors.

A package rather than a bare directory so ``importlib.resources`` can find
the bundle inside an installed wheel, where there is no filesystem path to
compute from ``__file__``.

The bundle is derived from the pinned official reference by
``tests/conformance/vector_builder.py`` and its SHA-256 is pinned in
``technocore_conform.selftest``. Every seed inside it is a published fixture
and must never be used for anything real.
"""

from __future__ import annotations
