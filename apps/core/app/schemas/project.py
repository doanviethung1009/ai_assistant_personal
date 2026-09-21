from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    color: str | None = Field(default=None, description="Mã hex, ví dụ #2563eb")

    @field_validator("color")
    @classmethod
    def _check_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HEX_COLOR.match(value):
            raise ValueError("color phải là mã hex dạng #rgb hoặc #rrggbb")
        return value.lower()


class ProjectCreate(ProjectBase):
    key: str = Field(
        description="Mã ngắn, chữ in hoa, ví dụ OPS hoặc HOMELAB",
        examples=["OPS"],
    )

    @field_validator("key")
    @classmethod
    def _check_key(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _KEY_PATTERN.match(normalized):
            raise ValueError("key phải gồm 2-20 ký tự A-Z, 0-9 hoặc _, bắt đầu bằng chữ")
        return normalized


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    color: str | None = None
    is_archived: bool | None = None

    @field_validator("color")
    @classmethod
    def _check_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HEX_COLOR.match(value):
            raise ValueError("color phải là mã hex dạng #rgb hoặc #rrggbb")
        return value.lower()


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ProjectSummary(BaseModel):
    """Bản rút gọn để nhúng trong TaskRead."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    color: str | None = None
