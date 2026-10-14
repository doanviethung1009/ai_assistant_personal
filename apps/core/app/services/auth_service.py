"""Đăng nhập: web gửi claim Google đã xác minh, core quyết định cho vào hay không.

Invite-only: không có tự đăng ký. Khoá định danh là `google_sub`; email chỉ dùng MỘT lần để khớp
lời mời. Thông báo lỗi trả client chung chung (không cho biết email có trong hệ thống hay
không); lý do thật chỉ nằm ở `audit_log` cho admin.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import AuditAction, UserStatus
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResult
from app.services import audit_service
from app.services.clock import now_utc
from app.services.errors import ForbiddenError, ValidationError
from app.services.user_service import normalize_email

logger = logging.getLogger(__name__)

# Mã lý do từ chối. Phần lớn client chỉ thấy `code`, không thấy lý do chi tiết.
NOT_INVITED = "not_invited"
DISABLED = "disabled"
EMAIL_UNVERIFIED = "email_unverified"
HD_NOT_ALLOWED = "hd_not_allowed"
ACCOUNT_MISMATCH = "account_mismatch"


async def _deny(
    session: AsyncSession, req: LoginRequest, email: str, reason: str, user: User | None = None
) -> ForbiddenError:
    """Ghi `login_denied` rồi trả lỗi để người gọi `raise`.

    COMMIT ngay tại đây: handler sắp ném lỗi nên dependency `get_session` sẽ ROLLBACK, và dòng
    nhật ký từ chối (thứ admin cần thấy nhất) sẽ mất nếu không commit trước.
    """
    audit_service.record(
        session,
        AuditAction.LOGIN_DENIED,
        actor_user_id=user.id if user else None,
        target_type="user" if user else None,
        target_id=user.id if user else None,
        client_ip=req.client_ip,
        details={"reason": reason, "email": email},
    )
    await session.commit()
    logger.info("đăng nhập bị từ chối reason=%s", reason)
    # Thông báo chung: không cho biết email có được mời hay không.
    return ForbiddenError("Tài khoản này chưa được cấp quyền truy cập", code=reason)


async def login(session: AsyncSession, req: LoginRequest) -> LoginResult:
    """Xác thực claim đã xác minh và kích hoạt/cập nhật user, trong MỘT transaction.

    Raises:
        ForbiddenError: 403 với `code` ∈ {not_invited, disabled, email_unverified,
            hd_not_allowed, account_mismatch}.
    """
    try:
        email = normalize_email(req.email)
    except ValidationError:
        # Email dị dạng không thể khớp lời mời nào.
        raise await _deny(session, req, req.email.strip().lower()[:320], NOT_INVITED) from None

    if not req.email_verified:
        raise await _deny(session, req, email, EMAIL_UNVERIFIED)

    allowed_hd = settings.google_allowed_hd
    if allowed_hd and (req.hd or "").strip().lower() not in allowed_hd:
        raise await _deny(session, req, email, HD_NOT_ALLOWED)

    # Khoá dòng theo thứ tự: sub trước, email sau. Hai lần đăng nhập đầu của cùng một người
    # (mở hai tab) bị tuần tự hoá, không thể cùng đi vào nhánh "gắn sub".
    by_sub = (
        (
            await session.execute(
                select(User).where(User.google_sub == req.google_sub).with_for_update()
            )
        )
        .scalars()
        .unique()
        .one_or_none()
    )

    if by_sub is not None:
        user = by_sub
        if user.status is UserStatus.DISABLED:
            raise await _deny(session, req, email, DISABLED, user)
        if user.email != email:
            # Google đổi email của tài khoản này: theo sub, nhưng không được trùng user khác.
            clash = await session.scalar(select(User.id).where(User.email == email))
            if clash is not None:
                raise await _deny(session, req, email, ACCOUNT_MISMATCH, user)
            user.email = email
    else:
        by_email = (
            (await session.execute(select(User).where(User.email == email).with_for_update()))
            .scalars()
            .unique()
            .one_or_none()
        )
        if by_email is None:
            raise await _deny(session, req, email, NOT_INVITED)
        user = by_email
        if user.google_sub is not None and user.google_sub != req.google_sub:
            # Email này đã gắn với MỘT tài khoản Google khác: không cho chiếm lời mời.
            raise await _deny(session, req, email, ACCOUNT_MISMATCH, user)
        if user.status is UserStatus.DISABLED:
            raise await _deny(session, req, email, DISABLED, user)
        user.google_sub = req.google_sub

    user.status = UserStatus.ACTIVE
    user.last_login_at = now_utc()
    if req.name and req.name.strip():
        user.name = req.name.strip()[:200]

    audit_service.record(
        session,
        AuditAction.LOGIN_SUCCESS,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        client_ip=req.client_ip,
    )
    await session.flush()
    return LoginResult(user_id=user.id, role=user.role, session_version=user.session_version)
