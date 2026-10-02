from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import TaskEventType, TaskPriority, TaskSource, TaskStatus

if TYPE_CHECKING:
    from app.models.project import Project


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    # ── Nội dung ────────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    assignee: Mapped[str | None] = mapped_column(String(200), default=None, index=True)

    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus, "task_status"),
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        enum_column(TaskPriority, "task_priority"),
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
        index=True,
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )

    # ── Thời gian ───────────────────────────────────────────────────
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    # Ngày dự định làm, dùng cho view agenda hàng ngày. Khác due_at (hạn chót).
    scheduled_for: Mapped[date | None] = mapped_column(Date, default=None, index=True)
    estimate_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    spent_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # ── Thùng rác ───────────────────────────────────────────────────
    # Xoá là xoá mềm: đặt deleted_at rồi giữ lại một thời gian
    # (settings.trash_retention_days, mặc định 30 ngày) để còn phục hồi.
    # Mọi truy vấn nghiệp vụ phải lọc `deleted_at IS NULL`.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}"
    )

    # ── Nguồn gốc: khai báo sẵn cho integration ở Phase 2 ───────────
    source: Mapped[TaskSource] = mapped_column(
        enum_column(TaskSource, "task_source"),
        default=TaskSource.MANUAL,
        server_default=TaskSource.MANUAL.value,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(255), default=None)
    external_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Payload thô từ nguồn ngoài, giữ để reconcile khi sync lệch.
    # Đây là dữ liệu KHÔNG đáng tin, không bao giờ đưa thẳng vào prompt.
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    # ── Quan hệ ─────────────────────────────────────────────────────
    project: Mapped[Project | None] = relationship(back_populates="tasks", lazy="selectin")
    events: Mapped[list[TaskEvent]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskEvent.created_at.desc()",
    )

    __table_args__ = (
        # Ràng buộc duy nhất PHẢI là partial index, chỉ tính task còn sống.
        #
        # Nếu dùng UniqueConstraint thường, một task đã xoá mềm vẫn chiếm chỗ
        # (source, external_id). Lần sync sau từ Jira sẽ đụng constraint và
        # không tạo lại được issue đó, dù người dùng đã bỏ nó vào thùng rác.
        # Postgres cho phép nhiều NULL external_id nên task nhập tay không
        # bị ảnh hưởng.
        Index(
            "uq_tasks_source_external_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("spent_minutes >= 0", name="spent_minutes_non_negative"),
        CheckConstraint(
            "estimate_minutes IS NULL OR estimate_minutes > 0",
            name="estimate_minutes_positive",
        ),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        Index("ix_tasks_tags", "tags", postgresql_using="gin"),
        # Phủ đúng truy vấn của view agenda. Partial để index chỉ chứa task
        # còn sống, vốn là toàn bộ dữ liệu mà nghiệp vụ quan tâm.
        Index(
            "ix_tasks_open_agenda",
            "scheduled_for",
            "due_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Phục vụ view thùng rác và job dọn quá hạn
        Index(
            "ix_tasks_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Task {self.id} {self.status} {self.title[:40]!r}>"


class TaskEvent(UUIDPrimaryKeyMixin, Base):
    """Nhật ký thay đổi của task.

    Phục vụ hai việc: theo dõi hoạt động hàng ngày, và làm audit trail khi
    agent tự động sửa task ở các phase sau.
    """

    __tablename__ = "task_events"

    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[TaskEventType] = mapped_column(
        enum_column(TaskEventType, "task_event_type")
    )
    # "user" cho hành động thủ công, "agent:<tên>" khi agent tự làm
    actor: Mapped[str] = mapped_column(String(100), default="user", server_default="user")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped[Task] = relationship(back_populates="events")

    __table_args__ = (Index("ix_task_events_task_created", "task_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<TaskEvent {self.event_type} task={self.task_id}>"
