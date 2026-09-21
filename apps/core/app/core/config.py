"""Cấu hình ứng dụng, nạp từ biến môi trường."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Chung ───────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    app_name: str = "Builder AI Assistant"

    # ── Hạ tầng ─────────────────────────────────────────────────────
    database_url: str = Field(
        ...,
        description="DSN async, ví dụ postgresql+asyncpg://user:pw@host:5432/db",
    )
    redis_url: str = "redis://redis:6379/0"

    # ── Bảo mật ─────────────────────────────────────────────────────
    api_key: str = Field(..., min_length=16, description="Khoá cho header X-API-Key")
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── LLM gateway (chưa dùng ở Phase 1) ───────────────────────────
    litellm_base_url: str | None = None
    litellm_master_key: str | None = None

    # ── Hiển thị ────────────────────────────────────────────────────
    # Chỉ dùng để quy đổi "hôm nay" cho view agenda. DB luôn lưu UTC.
    display_timezone: str = "Asia/Ho_Chi_Minh"

    # ── Thùng rác ───────────────────────────────────────────────────
    # Task xoá mềm được giữ bao nhiêu ngày trước khi xoá vĩnh viễn.
    # Đặt 0 nghĩa là xoá ngay, không qua thùng rác.
    trash_retention_days: int = Field(default=30, ge=0, le=365)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url phải dùng driver asyncpg (postgresql+asyncpg://)")
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sync_database_url(self) -> str:
        """DSN đồng bộ, dùng cho công cụ không hỗ trợ async."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
