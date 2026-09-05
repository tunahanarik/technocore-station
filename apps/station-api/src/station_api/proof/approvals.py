"""What a person approved before a proof bundle left this process.

ADR-0009 4 settles which of the two existing consent shapes this is.

``ExportConsent`` is not it
---------------------------
:class:`~station_api.evidence.export.ExportConsent` is a per-request boolean
that cannot be constructed without an acknowledgement. That is the right shape
for the evidence archive, where the consent is about *this request* and the
same archive may honestly be exported again a minute later. It is the wrong
shape here for one reason: it is **not single-use**, and the prompt asks for a
single-use approval.

``SendApproval`` is
--------------------
:class:`~station_api.compose.approvals.SendApproval` binds an approval to the
exact bytes the user read, to their session, and to a TTL, and it is spent
through :class:`~station_api.security.tokens.SingleUseStore`, which removes
the entry on **every** outcome so a replay fails and a double click is one
redemption. The same three properties are what a share approval needs, so the
same pattern is reused rather than a third consent object invented (ADR-0004 2
rules out the duplication by name).

What this approval is bound to
-------------------------------
* the **bundle digest** - the exact document the person was shown. Change an
  artifact and the digest changes, so an approval given for the old bundle
  no longer matches and is refused. That is ADR-0009 4's "if the artifact
  changes, the hash, the check and the old approval are re-evaluated",
  expressed as a structure rather than as a promise;
* the **task**, so an approval for one task cannot deliver another's bundle;
* the **content version** the task is bound to, so a task re-opened against
  edited content invalidates it for the same reason evidence stops matching
  (ADR-0004 5);
* the **session**, because an approval belongs to the browser session that
  made it - another session presenting it is not the person who read the
  bundle.

The object holds no key material. A digest, a task id, a content-version id
and a session id are all local, public values.
"""

from __future__ import annotations

from dataclasses import dataclass

#: How long a prepared bundle stays deliverable.
#:
#: The same three minutes ``SEND_TOKEN_TTL_SECONDS`` uses, and for the same
#: reason: the window is sized for a person reading a summary and deciding,
#: not for a machine. Written out rather than imported from the composer, so
#: a change to the message-send window is not silently a change to this one -
#: two windows that happen to be equal are not one window.
SHARE_TOKEN_TTL_SECONDS = 180


@dataclass(frozen=True, slots=True)
class ShareApproval:
    """One person's approval to deliver one exact bundle, once."""

    task_id: str
    session_id: str
    #: Digest of the canonical bundle document the person was shown.
    bundle_sha256: str
    #: The content version the task was bound to when the bundle was built.
    source_version_id: str


__all__ = ["SHARE_TOKEN_TTL_SECONDS", "ShareApproval"]
