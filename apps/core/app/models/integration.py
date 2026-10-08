"""Kết nối tích hợp ngoài (Jira...) kèm token đã mã hoá.

══════════════════════════════════════════════════════════════════════
 CHỨA SECRET. `secret_ciphertext` là token đã mã hoá bằng INTEGRATION_SECRET_KEY
 (core/secrets.py). Không đưa cột này vào schema đọc, log, export hay báo cáo nhập;
 bảng này cố ý KHÔNG nằm trong luồng export/import JSON.
══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import IntegrationKind

_KIND_CHECK = "kind IN (" + ", ".join(f"'{member.value}'" for member in IntegrationKind) + ")"


class IntegrationConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"

    kind: Mapped[IntegrationKind] = mapped_column(enum_column(IntegrationKind, "integration_kind"))
    name: Mapped[str] = mapped_column(String(100))
    # Chỉ https, đã chuẩn hoá (không cổng, không path). Validate ở service/schema; CHECK
    # ở DB là hàng rào cuối chống INSERT tay.
    base_url: Mapped[str] = mapped_column(Text)
    account_email: Mapped[str] = mapped_column(String(200))

    # Token mã hoá (Fernet), gắn với (id, base_url) của kết nối. NULL = chưa có token.
    # Luôn đi cặp với secret_last4. last4 là String(4), không phải CHAR(4): CHAR đệm khoảng
    # trắng, token kết thúc bằng khoảng trắng sẽ đọc ra khác giá trị đã ghi.
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    secret_last4: Mapped[str | None] = mapped_column(String(4), default=None)

    # Tuỳ chọn của loại kết nối: jql, project_key, project_name (Jira).
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_integration_connections_kind_name"),
        # CHECK tường minh vì enum_column() không sinh CHECK và `alembic check` không so CHECK.
        CheckConstraint(_KIND_CHECK, name="kind_valid"),
        CheckConstraint("base_url LIKE 'https://%'", name="base_url_https"),
        # Ciphertext và last4 hoặc cùng có hoặc cùng không: tránh trạng thái "có token
        # mà UI báo không có" (và ngược lại).
        CheckConstraint(
            "(secret_ciphertext IS NULL) = (secret_last4 IS NULL)", name="secret_pair_consistent"
        ),
    )

    @property
    def has_secret(self) -> bool:
        return self.secret_ciphertext is not None

    def __repr__(self) -> str:
        # Cố ý không in secret_*.
        return f"<IntegrationConnection {self.kind} {self.name!r}>"
