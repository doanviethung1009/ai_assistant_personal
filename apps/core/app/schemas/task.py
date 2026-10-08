from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from math import ceil
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.config import settings
from app.models.enums import TaskEventType, TaskPriority, TaskScope, TaskSource, TaskStatus
from app.schemas.common import normalize_tags as _normalize_tags
from app.schemas.project import ProjectSummary

# Giới hạn tham số `owner` của view=mine (spec task-scope 3.1): chặn đầu vào
# không đáng tin làm phình mệnh đề IN.
MAX_OWNERS = 20
MAX_OWNER_LEN = 200


class TaskView(StrEnum):
    """Góc nhìn lọc theo scope cho /tasks, /agenda, /stats.

    `ALL` là mặc định để client cũ không đổi hành vi. `MINE` là một view tính từ
    scope và assignee (không phải cột): xem `_view_clause` trong task_service.
    """

    ALL = "all"
    MINE = "mine"
    PERSONAL = "personal"
    WORK = "work"


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    assignee: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    project_id: uuid.UUID | None = None
    due_at: datetime | None = Field(default=None, description="Hạn chót, timestamptz")
    scheduled_for: date | None = Field(
        default=None, description="Ngày dự định làm. Khác due_at là hạn chót."
    )
    estimate_minutes: int | None = Field(default=None, gt=0, le=60 * 24 * 30)
    tags: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title không được rỗng")
        return stripped

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value)


class TaskCreate(TaskBase):
    # Integration và agent dùng cùng endpoint này. Web UI để mặc định MANUAL.
    source: TaskSource = TaskSource.MANUAL
    # None = suy từ source (default_scope_for). Integration truyền tường minh "work".
    scope: TaskScope | None = None
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = None
    raw_payload: dict[str, Any] | None = None


class TaskUpdate(BaseModel):
    """Patch bán phần.

    Field không truyền thì giữ nguyên; truyền null thì xoá giá trị. Router
    phân biệt hai trường hợp bằng model_dump(exclude_unset=True).
    """

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    assignee: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    project_id: uuid.UUID | None = None
    due_at: datetime | None = None
    scheduled_for: date | None = None
    estimate_minutes: int | None = Field(default=None, gt=0, le=60 * 24 * 30)
    spent_minutes: int | None = Field(default=None, ge=0)
    tags: list[str] | None = None
    scope: TaskScope | None = None

    @model_validator(mode="after")
    def _scope_not_null(self) -> TaskUpdate:
        # Cột scope NOT NULL: `null` tường minh phải bị từ chối ở đây (422) thay vì
        # để Postgres ném IntegrityError (500). Vắng khoá thì không nằm trong fields_set.
        if "scope" in self.model_fields_set and self.scope is None:
            raise ValueError("scope không được null")
        return self

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("title không được rỗng")
        return stripped

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_tags(value)


class TimeLogRequest(BaseModel):
    minutes: int = Field(gt=0, le=60 * 24, description="Số phút cộng thêm vào spent_minutes")
    note: str | None = Field(default=None, max_length=1000)


class TaskEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: TaskEventType
    actor: str
    payload: dict[str, Any] | None = None
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    assignee: str | None
    status: TaskStatus
    priority: TaskPriority
    project_id: uuid.UUID | None
    project: ProjectSummary | None = None
    due_at: datetime | None
    scheduled_for: date | None
    estimate_minutes: int | None
    spent_minutes: int
    completed_at: datetime | None
    tags: list[str]
    source: TaskSource
    # Bắt buộc, không default: OpenAPI sinh field required cho web.
    scope: TaskScope
    external_id: str | None
    external_url: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = Field(
        default=None, description="Khác null nghĩa là đang ở trong thùng rác"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_overdue(self) -> bool:
        if self.due_at is None or self.status.is_closed:
            return False
        return self.due_at < datetime.now(UTC)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def days_until_purge(self) -> int | None:
        """Số ngày còn lại trước khi bị xoá vĩnh viễn. Null nếu chưa xoá."""
        if self.deleted_at is None:
            return None

        expires_at = self.deleted_at + timedelta(days=settings.trash_retention_days)
        remaining = (expires_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return 0
        # Làm tròn lên: còn 2 tiếng vẫn tính là 1 ngày, để không hiện "0 ngày"
        # cho thứ chưa thực sự hết hạn.
        return max(1, ceil(remaining / 86_400))


class TaskDetail(TaskRead):
    events: list[TaskEventRead] = Field(default_factory=list)


class AgendaResponse(BaseModel):
    """View cho theo dõi hàng ngày."""

    reference_date: date = Field(description="Ngày tham chiếu theo timezone hiển thị")
    overdue: list[TaskRead] = Field(default_factory=list)
    scheduled_today: list[TaskRead] = Field(default_factory=list)
    in_progress: list[TaskRead] = Field(default_factory=list)
    due_soon: list[TaskRead] = Field(
        default_factory=list, description="Đến hạn trong 7 ngày tới, chưa xếp lịch"
    )
    completed_today: list[TaskRead] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def totals(self) -> dict[str, int]:
        return {
            "overdue": len(self.overdue),
            "scheduled_today": len(self.scheduled_today),
            "in_progress": len(self.in_progress),
            "due_soon": len(self.due_soon),
            "completed_today": len(self.completed_today),
        }


class TaskStatsResponse(BaseModel):
    reference_date: date
    by_status: dict[str, int]
    by_priority: dict[str, int]
    completed_last_7_days: dict[str, int] = Field(
        description="Số task hoàn thành theo ngày, key là ISO date"
    )
    open_total: int
    overdue_total: int
    minutes_logged_today: int
    trash_total: int = Field(default=0, description="Số task đang ở trong thùng rác")


class TrashResponse(BaseModel):
    """Thùng rác kèm thông tin về thời hạn giữ."""

    items: list[TaskRead]
    total: int
    limit: int
    offset: int
    retention_days: int = Field(
        description="Số ngày giữ task đã xoá trước khi xoá vĩnh viễn"
    )
    purged_now: int = Field(
        default=0,
        description="Số task quá hạn vừa bị dọn trong lần gọi này",
    )


class PurgeResponse(BaseModel):
    purged: int = Field(description="Số task đã xoá vĩnh viễn")
    retention_days: int
