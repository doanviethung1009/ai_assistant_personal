"""Schema của chức năng nhập dữ liệu hàng loạt từ file JSON (builder-data).

Hai nhóm:
- Envelope + schema từng dòng: mô tả cái file được PHÉP chứa. Mảng ở envelope khai
  `list[dict]` chứ không khai thẳng model dòng, vì một dòng sai không được làm cả
  request trả 422 chung chung. Service validate từng dòng để gom lỗi theo
  entity/index/id cho người dùng sửa file.
- Báo cáo (`ImportReport`): thứ duy nhất người dùng nhìn thấy trước khi quyết định
  ghi đè, nên chứa đủ diff từng bản ghi.

Cố ý KHÔNG có field `raw_payload` ở bất kỳ schema dòng nào: payload thô là dữ liệu
không đáng tin, không nhận từ file (xem docs/specs/import-json-to-postgres.md, D11).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    NoteKind,
    NoteSource,
    TaskEventType,
    TaskPriority,
    TaskScope,
    TaskSource,
    TaskStatus,
)
from app.schemas.task import clean_assignee

# v5 thêm `tasks.scope` (spec task-scope S11); v6 thêm `sync_urls` cấp file (B2).
# Web lên phiên bản mới mà backend chưa lên thì mọi file mới xuất sẽ bị 422. Backend
# nhận cả v5 và v6 (và cũ hơn): `ge=1, le=` ở envelope.
SUPPORTED_DATAFILE_VERSION = 6

# ═══════════════════════════════════════════════════════════════════════
#  Envelope
# ═══════════════════════════════════════════════════════════════════════


class DataFileEnvelope(BaseModel):
    """File `builder-data.json`: projects, tasks (kèm events), notes."""

    # Khoá lạ ở cấp file không làm hỏng việc nhập, chỉ được liệt kê trong báo cáo.
    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(default=1, ge=1, le=SUPPORTED_DATAFILE_VERSION)
    exported_at: str | None = None
    projects: list[dict[str, Any]] = Field(max_length=1_000)
    tasks: list[dict[str, Any]] = Field(max_length=20_000)
    notes: list[dict[str, Any]] = Field(default_factory=list, max_length=10_000)
    # B2: chỉ `meta.current_users` được nhập; các khoá khác (minutes_logged_*...) bị bỏ
    # và báo trong ignored_fields["meta"] (D-B2a: backend tự tính từ nhật ký).
    meta: dict[str, Any] | None = None
    # Danh sách URL đồng bộ (v6). None/vắng = không đụng cài đặt trong DB. Để Any: giá
    # trị sai kiểu phải ra lỗi theo dòng (code `setting_invalid`) chứ không 422 chung chung.
    sync_urls: Any = None


# ═══════════════════════════════════════════════════════════════════════
#  Schema từng dòng của file (extra="ignore": field lạ bị bỏ, service liệt kê)
# ═══════════════════════════════════════════════════════════════════════


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _not_blank(value: str) -> str:
    # DB có CHECK length(btrim(x)) > 0; bắt sớm để báo lỗi theo dòng thay vì
    # để Postgres từ chối cả lô.
    if not value.strip():
        raise ValueError("không được rỗng")
    return value


class ImportProject(_Row):
    id: uuid.UUID
    # Chặn độ dài sớm: key được chuẩn hoá bằng regex/unicodedata, đầu vào dài vô hạn
    # chỉ tốn CPU mà không có key hợp lệ nào dài như vậy.
    key: str = Field(max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    # Any ở mức parse: màu lạ (số, chuỗi quá dài...) không được làm hỏng cả project.
    # normalize_color chặn độ dài (MAX_COLOR_LEN, phòng ReDoS) và trả None kèm cảnh
    # báo `color_dropped` với mọi dạng không nhận ra (D7).
    color: Any = None
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _not_blank(value)


class ImportTaskEvent(_Row):
    id: uuid.UUID
    event_type: TaskEventType
    actor: str | None = Field(default=None, max_length=100)
    payload: dict[str, Any] | None = None
    created_at: datetime | None = None


class ImportTask(_Row):
    id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    assignee: str | None = Field(default=None, max_length=200)
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    project_id: uuid.UUID | None = None
    # Object project nhúng: chỉ dùng `key` làm đường dự phòng khi project_id không
    # khớp được. Phần còn lại bị bỏ và báo trong ignored_fields.
    project: dict[str, Any] | None = None
    due_at: datetime | None = None
    scheduled_for: date | None = None
    # Không ràng buộc ở đây: ngoài khoảng cho phép thì chuyển null + cảnh báo
    # thay vì từ chối cả task.
    estimate_minutes: int | None = None
    spent_minutes: int = Field(default=0, ge=0)
    completed_at: datetime | None = None
    tags: list[str] | None = None
    source: TaskSource = TaskSource.MANUAL
    # None/vắng (mọi file v1-v4) = suy từ source, xem _parse_task.
    scope: TaskScope | None = None
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _not_blank(value)

    @field_validator("assignee")
    @classmethod
    def _assignee(cls, value: str | None) -> str | None:
        return clean_assignee(value)


class ImportNote(_Row):
    id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    kind: NoteKind = NoteKind.COMMAND
    content: str = Field(min_length=1, max_length=20_000)
    description: str | None = None
    context: str | None = Field(default=None, max_length=200)
    project_id: uuid.UUID | None = None
    project: dict[str, Any] | None = None
    tags: list[str] | None = None
    is_pinned: bool = False
    is_dangerous: bool = False
    use_count: int = Field(default=0, ge=0)
    last_used_at: datetime | None = None
    source: NoteSource = NoteSource.MANUAL
    external_id: str | None = Field(default=None, max_length=255)
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @field_validator("title", "content")
    @classmethod
    def _text(cls, value: str) -> str:
        return _not_blank(value)


# ═══════════════════════════════════════════════════════════════════════
#  Báo cáo
# ═══════════════════════════════════════════════════════════════════════


class EntityCounts(BaseModel):
    received: int = 0
    created: int = 0
    replaced: int = 0
    # Trong số `replaced`, bao nhiêu bản mà file CŨ HƠN dữ liệu đang có.
    replaced_older: int = 0
    unchanged: int = 0
    skipped_trash: int = 0
    skipped_trash_in_db: int = 0
    # Task cá nhân trong DB được bảo vệ, không bị file ghi đè (trừ include_personal).
    skipped_personal: int = 0
    invalid: int = 0


class FieldChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class Replacement(BaseModel):
    entity: Literal["project", "task", "note", "setting"]
    # id trong DB (khác file_id khi matched_by = natural_key)
    id: uuid.UUID
    file_id: uuid.UUID
    label: str
    matched_by: Literal["id", "natural_key"]
    file_older_than_db: bool
    changes: list[FieldChange]


class ImportIssue(BaseModel):
    level: Literal["error", "warning"]
    entity: Literal["file", "project", "task", "task_event", "note", "setting"]
    index: int | None = None
    id: str | None = None
    code: str
    # Tiếng Việt, không chép nội dung note/task vào message.
    message: str


class KeyChange(BaseModel):
    original: str
    normalized: str


class ImportReport(BaseModel):
    import_id: uuid.UUID
    dry_run: bool
    committed: bool
    schema_version: int
    # sha256 của body thô; gửi lại làm `expect_sha256` khi nhập thật để chứng minh
    # file nhập là file đã kiểm tra.
    file_sha256: str
    counts: dict[str, EntityCounts]
    errors: int
    warnings: int
    issues: list[ImportIssue]
    issues_truncated: bool
    replacements: list[Replacement]
    replacements_truncated: bool
    project_key_changes: list[KeyChange]
    ignored_fields: dict[str, list[str]]
