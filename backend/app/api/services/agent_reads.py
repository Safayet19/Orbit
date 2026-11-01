from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.app.collectors.worldbank import INDICATORS_BY_SOURCE
from backend.app.db.models import (
    AgentDecision,
    AgentJob,
    AgentWorker,
    CollectionRun,
    Source,
    SourceSchedule,
)

WORKER_ONLINE_SECONDS = 90


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def get_agent_status(session: Session, now: datetime | None = None) -> dict[str, Any]:
    checked_at = now or datetime.now(timezone.utc)
    worker_items = _worker_items(session, checked_at)
    online_workers = [worker for worker in worker_items if worker["status"] != "offline"]
    scheduled_predicate = (
        SourceSchedule.enabled.is_(True)
        & (SourceSchedule.mode != "paused")
        & SourceSchedule.next_due_at.is_not(None)
    )
    schedule_counts = session.execute(
        select(
            func.coalesce(func.sum(case((scheduled_predicate, 1), else_=0)), 0),
            func.min(
                case(
                    (scheduled_predicate, SourceSchedule.next_due_at),
                    else_=None,
                )
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Source.enabled.is_(True)
                            & SourceSchedule.enabled.is_(True)
                            & (SourceSchedule.health_status == "healthy"),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Source.enabled.is_(True)
                            & SourceSchedule.enabled.is_(True)
                            & (SourceSchedule.health_status == "degraded"),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(SourceSchedule)
        .join(Source, Source.id == SourceSchedule.source_id)
    ).one()
    scheduled_sources = int(schedule_counts[0])
    next_schedule_execution = schedule_counts[1]
    healthy_sources = int(schedule_counts[2])
    degraded_sources = int(schedule_counts[3])
    pending_predicate = AgentJob.status.in_(("queued", "retry_wait"))
    job_counts = session.execute(
        select(
            func.coalesce(
                func.sum(case((AgentJob.status == "running", 1), else_=0)),
                0,
            ),
            func.coalesce(func.sum(case((pending_predicate, 1), else_=0)), 0),
            func.min(case((pending_predicate, AgentJob.scheduled_at), else_=None)),
            func.coalesce(
                func.sum(case((AgentJob.attempt_count > 1, 1), else_=0)),
                0,
            ),
        )
    ).one()
    active_jobs = int(job_counts[0])
    pending_jobs = int(job_counts[1])
    next_job_execution = job_counts[2]
    retry_count = int(job_counts[3])
    next_execution = min(
        (value for value in (next_schedule_execution, next_job_execution) if value is not None),
        key=_utc,
        default=None,
    )

    latest_success = session.execute(
        select(CollectionRun, Source.name)
        .join(Source, Source.id == CollectionRun.source_id)
        .where(CollectionRun.status == "completed")
        .order_by(CollectionRun.started_at.desc())
        .limit(1)
    ).first()
    latest_failure = session.execute(
        select(CollectionRun, Source.name)
        .join(Source, Source.id == CollectionRun.source_id)
        .where(CollectionRun.status == "failed")
        .order_by(CollectionRun.started_at.desc())
        .limit(1)
    ).first()
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
        )
    ).one()
    successful_count, failed_count = map(int, run_counts)
    thirty_days_ago = checked_at - timedelta(days=30)
    recent_completed = session.execute(
        select(CollectionRun.started_at, CollectionRun.completed_at)
        .where(
            CollectionRun.status == "completed",
            CollectionRun.completed_at >= thirty_days_ago,
        )
        .order_by(CollectionRun.completed_at.desc())
        .limit(200)
    ).all()
    durations = [
        max(0.0, (_utc(completed_at) - _utc(started_at)).total_seconds())
        for started_at, completed_at in recent_completed
        if completed_at is not None
    ]
    return {
        "checked_at": checked_at,
        "worker_online": bool(online_workers),
        "workers": worker_items,
        "active_jobs": active_jobs,
        "scheduled_jobs": pending_jobs + scheduled_sources,
        "scheduled_sources": scheduled_sources,
        "next_execution_at": next_execution,
        "healthy_sources": healthy_sources,
        "degraded_sources": degraded_sources,
        "latest_success": _run_info(latest_success) if latest_success else None,
        "latest_failure": _run_info(latest_failure) if latest_failure else None,
        "successful_jobs": successful_count,
        "failed_jobs": failed_count,
        "average_duration_seconds": (
            round(sum(durations) / len(durations), 2) if durations else None
        ),
        "average_duration_sample_size": len(durations),
        "retry_count": retry_count,
        "worker_offline_after_seconds": WORKER_ONLINE_SECONDS,
    }


def _run_info(item: tuple[CollectionRun, str]) -> dict[str, Any]:
    run, source_name = item
    return {
        "run_id": str(run.id),
        "source_name": source_name,
        "status": run.status,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "quality_status": run.quality_status,
        "error_summary": run.error_summary,
    }


def _worker_items(
    session: Session,
    checked_at: datetime,
) -> list[dict[str, Any]]:
    workers = session.scalars(
        select(AgentWorker).order_by(AgentWorker.last_heartbeat_at.desc())
    ).all()
    cutoff = checked_at - timedelta(seconds=WORKER_ONLINE_SECONDS)
    return [
        {
            "worker_id": worker.id,
            "status": (
                worker.status
                if worker.status != "offline"
                and _utc(worker.last_heartbeat_at) >= cutoff
                else "offline"
            ),
            "started_at": worker.started_at,
            "last_heartbeat_at": worker.last_heartbeat_at,
            "active_job_id": (
                str(worker.active_job_id) if worker.active_job_id else None
            ),
            "last_error": worker.last_error,
            "version": worker.version,
        }
        for worker in workers
    ]


def list_agent_workers(session: Session) -> list[dict[str, Any]]:
    return _worker_items(session, datetime.now(timezone.utc))


def list_agent_schedules(session: Session) -> list[dict[str, Any]]:
    latest_run_id = (
        select(CollectionRun.id)
        .where(CollectionRun.source_id == Source.id)
        .order_by(CollectionRun.started_at.desc())
        .limit(1)
        .correlate(Source)
        .scalar_subquery()
    )
    rows = session.execute(
        select(SourceSchedule, Source, CollectionRun)
        .join(Source, Source.id == SourceSchedule.source_id)
        .outerjoin(CollectionRun, CollectionRun.id == latest_run_id)
        .order_by(Source.name)
    ).all()
    return [
        {
            "source_id": source.source_key,
            "source_name": source.name,
            "approved": source.source_key in INDICATORS_BY_SOURCE,
            "source_enabled": source.enabled,
            "mode": schedule.mode,
            "enabled": schedule.enabled,
            "base_interval_seconds": schedule.base_interval_seconds,
            "minimum_interval_seconds": schedule.minimum_interval_seconds,
            "maximum_interval_seconds": schedule.maximum_interval_seconds,
            "priority": schedule.priority,
            "next_due_at": schedule.next_due_at,
            "last_attempted_at": schedule.last_attempted_at,
            "last_successful_at": schedule.last_successful_at,
            "consecutive_failures": schedule.consecutive_failures,
            "consecutive_unchanged": schedule.consecutive_unchanged,
            "health_status": (
                "paused"
                if schedule.mode == "paused" or not schedule.enabled or not source.enabled
                else schedule.health_status
            ),
            "health_reason": schedule.health_reason,
            "quality_ratio": schedule.quality_ratio,
            "latest_run": (
                {
                    "run_id": str(run.id),
                    "status": run.status,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "quality_status": run.quality_status,
                    "records_fetched": run.records_fetched,
                    "records_invalid": run.records_invalid,
                    "error_summary": run.error_summary,
                }
                if run
                else None
            ),
        }
        for schedule, source, run in rows
    ]


def list_agent_jobs(
    session: Session,
    page: int,
    page_size: int,
    source_key: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    query = select(AgentJob, Source.name, Source.source_key).join(
        Source, Source.id == AgentJob.source_id
    )
    count_query = select(func.count(AgentJob.id)).join(
        Source, Source.id == AgentJob.source_id
    )
    if source_key:
        query = query.where(Source.source_key == source_key)
        count_query = count_query.where(Source.source_key == source_key)
    if status:
        query = query.where(AgentJob.status == status)
        count_query = count_query.where(AgentJob.status == status)
    total = int(session.scalar(count_query) or 0)
    rows = session.execute(
        query.order_by(AgentJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "job_id": str(job.id),
            "source_id": source_key_value,
            "source_name": source_name,
            "trigger_type": job.trigger_type,
            "created_at": job.created_at,
            "scheduled_at": job.scheduled_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "status": job.status,
            "attempt_count": job.attempt_count,
            "worker_id": job.worker_id,
            "lease_expires_at": job.lease_expires_at,
            "lease_generation": job.lease_generation,
            "collection_run_id": (
                str(job.collection_run_id) if job.collection_run_id else None
            ),
            "failure_category": job.failure_category,
            "error_summary": job.error_summary,
            "quality_status": job.quality_status,
        }
        for job, source_name, source_key_value in rows
    ]
    return items, total


def list_agent_decisions(
    session: Session,
    page: int,
    page_size: int,
    source_key: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    query = select(AgentDecision, Source.name, Source.source_key).outerjoin(
        Source, Source.id == AgentDecision.source_id
    )
    count_query = select(func.count(AgentDecision.id))
    if source_key:
        query = query.where(Source.source_key == source_key)
        count_query = count_query.select_from(AgentDecision).outerjoin(
            Source, Source.id == AgentDecision.source_id
        ).where(Source.source_key == source_key)
    total = int(session.scalar(count_query) or 0)
    rows = session.execute(
        query.order_by(AgentDecision.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "decision_id": str(decision.id),
            "source_name": source_name or "System",
            "source_id": source_key_value,
            "job_id": str(decision.job_id) if decision.job_id else None,
            "decision_type": decision.decision_type,
            "reason_code": decision.reason_code,
            "explanation": decision.explanation,
            "context": decision.context,
            "created_at": decision.created_at,
            "next_action_at": decision.next_action_at,
        }
        for decision, source_name, source_key_value in rows
    ]
    return items, total


def get_agent_source_health(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "source_id": schedule["source_id"],
            "source_name": schedule["source_name"],
            "health_status": schedule["health_status"],
            "last_successful_at": schedule["last_successful_at"],
            "consecutive_failures": schedule["consecutive_failures"],
            "quality_ratio": schedule["quality_ratio"],
            "next_due_at": schedule["next_due_at"],
            "health_reason": schedule["health_reason"],
            "latest_run": schedule["latest_run"],
        }
        for schedule in list_agent_schedules(session)
    ]


def find_agent_schedule(
    session: Session,
    source_key: str,
) -> SourceSchedule | None:
    source_id = session.scalar(
        select(Source.id).where(Source.source_key == source_key)
    )
    if source_id is None:
        return None
    return session.get(SourceSchedule, source_id)
