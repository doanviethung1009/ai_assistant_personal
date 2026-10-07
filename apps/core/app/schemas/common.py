from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

MAX_TAGS = 20


def normalize_tags(value: list[str] | None) -> list[str]:
    """Chuẩn hoá tag: bỏ khoảng trắng, hạ chữ thường, thay space bằng gạch ngang.

    Dùng dict thay vì set để giữ thứ tự người dùng nhập, đồng thời loại trùng.

    Nằm ở đây thay vì trong schema của một entity vì cả Task và Note đều dùng.
    Hai bên chuẩn hoá khác nhau sẽ làm cùng một chữ ra hai tag khác nhau, và
    lọc theo tag sẽ trả thiếu.
    """
    if not value:
        return []
    seen: dict[str, None] = {}
    for raw in value:
        tag = raw.strip().lower().replace(" ", "-")
        if tag and len(tag) <= 64:
            seen[tag] = None
    if len(seen) > MAX_TAGS:
        raise ValueError(f"tối đa {MAX_TAGS} tag")
    return list(seen)


# Giữ Generic[T] thay vì cú pháp PEP 695: đổi sẽ đổi tên schema trong OpenAPI và làm
# lệch lib/generated/openapi.d.ts của web.
class Page(BaseModel, Generic[T]):  # noqa: UP046
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
