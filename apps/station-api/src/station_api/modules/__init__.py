"""The compile-time module registry (ADR-0004 1).

A "module" in this product is a **registry record**, not a directory. The code
that owns a responsibility stays where it is; the registry points at it. That
is the pattern the repository already uses in four places - ``sections.ts``,
``technocore/sources.py``, ``technocore/write_targets.py`` and
``identity/write_gate.py`` - and it is the one thing that lets a module
boundary exist without moving a single import path.

Nothing here is loaded from disk. There is no plugin directory, no entry-point
group and no dynamic import: the set of modules is a tuple literal, changing it
is a reviewable diff, and a security test proves the package contains no
dynamic-loading construct at all (AGENTS.md 2.9, charter ADR-017).
"""

from __future__ import annotations

from station_api.modules.completion import (
    ModuleCheck,
    ModuleCompletion,
    evaluate_module,
)
from station_api.modules.fields import (
    FIELD_DETAIL,
    PUBLICATION_FIELDS,
    UNFILLABLE_FIELDS,
    EvidenceField,
    EvidenceRef,
)
from station_api.modules.registry import (
    MODULES,
    POLICY_REFUSED_REQUIREMENTS,
    ModuleId,
    ModuleRecord,
    ModuleRequirement,
    ModuleState,
    get_module,
    requirement_keys,
)

__all__ = [
    "FIELD_DETAIL",
    "MODULES",
    "POLICY_REFUSED_REQUIREMENTS",
    "PUBLICATION_FIELDS",
    "UNFILLABLE_FIELDS",
    "EvidenceField",
    "EvidenceRef",
    "ModuleCheck",
    "ModuleCompletion",
    "ModuleId",
    "ModuleRecord",
    "ModuleRequirement",
    "ModuleState",
    "evaluate_module",
    "get_module",
    "requirement_keys",
]
