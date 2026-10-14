from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

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
