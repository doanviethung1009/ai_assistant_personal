"""Schema của chức năng nhập dữ liệu hàng loạt từ file JSON (builder-data, ai-logs).

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
    TaskSource,
    TaskStatus,
)

SUPPORTED_DATAFILE_VERSION = 4
SUPPORTED_AI_LOGS_VERSION = 1

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
    # B1: chỉ báo "bỏ qua". B2 mới nhập meta.current_users.
    meta: dict[str, Any] | None = None


class AiLogsEnvelope(BaseModel):
    """File `ai-logs.json`."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(default=1, ge=1, le=SUPPORTED_AI_LOGS_VERSION)
    exported_at: str | None = None
    ai_logs: list[dict[str, Any]] = Field(max_length=20_000)


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
    # File thật chứa `hsl(...)`; service chuẩn hoá về hex. Giới hạn 64 ký tự khớp
    # MAX_COLOR_LEN của normalize_color (phòng ReDoS).
    color: str | None = Field(default=None, max_length=64)
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


class ImportAiLog(_Row):
    id: uuid.UUID
    # str thay vì enum: file thật có `TOOL`, `UI/UX`, `DOCS`; service ánh xạ (D9).
    category: str | None = None
    prompt: str = Field(min_length=1)
    handling: str | None = None
    response: str = Field(min_length=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    invalid: int = 0


class FieldChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class Replacement(BaseModel):
    entity: Literal["project", "task", "note", "ai_log"]
    # id trong DB (khác file_id khi matched_by = natural_key)
    id: uuid.UUID
    file_id: uuid.UUID
    label: str
    matched_by: Literal["id", "natural_key"]
    file_older_than_db: bool
    changes: list[FieldChange]


class ImportIssue(BaseModel):
    level: Literal["error", "warning"]
    entity: Literal["file", "project", "task", "task_event", "note", "ai_log"]
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
