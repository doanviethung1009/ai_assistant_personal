"""Băm identifier đăng nhập gõ nhầm để ghi audit và đặt khoá rate limit.

WHY HMAC thay sha256 trần: identifier gõ sai thường chính là mật khẩu gõ nhầm ô. sha256 trần
của chuỗi ngắn dò ngược được bằng từ điển nếu ai đó đọc được audit_log hay Redis; HMAC với khoá
suy ra từ `core_jwt_secret` thì không dò được khi không có khoá. Đổi `core_jwt_secret` làm đổi
digest: chỉ ảnh hưởng khả năng đối chiếu audit cũ, không ảnh hưởng xác thực.
"""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import settings

# Tiền tố ngăn miền: digest này không bao giờ trùng HMAC cùng khoá dùng cho việc khác.
_DOMAIN = b"identifier-v1:"


def _normalize(identifier: str) -> bytes:
    return identifier.strip().lower().encode("utf-8", "replace")


def identifier_digest(identifier: str, secret: str | None = None) -> str:
    """HMAC-SHA256 (64 hex) của identifier đã chuẩn hoá. `secret` chỉ để test."""
    key = (secret if secret is not None else settings.core_jwt_secret.get_secret_value()).encode()
    return hmac.new(key, _DOMAIN + _normalize(identifier), hashlib.sha256).hexdigest()
