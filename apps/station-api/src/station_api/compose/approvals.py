"""What a user approved, and what that approval is bound to.

The chain is three requests, and each one narrows what the next may do
(ADR-0002 2). This module holds the two artefacts that carry the narrowing
between them; the policy that produces and checks them lives in
:mod:`station_api.compose.service`.

The draft digest
----------------
Computed over the **swept** text and the target room - the two things the
user is shown and asked to approve. It is not computed over the raw text: the
raw text is not what gets stored or signed, and approving one thing while
signing another is the failure this whole chain exists to prevent. Change
either the text or the room and the digest changes, so the signing step
refuses: an old approval cannot sign new content.

The send approval
-----------------
Bound to five things, and every one of them can go stale:

* the canonical byte digest - the exact bytes the signature covers;
* the room, because a signature over ``room|nonce|text`` is only valid for
  that room;
* the reserved nonce, so an approval cannot be replayed onto a fresh one;
* the signing DID, so an identity change invalidates it;
* the manifest verdict identity at the moment of signing, so a protocol
  check that has since been re-run - or has since found drift - cannot leave
  a three-minute-old approval firing against a contract nobody re-verified.

The session id is carried too. An approval belongs to the browser session
that made it; another session presenting it is not the person who read the
canonical text.

Neither object holds key material. A canonical digest, a signature, a DID, a
nonce and a room name are all public.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from station_api.digests import domain_digest, domain_digest_bytes

#: How long a prepared draft stays signable. The user has to read a diff and
#: decide; three minutes is generous for that and short enough that a
#: forgotten tab is not still armed after lunch.
DRAFT_TTL_SECONDS = 180

#: How long a signature approval stays sendable (ADR-0002 2). Deliberately
#: longer than the 30-second bootstrap token: that one is handed between two
#: machines, this one waits for a human to read the exact canonical bytes and
#: decide whether to publish them.
SEND_TOKEN_TTL_SECONDS = 180

#: Ceiling on prepared-but-unsigned drafts per process. Drafts are small and
#: expire on their own; the cap exists so a stuck client cannot grow the
#: table without bound.
MAX_OPEN_DRAFTS = 64

#: Domain separation. A digest is only meaningful against the thing it was
#: computed for, so each one names its own purpose and version.
DRAFT_DOMAIN = b"technocore-station/compose-draft/v1"
VERDICT_DOMAIN = b"technocore-station/manifest-verdict/v1"
CANONICAL_DOMAIN = b"technocore-station/canonical-bytes/v1"


def draft_digest(*, room: str, swept_text: str) -> str:
    """The digest the user's approval of step 1 is bound to."""
    return domain_digest(DRAFT_DOMAIN, room, swept_text)


def verdict_digest(*, state: str, checked_at: str, check_id: str) -> str:
    """A stable identity for one manifest verdict.

    Any *new* check produces a new identity, even one that finds the same
    protocol unchanged. That is deliberate and it is the fail-closed reading:
    an approval is bound to the evidence that existed when the user gave it,
    and a re-check is new evidence the user has not seen the result of.
    """
    return domain_digest(VERDICT_DOMAIN, state, checked_at, check_id)


def canonical_digest(canonical_bytes: bytes) -> str:
    """SHA-256 over the exact bytes the signature covers.

    Taken over the bytes rather than over the fields, because those bytes are
    what was signed. Rebuilding the canonical string from fields at send time
    and hashing *that* would compare our reconstruction with itself.
    """
    return domain_digest_bytes(CANONICAL_DOMAIN, canonical_bytes)


@dataclass(frozen=True, slots=True)
class Draft:
    """A prepared message, not yet signed and with no nonce."""

    id: str
    session_id: str
    room: str
    raw_text: str
    swept_text: str
    digest: str
    #: Whether the sweep changed what the user typed. Shown as a diff.
    changed_by_sweep: bool
    expires_at: float


@dataclass(frozen=True, slots=True)
class SendApproval:
    """A signature the user approved, and everything it is bound to."""

    draft_id: str
    session_id: str
    did: str
    room: str
    nonce: str
    reservation_id: str
    #: SHA-256 over the exact canonical bytes the signature covers.
    canonical_digest: str
    #: The 86-character wire signature. Public.
    signature: str
    #: The swept text, so the sent body is the approved body verbatim.
    swept_text: str
    #: Identity of the manifest verdict at the moment of signing.
    verdict_id: str


class DraftStore:
    """Prepared drafts, in process memory, bounded and expiring.

    A draft is not single-use: the same content may be signed again after a
    refusal, and forcing a re-type would push the user toward approving
    quickly rather than carefully. It *is* session-scoped and short-lived.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = DRAFT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        capacity: int = MAX_OPEN_DRAFTS,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._capacity = capacity
        self._drafts: dict[str, Draft] = {}
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def put(
        self,
        *,
        session_id: str,
        room: str,
        raw_text: str,
        swept_text: str,
        changed_by_sweep: bool,
    ) -> Draft:
        draft = Draft(
            id=secrets.token_urlsafe(16),
            session_id=session_id,
            room=room,
            raw_text=raw_text,
            swept_text=swept_text,
            digest=draft_digest(room=room, swept_text=swept_text),
            changed_by_sweep=changed_by_sweep,
            expires_at=self._clock() + self._ttl,
        )
        with self._lock:
            self._purge_locked()
            if len(self._drafts) >= self._capacity:
                # Drop the oldest rather than refusing the newest: the user
                # is in front of the newest one.
                oldest = min(self._drafts.values(), key=lambda item: item.expires_at)
                del self._drafts[oldest.id]
            self._drafts[draft.id] = draft
        return draft

    def get(self, draft_id: str, *, session_id: str) -> Draft | None:
        """The draft, if it exists, has not expired and is this session's."""
        now = self._clock()
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                return None
            if now > draft.expires_at:
                del self._drafts[draft_id]
                return None
        if draft.session_id != session_id:
            return None
        return draft

    def discard_session(self, session_id: str) -> int:
        """Forget every draft belonging to a session that has ended."""
        with self._lock:
            doomed = [
                draft_id
                for draft_id, draft in self._drafts.items()
                if draft.session_id == session_id
            ]
            for draft_id in doomed:
                del self._drafts[draft_id]
        return len(doomed)

    def _purge_locked(self) -> None:
        now = self._clock()
        for draft_id in [
            draft_id
            for draft_id, draft in self._drafts.items()
            if now > draft.expires_at
        ]:
            del self._drafts[draft_id]

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._drafts)


__all__ = [
    "CANONICAL_DOMAIN",
    "DRAFT_DOMAIN",
    "DRAFT_TTL_SECONDS",
    "MAX_OPEN_DRAFTS",
    "SEND_TOKEN_TTL_SECONDS",
    "VERDICT_DOMAIN",
    "Draft",
    "DraftStore",
    "SendApproval",
    "canonical_digest",
    "draft_digest",
    "verdict_digest",
]
