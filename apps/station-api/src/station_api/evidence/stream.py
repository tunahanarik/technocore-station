"""The export stream scanner.

One request, scanned line by line, holding a bounded amount of it.

Why the existing capped reader could not be reused
--------------------------------------------------
``client.py::_read_capped`` and ``write_client.py::_read_capped`` both stream,
and both then ``b"".join(chunks)`` - a whole document in memory, which is the
right trade for a 2 MiB manifest and the wrong one for a room ring that the
pinned reference lets run to 10 MiB with no server-side slicing (the export
lane publishes "No query parameters", and no ``Range`` support). The cap here
is 12 MiB, 10 MiB of ring plus room for a header line and growth, and the
peak memory is a few hundred kilobytes rather than the cap.

What is kept, and nothing else (ADR-0003 2)
-------------------------------------------
* **our own line's raw bytes**, with its byte offset and length;
* a bounded neighbourhood - bounded in lines *and* in bytes, because two
  bounds are needed: three short lines and three 10 MiB lines are both "three
  lines";
* the running SHA-256 of **everything this scan read**, including the part
  read after the match. When the cap stopped the scan that is the scanned
  prefix and not the whole body, which is why ``truncated`` travels with the
  digest everywhere it goes: a hash of a prefix described as a hash of the
  document would be a small lie with a very long life;
* the line count, and how many lines could not be read.

The full ring is never archived.

Line terminators, and the byte that is not one
----------------------------------------------
The reference writes ``orjson.dumps(rec) + b"\\n"``, so ``\\n`` is the only
terminator this scanner splits on. A body served with CRLF endings therefore
leaves the ``\\r`` at the end of the payload, and it is **kept**: the stored
line is the bytes that arrived, and stripping one of them to make the record
tidier would be the re-serialisation this whole module refuses to do. The
match still works, because a trailing ``\\r`` is whitespace to a JSON reader.

Parsing to find, raw bytes to keep
----------------------------------
A line is parsed to answer one question - "is this ours?" - and the answer is
recorded as the **bytes that were on the wire**, never as a re-serialisation
of the parse. That distinction is the whole point of the export lane: the
reference publishes it as "bytes exactly as written, never re-serialized - so
a signed record re-verifies from its exported line alone". A record rebuilt
from parsed fields would verify against itself and prove nothing.

Nonces are read as integers, never as floats
--------------------------------------------
The pinned description is explicit: "Parse ``nonce`` with a big-integer-safe
reader or keep it as digits: up to 19 digits is past 2^53, and a
float-rounded nonce fails good signatures." Python's ``int`` is arbitrary
precision and :func:`station_api.strict_json.loads_strict` produces one, so
the comparison below is exact. A line whose ``nonce`` arrives as a JSON float
is *not* rounded into a match - it fails the ``isinstance`` check and is not
ours, which is the fail-closed direction.
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from station_api.strict_json import StrictJsonError, loads_strict

#: Ceiling on the export body, on decompressed bytes, enforced while
#: streaming. 10 MiB is the reference's own ``limits.room_ring_bytes``; the
#: rest is headroom so a ring at its limit is not reported as truncated
#: because of a few hundred bytes of tail.
MAX_STREAM_BYTES = 12 * 1024 * 1024

#: Longest single line that can be a candidate. A record is a small JSON
#: object; anything larger is not ours and is not buffered to find out.
MAX_LINE_BYTES = 256 * 1024

#: How many lines of context are kept on each side of ours.
MAX_WINDOW_LINES = 2

#: Ceiling on the bytes kept per neighbouring line. Two bounds, because a
#: line count alone bounds nothing.
MAX_WINDOW_LINE_BYTES = 4 * 1024

#: How much is read from the transport at a time. The transient overshoot at
#: the cap is bounded by this and trimmed immediately.
CHUNK_BYTES = 64 * 1024

#: The line terminator the reference writes (``orjson.dumps(rec) + b"\\n"``).
LINE_TERMINATOR = b"\n"


@dataclass(frozen=True, slots=True)
class LineMatch:
    """The three public protocol values that identify our own record.

    All three, not one. ``sig`` alone would be enough in practice, but a
    record is ours because *this key* wrote *this nonce* with *this
    signature*; comparing all three means a partial match is a miss rather
    than a near-miss nobody notices.
    """

    did: str
    #: The exact digits that entered the canonical string. Compared as digits.
    nonce: str
    signature: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    """What one pass over an export stream established.

    Every field is a fact about the scan. None of them is a verdict: the six
    capture states in :mod:`station_api.evidence.states` are derived from this
    together with the generation header, and this module deliberately does not
    know about them.
    """

    #: Our record's bytes, without the line terminator. ``None`` when the scan
    #: did not find it - which proves nothing on its own (the ring forgets).
    line: bytes | None
    #: Byte offset of the first byte of that line within the stream.
    line_offset: int | None
    #: Bounded context, each entry already truncated to the per-line ceiling.
    window_before: tuple[bytes, ...] = ()
    window_after: tuple[bytes, ...] = ()
    #: SHA-256 over every byte this scan read, including everything after the
    #: match - and **only** that. When ``truncated`` is true the scan stopped
    #: at the cap, so this covers the scanned prefix rather than the body.
    stream_sha256: str = ""
    scanned_bytes: int = 0
    line_count: int = 0
    #: Lines that could not be read as a record. Unreadable is not altered.
    unreadable_lines: int = 0
    #: True when the cap stopped the scan, so absence means nothing at all.
    truncated: bool = False
    #: Bytes actually retained by this scan, for the memory-bound assertion.
    retained_bytes: int = field(default=0)

    @property
    def found(self) -> bool:
        return self.line is not None

    @property
    def line_length(self) -> int:
        return 0 if self.line is None else len(self.line)


def _is_our_line(payload: bytes, match: LineMatch) -> bool | None:
    """``True``/``False`` for a readable line, ``None`` when unreadable.

    ``loads_strict`` is used rather than ``json.loads`` for the property that
    matters on a line we did not write: a document with a duplicate ``sig``
    key means two different things to two readers, and silently keeping the
    last one would let a crafted line claim to be ours.
    """
    try:
        record = loads_strict(payload, max_bytes=MAX_LINE_BYTES)
    except StrictJsonError:
        return None

    if record.get("from") != match.did:
        return False
    if record.get("sig") != match.signature:
        return False

    nonce = record.get("nonce")
    # bool is an int subclass; ``True`` is not a nonce. A float here is a
    # rounded nonce and is refused rather than compared.
    if not isinstance(nonce, int) or isinstance(nonce, bool):
        return False
    return str(nonce) == match.nonce


def scan_export_stream(
    chunks: Iterable[bytes],
    *,
    match: LineMatch,
    cap: int = MAX_STREAM_BYTES,
) -> ScanResult:
    """Scan an NDJSON export, keeping a bounded amount of it.

    ``chunks`` is any iterable of bytes - in production ``iter_bytes`` from a
    streaming response, in tests a list. The scanner never sees a URL, a
    transport or a room name, so it can be exercised on hostile input without
    a network in the picture at all.
    """
    digest = hashlib.sha256()
    buffer = bytearray()
    scanned = 0
    consumed = 0  # bytes of complete lines already handed on, i.e. the offset
    line_count = 0
    unreadable = 0
    truncated = False
    skipping_overlong = False
    # True when the last chunk handled by the drop-everything path below ended
    # mid-line. That path counts terminators, so a final line without one
    # would otherwise not be counted at all.
    open_tail_dropped = False

    before: deque[bytes] = deque(maxlen=MAX_WINDOW_LINES)
    after: list[bytes] = []
    found: bytes | None = None
    found_offset: int | None = None

    def take_line(payload: bytes) -> None:
        """Classify one complete line. Never holds more than the bounds."""
        nonlocal found, found_offset, unreadable, line_count
        line_count += 1

        if found is not None:
            if len(after) < MAX_WINDOW_LINES:
                after.append(payload[:MAX_WINDOW_LINE_BYTES])
            return

        verdict = _is_our_line(payload, match)
        if verdict is None:
            unreadable += 1
            before.append(payload[:MAX_WINDOW_LINE_BYTES])
            return
        if verdict:
            found = payload
            found_offset = consumed
            return
        before.append(payload[:MAX_WINDOW_LINE_BYTES])

    for chunk in chunks:
        if not chunk:
            continue
        remaining = cap - scanned
        if len(chunk) > remaining:
            # Strictly greater: a body that is exactly the cap was read whole,
            # and reporting it as truncated would turn a complete scan into a
            # state that says "absence means nothing".
            chunk = chunk[:remaining]
            truncated = True
        digest.update(chunk)
        scanned += len(chunk)

        # Once our line and its whole trailing window are in hand there is
        # nothing left to buffer: the rest of the stream still feeds the hash
        # and the line count, and is dropped immediately. This is what keeps
        # peak memory independent of the body size.
        if found is not None and len(after) >= MAX_WINDOW_LINES:
            buffer.clear()
            line_count += chunk.count(LINE_TERMINATOR)
            open_tail_dropped = not chunk.endswith(LINE_TERMINATOR)
            if truncated:
                break
            continue

        buffer.extend(chunk)
        while True:
            index = buffer.find(LINE_TERMINATOR)
            if index < 0:
                if len(buffer) > MAX_LINE_BYTES:
                    # A line longer than any record we could have written.
                    # Drop it rather than grow, and count it as unreadable:
                    # "too long to read" is not "absent" and not "altered".
                    if not skipping_overlong:
                        skipping_overlong = True
                        unreadable += 1
                    consumed += len(buffer)
                    buffer.clear()
                break
            payload = bytes(buffer[:index])
            del buffer[: index + 1]
            if skipping_overlong:
                skipping_overlong = False
                consumed += len(payload) + 1
                continue
            take_line(payload)
            consumed += len(payload) + 1

        if truncated:
            break

    # A final line with no terminator. The reference heals a torn tail on the
    # next append, so an unterminated last line is a real record often enough
    # to be worth reading - but only when the scan reached the end. At the cap
    # the tail is a fragment of a line we did not finish reading, and reading
    # a fragment as a record is how a scanner invents evidence.
    if buffer and not truncated and not skipping_overlong:
        take_line(bytes(buffer))
    elif open_tail_dropped and not truncated:
        # Same rule, on the path that keeps no buffer: once our line and its
        # window are in hand the rest of the body is dropped as it arrives and
        # only its terminators are counted, so a completed stream whose last
        # line has none was one line short. The line is not read - there is
        # nothing left to look for - but it existed and is counted.
        line_count += 1

    retained = (
        (0 if found is None else len(found))
        + sum(len(item) for item in before)
        + sum(len(item) for item in after)
    )

    return ScanResult(
        line=found,
        line_offset=found_offset,
        window_before=tuple(before),
        window_after=tuple(after),
        stream_sha256=digest.hexdigest(),
        scanned_bytes=scanned,
        line_count=line_count,
        unreadable_lines=unreadable,
        truncated=truncated,
        retained_bytes=retained,
    )


__all__ = [
    "CHUNK_BYTES",
    "LINE_TERMINATOR",
    "MAX_LINE_BYTES",
    "MAX_STREAM_BYTES",
    "MAX_WINDOW_LINES",
    "MAX_WINDOW_LINE_BYTES",
    "LineMatch",
    "ScanResult",
    "scan_export_stream",
]
