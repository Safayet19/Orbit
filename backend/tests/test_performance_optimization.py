import asyncio
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, insert, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes.quality import quality_summary
from backend.app.api.routes.records import MAX_EXPORT_ROWS, export_records
from backend.app.api.services.admin_reads import get_overview, get_record, list_history
from backend.app.api.services.agent_reads import get_agent_status
from backend.app.collectors.worldbank import register_world_bank_sources
from backend.app.db.models import (
    AdminSession,
    Base,
    CollectionRun,
    CurrentRecord,
    RecordVersion,
    Source,
)


@pytest.fixture
def factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def _source(session: Session, source_key: str = "test-source") -> Source:
    source = Source(
        source_key=source_key,
        name=source_key.replace("-", " ").title(),
        source_type="api",
        official_url="https://example.test/data",
        category="test",
        collection_config={},
        licensing_metadata={},
        enabled=True,
    )
    session.add(source)
    session.flush()
    return source


def _current_record(
    source: Source,
    observed_at: datetime,
    data: dict[str, object],
    external_record_id: str,
) -> CurrentRecord:
    return CurrentRecord(
        source_id=source.id,
        external_record_id=external_record_id,
        category=source.category,
        data=data,
        source_url=source.official_url,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        fingerprint="0" * 64,
        status="active",
    )


def _record_version(
    record_id: uuid.UUID,
    version_number: int,
    observed_at: datetime,
    data: dict[str, object],
) -> RecordVersion:
    return RecordVersion(
        record_id=record_id,
        version_number=version_number,
        data=data,
        fingerprint=f"{version_number:064d}",
        observed_at=observed_at,
        provenance={},
    )


def _consume_stream(response) -> str:
    async def consume() -> str:
        chunks = [chunk async for chunk in response.body_iterator]
        return "".join(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            for chunk in chunks
        )

    return asyncio.run(consume())


def test_history_fetches_previous_versions_in_one_page_query(
    factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        source = _source(session)
        record = _current_record(source, now, {"value": 2}, "record-1")
        session.add(record)
        session.flush()
        session.add_all(
            [
                _record_version(record.id, 1, now - timedelta(days=1), {"value": 1}),
                _record_version(record.id, 2, now, {"value": 2}),
            ]
        )

    statements: list[str] = []
    bind = factory.kw["bind"]

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lower())

    event.listen(bind, "before_cursor_execute", capture)
    try:
        with factory() as session:
            items, total = list_history(session, page=1, page_size=20)
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    history_selects = [
        statement
        for statement in statements
        if statement.lstrip().startswith("select")
        and "orbit_record_versions" in statement
    ]
    assert total == 1
    assert items[0]["previous_data"] == {"value": 1}
    assert len(history_selects) == 2


def test_record_detail_loads_latest_version_in_its_primary_query(
    factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        source = _source(session)
        record = _current_record(source, now, {"value": 2}, "record-1")
        session.add(record)
        session.flush()
        session.add_all(
            [
                _record_version(record.id, 1, now - timedelta(days=1), {"value": 1}),
                _record_version(record.id, 2, now, {"value": 2}),
            ]
        )
        record_id = record.id

    statements: list[str] = []
    bind = factory.kw["bind"]

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lower())

    event.listen(bind, "before_cursor_execute", capture)
    try:
        with factory() as session:
            record = get_record(session, record_id)
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    detail_selects = [
        statement
        for statement in statements
        if statement.lstrip().startswith("select")
        and "orbit_records" in statement
    ]
    assert record is not None
    assert record.version_number == 2
    assert len(detail_selects) == 1


def test_overview_and_quality_aggregates_preserve_counts(
    factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        recent_source = _source(session)
        stale_source = _source(session, "stale-source")
        disabled_source = _source(session, "disabled-source")
        disabled_source.enabled = False
        session.add(
            _current_record(recent_source, now, {"value": 4}, "record-1")
        )
        session.add_all(
            [
                CollectionRun(
                    source_id=recent_source.id,
                    status="completed",
                    started_at=now,
                    completed_at=now,
                    records_new=2,
                ),
                CollectionRun(
                    source_id=stale_source.id,
                    status="failed",
                    started_at=now,
                    completed_at=now,
                ),
                CollectionRun(
                    source_id=disabled_source.id,
                    status="running",
                    started_at=now,
                ),
            ]
        )

    bind = factory.kw["bind"]
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement.lower())

    event.listen(bind, "before_cursor_execute", capture)
    try:
        with factory() as session:
            overview = get_overview(session, period_days=30)
        overview_select_count = len(statements)
        statements.clear()
        with factory() as session:
            quality = quality_summary(
                session,
                AdminSession(token_hash="test", csrf_hash="test"),
            )
        quality_select_count = len(statements)
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    assert overview.registered_sources == 3
    assert overview.enabled_sources == 2
    assert overview.stale_sources == 1
    assert overview.total_records == 1
    assert overview.successful_runs == 1
    assert overview.failed_runs == 1
    assert overview.running_runs == 1
    assert overview.chart[0]["new_records"] == 2
    assert quality["status"] == "error"
    assert quality["valid_records"] == 1
    assert quality["failed_runs"] == 1
    assert quality["sources_with_recent_errors"] == 1
    assert quality["stale_sources"] == 1
    assert overview_select_count == 6
    assert quality_select_count == 4


def test_agent_status_uses_seven_bounded_queries(
    factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        register_world_bank_sources(session, now)

    statements: list[str] = []
    bind = factory.kw["bind"]

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement.lower())

    event.listen(bind, "before_cursor_execute", capture)
    try:
        with factory() as session:
            status = get_agent_status(session, now)
    finally:
        event.remove(bind, "before_cursor_execute", capture)

    assert len(statements) == 7
    assert status["scheduled_sources"] == 3
    assert status["worker_online"] is False


def test_csv_export_preserves_dynamic_fields_and_streams_rows(
    factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        source = _source(session)
        session.add_all(
            [
                _current_record(
                    source,
                    now,
                    {"z": 1, "a": "=SUM(1,1)"},
                    "newest",
                ),
                _current_record(
                    source,
                    now - timedelta(days=1),
                    {"a": "plain", "other": {"b": 2}},
                    "older",
                ),
            ]
        )

    with factory() as session:
        response = export_records(session, AdminSession(token_hash="test", csrf_hash="test"))

    rows = list(csv.DictReader(io.StringIO(_consume_stream(response))))
    assert list(rows[0]) == [
        "record_id",
        "source_name",
        "external_record_id",
        "category",
        "source_url",
        "first_observed_at",
        "last_observed_at",
        "a",
        "other",
        "z",
    ]
    assert [row["external_record_id"] for row in rows] == ["newest", "older"]
    assert rows[0]["a"] == "'=SUM(1,1)"
    assert rows[1]["other"] == '{"b": 2}'


def test_csv_export_of_no_records_returns_headers_only(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        response = export_records(session, AdminSession(token_hash="test", csrf_hash="test"))

    assert _consume_stream(response).splitlines() == [
        "record_id,source_name,external_record_id,category,source_url,"
        "first_observed_at,last_observed_at"
    ]


def test_csv_export_streams_the_full_allowed_row_limit(
    factory: sessionmaker[Session],
) -> None:
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        source = _source(session)
        session.execute(
            insert(CurrentRecord),
            [
                {
                    "id": uuid.uuid4(),
                    "source_id": source.id,
                    "external_record_id": f"record-{index}",
                    "category": source.category,
                    "data": {"year": index},
                    "source_url": source.official_url,
                    "first_observed_at": now,
                    "last_observed_at": now - timedelta(seconds=index),
                    "fingerprint": "0" * 64,
                    "status": "active",
                }
                for index in range(MAX_EXPORT_ROWS)
            ],
        )

    with factory() as session:
        response = export_records(
            session,
            AdminSession(token_hash="test", csrf_hash="test"),
        )

    rows = list(csv.DictReader(io.StringIO(_consume_stream(response))))
    assert len(rows) == MAX_EXPORT_ROWS
    assert rows[0]["year"]
    assert rows[-1]["year"]


def test_csv_export_enforces_the_existing_row_limit() -> None:
    session = Mock()
    session.scalars.return_value.all.return_value = [
        uuid.uuid4() for _ in range(MAX_EXPORT_ROWS + 1)
    ]

    with pytest.raises(HTTPException) as error:
        export_records(
            session,
            AdminSession(token_hash="test", csrf_hash="test"),
        )

    assert error.value.status_code == 413
