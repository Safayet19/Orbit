from fastapi import APIRouter

from backend.app.api.auth import router as auth_router
from backend.app.api.routes.collections import router as collections_router
from backend.app.api.routes.overview import router as overview_router
from backend.app.api.routes.quality import router as quality_router
from backend.app.api.routes.records import history_router, router as records_router
from backend.app.api.routes.sources import router as sources_router
from backend.app.api.routes.system import router as system_router

router = APIRouter()
router.include_router(auth_router)
admin_router = APIRouter(prefix="/api/admin")
admin_router.include_router(overview_router)
admin_router.include_router(sources_router)
admin_router.include_router(collections_router)
admin_router.include_router(records_router)
admin_router.include_router(history_router)
admin_router.include_router(quality_router)
admin_router.include_router(system_router)
router.include_router(admin_router)
