"""Evidence and audit.

Four trust levels, kept apart on purpose (charter 15, ``docs/evidence-model.md``):

1. signature proof - this key signed these canonical bytes;
2. server observation - Station saw this exact exported line and this
   generation;
3. local receipt time - this machine's clock said so;
4. external anchoring - **absent in the MVP, and written as ``null``**.

Nothing in this package collapses those into one green badge, and nothing in
it uses the four forbidden phrases (:mod:`station_api.evidence.language`).
"""

from __future__ import annotations

__all__: list[str] = []
