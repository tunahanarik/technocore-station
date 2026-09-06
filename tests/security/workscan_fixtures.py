"""Shared fixtures for the Package H1 work-scan tests.

Everything here is synthetic. **No test in this package contacts Technocore,
Kibble or any other service**: the autouse guard in ``tests/conftest.py``
blocks the network at two layers, and every client below is driven through an
``httpx.MockTransport``.

The documents are shaped after the *pinned* ``openapi.json`` - the required
fields of ``/rooms`` and ``/r/{room}`` and no others - because the poverty of
the published ``rooms[]`` entry schema is itself the subject of several tests:
the schema declares the array items as bare objects and names no properties,
so a build that read a field the prose did not name would be reading a field
nobody published.

Every room name below carries ``test-only`` or is one the product refuses, so
no fixture can be mistaken for a room anybody should write to. ``lobby``
appears in exactly one place: the test that proves it is refused.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

#: A room name that passes the published pattern and carries no class marker.
ROOM = "test-only-room"

#: A second one, so "the scan reads the set the user chose" is testable with
#: more than one element.
SECOND_ROOM = "test-only-other"

#: The class markers a successful manifest check publishes. The same four the
#: pinned reference defines; passed to every call that resolves a room, since
#: an empty set is a refusal by design.
MARKERS = frozenset({"p", "mb", "d", "e"})

#: A line that matches a signal. Turkish, because the product is.
HELP_LINE = "kim yapabilir bu isi, bir yardimci olabilir mi acaba"

#: A line that matches the defect signal.
DEFECT_LINE = "TEST-ONLY: script calismiyor, hata veriyor"

#: A line that matches no signal at all. Its presence is what makes "lines
#: were read and produced nothing" distinguishable from "no lines were read".
QUIET_LINE = "TEST-ONLY: bugun hava guzel"

#: The user's actual complaint, as a line.
#:
#: Real work, phrased the way people phrase things: somebody has a broken
#: build and would like company. It contains **none** of the twenty-nine
#: literal markers the pattern list carried, so the build the user measured
#: produced nothing from it - no candidate and no refusal - and their three
#: rooms came back empty. ADR-0014 is about this line.
ORDINARY_WORK_LINE = (
    "TEST-ONLY: dun aksamdan beri derleme adimi yarida kesiliyor, "
    "bakabilecek biri varsa cok sevinirim"
)

#: A line that matches a prohibited shape *and* a signal, so the ordering of
#: the two checks is testable rather than assumed.
WALLET_LINE = "kim yapabilir: wallet baglayip claim alacak biri lazim"

#: The published ``did:key`` shape, exactly 56 characters. Test-only, and it
#: is a *shape* rather than a key: nothing here signs or verifies anything.
DID_KEY_TEST_ONLY = "did:key:z6Mk" + "1" * 44

#: A self-asserted nickname.
NICKNAME = "test-only-nick"


def message(
    seq: int,
    text: str,
    *,
    author: str = NICKNAME,
    ts: str = "2026-09-04T10:00:00.000001Z",
) -> dict[str, Any]:
    """One stored message, with the four fields the schema marks required."""
    return {"seq": seq, "ts": ts, "from": author, "text": text}


def room_document(
    *,
    room: str = ROOM,
    messages: list[dict[str, Any]] | None = None,
    count: int | None = None,
    first_seq: int | None = 1,
    last_seq: int | None = None,
) -> dict[str, Any]:
    """A ``/r/{room}?format=json`` body.

    ``count`` and ``last_seq`` default to values that agree with the array,
    and both can be overridden - which is the point, because the pinned
    description tells a client to read ``count`` rather than assume it, and a
    test that could not make the two disagree would not be testing that.
    """
    items = messages if messages is not None else [message(1, HELP_LINE)]
    return {
        "room": room,
        "count": len(items) if count is None else count,
        "first_seq": first_seq,
        "last_seq": (items[-1]["seq"] if items else 0) if last_seq is None else last_seq,
        "messages": items,
    }


def index_document(
    *, rooms: list[dict[str, Any]] | None = None, total: int | None = None
) -> dict[str, Any]:
    """A ``/rooms?format=json`` body.

    Carries the ``untrusted`` object the service publishes, so a test can show
    that this build does not depend on it: the caller-written fields are named
    in our own module, and a reply that shortened this list would not widen
    what we trust.
    """
    listed = (
        rooms
        if rooms is not None
        else [
            {"room": ROOM, "topic": "TEST-ONLY baslik"},
            {"room": SECOND_ROOM, "topic": ""},
        ]
    )
    return {
        "rooms": listed,
        "total": len(listed) if total is None else total,
        "capacity": 5120,
        "bytes": 1024,
        "notes": {},
        "engagement": {},
        "untrusted": {
            "fields": ["room", "topic"],
            "note": "TEST-ONLY: caller-written fields.",
        },
    }


def body_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(document).encode("utf-8")


# ---------------------------------------------------------------------------
# Recording transports
# ---------------------------------------------------------------------------


@dataclass
class TransportRecorder:
    """Every request a client actually attempted, and what it carried.

    Counting rather than asserting is the point on the startup tests: "no
    outbound request happens at launch" is a claim about a number, and reading
    the number back is the only way to know rather than to believe.
    """

    requests: list[httpx.Request] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.requests)

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "no request was attempted"
        return self.requests[-1]

    def urls(self) -> list[str]:
        return [str(request.url) for request in self.requests]


def recording_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[httpx.MockTransport, TransportRecorder]:
    """A mock transport that answers with ``handler`` and remembers the call."""
    recorder = TransportRecorder()

    def record(request: httpx.Request) -> httpx.Response:
        request.read()
        recorder.requests.append(request)
        return handler(request)

    return httpx.MockTransport(record), recorder


def json_transport(
    document: dict[str, Any],
) -> tuple[httpx.MockTransport, TransportRecorder]:
    """Answer every request with one JSON document and the right media type."""
    return recording_transport(
        lambda _: httpx.Response(
            200,
            content=body_bytes(document),
            headers={"content-type": "application/json"},
        )
    )


def routing_transport(
    documents: dict[str, dict[str, Any]],
) -> tuple[httpx.MockTransport, TransportRecorder]:
    """Answer per request path, so a multi-room scan can be driven honestly.

    A path with no entry answers 404, which is what makes "one room failed and
    the others still produced candidates" reachable in a test.
    """

    def answer(request: httpx.Request) -> httpx.Response:
        document = documents.get(request.url.path)
        if document is None:
            return httpx.Response(404, content=b"nope", headers={"content-type": "text/plain"})
        return httpx.Response(
            200,
            content=body_bytes(document),
            headers={"content-type": "application/json"},
        )

    return recording_transport(answer)


def status_transport(
    status_code: int, *, body: bytes = b"{}", headers: dict[str, str] | None = None
) -> tuple[httpx.MockTransport, TransportRecorder]:
    return recording_transport(
        lambda _: httpx.Response(status_code, content=body, headers=headers)
    )


def refusing_transport(
    exception: Exception,
) -> tuple[httpx.MockTransport, TransportRecorder]:
    """A transport that fails the way a network does."""

    def raise_it(_: httpx.Request) -> httpx.Response:
        raise exception

    return recording_transport(raise_it)


def never_called_transport() -> tuple[httpx.MockTransport, TransportRecorder]:
    """A transport that fails loudly if anything reaches it.

    Used where the claim is "nothing outbound happens here". The recorder is
    still returned so a test can assert the count is zero as well, which
    distinguishes "nothing was attempted" from "the assertion never ran".
    """

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            f"an outbound request was attempted: {request.method} {request.url}"
        )

    return recording_transport(refuse)


__all__ = [
    "DEFECT_LINE",
    "DID_KEY_TEST_ONLY",
    "HELP_LINE",
    "MARKERS",
    "NICKNAME",
    "ORDINARY_WORK_LINE",
    "QUIET_LINE",
    "ROOM",
    "SECOND_ROOM",
    "WALLET_LINE",
    "TransportRecorder",
    "body_bytes",
    "index_document",
    "json_transport",
    "message",
    "never_called_transport",
    "recording_transport",
    "refusing_transport",
    "room_document",
    "routing_transport",
    "status_transport",
]


# ---------------------------------------------------------------------------
# The reading lane, stubbed
# ---------------------------------------------------------------------------
#
# ADR-0014 made candidate derivation depend on a model's verdict, so the tests
# that are *not* about the model need a way to supply one without a provider.
# This is that way, and it is deliberately dumb: a mapping from ``seq`` to
# shape, decided by the test. Nothing here parses text, so a test that asserts
# something about a candidate is asserting it about the derivation rather than
# about a second implementation of the recogniser that was just deleted.


@dataclass
class StubReader:
    """A :class:`station_api.workscan.reading.LineReader` a test writes.

    ``verdicts`` maps a sequence number to a shape; a line with no entry comes
    back with no verdict, which is the model saying "no work here".
    ``refusals`` maps a sequence number to a reason, for the paths where the
    reading did not happen.

    It records what it was shown, because several tests are about exactly
    that: which lines reached the lane, and which did not.
    """

    verdicts: dict[int, Any] = field(default_factory=dict)
    refusals: dict[int, Any] = field(default_factory=dict)
    seen: list[tuple[int, str]] = field(default_factory=list)
    calls: int = 0

    def classify(self, lines: Any, *, counter: Any) -> Any:
        from station_api.workscan.reading import (
            LineVerdict,
            ReadingRefusal,
            RoomReading,
        )

        self.calls += 1
        self.seen.extend((line.seq, line.text) for line in lines)
        return RoomReading(
            verdicts=tuple(
                LineVerdict(seq=line.seq, signal=self.verdicts[line.seq])
                for line in lines
                if line.seq in self.verdicts
            ),
            refusals=tuple(
                ReadingRefusal(
                    seq=line.seq,
                    reason=self.refusals[line.seq],
                    detail="TEST-ONLY refusal detail.",
                )
                for line in lines
                if line.seq in self.refusals
            ),
            model_calls_used=counter.used,
        )


#: What the fixture lines are classified as, so a test that is not about the
#: model keeps the meaning it had before ADR-0014.
#:
#: Text-keyed rather than ``seq``-keyed because the same line appears at
#: different sequence numbers across this suite, and a table keyed by number
#: would have to be re-stated in every test. ``QUIET_LINE`` is deliberately
#: absent: "the model read this line and found no work" is the answer several
#: tests depend on being distinguishable from "this line was never read".
FIXTURE_VERDICTS: dict[str, str] = {}


@dataclass
class FixtureReader:
    """A reader that answers for the fixture lines and for nothing else.

    Used where a test needs a scan to *produce* something and is about
    anything other than the reading lane - the HTTP surface, the task
    machine, the request file. It contacts nobody and spends nothing.
    """

    def classify(self, lines: Any, *, counter: Any) -> Any:
        from station_api.workscan.reading import LineVerdict, RoomReading

        verdicts = []
        for line in lines:
            # Containment rather than equality: several tests wrap a fixture
            # line in hostile text, and the point of those tests is what
            # happens *after* a candidate exists.
            for known, signal in FIXTURE_VERDICTS.items():
                if known in line.text:
                    verdicts.append(LineVerdict(seq=line.seq, signal=signal))
                    break
        return RoomReading(verdicts=tuple(verdicts))


def reading_of(**verdicts: Any) -> Any:
    """A :class:`RoomReading` naming ``seq`` to shape, for direct derivation.

    Written as ``reading_of(s1=SignalId.HELP_WANTED)`` because keyword names
    cannot start with a digit; the ``s`` is stripped.
    """
    from station_api.workscan.reading import LineVerdict, RoomReading

    return RoomReading(
        verdicts=tuple(
            LineVerdict(seq=int(name.lstrip("s")), signal=signal)
            for name, signal in verdicts.items()
        )
    )


def _fill_fixture_verdicts() -> None:
    """Populate the table after import, so the enum is loaded lazily.

    Written as a function rather than as a literal above because importing
    ``station_api.workscan.candidates`` at module scope would make this
    fixtures file part of every import cycle it participates in.
    """
    from station_api.workscan.candidates import SignalId

    FIXTURE_VERDICTS.update(
        {
            HELP_LINE: SignalId.HELP_WANTED,
            DEFECT_LINE: SignalId.DEFECT_REPORT,
            ORDINARY_WORK_LINE: SignalId.HELP_WANTED,
            # Classified as work on purpose: the prohibition has to be what
            # refuses it, not the absence of a verdict.
            WALLET_LINE: SignalId.HELP_WANTED,
        }
    )


_fill_fixture_verdicts()

__all__ += ["FIXTURE_VERDICTS", "FixtureReader", "StubReader", "reading_of"]
