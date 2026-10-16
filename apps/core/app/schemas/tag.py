from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.schemas.common import normalize_tags


class TagStat(BaseModel):
    """Một tag cùng số task và số note đang dùng nó (không tính bản ghi đã xoá mềm)."""

    name: str
    task_count: int
    note_count: int


class TagRename(BaseModel):
    new_name: str = Field(min_length=1, max_length=64, description="Tên mới; được chuẩn hoá")

    @field_validator("new_name")
    @classmethod
    def _normalize(cls, value: str) -> str:
        # Dùng chung normalize_tags để tag đổi tên khớp tag nhập từ form task/note.
        normalized = normalize_tags([value])
        if not normalized:
            raise ValueError("new_name không hợp lệ")
        return normalized[0]


class TagRuleRead(BaseModel):
    """Quy tắc đồng bộ tag. Không trả email người tạo, chỉ tên hiển thị."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_tag: str
    target_tag: str | None = Field(description="NULL = tag bị chặn (đã xoá)")
    created_by_user_id: uuid.UUID | None
    created_by_name: str | None = Field(
        default=None, description="users.name; NULL nếu user đã bị xoá hoặc chưa có tên"
    )
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def kind(self) -> Literal["alias", "block"]:
        return "block" if self.target_tag is None else "alias"


class TagChangeResponse(BaseModel):
    tasks: int = Field(description="Số task đã đổi")
    notes: int = Field(description="Số note đã đổi")
    rule: TagRuleRead | None = Field(
        default=None,
        description="Rule đồng bộ vừa ghi; NULL nếu lệnh không chạm task work",
    )
