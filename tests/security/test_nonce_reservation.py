"""Nonce reservation: monotonic, per ``(did, room)``, and never reused.

The rule is one line of the protocol contract (5) and the pinned manifest:
a nonce is strictly greater than the last one that key used in that room, and
it is reserved inside a transaction **before** anything is signed. Everything
below is a way for that rule to be broken, tested to prove it is not:

* two callers racing for the same number, with real threads and real
  contention rather than a simulated one;
* a clock that jumps backwards;
* a process that dies between reserving and sending, and comes back;
* a reservation that is abandoned;
* the 19-digit ceiling the wire format imposes;
* a leading zero, which is the same number and different signed bytes.

Every DID here is a TEST-ONLY fixture string. No vault, no seed and no
network is involved: this is the counter, on its own.
"""

from __future__ import annotations

import itertools
import threading
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from station_api.compose.nonce import (
    MAX_NONCE_VALUE,
    NonceExhaustedError,
    NonceReserver,
    UnknownReservationError,
)
from station_api.config import Settings
from station_api.db.migrations_runner import initialise_database
from station_api.db.models import (
    MessageNonceReservation,
    NonceState,
    WriteOutcomeValue,
)
from technocore_conform import MAX_NONCE_DIGITS, is_valid_nonce

pytestmark = pytest.mark.security

#: TEST-ONLY. A syntactically plausible did:key that belongs to nobody.
TEST_ONLY_DID = "did:key:z6MkTESTONLYnotarealidentity0000000000000000000000000"
TEST_ONLY_DID_ALT = "did:key:z6MkTESTONLYsecondfixture000000000000000000000000000"

#: TEST-ONLY room names. Never the lobby (INV-05).
TEST_ROOM = "mb-station-test-only"
TEST_ROOM_ALT = "e-station-test-only"


@pytest.fixture
def reserver(engine: Engine) -> NonceReserver:
    return NonceReserver(engine)


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------


def test_a_reserved_nonce_is_a_valid_wire_nonce(reserver: NonceReserver) -> None:
    reservation = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)

    assert is_valid_nonce(reservation.nonce)
    assert reservation.nonce == str(reservation.value)
    assert len(reservation.nonce) <= MAX_NONCE_DIGITS


def test_successive_reservations_strictly_increase(reserver: NonceReserver) -> None:
    values = [
        reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM).value for _ in range(20)
    ]

    assert values == sorted(values)
    assert len(set(values)) == len(values)
    for earlier, later in itertools.pairwise(values):
        assert later > earlier


def test_the_counter_is_scoped_to_the_did_and_the_room(
    reserver: NonceReserver,
) -> None:
    """Two rooms, and two identities, keep separate counters.

    The protocol scopes the counter to the pair, so a shared counter would
    burn numbers nobody needed - and, worse, a *global* counter would leak
    how much the user writes elsewhere into every room they write to.
    """
    first = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    other_room = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM_ALT)
    other_did = reserver.reserve(did=TEST_ONLY_DID_ALT, room=TEST_ROOM)

    assert reserver.last_value(did=TEST_ONLY_DID, room=TEST_ROOM) == first.value
    assert reserver.last_value(did=TEST_ONLY_DID, room=TEST_ROOM_ALT) == other_room.value
    assert reserver.last_value(did=TEST_ONLY_DID_ALT, room=TEST_ROOM) == other_did.value


def test_a_fresh_counter_starts_at_the_millisecond_clock(engine: Engine) -> None:
    """The clock is the floor, so a new database does not restart low.

    A counter that began at 1 on a restored backup - or on a second machine
    holding the same identity - would have every write refused as a replay.
    """
    fixed_ms = 1_764_000_000_000
    reserver = NonceReserver(engine, clock_ms=lambda: fixed_ms)

    assert reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM).value == fixed_ms


def test_a_clock_that_jumps_backwards_does_not_reissue_a_number(
    engine: Engine,
) -> None:
    """``max(local + 1, clock)``: the local value wins when the clock lies.

    Daylight saving, an NTP correction and a virtual machine resuming from a
    snapshot all move a wall clock backwards. None of them may hand out a
    nonce this pair has already used.
    """
    ticks = iter([1_764_000_000_000, 1_000, 1_000, 1_764_000_000_000])
    reserver = NonceReserver(engine, clock_ms=lambda: next(ticks))

    first = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    after_jump = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    still_back = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    recovered = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)

    assert after_jump.value == first.value + 1
    assert still_back.value == after_jump.value + 1
    assert recovered.value > still_back.value


def test_no_reserved_nonce_ever_carries_a_leading_zero(engine: Engine) -> None:
    """ADR-0002 4.2. ``"007"`` and ``"7"`` are one number and two signatures.

    The server compares the nonce as an integer while the signature covers
    it as text, so a leading zero produces a signature over bytes the server
    did not store. The value is rendered from an int, which makes it
    unrepresentable rather than merely absent - asserted over a range of
    magnitudes so the property is not read off one lucky value.
    """
    def fixed(source: Iterator[int]) -> Callable[[], int]:
        # Bound explicitly rather than closed over the loop variable: a
        # closure here would read whichever value the loop had reached by
        # the time it ran, which is a real bug and a confusing one.
        return lambda: next(source)

    for start in (1, 9, 10, 99, 1000, 1_764_000_000_000):
        reserver = NonceReserver(engine, clock_ms=fixed(iter([start, start, start])))
        room = f"e-test-only-{start}"
        for _ in range(3):
            nonce = reserver.reserve(did=TEST_ONLY_DID, room=room).nonce
            assert not nonce.startswith("0")
            assert is_valid_nonce(nonce)


# ---------------------------------------------------------------------------
# Concurrency, with real threads
# ---------------------------------------------------------------------------


def _reserve_many(
    reserver: NonceReserver, *, room: str, count: int, into: list[int]
) -> None:
    for _ in range(count):
        into.append(reserver.reserve(did=TEST_ONLY_DID, room=room).value)


def test_concurrent_reservations_never_collide(reserver: NonceReserver) -> None:
    """Sixteen real threads, contending for one counter.

    Not a simulated race: the threads run the real reservation path against
    the real database at the same time. Every number handed out must be
    distinct - two callers holding one nonce would mean two different
    payloads signed under it, which is exactly the replay the counter exists
    to prevent.
    """
    threads_count = 16
    per_thread = 12
    results: list[list[int]] = [[] for _ in range(threads_count)]
    barrier = threading.Barrier(threads_count)

    def worker(index: int) -> None:
        # Start together, so the contention is real rather than incidental.
        barrier.wait()
        _reserve_many(
            reserver, room=TEST_ROOM, count=per_thread, into=results[index]
        )

    threads = [
        threading.Thread(target=worker, args=(index,))
        for index in range(threads_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()

    values = [value for chunk in results for value in chunk]
    assert len(values) == threads_count * per_thread
    assert len(set(values)) == len(values), "a nonce was handed out twice"


def test_two_independent_reservers_on_one_database_never_collide(
    engine: Engine,
) -> None:
    """The lock is not the only guard, and this proves it.

    A process-level lock cannot reach a second Station opened against the
    same database file. Two ``NonceReserver`` instances share nothing but the
    engine, so what keeps them apart here is the ``UNIQUE(did, room,
    nonce_value)`` constraint and the bounded re-read behind it.
    """
    first = NonceReserver(engine)
    second = NonceReserver(engine)
    results: list[list[int]] = [[], []]
    barrier = threading.Barrier(2)

    def worker(index: int, reserver: NonceReserver) -> None:
        barrier.wait()
        _reserve_many(reserver, room=TEST_ROOM, count=25, into=results[index])

    threads = [
        threading.Thread(target=worker, args=(0, first)),
        threading.Thread(target=worker, args=(1, second)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()

    values = results[0] + results[1]
    assert len(values) == 50
    assert len(set(values)) == 50


def test_the_database_itself_refuses_a_duplicate(engine: Engine) -> None:
    """The constraint is real, not merely declared.

    If this ever stopped being enforced, the cross-process test above would
    still pass by luck of timing while guarding nothing.
    """
    from sqlalchemy.exc import IntegrityError

    reserver = NonceReserver(engine)
    taken = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)

    with pytest.raises(IntegrityError), Session(engine) as session, session.begin():
        session.add(
            MessageNonceReservation(
                id="0" * 32,
                did=TEST_ONLY_DID,
                room=TEST_ROOM,
                nonce=taken.nonce,
                nonce_value=taken.value,
                reserved_at=taken.reserved_at,
                state=NonceState.RESERVED.value,
                outcome="",
                settled_at=None,
                detail="",
            )
        )


# ---------------------------------------------------------------------------
# Crash, resume, cancel: a number is never returned to circulation
# ---------------------------------------------------------------------------


def test_a_crash_between_reserving_and_sending_burns_the_number(
    settings: Settings,
) -> None:
    """Reopen the same database and the counter carries on past the gap.

    The reservation is written before the request, so a process that dies
    holding one leaves the number spent. Simulated the only honest way:
    dispose the engine, open a new one on the same file, and carry on.
    """
    first_engine = initialise_database(settings.database_path, stage=4)
    reserver = NonceReserver(first_engine)
    orphan = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    # No settle call: this is the process dying mid-flight.
    first_engine.dispose()

    resumed_engine = initialise_database(settings.database_path, stage=4)
    resumed = NonceReserver(resumed_engine)
    after = resumed.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)

    assert after.value > orphan.value
    assert after.nonce != orphan.nonce

    # And the orphan is still on the record as reserved, so a human reading
    # the table sees an unfinished write rather than a gap.
    state, outcome = resumed.describe(orphan.id)
    assert state == NonceState.RESERVED.value
    assert outcome == ""
    resumed_engine.dispose()


def test_a_cancelled_reservation_is_not_returned_to_circulation(
    reserver: NonceReserver,
) -> None:
    """Cancelled is not unused.

    The counter is strictly increasing, so a number handed out and dropped
    is still burnt. Re-issuing it would mean two different payloads under one
    nonce - and the second one would be refused as a replay, after the user
    approved it.
    """
    cancelled = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    reserver.cancel(cancelled.id, detail="kullanici vazgecti")

    following = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)

    assert following.value > cancelled.value
    state, outcome = reserver.describe(cancelled.id)
    assert state == NonceState.CANCELLED.value
    assert outcome == WriteOutcomeValue.NOT_SENT.value


@pytest.mark.parametrize(
    "outcome",
    [
        WriteOutcomeValue.ACCEPTED,
        WriteOutcomeValue.REFUSED,
        WriteOutcomeValue.OUTCOME_UNKNOWN,
    ],
)
def test_every_send_outcome_leaves_the_nonce_spent(
    reserver: NonceReserver, outcome: WriteOutcomeValue
) -> None:
    """ADR-0002 3: all three outcomes consume the number.

    ``refused`` is the interesting row. The server proved it stored nothing,
    so the number is objectively unused - and it still may not be reissued,
    because the signature that carried it exists and could be replayed.
    """
    reservation = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    reserver.commit_to_send(reservation.id)
    reserver.record_outcome(reservation.id, outcome=outcome)

    state, recorded = reserver.describe(reservation.id)
    assert state == NonceState.SPENT.value
    assert recorded == outcome.value
    assert reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM).value > reservation.value


def test_a_nonce_cannot_be_committed_to_a_send_twice(
    reserver: NonceReserver,
) -> None:
    """The storage-layer half of the double-click guard.

    The approval token is single-use and would already have refused. This is
    the second, independent refusal: a counter that can be committed twice is
    not a property to leave resting on one check.
    """
    reservation = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    reserver.commit_to_send(reservation.id)

    with pytest.raises(UnknownReservationError):
        reserver.commit_to_send(reservation.id)


def test_settling_an_unknown_reservation_is_refused(
    reserver: NonceReserver,
) -> None:
    with pytest.raises(UnknownReservationError):
        reserver.commit_to_send("f" * 32)


# ---------------------------------------------------------------------------
# The wire ceiling
# ---------------------------------------------------------------------------


def test_the_ceiling_is_a_nineteen_digit_value() -> None:
    """The protocol allows 1-19 digits; the store holds 64 signed bits.

    The lower of the two is the real ceiling. Reserving a number the database
    cannot hold would corrupt the counter silently, which is worse than
    refusing.
    """
    assert len(str(MAX_NONCE_VALUE)) == MAX_NONCE_DIGITS
    assert MAX_NONCE_VALUE <= 2**63 - 1
    assert MAX_NONCE_VALUE <= 10**MAX_NONCE_DIGITS - 1
    assert is_valid_nonce(str(MAX_NONCE_VALUE))


def test_a_counter_at_the_ceiling_refuses_rather_than_overflowing(
    engine: Engine,
) -> None:
    """The last usable number is issued; the next request is refused.

    Not clamped, not wrapped, not silently widened to twenty digits - all
    three would produce a nonce the server rejects, after the user approved
    it. The refusal happens before anything is signed.
    """
    reserver = NonceReserver(engine, clock_ms=lambda: MAX_NONCE_VALUE - 1)

    last_but_one = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    assert last_but_one.value == MAX_NONCE_VALUE - 1

    final = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    assert final.value == MAX_NONCE_VALUE
    assert len(final.nonce) == MAX_NONCE_DIGITS

    with pytest.raises(NonceExhaustedError):
        reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)


def test_the_exhausted_counter_writes_no_row(engine: Engine) -> None:
    """A refused reservation leaves the table exactly as it was."""
    reserver = NonceReserver(engine, clock_ms=lambda: MAX_NONCE_VALUE)
    reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)

    with pytest.raises(NonceExhaustedError):
        reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)

    with Session(engine) as session:
        rows = session.scalars(
            select(MessageNonceReservation).where(
                MessageNonceReservation.did == TEST_ONLY_DID
            )
        ).all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# The stored row carries nothing it should not
# ---------------------------------------------------------------------------


def test_the_reservation_row_holds_only_public_protocol_values(
    reserver: NonceReserver, engine: Engine
) -> None:
    """A DID, a room and a nonce are public. Nothing else is stored.

    ``test_database.py::test_schema_has_no_secret_columns`` scans the column
    *names*; this scans the values actually written, which is the half a
    naming rule cannot catch.
    """
    reservation = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ROOM)
    reserver.commit_to_send(reservation.id)
    reserver.record_outcome(
        reservation.id, outcome=WriteOutcomeValue.ACCEPTED, detail="kabul edildi"
    )

    with Session(engine) as session:
        row = session.get(MessageNonceReservation, reservation.id)
        assert row is not None
        blob = " ".join(
            [row.id, row.did, row.room, row.nonce, row.state, row.outcome, row.detail]
        ).lower()

    for forbidden in ("seed", "private", "passphrase", "mnemonic", "vault"):
        assert forbidden not in blob
