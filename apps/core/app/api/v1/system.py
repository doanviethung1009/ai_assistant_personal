from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import require_permission
from app.core.config import settings
from app.core.permissions import Permission
from app.schemas.system import SystemInfo
from app.services import clock

router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "/info",
    response_model=SystemInfo,
    dependencies=[Depends(require_permission(Permission.SYSTEM_READ))],
    summary="Thông tin hệ thống cho trang quản trị",
    description=(
        "Config vận hành không nhạy cảm: version, environment, rate limit, "
        "thời hạn thùng rác, CORS origins. Yêu cầu X-API-Key và quyền `system:read` "
        "(admin) — không trả bất kỳ secret nào."
    ),
)
async def get_system_info() -> SystemInfo:
    return SystemInfo(
        app_name=settings.app_name,
        version=__version__,
        environment=settings.environment,
        display_timezone=clock.display_tz().key,
        trash_retention_days=settings.trash_retention_days,
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_requests_per_minute=settings.rate_limit_requests_per_minute,
        cors_origins=settings.cors_origins,
    )
