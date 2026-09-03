"""Monotonic nonce reservation, per ``(did, room)``.

The rule is fixed by the protocol contract (docs/protocol-contract.md 5) and
by the pinned manifest, which states it in one sentence: a nonce is *strictly
greater than the last nonce that key used in that room*. Station's allocation
rule is::

    next = max(local_last + 1, milliseconds_since_epoch)

and it is applied **inside a transaction, before anything is signed**. The
ordering is not a preference. The nonce is part of the canonical string, so
it has to exist before the bytes exist; and if it were allocated after the
signature, the signature would cover a different nonce than the request
carried.

Why the clock is in the formula at all
--------------------------------------
``local_last + 1`` alone is correct but fragile: a database restored from a
backup, or a fresh profile signing for a DID that has written from another
machine, would restart the counter low and every write would be refused as a
replay. Taking the millisecond clock as a floor means a fresh counter starts
past anything a human-paced history could have reached. ``max`` of the two is
what keeps it monotonic when the clock disagrees - a clock that jumps
backwards changes nothing, because the local value still wins.

Leading zeros
-------------
The value is produced from an integer and rendered with ``str``, so it can
never carry a leading zero (ADR-0002 4.2). That matters because the server
compares the nonce as an integer while the signature covers it as text:
``"007"`` and ``"7"`` are the same number and different bytes, so a nonce
that ever acquired a leading zero would produce a signature over bytes the
server did not store.

Concurrency
-----------
Two guards, and they answer different questions:

* a process-level lock, because the realistic race is two clicks in one
  Station process;
* a ``UNIQUE(did, room, nonce_value)`` constraint, because a lock cannot
  reach a second process opening the same database file.

The bounded retry below runs **only** when the local store rejects an insert -
a write that provably did not happen, against a database we own. It is not,
and must not be confused with, a retry of an outbound request: ADR-0002 3
forbids those precisely because a failed HTTP write is not proof that nothing
was written.

Two rejections count as that, not one. ``IntegrityError`` is the constraint
firing; ``OperationalError`` - "database is locked" - is the second process
holding the file while we tried. Both mean the same thing here (no row was
written, re-read and try again), and both must end as a
``NonceReservationError``: the composer catches that class and turns it into
an explainable 409, while anything else escapes to the armoured 500 and tells
the user nothing.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from technocore_conform import MAX_NONCE_DIGITS, validate_nonce

from station_api.db.models import (
    MessageNonceReservation,
    NonceState,
    WriteOutcomeValue,
)

#: The largest nonce Station will ever produce.
#:
#: Two ceilings meet here and the lower one wins. The protocol allows 19
#: digits, which is ``10**19 - 1``; SQLite stores an integer in 64 signed
#: bits, whose maximum is ``2**63 - 1``. Reserving a number the database
#: cannot hold would silently corrupt the counter, so the storable bound is
#: the real one. It is still a 19-digit value, so nothing about the wire
#: format changes.
MAX_NONCE_VALUE = min(10**MAX_NONCE_DIGITS - 1, 2**63 - 1)

#: Attempts allowed when the uniqueness constraint rejects an insert. Each
#: retry re-reads the counter, so a genuine race resolves on the next pass;
#: this bound exists so a persistent constraint failure surfaces as an error
#: instead of a spin.
MAX_RESERVE_ATTEMPTS = 8


class NonceReservationError(Exception):
    """A nonce could not be reserved. The message is safe to show a user."""


class NonceExhaustedError(NonceReservationError):
    """The counter for this ``(did, room)`` has reached its ceiling."""


class UnknownReservationError(NonceReservationError):
    """No such reservation, or it has already been settled."""


class NonceStorageError(NonceReservationError):
    """The counter's own database refused to answer.

    A second Station process holding the SQLite file is the realistic cause.
    Fail-closed and explainable: no nonce is handed out, none is reused, and
    the caller gets a sentence instead of an armoured 500.
    """


@dataclass(frozen=True, slots=True)
class NonceReservation:
    """One allocated nonce. Carries no secret material."""

    id: str
    did: str
    room: str
    #: The exact characters that enter the canonical string.
    nonce: str
    value: int
    reserved_at: datetime


def _default_clock_ms() -> int:
    """Wall-clock milliseconds since the epoch."""
    return int(time.time() * 1000)


class NonceReserver:
    """Hands out and settles nonces. One instance per process."""

    def __init__(
        self, engine: Engine, *, clock_ms: Callable[[], int] = _default_clock_ms
    ) -> None:
        self._engine = engine
        self._clock_ms = clock_ms
        self._lock = threading.Lock()

    # --- allocation --------------------------------------------------------

    def reserve(self, *, did: str, room: str) -> NonceReservation:
        """Allocate the next nonce for ``(did, room)``.

        Raises rather than returning a fallback: a caller that cannot get a
        nonce must not proceed to sign anything.
        """
        with self._lock:
            last_error: Exception | None = None
            locked = False
            for _ in range(MAX_RESERVE_ATTEMPTS):
                try:
                    return self._reserve_once(did=did, room=room)
                except IntegrityError as exc:
                    # Another writer took the number between our read and our
                    # insert. Nothing was written; re-read and try again.
                    last_error = exc
                    locked = False
                except OperationalError as exc:
                    # A second process is holding the file. Also "nothing was
                    # written", so the same bounded retry applies - but the
                    # sentence at the end has to name a different cause,
                    # because "keep clicking" is the wrong advice for a lock.
                    last_error = exc
                    locked = True
            if locked:
                raise NonceStorageError(
                    "Nonce ayrilamadi: sayac veritabani mesgul. Baska bir "
                    "Station penceresi aciksa kapatip yeniden deneyin."
                ) from last_error
            raise NonceReservationError(
                "Nonce ayrilamadi: sayac uzerinde surekli cakisma var."
            ) from last_error

    def _reserve_once(self, *, did: str, room: str) -> NonceReservation:
        reservation_id = uuid.uuid4().hex
        now = datetime.now(UTC)

        with Session(self._engine) as session, session.begin():
            highest = session.scalar(
                select(func.max(MessageNonceReservation.nonce_value)).where(
                    MessageNonceReservation.did == did,
                    MessageNonceReservation.room == room,
                )
            )
            # Every row counts, whatever its state. A cancelled or unknown
            # reservation has still consumed its number.
            local_next = 1 if highest is None else int(highest) + 1
            value = max(local_next, self._clock_ms())

            if value > MAX_NONCE_VALUE:
                raise NonceExhaustedError(
                    "Bu oda ve kimlik icin nonce sayaci ust sinira ulasti; "
                    "protokol 19 haneden uzun bir nonce kabul etmiyor."
                )

            # Rendered from an int, so a leading zero is unrepresentable -
            # and validated against the official pattern before it can reach
            # a canonical string.
            nonce = validate_nonce(str(value))

            session.add(
                MessageNonceReservation(
                    id=reservation_id,
                    did=did,
                    room=room,
                    nonce=nonce,
                    nonce_value=value,
                    reserved_at=now,
                    state=NonceState.RESERVED.value,
                    outcome="",
                    settled_at=None,
                    detail="",
                )
            )

        return NonceReservation(
            id=reservation_id,
            did=did,
            room=room,
            nonce=nonce,
            value=value,
            reserved_at=now,
        )

    # --- settlement --------------------------------------------------------

    def commit_to_send(self, reservation_id: str) -> None:
        """Mark the nonce spent *before* the request leaves the process.

        Deliberately not "after": a crash, a killed process or a lost
        response between here and a reply must leave the number burnt. The
        state written here says the request was committed to, which is the
        strongest thing that can honestly be said at this point.
        """
        self._settle(
            reservation_id,
            state=NonceState.SPENT,
            outcome=WriteOutcomeValue.IN_FLIGHT,
            detail="",
            require_reserved=True,
        )

    def record_outcome(
        self, reservation_id: str, *, outcome: WriteOutcomeValue, detail: str = ""
    ) -> None:
        """Record how the committed request ended. The nonce stays spent."""
        self._settle(
            reservation_id,
            state=NonceState.SPENT,
            outcome=outcome,
            detail=detail,
            require_reserved=False,
        )

    def cancel(self, reservation_id: str, *, detail: str) -> None:
        """Abandon a reservation without sending anything.

        The number is not returned to circulation: see :class:`NonceState`.
        """
        self._settle(
            reservation_id,
            state=NonceState.CANCELLED,
            outcome=WriteOutcomeValue.NOT_SENT,
            detail=detail,
            require_reserved=False,
        )

    def _settle(
        self,
        reservation_id: str,
        *,
        state: NonceState,
        outcome: WriteOutcomeValue,
        detail: str,
        require_reserved: bool,
    ) -> None:
        try:
            self._settle_once(
                reservation_id,
                state=state,
                outcome=outcome,
                detail=detail,
                require_reserved=require_reserved,
            )
        except OperationalError as exc:
            # Same reasoning as ``reserve``: a locked file must not surface as
            # an armoured 500. Settling is what marks the number spent before
            # a request leaves, so failing here means nothing is sent - which
            # is the fail-closed side, and now it says so.
            raise NonceStorageError(
                "Nonce defteri guncellenemedi: sayac veritabani mesgul. "
                "Hicbir sey gonderilmedi."
            ) from exc

    def _settle_once(
        self,
        reservation_id: str,
        *,
        state: NonceState,
        outcome: WriteOutcomeValue,
        detail: str,
        require_reserved: bool,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            row = session.get(MessageNonceReservation, reservation_id)
            if row is None:
                raise UnknownReservationError("Nonce rezervasyonu bulunamadi.")
            if require_reserved and row.state != NonceState.RESERVED.value:
                # The double-click guard at the storage layer. The approval
                # token is single-use and would already have refused, but a
                # counter that can be committed twice is not a property to
                # leave resting on one check.
                raise UnknownReservationError(
                    "Bu nonce zaten harcanmis; ikinci kez gonderilemez."
                )
            row.state = state.value
            row.outcome = outcome.value
            row.settled_at = datetime.now(UTC)
            row.detail = detail[:500]

    # --- reads (diagnostics and tests) -------------------------------------

    def last_value(self, *, did: str, room: str) -> int:
        """The highest number this pair has consumed, or 0."""
        with Session(self._engine) as session:
            highest = session.scalar(
                select(func.max(MessageNonceReservation.nonce_value)).where(
                    MessageNonceReservation.did == did,
                    MessageNonceReservation.room == room,
                )
            )
        return 0 if highest is None else int(highest)

    def describe(self, reservation_id: str) -> tuple[str, str]:
        """``(state, outcome)`` for one reservation."""
        with Session(self._engine) as session:
            row = session.get(MessageNonceReservation, reservation_id)
            if row is None:
                raise UnknownReservationError("Nonce rezervasyonu bulunamadi.")
            return row.state, row.outcome


__all__ = [
    "MAX_NONCE_VALUE",
    "MAX_RESERVE_ATTEMPTS",
    "NonceExhaustedError",
    "NonceReservation",
    "NonceReservationError",
    "NonceReserver",
    "NonceStorageError",
    "UnknownReservationError",
]
