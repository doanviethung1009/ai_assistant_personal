"""Đọc/ghi cài đặt người dùng (app_settings) và danh sách assignee.

Chỉ nhận khoá khai báo ở `SettingKey`. Dữ liệu vào đã được chuẩn hoá ở
`schemas/settings.py` (cùng luật với đường nhập file).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.enums import SettingKey, TaskScope
from app.models.task import Task
from app.schemas.settings import normalize_names, normalize_urls
from app.services.task_service import _alive

# Chặn kích thước danh sách assignee: DISTINCT trên cột có thể phình khi Jira sync kéo
# hàng trăm người. Đủ cho dropdown/chọn "tôi là ai"; vượt thì cắt theo thứ tự chữ cái.
MAX_ASSIGNEES = 500


async def get_value(session: AsyncSession, key: SettingKey) -> Any | None:
    """Giá trị thô của một cài đặt, None nếu chưa từng lưu."""
    return await session.scalar(select(AppSetting.value).where(AppSetting.key == key.value))


async def _get_list(session: AsyncSession, key: SettingKey) -> list[str]:
    value = await get_value(session, key)
    # Phòng dòng bị sửa tay thành kiểu khác: trả rỗng thay vì làm vỡ web.
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


async def put_list(session: AsyncSession, key: SettingKey, value: list[str]) -> None:
    """Upsert một dòng. `updated_at` đặt tường minh vì ON CONFLICT không kích hoạt `onupdate`.

    KHÔNG chuẩn hoá: người gọi phải đưa giá trị đã qua `normalize_*` (API và đường nhập
    file đều đã làm). Dùng chung với import_service để hai đường ghi cùng một câu lệnh.
    """
    stmt = pg_insert(AppSetting).values(key=key.value, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppSetting.key],
        set_={"value": stmt.excluded.value, "updated_at": func.now()},
    )
    await session.execute(stmt)


async def get_current_users(session: AsyncSession) -> list[str]:
    return await _get_list(session, SettingKey.CURRENT_USERS)


async def set_current_users(session: AsyncSession, names: list[str]) -> list[str]:
    """Ghi đè toàn bộ danh sách. Chuẩn hoá lại ở đây để service an toàn khi gọi ngoài API."""
    clean = normalize_names(names)
    await put_list(session, SettingKey.CURRENT_USERS, clean)
    return clean


async def get_sync_urls(session: AsyncSession) -> list[str]:
    return await _get_list(session, SettingKey.SYNC_URLS)


async def set_sync_urls(session: AsyncSession, urls: list[str]) -> list[str]:
    """Ghi đè toàn bộ danh sách URL; kiểm https + allowlist (SSRF) trước khi lưu."""
    clean = normalize_urls(urls)
    await put_list(session, SettingKey.SYNC_URLS, clean)
    return clean


async def list_assignees(session: AsyncSession) -> list[str]:
    """Assignee khác nhau của task công việc CÒN SỐNG.

    Chỉ `scope = 'work'`: task cá nhân không có khái niệm giao cho ai, và tên trong đó
    không nên lọt vào danh sách chọn "tôi là ai" của team. Task trong thùng rác bị loại
    (`_alive`) để người đã rời đi không còn hiện sau khi xoá hết task của họ.
    """
    stmt = (
        select(Task.assignee)
        .where(_alive(), Task.scope == TaskScope.WORK, Task.assignee.is_not(None))
        .distinct()
        .order_by(Task.assignee)
        .limit(MAX_ASSIGNEES)
    )
    return list((await session.scalars(stmt)).all())
