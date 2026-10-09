"""services/clock.py: múi giờ hiển thị lúc chạy, ranh giới ngày địa phương, hạn cả ngày.

Phần thuần chạy ở mọi nơi; phần đánh dấu `db` cần Postgres thật.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import clock


@pytest.fixture
def env_tz(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "display_timezone", "Asia/Ho_Chi_Minh")
    return "Asia/Ho_Chi_Minh"


def test_display_tz_falls_back_to_env(env_tz: str) -> None:
    assert clock.display_tz().key == env_tz


def test_display_tz_order_contextvar_then_cache_then_env(env_tz: str) -> None:
    clock._cache = (ZoneInfo("Europe/Paris"), clock.time_module.monotonic() + 100)
    assert clock.display_tz().key == "Europe/Paris"  # cache thắng env
    clock.set_request_tz(ZoneInfo("Asia/Tokyo"))
    assert clock.display_tz().key == "Asia/Tokyo"  # ContextVar thắng cache
    clock.invalidate_display_tz_cache()
    assert clock.display_tz().key == env_tz


def test_cache_expires_after_ttl(env_tz: str, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(clock, "time_module", SimpleNamespace(monotonic=lambda: now[0]))
    clock._cache = (ZoneInfo("Europe/Paris"), now[0] + clock.CACHE_TTL_SECONDS)
    assert clock.CACHE_TTL_SECONDS == 10
    now[0] += clock.CACHE_TTL_SECONDS - 0.1
    assert clock.display_tz().key == "Europe/Paris"
    now[0] += 0.2
    assert clock.display_tz().key == env_tz


@pytest.mark.parametrize(
    ("tz", "start", "end"),
    [
        # UTC+14: ngày 09/10 địa phương bắt đầu 10:00Z ngày 08/10.
        (
            "Pacific/Kiritimati",
            datetime(2026, 10, 8, 10, tzinfo=UTC),
            datetime(2026, 10, 9, 10, tzinfo=UTC),
        ),
        # UTC-12: bắt đầu 12:00Z cùng ngày.
        (
            "Etc/GMT+12",
            datetime(2026, 10, 9, 12, tzinfo=UTC),
            datetime(2026, 10, 10, 12, tzinfo=UTC),
        ),
    ],
)
def test_local_day_bounds_extreme_offsets(tz: str, start: datetime, end: datetime) -> None:
    clock.set_request_tz(ZoneInfo(tz))
    assert clock.local_day_bounds_utc(date(2026, 10, 9)) == (start, end)


@pytest.mark.parametrize(("day", "hours"), [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_local_day_bounds_dst_days(day: date, hours: int) -> None:
    clock.set_request_tz(ZoneInfo("America/New_York"))
    start, end = clock.local_day_bounds_utc(day)
    assert end - start == timedelta(hours=hours)


def test_all_day_cutoff_is_midnight_utc_of_the_calendar_day() -> None:
    assert clock.today_all_day_cutoff(date(2026, 10, 9)) == datetime(2026, 10, 9, tzinfo=UTC)


@pytest.mark.db
async def test_load_display_tz_reads_db_and_binds_request(session: AsyncSession) -> None:
    await session.execute(
        text("INSERT INTO app_settings (key, value) VALUES ('display_timezone', '\"Asia/Tokyo\"')")
    )
    await session.commit()
    assert (await clock.load_display_tz(session)).key == "Asia/Tokyo"
    assert clock.display_tz().key == "Asia/Tokyo"


@pytest.mark.db
async def test_load_display_tz_ignores_corrupt_row(
    session: AsyncSession, env_tz: str, caplog: pytest.LogCaptureFixture
) -> None:
    await session.execute(
        text("INSERT INTO app_settings (key, value) VALUES ('display_timezone', '\"Mars/Base\"')")
    )
    await session.commit()
    assert (await clock.load_display_tz(session)).key == env_tz
    assert "không hợp lệ" in caplog.text
