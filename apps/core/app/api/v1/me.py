"""Hồ sơ của người đang đăng nhập."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.models.enums import AliasSource, UserStatus
from app.schemas.user import AliasRead, MeRead
from app.services import clock

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeRead, summary="Hồ sơ và quyền của tôi")
async def get_me(user: CurrentUserDep) -> MeRead:
    # `current_user` chỉ trả user ACTIVE nên status luôn là active ở đây.
    return MeRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        status=UserStatus.ACTIVE,
        effective_timezone=clock.display_tz().key,
        aliases=[AliasRead(source=AliasSource.JIRA, alias=a) for a in sorted(user.aliases)],
        permissions=sorted(user.permissions),
    )
