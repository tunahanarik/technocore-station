"""Single-use, short-lived browser handoff tokens.

The launcher opens ``/session/<token>`` in the browser exactly once. The token
is 256 bits of cryptographic randomness, is valid for 30 seconds, and is
revoked the first time it is presented (SI-04, SI-05, SI-06).

Tokens live only in process memory and are never written to disk or to a log.
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
class _Issued:
    expires_at: float


class BootstrapTokenStore:
    """In-memory store of pending one-shot handoff tokens."""

    def __init__(
        self,
        *,
        ttl_seconds: int = BOOTSTRAP_TOKEN_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._tokens: dict[str, _Issued] = {}
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def issue(self) -> str:
        """Mint a token. The caller must not log the return value."""
        token = secrets.token_urlsafe(TOKEN_ENTROPY_BYTES)
        register_secret(token)
        with self._lock:
            self._tokens[token] = _Issued(expires_at=self._clock() + self._ttl)
        return token

    def consume(self, token: str) -> bool:
        """Redeem a token exactly once.

        Returns True only for a token that is known, unexpired and unused.
        The entry is removed on every outcome, so a replay of a valid token
        fails and an expired token cannot be resurrected.
        """
        now = self._clock()
        with self._lock:
            issued = self._tokens.pop(token, None)
        forget_secret(token)
        if issued is None:
            return False
        return now <= issued.expires_at

    def purge_expired(self) -> None:
        now = self._clock()
        with self._lock:
            dead = [t for t, issued in self._tokens.items() if now > issued.expires_at]
            for token in dead:
                del self._tokens[token]
        for token in dead:
            forget_secret(token)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._tokens)
