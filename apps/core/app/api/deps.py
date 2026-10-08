from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import require_api_key
from app.db.session import get_session

logger = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ApiKeyDep = Annotated[str, Depends(require_api_key)]

# Khai bằng Header(alias=...) để OpenAPI (và types sinh cho web) có header này.
ImportSecretHeader = Annotated[
    str | None,
    Header(
        alias="X-Import-Secret",
        description="Bắt buộc khi dry_run=false: mật khẩu nhập dữ liệu (IMPORT_COMMIT_SECRET).",
    ),
]


def guard_import_secret(request: Request, secret: str | None) -> None:
    """Kiểm mật khẩu nhập (403).

    Dùng chung cho nhập thật và xoá lịch sử: web không có đăng nhập, API key lại nằm
    ở server env của web, nên thao tác không hoàn tác cần thêm lớp này.
    """
    configured = settings.import_commit_secret
    # Nguồn của request để điều tra dò mật khẩu; TUYỆT ĐỐI không log giá trị secret.
    client = request.client.host if request.client else "không rõ"
    if configured is None:
        logger.warning(
            "nhập thật bị từ chối: chưa cấu hình IMPORT_COMMIT_SECRET (client=%s)", client
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "Nhập thật đang bị tắt: server chưa cấu hình IMPORT_COMMIT_SECRET. "
                "Đặt biến môi trường này (tối thiểu 16 ký tự) rồi khởi động lại core."
            ),
        )
    # compare_digest trên bytes: chống đoán bí mật qua thời gian so sánh, và không
    # văng TypeError với ký tự ngoài ASCII. Giá trị KHÔNG được log hay echo lại.
    if secret is None or not secrets.compare_digest(
        secret.encode("utf-8"), configured.get_secret_value().encode("utf-8")
    ):
        logger.warning(
            "nhập thật bị từ chối: %s mật khẩu nhập (client=%s)",
            "thiếu" if secret is None else "sai",
            client,
        )
        raise HTTPException(
            status_code=403,
            detail="Thiếu hoặc sai mật khẩu nhập dữ liệu (header X-Import-Secret).",
        )
