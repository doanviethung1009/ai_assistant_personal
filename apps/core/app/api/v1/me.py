"""Hồ sơ của người đang đăng nhập và múi giờ riêng."""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep, bind_display_tz
from app.models.enums import AliasSource, UserStatus
from app.schemas.settings import DisplayTimezoneBody
from app.schemas.user import AliasRead, MeRead
from app.services import clock, user_service

router = APIRouter(tags=["me"])


def _me(user: CurrentUserDep, timezone: str | None) -> MeRead:
    # `current_user` chỉ trả user ACTIVE nên status luôn là active ở đây.
    return MeRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        status=UserStatus.ACTIVE,
        timezone=timezone,
        effective_timezone=clock.display_tz().key,
        aliases=[AliasRead(source=AliasSource.JIRA, alias=a) for a in sorted(user.aliases)],
        permissions=sorted(user.permissions),
    )


@router.get("/me", response_model=MeRead, summary="Hồ sơ và quyền của tôi")
async def get_me(user: CurrentUserDep) -> MeRead:
    return _me(user, user.timezone)


@router.put(
    "/me/timezone",
    response_model=MeRead,
    summary="Đặt múi giờ hiển thị của tôi",
    description="Tên IANA (vd Asia/Ho_Chi_Minh). `timezone = null` về mặc định của hệ thống.",
)
async def put_my_timezone(
    session: SessionDep, user: CurrentUserDep, body: DisplayTimezoneBody
) -> MeRead:
    updated = await user_service.set_timezone(session, user.id, body.timezone)
    # Phản hồi của chính request này cũng phải dùng múi giờ mới.
    await bind_display_tz(replace(user, timezone=updated.timezone))
    return _me(user, updated.timezone)
