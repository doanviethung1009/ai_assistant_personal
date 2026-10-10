"""Cài đặt người dùng: tên của User (current_users), URL đồng bộ (sync_urls), múi giờ hiển thị.

Nằm dưới router cha có `require_api_key`. Chỉ cài đặt KHÔNG bí mật (xem
models/app_setting.py). PUT là ghi đè toàn bộ danh sách (idempotent).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.settings import (
    CurrentUsersBody,
    DisplayTimezoneBody,
    DisplayTimezoneRead,
    SyncUrlsBody,
    TimezoneList,
)
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "/current-users",
    response_model=CurrentUsersBody,
    summary="Tên của User (dùng cho view=mine)",
)
async def get_current_users(session: SessionDep) -> CurrentUsersBody:
    return CurrentUsersBody(names=await settings_service.get_current_users(session))


@router.put(
    "/current-users",
    response_model=CurrentUsersBody,
    summary="Ghi đè danh sách tên của User",
    description="Tối đa 20 tên, mỗi tên 1..200 ký tự sau khi strip, loại trùng.",
)
async def put_current_users(body: CurrentUsersBody, session: SessionDep) -> CurrentUsersBody:
    return CurrentUsersBody(names=await settings_service.set_current_users(session, body.names))


@router.get(
    "/sync-urls",
    response_model=SyncUrlsBody,
    summary="URL file đồng bộ đã lưu",
)
async def get_sync_urls(session: SessionDep) -> SyncUrlsBody:
    # Dòng đã lưu từ trước khi allowlist đổi có thể không còn hợp lệ; GET trả nguyên văn
    # (không validate lại) để người dùng còn thấy và xoá được. Nơi fetch phải kiểm lại.
    return SyncUrlsBody.model_construct(urls=await settings_service.get_sync_urls(session))


@router.put(
    "/sync-urls",
    response_model=SyncUrlsBody,
    summary="Ghi đè danh sách URL đồng bộ",
    description=(
        "Tối đa 50 URL, chỉ https, host thuộc allowlist (Google Docs/Sheets/Drive, "
        "SharePoint/OneDrive + SYNC_URL_EXTRA_HOSTS). Chống SSRF: server sẽ fetch các URL này."
    ),
)
async def put_sync_urls(body: SyncUrlsBody, session: SessionDep) -> SyncUrlsBody:
    return SyncUrlsBody(urls=await settings_service.set_sync_urls(session, body.urls))


@router.get(
    "/display-timezone",
    response_model=DisplayTimezoneRead,
    summary="Múi giờ hiển thị hiệu lực",
)
async def get_display_timezone(session: SessionDep) -> DisplayTimezoneRead:
    return await settings_service.get_display_timezone(session)


@router.put(
    "/display-timezone",
    response_model=DisplayTimezoneRead,
    summary="Đặt múi giờ hiển thị",
    description=(
        "Tên IANA (vd Asia/Ho_Chi_Minh). `timezone = null` xoá cài đặt, quay về mặc định env. "
        "409 khi đang có lần nhập dữ liệu giữ khoá ghi. Worker khác có thể thấy giá trị mới "
        "chậm tối đa 10 giây (cache)."
    ),
)
async def put_display_timezone(
    body: DisplayTimezoneBody, session: SessionDep
) -> DisplayTimezoneRead:
    return await settings_service.set_display_timezone(session, body.timezone)


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
