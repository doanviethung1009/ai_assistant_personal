"""Schema của `POST /tasks/upsert-batch` (đồng bộ hàng loạt từ tích hợp)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import TaskPriority, TaskSource, TaskStatus
from app.schemas.common import normalize_tags as _normalize_tags
from app.schemas.task import MAX_ASSIGNEE_LEN, clean_assignee

MAX_BATCH_ITEMS = 1000
MAX_DESCRIPTION_LEN = 32_000


class TaskUpsert(BaseModel):
    """Một task từ nguồn ngoài.

    Khoá khớp là `(source của lô, external_id)`. Khi CẬP NHẬT chỉ các trường client
    thực sự gửi mới bị ghi đè (xét bằng `model_fields_set`), nên một nguồn không biết
    `status` sẽ không đặt lại status về `todo`. Khi TẠO MỚI, trường vắng dùng mặc định.

    `tags` được GỘP và `description` chỉ điền khi task đang rỗng (xem task_sync_service),
    để dữ liệu User tự thêm/sửa không mất sau mỗi lần sync.

    `external_url` chỉ nhận http/https (chống `javascript:`/`data:` bị render thành link).
    GHI CHÚ: `TaskCreate` (POST /tasks) chưa có ràng buộc này; ngoài phạm vi B4a.
    """

    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LEN)
    assignee: str | None = Field(default=None, max_length=MAX_ASSIGNEE_LEN)
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: datetime | None = None
    # Hạn là CẢ NGÀY (Jira `duedate`): bắt buộc `due_at` đúng 00:00:00 UTC. None = không nói
    # gì: tạo mới thì false; cập nhật thì giữ nguyên cờ hiện có trừ khi `due_at` đổi.
    due_all_day: bool | None = None
    scheduled_for: date | None = None
    estimate_minutes: int | None = Field(default=None, gt=0, le=60 * 24 * 30)
    tags: list[str] = Field(default_factory=list)
    external_url: str | None = Field(default=None, max_length=2048)
    # Mốc thời gian GỐC của nguồn (tuỳ chọn). Không múi giờ = giờ display_timezone.
    # `created_at` chỉ dùng khi tạo mới; `completed_at` dùng khi task ở trạng thái đóng.
    created_at: datetime | None = None
    completed_at: datetime | None = None
    # Project theo key (chuẩn hoá bằng normalize_project_key của B1, tự tạo nếu chưa có).
    project_key: str | None = Field(default=None, max_length=100)
    project_name: str | None = Field(default=None, max_length=200)
    # Payload thô của nguồn ngoài: KHÔNG đáng tin. Service giới hạn kích thước và loại
    # khoá nhạy cảm trước khi lưu.
    raw_payload: dict[str, Any] | None = None

    @field_validator(
        "external_id",
        "title",
        "description",
        "assignee",
        "external_url",
        "project_key",
        "project_name",
        mode="before",
    )
    @classmethod
    def _drop_nul(cls, value: Any) -> Any:
        # Postgres từ chối U+0000 trong text: một ký tự này làm hỏng cả lô (500).
        return value.replace("\x00", "") if isinstance(value, str) else value

    @model_validator(mode="after")
    def _all_day_is_midnight_utc(self) -> TaskUpsert:
        if self.due_all_day:
            due = self.due_at
            # Datetime không múi giờ sẽ được hiểu theo múi giờ hiển thị, không thể là nửa đêm UTC.
            if (
                due is None
                or due.tzinfo is None
                or due.astimezone(UTC).time() != datetime.min.time()
            ):
                raise ValueError("due_all_day=true đòi due_at là đúng 00:00:00 UTC")
        return self

    @field_validator("tags", mode="before")
    @classmethod
    def _drop_nul_tags(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [v.replace("\x00", "") if isinstance(v, str) else v for v in value]
        return value

    @field_validator("external_id", "title")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("không được rỗng")
        return stripped

    @field_validator("external_url")
    @classmethod
    def _http_url_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parts = urlsplit(stripped)
        except ValueError:
            raise ValueError("external_url không hợp lệ") from None
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            raise ValueError("external_url chỉ nhận http/https")
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch.isspace() for ch in stripped):
            raise ValueError("external_url chứa ký tự không hợp lệ")
        return stripped

    @field_validator("assignee")
    @classmethod
    def _clean_assignee(cls, value: str | None) -> str | None:
        return clean_assignee(value)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value)


class TaskUpsertBatch(BaseModel):
    source: TaskSource = Field(description="Nguồn tích hợp, không được là `manual`")
    items: list[TaskUpsert] = Field(max_length=MAX_BATCH_ITEMS)

    @field_validator("source")
    @classmethod
    def _not_manual(cls, value: TaskSource) -> TaskSource:
        # `manual` là task User tự tạo (scope=personal); đồng bộ không được đụng tới.
        if value is TaskSource.MANUAL:
            raise ValueError("source không được là manual")
        return value


class UpsertItemError(BaseModel):
    index: int = Field(description="Vị trí của item trong `items` (từ 0)")
    reason: str


class UpsertItemWarning(BaseModel):
    """Item VẪN được upsert nhưng một phần dữ liệu bị bỏ (hiện chỉ có `raw_payload`)."""

    index: int = Field(description="Vị trí của item trong `items` (từ 0)")
    reason: str


class TaskUpsertResult(BaseModel):
    added: int
    updated: int
    unchanged: int
    skipped_personal: int = Field(
        description="Trùng khoá với task scope=personal nên bị bỏ qua, không ghi đè"
    )
    errors: list[UpsertItemError] = Field(default_factory=list)
    kept_manual_due: int = Field(
        default=0,
        description="Số task giữ nguyên hạn vì User đã sửa tay (chỉ khi sync_if_unchanged)",
    )
    warnings: list[UpsertItemWarning] = Field(
        default_factory=list,
        description="Item đã upsert nhưng bị bỏ raw_payload (quá lớn, quá sâu, hết ngân sách lô)",
    )
