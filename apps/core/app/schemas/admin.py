"""Schema của `/api/v1/admin/*`.

KHÔNG có trường nào mang `password_hash`. Mật khẩu tạm chỉ xuất hiện trong `LocalUserCreated`
và `TemporaryPassword`, đúng một lần, kèm `Cache-Control: no-store`.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import AliasSource, AuthProvider, UserRole, UserStatus
from app.schemas.user import AliasRead

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
MAX_ALIASES = 20


class UserAdminRead(BaseModel):
    id: uuid.UUID
    email: str
    username: str | None
    name: str | None
    role: UserRole
    status: UserStatus
    auth_provider: AuthProvider
    must_change_password: bool
    locked_until: datetime | None
    failed_login_count: int
    last_login_at: datetime | None
    created_at: datetime
    invited_by: uuid.UUID | None
    aliases: list[AliasRead]
    # Email thuộc ADMIN_EMAILS: UI khoá nút hạ role/khoá/xoá (core vẫn quyết định).
    is_env_admin: bool


_ALIAS_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def clean_initial_aliases(values: list[str]) -> list[str]:
    """Chuẩn hoá alias Jira gán lúc tạo user: strip, 1..200 ký tự, không ký tự điều khiển,
    không trùng. Lỗi thì 422 ngay (khác `add_aliases`, nơi tên trùng NGƯỜI KHÁC chỉ bị bỏ qua)."""
    cleaned: list[str] = []
    for raw in values:
        alias = raw.strip()
        if not 1 <= len(alias) <= 200:
            raise ValueError("alias phải dài 1-200 ký tự")
        if _ALIAS_CONTROL_RE.search(alias):
            raise ValueError("alias không được chứa ký tự điều khiển")
        cleaned.append(alias)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("alias bị trùng")
    return cleaned


class GoogleUserInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: UserRole = UserRole.MEMBER
    name: str | None = Field(default=None, max_length=200)
    # Alias Jira gán ngay lúc mời; tên đang thuộc user khác bị bỏ qua (xem `aliases_skipped`).
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)

    @field_validator("aliases")
    @classmethod
    def _aliases_format(cls, value: list[str]) -> list[str]:
        return clean_initial_aliases(value)


class LocalUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=320)
    name: str | None = Field(default=None, max_length=200)
    role: UserRole = UserRole.MEMBER
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)

    @field_validator("aliases")
    @classmethod
    def _aliases_format(cls, value: list[str]) -> list[str]:
        return clean_initial_aliases(value)

    @field_validator("username")
    @classmethod
    def _username_format(cls, value: str) -> str:
        clean = value.strip().lower()
        if not USERNAME_RE.fullmatch(clean):
            raise ValueError(
                "tên đăng nhập 3-64 ký tự: chữ thường, số, . _ -, bắt đầu bằng chữ hoặc số"
            )
        return clean


class UserInvited(UserAdminRead):
    """Response mời Google: `UserAdminRead` cộng `aliases_skipped`. Là lớp con nên client cũ
    (chỉ đọc các trường của `UserAdminRead`) không bị phá."""

    # Alias yêu cầu nhưng đã thuộc user khác (hoặc đua nhau), không được gán.
    aliases_skipped: list[str] = Field(default_factory=list)


class LocalUserCreated(BaseModel):
    user: UserAdminRead
    # Hiện MỘT lần. Không lưu ở đâu ngoài hash.
    temporary_password: str
    aliases_skipped: list[str] = Field(default_factory=list)


class TemporaryPassword(BaseModel):
    temporary_password: str


class UserAdminUpdate(BaseModel):
    """Ít nhất một trường. `email`/`username` chỉ áp cho tài khoản nội bộ."""

    model_config = ConfigDict(extra="forbid")

    role: UserRole | None = None
    status: Literal["active", "disabled"] | None = None
    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    username: str | None = Field(default=None, min_length=3, max_length=64)

    @field_validator("username")
    @classmethod
    def _username_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip().lower()
        if not USERNAME_RE.fullmatch(clean):
            raise ValueError("tên đăng nhập không hợp lệ")
        return clean

    @model_validator(mode="after")
    def _at_least_one(self) -> UserAdminUpdate:
        if not self.model_fields_set:
            raise ValueError("cần ít nhất một trường để cập nhật")
        for field in ("role", "status", "email", "username"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} không được null")
        return self


class AliasItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: AliasSource = AliasSource.JIRA
    alias: str = Field(min_length=1, max_length=200)


class AliasesSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aliases: list[AliasItem] = Field(max_length=MAX_ALIASES)

    @model_validator(mode="after")
    def _no_duplicates(self) -> AliasesSet:
        names = [item.alias.strip() for item in self.aliases]
        if any(not n for n in names):
            raise ValueError("alias không được rỗng")
        if len(set(names)) != len(names):
            raise ValueError("alias bị trùng")
        return self


class AuditRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    action: str
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    target_type: str | None
    target_id: uuid.UUID | None
    target_email: str | None
    client_ip: str | None
    details: dict[str, Any] | None

    @field_validator("client_ip", mode="before")
    @classmethod
    def _ip_to_str(cls, value: object) -> object:
        return None if value is None else str(value)
