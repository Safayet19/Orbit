import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from backend.app.api.router import router as api_router
from backend.app.core.logging import configure_logging
from backend.app.db.session import create_database_engine, create_session_factory

LOGGER = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    configured = os.environ.get(
        "ADMIN_ALLOWED_ORIGINS",
        "http://localhost:5173",
    )
    return [
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip()
    ]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    engine = create_database_engine()
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="Orbit Admin API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def prevent_admin_caching(
    request: Request,
    call_next: Any,
) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(Exception)
async def sanitized_internal_error(
    request: Request,
    error: Exception,
) -> JSONResponse:
    LOGGER.error(
        "api_internal_error path=%s error_type=%s",
        request.url.path,
        type(error).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "orbit-admin-api"}


app.include_router(api_router)
