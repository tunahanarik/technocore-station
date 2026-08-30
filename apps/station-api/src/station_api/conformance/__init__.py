"""Conformance status for the write gate.

A thin adapter over ``technocore_conform.run_self_test``. The protocol logic
lives in the package; this module only decides when to run it and how the
result reaches the rest of the application.
"""

from __future__ import annotations

from station_api.conformance.service import (
    ConformanceService,
    default_conformance_service,
    reset_default_conformance_service,
)

__all__ = [
    "ConformanceService",
    "default_conformance_service",
    "reset_default_conformance_service",
]
