"""Đăng nhập: Google (web gửi claim đã xác minh) và tài khoản nội bộ (mật khẩu).

Invite-only: không có tự đăng ký. Google: khoá định danh là `google_sub`; email chỉ dùng MỘT lần
để khớp lời mời. Mật khẩu: core tự so argon2id rồi web ký JWT như với Google. Thông báo lỗi trả
client chung chung (không cho biết email/tên đăng nhập có trong hệ thống hay không); lý do thật
chỉ nằm ở `audit_log` cho admin.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import passwords
from app.core.config import settings
from app.models.enums import AuditAction, AuthProvider, UserStatus
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResult, PasswordLoginRequest
from app.services import audit_service, user_service
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
# Chỉ ở audit: email Google trùng tài khoản nội bộ. Client vẫn nhận `account_mismatch`.
PROVIDER_LOCAL = "provider_local"
PASSWORD_LOGIN_DISABLED = "password_login_disabled"  # noqa: S105 - mã lỗi, không phải mật khẩu
INVALID_CREDENTIALS = "invalid_credentials"


async def _deny(
    session: AsyncSession,
    req: LoginRequest,
    email: str,
    reason: str,
    user: User | None = None,
    *,
    code: str | None = None,
    extra: dict[str, str] | None = None,
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
        details={"reason": reason, "email": email, **(extra or {})},
    )
    await session.commit()
    logger.info("đăng nhập bị từ chối reason=%s", reason)
    # Thông báo chung: không cho biết email có được mời hay không.
    return ForbiddenError("Tài khoản này chưa được cấp quyền truy cập", code=code or reason)


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
        if user.auth_provider is AuthProvider.LOCAL:
            # BẮT BUỘC: nếu không, Google sẽ gắn `google_sub` vào tài khoản nội bộ trùng email
            # và chiếm nó. Client chỉ thấy account_mismatch; audit ghi rõ provider.
            raise await _deny(
                session,
                req,
                email,
                PROVIDER_LOCAL,
                user,
                code=ACCOUNT_MISMATCH,
                extra={"provider": "local"},
            )
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


# ═══════════════════════════════════════════════════════════════════════
#  Đăng nhập bằng mật khẩu (tài khoản nội bộ)
# ═══════════════════════════════════════════════════════════════════════


async def _deny_password(
    session: AsyncSession,
    req: PasswordLoginRequest,
    reason: str,
    user: User | None,
    *,
    locked_now: bool = False,
) -> ForbiddenError:
    """Ghi `login_denied` (và `login_locked` nếu vừa khoá) rồi COMMIT, trả lỗi chung để `raise`.

    COMMIT ở đây vì handler sắp ném lỗi, `get_session` sẽ rollback và bộ đếm sai + nhật ký sẽ
    mất; không có chúng thì khoá 5 lần sai vô hiệu. Mọi lý do đều ra cùng một thông báo và mã.

    `identifier` KHÔNG vào audit: identifier gõ sai thường là mật khẩu gõ nhầm ô. Chỉ ghi
    16 ký tự đầu sha256 khi không khớp user nào; khớp thì có `target_id`.
    """
    details: dict[str, str] = {"reason": reason, "method": "password"}
    if user is None:
        digest = hashlib.sha256(req.identifier.strip().lower().encode("utf-8", "replace"))
        details["identifier_sha256"] = digest.hexdigest()[:16]
    audit_service.record(
        session,
        AuditAction.LOGIN_DENIED,
        actor_user_id=user.id if user else None,
        target_type="user" if user else None,
        target_id=user.id if user else None,
        client_ip=req.client_ip,
        details=details,
    )
    if locked_now and user is not None:
        audit_service.record(
            session,
            AuditAction.LOGIN_LOCKED,
            actor_user_id=user.id,
            target_type="user",
            target_id=user.id,
            client_ip=req.client_ip,
            details={
                "failed_attempts": passwords.MAX_FAILED_LOGINS,
                "minutes": int(passwords.LOCK_DURATION.total_seconds() // 60),
            },
        )
    await session.commit()
    logger.info("đăng nhập mật khẩu bị từ chối reason=%s", reason)
    return ForbiddenError(
        "Sai thông tin đăng nhập hoặc tài khoản tạm bị khoá", code=INVALID_CREDENTIALS
    )


async def login_password(session: AsyncSession, req: PasswordLoginRequest) -> LoginResult:
    """Xác thực identifier + mật khẩu của tài khoản nội bộ, trong MỘT transaction.

    Thứ tự CỐ ĐỊNH (spec 3.4): tìm user -> verify (LUÔN đúng một lần, hash giả nếu không có
    user) -> khoá -> status -> hạn mật khẩu tạm. Kiểm status/khoá SAU verify để kẻ đoán không
    phân biệt được "đang khoá/disabled" với "sai mật khẩu" qua thời gian hay thông báo.

    Raises:
        ForbiddenError: 403 `password_login_disabled` (công tắc), hoặc 403
            `invalid_credentials` cho MỌI thất bại khác (không có user, không phải `local`, sai
            mật khẩu, đang khoá, disabled, mật khẩu tạm quá 72 giờ).
    """
    if not settings.password_login_enabled:
        raise ForbiddenError("Đăng nhập bằng mật khẩu đang tắt", code=PASSWORD_LOGIN_DISABLED)

    user = await user_service.find_local_by_identifier(session, req.identifier)
    result = await passwords.verify_password(
        user.password_hash if user else None, req.password.get_secret_value()
    )
    now = now_utc()

    if user is None:
        raise await _deny_password(session, req, "unknown_identifier", None)
    if user.locked_until is not None and user.locked_until > now:
        # Đang khoá: KHÔNG đếm thêm, nếu không kẻ đoán gia hạn khoá mãi mãi.
        raise await _deny_password(session, req, "locked", user)
    if not result.ok:
        user.failed_login_count += 1
        locked_now = user.failed_login_count >= passwords.MAX_FAILED_LOGINS
        if locked_now:
            user.locked_until = now + passwords.LOCK_DURATION
            user.failed_login_count = 0
        raise await _deny_password(session, req, "wrong_password", user, locked_now=locked_now)
    if user.status is not UserStatus.ACTIVE:
        raise await _deny_password(session, req, "disabled", user)
    if passwords.temporary_password_expired(
        user.must_change_password, user.password_changed_at, now
    ):
        raise await _deny_password(session, req, "temp_password_expired", user)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if result.needs_rehash:
        # Tham số băm đã được nâng: băm lại bằng mật khẩu vừa xác minh, cùng transaction.
        user.password_hash = await passwords.hash_password(req.password.get_secret_value())
    audit_service.record(
        session,
        AuditAction.LOGIN_SUCCESS,
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        client_ip=req.client_ip,
        details={"method": "password"},
    )
    await session.flush()
    return LoginResult(user_id=user.id, role=user.role, session_version=user.session_version)
