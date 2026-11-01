import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.auth import get_admin_session, require_csrf
from backend.app.api.dependencies import get_session
from backend.app.api.schemas import CollectionRequest, PageMetadata
from backend.app.api.services.admin_reads import get_run, list_runs
from backend.app.api.services.admin_writes import AdminOperationError, create_collection_run
from backend.app.core.admin_config import AdminConfig, get_admin_config
from backend.app.db.models import AdminSession
from backend.app.workers.agent_worker import JobLease, execute_owned_job

router = APIRouter(
    prefix="/collections",
    tags=["collections"],
    dependencies=[Depends(get_admin_session)],
)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_collection(
    payload: CollectionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    admin_session: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    source_key = payload.source_id
    config: AdminConfig = get_admin_config()
    require_csrf(
        request,
        request.headers.get("x-csrf-token"),
        admin_session,
        config,
    )
    try:
        run, job = create_collection_run(session, source_key)
        run_id = run.id
        lease = JobLease(
            job_id=job.id,
            run_id=run.id,
            source_id=job.source_id,
            source_key=source_key,
            worker_id=job.worker_id or "",
            generation=job.lease_generation,
        )
        session.commit()
        factory: sessionmaker[Session] = request.app.state.session_factory
        background_tasks.add_task(execute_owned_job, factory, lease)
    except AdminOperationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail="Collection could not be scheduled.",
        ) from None
    return {"run_id": str(run_id), "status": "running"}


@router.get("")
def collection_runs(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    page: int = 1,
    page_size: int = 20,
    source_id: str | None = None,
    state: Literal["running", "completed", "failed"] | None = None,
) -> dict[str, object]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    items, total = list_runs(session, page, page_size, source_id, state)
    return {
        "items": [item.model_dump() for item in items],
        "pagination": PageMetadata(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    }


@router.get("/{run_id}")
def collection_run_detail(
    run_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    result = get_run(session, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Collection run not found.")
    return result.model_dump()
