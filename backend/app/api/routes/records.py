import csv
import io
import json
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Literal, TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.auth import get_admin_session
from backend.app.api.dependencies import get_session
from backend.app.api.schemas import PageMetadata
from backend.app.api.services.admin_reads import (
    get_record,
    list_history,
    list_records,
    list_versions,
    record_filter_expressions,
)
from backend.app.db.models import AdminSession, CurrentRecord, Source

router = APIRouter(
    prefix="/records",
    tags=["records"],
    dependencies=[Depends(get_admin_session)],
)
MAX_EXPORT_ROWS = 5000
EXPORT_BATCH_SIZE = 250
EXPORT_CHUNK_ROWS = 64


class RecordFilters(TypedDict):
    search: str | None
    source_key: str | None
    category: str | None
    observed_after: datetime | None
    observed_before: datetime | None


def _record_filters(
    search: str | None,
    source_id: str | None,
    category: str | None,
    observed_after: datetime | None,
    observed_before: datetime | None,
) -> RecordFilters:
    if observed_after and observed_before and observed_after > observed_before:
        raise HTTPException(
            status_code=422,
            detail="observed_after must not be later than observed_before.",
        )
    return {
        "search": search,
        "source_key": source_id,
        "category": category,
        "observed_after": observed_after,
        "observed_before": observed_before,
    }


@router.get("")
def records(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=120)] = None,
    source_id: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[str | None, Query(max_length=120)] = None,
    observed_after: datetime | None = None,
    observed_before: datetime | None = None,
    sort_by: Literal[
        "last_observed_at",
        "first_observed_at",
        "category",
        "external_record_id",
    ] = "last_observed_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> dict[str, object]:
    filters = _record_filters(
        search, source_id, category, observed_after, observed_before
    )
    items, total = list_records(
        session,
        page,
        page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        **filters,
    )
    return {
        "items": [item.model_dump() for item in items],
        "pagination": PageMetadata(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    }


@router.get("/export.csv")
def export_records(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    search: Annotated[str | None, Query(max_length=120)] = None,
    source_id: Annotated[str | None, Query(max_length=120)] = None,
    category: Annotated[str | None, Query(max_length=120)] = None,
    observed_after: datetime | None = None,
    observed_before: datetime | None = None,
) -> StreamingResponse:
    filters = _record_filters(
        search, source_id, category, observed_after, observed_before
    )
    conditions = record_filter_expressions(**filters)
    record_ids = session.scalars(
        select(CurrentRecord.id)
        .join(Source, CurrentRecord.source_id == Source.id)
        .where(*conditions)
        .order_by(CurrentRecord.last_observed_at.desc(), CurrentRecord.id)
        .limit(MAX_EXPORT_ROWS + 1)
    ).all()
    if len(record_ids) > MAX_EXPORT_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Export is limited to {MAX_EXPORT_ROWS} records; narrow the filters.",
        )

    field_names: set[str] = set()
    prefetched_records: list[tuple[CurrentRecord, str]] | None = None
    if len(record_ids) <= EXPORT_BATCH_SIZE and record_ids:
        rows = session.execute(
            select(CurrentRecord, Source.name)
            .join(Source, CurrentRecord.source_id == Source.id)
            .where(CurrentRecord.id.in_(record_ids))
        ).all()
        records_by_id = {
            record.id: (record, source_name)
            for record, source_name in rows
        }
        prefetched_records = [records_by_id[record_id] for record_id in record_ids]
        for record, _source_name in prefetched_records:
            field_names.update(record.data)
    else:
        for offset in range(0, len(record_ids), EXPORT_BATCH_SIZE):
            batch_ids = record_ids[offset : offset + EXPORT_BATCH_SIZE]
            data_rows = session.scalars(
                select(CurrentRecord.data).where(CurrentRecord.id.in_(batch_ids))
            ).all()
            for data in data_rows:
                field_names.update(data)
    ordered_fields = sorted(field_names)
    export_sessions = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    session.close()

    def generate_csv() -> Iterator[str]:
        with export_sessions() as export_session:
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            pending_rows = 0
            writer.writerow(
                _safe_csv_value(value)
                for value in [
                    "record_id",
                    "source_name",
                    "external_record_id",
                    "category",
                    "source_url",
                    "first_observed_at",
                    "last_observed_at",
                    *ordered_fields,
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

            for offset in range(0, len(record_ids), EXPORT_BATCH_SIZE):
                batch_ids = record_ids[offset : offset + EXPORT_BATCH_SIZE]
                if prefetched_records is not None:
                    rows = prefetched_records[offset : offset + len(batch_ids)]
                    batch_records = dict(
                        zip(batch_ids, rows, strict=True)
                    )
                else:
                    rows = export_session.execute(
                        select(CurrentRecord, Source.name)
                        .join(Source, CurrentRecord.source_id == Source.id)
                        .where(CurrentRecord.id.in_(batch_ids))
                    ).all()
                    batch_records = {
                        record.id: (record, source_name)
                        for record, source_name in rows
                    }
                for record_id in batch_ids:
                    record, source_name = batch_records[record_id]
                    values = [
                        record.id,
                        source_name,
                        record.external_record_id,
                        record.category,
                        record.source_url,
                        record.first_observed_at.isoformat(),
                        record.last_observed_at.isoformat(),
                    ]
                    values.extend(
                        record.data.get(field) for field in ordered_fields
                    )
                    writer.writerow(_safe_csv_value(value) for value in values)
                    pending_rows += 1
                    if pending_rows == EXPORT_CHUNK_ROWS:
                        yield buffer.getvalue()
                        buffer.seek(0)
                        buffer.truncate(0)
                        pending_rows = 0
            if buffer.tell():
                yield buffer.getvalue()

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="orbit-records.csv"'},
    )


def _safe_csv_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = "" if value is None else str(value)
    if text.lstrip(" ").startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


@router.get("/{record_id}/versions")
def record_versions(
    record_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    if get_record(session, record_id) is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    versions = list_versions(session, record_id)
    return {"items": [version.model_dump() for version in versions]}


@router.get("/{record_id}")
def record_detail(
    record_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    record = get_record(session, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    return record.model_dump()


history_router = APIRouter(
    prefix="/history",
    tags=["history"],
    dependencies=[Depends(get_admin_session)],
)


@history_router.get("")
def history(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    source_id: str | None = None,
) -> dict[str, object]:
    items, total = list_history(session, page, page_size, source_id)
    return {
        "items": items,
        "pagination": PageMetadata(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    }
