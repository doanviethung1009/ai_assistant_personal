"""Ánh xạ issue Jira -> `TaskUpsert` (port từ `syncJiraAction` ở apps/web/app/jira-actions.ts).

══════════════════════════════════════════════════════════════════════
 DỮ LIỆU JIRA LÀ UNTRUSTED. Quy tắc cứng:
 - Mọi chuỗi chỉ là DỮ LIỆU để lưu/hiển thị. KHÔNG đưa summary/description/label/tên vào
   prompt LLM, shell, SQL hay JQL (project.md: nội dung nguồn ngoài không bao giờ thành
   instruction).
 - Làm sạch ký tự điều khiển và ký tự bidi (giả dòng log, đảo chiều hiển thị).
 - `raw_payload` dựng theo ALLOWLIST field, KHÔNG lưu cả issue (description, comment,
   attachment, custom field có thể chứa secret/PII).
 - `external_url` do ta tự dựng từ base_url đã lưu + key đã kiểm định dạng, không lấy URL
   nào từ Jira (kể cả `self`).
══════════════════════════════════════════════════════════════════════

Ánh xạ giữ đúng bản TypeScript, trừ các điểm lệch có chủ đích ghi ở cuối file.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError as PydanticValidationError

from app.models.enums import TaskPriority, TaskStatus
from app.schemas.common import MAX_TAGS
from app.schemas.task import MAX_ASSIGNEE_LEN
from app.schemas.task_upsert import TaskUpsert
from app.services.import_service import normalize_project_key

# Tên custom field Jira được coi là thông tin phân nhóm dự án (cùng regex với bản TS).
CUSTOM_TAG_FIELD = re.compile(
    r"company|group|customer|client|team|squad|tribe|department|công ty|nhóm|khách|dự án",
    re.IGNORECASE,
)
# Khoá issue Jira: PROJ-123. Chặn mọi thứ khác trước khi ghép vào URL/external_id.
_ISSUE_KEY_RE = re.compile(
    r"[A-Z][A-Z0-9_]{1,254}-[0-9]{1,9}"
)  # dùng fullmatch: `$` nhận cả "\n" cuối
ADF_PLACEHOLDER = "[Nội dung Jira dạng khối (Atlassian Document Format)]"
_MAX_TITLE = 500
_MAX_NAME = 200
_MAX_DESCRIPTION = 32_000
_MAX_CUSTOM_DEPTH = 5

# Cf (định dạng: bidi override, BOM, soft hyphen, zero-width space...) bị loại vì đảo chiều
# hiển thị/giả tên/vô hình. NGOẠI LỆ giữ ZWJ (U+200D, ghép emoji) và ZWNJ (U+200C, cần cho
# chữ Ba Tư/Ấn). Zl/Zp (U+2028/2029) ngắt dòng như \n nên đổi thành khoảng trắng/xuống dòng.
_KEEP_CF = {"\u200c", "\u200d"}

_PRIORITY_MAP = {
    "highest": TaskPriority.URGENT,
    "critical": TaskPriority.URGENT,
    "blocker": TaskPriority.URGENT,
    "high": TaskPriority.HIGH,
    "major": TaskPriority.HIGH,
    "medium": TaskPriority.MEDIUM,
    "normal": TaskPriority.MEDIUM,
    "low": TaskPriority.LOW,
    "minor": TaskPriority.LOW,
    "lowest": TaskPriority.LOW,
    "trivial": TaskPriority.LOW,
}


class MappingError(ValueError):
    """Issue không ánh xạ được; message tự viết, KHÔNG chứa nội dung Jira."""


def clean_text(value: Any, *, multiline: bool = False) -> str:
    """Chuỗi sạch: bỏ Cc/Cf (trừ ZWJ/ZWNJ), \\n \\t giữ khi `multiline`; strip."""
    if not isinstance(value, str):
        return ""
    out: list[str] = []
    for ch in value:
        category = unicodedata.category(ch)
        if category in ("Zl", "Zp") or (category == "Cc" and ch in "\n\r\t"):
            out.append(
                "\n" if multiline and ch == "\n" else "\t" if multiline and ch == "\t" else " "
            )
        elif category == "Cc" or (category == "Cf" and ch not in _KEEP_CF):
            continue
        else:
            out.append(ch)
    return "".join(out).strip()


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _slug(value: Any) -> str:
    return re.sub(r"\s+", "-", clean_text(value).lower())


def _custom_value_to_strings(value: Any, depth: int = 0) -> list[str]:
    if depth > _MAX_CUSTOM_DEPTH:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _custom_value_to_strings(v, depth + 1)]
    if isinstance(value, dict):
        for key in ("value", "name", "displayName"):
            if isinstance(value.get(key), str):
                return [value[key]]
    return []


def map_status(name: str | None) -> TaskStatus:
    """Cùng chuỗi `if` của bản TS: điều kiện sau ghi đè điều kiện trước (cancelled thắng)."""
    lowered = (name or "").lower()
    status = TaskStatus.TODO
    if any(w in lowered for w in ("progress", "doing", "review")):
        status = TaskStatus.IN_PROGRESS
    if any(w in lowered for w in ("done", "close", "resolved")):
        status = TaskStatus.DONE
    if any(w in lowered for w in ("cancel", "reject", "won't do", "obsolete")):
        status = TaskStatus.CANCELLED
    return status


def parse_jira_datetime(value: Any) -> datetime | None:
    """Parse thời điểm Jira (`2024-05-01T10:00:00.000+0700`); lỗi thì None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    # Jira luôn trả offset; nếu thiếu thì coi là UTC để không lệch theo múi giờ hiển thị.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_due(value: Any) -> datetime | None:
    # Cách lưu CHUẨN của hạn cả ngày: 00:00 UTC của ngày lịch (không phụ thuộc múi giờ hiển thị),
    # đi kèm `due_all_day=True`. Bản TS: new Date("YYYY-MM-DD").toISOString() cho cùng giá trị.
    if not isinstance(value, str) or not value:
        return None
    try:
        day = date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def previous_due(payload: dict[str, Any] | None) -> tuple[datetime | None, bool] | None:
    """Hạn mà lần sync TRƯỚC đã đặt, suy từ `raw_payload.fields.duedate`.

    `duedate` vắng trong payload nghĩa là Jira không có hạn (build_raw_payload bỏ khoá null).
    None = không biết (task chưa từng có payload từ Jira), người gọi phải giữ hạn hiện có.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("fields"), dict):
        return None
    due = _parse_due(payload["fields"].get("duedate"))
    return due, due is not None


def _cap(text: str, limit: int) -> str:
    return text[:limit]


def build_raw_payload(issue: dict[str, Any], base_host: str) -> dict[str, Any]:
    """Payload đối soát theo ALLOWLIST. Không có description/comment/custom field."""
    fields = _obj(issue.get("fields"))

    def pick_name(key: str, inner: str = "name") -> dict[str, str] | None:
        value = _obj(fields.get(key)).get(inner)
        return {inner: clean_text(value)} if isinstance(value, str) else None

    out_fields: dict[str, Any] = {}
    for key in ("summary", "updated", "created", "resolutiondate", "duedate"):
        if isinstance(fields.get(key), str):
            out_fields[key] = _cap(clean_text(fields[key]), _MAX_TITLE)
    for key, inner in (("status", "name"), ("priority", "name"), ("assignee", "displayName")):
        picked = pick_name(key, inner)
        if picked is not None:
            out_fields[key] = picked
    project_key = pick_name("project", "key")
    if project_key is not None:
        out_fields["project"] = project_key
    labels = fields.get("labels")
    if isinstance(labels, list):
        out_fields["labels"] = [clean_text(x)[:100] for x in labels[:50] if isinstance(x, str)]

    payload: dict[str, Any] = {"fields": out_fields}
    for key in ("id", "key"):
        if isinstance(issue.get(key), str):
            payload[key] = clean_text(issue[key])[:100]
    # `self` chỉ giữ khi https cùng host base_url, bỏ query/fragment (có thể mang tham số).
    raw_self = issue.get("self")
    if isinstance(raw_self, str):
        try:
            parts = urlsplit(raw_self)
            if parts.scheme == "https" and (parts.hostname or "").lower() == base_host:
                payload["self"] = f"https://{base_host}{parts.path}"[:500]
        except ValueError:
            pass
    return payload


def map_issue(
    issue: Any,
    *,
    base_url: str,
    field_names: dict[str, str],
    fallback_project_key: str | None = None,
    fallback_project_name: str | None = None,
    notes: list[str] | None = None,
) -> TaskUpsert:
    """Một issue -> TaskUpsert.

    `notes`: nếu truyền, nhận các câu cảnh báo tự viết (tag bị bỏ, assignee bị cắt) để
    người gọi đưa vào `warnings` của kết quả sync.

    Raises:
        MappingError: thiếu/sai khoá issue hoặc dữ liệu không dựng được TaskUpsert.
    """
    if not isinstance(issue, dict):
        raise MappingError("issue không phải đối tượng")
    key = issue.get("key")
    if not isinstance(key, str) or not _ISSUE_KEY_RE.fullmatch(key):
        raise MappingError("khoá issue thiếu hoặc sai định dạng")
    fields = _obj(issue.get("fields"))
    base_host = urlsplit(base_url).hostname or ""

    title = _cap(clean_text(fields.get("summary")), _MAX_TITLE) or "No Title"

    # Bản TS: description dạng chuỗi giữ nguyên; dạng khối ADF chỉ lưu dòng giữ chỗ.
    raw_description = fields.get("description")
    description: str | None = None
    if isinstance(raw_description, str):
        description = _cap(clean_text(raw_description, multiline=True), _MAX_DESCRIPTION) or None
    elif isinstance(raw_description, dict):
        description = ADF_PLACEHOLDER

    status = map_status(_obj(fields.get("status")).get("name"))

    project_obj = _obj(fields.get("project"))
    jira_project_key = clean_text(project_obj.get("key"))
    # Nhóm tag theo ĐỘ ƯU TIÊN khi phải cắt ở MAX_TAGS: định danh (jira, project, loại
    # issue) và custom field phân nhóm trước, rồi parent/component/version, label cuối
    # (label là thứ nhiều và ít quan trọng nhất; không để chúng đẩy tag định danh ra ngoài).
    identity = ["jira", _slug(jira_project_key), _slug(_obj(fields.get("issuetype")).get("name"))]
    grouping: list[str] = []
    extracted = ""
    for field_id, value in fields.items():
        if not field_id.startswith("customfield_") or value is None:
            continue
        if not CUSTOM_TAG_FIELD.search(field_names.get(field_id, "")):
            continue
        for text in _custom_value_to_strings(value):
            cleaned = clean_text(text)
            if cleaned and not extracted:
                extracted = cleaned
            grouping.append(_slug(cleaned))
    secondary = [_slug(_obj(fields.get("parent")).get("key"))]
    for field in ("components", "fixVersions"):
        values = fields.get(field)
        secondary.extend(
            _slug(_obj(v).get("name")) for v in (values if isinstance(values, list) else [])
        )
    labels = fields.get("labels")
    label_tags = (
        [_slug(x) for x in labels if isinstance(x, str)] if isinstance(labels, list) else []
    )
    ordered = list(dict.fromkeys(t for t in (*identity, *grouping, *secondary, *label_tags) if t))
    tag_list = ordered[:MAX_TAGS]
    if len(ordered) > MAX_TAGS and notes is not None:
        notes.append(f"{len(ordered) - MAX_TAGS} tag vượt trần {MAX_TAGS} nên bị bỏ")

    # Project: custom field phân nhóm > project của issue > tiền tố khoá issue (như bản TS).
    # `extracted` có thể không chuẩn hoá được ("!!!"): rơi về key của Jira thay vì loại issue.
    project_key: str | None = None
    project_name: str | None = None
    for candidate_key, candidate_name in (
        (extracted, extracted),
        (jira_project_key, clean_text(project_obj.get("name"))),
        (key.split("-")[0], ""),
        (fallback_project_key or "", fallback_project_name or ""),
    ):
        if not candidate_key:
            continue
        try:
            project_key = normalize_project_key(candidate_key)
        except ValueError:
            continue
        project_name = _cap(candidate_name or project_key, _MAX_NAME)
        break

    assignee = clean_text(_obj(fields.get("assignee")).get("displayName")) or None
    if assignee is not None and len(assignee) > MAX_ASSIGNEE_LEN:
        # Cắt thay vì để TaskUpsert từ chối cả issue vì một tên quá dài.
        assignee = assignee[:MAX_ASSIGNEE_LEN].strip()
        if notes is not None:
            notes.append("tên assignee quá dài nên bị cắt")

    updated_at = parse_jira_datetime(fields.get("updated"))
    resolved = parse_jira_datetime(fields.get("resolutiondate")) or updated_at
    priority = _PRIORITY_MAP.get(clean_text(_obj(fields.get("priority")).get("name")).lower())

    data: dict[str, Any] = {
        "external_id": key,
        "title": title,
        "description": description,
        "assignee": assignee,
        "status": status,
        "tags": tag_list,
        "external_url": f"{base_url}/browse/{key}",
        "created_at": parse_jira_datetime(fields.get("created")),
        "completed_at": resolved,
        "project_key": project_key,
        "project_name": project_name,
        "raw_payload": build_raw_payload(issue, base_host),
    }
    # Priority lạ -> không gửi: task mới lấy mặc định, task cũ giữ giá trị User đã đặt.
    if priority is not None:
        data["priority"] = priority
    # Hạn Jira là NGÀY thuần nên luôn cả ngày. Jira bỏ hạn thì gửi null tường minh; việc có
    # ghi đè hạn User đã sửa hay không do task_sync_service quyết (luật due_baseline).
    due = _parse_due(fields.get("duedate"))
    data["due_at"] = due
    data["due_all_day"] = due is not None
    try:
        return TaskUpsert(**data)
    except PydanticValidationError:
        # Không echo lỗi gốc: nó lặp lại giá trị (nội dung Jira) trong message.
        raise MappingError("dữ liệu issue không hợp lệ so với schema task") from None


# Điểm lệch có chủ đích so với bản TS (và cách Jira sync dùng upsert):
# - Trường CHỈ GHI KHI TẠO (create_only trong integration_sync_service): priority,
#   assignee, project_key. Khớp bản TS (task có sẵn không bị đổi các trường này) để giá trị
#   User sửa tay không bị sync ghi đè và task cũ không bị chuyển project. Status, title,
#   external_url và tags (gộp) vẫn được áp khi cập nhật.
# - priority: bản TS luôn đặt `medium` khi tạo; ở đây ánh xạ từ tên priority của Jira
#   (Highest/Critical/Blocker -> urgent ... Lowest -> low), tên lạ thì mặc định của task mới.
# - due_at/due_all_day: luôn gửi (null khi Jira không có hạn). Khi cập nhật, hạn chỉ bị ghi
#   đè nếu User chưa sửa tay: so hạn hiện có với `raw_payload.fields.duedate` lần trước
#   (`previous_due`). Bản TS (jira-actions.ts) áp cùng luật.
# - completed_at: bản TS luôn đè bằng resolutiondate mỗi lần sync; ở đây chỉ đổi khi status
#   chuyển sang đóng (hoặc điền khi đang đóng mà trống), theo task_sync_service.
# - external_url: bản TS chỉ đặt khi tạo; ở đây được áp cả khi cập nhật (tự dựng từ base_url
#   đã lưu, nên chỉ đổi khi base_url đổi). Cũng là cơ sở để chặn ghi đè chéo kết nối.
# - Project "mặc định" của kết nối (config.project_key) chỉ là phương án cuối: ở bản TS nó
#   không bao giờ được dùng vì khoá issue luôn cho ra một project.
