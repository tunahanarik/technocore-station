"""The OpenCode Go connection.

The fourth outbound surface in this application, and the first one that
carries a credential. Its shape is deliberately the same as the three
Technocore clients' - a closed address registry, one reviewed client module,
and a service that turns a failure into a stated verdict rather than a
plausible-looking success - and its differences are all written down where
they live:

:mod:`~station_api.opencode.registry`     four fixed addresses, and the
                                          compile-time model table a fetched
                                          catalog can never widen
:mod:`~station_api.opencode.client`       the only module here that imports
                                          httpx, and the only place in the
                                          repository that writes an
                                          ``Authorization`` header
:mod:`~station_api.opencode.credential_store`  the DPAPI envelope, with the one
                                          deliberate inversion of the audit
                                          envelope's never-overwrite rule
:mod:`~station_api.opencode.adapters`     three protocol families, one event
:mod:`~station_api.opencode.events`       that event, and its refusal to
                                          invent a usage figure
:mod:`~station_api.opencode.catalog`      reading the public catalog, and
                                          joining it to the closed table
:mod:`~station_api.opencode.quota`        read-only spending context; no
                                          budget opens here
:mod:`~station_api.opencode.service`      the whole of it, with redaction
                                          held around every use

What this package does **not** do: streaming, tool calls, an automatic call
of any kind at startup, a verification badge for a credential nothing can
verify, or a silent substitution of the model the user chose.
"""

from station_api.opencode.errors import (
    CredentialEnvelopeError,
    ModelNotSelectableError,
    OpenCodeConfigurationError,
    OpenCodeError,
    OpenCodeLostResponseError,
    OpenCodeRequestError,
    OpenCodeResponseError,
)
from station_api.opencode.service import (
    CatalogState,
    ConnectionCheck,
    ConnectionView,
    OpenCodeService,
    VerificationState,
)

__all__ = [
    "CatalogState",
    "ConnectionCheck",
    "ConnectionView",
    "CredentialEnvelopeError",
    "ModelNotSelectableError",
    "OpenCodeConfigurationError",
    "OpenCodeError",
    "OpenCodeLostResponseError",
    "OpenCodeRequestError",
    "OpenCodeResponseError",
    "OpenCodeService",
    "VerificationState",
]
