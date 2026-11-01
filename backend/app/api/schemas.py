from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=120)


class SourceEnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class AgentScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["fixed", "adaptive", "paused"] | None = None
    enabled: bool | None = None
    base_interval_seconds: int | None = Field(default=None, ge=3600, le=7_776_000)
    minimum_interval_seconds: int | None = Field(default=None, ge=60, le=7_776_000)
    maximum_interval_seconds: int | None = Field(default=None, ge=3600, le=31_536_000)
    priority: int | None = Field(default=None, ge=1, le=10)


class AuthenticatedUser(BaseModel):
    username: str
    csrf_token: str


class PageMetadata(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class SourceSummary(BaseModel):
    id: str
    name: str
    source_key: str
    category: str
    source_type: str
    official_url: str
    enabled: bool
    last_collection_at: datetime | None
    last_result: str | None
    latest_record_count: int
    latest_error: str | None
    supported: bool


class RunSummary(BaseModel):
    id: str
    source_id: str
    source_name: str
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    records_fetched: int
    records_new: int
    records_changed: int
    records_unchanged: int
    records_invalid: int
    error_summary: str | None
    quality_status: str = "unknown"


class RecordSummary(BaseModel):
    id: str
    source_id: str
    source_name: str
    external_record_id: str
    category: str
    data: dict[str, Any]
    source_url: str
    first_observed_at: datetime
    last_observed_at: datetime
    status: str
    version_number: int


class RecordVersionResponse(BaseModel):
    id: str
    version_number: int
    data: dict[str, Any]
    fingerprint: str
    observed_at: datetime
    provenance: dict[str, Any]
    previous_data: dict[str, Any] | None


class InvalidRecordSummary(BaseModel):
    id: str
    source_name: str
    source_key: str
    run_id: str
    external_record_id: str | None
    error_details: list[dict[str, str]]
    created_at: datetime
    severity: Literal["warning", "error"]


class OverviewResponse(BaseModel):
    refreshed_at: datetime
    total_records: int
    registered_sources: int
    successful_runs: int
    failed_runs: int
    running_runs: int
    enabled_sources: int
    stale_sources: int | None
    chart: list[dict[str, Any]]
    recent_runs: list[RunSummary]
    recent_changes: list[dict[str, Any]]
