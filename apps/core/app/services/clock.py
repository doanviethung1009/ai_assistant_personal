"""Quy đổi thời gian.

DB lưu UTC. Khái niệm "hôm nay" là của người dùng, nên phải quy đổi qua
timezone hiển thị rồi mới suy ra khoảng UTC tương ứng.

Múi giờ hiển thị là MỘT giá trị duy nhất của server: env DISPLAY_TIMEZONE
(`settings.display_timezone`). Không có múi giờ theo user hay ghi đè trong DB, nên
`display_tz()` thuần đồng bộ, không cần session hay ContextVar; `TaskRead.is_overdue`
(computed field) và `task_sync_service._to_utc` gọi được từ mọi nơi.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo

from app.core.config import settings


@cache
def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def display_tz() -> ZoneInfo:
    """Múi giờ của server. Cache theo TÊN nên test đổi `settings.display_timezone` bằng
    monkeypatch có hiệu lực ngay, không cần xoá cache."""
    return _zone(settings.display_timezone)


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
