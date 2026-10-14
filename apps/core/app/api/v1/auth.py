"""Đăng nhập. Web gọi lúc callback Google hoặc submit form mật khẩu; KHÔNG cần JWT (chưa có),
chỉ cần `X-API-Key`."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import SessionDep
from app.core.rate_limit import enforce_login_limits, enforce_password_login_limits
from app.schemas.auth import LoginRequest, LoginResult, PasswordLoginRequest
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginResult,
    summary="Web chuyển claim Google đã xác minh để đăng nhập (invite-only)",
    description=(
        "Chỉ tin được khi đi cùng `X-API-Key` của web. 403 với `code` ∈ {not_invited, "
        "disabled, email_unverified, hd_not_allowed, account_mismatch}; thông báo chung, "
        "lý do thật nằm ở audit_log. 429 khi vượt giới hạn đăng nhập."
    ),
)
async def login(request: Request, session: SessionDep, payload: LoginRequest) -> LoginResult:
    # IP browser do web chuyển (Caddy ghi đè X-Forwarded-For); thiếu thì dùng IP kết nối.
    fallback = request.client.host if request.client else None
    await enforce_login_limits(payload.client_ip or fallback)
    return await auth_service.login(session, payload)


@router.post(
    "/login/password",
    response_model=LoginResult,
    summary="Đăng nhập tài khoản nội bộ bằng tên đăng nhập hoặc email + mật khẩu",
    description=(
        "Chỉ API key (web gọi từ Server Action). 200 trả `LoginResult` như `/auth/login`, web ký "
        "JWT. Mọi thất bại (không có tài khoản, sai mật khẩu, đang khoá, bị khoá, mật khẩu tạm hết "
        "hạn) đều 403 `invalid_credentials` cùng một thông báo. 403 `password_login_disabled` khi "
        "công tắc PASSWORD_LOGIN_ENABLED=false; 429 khi vượt giới hạn."
    ),
)
async def login_password(
    request: Request, session: SessionDep, payload: PasswordLoginRequest
) -> LoginResult:
    fallback = request.client.host if request.client else None
    await enforce_password_login_limits(payload.client_ip or fallback, payload.identifier)
    return await auth_service.login_password(session, payload)
