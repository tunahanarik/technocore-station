"""OpenCode connection errors.

Every failure here is fail-closed in the same sense the Technocore client's
are: a call either produced bytes we parsed into an event, or the connection
is *unavailable* and nothing pretends otherwise.

One difference from :mod:`station_api.technocore.errors` is worth naming.
There, a failure costs a retry. Here a failure may already have cost money -
a request that left this process and whose response was lost may still have
been billed - so :class:`OpenCodeLostResponseError` exists to say exactly
that instead of being folded into "transport failure".

Error messages never carry the API key, the user's identity or a file path.
They may name the endpoint id, the HTTP status and a byte count, because
those are properties of our own request.
"""

from __future__ import annotations


class OpenCodeError(Exception):
    """Base class for every OpenCode connection failure."""


class OpenCodeConfigurationError(OpenCodeError):
    """The connection is not configured, or is configured with something unusable."""


class CredentialEnvelopeError(OpenCodeError):
    """The provider key envelope could not be written, read or removed."""


class OpenCodeRequestError(OpenCodeError):
    """The request could not be completed.

    Covers DNS, TLS, timeout, connection reset and a status we refuse to read
    as success. Deliberately one class: from the caller's point of view they
    all mean the same thing, which is that we do not know what happened
    upstream.
    """


class OpenCodeLostResponseError(OpenCodeRequestError):
    """The request left this process and the answer did not come back.

    Named separately because the honest consequence is not "try again". A
    metered request whose response was lost may still have been charged, so
    this is reported to the user rather than retried (ADR-0005 11).
    """


class UnexpectedRedirectError(OpenCodeRequestError):
    """The origin answered with a redirect.

    Redirects are never followed. Following one is precisely how a request
    carrying a provider key leaves the allow-listed origin.
    """


class ResponseTooLargeError(OpenCodeRequestError):
    """The body exceeded the per-endpoint cap, measured on decompressed bytes."""


class OpenCodeResponseError(OpenCodeError):
    """The response arrived but is not usable: malformed, empty or the wrong shape."""


class ModelNotSelectableError(OpenCodeError):
    """The chosen model cannot be used, and the reason is in the message.

    Raised rather than silently substituted. There is no fallback model and
    no "closest match": a request for a model this build cannot address is a
    refusal the user sees (ADR-0005 11).
    """


__all__ = [
    "CredentialEnvelopeError",
    "ModelNotSelectableError",
    "OpenCodeConfigurationError",
    "OpenCodeError",
    "OpenCodeLostResponseError",
    "OpenCodeRequestError",
    "OpenCodeResponseError",
    "ResponseTooLargeError",
    "UnexpectedRedirectError",
]
