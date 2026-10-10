from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.api.deps import SessionDep
from app.core.config import settings
from app.schemas.system import SystemInfo
from app.services import settings_service

router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "/info",
    response_model=SystemInfo,
    summary="Thông tin hệ thống cho trang quản trị",
    description=(
        "Config vận hành không nhạy cảm: version, environment, rate limit, "
        "thời hạn thùng rác, CORS origins. Yêu cầu X-API-Key như mọi "
        "endpoint khác dưới /api/v1 — không trả bất kỳ secret nào."
    ),
)
async def get_system_info(session: SessionDep) -> SystemInfo:
    tz = await settings_service.get_display_timezone(session)
    return SystemInfo(
        app_name=settings.app_name,
        version=__version__,
        environment=settings.environment,
        display_timezone=tz.timezone,
        display_timezone_default=settings.display_timezone,
        trash_retention_days=settings.trash_retention_days,
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_requests_per_minute=settings.rate_limit_requests_per_minute,
        cors_origins=settings.cors_origins,
    )
