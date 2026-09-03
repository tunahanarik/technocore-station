"""Single-use, short-lived tokens.

Two things are built on the same store, and they are the same shape for the
same reason: both hand a capability to a caller once, and both must refuse a
replay rather than merely discourage one.

* **Bootstrap tokens.** The launcher opens ``/session/<token>`` in the
  browser exactly once. 256 bits of randomness, valid for 30 seconds, revoked
  the first time it is presented (SI-04, SI-05, SI-06).
* **Send approvals.** The composer mints one after the user has read the
  canonical text and approved the signature. It carries the payload that
  binds the approval to that exact write, and is valid for 180 seconds
  (ADR-0002 2).

Tokens live only in process memory and are never written to disk or to a
log: every issued value is registered with the redaction filter, and
forgotten again the moment it can no longer appear.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from station_api.config import BOOTSTRAP_TOKEN_TTL_SECONDS
from station_api.logging_setup import forget_secret, register_secret

#: 32 bytes == 256 bits of entropy. token_urlsafe encodes them base64url.
TOKEN_ENTROPY_BYTES = 32


@dataclass(frozen=True)
class _Issued[T]:
    expires_at: float
    payload: T


class SingleUseStore[T]:
    """In-memory store of one-shot tokens, each carrying a payload.

    ``consume`` is the only way out and it removes the entry on **every**
    outcome, so a replay of a valid token fails and an expired token cannot
    be resurrected by a clock change. The removal happens under the lock
    together with the lookup, which is what makes a double click a single
    redemption rather than a race.
    """

    def __init__(
        self, *, ttl_seconds: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._tokens: dict[str, _Issued[T]] = {}
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def issue(self, payload: T) -> str:
        """Mint a token. The caller must not log the return value."""
        token = secrets.token_urlsafe(TOKEN_ENTROPY_BYTES)
        register_secret(token)
        with self._lock:
            self._tokens[token] = _Issued(
                expires_at=self._clock() + self._ttl, payload=payload
            )
        return token

    def consume(self, token: str) -> tuple[bool, T | None]:
        """Redeem a token exactly once.

        Returns ``(True, payload)`` only for a token that is known, unexpired
        and unused; ``(False, None)`` otherwise. An expired token is
        deliberately indistinguishable from an unknown one to the caller's
        control flow - both mean "there is no valid approval here".
        """
        now = self._clock()
        with self._lock:
            issued = self._tokens.pop(token, None)
        forget_secret(token)
        if issued is None:
            return False, None
        if now > issued.expires_at:
            return False, None
        return True, issued.payload

    def purge_expired(self) -> None:
        now = self._clock()
        with self._lock:
            dead = [t for t, issued in self._tokens.items() if now > issued.expires_at]
            for token in dead:
                del self._tokens[token]
        for token in dead:
            forget_secret(token)

    def discard_where(self, predicate: Callable[[T], bool]) -> int:
        """Drop every pending token whose payload matches.

        Used to invalidate approvals wholesale when the thing they were bound
        to has changed - a session ending, an identity revoked. Returns how
        many were dropped.
        """
        with self._lock:
            doomed = [
                token
                for token, issued in self._tokens.items()
                if predicate(issued.payload)
            ]
            for token in doomed:
                del self._tokens[token]
        for token in doomed:
            forget_secret(token)
        return len(doomed)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._tokens)


class BootstrapTokenStore:
    """In-memory store of pending one-shot handoff tokens.

    A thin naming layer over :class:`SingleUseStore`: the handoff carries no
    payload, so its ``consume`` answers a plain boolean.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = BOOTSTRAP_TOKEN_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store: SingleUseStore[None] = SingleUseStore(
            ttl_seconds=ttl_seconds, clock=clock
        )

    @property
    def ttl_seconds(self) -> int:
        return self._store.ttl_seconds

    def issue(self) -> str:
        """Mint a token. The caller must not log the return value."""
        return self._store.issue(None)

    def consume(self, token: str) -> bool:
        """Redeem a token exactly once."""
        accepted, _ = self._store.consume(token)
        return accepted

    def purge_expired(self) -> None:
        self._store.purge_expired()

    @property
    def pending_count(self) -> int:
        return self._store.pending_count


__all__ = ["TOKEN_ENTROPY_BYTES", "BootstrapTokenStore", "SingleUseStore"]
