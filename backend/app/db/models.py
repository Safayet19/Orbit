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
