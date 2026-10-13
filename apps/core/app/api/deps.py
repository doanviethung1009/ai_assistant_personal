from __future__ import annotations

from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, CurrentUserDep, current_user, require_permission
from app.core.config import settings
from app.core.permissions import Permission
from app.core.security import require_api_key
from app.db.session import get_session
from app.services import clock

__all__ = [
    "ApiKeyDep",
    "CurrentUser",
    "CurrentUserDep",
    "Permission",
    "SessionDep",
    "bind_display_tz",
    "current_user",
    "require_permission",
]

# scope="function": phần sau yield của get_session (commit) phải chạy TRƯỚC khi response được
# gửi. Mặc định (scope="request", FastAPI >= 0.118) nó chạy SAU khi gửi, nên client nhận 2xx
# khi transaction chưa commit và request kế tiếp đọc dữ liệu cũ. Đổi lại: không được dùng
# session trong BackgroundTasks hay response streaming (session đã đóng lúc đó).
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
ApiKeyDep = Annotated[str, Depends(require_api_key)]


async def bind_display_tz(user: CurrentUserDep) -> None:
    """Gắn múi giờ hiệu lực cho request: múi giờ của user, không có thì mặc định env.

    PHẢI là `async def`: dependency đồng bộ chạy trong threadpool nên ContextVar đặt ở đó
    không truyền về task của request. Không chạm DB: `current_user` đã đọc `users.timezone`.
    Múi giờ lưu hỏng (sửa tay DB) thì rơi về env thay vì làm vỡ request.
    """
    try:
        tz = ZoneInfo(user.timezone or settings.display_timezone)
    except (KeyError, ValueError, OSError, ImportError):
        # ZoneInfoNotFoundError là KeyError; thiếu gói tzdata cho tên lạ ném ModuleNotFoundError.
        tz = ZoneInfo(settings.display_timezone)
    clock.set_request_tz(tz)
