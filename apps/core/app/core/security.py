"""Xác thực bằng API key (lớp "request đến từ web").

API key tĩnh chỉ chứng minh request đi qua web (key nằm trong server env của web, không xuống
browser). NGƯỜI DÙNG nào đang gọi do `core/auth.py` quyết định bằng JWT 60 giây; mọi endpoint
dưới /api/v1 đòi cả hai, riêng /api/v1/auth/login chỉ đòi API key.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

_API_KEY_HEADER = "X-API-Key"

api_key_scheme = APIKeyHeader(
    name=_API_KEY_HEADER,
    auto_error=False,
    description=(
        "Khoá tĩnh của người dùng. Web UI gọi qua route handler phía server, "
        "khoá không xuống browser."
    ),
)


async def require_api_key(provided: str | None = Security(api_key_scheme)) -> str:
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Thiếu header {_API_KEY_HEADER}",
            headers={"WWW-Authenticate": _API_KEY_HEADER},
        )

    # compare_digest để không rò rỉ thông tin qua thời gian so sánh
    if not secrets.compare_digest(provided, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key không hợp lệ",
        )

    return provided
