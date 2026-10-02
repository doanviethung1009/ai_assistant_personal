from __future__ import annotations

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    """Config vận hành cho trang Thông tin hệ thống/Quản trị trên web.

    CHỈ đưa field không nhạy cảm vào đây. Không bao giờ thêm database_url,
    api_key, litellm_master_key hay bất kỳ secret nào — endpoint này yêu cầu
    X-API-Key (một key cho một người ở Phase 1) nhưng không có RBAC, nên
    "đã xác thực" không đồng nghĩa "được xem mọi secret của hệ thống". Xem
    cảnh báo tương tự ở web-conventions.md về trang quản trị.
    """

    app_name: str
    version: str
    environment: str
    display_timezone: str
    trash_retention_days: int
    rate_limit_enabled: bool
    rate_limit_requests_per_minute: int
    cors_origins: list[str] = Field(
        description="Domain được phép gọi API từ browser. Không phải secret."
    )
