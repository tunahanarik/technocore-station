"""In-memory session store.

Sessions and their CSRF values exist only in process memory (SI-09). Nothing
here is persisted: closing the application ends every session. The CSRF value
is minted together with the session so that ``/api/session/bootstrap`` can
stay a pure read and needs no CSRF exemption (IMP-105).
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field

from station_api.logging_setup import forget_secret, register_secret

SESSION_ID_BYTES = 32
CSRF_TOKEN_BYTES = 32


@dataclass(frozen=True)
class Session:
    """A browser session. Carries no user secret of any kind."""

    session_id: str
    csrf_token: str
    metadata: dict[str, str] = field(default_factory=dict)


class SessionStore:
    """Thread-safe, memory-only session table."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self) -> Session:
        session = Session(
            session_id=secrets.token_urlsafe(SESSION_ID_BYTES),
            csrf_token=secrets.token_urlsafe(CSRF_TOKEN_BYTES),
        )
        register_secret(session.session_id)
        register_secret(session.csrf_token)
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        with self._lock:
            return self._sessions.get(session_id)

    def revoke(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            forget_secret(session.session_id)
            forget_secret(session.csrf_token)

    def clear(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            forget_secret(session.session_id)
            forget_secret(session.csrf_token)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
