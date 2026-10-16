from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

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


class TagChangeResponse(BaseModel):
    tasks: int = Field(description="Số task đã đổi")
    notes: int = Field(description="Số note đã đổi")
