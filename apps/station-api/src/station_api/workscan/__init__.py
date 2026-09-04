"""Package H1: the read-only public-room work scan.

Four things live here and nothing else: the fourth closed address registry,
the fifth outbound client, the deterministic candidate derivation, and the
records that say what this build could and could not verify.

There is no scheduler, no background task and no long-poll in this package.
Every outbound request in it happens because a person pressed something
(ADR-0007 4).
"""

from __future__ import annotations
