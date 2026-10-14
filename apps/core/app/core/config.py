"""Cấu hình ứng dụng, nạp từ biến môi trường."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.timezones import normalize_timezone
from app.core.url_allowlist import parse_extra_hosts


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
        # ValidationError mặc định in cả giá trị đầu vào. Với secret ngắn hơn
        # min_length, giá trị đó sẽ lọt vào log khởi động; ẩn đi cho mọi setting.
        hide_input_in_errors=True,
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
    # NoDecode: pydantic-settings mặc định JSON-decode field kiểu list trước
    # khi field_validator(mode="before") chạy, nên ".env" không thể dùng
    # chuỗi comma-separated bình thường (vd CORS_ORIGINS=a,b) mà sẽ crash
    # vì không parse được JSON. NoDecode tắt bước đó, để validator dưới xử lý.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Khoá ký JWT người dùng do web phát cho core (HS256, sống 60 giây). PHẢI khác API_KEY và
    # AUTH_SECRET của web. Bắt buộc (không có default): thiếu thì core KHÔNG khởi động, thay vì
    # chạy mà không xác thực được người dùng (fail closed). Tối thiểu 32 ký tự.
    # SecretStr: repr/log/dump không in giá trị.
    core_jwt_secret: SecretStr = Field(..., min_length=32)
    # Email luôn là admin. Lúc khởi động core upsert (chưa có thì tạo `invited` role admin, có rồi
    # thì ép role=admin) và UI không hạ/khoá được: đường "phá kính" khi lỡ khoá hết admin.
    # NoDecode như cors_origins: chuỗi phân cách dấu phẩy từ .env.
    admin_emails: Annotated[list[str], NoDecode] = []
    # Google Workspace domain được phép đăng nhập; rỗng = mọi tài khoản đã được mời. Web cũng
    # kiểm, core kiểm lại vì web không phải ranh giới bảo mật duy nhất.
    google_allowed_hd: Annotated[list[str], NoDecode] = []

    # Khoá mã hoá token của integration (Jira...) khi lưu DB: chuỗi Fernet (32 byte
    # base64 url-safe, sinh bằng `Fernet.generate_key()`). Khác API_KEY và khác
    # IMPORT_COMMIT_SECRET. Để trống = tắt lưu token (endpoint trả 503), app VẪN khởi
    # động. SecretStr: repr/log/dump không in giá trị. Mất khoá thì phải nhập lại
    # token. Xem core/secrets.py.
    integration_secret_key: SecretStr = Field(default=SecretStr(""))
    # Khoá CŨ để xoay khoá (danh sách phân cách dấu phẩy). Chỉ dùng để GIẢI MÃ; token ghi
    # mới luôn dùng khoá chính. Quy trình: đặt khoá mới vào KEY, khoá cũ vào KEY_OLD, rồi
    # mã hoá lại dần (secrets.rotate_ciphertext, hoặc nhập lại token); bỏ KEY_OLD khi
    # không còn ciphertext khoá cũ.
    integration_secret_key_old: SecretStr = Field(default=SecretStr(""))

    # Host bổ sung cho allowlist của sync_urls (ngoài Google/SharePoint/OneDrive đặt
    # cứng trong core/url_allowlist.py). Phân cách bằng dấu phẩy; `host` khớp chính xác,
    # `*.host` khớp mọi tên miền con. Chỉ https, cổng 443. Sai cú pháp thì app KHÔNG
    # khởi động: thừa host là lỗ hổng SSRF, nên không lặng lẽ bỏ qua.
    sync_url_extra_hosts: Annotated[list[str], NoDecode] = []

    # ── LLM gateway (chưa dùng ở Phase 1) ───────────────────────────
    litellm_base_url: str | None = None
    litellm_master_key: str | None = None

    # ── Hiển thị ────────────────────────────────────────────────────
    # Múi giờ của server: nguồn DUY NHẤT (không có múi giờ theo user hay ghi đè trong DB).
    # Thứ tự đọc env: DISPLAY_TIMEZONE, rồi TZ (docker-compose truyền cho mọi service nên web
    # và core cùng một giá trị), rồi mặc định. Đọc qua services/clock.py. DB luôn lưu UTC.
    display_timezone: str = Field(
        default="Asia/Ho_Chi_Minh",
        validation_alias=AliasChoices("DISPLAY_TIMEZONE", "TZ"),
    )

    # ── Thùng rác ───────────────────────────────────────────────────
    # Task xoá mềm được giữ bao nhiêu ngày trước khi xoá vĩnh viễn.
    # Đặt 0 nghĩa là xoá ngay, không qua thùng rác.
    trash_retention_days: int = Field(default=30, ge=0, le=365)

    # ── Rate limit ──────────────────────────────────────────────────
    # Đếm theo cửa sổ 60s ở Redis, xem core/rate_limit.py. Bật mặc định vì
    # một API key tĩnh không có gì ngăn một client lỗi gọi lặp vô hạn.
    # 300/phút theo user (Q11 spec web-authjs-login); chưa có JWT thì tính theo IP.
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = Field(default=300, ge=1)

    @field_validator("display_timezone", mode="before")
    @classmethod
    def _blank_timezone_means_unset(cls, value: object) -> object:
        # Biến rỗng (compose `TZ: ${TZ:-}`, `TZ=` trong .env) = chưa đặt, không phải lỗi.
        # Không dùng env_ignore_empty toàn cục: nó đổi nghĩa CORS_ORIGINS="" (từ [] sang
        # mặc định localhost). DISPLAY_TIMEZONE rỗng thì thử TZ trước khi về mặc định.
        if isinstance(value, str) and not value.strip():
            fallback = os.environ.get("TZ", "").strip()
            return fallback or "Asia/Ho_Chi_Minh"
        return value

    @field_validator("display_timezone")
    @classmethod
    def _check_display_timezone(cls, value: str) -> str:
        # Fail fast: tên sai thì app không lên, thay vì vỡ ở request đầu tiên tính "hôm nay".
        return normalize_timezone(value)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("sync_url_extra_hosts", mode="before")
    @classmethod
    def _parse_extra_hosts(cls, value: object) -> object:
        # NoDecode như cors_origins: chuỗi `a.com,*.b.com` từ .env/compose, biến rỗng = [].
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            # Chỉ để kiểm cú pháp (ném ValueError -> ValidationError); giữ dạng chuẩn hoá.
            parse_extra_hosts(value)
            return [str(item).strip().lower() for item in value if str(item).strip()]
        return value

    @field_validator("admin_emails", "google_allowed_hd", mode="before")
    @classmethod
    def _parse_lower_csv(cls, value: object) -> object:
        # Email và domain so khớp không phân biệt hoa thường: chuẩn hoá một lần ở đây.
        if isinstance(value, str):
            value = value.split(",")
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
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
