import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.services.admin_reads import SUPPORTED_SOURCE_IDS
from backend.app.db.models import CollectionRun, Source, utc_now
from backend.app.db.repositories import start_run


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
    session.flush()
    return source


def create_collection_run(session: Session, source_key: str) -> CollectionRun:
    source = session.scalar(
        select(Source).where(Source.source_key == source_key).with_for_update()
    )
    if source is None:
        raise AdminOperationError("Source not found.")
    if not source.enabled:
        raise AdminOperationError("Source is disabled.")
    if source_key not in SUPPORTED_SOURCE_IDS:
        raise AdminOperationError("No approved collector is registered for this source.")

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

    return start_run(session, source.id)
