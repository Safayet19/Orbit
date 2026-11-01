import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.decision_engine import Decision, DecisionType
from backend.app.api.services.admin_reads import SUPPORTED_SOURCE_IDS
from backend.app.db.models import (
    AgentJob,
    CollectionRun,
    Source,
    SourceSchedule,
    utc_now,
)
from backend.app.db.repositories import start_run
from backend.app.workers.agent_worker import JOB_LEASE_SECONDS, _record_decision


class AdminOperationError(ValueError):
    pass


def update_source_enabled(
    session: Session,
    source_key: str,
    enabled: bool,
) -> Source:
    source = session.scalar(
        select(Source).where(Source.source_key == source_key).with_for_update()
    )
    if source is None:
        raise AdminOperationError("Source not found.")
    if enabled and source_key not in SUPPORTED_SOURCE_IDS:
        raise AdminOperationError("No approved collector is registered for this source.")
    source.enabled = enabled
    source.updated_at = utc_now()
    schedule = session.get(SourceSchedule, source.id)
    if schedule is not None:
        if enabled and schedule.enabled and schedule.mode != "paused":
            schedule.next_due_at = schedule.next_due_at or utc_now()
            if schedule.health_status == "paused":
                schedule.health_status = "unknown"
                schedule.health_reason = None
        elif not enabled:
            schedule.health_status = "paused"
            schedule.health_reason = "The source is disabled by an administrator."
        schedule.updated_at = utc_now()
    session.flush()
    return source


def create_collection_run(
    session: Session,
    source_key: str,
) -> tuple[CollectionRun, AgentJob]:
    source = session.scalar(
        select(Source).where(Source.source_key == source_key).with_for_update()
    )
    if source is None:
        raise AdminOperationError("Source not found.")
    if not source.enabled:
        raise AdminOperationError("Source is disabled.")
    if source_key not in SUPPORTED_SOURCE_IDS:
        raise AdminOperationError("No approved collector is registered for this source.")

    active_job = session.scalar(
        select(AgentJob.id)
        .where(
            AgentJob.source_id == source.id,
            AgentJob.status.in_(("queued", "running", "retry_wait")),
        )
        .limit(1)
    )
    if active_job is not None:
        raise AdminOperationError("A collection is already queued or running for this source.")
    active_run = session.scalar(
        select(CollectionRun.id)
        .where(
            CollectionRun.source_id == source.id,
            CollectionRun.status == "running",
        )
        .limit(1)
    )
    if active_run is not None:
        raise AdminOperationError("A collection is already running for this source.")

    now = utc_now()
    run = start_run(session, source.id)
    manual_worker_id = f"manual-api-{uuid.uuid4()}"
    job = AgentJob(
        source_id=source.id,
        trigger_type="manual",
        scheduled_at=now,
        started_at=now,
        status="running",
        attempt_count=1,
        worker_id=manual_worker_id,
        lease_expires_at=now + timedelta(seconds=JOB_LEASE_SECONDS),
        lease_generation=1,
        collection_run_id=run.id,
    )
    session.add(job)
    session.flush()
    schedule = session.get(SourceSchedule, source.id)
    if schedule is not None:
        schedule.last_attempted_at = now
    _record_decision(
        session,
        Decision(
            DecisionType.COLLECT_NOW,
            "administrator_manual_request",
            "An authenticated administrator requested an approved manual collection.",
            now,
            {"source_id": source_key, "trigger_type": "manual"},
        ),
        source.id,
        job.id,
    )
    return run, job
