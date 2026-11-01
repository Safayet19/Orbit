import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.auth import get_admin_session
from backend.app.api.dependencies import get_session
from backend.app.collectors.worldbank import WorldBankInflationCollector
from backend.app.core.admin_config import AdminConfig, get_admin_config
from backend.app.core.config import EXPECTED_DATABASE
from backend.app.db.models import AdminSession
from backend.app.schemas.records import WORLD_BANK_SOURCE_ID

router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(get_admin_session)],
)


@router.get("")
def system_information(
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[AdminSession, Depends(get_admin_session)],
) -> dict[str, object]:
    checked_at = datetime.now(timezone.utc)
    try:
        database_name = session.scalar(text("SELECT current_database()"))
        tls_active = bool(
            session.connection().connection.driver_connection.pgconn.ssl_in_use
        )
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connectivity check failed.",
        ) from None
    if database_name != EXPECTED_DATABASE:
        raise HTTPException(
            status_code=503,
            detail="Database target is not the expected application database.",
        )
    config: AdminConfig = get_admin_config()
    return {
        "application": "Orbit",
        "version": "0.1.0",
        "environment": config.environment,
        "api_status": "healthy",
        "database": {
            "status": "connected",
            "provider": "Neon PostgreSQL",
            "name": EXPECTED_DATABASE,
            "tls_active": tls_active,
            "checked_at": checked_at,
        },
        "collectors": [
            {
                "source_id": WORLD_BANK_SOURCE_ID,
                "name": "World Bank Bangladesh Inflation",
                "category": WorldBankInflationCollector.category,
            }
        ],
        "scheduling": {"configured": False, "status": "Not configured"},
    }
