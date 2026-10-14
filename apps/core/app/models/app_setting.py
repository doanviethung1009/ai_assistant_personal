"""Cài đặt người dùng dạng key-value (app_settings).

══════════════════════════════════════════════════════════════════════
 CHỈ CHO CÀI ĐẶT KHÔNG BÍ MẬT. Không lưu token, mật khẩu hay khoá API ở đây: bảng
 này được export, nhập lại và hiện trong báo cáo nhập. Secret của integration
 (Jira...) thuộc pha B4 với cơ chế mã hoá riêng.
══════════════════════════════════════════════════════════════════════

Khoá hợp lệ khai báo cứng ở `SettingKey` và bị DB chặn bằng CHECK, nên một lỗi code
hay một INSERT tay không thể tạo khoá lạ.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import SettingKey

_KEY_CHECK = "key IN (" + ", ".join(f"'{member.value}'" for member in SettingKey) + ")"


class AppSetting(Base):
    """Một cài đặt. `value` là JSON: list[str] (current_users, sync_urls) hoặc chuỗi
    (display_timezone)."""

    __tablename__ = "app_settings"

    # Khoá tự nhiên làm PK: mỗi cài đặt đúng một dòng, upsert theo khoá.
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # CHECK tường minh vì `alembic check` không so CHECK: thêm SettingKey mà quên
        # migration DROP/ADD CONSTRAINT sẽ không bị phát hiện, DB sẽ từ chối giá trị mới.
        CheckConstraint(_KEY_CHECK, name="key_valid"),
    )
