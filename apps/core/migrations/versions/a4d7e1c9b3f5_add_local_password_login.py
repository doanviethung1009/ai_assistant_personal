"""thêm tài khoản nội bộ: auth_provider, username, password_hash và cột khoá đăng nhập

Revision ID: a4d7e1c9b3f5
Revises: e8a3c6f2b1d7
Create Date: 2026-10-15 09:00:00.000000

Spec: docs/specs/admin-users-local-login.md mục 2.

Cột mới đều có default hằng nên Postgres >= 11 chỉ đổi metadata, không viết lại bảng. Dòng cũ
thành `auth_provider = 'google'`, không cần backfill. `ck_users_active_has_sub` được thay bằng
bản cho phép tài khoản `local` (không có google_sub) ở trạng thái active.

Downgrade: MẤT hash mật khẩu và tên đăng nhập. Tài khoản `local` còn lại sẽ thành tài khoản
`google` bị `disabled` (không đăng nhập được, session_version tăng để mọi phiên chết), dữ liệu
sở hữu (owner_id) giữ nguyên. Dump trước khi hạ trên dữ liệu thật:
  pg_dump -t users
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a4d7e1c9b3f5"
down_revision: str | None = "e8a3c6f2b1d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_ACTIVE_HAS_SUB = "status <> 'active' OR google_sub IS NOT NULL"
_NEW_ACTIVE_HAS_SUB = "status <> 'active' OR auth_provider = 'local' OR google_sub IS NOT NULL"

# (tên đầy đủ, biểu thức). Thứ tự không quan trọng: không CHECK nào tham chiếu CHECK khác.
_CHECKS: list[tuple[str, str]] = [
    ("ck_users_auth_provider_valid", "auth_provider IN ('google', 'local')"),
    (
        "ck_users_username_format",
        "username IS NULL OR username ~ '^[a-z0-9][a-z0-9._-]{2,63}$'",
    ),
    (
        "ck_users_local_credentials",
        "auth_provider <> 'local' OR (username IS NOT NULL AND password_hash IS NOT NULL)",
    ),
    (
        "ck_users_google_no_password",
        "auth_provider <> 'google' OR (password_hash IS NULL AND username IS NULL "
        "AND must_change_password = false)",
    ),
    ("ck_users_local_no_sub", "auth_provider <> 'local' OR google_sub IS NULL"),
    ("ck_users_local_not_invited", "auth_provider <> 'local' OR status <> 'invited'"),
    ("ck_users_failed_login_non_negative", "failed_login_count >= 0"),
]


def upgrade() -> None:
    # Chờ khoá tối đa 5s thay vì treo hàng đợi truy vấn của bảng users.
    op.execute("SET LOCAL lock_timeout = '5s'")

    op.add_column(
        "users",
        sa.Column("auth_provider", sa.String(length=32), server_default="google", nullable=False),
    )
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users", sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))

    op.drop_constraint(op.f("ck_users_active_has_sub"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_active_has_sub"), "users", _NEW_ACTIVE_HAS_SUB)
    for name, expr in _CHECKS:
        op.create_check_constraint(op.f(name), "users", expr)
    op.create_unique_constraint(op.f("uq_users_username"), "users", ["username"])

    op.create_index(
        "ix_audit_log_target_created",
        "audit_log",
        ["target_type", "target_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")

    # (1) CHECK cũ `active_has_sub` không cho phép dòng active không có google_sub: khoá mọi
    # tài khoản nội bộ trước, đồng thời tăng sv để phiên đang chạy chết ngay.
    op.execute(
        "UPDATE users SET status = 'disabled', session_version = session_version + 1 "
        "WHERE auth_provider = 'local'"
    )

    # (2) Gỡ index, UNIQUE, CHECK mới.
    op.drop_index("ix_audit_log_target_created", table_name="audit_log")
    op.drop_constraint(op.f("uq_users_username"), "users", type_="unique")
    for name, _expr in reversed(_CHECKS):
        op.drop_constraint(op.f(name), "users", type_="check")

    # (3) Trả CHECK cũ.
    op.drop_constraint(op.f("ck_users_active_has_sub"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_active_has_sub"), "users", _OLD_ACTIVE_HAS_SUB)

    # (4) Bỏ 7 cột.
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
    op.drop_column("users", "auth_provider")
