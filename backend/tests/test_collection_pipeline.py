import json
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.agents.orchestrator import CollectionOrchestrator, CollectionRunError
from backend.app.collectors.base import Collector
from backend.app.collectors.worldbank import (
    CollectorError,
    WorldBankInflationCollector,
)
from backend.app.db.models import (
    Base,
    CollectionRun,
    CurrentRecord,
    RecordVersion,
    Source,
)
from backend.app.db.repositories import upsert_observation
from backend.app.pipeline.fingerprint import content_fingerprint
from backend.app.schemas.records import (
    WORLD_BANK_SOURCE_ID,
    WORLD_BANK_SOURCE_URL,
    WorldBankInflationRecord,
)


def _api_record(year: str, value: float | None) -> dict[str, object]:
    return {
        "country": {"id": "BD", "value": "Bangladesh"},
        "countryiso3code": "BGD",
        "indicator": {"id": "FP.CPI.TOTL.ZG", "value": "Inflation"},
        "date": year,
        "value": value,
    }


def _validated_record(value: str, observed_at: datetime) -> WorldBankInflationRecord:
    year = 2023
    return WorldBankInflationRecord(
        source_id=WORLD_BANK_SOURCE_ID,
        external_record_id=f"{WORLD_BANK_SOURCE_ID}:BGD:FP.CPI.TOTL.ZG:{year}",
        country_code="BGD",
        indicator_code="FP.CPI.TOTL.ZG",
        year=year,
        value=Decimal(value),
        source_url=WORLD_BANK_SOURCE_URL,
        observed_at=observed_at,
    )


def test_fingerprint_ignores_observation_timestamp() -> None:
    first = {
        "year": 2023,
        "value": Decimal("2.5000"),
        "observed_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    second = {
        "value": Decimal("2.5"),
        "observed_at": datetime(2025, 1, 2, tzinfo=timezone.utc),
        "year": 2023,
    }

    assert content_fingerprint(first) == content_fingerprint(second)


def test_world_bank_schema_rejects_another_country() -> None:
    record = _validated_record(
        "2.5",
        datetime(2025, 1, 1, tzinfo=timezone.utc),
    ).model_dump()
    record["country_code"] = "USA"
    record["external_record_id"] = (
        f"{WORLD_BANK_SOURCE_ID}:USA:FP.CPI.TOTL.ZG:2023"
    )

    with pytest.raises(ValueError):
        WorldBankInflationRecord.model_validate(record)


def test_world_bank_collector_paginates_and_omits_missing_values() -> None:
    responses = {
        1: [
            {"page": 1, "pages": 2, "total": 3},
            [_api_record("2023", 2.5), _api_record("2022", None)],
        ],
        2: [{"page": 2, "pages": 2, "total": 3}, [_api_record("2021", 5.6)]],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        page = int(_request.url.params["page"])
        return httpx.Response(200, content=json.dumps(responses[page]).encode())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = WorldBankInflationCollector(client=client, retry_delay=0)
    records = collector.fetch_records()
    client.close()

    assert len(records) == 2
    assert [record["date"] for record in records] == ["2023", "2021"]
    assert isinstance(records[0]["value"], Decimal)


def test_repository_deduplicates_and_appends_changed_versions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    with Session(engine) as session, session.begin():
        source = Source(
            source_key=WORLD_BANK_SOURCE_ID,
            name="World Bank Bangladesh Inflation",
            source_type="api",
            official_url=WORLD_BANK_SOURCE_URL,
            category="economic_indicators",
            collection_config={},
            licensing_metadata={},
            enabled=True,
        )
        session.add(source)
        session.flush()

        assert upsert_observation(
            session, source, _validated_record("2.5", first_time)
        ) == "new"
        assert upsert_observation(
            session,
            source,
            _validated_record("2.500", datetime(2025, 1, 2, tzinfo=timezone.utc)),
        ) == "unchanged"
        assert upsert_observation(
            session,
            source,
            _validated_record("3.1", datetime(2025, 1, 3, tzinfo=timezone.utc)),
        ) == "changed"

        current_records = session.scalars(select(CurrentRecord)).all()
        versions = session.scalars(select(RecordVersion)).all()
        assert len(current_records) == 1
        assert len(versions) == 2
        assert [version.version_number for version in versions] == [1, 2]

    engine.dispose()


def test_world_bank_rejects_malformed_response() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"unexpected": "shape"})
        )
    )
    collector = WorldBankInflationCollector(client=client, retry_delay=0)

    try:
        try:
            collector.fetch_records()
        except CollectorError:
            pass
        else:
            raise AssertionError("Malformed API response should fail collection.")
    finally:
        client.close()


def test_failed_collection_is_recorded_without_partial_records() -> None:
    class FailingCollector(Collector):
        source_id = WORLD_BANK_SOURCE_ID
        category = "economic_indicators"
        record_model = WorldBankInflationRecord

        def fetch_records(self) -> list[dict[str, object]]:
            raise RuntimeError("private connection details must not be stored")

        def normalize(self, raw_record: dict[str, object]) -> dict[str, object]:
            return raw_record

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            Source(
                source_key=WORLD_BANK_SOURCE_ID,
                name="World Bank Bangladesh Inflation",
                source_type="api",
                official_url=WORLD_BANK_SOURCE_URL,
                category="economic_indicators",
                collection_config={},
                licensing_metadata={},
                enabled=True,
            )
        )

    try:
        try:
            CollectionOrchestrator(factory).run(
                WORLD_BANK_SOURCE_ID,
                FailingCollector(),
            )
        except CollectionRunError:
            pass
        else:
            raise AssertionError("A failed source request should fail the run.")

        with factory() as session:
            run = session.scalar(select(CollectionRun))
            assert run is not None
            assert run.status == "failed"
            assert run.error_summary == "Collection failed (RuntimeError)."
            assert session.scalars(select(CurrentRecord)).all() == []
            assert session.scalars(select(RecordVersion)).all() == []
    finally:
        engine.dispose()
