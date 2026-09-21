from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.task import Task


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    key: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # Mã hex để UI tô màu, ví dụ #2563eb
    color: Mapped[str | None] = mapped_column(String(7), default=None)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    tasks: Mapped[list[Task]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Project {self.key}>"
