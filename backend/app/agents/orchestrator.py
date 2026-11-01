import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.collectors.base import Collector, RecordNormalizationError
from backend.app.db import repositories
from backend.app.db.models import CollectionRun, utc_now
from backend.app.pipeline.normalizer import normalize_record
from backend.app.pipeline.validator import validate_record

LOGGER = logging.getLogger(__name__)


class CollectionRunError(RuntimeError):
    """Raised when collection cannot complete; message contains no source secrets."""


@dataclass(frozen=True)
class CollectionSummary:
    run_id: uuid.UUID
    source_id: str
    status: str
    records_fetched: int
    records_new: int
    records_changed: int
    records_unchanged: int
    records_invalid: int
    duration_seconds: float


def _validation_details(error: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "field": ".".join(str(part) for part in item["loc"])[:120],
            "type": str(item["type"])[:80],
        }
        for item in error.errors(include_input=False)
    ]


def _failed_record_details(error: Exception) -> list[dict[str, str]]:
    return [{"field": "", "type": type(error).__name__[:80]}]


def _external_identifier(normalized: Mapping[str, Any]) -> str | None:
    value = normalized.get("external_record_id")
    if isinstance(value, str) and 1 <= len(value) <= 200:
        return value
    return None


def _safe_error_summary(error: Exception) -> str:
    return f"Collection failed ({type(error).__name__})."


class CollectionOrchestrator:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def run(
        self,
        source_id: str,
        collector: Collector,
        run_id: uuid.UUID | None = None,
    ) -> CollectionSummary:
        try:
            return self._run(source_id, collector, run_id)
        finally:
            collector.close()

    def _run(
        self,
        source_id: str,
        collector: Collector,
        requested_run_id: uuid.UUID | None,
    ) -> CollectionSummary:
        if source_id != collector.source_id:
            raise CollectionRunError("Requested source does not match its collector.")

        started_clock = time.monotonic()
        try:
            with self._session_factory.begin() as session:
                source = repositories.get_enabled_source(session, source_id)
                if source is None:
                    raise CollectionRunError("Source is not registered and enabled.")
                if requested_run_id is None:
                    run = repositories.start_run(session, source.id)
                else:
                    run = session.get(CollectionRun, requested_run_id)
                    if (
                        run is None
                        or run.source_id != source.id
                        or run.status != "running"
                    ):
                        raise CollectionRunError(
                            "Collection run is not available for execution."
                        )
                run_id = run.id
                source_snapshot = source
        except Exception as error:
            if isinstance(error, CollectionRunError):
                raise
            LOGGER.error(
                "collection_start_failed source=%s error_type=%s",
                source_id,
                type(error).__name__,
            )
            raise CollectionRunError(
                f"Collection could not start ({type(error).__name__})."
            ) from None

        LOGGER.info("collection_started source=%s run_id=%s", source_id, run_id)
        observed_at = utc_now()
        raw_records: Sequence[Mapping[str, Any]]
        try:
            raw_records = collector.fetch_records()
            fetched_count = len(raw_records)
            valid_records: list[BaseModel] = []
            invalid_records: list[tuple[str | None, list[dict[str, str]]]] = []

            for raw_record in raw_records:
                normalized: Mapping[str, Any] = {}
                try:
                    normalized = normalize_record(collector, raw_record)
                    validated = validate_record(
                        collector,
                        {**normalized, "observed_at": observed_at},
                    )
                    valid_records.append(validated)
                except ValidationError as error:
                    invalid_records.append(
                        (_external_identifier(normalized), _validation_details(error))
                    )
                except RecordNormalizationError as error:
                    invalid_records.append(
                        (
                            _external_identifier(normalized),
                            [{"field": error.field, "type": type(error).__name__}],
                        )
                    )
                except (TypeError, ValueError) as error:
                    invalid_records.append(
                        (_external_identifier(normalized), _failed_record_details(error))
                    )

            completed_at = utc_now()
            with self._session_factory.begin() as session:
                counts = repositories.persist_success(
                    session=session,
                    run_id=run_id,
                    source=source_snapshot,
                    records=valid_records,
                    invalid_records=invalid_records,
                    records_fetched=fetched_count,
                    completed_at=completed_at,
                )
        except Exception as error:
            failure_summary = _safe_error_summary(error)
            try:
                with self._session_factory.begin() as session:
                    repositories.mark_run_failed(
                        session,
                        run_id,
                        utc_now(),
                        failure_summary,
                    )
            except Exception as status_error:
                LOGGER.error(
                    "collection_failure_status_not_persisted source=%s run_id=%s "
                    "error_type=%s",
                    source_id,
                    run_id,
                    type(status_error).__name__,
                )
            LOGGER.error(
                "collection_failed source=%s run_id=%s error_type=%s",
                source_id,
                run_id,
                type(error).__name__,
            )
            if isinstance(error, CollectionRunError):
                raise
            raise CollectionRunError(failure_summary) from None
        duration = time.monotonic() - started_clock
        summary = CollectionSummary(
            run_id=run_id,
            source_id=source_id,
            status="completed",
            records_fetched=fetched_count,
            records_new=counts["new"],
            records_changed=counts["changed"],
            records_unchanged=counts["unchanged"],
            records_invalid=len(invalid_records),
            duration_seconds=duration,
        )
        LOGGER.info(
            "collection_completed source=%s run_id=%s status=%s fetched=%d "
            "new=%d changed=%d unchanged=%d invalid=%d duration_seconds=%.3f",
            source_id,
            run_id,
            summary.status,
            summary.records_fetched,
            summary.records_new,
            summary.records_changed,
            summary.records_unchanged,
            summary.records_invalid,
            summary.duration_seconds,
        )
        return summary
