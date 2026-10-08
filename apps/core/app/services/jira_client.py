"""Connector Jira: dựng JQL an toàn và phân trang `POST /rest/api/3/search/jql`.

══════════════════════════════════════════════════════════════════════
 CHẠM SECRET VÀ GỌI RA NGOÀI. Quy tắc cứng:
 - Token chỉ tồn tại trong `JiraClient._auth` (chuỗi Basic) và chỉ gắn vào header của từng
   request; không log, không đưa vào exception, repr, URL. Exception ở đây có message TỰ
   VIẾT và `raise ... from None`: không bao giờ chuyển tiếp message của httpx/httpcore hay
   BODY của Jira (body có thể echo header, JQL, hoặc nội dung nhạy cảm).
 - Mọi request đi qua transport do người gọi đưa vào; ở production là
   `ssrf_guard.PinnedTransport` (kiểm IP + ghim IP + chỉ host của base_url). Client luôn
   `follow_redirects=False` và `trust_env=False` (proxy sẽ vòng qua chốt SSRF).
 - 3xx là lỗi, KHÔNG theo: theo redirect sang host khác sẽ gửi Authorization cho host đó.
 - Trần: 100 trang x 100 issue, 30 giây mỗi request, 5 phút cả lần sync, 10 MB mỗi trang
   (đọc theo luồng, dừng ngay khi vượt, không dựa vào Content-Length), 50 MB cả lần sync.
 - Response nén (Content-Encoding khác identity) bị từ chối: chống decompression bomb.
 - Lỗi mạng (DNS, bị chặn SSRF, kết nối, timeout) dùng MỘT thông báo cố định; nguyên nhân
   chỉ ghi log server, để không thành oracle dò mạng nội bộ.
══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import httpx

from app.services.errors import DomainError, ValidationError
from app.services.jira_mapping import CUSTOM_TAG_FIELD
from app.services.ssrf_guard import NetworkUnavailableError

logger = logging.getLogger(__name__)

MAX_PAGES: Final = 100
PAGE_SIZE: Final = 100
REQUEST_TIMEOUT_SECONDS: Final = 30.0
TOTAL_TIMEOUT_SECONDS: Final = 300.0
MAX_RESPONSE_BYTES: Final = 10 * 1024 * 1024
# Trần tổng số byte đã đọc cho cả lần sync: 100 trang x 10 MB là 1 GB băng thông/CPU parse
# do Jira (hoặc kẻ giả Jira) điều khiển. Vượt thì dừng như chạm trần trang (truncated).
MAX_TOTAL_BYTES: Final = 50 * 1024 * 1024
MAX_TAG_FIELDS: Final = 20
MAX_JQL_LEN: Final = 4000
SEARCH_PATH: Final = "/rest/api/3/search/jql"
FIELD_PATH: Final = "/rest/api/3/field"
# Chỉ xin những field ánh xạ cần (thay cho `*all`: custom field có thể rất lớn/chứa PII).
# Custom field Company/Team... được xác định qua GET /field rồi thêm id vào danh sách.
BASE_FIELDS: Final = (
    "summary",
    "description",
    "status",
    "priority",
    "assignee",
    "project",
    "labels",
    "components",
    "fixVersions",
    "issuetype",
    "parent",
    "duedate",
    "created",
    "updated",
    "resolutiondate",
)


class JiraSyncError(DomainError):
    """Lỗi khi gọi Jira. Message tự viết, kèm mã trạng thái nếu có, KHÔNG kèm body."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


# ═══════════════════════════════════════════════════════════════════════
#  JQL
# ═══════════════════════════════════════════════════════════════════════


def jql_string(value: str) -> str:
    """Đưa một giá trị vào JQL dưới dạng chuỗi trong nháy kép, đã escape.

    WHY: tên người dùng (current_users) và mã dự án là dữ liệu do User/Jira đưa vào, nếu
    ghép thẳng thì `x") OR project = SECRET OR assignee in ("y` đổi nghĩa truy vấn. Trong
    JQL chuỗi nháy kép, chỉ `\\` và `"` là đặc biệt; xuống dòng/tab cũng escape để một giá
    trị không phá cấu trúc dòng.
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


_ORDER_BY_RE = re.compile(r"(?:^|\s+)order\s+by[\s\S]*$", re.IGNORECASE)


def build_jql(config_jql: str | None, current_users: list[str], since_minutes: int | None) -> str:
    """JQL cuối cùng cho lần sync.

    - `config_jql` có: dùng nguyên (do chủ kết nối tự viết); nếu chỉ là danh sách mã dự án
      ("DBA, PROJ", không có `=`, ` in `, ` is `, `~`) thì thành `project in (...)` như bản
      web.
    - Không có: `assignee in (...)` theo `current_users` (B2). Cả hai rỗng thì LỖI, không
      bao giờ chạy truy vấn toàn Jira.
    - `since_minutes`: thêm `updated >= -Nm`, N là SỐ NGUYÊN do server tính; không có chuỗi
      nào từ client được nối vào JQL.
    """
    jql = (config_jql or "").strip()
    if jql:
        lowered = jql.lower()
        if "=" not in jql and " in " not in lowered and " is " not in lowered and "~" not in jql:
            keys = [k.strip() for k in jql.split(",") if k.strip()]
            if not keys:
                raise ValidationError("JQL của kết nối không hợp lệ")
            jql = f"project in ({', '.join(jql_string(k) for k in keys)}) ORDER BY updated DESC"
    elif current_users:
        names = ", ".join(jql_string(n) for n in current_users)
        jql = f"assignee in ({names}) ORDER BY updated DESC"
    else:
        raise ValidationError(
            "Kết nối chưa có JQL và chưa đặt 'Tên người dùng' (current_users) trong cài đặt, "
            "nên không có điều kiện lọc. Nhập JQL cho kết nối hoặc đặt tên người dùng."
        )
    if since_minutes is not None:
        base = _ORDER_BY_RE.sub("", jql).strip()
        window = f"updated >= -{int(since_minutes)}m"
        jql = f"({base}) AND {window}" if base else window
        jql += " ORDER BY updated DESC"
    if len(jql) > MAX_JQL_LEN:
        raise ValidationError("JQL quá dài")
    return jql


_SINCE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
_SINCE_SLACK_MINUTES: Final = 5


def parse_since(raw: str | None, *, now: datetime | None = None) -> int | None:
    """`since` (ISO date hoặc datetime) -> số phút so với hiện tại, hoặc None nếu vắng.

    WHY phút tương đối thay vì `updated >= "2024-05-01 10:00"`: JQL tuyệt đối được hiểu theo
    múi giờ trong hồ sơ tài khoản Jira (ta không biết) nên lệch giờ sẽ bỏ sót issue; tương
    đối thì không. Cộng thêm vài phút dư để chồng lấp, upsert idempotent nên an toàn.
    Không có múi giờ = UTC. Ngày tương lai quá 1 ngày hoặc trước năm 2000 bị từ chối.

    Raises:
        ValidationError: định dạng sai (422). Thông báo không lặp lại giá trị.
    """
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    if not _SINCE_RE.match(text):
        raise ValidationError(
            "since phải là ngày/giờ ISO 8601, ví dụ 2024-05-01 hoặc 2024-05-01T10:00:00Z"
        )
    try:
        if len(text) == 10:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=UTC)
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
    except ValueError:
        raise ValidationError("since không phải ngày/giờ hợp lệ") from None
    current = now or datetime.now(UTC)
    delta_seconds = (current - parsed).total_seconds()
    if parsed.year < 2000 or delta_seconds < -86400:
        raise ValidationError("since nằm ngoài khoảng cho phép")
    return max(1, int(delta_seconds // 60) + 1) + _SINCE_SLACK_MINUTES


# ═══════════════════════════════════════════════════════════════════════
#  HTTP
# ═══════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class JiraPage:
    issues: list[Any]
    field_names: dict[str, str]


def _status_error(status: int) -> JiraSyncError:
    """Thông báo tự viết theo mã trạng thái; tuyệt đối không đọc/kèm body của Jira."""
    if status == 401:
        return JiraSyncError(
            "Jira trả 401: sai email hoặc API token. Hãy nhập lại token cho kết nối."
        )
    if status == 403:
        return JiraSyncError(
            "Jira trả 403: tài khoản thiếu quyền, hoặc Jira yêu cầu xác thực bổ sung."
        )
    if status == 404:
        return JiraSyncError("Jira trả 404: không tìm thấy API Jira, hãy kiểm tra base_url.")
    if status == 400:
        return JiraSyncError("Jira trả 400: truy vấn JQL bị từ chối, hãy kiểm tra JQL của kết nối.")
    if status == 429:
        return JiraSyncError("Jira trả 429: bị giới hạn tốc độ, hãy thử lại sau ít phút.")
    if 300 <= status < 400:
        return JiraSyncError(
            f"Jira trả {status} (chuyển hướng). Không theo chuyển hướng để tránh gửi "
            "thông tin xác thực sang host khác; hãy kiểm tra base_url."
        )
    if 500 <= status < 600:
        return JiraSyncError(f"Jira trả {status}: lỗi phía máy chủ Jira, hãy thử lại sau.")
    return JiraSyncError(f"Jira trả mã {status} không mong đợi.")


class JiraClient:
    """Một client cho MỘT lần sync. Không dùng lại giữa các lần: token nằm trong đối tượng."""

    def __init__(self, base_url: str, email: str, token: str, transport: httpx.AsyncBaseTransport):
        self._base_url = base_url.rstrip("/")
        self._auth = "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
        self._transport = transport
        self._deadline = 0.0
        self.truncated = False
        self.truncated_reason: str | None = None
        self.pages = 0
        self.total_bytes = 0
        # Tên field gộp tích luỹ qua MỌI trang (trang sau có thể có custom field mới).
        self.field_names: dict[str, str] = {}
        # Cảnh báo tự viết (vd. không lấy được danh sách custom field) cho người gọi.
        self.notes: list[str] = []

    def __repr__(self) -> str:
        # Đặt tường minh để một lần refactor sau này không vô tình đưa `_auth` vào repr.
        return "<JiraClient>"

    def _total_timeout_error(self) -> JiraSyncError:
        return JiraSyncError(
            f"Lần đồng bộ vượt {int(TOTAL_TIMEOUT_SECONDS // 60)} phút, đã dừng.",
            status_code=504,
        )

    async def _request(
        self, client: httpx.AsyncClient, method: str, path: str, body: dict[str, Any] | None
    ) -> Any:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise self._total_timeout_error()
        limit = min(REQUEST_TIMEOUT_SECONDS, remaining)
        try:
            async with asyncio.timeout(limit):
                return await self._request_inner(client, method, path, body)
        except DomainError:
            raise  # JiraSyncError / lỗi SSRF: đã có message tự viết
        except Exception as exc:
            if limit < REQUEST_TIMEOUT_SECONDS and isinstance(exc, TimeoutError):
                raise self._total_timeout_error() from None
            # Nguyên nhân thật chỉ vào log server; response dùng thông báo mạng cố định.
            logger.warning("jira_network_error error=%s", type(exc).__name__)
            raise NetworkUnavailableError from None

    async def _request_inner(
        self, client: httpx.AsyncClient, method: str, path: str, body: dict[str, Any] | None
    ) -> Any:
        headers = {"Authorization": self._auth}
        content = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            content = json.dumps(body).encode("utf-8")
        request = client.build_request(
            method, self._base_url + path, content=content, headers=headers
        )
        response = await client.send(request, stream=True, follow_redirects=False)
        received = bytearray()
        try:
            if response.status_code != 200:
                raise _status_error(response.status_code)
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            if encoding not in ("", "identity"):
                # Ta xin identity; nén là bất thường và là đường decompression bomb.
                raise JiraSyncError("Phản hồi của Jira dùng nén không được chấp nhận.")
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                raise self._too_large()
            async for chunk in response.aiter_bytes():
                received.extend(chunk)
                if len(received) > MAX_RESPONSE_BYTES:
                    raise self._too_large()
        finally:
            await response.aclose()
        self.total_bytes += len(received)
        try:
            return json.loads(bytes(received))
        except (ValueError, RecursionError):
            raise JiraSyncError("Phản hồi của Jira không phải JSON hợp lệ.") from None

    @staticmethod
    def _too_large() -> JiraSyncError:
        return JiraSyncError(
            f"Phản hồi của Jira vượt {MAX_RESPONSE_BYTES // (1024 * 1024)} MB cho một trang; "
            "hãy thu hẹp JQL.",
            status_code=502,
        )

    async def _tag_fields(self, client: httpx.AsyncClient) -> dict[str, str]:
        """id -> tên của custom field có tên khớp Company/Team/... (tối đa MAX_TAG_FIELDS).

        Một lần GET /field (cùng transport đã ghim, nên cùng chốt SSRF). Lỗi từ phía Jira
        (không phải lỗi mạng) chỉ làm mất tag/project từ custom field, không chặn sync;
        sai token sẽ lộ ra ở lần search ngay sau với thông báo đúng.
        """
        try:
            data = await self._request(client, "GET", FIELD_PATH, None)
        except JiraSyncError as exc:
            self.notes.append(
                "Không lấy được danh sách field tuỳ chỉnh; bỏ qua tag/project từ custom field "
                f"({exc.message})"
            )
            return {}
        found: dict[str, str] = {}
        for field in data if isinstance(data, list) else []:
            if not isinstance(field, dict):
                continue
            field_id, name = field.get("id"), field.get("name")
            if (
                isinstance(field_id, str)
                and field_id.startswith("customfield_")
                and isinstance(name, str)
                and CUSTOM_TAG_FIELD.search(name)
            ):
                found[field_id] = name
            if len(found) >= MAX_TAG_FIELDS:
                break
        return found

    async def search(self, jql: str) -> AsyncIterator[JiraPage]:
        """Lần lượt từng trang (theo nextPageToken). Chạm trần thì `truncated`.

        Trả theo trang để người gọi ánh xạ và GHI từng lô rồi bỏ bản thô ngay.

        Không bọc `asyncio.timeout` quanh cả generator: timeout đó vẫn chạy khi generator
        đang tạm dừng ở `yield` (người gọi ghi DB), và khi nó nổ thì CancelledError rơi vào
        code của người gọi chứ không vào generator, nên không đổi được thành lỗi sạch. Thay
        vào đó dùng hạn chót (`_deadline`, giờ đơn điệu) kiểm trước MỖI request.
        """
        self._deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        async with httpx.AsyncClient(
            transport=self._transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
            headers=headers,
        ) as client:
            tag_fields = await self._tag_fields(client)
            self.field_names.update(tag_fields)
            body: dict[str, Any] = {
                "jql": jql,
                "maxResults": PAGE_SIZE,
                "fields": [*BASE_FIELDS, *tag_fields],
                "expand": "names",
            }
            while True:
                # Tới đây từ lần lặp thứ hai nghĩa là Jira còn trang kế (có nextPageToken).
                if self.pages >= MAX_PAGES:
                    self.truncated, self.truncated_reason = True, "pages"
                    return
                if self.total_bytes >= MAX_TOTAL_BYTES:
                    self.truncated, self.truncated_reason = True, "bytes"
                    return
                data = await self._request(client, "POST", SEARCH_PATH, body)
                if not isinstance(data, dict):
                    raise JiraSyncError("Phản hồi của Jira có cấu trúc không mong đợi.")
                self.pages += 1
                names = data.get("names")
                if isinstance(names, dict):
                    self.field_names.update(
                        {
                            k: v
                            for k, v in names.items()
                            if isinstance(k, str) and isinstance(v, str)
                        }
                    )
                issues = data.get("issues")
                yield JiraPage(
                    issues=issues if isinstance(issues, list) else [],
                    field_names=self.field_names,
                )
                token = data.get("nextPageToken")
                if data.get("isLast") or not isinstance(token, str) or not token:
                    return
                body["nextPageToken"] = token
