import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import String, cast, case, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from backend.app.api.schemas import (
    InvalidRecordSummary,
    OverviewResponse,
    RecordSummary,
    RecordVersionResponse,
    RunSummary,
    SourceSummary,
)
from backend.app.collectors.worldbank import INDICATOR_SPECS
from backend.app.db.models import (
    CollectionRun,
    CurrentRecord,
    InvalidRecord,
    RecordVersion,
    Source,
)

SUPPORTED_SOURCE_IDS = frozenset(spec.source_id for spec in INDICATOR_SPECS)


def _run_summary(run: CollectionRun, source_name: str, now: datetime) -> RunSummary:
    end = run.completed_at or now
    normalized_end = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
    normalized_start = (
        run.started_at.replace(tzinfo=timezone.utc)
        if run.started_at.tzinfo is None
        else run.started_at
    )
    duration = max(0.0, (normalized_end - normalized_start).total_seconds())
    return RunSummary(
        id=str(run.id),
        source_id=str(run.source_id),
        source_name=source_name,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=duration if run.completed_at else None,
        records_fetched=run.records_fetched,
        records_new=run.records_new,
        records_changed=run.records_changed,
        records_unchanged=run.records_unchanged,
        records_invalid=run.records_invalid,
        error_summary=run.error_summary,
        quality_status=run.quality_status,
    )


def list_runs(
    session: Session,
    page: int = 1,
    page_size: int = 20,
    source_key: str | None = None,
    status: str | None = None,
) -> tuple[list[RunSummary], int]:
    query = select(CollectionRun, Source.name).join(
        Source, CollectionRun.source_id == Source.id
    )
    count_query = select(func.count(CollectionRun.id)).join(
        Source, CollectionRun.source_id == Source.id
    )
    if source_key:
        query = query.where(Source.source_key == source_key)
        count_query = count_query.where(Source.source_key == source_key)
    if status:
        query = query.where(CollectionRun.status == status)
        count_query = count_query.where(CollectionRun.status == status)

    total = int(session.scalar(count_query) or 0)
    rows = session.execute(
        query.order_by(CollectionRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    now = datetime.now(timezone.utc)
    return [_run_summary(run, name, now) for run, name in rows], total


def get_run(session: Session, run_id: uuid.UUID) -> RunSummary | None:
    row = session.execute(
        select(CollectionRun, Source.name)
        .join(Source, CollectionRun.source_id == Source.id)
        .where(CollectionRun.id == run_id)
    ).first()
    return _run_summary(row[0], row[1], datetime.now(timezone.utc)) if row else None


def list_sources(session: Session) -> list[SourceSummary]:
    latest_run_id = (
        select(CollectionRun.id)
        .where(CollectionRun.source_id == Source.id)
        .order_by(CollectionRun.started_at.desc())
        .limit(1)
        .correlate(Source)
        .scalar_subquery()
    )
    record_counts = (
        select(CurrentRecord.source_id, func.count(CurrentRecord.id).label("record_count"))
        .group_by(CurrentRecord.source_id)
        .subquery()
    )
    latest_run_rows = session.execute(
        select(
            Source,
            CollectionRun,
            func.coalesce(record_counts.c.record_count, 0),
        )
        .outerjoin(CollectionRun, CollectionRun.id == latest_run_id)
        .outerjoin(record_counts, record_counts.c.source_id == Source.id)
        .order_by(Source.name)
    ).all()
    return [
        SourceSummary(
            id=str(source.id),
            name=source.name,
            source_key=source.source_key,
            category=source.category,
            source_type=source.source_type,
            official_url=source.official_url,
            enabled=source.enabled,
            last_collection_at=run.completed_at or run.started_at if run else None,
            last_result=run.status if run else None,
            latest_record_count=int(record_count),
            latest_error=run.error_summary if run else None,
            supported=source.source_key in SUPPORTED_SOURCE_IDS,
        )
        for source, run, record_count in latest_run_rows
    ]


def get_source_detail(session: Session, source_key: str) -> dict[str, Any] | None:
    source = session.scalar(select(Source).where(Source.source_key == source_key))
    if source is None:
        return None
    runs, total = list_runs(
        session,
        page=1,
        page_size=10,
        source_key=source_key,
    )
    latest = runs[0] if runs else None
    records_count = session.scalar(
        select(func.count(CurrentRecord.id)).where(CurrentRecord.source_id == source.id)
    )
    return {
        "id": str(source.id),
        "name": source.name,
        "source_key": source.source_key,
        "source_type": source.source_type,
        "official_url": source.official_url,
        "category": source.category,
        "enabled": source.enabled,
        "supported": source.source_key in SUPPORTED_SOURCE_IDS,
        "collection_config": source.collection_config,
        "licensing_metadata": source.licensing_metadata,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
        "latest_record_count": int(records_count or 0),
        "latest_result": latest.model_dump() if latest else None,
        "recent_runs": [run.model_dump() for run in runs],
        "recent_runs_total": total,
    }


def get_overview(session: Session, period_days: int) -> OverviewResponse:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=period_days)
    total_records = int(session.scalar(select(func.count(CurrentRecord.id))) or 0)
    stale_before = now - timedelta(days=7)
    recent_completed_run = (
        select(CollectionRun.id)
        .where(
            CollectionRun.source_id == Source.id,
            CollectionRun.status == "completed",
            CollectionRun.completed_at >= stale_before,
        )
        .exists()
    )
    source_counts = session.execute(
        select(
            func.count(Source.id),
            func.coalesce(
                func.sum(case((Source.enabled.is_(True), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Source.enabled.is_(True) & ~recent_completed_run,
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
    ).one()
    registered_sources, enabled_sources, stale_sources = map(int, source_counts)
    run_counts = session.execute(
        select(
            func.coalesce(
                func.sum(case((CollectionRun.status == "completed", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((CollectionRun.status == "failed", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((CollectionRun.status == "running", 1), else_=0)),
                0,
            ),
        )
    ).one()
    successful_runs, failed_runs, running_runs = map(int, run_counts)

    day_expression = (
        func.date_trunc("day", CollectionRun.started_at)
        if session.get_bind().dialect.name == "postgresql"
        else func.date(CollectionRun.started_at)
    )
    trend_rows = session.execute(
        select(
            day_expression.label("day"),
            func.coalesce(func.sum(CollectionRun.records_new), 0),
            func.coalesce(func.sum(CollectionRun.records_changed), 0),
            func.sum(case((CollectionRun.status == "failed", 1), else_=0)),
        )
        .where(CollectionRun.started_at >= since)
        .group_by(day_expression)
        .order_by(day_expression)
    ).all()
    chart = [
        {
            "date": day.isoformat() if isinstance(day, datetime) else str(day),
            "new_records": int(new_records),
            "changed_records": int(changed_records),
            "failed_runs": int(failures),
        }
        for day, new_records, changed_records, failures in trend_rows
    ]

    recent_rows = session.execute(
        select(CollectionRun, Source.name)
        .join(Source, CollectionRun.source_id == Source.id)
        .order_by(CollectionRun.started_at.desc())
        .limit(8)
    ).all()
    recent_runs = [_run_summary(run, name, now) for run, name in recent_rows]

    previous_version = aliased(RecordVersion)
    recent_version_rows = session.execute(
        select(RecordVersion, CurrentRecord, Source.name, previous_version.data)
        .join(CurrentRecord, RecordVersion.record_id == CurrentRecord.id)
        .join(Source, CurrentRecord.source_id == Source.id)
        .outerjoin(
            previous_version,
            (previous_version.record_id == RecordVersion.record_id)
            & (previous_version.version_number == RecordVersion.version_number - 1),
        )
        .where(RecordVersion.version_number > 1)
        .order_by(RecordVersion.observed_at.desc())
        .limit(8)
    ).all()
    recent_changes: list[dict[str, Any]] = []
    for version, record, source_name, previous_data in recent_version_rows:
        recent_changes.append(
            {
                "version_id": str(version.id),
                "record_id": str(record.id),
                "external_record_id": record.external_record_id,
                "source_name": source_name,
                "version_number": version.version_number,
                "observed_at": version.observed_at,
                "previous_data": previous_data or {},
                "data": version.data,
            }
        )

    return OverviewResponse(
        refreshed_at=now,
        total_records=total_records,
        registered_sources=registered_sources,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        running_runs=running_runs,
        enabled_sources=enabled_sources,
        stale_sources=stale_sources,
        chart=chart,
        recent_runs=recent_runs,
        recent_changes=recent_changes,
    )


def record_filter_expressions(
    search: str | None = None,
    source_key: str | None = None,
    category: str | None = None,
    observed_after: datetime | None = None,
    observed_before: datetime | None = None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if search:
        term = f"%{search.strip()[:120]}%"
        filters.append(
            or_(
                CurrentRecord.external_record_id.ilike(term),
                CurrentRecord.category.ilike(term),
                cast(CurrentRecord.data, String).ilike(term),
                Source.name.ilike(term),
            )
        )
    if source_key:
        filters.append(Source.source_key == source_key)
    if category:
        filters.append(CurrentRecord.category == category)
    if observed_after:
        filters.append(CurrentRecord.last_observed_at >= observed_after)
    if observed_before:
        filters.append(CurrentRecord.last_observed_at <= observed_before)
    return filters


def list_records(
    session: Session,
    page: int,
    page_size: int,
    search: str | None = None,
    source_key: str | None = None,
    category: str | None = None,
    observed_after: datetime | None = None,
    observed_before: datetime | None = None,
    sort_by: str = "last_observed_at",
    sort_order: str = "desc",
) -> tuple[list[RecordSummary], int]:
    allowed_sort = {
        "last_observed_at": CurrentRecord.last_observed_at,
        "first_observed_at": CurrentRecord.first_observed_at,
        "category": CurrentRecord.category,
        "external_record_id": CurrentRecord.external_record_id,
    }
    count_query = select(func.count(CurrentRecord.id)).join(
        Source, CurrentRecord.source_id == Source.id
    )
    filters = record_filter_expressions(
        search,
        source_key,
        category,
        observed_after,
        observed_before,
    )
    count_query = count_query.where(*filters)

    total = int(session.scalar(count_query) or 0)
    column = allowed_sort[sort_by]
    sort_column = column.desc() if sort_order == "desc" else column.asc()
    latest_version_number = (
        select(func.max(RecordVersion.version_number))
        .where(RecordVersion.record_id == CurrentRecord.id)
        .correlate(CurrentRecord)
        .scalar_subquery()
    )
    rows = session.execute(
        select(CurrentRecord, Source.name, latest_version_number)
        .join(Source, CurrentRecord.source_id == Source.id)
        .where(*filters)
        .order_by(sort_column, CurrentRecord.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    results = []
    for record, source_name, latest_version in rows:
        results.append(
            RecordSummary(
                id=str(record.id),
                source_id=str(record.source_id),
                source_name=source_name,
                external_record_id=record.external_record_id,
                category=record.category,
                data=record.data,
                source_url=record.source_url,
                first_observed_at=record.first_observed_at,
                last_observed_at=record.last_observed_at,
                status=record.status,
                version_number=int(latest_version or 0),
            )
        )
    return results, total


def get_record(session: Session, record_id: uuid.UUID) -> RecordSummary | None:
    latest_version_number = (
        select(func.max(RecordVersion.version_number))
        .where(RecordVersion.record_id == CurrentRecord.id)
        .correlate(CurrentRecord)
        .scalar_subquery()
    )
    row = session.execute(
        select(CurrentRecord, Source.name, latest_version_number)
        .join(Source, CurrentRecord.source_id == Source.id)
        .where(CurrentRecord.id == record_id)
    ).first()
    if row is None:
        return None
    record, source_name, latest_version = row
    return RecordSummary(
        id=str(record.id),
        source_id=str(record.source_id),
        source_name=source_name,
        external_record_id=record.external_record_id,
        category=record.category,
        data=record.data,
        source_url=record.source_url,
        first_observed_at=record.first_observed_at,
        last_observed_at=record.last_observed_at,
        status=record.status,
        version_number=int(latest_version or 0),
    )


def list_versions(
    session: Session,
    record_id: uuid.UUID,
) -> list[RecordVersionResponse]:
    versions = session.scalars(
        select(RecordVersion)
        .where(RecordVersion.record_id == record_id)
        .order_by(RecordVersion.version_number.desc())
        .limit(100)
    ).all()
    previous_by_number: dict[int, dict[str, Any] | None] = {}
    version_numbers = [version.version_number for version in versions]
    if version_numbers:
        previous_versions = session.scalars(
            select(RecordVersion).where(
                RecordVersion.record_id == record_id,
                RecordVersion.version_number.in_(
                    [number - 1 for number in version_numbers if number > 1]
                ),
            )
        ).all()
        previous_by_number = {
            version.version_number + 1: version.data for version in previous_versions
        }
    return [
        RecordVersionResponse(
            id=str(version.id),
            version_number=version.version_number,
            data=version.data,
            fingerprint=version.fingerprint,
            observed_at=version.observed_at,
            provenance=version.provenance,
            previous_data=previous_by_number.get(version.version_number),
        )
        for version in versions
    ]


def list_history(
    session: Session,
    page: int,
    page_size: int,
    source_key: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    query = (
        select(RecordVersion, CurrentRecord, Source.name, Source.source_key)
        .join(CurrentRecord, RecordVersion.record_id == CurrentRecord.id)
        .join(Source, CurrentRecord.source_id == Source.id)
        .where(RecordVersion.version_number > 1)
    )
    count_query = (
        select(func.count(RecordVersion.id))
        .join(CurrentRecord, RecordVersion.record_id == CurrentRecord.id)
        .join(Source, CurrentRecord.source_id == Source.id)
        .where(RecordVersion.version_number > 1)
    )
    if source_key:
        query = query.where(Source.source_key == source_key)
        count_query = count_query.where(Source.source_key == source_key)
    total = int(session.scalar(count_query) or 0)
    previous_version = aliased(RecordVersion)
    rows = session.execute(
        query.add_columns(previous_version.data)
        .outerjoin(
            previous_version,
            (previous_version.record_id == RecordVersion.record_id)
            & (
                previous_version.version_number
                == RecordVersion.version_number - 1
            ),
        )
        .order_by(RecordVersion.observed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    result: list[dict[str, Any]] = []
    for version, record, source_name, source_key_value, previous in rows:
        result.append(
            {
                "version_id": str(version.id),
                "record_id": str(record.id),
                "external_record_id": record.external_record_id,
                "source_name": source_name,
                "source_key": source_key_value,
                "observed_at": version.observed_at,
                "version_number": version.version_number,
                "previous_data": previous or {},
                "data": version.data,
            }
        )
    return result, total


def list_invalid_records(
    session: Session,
    page: int,
    page_size: int,
) -> tuple[list[InvalidRecordSummary], int]:
    total = int(session.scalar(select(func.count(InvalidRecord.id))) or 0)
    rows = session.execute(
        select(InvalidRecord, Source.name, Source.source_key)
        .join(Source, InvalidRecord.source_id == Source.id)
        .order_by(InvalidRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [
        InvalidRecordSummary(
            id=str(invalid.id),
            source_name=name,
            source_key=source_key,
            run_id=str(invalid.run_id),
            external_record_id=invalid.external_record_id,
            error_details=invalid.error_details,
            created_at=invalid.created_at,
            severity="warning",
        )
        for invalid, name, source_key in rows
    ], total
