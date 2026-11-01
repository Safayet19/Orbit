import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    CollectionRun,
    CurrentRecord,
    InvalidRecord,
    RecordVersion,
    Source,
)
from backend.app.pipeline.fingerprint import content_fingerprint

RecordOutcome = Literal["new", "changed", "unchanged"]


@dataclass(frozen=True)
class _PreparedObservation:
    record: BaseModel
    external_id: str
    observed_at: datetime
    source_url: str
    numeric_value: Decimal | None
    data: dict[str, Any]
    fingerprint: str


def get_enabled_source(session: Session, source_key: str) -> Source | None:
    return session.scalar(
        select(Source).where(Source.source_key == source_key, Source.enabled.is_(True))
    )


def start_run(session: Session, source_id: uuid.UUID) -> CollectionRun:
    run = CollectionRun(source_id=source_id, status="running")
    session.add(run)
    session.flush()
    return run


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _record_data(record: BaseModel) -> dict[str, Any]:
    values = record.model_dump(
        mode="python",
        exclude={"external_record_id", "source_url", "observed_at"},
    )
    return _json_value(values)


def _numeric_value(record: BaseModel) -> Decimal | None:
    value = getattr(record, "value", None)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def upsert_observation(
    session: Session,
    source: Source,
    record: BaseModel,
    existing_records: dict[str, CurrentRecord] | None = None,
    *,
    prepared: _PreparedObservation | None = None,
    latest_version_numbers: dict[uuid.UUID, int] | None = None,
) -> RecordOutcome:
    if prepared is None:
        data = _record_data(record)
        prepared = _PreparedObservation(
            record=record,
            external_id=str(getattr(record, "external_record_id")),
            observed_at=getattr(record, "observed_at"),
            source_url=str(getattr(record, "source_url")),
            numeric_value=_numeric_value(record),
            data=data,
            fingerprint=content_fingerprint(data),
        )
    external_id = prepared.external_id
    observed_at = prepared.observed_at
    source_url = prepared.source_url
    numeric_value = prepared.numeric_value
    data = prepared.data
    fingerprint = prepared.fingerprint
    query = select(CurrentRecord).where(
        CurrentRecord.source_id == source.id,
        CurrentRecord.external_record_id == external_id,
    )
    current = (
        existing_records.get(external_id)
        if existing_records is not None
        else session.scalar(query.with_for_update())
    )
    outcome: RecordOutcome

    if current is None:
        candidate = CurrentRecord(
            source_id=source.id,
            external_record_id=external_id,
            category=source.category,
            data=data,
            numeric_value=numeric_value,
            source_url=source_url,
            first_observed_at=observed_at,
            last_observed_at=observed_at,
            fingerprint=fingerprint,
            status="active",
        )
        try:
            with session.begin_nested():
                session.add(candidate)
                session.flush()
            current = candidate
            outcome = "new"
        except IntegrityError:
            current = session.scalar(query.with_for_update())
            if current is None:
                raise
            outcome = "changed" if current.fingerprint != fingerprint else "unchanged"
        if existing_records is not None:
            existing_records[external_id] = current
    else:
        outcome = "changed" if current.fingerprint != fingerprint else "unchanged"

    if outcome == "unchanged":
        current.last_observed_at = observed_at
    elif current.fingerprint != fingerprint:
        current.data = data
        current.numeric_value = numeric_value
        current.source_url = source_url
        current.last_observed_at = observed_at
        current.fingerprint = fingerprint
        current.status = "active"
        outcome = "changed"

    if outcome != "unchanged":
        if outcome == "new":
            version_number = 1
            if latest_version_numbers is not None:
                latest_version_numbers[current.id] = version_number
        else:
            if latest_version_numbers is not None and current.id in latest_version_numbers:
                latest_version = latest_version_numbers[current.id]
            else:
                latest_version = session.scalar(
                    select(func.max(RecordVersion.version_number)).where(
                        RecordVersion.record_id == current.id
                    )
                )
            version_number = (latest_version or 0) + 1
            if latest_version_numbers is not None:
                latest_version_numbers[current.id] = version_number
        session.add(
            RecordVersion(
                record_id=current.id,
                version_number=version_number,
                data=data,
                numeric_value=numeric_value,
                fingerprint=fingerprint,
                observed_at=observed_at,
                provenance={
                    "source_id": str(source.id),
                    "source_key": source.source_key,
                    "source_url": source_url,
                    "external_record_id": external_id,
                },
            )
        )
    return outcome


def persist_success(
    session: Session,
    run_id: uuid.UUID,
    source: Source,
    records: Sequence[BaseModel],
    invalid_records: Sequence[tuple[str | None, list[dict[str, str]]]],
    records_fetched: int,
    completed_at: datetime,
    quality_status: str = "healthy",
    quality_details: dict[str, Any] | None = None,
) -> dict[str, int]:
    counts = {"new": 0, "changed": 0, "unchanged": 0}
    prepared_records = []
    for record in records:
        data = _record_data(record)
        prepared_records.append(
            _PreparedObservation(
                record=record,
                external_id=str(getattr(record, "external_record_id")),
                observed_at=getattr(record, "observed_at"),
                source_url=str(getattr(record, "source_url")),
                numeric_value=_numeric_value(record),
                data=data,
                fingerprint=content_fingerprint(data),
            )
        )
    external_ids = {item.external_id for item in prepared_records}
    existing_records: dict[str, CurrentRecord] = {}
    if external_ids:
        current_rows = session.scalars(
            select(CurrentRecord)
            .where(
                CurrentRecord.source_id == source.id,
                CurrentRecord.external_record_id.in_(external_ids),
            )
            .with_for_update()
        ).all()
        existing_records = {
            current.external_record_id: current for current in current_rows
        }

    changed_record_ids = {
        current.id
        for item in prepared_records
        if (current := existing_records.get(item.external_id)) is not None
        and current.fingerprint != item.fingerprint
    }
    latest_version_numbers = (
        {
            record_id: int(version_number)
            for record_id, version_number in session.execute(
                select(
                    RecordVersion.record_id,
                    func.max(RecordVersion.version_number),
                )
                .where(RecordVersion.record_id.in_(changed_record_ids))
                .group_by(RecordVersion.record_id)
            ).all()
        }
        if changed_record_ids
        else {}
    )
    for record, prepared in zip(records, prepared_records, strict=True):
        outcome = upsert_observation(
            session,
            source,
            record,
            existing_records=existing_records,
            prepared=prepared,
            latest_version_numbers=latest_version_numbers,
        )
        counts[outcome] += 1

    for external_id, error_details in invalid_records:
        session.add(
            InvalidRecord(
                run_id=run_id,
                source_id=source.id,
                external_record_id=external_id,
                error_details=error_details,
            )
        )

    run = session.get(CollectionRun, run_id)
    if run is None:
        raise RuntimeError("Collection run disappeared before finalization.")
    run.status = "completed"
    run.completed_at = completed_at
    run.records_fetched = records_fetched
    run.records_new = counts["new"]
    run.records_changed = counts["changed"]
    run.records_unchanged = counts["unchanged"]
    run.records_invalid = len(invalid_records)
    run.quality_status = quality_status
    run.quality_details = quality_details or {}
    return counts


def mark_run_failed(
    session: Session,
    run_id: uuid.UUID,
    completed_at: datetime,
    error_summary: str,
) -> None:
    run = session.get(CollectionRun, run_id)
    if run is None:
        raise RuntimeError("Collection run disappeared before failure handling.")
    run.status = "failed"
    run.completed_at = completed_at
    run.error_summary = error_summary[:300]
    run.quality_status = "failed"
