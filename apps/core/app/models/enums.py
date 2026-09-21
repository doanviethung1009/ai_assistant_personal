"""Enum dùng chung.

Lưu trong DB dưới dạng VARCHAR + CHECK (native_enum=False) thay vì native
enum của Postgres. Lý do: thêm giá trị mới chỉ cần sửa CHECK, không phải
ALTER TYPE với các ràng buộc về transaction.
"""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def is_closed(self) -> bool:
        return self in {TaskStatus.DONE, TaskStatus.CANCELLED}


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

    @property
    def weight(self) -> int:
        return {"low": 0, "medium": 1, "high": 2, "urgent": 3}[self.value]


class TaskSource(StrEnum):
    """Nguồn gốc của task.

    Phase 1 chỉ dùng MANUAL. Các giá trị còn lại khai báo trước để thêm
    integration không cần migration đổi CHECK constraint.
    """

    MANUAL = "manual"
    JIRA = "jira"
    CALENDAR = "calendar"
    EMAIL = "email"
    OBSIDIAN = "obsidian"
    GITHUB = "github"
    GITLAB = "gitlab"
    AGENT = "agent"


class TaskEventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    SCHEDULED = "scheduled"
    TIME_LOGGED = "time_logged"
    COMPLETED = "completed"
    REOPENED = "reopened"
    NOTE_ADDED = "note_added"
    SYNCED = "synced"
    # Xoá mềm, đưa vào thùng rác. Task vẫn còn trong DB.
    DELETED = "deleted"
    # Lấy lại từ thùng rác
    RESTORED = "restored"
