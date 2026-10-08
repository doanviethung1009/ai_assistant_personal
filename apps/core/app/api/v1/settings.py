"""Cài đặt người dùng: tên của User (current_users) và URL đồng bộ (sync_urls).

Nằm dưới router cha có `require_api_key`. Chỉ cài đặt KHÔNG bí mật (xem
models/app_setting.py). PUT là ghi đè toàn bộ danh sách (idempotent).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.settings import CurrentUsersBody, SyncUrlsBody
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
