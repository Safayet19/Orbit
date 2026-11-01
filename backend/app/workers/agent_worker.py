import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.decision_engine import (
    Decision,
    DecisionType,
    outcome_decision,
)
from backend.app.agents.orchestrator import CollectionOrchestrator, CollectionRunError
from backend.app.collectors.worldbank import (
    CollectorError,
    create_world_bank_collector,
    register_world_bank_sources,
)
from backend.app.db.models import (
    AgentDecision,
    AgentJob,
    AgentWorker as AgentWorkerRecord,
    CollectionRun,
    Source,
    SourceSchedule,
    utc_now,
)
from backend.app.db.repositories import start_run

LOGGER = logging.getLogger(__name__)
WORKER_HEARTBEAT_SECONDS = 20
WORKER_OFFLINE_SECONDS = 90
JOB_LEASE_SECONDS = 180
MAX_CLAIM_BATCH = 100


@dataclass(frozen=True)
class JobLease:
    job_id: uuid.UUID
    run_id: uuid.UUID
    source_id: uuid.UUID
    source_key: str
    worker_id: str
    generation: int


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _record_decision(
    session: Session,
    decision: Decision,
    source_id: uuid.UUID | None,
    job_id: uuid.UUID | None = None,
) -> None:
    session.add(
        AgentDecision(
            source_id=source_id,
            job_id=job_id,
            decision_type=decision.decision_type.value,
            reason_code=decision.reason_code,
            explanation=decision.explanation,
            context=decision.context,
            next_action_at=decision.next_action_at,
        )
    )


def _active_job_exists(session: Session, source_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(AgentJob.id)
            .where(
                AgentJob.source_id == source_id,
                AgentJob.status.in_(("queued", "running", "retry_wait")),
            )
            .limit(1)
        )
        is not None
    )


def _recover_expired_jobs(session: Session, now: datetime) -> int:
    expired_jobs = session.scalars(
        select(AgentJob)
        .where(
            AgentJob.status == "running",
            AgentJob.lease_expires_at <= now,
        )
        .order_by(AgentJob.lease_expires_at)
        .limit(MAX_CLAIM_BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    recovered = 0
    for job in expired_jobs:
        schedule = session.get(SourceSchedule, job.source_id)
        if schedule is None:
            job.status = "failed"
            job.completed_at = now
            job.error_summary = "Schedule configuration was missing during recovery."
            job.worker_id = None
            job.lease_expires_at = None
            continue
        if job.collection_run_id is not None:
            run = session.get(CollectionRun, job.collection_run_id)
            if run is not None and run.status == "running":
                run.status = "failed"
                run.quality_status = "failed"
                run.completed_at = now
                run.error_summary = "Collection was interrupted; the worker lease expired."
        attempts_exhausted = job.attempt_count >= schedule.maximum_retries
        generation_context = {
            "attempt_count": job.attempt_count,
            "lease_generation": job.lease_generation,
            "previous_worker_id": job.worker_id,
        }
        job.worker_id = None
        job.lease_expires_at = None
        job.collection_run_id = None
        schedule.consecutive_failures += 1
        schedule.health_status = "degraded"
        schedule.health_reason = "A worker lease expired before the job completed."
        if attempts_exhausted:
            job.status = "failed"
            job.completed_at = now
            schedule.next_due_at = None
            decision = Decision(
                DecisionType.PAUSE_FOR_REVIEW,
                "recovery_attempt_limit",
                "The worker stopped before completion and the retry limit was reached; "
                "automatic execution is paused for administrator review.",
                None,
                generation_context,
            )
        else:
            backoff = min(300 * 2 ** max(0, job.attempt_count - 1), 21600)
            next_time = now + timedelta(seconds=backoff)
            job.status = "retry_wait"
            job.scheduled_at = next_time
            schedule.next_due_at = next_time
            decision = Decision(
                DecisionType.RETRY_LATER,
                "expired_lease_recovered",
                "The previous worker lease expired; the interrupted task was recovered "
                "and will retry after bounded backoff.",
                next_time,
                generation_context,
            )
        _record_decision(session, decision, job.source_id, job.id)
        recovered += 1
        LOGGER.warning(
            "agent_job_recovered job_id=%s source_id=%s attempt=%d terminal=%s",
            job.id,
            job.source_id,
            job.attempt_count,
            attempts_exhausted,
        )
    return recovered


def _enqueue_due_jobs(session: Session, now: datetime) -> int:
    candidates = session.execute(
        select(SourceSchedule, Source)
        .join(Source, Source.id == SourceSchedule.source_id)
        .where(
            Source.enabled.is_(True),
            SourceSchedule.enabled.is_(True),
            SourceSchedule.mode != "paused",
            SourceSchedule.next_due_at.is_not(None),
            SourceSchedule.next_due_at <= now,
        )
        .order_by(SourceSchedule.next_due_at, SourceSchedule.priority.desc())
        .limit(MAX_CLAIM_BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    enqueued = 0
    for schedule, source in candidates:
        if _active_job_exists(session, source.id):
            continue
        running_legacy_run = session.scalar(
            select(CollectionRun.id)
            .where(
                CollectionRun.source_id == source.id,
                CollectionRun.status == "running",
            )
            .limit(1)
        )
        if running_legacy_run is not None:
            continue
        job = AgentJob(
            source_id=source.id,
            trigger_type="scheduled",
            scheduled_at=now,
            status="queued",
        )
        try:
            with session.begin_nested():
                session.add(job)
                session.flush()
        except IntegrityError:
            continue
        schedule.next_due_at = None
        schedule.last_decision = DecisionType.COLLECT_NOW.value
        _record_decision(
            session,
            Decision(
                DecisionType.COLLECT_NOW,
                "schedule_due",
                "The approved source is enabled and its persisted schedule is due.",
                now,
                {
                    "source_id": source.source_key,
                    "mode": schedule.mode,
                    "priority": schedule.priority,
                },
            ),
            source.id,
            job.id,
        )
        LOGGER.info(
            "agent_job_scheduled source_id=%s job_id=%s trigger=scheduled",
            source.source_key,
            job.id,
        )
        enqueued += 1
    return enqueued


def _claim_job(
    session: Session,
    worker_id: str,
    now: datetime,
) -> JobLease | None:
    rows = session.execute(
        select(AgentJob, SourceSchedule, Source)
        .join(SourceSchedule, SourceSchedule.source_id == AgentJob.source_id)
        .join(Source, Source.id == AgentJob.source_id)
        .where(
            Source.enabled.is_(True),
            AgentJob.status.in_(("queued", "retry_wait")),
            AgentJob.scheduled_at <= now,
            SourceSchedule.enabled.is_(True),
        )
        .order_by(AgentJob.scheduled_at, AgentJob.created_at)
        .limit(MAX_CLAIM_BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    if not rows:
        return None

    def priority(item: tuple[AgentJob, SourceSchedule, Source]) -> tuple[float, int, str]:
        job, schedule, source = item
        overdue_hours = max(
            0.0,
            (now - _as_utc(job.scheduled_at)).total_seconds() / 3600,
        )
        score = min(overdue_hours, 1000.0) + schedule.priority * 24
        return (-score, _as_utc(job.created_at).timestamp(), source.source_key)

    rows.sort(key=priority)
    for job, schedule, source in rows:
        if job.trigger_type == "scheduled" and schedule.mode == "paused":
            job.status = "cancelled"
            job.completed_at = now
            schedule.next_due_at = None
            _record_decision(
                session,
                Decision(
                    DecisionType.POSTPONE,
                    "schedule_paused_before_claim",
                    "The schedule was paused before this job was claimed; no collection was run.",
                    None,
                    {"source_id": source.source_key},
                ),
                source.id,
                job.id,
            )
            continue
        if _active_job_exists(session, source.id) and job.status not in {
            "queued",
            "retry_wait",
        }:
            continue
        legacy_run = session.scalar(
            select(CollectionRun.id)
            .where(
                CollectionRun.source_id == source.id,
                CollectionRun.status == "running",
            )
            .limit(1)
        )
        if legacy_run is not None:
            continue
        job.status = "running"
        job.worker_id = worker_id
        job.started_at = job.started_at or now
        job.attempt_count += 1
        job.lease_generation += 1
        job.lease_expires_at = now + timedelta(seconds=JOB_LEASE_SECONDS)
        run = start_run(session, source.id)
        job.collection_run_id = run.id
        schedule.last_attempted_at = now
        worker = session.get(AgentWorkerRecord, worker_id)
        if worker is not None:
            worker.status = "executing"
            worker.active_job_id = job.id
            worker.last_heartbeat_at = now
        LOGGER.info(
            "agent_job_claimed worker_id=%s job_id=%s source_id=%s generation=%d",
            worker_id,
            job.id,
            source.source_key,
            job.lease_generation,
        )
        return JobLease(
            job_id=job.id,
            run_id=run.id,
            source_id=source.id,
            source_key=source.source_key,
            worker_id=worker_id,
            generation=job.lease_generation,
        )
    return None


def _lease_valid(
    session: Session,
    lease: JobLease,
    *,
    lock: bool = False,
) -> AgentJob:
    query = select(AgentJob).where(AgentJob.id == lease.job_id)
    if lock:
        query = query.with_for_update()
    job = session.scalar(query)
    if (
        job is None
        or job.status != "running"
        or job.worker_id != lease.worker_id
        or job.lease_generation != lease.generation
        or job.lease_expires_at is None
        or _as_utc(job.lease_expires_at) <= utc_now()
    ):
        raise CollectionRunError("Collection lease is no longer owned by this worker.")
    return job


class _LeaseHeartbeat:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        lease: JobLease,
        interval_seconds: int = WORKER_HEARTBEAT_SECONDS,
    ) -> None:
        self._factory = session_factory
        self._lease = lease
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"orbit-lease-{lease.job_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 2)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                now = utc_now()
                with self._factory.begin() as session:
                    job = session.scalar(
                        select(AgentJob)
                        .where(AgentJob.id == self._lease.job_id)
                        .with_for_update()
                    )
                    if (
                        job is None
                        or job.status != "running"
                        or job.worker_id != self._lease.worker_id
                        or job.lease_generation != self._lease.generation
                    ):
                        return
                    job.lease_expires_at = now + timedelta(seconds=JOB_LEASE_SECONDS)
                    worker = session.get(AgentWorkerRecord, self._lease.worker_id)
                    if worker is not None:
                        worker.last_heartbeat_at = now
                        worker.status = "executing"
                        worker.active_job_id = job.id
            except SQLAlchemyError as error:
                LOGGER.error(
                    "agent_heartbeat_failed worker_id=%s error_type=%s",
                    self._lease.worker_id,
                    type(error).__name__,
                )


def execute_owned_job(
    session_factory: sessionmaker[Session],
    lease: JobLease,
) -> None:
    heartbeat = _LeaseHeartbeat(session_factory, lease)
    heartbeat.start()
    try:
        def verify_lease(session: Session) -> None:
            _lease_valid(session, lease, lock=True)

        try:
            collector = create_world_bank_collector(lease.source_key)
            summary = CollectionOrchestrator(session_factory).run(
                lease.source_key,
                collector,
                run_id=lease.run_id,
                before_persist=verify_lease,
            )
        except Exception as error:
            category = (
                getattr(error, "failure_category", error.category)
                if isinstance(error, CollectorError)
                else getattr(error, "failure_category", "worker_execution_error")
            )
            _finish_failed_job(session_factory, lease, error, category)
            return
        _finish_successful_job(session_factory, lease, summary)
    finally:
        heartbeat.stop()


def _finish_successful_job(
    session_factory: sessionmaker[Session],
    lease: JobLease,
    summary: Any,
) -> None:
    now = utc_now()
    with session_factory.begin() as session:
        job = session.scalar(
            select(AgentJob).where(AgentJob.id == lease.job_id).with_for_update()
        )
        if (
            job is None
            or job.worker_id != lease.worker_id
            or job.lease_generation != lease.generation
            or job.status != "running"
        ):
            LOGGER.warning("agent_stale_completion_rejected job_id=%s", lease.job_id)
            return
        schedule = session.get(SourceSchedule, lease.source_id)
        if schedule is None:
            job.status = "failed"
            job.completed_at = now
            job.error_summary = "Schedule configuration was missing after collection."
            return
        outcome = outcome_decision(
            schedule,
            now=now,
            succeeded=True,
            records_new=summary.records_new,
            records_changed=summary.records_changed,
            records_invalid=summary.records_invalid,
            records_fetched=summary.records_fetched,
        )
        job.status = "completed"
        job.completed_at = now
        job.lease_expires_at = None
        job.quality_status = summary.quality_status
        schedule.last_successful_at = now
        schedule.consecutive_failures = outcome.consecutive_failures
        schedule.consecutive_unchanged = outcome.consecutive_unchanged
        schedule.quality_ratio = outcome.quality_ratio
        schedule.health_status = outcome.health_status
        schedule.health_reason = outcome.health_reason
        schedule.next_due_at = (
            outcome.next_due_at if schedule.enabled and schedule.mode != "paused" else None
        )
        schedule.last_decision = outcome.decision.decision_type.value
        worker = session.get(AgentWorkerRecord, lease.worker_id)
        if worker is not None:
            worker.last_heartbeat_at = now
            worker.status = "idle"
            worker.active_job_id = None
        _record_decision(session, outcome.decision, lease.source_id, lease.job_id)
    LOGGER.info(
        "agent_job_completed worker_id=%s job_id=%s source_id=%s quality=%s",
        lease.worker_id,
        lease.job_id,
        lease.source_key,
        summary.quality_status,
    )


def _finish_failed_job(
    session_factory: sessionmaker[Session],
    lease: JobLease,
    error: Exception,
    category: str,
) -> None:
    now = utc_now()
    with session_factory.begin() as session:
        job = session.scalar(
            select(AgentJob).where(AgentJob.id == lease.job_id).with_for_update()
        )
        if (
            job is None
            or job.worker_id != lease.worker_id
            or job.lease_generation != lease.generation
            or job.status != "running"
        ):
            LOGGER.warning("agent_stale_failure_rejected job_id=%s", lease.job_id)
            return
        schedule = session.get(SourceSchedule, lease.source_id)
        if schedule is None:
            job.status = "failed"
            job.completed_at = now
            job.error_summary = "Schedule configuration was missing after a failed collection."
            return
        retry_after = (
            error.retry_after_seconds if isinstance(error, CollectorError) else None
        )
        outcome = outcome_decision(
            schedule,
            now=now,
            succeeded=False,
            retry_after_seconds=retry_after,
            failure_category=category,
        )
        job.status = (
            "retry_wait"
            if outcome.next_due_at is not None
            else "failed"
        )
        job.scheduled_at = outcome.next_due_at or now
        job.completed_at = None if outcome.next_due_at is not None else now
        job.lease_expires_at = None
        job.failure_category = category[:40]
        job.error_summary = f"Collection failed ({category})."
        job.quality_status = "failed"
        schedule.consecutive_failures = outcome.consecutive_failures
        schedule.health_status = outcome.health_status
        schedule.health_reason = outcome.health_reason
        schedule.next_due_at = (
            outcome.next_due_at if schedule.enabled and schedule.mode != "paused" else None
        )
        schedule.last_decision = outcome.decision.decision_type.value
        worker = session.get(AgentWorkerRecord, lease.worker_id)
        if worker is not None:
            worker.last_heartbeat_at = now
            worker.status = "idle"
            worker.active_job_id = None
            worker.last_error = f"Collection failed ({category})."
        _record_decision(session, outcome.decision, lease.source_id, lease.job_id)
    LOGGER.error(
        "agent_job_failed worker_id=%s job_id=%s source_id=%s category=%s error_type=%s",
        lease.worker_id,
        lease.job_id,
        lease.source_key,
        category,
        type(error).__name__,
    )


class AgentWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        poll_interval_seconds: int = 30,
        worker_id: str | None = None,
    ) -> None:
        self._factory = session_factory
        self._poll_interval = max(1, poll_interval_seconds)
        self.worker_id = worker_id or f"orbit-worker-{uuid.uuid4()}"
        self._stop = threading.Event()

    def start(self, once: bool = False) -> int:
        self._register()
        LOGGER.info("agent_worker_started worker_id=%s once=%s", self.worker_id, once)
        try:
            if once:
                lease = self._cycle()
                if lease is not None:
                    execute_owned_job(self._factory, lease)
                return 0
            while not self._stop.is_set():
                lease = self._cycle()
                if lease is not None:
                    execute_owned_job(self._factory, lease)
                    continue
                self._stop.wait(self._poll_interval)
            return 0
        finally:
            self._shutdown()

    def stop(self) -> None:
        self._stop.set()

    def _register(self) -> None:
        now = utc_now()
        with self._factory.begin() as session:
            register_world_bank_sources(session, now)
            session.merge(
                AgentWorkerRecord(
                    id=self.worker_id,
                    started_at=now,
                    last_heartbeat_at=now,
                    status="idle",
                    version="0.1.0",
                )
            )
        LOGGER.info("agent_sources_registered worker_id=%s", self.worker_id)

    def _cycle(self) -> JobLease | None:
        now = utc_now()
        with self._factory.begin() as session:
            worker = session.get(AgentWorkerRecord, self.worker_id)
            if worker is not None:
                worker.last_heartbeat_at = now
                worker.status = "idle"
                worker.active_job_id = None
            _recover_expired_jobs(session, now)
            _enqueue_due_jobs(session, now)
            return _claim_job(session, self.worker_id, now)

    def _shutdown(self) -> None:
        now = utc_now()
        try:
            with self._factory.begin() as session:
                worker = session.get(AgentWorkerRecord, self.worker_id)
                if worker is not None:
                    worker.status = "offline"
                    worker.active_job_id = None
                    worker.last_heartbeat_at = now
            LOGGER.info("agent_worker_stopped worker_id=%s", self.worker_id)
        except SQLAlchemyError as error:
            LOGGER.error(
                "agent_worker_shutdown_state_failed worker_id=%s error_type=%s",
                self.worker_id,
                type(error).__name__,
            )
