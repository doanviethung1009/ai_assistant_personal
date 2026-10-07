from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.config import settings
from app.models.enums import NoteKind, NoteSource
from app.schemas.common import normalize_tags
from app.schemas.project import ProjectSummary

# Note là snippet, không phải nơi chứa file log hay dump database. Giới hạn
# để một lần dán nhầm không làm phình bảng và làm chậm danh sách.
MAX_CONTENT = 20_000


def _require_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} không được rỗng")
    return stripped


class NoteBase(BaseModel):
    title: str = Field(min_length=1, max_length=300, description="Tên ngắn để tìm lại")
    kind: NoteKind = Field(
        default=NoteKind.COMMAND,
        description="Phân loại nội dung, quyết định cách hiển thị",
    )
    content: str = Field(
        min_length=1,
        max_length=MAX_CONTENT,
        description=(
            "Nội dung để copy: câu lệnh, câu SQL, đoạn cấu hình. "
            "Server không bao giờ thực thi giá trị này."
        ),
    )
    description: str | None = Field(
        default=None, description="Vì sao cần và khi nào dùng"
    )
    context: str | None = Field(
        default=None,
        max_length=200,
        description="Nơi áp dụng: host, database, môi trường",
        examples=["prod, DB builder_ai"],
    )
    project_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list)
    is_pinned: bool = Field(default=False, description="Ghim lên đầu danh sách")
    is_dangerous: bool = Field(
        default=False,
        description="Đánh dấu lệnh có thể gây mất dữ liệu, UI sẽ cảnh báo trước khi copy",
    )

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        return _require_text(value, "title")

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        # Chỉ bỏ khoảng trắng ở hai đầu. Thụt lề bên trong là phần nội dung,
        # đặc biệt với YAML và SQL nhiều dòng.
        return _require_text(value, "content")

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value)


class NoteCreate(NoteBase):
    # Integration và agent dùng cùng endpoint này. Web UI để mặc định MANUAL.
    source: NoteSource = NoteSource.MANUAL
    external_id: str | None = Field(default=None, max_length=255)
    raw_payload: dict[str, Any] | None = None


class NoteUpdate(BaseModel):
    """Patch bán phần.

    Field không truyền thì giữ nguyên; truyền null thì xoá giá trị. Router
    phân biệt hai trường hợp bằng model_dump(exclude_unset=True).
    """

    title: str | None = Field(default=None, min_length=1, max_length=300)
    kind: NoteKind | None = None
    content: str | None = Field(default=None, min_length=1, max_length=MAX_CONTENT)
    description: str | None = None
    context: str | None = Field(default=None, max_length=200)
    project_id: uuid.UUID | None = None
    tags: list[str] | None = None
    is_pinned: bool | None = None
    is_dangerous: bool | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        return None if value is None else _require_text(value, "title")

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str | None) -> str | None:
        return None if value is None else _require_text(value, "content")

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_tags(value)


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    kind: NoteKind
    content: str
    description: str | None
    context: str | None
    project_id: uuid.UUID | None
    project: ProjectSummary | None = None
    tags: list[str]
    is_pinned: bool
    is_dangerous: bool
    use_count: int
    last_used_at: datetime | None
    source: NoteSource
    external_id: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = Field(
        default=None, description="Khác null nghĩa là đang ở trong thùng rác"
    )

    archived_at: datetime | None = Field(
        default=None,
        description="Khác null nghĩa là đã lưu trữ: ẩn khỏi danh sách mặc định, không bị dọn",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def days_until_purge(self) -> int | None:
        """Số ngày còn lại trước khi bị xoá vĩnh viễn. Null nếu chưa xoá.

        Tính ở server vì thời hạn giữ là cấu hình của server
        (settings.trash_retention_days), client không biết giá trị đó.
        """
        if self.deleted_at is None:
            return None

        expires_at = self.deleted_at + timedelta(days=settings.trash_retention_days)
        remaining = (expires_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return 0
        # Làm tròn lên, để không hiện "0 ngày" cho thứ chưa thực sự hết hạn
        return max(1, ceil(remaining / 86_400))


class NoteTrashResponse(BaseModel):
    """Thùng rác của note kèm thông tin về thời hạn giữ."""

    items: list[NoteRead]
    total: int
    limit: int
    offset: int
    retention_days: int = Field(
        description="Số ngày giữ note đã xoá trước khi xoá vĩnh viễn"
    )
    purged_now: int = Field(
        default=0, description="Số note quá hạn vừa bị dọn trong lần gọi này"
    )


class NotePurgeResponse(BaseModel):
    purged: int = Field(description="Số note đã xoá vĩnh viễn")
    retention_days: int
