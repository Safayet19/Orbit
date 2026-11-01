import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.agents.decision_engine import (
    DecisionType,
    outcome_decision,
)
from backend.app.agents.orchestrator import CollectionOrchestrator
from backend.app.collectors.worldbank import (
    INDICATOR_SPECS,
    WorldBankIndicatorCollector,
    WorldBankInflationCollector,
    register_world_bank_sources,
)
from backend.app.db.models import (
    AgentDecision,
    AgentJob,
    Base,
    CollectionRun,
    CurrentRecord,
    RecordVersion,
    Source,
    SourceSchedule,
)
from backend.app.db.repositories import upsert_observation
from backend.app.schemas.records import (
    WORLD_BANK_SOURCE_ID,
    WORLD_BANK_SOURCE_URL,
    WorldBankInflationRecord,
)
from backend.app.workers.agent_worker import (
    AgentWorker,
    JobLease,
    _claim_job,
    _recover_expired_jobs,
    _lease_valid,
)


@pytest.fixture
def factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _seed_sources(factory: sessionmaker, now: datetime) -> None:
    with factory.begin() as session:
        register_world_bank_sources(session, now)


def _inflation_record(value: str, observed_at: datetime) -> WorldBankInflationRecord:
    return WorldBankInflationRecord(
        source_id=WORLD_BANK_SOURCE_ID,
        external_record_id=f"{WORLD_BANK_SOURCE_ID}:BGD:FP.CPI.TOTL.ZG:2023",
        country_code="BGD",
        indicator_code="FP.CPI.TOTL.ZG",
        year=2023,
        value=Decimal(value),
        source_url=WORLD_BANK_SOURCE_URL,
        observed_at=observed_at,
    )


def test_source_registration_is_idempotent_and_preserves_policy(
    factory: sessionmaker,
) -> None:
    now = datetime.now(timezone.utc)
    _seed_sources(factory, now)
    with factory.begin() as session:
        schedule = session.scalar(
            select(SourceSchedule)
            .join(Source)
            .where(Source.source_key == "worldbank-bd-population")
        )
        assert schedule is not None
        schedule.base_interval_seconds = 40 * 24 * 60 * 60
        schedule.priority = 9

    _seed_sources(factory, now + timedelta(days=1))
    with factory() as session:
        assert session.scalar(select(Source).where(Source.source_key == "worldbank-bd-inflation")) is not None
        assert len(session.scalars(select(Source)).all()) == 3
        assert len(session.scalars(select(SourceSchedule)).all()) == 3
        population_schedule = session.scalar(
            select(SourceSchedule)
            .join(Source)
            .where(Source.source_key == "worldbank-bd-population")
        )
        assert population_schedule is not None
        assert population_schedule.base_interval_seconds == 40 * 24 * 60 * 60
        assert population_schedule.priority == 9


@pytest.mark.parametrize(
    ("changes", "expected_interval", "decision_type"),
    [
        ({"records_new": 0, "records_changed": 0}, 90 * 86400, DecisionType.ADJUST_INTERVAL),
        ({"records_new": 1, "records_changed": 0}, 15 * 86400, DecisionType.ADJUST_INTERVAL),
    ],
)
def test_adaptive_schedule_respects_bounds(
    factory: sessionmaker,
    changes: dict[str, int],
    expected_interval: int,
    decision_type: DecisionType,
) -> None:
    now = datetime.now(timezone.utc)
    _seed_sources(factory, now)
    with factory() as session:
        schedule = session.scalar(select(SourceSchedule))
        assert schedule is not None
        schedule.consecutive_unchanged = 8
        schedule.maximum_interval_seconds = 90 * 86400
        outcome = outcome_decision(
            schedule,
            now=now,
            succeeded=True,
            records_fetched=20,
            **changes,
        )
    assert outcome.decision.decision_type is decision_type
    assert outcome.next_due_at == now + timedelta(seconds=expected_interval)


def test_failures_back_off_and_stop_at_retry_limit(factory: sessionmaker) -> None:
    now = datetime.now(timezone.utc)
    _seed_sources(factory, now)
    with factory() as session:
        schedule = session.scalar(select(SourceSchedule))
        assert schedule is not None
        retry = outcome_decision(
            schedule,
            now=now,
            succeeded=False,
            failure_category="temporary_network_failure",
            retry_after_seconds=600,
        )
        assert retry.decision.decision_type is DecisionType.RETRY_LATER
        assert retry.next_due_at == now + timedelta(seconds=600)
        schedule.consecutive_failures = schedule.maximum_retries - 1
        stopped = outcome_decision(
            schedule,
            now=now,
            succeeded=False,
            failure_category="temporary_network_failure",
        )
        assert stopped.decision.decision_type is DecisionType.PAUSE_FOR_REVIEW
        assert stopped.next_due_at is None


def test_worker_claims_due_sources_without_duplicate_source_claims(
    factory: sessionmaker,
) -> None:
    now = datetime.now(timezone.utc)
    _seed_sources(factory, now)
    with factory.begin() as session:
        schedules = session.scalars(select(SourceSchedule)).all()
        for schedule in schedules:
            schedule.next_due_at = (
                now if schedule.source_id == schedules[0].source_id else now + timedelta(days=4)
            )

    first_worker = AgentWorker(factory, worker_id="worker-one")
    second_worker = AgentWorker(factory, worker_id="worker-two")
    first_worker._register()
    second_worker._register()
    first_lease = first_worker._cycle()
    second_lease = second_worker._cycle()
    assert first_lease is not None
    assert second_lease is None
    with factory() as session:
        jobs = session.scalars(
            select(AgentJob).where(
                AgentJob.status.in_(("queued", "running", "retry_wait"))
            )
        ).all()
        assert len(jobs) == 1
        assert jobs[0].source_id == first_lease.source_id


def test_expired_worker_lease_is_recovered_and_previous_run_closed(
    factory: sessionmaker,
) -> None:
    now = datetime.now(timezone.utc)
    _seed_sources(factory, now)
    with factory.begin() as session:
        source = session.scalar(select(Source))
        schedule = session.get(SourceSchedule, source.id)
        run = CollectionRun(source_id=source.id, status="running")
        session.add(run)
        session.flush()
        job = AgentJob(
            source_id=source.id,
            trigger_type="scheduled",
            status="running",
            scheduled_at=now - timedelta(minutes=10),
            started_at=now - timedelta(minutes=10),
            attempt_count=1,
            worker_id="dead-worker",
            lease_expires_at=now - timedelta(seconds=1),
            lease_generation=1,
            collection_run_id=run.id,
        )
        session.add(job)
        session.flush()
        recovered = _recover_expired_jobs(session, now)
        assert recovered == 1
        assert job.status == "retry_wait"
        assert job.worker_id is None
        assert job.lease_generation == 1
        assert run.status == "failed"
        assert schedule.health_status == "degraded"
        assert session.scalar(select(AgentDecision)) is not None


def test_stale_worker_generation_cannot_write(factory: sessionmaker) -> None:
    now = datetime.now(timezone.utc)
    _seed_sources(factory, now)
    worker = AgentWorker(factory, worker_id="lease-worker")
    worker._register()
    lease = worker._cycle()
    assert lease is not None
    with factory.begin() as session:
        job = session.get(AgentJob, lease.job_id)
        assert job is not None
        job.lease_generation += 1
    with factory() as session:
        with pytest.raises(Exception, match="lease is no longer owned"):
            _lease_valid(session, lease)


@pytest.mark.parametrize("spec", INDICATOR_SPECS, ids=lambda spec: spec.source_id)
def test_world_bank_indicator_adapters_validate_registered_sources(spec) -> None:
    payload = [
        {"page": 1, "pages": 1, "total": 1},
        [
            {
                "country": {"id": "BD", "value": "Bangladesh"},
                "countryiso3code": "BGD",
                "indicator": {"id": spec.indicator_code, "value": spec.name},
                "date": "2023",
                "value": 123.45,
            }
        ],
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, content=json.dumps(payload).encode())
        )
    )
    collector = (
        WorldBankInflationCollector(client=client, retry_delay=0)
        if spec.source_id == WORLD_BANK_SOURCE_ID
        else WorldBankIndicatorCollector(spec, client=client, retry_delay=0)
    )
    try:
        raw = collector.fetch_records()[0]
        normalized = collector.normalize(raw)
        validated = collector.record_model.model_validate(
            {**normalized, "observed_at": datetime.now(timezone.utc)}
        )
        assert validated.source_id == spec.source_id
        assert validated.indicator_code == spec.indicator_code
        assert str(validated.value) == "123.45"
    finally:
        collector.close()
        client.close()


def test_poor_quality_does_not_replace_known_good_records(factory: sessionmaker) -> None:
    now = datetime.now(timezone.utc)
    _seed_sources(factory, now)

    class InvalidValuesCollector(WorldBankInflationCollector):
        def fetch_records(self) -> list[dict[str, object]]:
            return [{"year": str(2023 + index), "value": False} for index in range(5)]

        def normalize(self, raw_record):
            year = int(raw_record["year"])
            return {
                "source_id": WORLD_BANK_SOURCE_ID,
                "external_record_id": f"{WORLD_BANK_SOURCE_ID}:BGD:FP.CPI.TOTL.ZG:{year}",
                "country_code": "BGD",
                "indicator_code": "FP.CPI.TOTL.ZG",
                "year": year,
                "value": raw_record["value"],
                "source_url": WORLD_BANK_SOURCE_URL,
            }

    with factory.begin() as session:
        source = session.scalar(
            select(Source).where(Source.source_key == WORLD_BANK_SOURCE_ID)
        )
        assert source is not None
        upsert_observation(session, source, _inflation_record("2.5", now))
        existing = session.scalar(select(CurrentRecord))
        assert existing is not None
        existing_id = existing.id
        previous_fingerprint = existing.fingerprint

    summary = CollectionOrchestrator(factory).run(
        WORLD_BANK_SOURCE_ID,
        InvalidValuesCollector(),
    )

    with factory() as session:
        saved = session.get(CurrentRecord, existing_id)
        run = session.scalar(select(CollectionRun).order_by(CollectionRun.started_at.desc()))
        versions = session.scalars(select(RecordVersion)).all()
        assert summary.quality_status == "degraded"
        assert run is not None
        assert run.status == "completed"
        assert run.quality_status == "degraded"
        assert run.records_invalid == 5
        assert saved is not None and saved.fingerprint == previous_fingerprint
        assert len(versions) == 1
