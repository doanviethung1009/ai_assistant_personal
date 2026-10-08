"""Schema và chuẩn hoá cho cài đặt người dùng (current_users, sync_urls).

Hàm `normalize_names` và `normalize_urls` là NGUỒN DUY NHẤT của luật hợp lệ: API
PUT và bước nhập file (import_service) cùng gọi, để một giá trị bị API từ chối
không thể lọt vào DB qua đường nhập.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.core.url_allowlist import check_sync_url

MAX_USER_NAMES = 20
MAX_NAME_LEN = 200
MAX_SYNC_URLS = 50

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

# Lý do từ chối URL -> thông điệp tiếng Việt. Không bao giờ chèn URL vào thông điệp:
# link chia sẻ thường chứa token trong query string.
_URL_REASON_TEXT = {
    "too_long": "quá dài",
    "bad_chars": "chứa khoảng trắng hoặc ký tự điều khiển",
    "malformed": "không đúng dạng URL",
    "not_https": "chỉ chấp nhận https",
    "bad_netloc": "địa chỉ không hợp lệ (cấm user:pass@, cổng lạ, ký tự ngoài ASCII)",
    "ip_literal": "không chấp nhận địa chỉ IP",
    "host_not_allowed": "host không nằm trong danh sách cho phép",
}


def normalize_names(raw: Any) -> list[str]:
    """Chuẩn hoá danh sách tên người dùng: strip, 1..200 ký tự, loại trùng, tối đa 20.

    Vì sao nghiêm: `view=mine` so khớp assignee CHÍNH XÁC với các tên này, nên tên có
    khoảng trắng thừa sẽ không bao giờ khớp. Tên rỗng là lỗi chứ không lặng lẽ bỏ,
    để người dùng biết dữ liệu mình gửi bị sai.
    Raise ValueError (thông điệp tiếng Việt, không chứa giá trị gốc).
    """
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise ValueError("names phải là danh sách chuỗi")
    if len(raw) > MAX_USER_NAMES:
        raise ValueError(f"Tối đa {MAX_USER_NAMES} tên")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("Mỗi tên phải là chuỗi")
        name = item.strip()
        if not name:
            raise ValueError("Tên không được rỗng")
        if len(name) > MAX_NAME_LEN:
            raise ValueError(f"Tên tối đa {MAX_NAME_LEN} ký tự")
        if _CONTROL_CHARS.search(name):
            raise ValueError("Tên không được chứa ký tự điều khiển")
        if name not in out:
            out.append(name)
    return out


def normalize_urls(raw: Any) -> list[str]:
    """Chuẩn hoá danh sách URL đồng bộ: strip, loại trùng, tối đa 50, chỉ https + allowlist.

    Kiểm lúc LƯU (ở đây) và phải kiểm lại lúc FETCH ở nơi gọi (web): allowlist có thể
    đổi sau khi lưu, và redirect có thể đưa tới host khác.
    Raise ValueError (thông điệp tiếng Việt, không chứa URL).
    """
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise ValueError("urls phải là danh sách chuỗi")
    if len(raw) > MAX_SYNC_URLS:
        raise ValueError(f"Tối đa {MAX_SYNC_URLS} URL")
    out: list[str] = []
    for position, item in enumerate(raw, start=1):
        if not isinstance(item, str):
            raise ValueError("Mỗi URL phải là chuỗi")
        url = item.strip()
        reason = check_sync_url(url, settings.sync_url_extra_hosts)
        if reason is not None:
            raise ValueError(f"URL thứ {position} bị từ chối: {_URL_REASON_TEXT[reason]}")
        if url not in out:
            out.append(url)
    return out


class CurrentUsersBody(BaseModel):
    """Danh sách tên của chính User, dùng để lọc `view=mine`/`owner`."""

    model_config = ConfigDict(extra="forbid")

    # max_length chặn payload khổng lồ trước khi validator chạy; luật chi tiết ở normalize_names.
    names: list[str] = Field(max_length=MAX_USER_NAMES)

    @field_validator("names", mode="after")
    @classmethod
    def _names(cls, value: list[str]) -> list[str]:
        return normalize_names(value)


class SyncUrlsBody(BaseModel):
    """Danh sách URL file đồng bộ (Google Sheets, SharePoint...)."""

    model_config = ConfigDict(extra="forbid")

    urls: list[str] = Field(max_length=MAX_SYNC_URLS)

    @field_validator("urls", mode="after")
    @classmethod
    def _urls(cls, value: list[str]) -> list[str]:
        return normalize_urls(value)
