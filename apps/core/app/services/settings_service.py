"""Đọc/ghi cài đặt toàn cục (app_settings: sync_urls) và danh sách assignee.

`current_users` và `display_timezone` KHÔNG còn được đọc/ghi ở đây: chúng thành alias và múi giờ
của từng user (bảng `users`/`user_aliases`). Dòng cũ trong app_settings được CLI bootstrap sao chép
đi rồi để nguyên (downgrade code cũ vẫn chạy).

Chỉ nhận khoá khai báo ở `SettingKey`. Dữ liệu vào đã được chuẩn hoá ở
`schemas/settings.py` (cùng luật với đường nhập file).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezones import utc_offset_minutes, valid_timezone_names
from app.db import locks
from app.models.app_setting import AppSetting
from app.models.enums import SettingKey, TaskScope
from app.models.task import Task
from app.schemas.settings import TimezoneList, TimezoneOption, normalize_urls
from app.services.task_service import _alive

# Chặn kích thước danh sách assignee: DISTINCT trên cột có thể phình khi Jira sync kéo
# hàng trăm người. Đủ cho dropdown/chọn "tôi là ai"; vượt thì cắt theo thứ tự chữ cái.
MAX_ASSIGNEES = 500

# Tên khoá và cách chờ nằm ở db/locks.py (dùng chung với nhập và upsert-batch). Giữ tên
# ở đây vì import_service và test tham chiếu qua module này.
IMPORT_LOCK_NAME = locks.IMPORT_LOCK_NAME
# Chờ khoá tối đa bấy lâu rồi 409, thay vì treo request khi có lần nhập lớn đang chạy.
SETTINGS_LOCK_TIMEOUT = "5s"


async def get_value(session: AsyncSession, key: SettingKey) -> Any | None:
    """Giá trị thô của một cài đặt, None nếu chưa từng lưu."""
    return await session.scalar(select(AppSetting.value).where(AppSetting.key == key.value))


async def _get_list(session: AsyncSession, key: SettingKey) -> list[str]:
    value = await get_value(session, key)
    # Phòng dòng bị sửa tay thành kiểu khác: trả rỗng thay vì làm vỡ web.
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


async def put_value(session: AsyncSession, key: SettingKey, value: Any) -> None:
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


async def put_list(session: AsyncSession, key: SettingKey, value: list[str]) -> None:
    """Ghi cài đặt dạng danh sách chuỗi (xem `put_value`)."""
    await put_value(session, key, value)


async def get_sync_urls(session: AsyncSession) -> list[str]:
    return await _get_list(session, SettingKey.SYNC_URLS)


async def set_sync_urls(session: AsyncSession, urls: list[str]) -> list[str]:
    """Ghi đè toàn bộ danh sách URL; kiểm https + allowlist (SSRF) trước khi lưu."""
    clean = normalize_urls(urls)
    await locks.take_import_write_lock(session, lock_timeout=SETTINGS_LOCK_TIMEOUT)
    await put_list(session, SettingKey.SYNC_URLS, clean)
    return clean


def list_timezones() -> TimezoneList:
    """Danh mục IANA. Không phân trang: ~600 tên tĩnh (< 25 KB), không phải dữ liệu tăng dần."""
    items = [
        TimezoneOption(name=name, utc_offset_minutes=utc_offset_minutes(name))
        for name in sorted(valid_timezone_names())
    ]
    return TimezoneList(items=items, total=len(items))


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
