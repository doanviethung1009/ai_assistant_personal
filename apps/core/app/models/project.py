from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.note import Note
    from app.models.task import Task


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    key: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # Mã hex để UI tô màu, ví dụ #2563eb
    color: Mapped[str | None] = mapped_column(String(7), default=None)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Người tạo, chỉ để biết ai được sửa/xoá. Project dùng chung cho mọi user nhìn thấy; NULL =
    # project dùng chung từ Jira/nhập file (chỉ lead/admin sửa).
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )

    tasks: Mapped[list[Task]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )
    # Xoá project chỉ gỡ liên kết (ondelete="SET NULL"), note vẫn còn nguyên.
    notes: Mapped[list[Note]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Project {self.key}>"
