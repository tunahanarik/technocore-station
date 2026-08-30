"""Read-only Technocore monitoring (Stage 3).

Station's entire outbound surface. It reads six official documents over
HTTPS, compares the machine-readable protocol contract against what Stage 2B
signs for, and reports a verdict the write gate consumes.

It sends no writes. Note that "only GET" would not be a safety property on
this service - Technocore performs writes over GET - so the safety property
is the closed source registry in ``sources``: a URL that is not built from an
entry there cannot be requested.
"""

from __future__ import annotations

from station_api.technocore.client import ReadOnlyTechnocoreClient
from station_api.technocore.errors import (
    DocumentParseError,
    ResponseTooLargeError,
    SourceFetchError,
    TechnocoreError,
    UnexpectedRedirectError,
)
from station_api.technocore.projection import PROTOCOL_FIELDS, DriftState, Severity
from station_api.technocore.service import (
    SourceStatus,
    TechnocoreService,
    TechnocoreStatus,
)
from station_api.technocore.sources import (
    SOURCES,
    TECHNOCORE_ORIGIN,
    OfficialSource,
    SourceId,
)

__all__ = [
    "PROTOCOL_FIELDS",
    "SOURCES",
    "TECHNOCORE_ORIGIN",
    "DocumentParseError",
    "DriftState",
    "OfficialSource",
    "ReadOnlyTechnocoreClient",
    "ResponseTooLargeError",
    "Severity",
    "SourceFetchError",
    "SourceId",
    "SourceStatus",
    "TechnocoreError",
    "TechnocoreService",
    "TechnocoreStatus",
    "UnexpectedRedirectError",
]
