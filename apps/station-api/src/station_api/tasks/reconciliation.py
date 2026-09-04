"""The startup reconciliation scan. It reads, and it does not write.

ADR-0004 6, and the discovery behind it: ``WriteOutcomeValue.IN_FLIGHT`` has
been written since Package D and **nothing has ever read it back**. There is
no ``lifespan`` and no ``on_event`` in ``app.py``, so a send that died between
``commit_to_send`` and ``record_outcome`` stayed ``in_flight`` for the life of
the database, visible to nobody.

This closes the read half and only the read half:

* it runs one ``SELECT`` at application build time;
* it makes no outbound request - not a retry, not a capture, not a probe. A
  test asserts the number of requests that leave this process during a scan is
  **zero**, and the suite's autouse network guard would raise loudly if one
  were attempted anyway;
* it changes no row. The ledger says ``in_flight`` before the scan and
  ``in_flight`` after it;
* it decides nothing. Whether to continue is the user's call, and when they
  make it every check runs again from the start.

That is the same narrowing ADR-0003 4 applied to reconciliation on the
evidence side: *a capture may be attempted, a send may not be repeated*. An
automatic continuation would turn one approved message into an unknown number
of published ones, which is precisely the failure the three-valued outcome
exists to keep visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from station_api.db.models import (
    MessageNonceReservation,
    NonceState,
    WriteOutcomeValue,
)

#: Most rows one scan reports. A bound on the read, not on the store: nothing
#: here prunes anything.
MAX_UNFINISHED_REPORTED = 200

#: The sentence shown beside the list. It says what the scan did and, just as
#: importantly, what it did not do.
RECONCILIATION_DETAIL = (
    "Yarim kalmis gonderimler yalnizca listelendi. Hicbir istek gonderilmedi, "
    "hicbir kayit degistirilmedi ve hicbir gonderim otomatik olarak "
    "surdurulmedi. Devam karari kullanicinindir ve devam edilirse butun "
    "kontroller bastan kosar."
)

#: The sentence shown when there is nothing to report.
NOTHING_UNFINISHED_DETAIL = (
    "Yarim kalmis gonderim yok: defterdeki her harcanmis nonce bir sonuca "
    "baglanmis durumda."
)


@dataclass(frozen=True, slots=True)
class UnfinishedWrite:
    """One send that was committed to and never settled.

    Everything here is a public protocol value: a ledger id, a DID, a room
    name, a nonce and two timestamps. No canonical text, no signature, no
    response body - the scan reports that something is unfinished, not what it
    said.
    """

    reservation_id: str
    did: str
    room: str
    nonce: str
    reserved_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """What one read-only scan found."""

    scanned_at: datetime
    unfinished: tuple[UnfinishedWrite, ...]
    detail: str
    #: Stated as a value, not only in prose, so a caller cannot report this
    #: scan as having done something. It is always ``False``.
    resumed_any: bool = False

    @property
    def unfinished_count(self) -> int:
        return len(self.unfinished)


def scan_unfinished_writes(engine: Engine | None) -> ReconciliationReport:
    """List the sends that were committed to and never settled.

    Read-only by construction: one ``select``, a session that is never
    ``begin()``-ed and never flushed, and no client of any kind imported by
    this module.

    ``None`` engine answers an empty report rather than raising. A machine
    with no database has no ledger to reconcile, and failing to build the
    application over it would trade a missing list for a missing product.
    """
    scanned_at = datetime.now(UTC)
    if engine is None:
        return ReconciliationReport(
            scanned_at=scanned_at, unfinished=(), detail=NOTHING_UNFINISHED_DETAIL
        )

    with Session(engine) as session:
        rows = (
            session.execute(
                select(MessageNonceReservation)
                .where(
                    MessageNonceReservation.state == NonceState.SPENT.value,
                    MessageNonceReservation.outcome
                    == WriteOutcomeValue.IN_FLIGHT.value,
                )
                .order_by(MessageNonceReservation.reserved_at.desc())
                .limit(MAX_UNFINISHED_REPORTED)
            )
            .scalars()
            .all()
        )

    unfinished = tuple(
        UnfinishedWrite(
            reservation_id=row.id,
            did=row.did,
            room=row.room,
            nonce=row.nonce,
            reserved_at=row.reserved_at,
        )
        for row in rows
    )
    return ReconciliationReport(
        scanned_at=scanned_at,
        unfinished=unfinished,
        detail=RECONCILIATION_DETAIL if unfinished else NOTHING_UNFINISHED_DETAIL,
    )


__all__ = [
    "MAX_UNFINISHED_REPORTED",
    "NOTHING_UNFINISHED_DETAIL",
    "RECONCILIATION_DETAIL",
    "ReconciliationReport",
    "UnfinishedWrite",
    "scan_unfinished_writes",
]
