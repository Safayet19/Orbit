import csv
import io
import json
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.auth import get_admin_session
from backend.app.api.dependencies import get_session
from backend.app.api.schemas import PageMetadata
from backend.app.api.services.admin_reads import (
    get_record,
    list_history,
    list_records,
    list_versions,
)
from backend.app.db.models import AdminSession

router = APIRouter(
    prefix="/records",
    tags=["records"],
    dependencies=[Depends(get_admin_session)],
)
MAX_EXPORT_ROWS = 5000


def _record_filters(
    search: str | None,
    source_id: str | None,
    category: str | None,
    observed_after: datetime | None,
    observed_before: datetime | None,
) -> dict[str, object]:
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
    items, total = list_records(
        session,
        1,
        min(MAX_EXPORT_ROWS, 100),
        **filters,
    )
    if total > MAX_EXPORT_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Export is limited to {MAX_EXPORT_ROWS} records; narrow the filters.",
        )
    while len(items) < total:
        next_page, _ = list_records(
            session,
            len(items) // 100 + 1,
            100,
            **filters,
        )
        if not next_page:
            break
        items.extend(next_page)

    field_names = sorted(
        {
            key
            for record in items
            for key in record.data
        }
    )
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
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
            *field_names,
        ]
    )
    for record in items:
        values = [
            record.id,
            record.source_name,
            record.external_record_id,
            record.category,
            record.source_url,
            record.first_observed_at.isoformat(),
            record.last_observed_at.isoformat(),
        ]
        values.extend(record.data.get(field) for field in field_names)
        writer.writerow(_safe_csv_value(value) for value in values)

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
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
