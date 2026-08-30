"""Persistence for official-source checks.

These rows are **evidence**, not authority. Nothing in this module is
consulted by the write gate: the gate reads the in-process verdict, so a
successful check recorded an hour ago cannot re-open the outbound door after
a restart. Keeping that separation in the storage layer, rather than only in
the caller, is what makes it hard to undo by accident.

Retention is bounded. A check writes one row per source, a user may press the
button repeatedly, and an evidence table that grows without limit eventually
becomes the reason someone deletes the database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from station_api.db.models import ManifestCheck, OfficialSourceSnapshot
from station_api.technocore.projection import safe_display
from station_api.technocore.sources import OfficialSource

#: Number of check runs kept. Fifty is plenty for reviewing a drift event and
#: small enough that the table never becomes a disk problem.
RETAINED_CHECKS = 50

#: Longest excerpt stored per source. Enough to recognise a document, far too
#: little to be a copy of it.
MAX_EXCERPT_CHARS = 4096


#: Per-source outcomes. A Literal rather than a bare str so the API layer
#: cannot widen it by accident: the response model declares the same three
#: values, and mypy checks that the two agree.
Outcome = Literal["ok", "fetch_error", "parse_error"]


class SnapshotOutcome:
    """The three outcome values, named."""

    OK: Outcome = "ok"
    FETCH_ERROR: Outcome = "fetch_error"
    PARSE_ERROR: Outcome = "parse_error"


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """One source's result, ready to persist."""

    source: OfficialSource
    fetched_at: datetime
    outcome: Outcome
    http_status: int = 0
    content_type: str = ""
    etag: str = ""
    last_modified: str = ""
    content_sha256: str = ""
    byte_count: int = 0
    body: bytes = b""
    detail: str = ""

    @property
    def short_hash(self) -> str:
        return self.content_sha256[:12]


def _excerpt(body: bytes) -> str:
    """A bounded, swept excerpt of a remote document.

    Decoded leniently and swept through the same rule the protocol projection
    uses, because this text ends up in a database a human will read: a
    document that embeds a terminal escape or a megabyte of padding should
    not be able to put either there.
    """
    if not body:
        return ""
    text = body.decode("utf-8", errors="replace")
    return safe_display(text[: MAX_EXCERPT_CHARS * 2])[:MAX_EXCERPT_CHARS]


def record_check(
    engine: Engine,
    *,
    started_at: datetime,
    completed_at: datetime,
    state: str,
    reasons: tuple[str, ...],
    critical_count: int,
    warning_count: int,
    records: tuple[SourceRecord, ...],
) -> str:
    """Write one check and its per-source snapshots, then prune.

    A single transaction: either the check row and every snapshot land, or
    none of them do. A half-written check would be evidence of something that
    never happened.
    """
    check_id = uuid.uuid4().hex

    with Session(engine) as session, session.begin():
        session.add(
            ManifestCheck(
                id=check_id,
                started_at=started_at,
                completed_at=completed_at,
                state=state,
                critical_count=critical_count,
                warning_count=warning_count,
                reasons="\n".join(reasons),
            )
        )
        for record in records:
            session.add(
                OfficialSourceSnapshot(
                    id=uuid.uuid4().hex,
                    check_id=check_id,
                    source_id=record.source.id.value,
                    url=record.source.url,
                    authority=record.source.authority,
                    fetched_at=record.fetched_at,
                    http_status=record.http_status,
                    content_type=record.content_type[:128],
                    etag=record.etag[:256],
                    last_modified=record.last_modified[:128],
                    content_sha256=record.content_sha256,
                    byte_count=record.byte_count,
                    snapshot_excerpt=_excerpt(record.body),
                    outcome=record.outcome,
                    detail=safe_display(record.detail),
                )
            )
        _prune(session)

    return check_id


def _prune(session: Session) -> None:
    """Keep the newest ``RETAINED_CHECKS`` runs and delete the rest.

    Snapshots are deleted explicitly rather than left to the foreign key's
    ``ON DELETE CASCADE``: SQLite only enforces that cascade while ``PRAGMA
    foreign_keys`` is on, and a retention policy that silently depends on a
    pragma is a leak waiting to happen.
    """
    keep = session.scalars(
        select(ManifestCheck.id)
        .order_by(ManifestCheck.completed_at.desc(), ManifestCheck.id.desc())
        .limit(RETAINED_CHECKS)
    ).all()
    if not keep:
        return

    stale = session.scalars(
        select(ManifestCheck.id).where(ManifestCheck.id.not_in(keep))
    ).all()
    if not stale:
        return

    session.execute(
        delete(OfficialSourceSnapshot).where(OfficialSourceSnapshot.check_id.in_(stale))
    )
    session.execute(delete(ManifestCheck).where(ManifestCheck.id.in_(stale)))


def count_checks(engine: Engine) -> int:
    """How many check runs are retained. For tests and diagnostics."""
    with Session(engine) as session:
        return len(session.scalars(select(ManifestCheck.id)).all())


def count_snapshots(engine: Engine) -> int:
    """How many per-source snapshots are retained."""
    with Session(engine) as session:
        return len(session.scalars(select(OfficialSourceSnapshot.id)).all())


__all__ = [
    "MAX_EXCERPT_CHARS",
    "RETAINED_CHECKS",
    "Outcome",
    "SnapshotOutcome",
    "SourceRecord",
    "count_checks",
    "count_snapshots",
    "record_check",
]
