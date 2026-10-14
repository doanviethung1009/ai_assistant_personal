from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    """Claim đã được WEB xác minh với Google (chữ ký, aud, nonce), chuyển cho core.

    Core không có cách tự kiểm id_token, nên endpoint này chỉ tin được khi đi cùng `X-API-Key`
    của web (nằm trong server env của web, không xuống browser). KHÔNG nhận hay lưu id_token,
    access_token, refresh_token.
    """

    model_config = ConfigDict(extra="forbid")

    google_sub: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    email_verified: bool
    name: str | None = Field(default=None, max_length=200)
    # Google Workspace domain (claim `hd`), nếu có.
    hd: str | None = Field(default=None, max_length=255)
    # IP của browser do reverse proxy đặt (hop đầu của X-Forwarded-For), để giới hạn tốc độ
    # đăng nhập và ghi nhật ký. Không phải bằng chứng danh tính.
    client_ip: str | None = Field(default=None, max_length=45)


class LoginResult(BaseModel):
    user_id: uuid.UUID
    role: UserRole
    session_version: int


MAX_PASSWORD_INPUT = 1024


def _check_secret_length(value: SecretStr) -> SecretStr:
    """1..1024 ký tự. Kiểm bằng validator thay vì ràng buộc của Field vì SecretStr không chắc
    nhận min_length/max_length ở mọi phiên bản pydantic; thông báo không echo giá trị."""
    if not 1 <= len(value.get_secret_value()) <= MAX_PASSWORD_INPUT:
        raise ValueError(f"mật khẩu phải dài 1-{MAX_PASSWORD_INPUT} ký tự")
    return value


class PasswordLoginRequest(BaseModel):
    """Đăng nhập tài khoản nội bộ. Web chuyển nguyên văn những gì người dùng gõ.

    `password` là `SecretStr` để repr/log/dump không in giá trị. `identifier` có `@` thì so với
    email, không có thì so với username; chỉ trong tài khoản `local`.
    """

    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1, max_length=320)
    password: SecretStr
    # IP browser do web chuyển, để giới hạn tốc độ và ghi nhật ký (không phải bằng chứng danh tính).
    client_ip: str | None = Field(default=None, max_length=45)

    @field_validator("password")
    @classmethod
    def _password_length(cls, value: SecretStr) -> SecretStr:
        return _check_secret_length(value)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr
    new_password: SecretStr

    @field_validator("current_password", "new_password")
    @classmethod
    def _lengths(cls, value: SecretStr) -> SecretStr:
        return _check_secret_length(value)


class PasswordChanged(BaseModel):
    """`session_version` mới: web dùng nó (hoặc đăng nhập lại) để phiên hiện tại không chết."""

    session_version: int
