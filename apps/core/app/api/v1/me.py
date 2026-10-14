"""Hồ sơ của người đang đăng nhập."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUserDep, SessionDep
from app.core.rate_limit import enforce_password_change_limit
from app.models.enums import AliasSource, UserStatus
from app.schemas.auth import PasswordChange, PasswordChanged
from app.schemas.user import AliasRead, MeRead
from app.services import clock, user_service

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
        auth_provider=user.auth_provider,
        username=user.username,
        must_change_password=user.must_change_password,
    )


@router.post(
    "/me/password",
    response_model=PasswordChanged,
    summary="Tự đổi mật khẩu (tài khoản nội bộ)",
    description=(
        "Được phép cả khi đang bị ép đổi mật khẩu. Thành công thì `session_version` tăng: mọi "
        "thiết bị khác bị đăng xuất. Sai mật khẩu hiện tại là 422 `current_password_invalid` "
        "(không phải 401, vì web coi 401 là hết phiên). 409 `not_local_account` với tài khoản "
        "Google; 422 `weak_password`; 429 sau 5 lần/15 phút."
    ),
)
async def change_password(
    request: Request, session: SessionDep, user: CurrentUserDep, payload: PasswordChange
) -> PasswordChanged:
    await enforce_password_change_limit(user.id)
    version = await user_service.change_own_password(
        session,
        user.id,
        payload.current_password.get_secret_value(),
        payload.new_password.get_secret_value(),
        client_ip=request.client.host if request.client else None,
    )
    return PasswordChanged(session_version=version)
