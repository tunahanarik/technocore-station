"""The four shapes of work this product proposes. Four, and never a fifth.

Its own module for one mechanical reason: :mod:`station_api.workscan.reading`
names a shape on the way back from the reading lane, and
:mod:`station_api.workscan.candidates` names the reading on the way in, so the
enum has to sit under both rather than inside one of them.

The names are unchanged from Package H1 and so are their meanings.
:data:`station_api.workscan.candidates.SIGNALS` still holds the sentences each
one commits a candidate to; what ADR-0014 removed is the list of literal
phrases a line had to contain to be counted as one.

``SignalId`` is re-exported from :mod:`station_api.workscan.candidates`, so
every existing import of it keeps working and nothing outside this package has
to know the enum moved.
"""

from __future__ import annotations

from enum import StrEnum


class SignalId(StrEnum):
    """The kinds of work this build recognises."""

    HELP_WANTED = "help_wanted"
    DEFECT_REPORT = "defect_report"
    REVIEW_REQUEST = "review_request"
    DOCUMENTATION_GAP = "documentation_gap"


__all__ = ["SignalId"]
