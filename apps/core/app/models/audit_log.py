"""Nhật ký hành động quản trị và đăng nhập. CHỈ INSERT.

Service không có hàm sửa hay xoá dòng ở đây. `details` không bao giờ chứa token, cookie, JWT,
mã OAuth hay mật khẩu (xem `AuditAction`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_log"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # SET NULL: xoá user không được kéo theo mất nhật ký.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    # Giá trị của AuditAction. Cố ý không CHECK, xem docstring của AuditAction.
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32), default=None)
    target_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    client_ip: Mapped[str | None] = mapped_column(INET, default=None)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    __table_args__ = (
        Index("ix_audit_log_created_at", "created_at"),
        Index("ix_audit_log_actor_created", "actor_user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} actor={self.actor_user_id}>"
