"""Đăng nhập. Web gọi lúc callback Google; KHÔNG cần JWT (chưa có), chỉ cần `X-API-Key`."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import SessionDep
from app.core.rate_limit import enforce_login_limits
from app.schemas.auth import LoginRequest, LoginResult
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
