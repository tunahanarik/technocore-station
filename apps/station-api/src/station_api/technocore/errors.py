"""Read-only Technocore client errors.

Every failure here is fail-closed. There is no error that a caller can treat
as "probably fine": a fetch either produced bytes we can hash and parse, or
the source is ``unavailable`` and the write gate stays shut.

Error messages never carry user data. They may name the source id, the HTTP
status and a byte count, because those are properties of our own request to a
public document - not of the user's identity, which this client never sees.
"""

from __future__ import annotations


class TechnocoreError(Exception):
    """Base class for every read-only client failure."""


class SourceFetchError(TechnocoreError):
    """The document could not be retrieved.

    Covers DNS, TLS, timeout, connection reset and a non-success status.
    Deliberately one class: from the gate's point of view they all mean the
    same thing, which is that we do not know the live contract.
    """


class UnexpectedRedirectError(SourceFetchError):
    """The origin answered with a redirect.

    Redirects are never followed. A redirect away from the pinned origin is
    exactly the case where following it would silently move us to a host the
    allow-list was written to exclude.
    """


class ResponseTooLargeError(SourceFetchError):
    """The body exceeded the per-source cap.

    Checked on the decompressed bytes, so a small compressed payload that
    expands to gigabytes is refused rather than buffered.
    """


class DocumentParseError(TechnocoreError):
    """The document was retrieved but is not usable.

    Malformed JSON, a duplicate key, a non-finite number or an unexpected
    top-level type. A document we cannot parse cannot be compared, and an
    uncomparable document is never ``current``.
    """


__all__ = [
    "DocumentParseError",
    "ResponseTooLargeError",
    "SourceFetchError",
    "TechnocoreError",
    "UnexpectedRedirectError",
]
