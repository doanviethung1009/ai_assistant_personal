"""Quản trị người dùng và nhật ký. Mọi route cần permission `user:manage` (chỉ admin).

Router này nằm trong `active_router` (api/v1/router.py) nên cũng bị chặn khi chính admin còn
phải đổi mật khẩu. Logic nằm ở `user_service`/`audit_service`; file này chỉ dịch HTTP.

Route tĩnh (`/users/local`, `/audit-log`) khai báo TRƯỚC `/users/{user_id}`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import CurrentUserDep, SessionDep, require_permission
from app.core.config import settings
from app.core.permissions import Permission
from app.models.enums import AuditAction, AuthProvider, UserRole, UserStatus
from app.models.user import User
from app.schemas.admin import (
    AliasesSet,
    AuditRead,
    GoogleUserInvite,
    LocalUserCreate,
    LocalUserCreated,
    TemporaryPassword,
    UserAdminRead,
    UserAdminUpdate,
)
from app.schemas.common import Page
from app.schemas.user import AliasRead
from app.services import audit_service, user_service

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_permission(Permission.USER_MANAGE))],
)

# Mật khẩu tạm trong body: không proxy hay trình duyệt nào được lưu cache.
_NO_STORE = "no-store"


def _read(user: User) -> UserAdminRead:
    """Dựng `UserAdminRead` thủ công: chủ ý KHÔNG dùng `from_attributes` để `password_hash` không
    thể lọt vào response dù ai đó thêm trường vào schema sau này."""
    return UserAdminRead(
        id=user.id,
        email=user.email,
        username=user.username,
        name=user.name,
        role=user.role,
        status=user.status,
        auth_provider=user.auth_provider,
        must_change_password=user.must_change_password,
        locked_until=user.locked_until,
        failed_login_count=user.failed_login_count,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        invited_by=user.invited_by,
        aliases=[AliasRead(source=a.source, alias=a.alias) for a in user.aliases],
        is_env_admin=user.email in settings.admin_emails,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Người dùng
# ═══════════════════════════════════════════════════════════════════════


@router.get("/users", response_model=Page[UserAdminRead], summary="Danh sách người dùng")
async def list_users(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    role: UserRole | None = None,
    status: UserStatus | None = None,
    auth_provider: AuthProvider | None = None,
    locked: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> Page[UserAdminRead]:
    users, total = await user_service.list_users(
        session,
        q=q,
        role=role,
        status=status,
        auth_provider=auth_provider,
        locked=locked,
        limit=limit,
        offset=offset,
    )
    return Page[UserAdminRead](
        items=[_read(u) for u in users], total=total, limit=limit, offset=offset
    )


@router.post(
    "/users",
    response_model=UserAdminRead,
    status_code=201,
    summary="Mời một email Google (trạng thái invited)",
)
async def invite_google_user(
    session: SessionDep, admin: CurrentUserDep, payload: GoogleUserInvite
) -> UserAdminRead:
    user = await user_service.invite_user(
        session, payload.email, payload.role, name=payload.name, actor_user_id=admin.id
    )
    return _read(await user_service.get_user_fresh(session, user.id))


@router.post(
    "/users/local",
    response_model=LocalUserCreated,
    status_code=201,
    summary="Tạo tài khoản nội bộ kèm mật khẩu tạm (hiện MỘT lần)",
    description=(
        "Trả `temporary_password` đúng một lần, header `Cache-Control: no-store`. Người dùng "
        "phải đổi mật khẩu ở lần đăng nhập đầu; mật khẩu tạm hết hạn sau 72 giờ."
    ),
)
async def create_local_user(
    session: SessionDep, admin: CurrentUserDep, payload: LocalUserCreate, response: Response
) -> LocalUserCreated:
    user, temporary = await user_service.create_local_user(
        session,
        username=payload.username,
        email=payload.email,
        name=payload.name,
        role=payload.role,
        actor_user_id=admin.id,
    )
    response.headers["Cache-Control"] = _NO_STORE
    return LocalUserCreated(
        user=_read(await user_service.get_user_fresh(session, user.id)),
        temporary_password=temporary,
    )


@router.get("/users/{user_id}", response_model=UserAdminRead, summary="Chi tiết một người dùng")
async def get_user(session: SessionDep, user_id: uuid.UUID) -> UserAdminRead:
    return _read(await user_service.get_user_fresh(session, user_id))


@router.patch(
    "/users/{user_id}",
    response_model=UserAdminRead,
    summary="Đổi role, trạng thái, tên, email hoặc tên đăng nhập",
    description=(
        "409: `self_lockout` (tự hạ role/tự khoá), `last_admin`, `env_admin` (email thuộc "
        "ADMIN_EMAILS), `email_exists`, `username_exists`, `not_local_account` (sửa email hoặc "
        "tên đăng nhập của tài khoản Google). `status=active` cho tài khoản Google chưa gắn "
        "`google_sub` được lưu thành `invited`."
    ),
)
async def update_user(
    session: SessionDep, admin: CurrentUserDep, user_id: uuid.UUID, payload: UserAdminUpdate
) -> UserAdminRead:
    changes = payload.model_dump(exclude_unset=True)
    await user_service.update_user(session, user_id, changes, actor_user_id=admin.id)
    return _read(await user_service.get_user_fresh(session, user_id))


@router.post(
    "/users/{user_id}/reset-password",
    response_model=TemporaryPassword,
    summary="Đặt lại mật khẩu tài khoản nội bộ (mật khẩu tạm hiện MỘT lần)",
    description=(
        "Thu hồi mọi phiên của người đó và ép đổi mật khẩu. 409 `not_local_account` (tài khoản "
        "Google), `self_action` (tự đặt lại: dùng `/me/password`)."
    ),
)
async def reset_password(
    session: SessionDep, admin: CurrentUserDep, user_id: uuid.UUID, response: Response
) -> TemporaryPassword:
    _, temporary = await user_service.reset_password(session, user_id, actor_user_id=admin.id)
    response.headers["Cache-Control"] = _NO_STORE
    return TemporaryPassword(temporary_password=temporary)


@router.post(
    "/users/{user_id}/unlock",
    status_code=204,
    response_class=Response,
    summary="Mở khoá đăng nhập tạm (xoá bộ đếm sai và thời hạn khoá)",
)
async def unlock_user(session: SessionDep, admin: CurrentUserDep, user_id: uuid.UUID) -> Response:
    await user_service.unlock(session, user_id, actor_user_id=admin.id)
    return Response(status_code=204)


@router.post(
    "/users/{user_id}/revoke-sessions",
    status_code=204,
    response_class=Response,
    summary="Đăng xuất mọi thiết bị của người dùng",
)
async def revoke_user_sessions(
    session: SessionDep, admin: CurrentUserDep, user_id: uuid.UUID
) -> Response:
    await user_service.revoke_sessions(session, user_id, actor_user_id=admin.id)
    return Response(status_code=204)


@router.put(
    "/users/{user_id}/aliases",
    response_model=UserAdminRead,
    summary="Thay toàn bộ alias Jira của người dùng",
    description="409 `alias_taken` khi một tên đang thuộc user khác (detail có email người giữ).",
)
async def set_user_aliases(
    session: SessionDep, admin: CurrentUserDep, user_id: uuid.UUID, payload: AliasesSet
) -> UserAdminRead:
    await user_service.replace_aliases(
        session, user_id, [item.alias for item in payload.aliases], actor_user_id=admin.id
    )
    return _read(await user_service.get_user_fresh(session, user_id))


@router.delete(
    "/users/{user_id}",
    status_code=204,
    response_class=Response,
    summary="Xoá cứng user chưa có dữ liệu",
    description=(
        "409: `has_data` (còn task/note, kể cả trong thùng rác: hãy khoá thay vì xoá), "
        "`self_lockout`, `last_admin`, `env_admin`."
    ),
)
async def delete_user(session: SessionDep, admin: CurrentUserDep, user_id: uuid.UUID) -> Response:
    await user_service.delete_user(session, user_id, actor_user_id=admin.id)
    return Response(status_code=204)


# ═══════════════════════════════════════════════════════════════════════
#  Nhật ký
# ═══════════════════════════════════════════════════════════════════════


@router.get("/audit-log", response_model=Page[AuditRead], summary="Nhật ký, mới nhất trước")
async def list_audit_log(
    session: SessionDep,
    action: AuditAction | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> Page[AuditRead]:
    entries, total = await audit_service.list_entries(
        session,
        action=action,
        actor_user_id=actor_user_id,
        target_id=target_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    items = [
        AuditRead(
            id=row.id,
            created_at=row.created_at,
            action=row.action,
            actor_user_id=row.actor_user_id,
            actor_email=actor_email,
            target_type=row.target_type,
            target_id=row.target_id,
            target_email=target_email,
            client_ip=row.client_ip,
            details=row.details,
        )
        for row, actor_email, target_email in entries
    ]
    return Page[AuditRead](items=items, total=total, limit=limit, offset=offset)
