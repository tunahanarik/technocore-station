"""Pydantic response models.

Every field that can ever leave this process is declared here. No model in
this module, or any module that follows it, may carry a field whose name
contains ``seed``, ``private``, ``secret`` or ``mnemonic`` (INV-01, SI-34).
The database path is likewise never returned (SI-36).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HealthResponse(StrictModel):
    """Public liveness probe. Deliberately carries no environment detail."""

    status: Literal["ok"] = "ok"
    service: Literal["station-api"] = "station-api"


class SessionBootstrapResponse(StrictModel):
    """Hands the SPA its per-session CSRF value.

    The client keeps this in memory only. It is never written to
    localStorage, sessionStorage or IndexedDB (SI-24).
    """

    csrf_token: str = Field(description="Send as the X-Station-CSRF header.")
    csrf_header: str = Field(description="Name of the header to send it in.")


class ServiceStatus(StrictModel):
    state: Literal["running"] = "running"
    stage: int = Field(description="Implemented roadmap stage.")
    mode: Literal["production", "development"]


class DatabaseStatus(StrictModel):
    state: Literal["ready", "unavailable"]
    journal_mode: str = Field(description="Expected to be wal.")
    foreign_keys: bool
    schema_revision: str


class SessionSecurityStatus(StrictModel):
    state: Literal["active"] = "active"
    cookie_http_only: bool
    cookie_same_site: Literal["strict"]
    # Loopback HTTP: the Secure flag is deliberately not set, because browsers
    # do not honour it consistently over plain HTTP. Reported so the UI can
    # state the real posture instead of implying a guarantee.
    cookie_secure: bool
    csrf_required: bool
    transport: Literal["loopback-http"] = "loopback-http"


class TechnocoreStatus(StrictModel):
    """Always disconnected in this stage. There is no network client yet."""

    state: Literal["not_connected"] = "not_connected"
    available_from_stage: int = 3
    detail: str


class AppStatusResponse(StrictModel):
    service: ServiceStatus
    database: DatabaseStatus
    session_security: SessionSecurityStatus
    technocore: TechnocoreStatus
