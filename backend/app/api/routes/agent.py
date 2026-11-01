from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.auth import get_admin_session, require_csrf
from backend.app.api.dependencies import get_session
from backend.app.api.schemas import AgentScheduleUpdate, PageMetadata
from backend.app.api.services.agent_reads import (
    get_agent_source_health,
    get_agent_status,
    list_agent_decisions,
    list_agent_jobs,
    list_agent_schedules,
    list_agent_workers,
)
from backend.app.api.services.agent_writes import (
    AgentScheduleError,
    pause_schedule,
    resume_schedule,
    update_schedule,
)
from backend.app.core.admin_config import AdminConfig, get_admin_config
from backend.app.db.models import AdminSession

router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(get_admin_session)],
)


def _require_csrf(request: Request, admin_session: AdminSession) -> None:
    config: AdminConfig = get_admin_config()
    require_csrf(
        request,
        request.headers.get("x-csrf-token"),
        admin_session,
        config,
    )


@router.get("/status")
def agent_status(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    return get_agent_status(session)


@router.get("/workers")
def agent_workers(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    return {"items": list_agent_workers(session)}


@router.get("/schedules")
def agent_schedules(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    source_id: str | None = Query(default=None, max_length=120),
    health: Literal["healthy", "degraded", "failed", "paused", "unknown"] | None = None,
) -> dict[str, object]:
    items = list_agent_schedules(session)
    if source_id:
        items = [item for item in items if item["source_id"] == source_id]
    if health:
        items = [item for item in items if item["health_status"] == health]
    return {"items": items, "total": len(items)}


@router.get("/sources/health")
def agent_source_health(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    items = get_agent_source_health(session)
    return {"items": items, "total": len(items)}


@router.get("/jobs")
def agent_jobs(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    source_id: Annotated[str | None, Query(max_length=120)] = None,
    state: Literal["queued", "running", "retry_wait", "completed", "failed", "cancelled"] | None = None,
) -> dict[str, object]:
    items, total = list_agent_jobs(session, page, page_size, source_id, state)
    return {
        "items": items,
        "pagination": PageMetadata(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    }


@router.get("/decisions")
def agent_decisions(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    source_id: Annotated[str | None, Query(max_length=120)] = None,
) -> dict[str, object]:
    items, total = list_agent_decisions(session, page, page_size, source_id)
    return {
        "items": items,
        "pagination": PageMetadata(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    }


@router.patch("/schedules/{source_key}")
def patch_schedule(
    source_key: str,
    payload: AgentScheduleUpdate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_session: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    _require_csrf(request, admin_session)
    try:
        schedule = update_schedule(session, source_key, payload)
        session.commit()
        return {
            "source_id": source_key,
            "mode": schedule.mode,
            "enabled": schedule.enabled,
            "base_interval_seconds": schedule.base_interval_seconds,
            "minimum_interval_seconds": schedule.minimum_interval_seconds,
            "maximum_interval_seconds": schedule.maximum_interval_seconds,
            "priority": schedule.priority,
            "next_due_at": schedule.next_due_at,
            "message": "Scheduling policy updated.",
        }
    except AgentScheduleError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.post("/schedules/{source_key}/pause")
def pause_source_schedule(
    source_key: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_session: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    _require_csrf(request, admin_session)
    try:
        schedule = pause_schedule(session, source_key)
        session.commit()
        return {"source_id": source_key, "mode": schedule.mode, "message": "Automatic scheduling paused."}
    except AgentScheduleError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.post("/schedules/{source_key}/resume")
def resume_source_schedule(
    source_key: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_session: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    _require_csrf(request, admin_session)
    try:
        schedule = resume_schedule(session, source_key)
        session.commit()
        return {
            "source_id": source_key,
            "mode": schedule.mode,
            "next_due_at": schedule.next_due_at,
            "message": "Automatic scheduling resumed.",
        }
    except AgentScheduleError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from None
