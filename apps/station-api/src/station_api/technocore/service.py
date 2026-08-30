"""Orchestrates the read-only check and owns the verdict.

The verdict lives **in this process**, and starts at ``never_checked`` every
time Station launches. That is the load-bearing design decision of Stage 3:

* No network request happens at startup. Opening the app contacts nobody.
* Only a user pressing "check the official sources" runs a fetch.
* A successful check recorded in the database does not restore an open gate
  after a restart, because the gate never reads the database.

The alternative - persisting ``manifest_current=true`` and trusting it later -
would mean an outbound write could be authorised by a check that ran days ago
against a service that has since changed. The gate would be reporting history
as if it were the present.

Fail-closed throughout: a required document that cannot be fetched or parsed
produces ``unavailable``, and an unexpected exception produces ``unavailable``
too rather than escaping into a request handler.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine

from station_api.strict_json import StrictJsonError, loads_strict
from station_api.technocore.client import FetchResult, ReadOnlyTechnocoreClient
from station_api.technocore.errors import TechnocoreError
from station_api.technocore.projection import (
    DriftState,
    ProjectionResult,
    project,
    safe_display,
    unavailable,
)
from station_api.technocore.snapshot import (
    Outcome,
    SnapshotOutcome,
    SourceRecord,
    record_check,
)
from station_api.technocore.sources import SOURCES, OfficialSource, SourceId


@dataclass(frozen=True, slots=True)
class SourceStatus:
    """What the UI is allowed to know about one source."""

    source_id: str
    url: str
    authority: int
    outcome: Outcome
    http_status: int
    content_type: str
    etag: str
    last_modified: str
    short_hash: str
    byte_count: int
    detail: str
    rationale: str


@dataclass(frozen=True, slots=True)
class TechnocoreStatus:
    """The whole verdict, and everything needed to interpret it.

    Deliberately carries no document body. The raw manifests stay in the
    database excerpt for human review and never cross the HTTP boundary.
    """

    state: DriftState
    checked_at: datetime | None
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    reasons: tuple[str, ...] = ()
    sources: tuple[SourceStatus, ...] = ()
    projection: ProjectionResult | None = None
    check_id: str = ""

    @property
    def manifest_current(self) -> bool:
        """The single fact the write gate consumes."""
        return self.state is DriftState.CURRENT


@dataclass
class _State:
    """Mutable in-process state, guarded by a lock."""

    status: TechnocoreStatus = field(
        default_factory=lambda: TechnocoreStatus(
            state=DriftState.NEVER_CHECKED,
            checked_at=None,
            last_attempt_at=None,
            last_success_at=None,
        )
    )


class TechnocoreService:
    """Runs user-initiated read-only checks and remembers the last verdict."""

    def __init__(
        self,
        *,
        engine: Engine | None = None,
        client: ReadOnlyTechnocoreClient | None = None,
    ) -> None:
        self._engine = engine
        self._client = client if client is not None else ReadOnlyTechnocoreClient()
        self._lock = threading.Lock()
        self._state = _State()

    # --- read --------------------------------------------------------------

    def status(self) -> TechnocoreStatus:
        """The current verdict. Never triggers a network request."""
        with self._lock:
            return self._state.status

    @property
    def manifest_current(self) -> bool:
        return self.status().manifest_current

    # --- the user-initiated check -----------------------------------------

    def refresh(self) -> TechnocoreStatus:
        """Fetch every registered source and re-evaluate the verdict.

        Called only from the CSRF-protected refresh route, which is reachable
        only from an explicit user action.
        """
        started_at = datetime.now(UTC)
        try:
            status = self._run_check(started_at)
        except Exception as exc:
            # Broad on purpose. An unexpected failure must become a closed
            # gate, not an exception that some caller's except-block turns
            # into an apparent success.
            status = self._unavailable_status(
                (f"beklenmeyen hata: {type(exc).__name__}",)
            )

        with self._lock:
            previous = self._state.status
            self._state.status = _carry_last_success(status, previous)
        return self.status()

    # --- internals ---------------------------------------------------------

    def _run_check(self, started_at: datetime) -> TechnocoreStatus:
        records: list[SourceRecord] = []
        documents: dict[SourceId, dict[str, Any]] = {}
        failures: list[str] = []

        for source in SOURCES:
            record, parsed = self._read_source(source)
            records.append(record)
            if parsed is not None:
                documents[source.id] = parsed
            if record.outcome != SnapshotOutcome.OK and source.required_for_verdict:
                failures.append(f"{source.id.value}: {record.detail}")

        result = unavailable(tuple(failures)) if failures else project(documents)

        completed_at = datetime.now(UTC)
        check_id = self._persist(
            started_at=started_at,
            completed_at=completed_at,
            result=result,
            records=tuple(records),
        )

        return TechnocoreStatus(
            state=result.state,
            checked_at=completed_at,
            last_attempt_at=completed_at,
            last_success_at=completed_at if result.state is DriftState.CURRENT else None,
            reasons=result.reasons,
            sources=tuple(_to_status(record) for record in records),
            projection=result,
            check_id=check_id,
        )

    def _read_source(
        self, source: OfficialSource
    ) -> tuple[SourceRecord, dict[str, Any] | None]:
        """Fetch and, for JSON sources, parse. Never raises."""
        try:
            fetched = self._client.fetch(source)
        except TechnocoreError as exc:
            return (
                SourceRecord(
                    source=source,
                    fetched_at=datetime.now(UTC),
                    outcome=SnapshotOutcome.FETCH_ERROR,
                    detail=safe_display(str(exc)),
                ),
                None,
            )

        record = _ok_record(source, fetched)
        if source.media != "application/json":
            return record, None

        try:
            parsed = loads_strict(fetched.body, max_bytes=source.max_bytes)
        except StrictJsonError as exc:
            return (
                SourceRecord(
                    source=record.source,
                    fetched_at=record.fetched_at,
                    outcome=SnapshotOutcome.PARSE_ERROR,
                    http_status=record.http_status,
                    content_type=record.content_type,
                    etag=record.etag,
                    last_modified=record.last_modified,
                    content_sha256=record.content_sha256,
                    byte_count=record.byte_count,
                    body=record.body,
                    detail=safe_display(str(exc)),
                ),
                None,
            )

        return record, parsed

    def _persist(
        self,
        *,
        started_at: datetime,
        completed_at: datetime,
        result: ProjectionResult,
        records: tuple[SourceRecord, ...],
    ) -> str:
        """Write the evidence. Without an engine, the check still works."""
        if self._engine is None:
            return ""
        return record_check(
            self._engine,
            started_at=started_at,
            completed_at=completed_at,
            state=result.state.value,
            reasons=result.reasons,
            critical_count=len(result.critical_mismatches),
            warning_count=len(result.warnings),
            records=records,
        )

    def _unavailable_status(self, reasons: tuple[str, ...]) -> TechnocoreStatus:
        now = datetime.now(UTC)
        return TechnocoreStatus(
            state=DriftState.UNAVAILABLE,
            checked_at=now,
            last_attempt_at=now,
            last_success_at=None,
            reasons=reasons,
            sources=(),
            projection=unavailable(reasons),
        )


def _ok_record(source: OfficialSource, fetched: FetchResult) -> SourceRecord:
    return SourceRecord(
        source=source,
        fetched_at=fetched.fetched_at,
        outcome=SnapshotOutcome.OK,
        http_status=fetched.status_code,
        content_type=fetched.content_type,
        etag=fetched.etag,
        last_modified=fetched.last_modified,
        content_sha256=fetched.sha256,
        byte_count=fetched.byte_count,
        body=fetched.body,
    )


def _to_status(record: SourceRecord) -> SourceStatus:
    return SourceStatus(
        source_id=record.source.id.value,
        url=record.source.url,
        authority=record.source.authority,
        outcome=record.outcome,
        http_status=record.http_status,
        content_type=record.content_type,
        etag=record.etag,
        last_modified=record.last_modified,
        short_hash=record.short_hash,
        byte_count=record.byte_count,
        detail=record.detail,
        rationale=record.source.rationale,
    )


def _carry_last_success(
    status: TechnocoreStatus, previous: TechnocoreStatus
) -> TechnocoreStatus:
    """Keep the timestamp of the last *successful* check for display.

    Only the timestamp is carried. The state, the reasons and
    ``manifest_current`` all come from the check that just ran, so a network
    failure can never be papered over by an older success - it is shown
    beside the failure, not instead of it.
    """
    if status.last_success_at is not None:
        return status
    return TechnocoreStatus(
        state=status.state,
        checked_at=status.checked_at,
        last_attempt_at=status.last_attempt_at,
        last_success_at=previous.last_success_at,
        reasons=status.reasons,
        sources=status.sources,
        projection=status.projection,
        check_id=status.check_id,
    )


__all__ = ["SourceStatus", "TechnocoreService", "TechnocoreStatus"]
