"""Schema của lịch sử duyệt web.

Mảng `items` của batch khai thẳng model dòng và tối đa 10 000 phần tử: vượt thì 422
trước khi service chạm DB. URL sai (không http/https, quá dài) KHÔNG làm hỏng cả lô;
service bỏ và đếm vào `invalid`.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_BATCH_ITEMS = 10_000
MAX_PROFILE_LEN = 200
_MAX_INT32 = 2_147_483_647
# Ký tự điều khiển (kể cả xuống dòng) không có chỗ trong tên thư mục profile.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def clean_profile(value: str) -> str:
    """Chuẩn hoá tên profile; từ chối thứ trông như đường dẫn.

    Profile chỉ là nhãn ("Default", "Profile 1"). Đường dẫn tuyệt đối sẽ làm lộ cấu trúc
    thư mục máy người dùng vào DB và vào UI, nên chặn ở cửa vào thay vì tin client.
    """
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("profile không được rỗng")
    if len(cleaned) > MAX_PROFILE_LEN:
        raise ValueError(f"profile tối đa {MAX_PROFILE_LEN} ký tự")
    if "/" in cleaned or "\\" in cleaned or _WINDOWS_DRIVE.match(cleaned):
        raise ValueError("profile là tên thư mục, không được chứa đường dẫn")
    if cleaned in {".", ".."} or _CONTROL.search(cleaned):
        raise ValueError("profile không hợp lệ")
    return cleaned


class BrowserHistoryItem(BaseModel):
    """Một dòng của batch. `last_visit_at` không múi giờ được hiểu là giờ display_timezone."""

    # 8192 > MAX_URL_LEN (4096) có chủ ý: URL 4097-8192 ký tự được đếm `invalid` thay vì
    # làm cả lô trả 422; chuẩn hoá vẫn chặn > 4096.
    url: str = Field(min_length=1, max_length=8192)
    title: str | None = Field(default=None, max_length=8000)
    visit_count: int = Field(default=0, ge=0, le=_MAX_INT32)
    last_visit_at: datetime


class BrowserHistoryBatch(BaseModel):
    profile: str
    items: list[BrowserHistoryItem] = Field(max_length=MAX_BATCH_ITEMS)

    @field_validator("profile")
    @classmethod
    def _profile(cls, value: str) -> str:
        return clean_profile(value)


class BrowserHistoryBatchResult(BaseModel):
    received: int
    created: int
    updated: int
    # Dòng đã có sẵn và không có số liệu mới hơn (gửi lại cùng lô thì toàn bộ rơi vào đây).
    # Gồm cả các dòng trùng URL đã được gộp lại trong cùng lô.
    unchanged: int
    # Bỏ qua: URL không phải http/https, quá dài, hoặc không phân tích được.
    invalid: int


class BrowserHistoryRead(BaseModel):
    id: uuid.UUID
    profile: str
    url: str
    title: str
    visit_count: int
    last_visit_at: datetime
    synced_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BrowserHistoryDeleteResult(BaseModel):
    deleted: int


class BrowserHistoryImportReport(BrowserHistoryBatchResult):
    """Báo cáo nhập `chrome-history.json`; dry_run chỉ đếm, không ghi."""

    dry_run: bool
    committed: bool
    profile: str
    # sha256 của body thô, để đối chiếu file đã kiểm tra với file nhập thật.
    file_sha256: str


# ═══════════════════════════════════════════════════════════════════════
#  File chrome-history.json (do web ghi ở chế độ file)
# ═══════════════════════════════════════════════════════════════════════

MAX_IMPORT_ITEMS = 50_000


class ChromeHistoryFile(BaseModel):
    """Envelope của `chrome-history.json`.

    `source_path` là đường dẫn tuyệt đối trên máy người dùng: cố ý KHÔNG khai thành
    field, nên không bao giờ được đọc hay lưu. `items` để dict thô vì một dòng hỏng
    phải được đếm vào `invalid` chứ không làm cả file trả 422.
    """

    model_config = ConfigDict(extra="ignore")

    synced_at: str | None = None
    items: list[dict[str, Any]] = Field(max_length=MAX_IMPORT_ITEMS)


class ChromeHistoryRow(BaseModel):
    """Một dòng của file; `last_visit_time` là giờ địa phương không múi giờ."""

    model_config = ConfigDict(extra="ignore")

    url: str = Field(min_length=1)
    title: str | None = None
    visit_count: int = Field(default=0, ge=0, le=_MAX_INT32)
    last_visit_time: datetime
