from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.orm import Session

from backend.app.api.auth import get_admin_session
from backend.app.api.dependencies import get_session
from backend.app.api.schemas import PageMetadata
from backend.app.db.models import (
    AdminSession,
    CollectionRun,
    CurrentRecord,
    InvalidRecord,
    Source,
)

router = APIRouter(
    prefix="/quality",
    tags=["quality"],
    dependencies=[Depends(get_admin_session)],
)


@router.get("")
def quality_summary(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    valid_records = int(session.scalar(select(func.count(CurrentRecord.id))) or 0)
    invalid_records = int(session.scalar(select(func.count(InvalidRecord.id))) or 0)
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
    enabled_sources, stale_sources = map(int, source_counts)
    run_counts = session.execute(
        select(
            func.coalesce(
                func.sum(case((CollectionRun.status == "failed", 1), else_=0)),
                0,
            ),
            func.count(
                func.distinct(
                    case(
                        (
                            (CollectionRun.status == "failed")
                            & (CollectionRun.started_at >= now - timedelta(days=7)),
                            CollectionRun.source_id,
                        ),
                        else_=None,
                    )
                )
            ),
        )
    ).one()
    failed_runs, recent_failed_sources = map(int, run_counts)
    status_value = (
        "unknown"
        if not enabled_sources
        else "error"
        if failed_runs
        else "warning"
        if invalid_records or stale_sources
        else "healthy"
    )
    return {
        "status": status_value,
        "valid_records": valid_records,
        "invalid_records": invalid_records,
        "failed_runs": failed_runs,
        "sources_with_recent_errors": recent_failed_sources,
        "stale_sources": stale_sources,
        "potential_duplicates": None,
        "potential_duplicates_measurable": False,
    }


@router.get("/issues")
def quality_issues(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, object]:
    failed_issues = (
        select(
            CollectionRun.id.label("id"),
            Source.name.label("source_name"),
            Source.source_key.label("source_key"),
            CollectionRun.id.label("run_id"),
            literal(None, type_=InvalidRecord.external_record_id.type).label(
                "external_record_id"
            ),
            func.jsonb_build_array(
                func.jsonb_build_object(
                    "field",
                    "",
                    "type",
                    func.coalesce(CollectionRun.error_summary, "Collection failure"),
                )
            ).label("error_details"),
            func.coalesce(CollectionRun.completed_at, CollectionRun.started_at).label(
                "created_at"
            ),
            literal("error").label("severity"),
        )
        .join(Source, CollectionRun.source_id == Source.id)
        .where(CollectionRun.status == "failed")
    )
    invalid_issues = (
        select(
            InvalidRecord.id.label("id"),
            Source.name.label("source_name"),
            Source.source_key.label("source_key"),
            InvalidRecord.run_id.label("run_id"),
            InvalidRecord.external_record_id.label("external_record_id"),
            InvalidRecord.error_details.label("error_details"),
            InvalidRecord.created_at.label("created_at"),
            literal("warning").label("severity"),
        )
        .join(Source, InvalidRecord.source_id == Source.id)
    )
    issue_query = union_all(failed_issues, invalid_issues).subquery()
    total = int(session.scalar(select(func.count()).select_from(issue_query)) or 0)
    rows = session.execute(
        select(issue_query)
        .order_by(issue_query.c.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).mappings().all()
    items = [
        {
            "id": str(row["id"]),
            "source_name": row["source_name"],
            "source_key": row["source_key"],
            "run_id": str(row["run_id"]),
            "external_record_id": row["external_record_id"],
            "error_details": row["error_details"],
            "created_at": row["created_at"],
            "severity": row["severity"],
        }
        for row in rows
    ]
    return {
        "items": items,
        "pagination": PageMetadata(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    }
