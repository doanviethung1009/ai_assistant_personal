from __future__ import annotations

from sqlalchemy import (
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import AiLogCategory


class AiLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Bảng lưu trữ lịch sử xử lý của AI (AI Task Trace)."""

    __tablename__ = "ai_logs"

    category: Mapped[AiLogCategory] = mapped_column(
        enum_column(AiLogCategory, "ai_log_category"),
        default=AiLogCategory.OTHER,
        server_default=AiLogCategory.OTHER.value,
        index=True,
    )
    prompt: Mapped[str] = mapped_column(Text)
    handling: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<AiLog {self.id} {self.category}>"
