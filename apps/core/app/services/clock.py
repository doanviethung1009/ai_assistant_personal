"""Quy đổi thời gian.

DB lưu UTC. Khái niệm "hôm nay" là của người dùng, nên phải quy đổi qua
timezone hiển thị rồi mới suy ra khoảng UTC tương ứng.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


def display_tz() -> ZoneInfo:
    return ZoneInfo(settings.display_timezone)


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
