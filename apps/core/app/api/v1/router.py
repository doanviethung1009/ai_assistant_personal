from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import bind_display_tz
from app.api.v1 import (
    imports,
    integrations,
    notes,
    projects,
    settings,
    system,
    tasks,
)
from app.core.security import require_api_key

# Mọi endpoint dưới /api/v1 đều yêu cầu API key. Health nằm ngoài prefix này
# để probe của Prometheus gọi được mà không cần khoá.
api_router = APIRouter(
    prefix="/api/v1", dependencies=[Depends(require_api_key), Depends(bind_display_tz)]
)
api_router.include_router(tasks.router)
api_router.include_router(projects.router)
api_router.include_router(notes.router)
api_router.include_router(system.router)
api_router.include_router(imports.router)
api_router.include_router(settings.router)
api_router.include_router(integrations.router)
