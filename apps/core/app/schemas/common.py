from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Envelope phân trang. Dùng offset vì dữ liệu cá nhân, không cần cursor."""

    items: list[T]
    total: int = Field(description="Tổng số bản ghi khớp filter, không tính phân trang")
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class ErrorDetail(BaseModel):
    detail: str
