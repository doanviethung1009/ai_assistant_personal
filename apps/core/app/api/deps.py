from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import require_api_key
from app.db.session import SessionFactory, get_session
from app.services import clock

logger = logging.getLogger(__name__)

# scope="function": phần sau yield của get_session (commit) phải chạy TRƯỚC khi response được
# gửi. Mặc định (scope="request", FastAPI >= 0.118) nó chạy SAU khi gửi, nên client nhận 2xx
# khi transaction chưa commit và request kế tiếp đọc dữ liệu cũ. Đổi lại: không được dùng
# session trong BackgroundTasks hay response streaming (session đã đóng lúc đó).
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
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


async def bind_display_tz() -> None:
    """Gắn múi giờ hiệu lực cho request (xem services/clock.py).

    PHẢI là `async def`: dependency đồng bộ chạy trong threadpool nên ContextVar đặt ở đó
    không truyền về task của request.

    KHÔNG dùng SessionDep: route sync Jira cố ý không giữ session suốt lúc gọi Jira, mà
    session của dependency sống đến hết request. Cache miss thì mở session riêng, đọc
    một dòng rồi đóng ngay (cache còn hạn thì không chạm DB).
    """
    if clock.is_display_tz_cached():
        await clock.load_display_tz(None)
        return
    async with SessionFactory() as session:
        await clock.load_display_tz(session)
