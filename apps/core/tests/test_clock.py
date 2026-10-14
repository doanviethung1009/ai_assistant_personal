"""services/clock.py: múi giờ của server, ranh giới ngày địa phương, hạn cả ngày.

Toàn bộ là phần thuần, không cần Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import settings
from app.services import clock


@pytest.fixture
def env_tz(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "display_timezone", "Asia/Ho_Chi_Minh")
    return "Asia/Ho_Chi_Minh"


def test_display_tz_falls_back_to_env(env_tz: str) -> None:
    assert clock.display_tz().key == env_tz


def test_display_tz_follows_settings_without_clearing_cache(
    env_tz: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "display_timezone", "Europe/Paris")
    assert clock.display_tz().key == "Europe/Paris"
    monkeypatch.setattr(settings, "display_timezone", "Asia/Tokyo")
    assert clock.display_tz().key == "Asia/Tokyo"


def test_display_timezone_env_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    def build() -> str:
        return Settings(_env_file=None).display_timezone  # type: ignore[call-arg]

    monkeypatch.delenv("DISPLAY_TIMEZONE", raising=False)
    monkeypatch.delenv("TZ", raising=False)
    assert build() == "Asia/Ho_Chi_Minh"
    monkeypatch.setenv("TZ", "Europe/Paris")
    assert build() == "Europe/Paris"
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Asia/Tokyo")
    assert build() == "Asia/Tokyo"
    monkeypatch.delenv("DISPLAY_TIMEZONE")
    monkeypatch.setenv("TZ", "Mars/Base")
    with pytest.raises(ValueError):
        build()


def test_display_timezone_blank_env_means_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    def build() -> str:
        return Settings(_env_file=None).display_timezone  # type: ignore[call-arg]

    monkeypatch.delenv("DISPLAY_TIMEZONE", raising=False)
    monkeypatch.setenv("TZ", "")
    assert build() == "Asia/Ho_Chi_Minh"
    monkeypatch.setenv("TZ", "   ")
    assert build() == "Asia/Ho_Chi_Minh"
    # DISPLAY_TIMEZONE rỗng không che TZ hợp lệ.
    monkeypatch.setenv("DISPLAY_TIMEZONE", "")
    monkeypatch.setenv("TZ", "Europe/Paris")
    assert build() == "Europe/Paris"
    # Khác rỗng mà sai tên vẫn fail-fast; DISPLAY_TIMEZONE thắng TZ.
    monkeypatch.setenv("TZ", "Mars/Base")
    monkeypatch.setenv("DISPLAY_TIMEZONE", "Asia/Tokyo")
    assert build() == "Asia/Tokyo"
    monkeypatch.delenv("DISPLAY_TIMEZONE")
    with pytest.raises(ValueError):
        build()


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
def test_local_day_bounds_extreme_offsets(
    tz: str, start: datetime, end: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "display_timezone", tz)
    assert clock.local_day_bounds_utc(date(2026, 10, 9)) == (start, end)


@pytest.mark.parametrize(("day", "hours"), [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_local_day_bounds_dst_days(
    day: date, hours: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "display_timezone", "America/New_York")
    start, end = clock.local_day_bounds_utc(day)
    assert end - start == timedelta(hours=hours)


def test_all_day_cutoff_is_midnight_utc_of_the_calendar_day() -> None:
    assert clock.today_all_day_cutoff(date(2026, 10, 9)) == datetime(2026, 10, 9, tzinfo=UTC)
