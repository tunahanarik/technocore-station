"""What this lane raises. Two classes, and neither of them is a candidate.

Separate from :mod:`station_api.workscan.errors` on purpose: a failure to read
a line with a model is a different event from a failure to parse a room's
document, and a route that could not tell them apart would answer the same way
for "the provider is down" and "the reply was not JSON".
"""

from __future__ import annotations


class WorkReaderError(Exception):
    """Base for everything this package raises."""


class ReadingProtocolError(WorkReaderError):
    """An answer this build will not use.

    A tool name that is not in the closed registry, an argument that did not
    satisfy its declared type, a line number outside the batch that was sent,
    or the same line named under two shapes. Every one of them drops the
    **whole turn**: a proposal is used entire or not at all.
    """


__all__ = ["ReadingProtocolError", "WorkReaderError"]
