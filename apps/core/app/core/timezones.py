"""Kiểm tra tên múi giờ IANA. Hàm thuần, không phụ thuộc config nên `config.py` dùng được.

Nguồn DUY NHẤT của luật "tên múi giờ hợp lệ": validator env, API PUT và đường nhập
file cùng gọi `normalize_timezone`, nên giá trị API từ chối không lọt vào DB qua cửa khác.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

MAX_TIMEZONE_LEN = 64

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
# `Factory` và `localtime` có trong tzdata nhưng không phải múi giờ người dùng chọn được.
_EXCLUDED = frozenset({"Factory", "localtime"})


@lru_cache(maxsize=1)
def valid_timezone_names() -> frozenset[str]:
    """Tập tên hợp lệ, tính một lần (quét tzdata tốn vài chục ms)."""
    return frozenset(available_timezones() - _EXCLUDED)


def normalize_timezone(value: str) -> str:
    """Strip rồi kiểm tên IANA; trả tên chuẩn. Raise ValueError (thông điệp tiếng Việt)."""
    if not isinstance(value, str):
        raise ValueError("Múi giờ phải là chuỗi")
    name = value.strip()
    if not name:
        raise ValueError("Múi giờ không được rỗng")
    if len(name) > MAX_TIMEZONE_LEN:
        raise ValueError(f"Múi giờ tối đa {MAX_TIMEZONE_LEN} ký tự")
    if _CONTROL_CHARS.search(name):
        raise ValueError("Múi giờ không được chứa ký tự điều khiển")
    if name not in valid_timezone_names():
        raise ValueError("Múi giờ không nằm trong danh sách IANA")
    return name


def utc_offset_minutes(name: str, at: datetime | None = None) -> int:
    """Offset của múi giờ so với UTC tại thời điểm `at` (mặc định: bây giờ), đơn vị phút."""
    moment = (at or datetime.now(UTC)).astimezone(ZoneInfo(name))
    offset = moment.utcoffset()
    return int(offset.total_seconds() // 60) if offset is not None else 0
