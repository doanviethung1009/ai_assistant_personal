from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.models.enums import AliasSource, UserRole, UserStatus


class AliasRead(BaseModel):
    source: AliasSource
    alias: str


class MeRead(BaseModel):
    """Hồ sơ của người đang đăng nhập; web dùng `permissions` để ẩn/hiện, không so chuỗi role."""

    id: uuid.UUID
    email: str
    name: str | None
    role: UserRole
    status: UserStatus
    effective_timezone: str = Field(description="Múi giờ của server")
    aliases: list[AliasRead]
    permissions: list[Permission]
