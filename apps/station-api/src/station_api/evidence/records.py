"""The read-only view of an evidence record, and which levels it carries.

One dataclass, built from the ORM row and consumed by the export writers and
the API. It exists so the four trust levels have a shape in the code and not
only in a document: a caller cannot accidentally report level 2 as filled
when nothing was captured, because the level's own object says whether it is
filled and why.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from station_api.db.models import EvidenceRecord
from station_api.evidence.states import CAPTURE_DETAIL, CaptureState
from station_api.strict_json import (
    b64u_decode,
    b64u_encode,
    canonical_json_bytes,
    loads_strict,
)

#: The four levels, in the charter's order, with the names the charter fixes
#: (15.1). These strings appear in exports, so they are the *permitted*
#: spellings rather than convenient shorthands.
LEVEL_NAMES: tuple[str, ...] = (
    "Imza kaniti",
    "Sunucu gozlemi",
    "Yerel kayit zamani",
    "Harici anchor",
)

#: Why level 4 is empty. Written into every export, so "absent" never has to
#: be inferred from a missing key.
LEVEL_4_ABSENT = "MVP kapsaminda yoktur; null olarak yazilir."


@dataclass(frozen=True, slots=True)
class LevelState:
    """Whether one trust level is filled, and one sentence about it."""

    level: int
    name: str
    present: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvidenceView:
    """Everything about one record that may leave this process."""

    id: str
    reservation_id: str
    room: str
    did: str
    nonce: str
    canonical: str
    canonical_sha256: str
    signature: str
    signature_verified: bool
    request_sha256: str
    request_body: bytes
    response_sha256: str
    response_body: bytes
    http_status: int
    write_outcome: str
    capture_state: str
    capture_detail: str
    captured_at: datetime | None
    export_url: str
    #: The epoch this record was first seen under. The baseline, never
    #: overwritten.
    room_generation: str
    #: The epoch ``captured_line`` was read under, so the two can never be
    #: reported side by side while belonging to different rooms.
    capture_generation: str
    #: Sticky: this room has been seen under more than one epoch.
    generation_changed: bool
    captured_line: bytes | None
    captured_line_offset: int | None
    captured_line_length: int | None
    captured_window: tuple[bytes, ...]
    stream_sha256: str
    stream_bytes: int
    stream_truncated: bool
    stream_line_count: int
    unreadable_lines: int
    recorded_at: datetime
    #: Always ``None`` in this release, and written as ``null``.
    external_anchor: str | None

    @property
    def levels(self) -> tuple[LevelState, ...]:
        """Which levels this record actually carries.

        Level 2 is present only for ``line_captured``. The other five capture
        states are recorded honestly and are *not* a server observation: an
        absent line proves nothing, a truncated scan scanned nothing, and a
        changed generation makes the two sides incomparable (ADR-0003 3).
        """
        captured = self.capture_state == CaptureState.LINE_CAPTURED.value
        return (
            LevelState(
                level=1,
                name=LEVEL_NAMES[0],
                present=self.signature_verified,
                detail=(
                    "Station kendi kanonik metnini kendi imzasiyla dogruladi."
                    if self.signature_verified
                    else "Imza yerel olarak dogrulanamadi."
                ),
            ),
            LevelState(
                level=2,
                name=LEVEL_NAMES[1],
                present=captured,
                detail=self.capture_detail
                or (
                    CAPTURE_DETAIL[CaptureState(self.capture_state)]
                    if self.capture_state
                    else "Henuz yakalama denenmedi."
                ),
            ),
            LevelState(
                level=3,
                name=LEVEL_NAMES[2],
                present=True,
                detail="Bu makinenin saati; guvenilir bir zaman damgasi degildir.",
            ),
            LevelState(
                level=4,
                name=LEVEL_NAMES[3],
                present=False,
                detail=LEVEL_4_ABSENT,
            ),
        )


def encode_window(lines: tuple[bytes, ...]) -> str:
    """The neighbourhood, as a canonical JSON array of base64url strings.

    base64url rather than text: these are bytes from a stream we did not
    write, and decoding them for storage would mean deciding what to do with
    a sequence that is not UTF-8. Keeping them as bytes keeps that decision
    at the display boundary, where it belongs.
    """
    return canonical_json_bytes({"lines": [b64u_encode(line) for line in lines]}).decode(
        "utf-8"
    )


def decode_window(payload: str) -> tuple[bytes, ...]:
    if not payload:
        return ()
    document: dict[str, Any] = loads_strict(payload)
    raw = document.get("lines")
    if not isinstance(raw, list):
        return ()
    return tuple(b64u_decode(item) for item in raw if isinstance(item, str))


def to_view(row: EvidenceRecord) -> EvidenceView:
    """Project one ORM row. Never reaches for a column that is not here."""
    return EvidenceView(
        id=row.id,
        reservation_id=row.reservation_id,
        room=row.room,
        did=row.did,
        nonce=row.nonce,
        canonical=row.canonical,
        canonical_sha256=row.canonical_sha256,
        signature=row.signature,
        signature_verified=row.signature_verified,
        request_sha256=row.request_sha256,
        request_body=row.request_body,
        response_sha256=row.response_sha256,
        response_body=row.response_body,
        http_status=row.http_status,
        write_outcome=row.write_outcome,
        capture_state=row.capture_state,
        capture_detail=row.capture_detail,
        captured_at=row.captured_at,
        export_url=row.export_url,
        room_generation=row.room_generation,
        capture_generation=row.capture_generation,
        generation_changed=row.generation_changed,
        captured_line=row.captured_line,
        captured_line_offset=row.captured_line_offset,
        captured_line_length=row.captured_line_length,
        captured_window=decode_window(row.captured_window),
        stream_sha256=row.stream_sha256,
        stream_bytes=row.stream_bytes,
        stream_truncated=row.stream_truncated,
        stream_line_count=row.stream_line_count,
        unreadable_lines=row.unreadable_lines,
        recorded_at=row.recorded_at,
        external_anchor=row.external_anchor,
    )


__all__ = [
    "LEVEL_4_ABSENT",
    "LEVEL_NAMES",
    "EvidenceView",
    "LevelState",
    "decode_window",
    "encode_window",
    "to_view",
]
