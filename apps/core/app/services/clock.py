"""Quy đổi thời gian.

DB lưu UTC. Khái niệm "hôm nay" là của người dùng, nên phải quy đổi qua
timezone hiển thị rồi mới suy ra khoảng UTC tương ứng.

Múi giờ hiển thị là cài đặt lúc chạy (dòng app_settings 'display_timezone'), mặc định
là env DISPLAY_TIMEZONE. Thứ tự tra của `display_tz()`:
  1. ContextVar của request hiện tại (đặt bởi `load_display_tz` qua dependency
     `api.deps.bind_display_tz`): mọi phép tính trong MỘT request dùng cùng một múi giờ.
  2. Cache tiến trình còn hạn (TTL 10 giây).
  3. Env.
`display_tz()` giữ chữ ký đồng bộ vì `TaskRead.is_overdue` (computed field) và
`task_sync_service._to_utc` gọi từ chỗ không có session.
"""

from __future__ import annotations

import logging
import time as time_module
from contextvars import ContextVar
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timezones import normalize_timezone
from app.models.app_setting import AppSetting
from app.models.enums import SettingKey

logger = logging.getLogger(__name__)

# Hai worker uvicorn có hai cache riêng: worker kia thấy giá trị mới chậm tối đa chừng này.
CACHE_TTL_SECONDS = 10.0

_request_tz: ContextVar[ZoneInfo | None] = ContextVar("display_tz_request", default=None)
# (múi giờ, thời điểm hết hạn theo time.monotonic)
_cache: tuple[ZoneInfo, float] | None = None


def _default_tz() -> ZoneInfo:
    return ZoneInfo(settings.display_timezone)


def _cached() -> ZoneInfo | None:
    if _cache is not None and time_module.monotonic() < _cache[1]:
        return _cache[0]
    return None


def display_tz() -> ZoneInfo:
    return _request_tz.get() or _cached() or _default_tz()


def is_display_tz_cached() -> bool:
    return _cached() is not None


async def load_display_tz(session: AsyncSession | None) -> ZoneInfo:
    """Đọc múi giờ hiệu lực (cache còn hạn thì khỏi hỏi DB) và gắn cho request hiện tại.

    `session` chỉ được None khi cache còn hạn (xem `is_display_tz_cached`).
    """
    global _cache
    tz = _cached()
    if tz is None:
        if session is None:
            tz = _default_tz()
            _request_tz.set(tz)
            return tz
        raw = await session.scalar(
            select(AppSetting.value).where(AppSetting.key == SettingKey.DISPLAY_TIMEZONE.value)
        )
        tz = _default_tz()
        if raw is not None:
            try:
                tz = ZoneInfo(normalize_timezone(raw))
            except (ValueError, TypeError, OSError):
                # Dòng bị sửa tay hoặc tên bị tzdata gỡ: rơi về env, không làm vỡ request.
                logger.warning("display_timezone trong DB không hợp lệ, dùng giá trị env")
        _cache = (tz, time_module.monotonic() + CACHE_TTL_SECONDS)
    _request_tz.set(tz)
    return tz


def invalidate_display_tz_cache() -> None:
    """Gọi sau khi ghi setting. Chỉ có tác dụng ở worker đang xử lý request ghi."""
    global _cache
    _cache = None
    _request_tz.set(None)


def set_request_tz(tz: ZoneInfo) -> None:
    """Ép múi giờ cho request hiện tại (dùng sau khi chính request này vừa đổi setting)."""
    _request_tz.set(tz)


def now_utc() -> datetime:
    return datetime.now(UTC)


def local_today() -> date:
    return datetime.now(display_tz()).date()


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Trả về [đầu ngày, đầu ngày kế tiếp) của một ngày địa phương, theo UTC."""
    tz = display_tz()
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def today_all_day_cutoff(today: date) -> datetime:
    """Mốc so cho hạn CẢ NGÀY: `due_at` lưu 00:00 UTC của ngày lịch, nên ngày hạn < hôm nay
    (địa phương) khi và chỉ khi `due_at` < 00:00 UTC của chính ngày `today`."""
    return datetime.combine(today, time.min, tzinfo=UTC)
