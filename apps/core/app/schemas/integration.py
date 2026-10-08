"""Schema của kết nối tích hợp.

══════════════════════════════════════════════════════════════════════
 TOKEN LÀ WRITE-ONLY. Nó chỉ có ở schema ghi (Create/Update) dưới dạng SecretStr; schema
 đọc (`IntegrationRead`) không có trường token/ciphertext, chỉ `has_secret` và
 `secret_last4`. Thông báo lỗi validate KHÔNG được chứa giá trị token (và handler 422 ở
 main.py còn bỏ `input` cho /api/v1/integrations).
══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.models.enums import IntegrationKind

MIN_TOKEN_LEN = 8
MAX_TOKEN_LEN = 512
MAX_BASE_URL_LEN = 2048

_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
# Tên nội bộ/loopback theo ĐUÔI tên miền. Chặn theo tên là hàng rào mức literal; phân
# giải DNS để chặn host trỏ vào IP private là việc của B4b (lúc thực sự gọi ra ngoài).
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".localdomain",
    ".lan",
    ".intranet",
    ".home.arpa",
)


def validate_base_url(raw: str) -> str:
    """Kiểm và chuẩn hoá `base_url` về dạng `https://host` (chống SSRF mức literal).

    Chấp nhận: https, tên miền ASCII có ít nhất một dấu chấm, cổng vắng hoặc 443, path
    rỗng hoặc `/`. Từ chối: http, IP literal (v4/v6, kể cả dạng số/hex mà OS vẫn hiểu
    là IP), localhost và các đuôi nội bộ, userinfo, cổng lạ, path/query/fragment, ký tự
    điều khiển, tên miền Unicode (phải dùng punycode `xn--`).

    GIỚI HẠN B4a: chỉ chặn theo tên host literal. Host công khai nhưng phân giải ra IP
    private (DNS rebinding) chưa bị chặn ở đây; B4b phải phân giải và kiểm IP lúc gọi.

    Raises:
        ValueError: thông báo tiếng Việt, không chứa giá trị đầu vào.
    """
    candidate = raw.strip()
    if not candidate:
        raise ValueError("base_url không được rỗng")
    if len(candidate) > MAX_BASE_URL_LEN:
        raise ValueError("base_url quá dài")
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F or ch == "\\" for ch in candidate):
        raise ValueError("base_url chứa ký tự không hợp lệ")
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise ValueError("base_url không phải URL hợp lệ") from None
    if parts.scheme.lower() != "https":
        raise ValueError("base_url chỉ chấp nhận https")
    if not host:
        raise ValueError("base_url thiếu tên miền")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValueError("base_url không được chứa user:password")
    if parts.query or parts.fragment or "?" in candidate or "#" in candidate:
        raise ValueError("base_url không được có query hoặc fragment")
    if parts.path not in ("", "/"):
        raise ValueError("base_url chỉ gồm tên miền, không có path")
    if port not in (None, 443):
        raise ValueError("base_url chỉ chấp nhận cổng 443")
    # netloc phải đúng là host hoặc host:443: chặn `host:` rỗng, ngoặc vuông IPv6, v.v.
    if parts.netloc.lower() not in (host, f"{host}:443"):
        raise ValueError("base_url không hợp lệ")
    return f"https://{_validate_host(host)}"


def _validate_host(host: str) -> str:
    if not host.isascii():
        raise ValueError("tên miền phải là ASCII (dùng dạng punycode xn--)")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("base_url không được là địa chỉ IP, hãy dùng tên miền")
    if host.endswith("."):
        raise ValueError("tên miền không được kết thúc bằng dấu chấm")
    if len(host) > 253 or "." not in host:
        raise ValueError("tên miền không hợp lệ (cần dạng ten.mien.com)")
    labels = host.split(".")
    if not all(_LABEL_RE.match(label) for label in labels):
        raise ValueError("tên miền chứa ký tự không hợp lệ")
    # `2130706433`, `0x7f.1`, `127.1`: getaddrinfo vẫn hiểu là IP. Nhãn cuối của tên miền
    # thật không bao giờ toàn chữ số hay dạng 0x...
    last = labels[-1]
    if last.isdigit() or re.fullmatch(r"0x[0-9a-f]*", last):
        raise ValueError("base_url không được là địa chỉ IP, hãy dùng tên miền")
    if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        raise ValueError("base_url không được trỏ tới host nội bộ")
    return host


def reject_control_chars(value: str, field: str, *, allow_whitespace: bool = False) -> str:
    """Từ chối NUL và ký tự điều khiển (Cc: C0, DEL, C1).

    WHY: Postgres không lưu U+0000 trong text/JSONB (ném lỗi => 500), còn xuống dòng/ESC
    trong tên hiển thị dùng để giả dòng log hoặc làm bẩn UI. `allow_whitespace` cho
    JQL nhiều dòng (\t \n \r).
    """
    for ch in value:
        if unicodedata.category(ch) == "Cc" and not (allow_whitespace and ch in "\t\n\r"):
            raise ValueError(f"{field} chứa ký tự điều khiển")
    return value


def _strip_or_none(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    return value


class JiraConfig(BaseModel):
    """`config` của kết nối Jira. Khoá lạ bị từ chối để không nhét secret vào đây."""

    model_config = ConfigDict(extra="forbid")

    jql: str | None = Field(default=None, max_length=2000)
    project_key: str | None = Field(default=None, max_length=100)
    project_name: str | None = Field(default=None, max_length=200)

    _blank_to_none = field_validator("jql", "project_key", "project_name", mode="before")(
        _strip_or_none
    )

    @field_validator("jql")
    @classmethod
    def _clean_jql(cls, value: str | None) -> str | None:
        return None if value is None else reject_control_chars(value, "jql", allow_whitespace=True)

    @field_validator("project_key", "project_name")
    @classmethod
    def _clean_project_fields(cls, value: str | None, info: ValidationInfo) -> str | None:
        return None if value is None else reject_control_chars(value, str(info.field_name))


class _SecretInput(BaseModel):
    """Phần dùng chung cho schema ghi có token."""

    # repr=False + SecretStr: model bị in ra log/traceback cũng không lộ token.
    token: SecretStr | None = Field(
        default=None,
        repr=False,
        description="API token, chỉ ghi. Rỗng hoặc null = không đổi token đang lưu.",
    )

    @field_validator("token", mode="before")
    @classmethod
    def _blank_token_is_unset(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("token")
    @classmethod
    def _token_length(cls, value: SecretStr | None) -> SecretStr | None:
        # Thông báo không chứa token. Độ dài tối thiểu cũng để `secret_last4` không
        # lộ gần hết một token ngắn.
        if value is None:
            return value
        if not MIN_TOKEN_LEN <= len(value.get_secret_value()) <= MAX_TOKEN_LEN:
            raise ValueError(f"token phải dài {MIN_TOKEN_LEN}-{MAX_TOKEN_LEN} ký tự")
        return value


class _ConnectionFields(BaseModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        # None chỉ tới được đây ở IntegrationUpdate (null tường minh); _check từ chối sau.
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name không được rỗng")
        return reject_control_chars(stripped, "name")

    @field_validator("base_url", check_fields=False)
    @classmethod
    def _clean_base_url(cls, value: str | None) -> str | None:
        return None if value is None else validate_base_url(value)

    @field_validator("account_email", check_fields=False)
    @classmethod
    def _clean_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not _EMAIL_RE.match(stripped):
            raise ValueError("account_email không hợp lệ")
        return reject_control_chars(stripped, "account_email")


class IntegrationCreate(_ConnectionFields, _SecretInput):
    kind: IntegrationKind = IntegrationKind.JIRA
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(description="https://<tên miền>, không IP, không path")
    account_email: str = Field(min_length=3, max_length=200)
    config: JiraConfig = Field(default_factory=JiraConfig)


class IntegrationUpdate(_ConnectionFields, _SecretInput):
    """Patch bán phần: khoá vắng thì giữ nguyên. `kind` không đổi được."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = None
    account_email: str | None = Field(default=None, min_length=3, max_length=200)
    config: JiraConfig | None = Field(
        default=None, description="Có gửi thì THAY toàn bộ config, không gộp."
    )
    clear_token: bool = Field(
        default=False, description="true = xoá token đang lưu. Không dùng cùng `token`."
    )

    @model_validator(mode="after")
    def _check(self) -> IntegrationUpdate:
        # Cột NOT NULL: null tường minh phải là 422 chứ không để DB ném 500.
        for name in ("name", "base_url", "account_email", "config"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} không được null")
        if self.clear_token and self.token is not None:
            raise ValueError("không gửi token cùng lúc với clear_token")
        return self


class IntegrationRead(BaseModel):
    """Kết nối trả cho client. KHÔNG có token hay ciphertext, dưới mọi hình thức."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: IntegrationKind
    name: str
    base_url: str
    account_email: str
    config: dict[str, Any]
    has_secret: bool
    secret_last4: str | None
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SyncMessage(BaseModel):
    """Một lỗi/cảnh báo của lần đồng bộ. `reason` là câu TỰ VIẾT, không chứa nội dung Jira."""

    index: int | None = Field(
        default=None, description="Vị trí issue trong dữ liệu đã tải (từ 0); null = cả lần sync"
    )
    external_id: str | None = Field(default=None, description="Khoá issue (PROJ-123) nếu có")
    reason: str


class SyncResult(BaseModel):
    fetched: int = Field(description="Số issue Jira đã tải (kể cả issue bị loại do lỗi)")
    pages: int
    added: int
    updated: int
    unchanged: int
    skipped_personal: int = Field(
        description="Trùng khoá với task scope=personal nên bị bỏ qua, không ghi đè"
    )
    errors: list[SyncMessage] = Field(default_factory=list)
    warnings: list[SyncMessage] = Field(default_factory=list)
    truncated: bool = Field(
        description="Chạm trần 100 trang: chưa lấy hết, và last_sync_at không được cập nhật"
    )
