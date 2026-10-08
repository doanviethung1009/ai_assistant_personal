"""Lịch sử duyệt web (browser_history), đẩy lên từ máy chạy web.

══════════════════════════════════════════════════════════════════════
 DỮ LIỆU RIÊNG TƯ NHẠY CẢM. URL được CHUẨN HOÁ TRƯỚC KHI LƯU: bỏ query string, fragment
 và userinfo, vì chúng hay chứa token (link reset mật khẩu, OAuth `code=`). Cột `url`
 không bao giờ chứa phần đó; đừng thêm đường ghi nào bỏ qua `normalize_url`.

 RỦI RO CÒN LẠI: chỉ bỏ query/fragment/userinfo, PATH được giữ nguyên. Path vẫn có thể
 chứa token (`/reset-password/<token>`, link chia sẻ kiểu `/s/<id>`). Không có cách
 chung để nhận ra; coi cả bảng là nhạy cảm, đừng log hay xuất `url` ra ngoài.
 Đã biết: danh sách đếm `COUNT(*)` mỗi trang, chấp nhận được ở quy mô cá nhân.
══════════════════════════════════════════════════════════════════════

Backend chạy trong container nên không thấy hồ sơ Chrome của host. Web đọc Chrome rồi
đẩy lên qua `POST /browser-history/batch`; bảng này chỉ là nơi lưu.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class BrowserHistory(UUIDPrimaryKeyMixin, Base):
    """Một URL đã chuẩn hoá trong một profile trình duyệt."""

    __tablename__ = "browser_history"

    # Tên thư mục profile ("Default", "Profile 1"), KHÔNG phải đường dẫn.
    profile: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    # sha256 hex của `url` đã chuẩn hoá: URL dài không đưa thẳng vào unique index được.
    url_hash: Mapped[str] = mapped_column(CHAR(64))
    title: Mapped[str] = mapped_column(Text, server_default=text("''"))
    visit_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_visit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("profile", "url_hash", name="uq_browser_history_profile_url_hash"),
        CheckConstraint("visit_count >= 0", name="visit_count_non_negative"),
        CheckConstraint("url_hash ~ '^[0-9a-f]{64}$'", name="url_hash_hex"),
        CheckConstraint("char_length(url) <= 4096", name="url_max_len"),
        CheckConstraint("profile <> ''", name="profile_not_empty"),
        CheckConstraint("url ~ '^https?://'", name="url_http_scheme"),
        # Khớp ORDER BY của danh sách (id làm khoá phụ để phân trang ổn định).
        Index("ix_browser_history_last_visit_at_id", last_visit_at.column.desc(), "id"),
        Index(
            "ix_browser_history_profile_last_visit_at_id",
            "profile",
            last_visit_at.column.desc(),
            "id",
        ),
    )
