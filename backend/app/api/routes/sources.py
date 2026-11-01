from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from backend.app.api.auth import get_admin_session, require_csrf
from backend.app.api.dependencies import get_session
from backend.app.api.schemas import SourceEnabledRequest
from backend.app.api.services.admin_reads import get_source_detail, list_sources
from backend.app.api.services.admin_writes import AdminOperationError, update_source_enabled
from backend.app.core.admin_config import AdminConfig, get_admin_config
from backend.app.db.models import AdminSession

router = APIRouter(
    prefix="/sources",
    tags=["sources"],
    dependencies=[Depends(get_admin_session)],
)


@router.get("")
def sources(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    search: str | None = None,
    category: str | None = None,
    state: Literal["enabled", "disabled"] | None = None,
    sort_by: Literal["name", "category", "last_collection_at"] = "name",
    sort_order: Literal["asc", "desc"] = "asc",
) -> dict[str, object]:
    result = list_sources(session)
    if search:
        folded_search = search.casefold()[:120]
        result = [
            source
            for source in result
            if folded_search in source.name.casefold()
            or folded_search in source.source_key.casefold()
        ]
    if category:
        result = [source for source in result if source.category == category]
    if state:
        enabled = state == "enabled"
        result = [source for source in result if source.enabled is enabled]
    result.sort(
        key=lambda source: (
            getattr(source, sort_by) is None,
            getattr(source, sort_by) or "",
        ),
        reverse=sort_order == "desc",
    )
    return {"items": [source.model_dump() for source in result], "total": len(result)}


@router.get("/{source_key}")
def source_detail(
    source_key: str,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    result = get_source_detail(session, source_key)
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return result


@router.patch("/{source_key}/enabled", status_code=status.HTTP_200_OK)
def set_source_enabled(
    source_key: str,
    payload: SourceEnabledRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_session: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    config: AdminConfig = get_admin_config()
    require_csrf(
        request,
        request.headers.get("x-csrf-token"),
        admin_session,
        config,
    )
    try:
        source = update_source_enabled(session, source_key, payload.enabled)
        session.commit()
        return {
            "source_key": source.source_key,
            "enabled": source.enabled,
            "message": "Source settings updated.",
        }
    except AdminOperationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
