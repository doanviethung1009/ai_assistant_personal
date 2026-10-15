"""Người dùng (đăng nhập Google hoặc tài khoản nội bộ bằng mật khẩu) và alias của họ.

Core là nơi QUYẾT ĐỊNH quyền. Tài khoản `google`: web xác thực với Google rồi chuyển claim đã
xác minh cho `POST /auth/login`; không lưu access_token, refresh_token, id_token hay ảnh đại
diện, chỉ giữ `google_sub` (khoá định danh ổn định), email và tên. Tài khoản `local`: admin tạo,
core giữ hash argon2id và tự so mật khẩu (`POST /auth/login/password`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import AliasSource, AuthProvider, UserRole, UserStatus


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Một tài khoản. Tạo bởi admin/CLI/`ADMIN_EMAILS`, không có tự đăng ký.

    `session_version` tăng lên để thu hồi mọi phiên đang chạy: JWT web->core mang `sv` và core
    so với giá trị này ở MỌI request, nên có hiệu lực ngay, không phải chờ cookie hết hạn.
    """

    __tablename__ = "users"

    # Luôn lower(strip) trước khi ghi; CHECK ở DB là hàng rào cuối. KHÔNG bỏ dấu chấm hay
    # `+tag` của Gmail: admin mời đúng địa chỉ mà người dùng đăng nhập.
    email: Mapped[str] = mapped_column(String(320))
    # NULL cho tới lần đăng nhập đầu tiên (status=invited). Sau đó là khoá định danh thật.
    google_sub: Mapped[str | None] = mapped_column(String(255), default=None)
    name: Mapped[str | None] = mapped_column(String(200), default=None)
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, "user_role"),
        default=UserRole.MEMBER,
        server_default=UserRole.MEMBER.value,
    )
    status: Mapped[UserStatus] = mapped_column(
        enum_column(UserStatus, "user_status"),
        default=UserStatus.INVITED,
        server_default=UserStatus.INVITED.value,
    )
    # KHÔNG CÒN DÙNG: múi giờ nay chỉ lấy từ server (DISPLAY_TIMEZONE). Cột để nguyên,
    # gỡ bằng migration riêng sau.
    timezone: Mapped[str | None] = mapped_column(String(64), default=None)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Một tài khoản chỉ có MỘT cách đăng nhập; không chuyển đổi, không gắn thêm cách thứ hai.
    auth_provider: Mapped[AuthProvider] = mapped_column(
        enum_column(AuthProvider, "auth_provider"),
        default=AuthProvider.GOOGLE,
        server_default=AuthProvider.GOOGLE.value,
    )
    # Chỉ tài khoản `local`, lưu chữ thường, không có `@` (để phân biệt với email khi đăng nhập).
    username: Mapped[str | None] = mapped_column(String(64), default=None)
    # ═══════════════════════════════════════════════════════════════════
    #  `password_hash` KHÔNG BAO GIỜ được đưa vào schema đọc, log hay audit.
    # ═══════════════════════════════════════════════════════════════════
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    # true sau khi admin tạo/đặt lại: core chặn mọi route trừ /me và /me/password.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Lần đặt mật khẩu gần nhất; mật khẩu tạm hết hạn tính từ mốc này.
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    aliases: Mapped[list[UserAlias]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        # NULL được lặp: nhiều user `invited` chưa có sub.
        UniqueConstraint("google_sub", name="uq_users_google_sub"),
        # NULL được lặp: chỉ tài khoản `local` có username.
        UniqueConstraint("username", name="uq_users_username"),
        # CHECK tường minh vì enum_column() không sinh CHECK và `alembic check` không so CHECK.
        CheckConstraint(
            "email = lower(btrim(email)) AND position('@' in email) > 1",
            name="email_normalized",
        ),
        CheckConstraint("role IN ('admin', 'lead', 'member')", name="role_valid"),
        CheckConstraint("status IN ('invited', 'active', 'disabled')", name="status_valid"),
        # Tài khoản Google đã kích hoạt phải gắn sub; tài khoản nội bộ không có sub.
        CheckConstraint(
            "status <> 'active' OR auth_provider = 'local' OR google_sub IS NOT NULL",
            name="active_has_sub",
        ),
        CheckConstraint("session_version >= 0", name="session_version_non_negative"),
        CheckConstraint("auth_provider IN ('google', 'local')", name="auth_provider_valid"),
        CheckConstraint(
            "username IS NULL OR username ~ '^[a-z0-9][a-z0-9._-]{2,63}$'",
            name="username_format",
        ),
        CheckConstraint(
            "auth_provider <> 'local' OR (username IS NOT NULL AND password_hash IS NOT NULL)",
            name="local_credentials",
        ),
        CheckConstraint(
            "auth_provider <> 'google' OR (password_hash IS NULL AND username IS NULL "
            "AND must_change_password = false)",
            name="google_no_password",
        ),
        CheckConstraint("auth_provider <> 'local' OR google_sub IS NULL", name="local_no_sub"),
        CheckConstraint(
            "auth_provider <> 'local' OR status <> 'invited'", name="local_not_invited"
        ),
        CheckConstraint("failed_login_count >= 0", name="failed_login_non_negative"),
    )

    def __repr__(self) -> str:
        # Cố ý không in email (PII) ra log.
        return f"<User {self.id} {self.role} {self.status}>"


class UserAlias(UUIDPrimaryKeyMixin, Base):
    """Tên của user trong hệ thống nguồn (vd assignee Jira), quyết định "việc của tôi".

    Alias quyết định cả QUYỀN SỬA task `work` giao cho tên đó, nên chỉ admin được sửa và một
    tên chỉ thuộc đúng một user (`uq_user_aliases_source_alias`). So khớp CHÍNH XÁC, phân biệt
    hoa thường, giống quy tắc so assignee từ trước tới nay.
    """

    __tablename__ = "user_aliases"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    source: Mapped[AliasSource] = mapped_column(enum_column(AliasSource, "alias_source"))
    alias: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("source", "alias", name="uq_user_aliases_source_alias"),
        Index("ix_user_aliases_user_id", "user_id"),
        CheckConstraint("source IN ('jira')", name="source_valid"),
        CheckConstraint("alias = btrim(alias) AND length(alias) > 0", name="alias_trimmed"),
    )

    def __repr__(self) -> str:
        return f"<UserAlias {self.source} user={self.user_id}>"
