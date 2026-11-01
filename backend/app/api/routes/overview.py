from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.auth import get_admin_session
from backend.app.api.dependencies import get_session
from backend.app.api.schemas import OverviewResponse
from backend.app.api.services.admin_reads import get_overview
from backend.app.db.models import AdminSession

router = APIRouter(
    prefix="/overview",
    tags=["overview"],
    dependencies=[Depends(get_admin_session)],
)


@router.get("", response_model=OverviewResponse)
def overview(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
    period: Annotated[int, Query(ge=7, le=90)] = 30,
) -> OverviewResponse:
    if period not in {7, 30, 90}:
        raise HTTPException(status_code=422, detail="Period must be 7, 30, or 90 days.")
    return get_overview(session, period)
