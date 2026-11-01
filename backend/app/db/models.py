import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "orbit_sources"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_orbit_sources_source_key"),
        Index("ix_orbit_sources_category_enabled", "category", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    collection_config: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    licensing_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=utc_now,
    )


class CollectionRun(Base):
    __tablename__ = "orbit_collection_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_orbit_collection_runs_status",
        ),
        CheckConstraint(
            "records_fetched >= 0 AND records_new >= 0 AND records_changed >= 0 "
            "AND records_unchanged >= 0 AND records_invalid >= 0",
            name="ck_orbit_collection_runs_nonnegative_counts",
        ),
        CheckConstraint(
            "quality_status IN ('healthy', 'degraded', 'failed', 'unknown')",
            name="ck_orbit_collection_runs_quality_status",
        ),
        Index("ix_orbit_collection_runs_source_started", "source_id", "started_at"),
        Index("ix_orbit_collection_runs_status_started", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orbit_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(String(300))
    quality_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default="unknown"
    )
    quality_details: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )


class CurrentRecord(Base):
    __tablename__ = "orbit_records"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "external_record_id", name="uq_orbit_records_source_external"
        ),
        Index("ix_orbit_records_source_category", "source_id", "category"),
        Index("ix_orbit_records_last_observed", "last_observed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orbit_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_record_id: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class RecordVersion(Base):
    __tablename__ = "orbit_record_versions"
    __table_args__ = (
        UniqueConstraint("record_id", "version_number", name="uq_orbit_record_versions_number"),
        Index("ix_orbit_record_versions_record_observed", "record_id", "observed_at"),
        Index("ix_orbit_record_versions_fingerprint", "fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orbit_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)


class InvalidRecord(Base):
    __tablename__ = "orbit_invalid_records"
    __table_args__ = (
        Index("ix_orbit_invalid_records_source_created", "source_id", "created_at"),
        Index("ix_orbit_invalid_records_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orbit_collection_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orbit_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_record_id: Mapped[str | None] = mapped_column(String(200))
    error_details: Mapped[list[dict[str, str]]] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AdminSession(Base):
    __tablename__ = "orbit_admin_sessions"
    __table_args__ = (
        Index("ix_orbit_admin_sessions_expires_at", "expires_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceSchedule(Base):
    __tablename__ = "orbit_source_schedules"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('fixed', 'adaptive', 'paused')",
            name="ck_orbit_source_schedules_mode",
        ),
        CheckConstraint(
            "base_interval_seconds BETWEEN 3600 AND 7776000",
            name="ck_orbit_source_schedules_base_interval",
        ),
        CheckConstraint(
            "minimum_interval_seconds BETWEEN 60 AND 7776000",
            name="ck_orbit_source_schedules_min_interval",
        ),
        CheckConstraint(
            "maximum_interval_seconds BETWEEN 3600 AND 31536000",
            name="ck_orbit_source_schedules_max_interval",
        ),
        CheckConstraint(
            "minimum_interval_seconds <= base_interval_seconds "
            "AND base_interval_seconds <= maximum_interval_seconds",
            name="ck_orbit_source_schedules_interval_order",
        ),
        CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="ck_orbit_source_schedules_priority",
        ),
        Index("ix_orbit_source_schedules_due", "enabled", "mode", "next_due_at"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orbit_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="adaptive", server_default="adaptive"
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    base_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    consecutive_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    health_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default="unknown"
    )
    health_reason: Mapped[str | None] = mapped_column(String(300))
    quality_ratio: Mapped[float | None] = mapped_column()
    last_decision: Mapped[str | None] = mapped_column(String(40))
    policy_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utc_now
    )


class AgentWorker(Base):
    __tablename__ = "orbit_agent_workers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('starting', 'idle', 'executing', 'stopping', 'unhealthy', 'offline')",
            name="ck_orbit_agent_workers_status",
        ),
        Index("ix_orbit_agent_workers_heartbeat", "last_heartbeat_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="starting", server_default="starting"
    )
    active_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    last_error: Mapped[str | None] = mapped_column(String(300))
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class AgentJob(Base):
    __tablename__ = "orbit_agent_jobs"
    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('manual', 'scheduled')",
            name="ck_orbit_agent_jobs_trigger",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'completed', 'failed', 'cancelled')",
            name="ck_orbit_agent_jobs_status",
        ),
        Index("ix_orbit_agent_jobs_claim", "status", "scheduled_at", "created_at"),
        Index("ix_orbit_agent_jobs_source_created", "source_id", "created_at"),
        Index(
            "uq_orbit_agent_jobs_active_source",
            "source_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'retry_wait')"),
            sqlite_where=text("status IN ('queued', 'running', 'retry_wait')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orbit_sources.id", ondelete="RESTRICT"), nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", server_default="queued"
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orbit_collection_runs.id", ondelete="SET NULL")
    )
    failure_category: Mapped[str | None] = mapped_column(String(40))
    error_summary: Mapped[str | None] = mapped_column(String(300))
    quality_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default="unknown"
    )


class AgentDecision(Base):
    __tablename__ = "orbit_agent_decisions"
    __table_args__ = (
        Index("ix_orbit_agent_decisions_created", "created_at"),
        Index("ix_orbit_agent_decisions_source_created", "source_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orbit_sources.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orbit_agent_jobs.id", ondelete="SET NULL")
    )
    decision_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(60), nullable=False)
    explanation: Mapped[str] = mapped_column(String(500), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="1", server_default="1"
    )
