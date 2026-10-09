"""Cấu hình ứng dụng, nạp từ biến môi trường."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.timezones import normalize_timezone
from app.core.url_allowlist import parse_extra_hosts


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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
    # Mật khẩu cho thao tác nhập dữ liệu THẬT (ghi đè hàng loạt). Web không có đăng
    # nhập, nên API key một mình không đủ để cho phép ghi đè: người gửi phải biết
    # thêm bí mật này (header X-Import-Secret). Để trống = tắt hẳn nhập thật; dry-run
    # không cần. Tối thiểu 16 ký tự khi có đặt.
    # SecretStr: repr/log/dump không in giá trị.
    import_commit_secret: SecretStr | None = Field(default=None, min_length=16)

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
    # MẶC ĐỊNH khi chưa có dòng app_settings 'display_timezone'. Giá trị hiệu lực đọc qua
    # services/clock.py (User đổi được lúc chạy). DB luôn lưu UTC.
    display_timezone: str = "Asia/Ho_Chi_Minh"

    # ── Thùng rác ───────────────────────────────────────────────────
    # Task xoá mềm được giữ bao nhiêu ngày trước khi xoá vĩnh viễn.
    # Đặt 0 nghĩa là xoá ngay, không qua thùng rác.
    trash_retention_days: int = Field(default=30, ge=0, le=365)

    # ── Rate limit ──────────────────────────────────────────────────
    # Đếm theo cửa sổ 60s ở Redis, xem core/rate_limit.py. Bật mặc định vì
    # một API key tĩnh không có gì ngăn một client lỗi gọi lặp vô hạn.
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = Field(default=120, ge=1)

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

    @field_validator("import_commit_secret", mode="before")
    @classmethod
    def _blank_secret_is_unset(cls, value: object) -> object:
        # compose hay truyền biến rỗng (`IMPORT_COMMIT_SECRET=`): coi là chưa cấu hình
        # thay vì làm app không khởi động được vì vi phạm min_length. Cắt khoảng trắng
        # hai đầu vì header HTTP bị cắt khoảng trắng: secret có khoảng trắng đầu/cuối
        # sẽ không bao giờ khớp với giá trị client gửi.
        if isinstance(value, str):
            return value.strip() or None
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
