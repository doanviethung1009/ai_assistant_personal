"""Cài đặt toàn cục: URL đồng bộ (sync_urls) và danh mục múi giờ IANA.

Nằm dưới router cha có `require_api_key` và JWT người dùng. Chỉ cài đặt KHÔNG bí mật (xem
models/app_setting.py). PUT là ghi đè toàn bộ danh sách (idempotent).

Đã gỡ khi có đăng nhập (docs/specs/auth-multiuser.md): `/settings/current-users` (thay bằng
alias của từng user, admin quản lý) và `/settings/display-timezone` (thay bằng `PUT /me/timezone`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep, require_permission
from app.core.permissions import Permission
from app.schemas.settings import SyncUrlsBody, TimezoneList
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "/sync-urls",
    response_model=SyncUrlsBody,
    dependencies=[Depends(require_permission(Permission.INTEGRATION_MANAGE))],
    summary="URL file đồng bộ đã lưu (cài đặt toàn cục, chỉ admin)",
)
async def get_sync_urls(session: SessionDep) -> SyncUrlsBody:
    # Dòng đã lưu từ trước khi allowlist đổi có thể không còn hợp lệ; GET trả nguyên văn
    # (không validate lại) để người dùng còn thấy và xoá được. Nơi fetch phải kiểm lại.
    return SyncUrlsBody.model_construct(urls=await settings_service.get_sync_urls(session))


@router.put(
    "/sync-urls",
    response_model=SyncUrlsBody,
    dependencies=[Depends(require_permission(Permission.INTEGRATION_MANAGE))],
    summary="Ghi đè danh sách URL đồng bộ (chỉ admin)",
    description=(
        "Tối đa 50 URL, chỉ https, host thuộc allowlist (Google Docs/Sheets/Drive, "
        "SharePoint/OneDrive + SYNC_URL_EXTRA_HOSTS). Chống SSRF: server sẽ fetch các URL này. "
        "Link chia sẻ thường mang token trong query nên chỉ admin đọc/ghi."
    ),
)
async def put_sync_urls(body: SyncUrlsBody, session: SessionDep) -> SyncUrlsBody:
    return SyncUrlsBody(urls=await settings_service.set_sync_urls(session, body.urls))


@router.get(
    "/timezones",
    response_model=TimezoneList,
    summary="Danh mục múi giờ IANA",
    description=(
        "Không phân trang: đây là danh mục tĩnh khoảng 600 tên (dưới 25 KB), không phải dữ "
        "liệu người dùng tăng dần nên không thuộc quy tắc 50 dòng/trang."
    ),
)
async def list_timezones() -> TimezoneList:
    return settings_service.list_timezones()
