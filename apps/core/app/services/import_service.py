"""Nhập hàng loạt từ file JSON (builder-data.json, ai-logs.json) vào Postgres.

══════════════════════════════════════════════════════════════════════
 CẢNH BÁO: MODULE NÀY GHI ĐÈ BẢN GHI ĐÃ TỒN TẠI.

 - Bản ghi trong DB khớp với bản ghi trong file (theo id, hoặc khoá tự nhiên)
   và có khác biệt thì BỊ GHI ĐÈ bằng nội dung file. File cũ hơn DB vẫn ghi đè
   (chỉ được đánh dấu `file_older_than_db`), nên dry-run là bước bắt buộc.
 - KHÔNG BAO GIỜ xoá bản ghi: DB có mà file không có thì giữ nguyên. Bản ghi đang
   ở thùng rác (trong DB hoặc trong file) không bị hồi sinh hay xoá.
 - KHÔNG nhận `raw_payload` từ file; khi ghi đè giữ nguyên `raw_payload` của DB.
 - Nội dung note, payload event, mô tả task trong file là DỮ LIỆU KHÔNG ĐÁNG TIN:
   chỉ lưu, không thực thi, không đưa vào log hay message lỗi.
 - Mọi thứ trong một request nằm trong MỘT transaction (all-or-nothing) và được
   tuần tự hoá bằng advisory lock; không lấy được khoá thì 409.
══════════════════════════════════════════════════════════════════════

Luồng một lần nhập: khoá -> parse từng dòng (gom lỗi) -> lập kế hoạch (khớp bản
ghi, diff, đếm) -> kiểm `expect_replaced` -> ghi (INSERT/UPDATE) -> ghi sổ audit
-> COMMIT. Dry-run đi đúng đường đó rồi ROLLBACK ở cuối, để CHECK/unique của
Postgres cũng được kiểm chứ không chỉ validate ở Python.

Service tự kết thúc transaction (commit hoặc rollback): sau khi trả về, session
không còn giữ khoá hay thay đổi dang dở.
"""

from __future__ import annotations

import colorsys
import json
import logging
import re
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import Select, Table, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AiLog
from app.models.enums import (
    AiLogCategory,
    ImportAction,
    ImportEntity,
    ImportKind,
    TaskEventType,
    default_scope_for,
)
from app.models.import_audit import ImportAudit, ImportRun
from app.models.note import Note
from app.models.project import Project
from app.models.task import Task, TaskEvent
from app.schemas.common import normalize_tags
from app.schemas.imports import (
    AiLogsEnvelope,
    DataFileEnvelope,
    EntityCounts,
    FieldChange,
    ImportAiLog,
    ImportIssue,
    ImportNote,
    ImportProject,
    ImportReport,
    ImportTask,
    ImportTaskEvent,
    KeyChange,
    Replacement,
)
from app.services.errors import ConflictError, ValidationError
from app.services.task_service import _jsonable

logger = logging.getLogger(__name__)

# ── Giới hạn (spec 3.3, D12) ────────────────────────────────────────
MAX_EVENTS = 200_000
MAX_EVENT_PAYLOAD_BYTES = 16 * 1024
MAX_ISSUES = 500
MAX_REPLACEMENTS = 5_000
MAX_FIELDS_PER_REPLACEMENT = 30
# Khoá lạ trong file do người gửi quyết định: chặn số lượng và độ dài khi báo cáo.
MAX_IGNORED_NAMES = 50
MAX_IGNORED_NAME_LEN = 64
MAX_KEY_ORIGINAL_LEN = 40
# Actor của event nhập từ file luôn có tiền tố `import:` để không giả danh `user`
# hay `agent:*`; phần gốc cắt còn 90 ký tự cho vừa varchar(100).
EVENT_ACTOR_PREFIX = "import:"
MAX_EVENT_ACTOR_LEN = 90
# Chờ khoá dòng tối đa bấy lâu; hết hạn thì 409 thay vì treo request.
LOCK_TIMEOUT = "5s"
MAX_TEXT = 200
READ_BATCH = 1_000
WRITE_BATCH = 500

IMPORT_LOCK_NAME = "builder:import"
NO_HANDLING = "(không ghi nhận)"

# Field nhập được của từng thực thể, KHÔNG gồm id/created_at/updated_at/raw_payload.
PROJECT_FIELDS = ("key", "name", "description", "color", "is_archived")
TASK_FIELDS = (
    "title",
    "description",
    "assignee",
    "status",
    "priority",
    "project_id",
    "due_at",
    "scheduled_for",
    "estimate_minutes",
    "spent_minutes",
    "completed_at",
    "tags",
    "source",
    "scope",
    "external_id",
    "external_url",
)
NOTE_FIELDS = (
    "title",
    "kind",
    "content",
    "description",
    "context",
    "project_id",
    "tags",
    "is_pinned",
    "is_dangerous",
    "use_count",
    "last_used_at",
    "source",
    "external_id",
    "archived_at",
)
AI_LOG_FIELDS = ("category", "prompt", "handling", "response")

# Khác biệt ở các cột này KHÔNG tính là "có thay đổi" (D16): chạy lại cùng file
# phải ra toàn `unchanged`. raw_payload không bao giờ đến từ file nên cũng bỏ.
_DIFF_IGNORED = frozenset({"updated_at", "created_at", "raw_payload"})

_COUNT_KEYS = {
    "project": "projects",
    "task": "tasks",
    "task_event": "task_events",
    "note": "notes",
    "ai_log": "ai_logs",
}


# ═══════════════════════════════════════════════════════════════════════
#  Hàm thuần (test được không cần DB)
# ═══════════════════════════════════════════════════════════════════════


def normalize_project_key(raw: str) -> str:
    """Đưa tên project bất kỳ về dạng key hợp lệ `^[A-Z][A-Z0-9_]{1,19}$` (D7).

    File thật có key `ONE NEXUS`, `SAO MỘC`, `KHÁC` mà schema backend từ chối.
    Hàm này là nguồn duy nhất của quy tắc chuẩn hoá để B4 (Jira sync) dùng lại,
    tránh hai nơi sinh hai key khác nhau cho cùng một project.

    Raises:
        ValueError: không còn đủ 2 ký tự hợp lệ sau chuẩn hoá.
    """
    # Đ/đ không tách được bằng NFKD (không phải chữ + dấu) nên đổi tay trước.
    folded = raw.replace("Đ", "D").replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", folded)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    key = re.sub(r"[^A-Z0-9]+", "_", ascii_text.upper()).strip("_")
    if not key:
        raise ValueError("key không còn ký tự hợp lệ sau chuẩn hoá")
    if not key[0].isalpha():
        key = f"P_{key}"
    # Cắt xong có thể để lại `_` ở đuôi.
    key = key[:20].rstrip("_")
    if len(key) < 2:
        raise ValueError("key quá ngắn sau chuẩn hoá")
    return key


# Phân tách giữa các thành phần là `\s*,\s*` HOẶC `\s+`, hai nhánh không bao giờ
# khớp cùng một chuỗi con. Bản cũ `\s*[, ]\s*` cho phép một dãy dấu cách được chia
# cho hai `\s*` theo nhiều cách và gây backtracking bậc hai (ReDoS) với đầu vào
# không đáng tin.
_HSL_RE = re.compile(
    r"hsl\(\s*(-?\d+(?:\.\d+)?)(?:deg)?(?:\s*,\s*|\s+)(\d+(?:\.\d+)?)%"
    r"(?:\s*,\s*|\s+)(\d+(?:\.\d+)?)%\s*\)",
    re.IGNORECASE,
)
# Màu hợp lệ dài tối đa vài chục ký tự. Chặn độ dài TRƯỚC mọi regex để đầu vào
# khổng lồ không bao giờ chạm tới bộ khớp mẫu.
MAX_COLOR_LEN = 64
_HEX6_RE = re.compile(r"#([0-9a-fA-F]{6})")
_HEX3_RE = re.compile(r"#([0-9a-fA-F]{3})")


def normalize_color(value: Any) -> str | None:
    """Chuẩn hoá màu về `#rrggbb` chữ thường (cột `projects.color` là varchar(7)).

    Web cũ lưu `hsl(253, 70%, 65%)`; backend chỉ nhận hex. Dạng không nhận ra
    (tên màu, rgb()...) thành None thay vì làm hỏng cả project.
    """
    if not isinstance(value, str) or len(value) > MAX_COLOR_LEN:
        return None
    s = value.strip()
    if _HEX6_RE.fullmatch(s):
        return s.lower()
    if m := _HEX3_RE.fullmatch(s):
        return "#" + "".join(ch * 2 for ch in m.group(1).lower())
    if m := _HSL_RE.fullmatch(s):
        hue = (float(m.group(1)) % 360) / 360
        sat = min(float(m.group(2)), 100.0) / 100
        light = min(float(m.group(3)), 100.0) / 100
        r, g, b = colorsys.hls_to_rgb(hue, light, sat)
        return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"
    return None


def map_ai_log_category(value: str | None) -> AiLogCategory:
    """Ánh xạ category của file ai-logs sang enum backend (D9).

    File ghi `TOOL`, `UI/UX`, `DOCS`...; enum backend chỉ có app/api/web/tool/other.
    """
    if not value:
        return AiLogCategory.OTHER
    lowered = value.strip().lower()
    if lowered == "ui/ux":
        return AiLogCategory.WEB
    try:
        return AiLogCategory(lowered)
    except ValueError:
        return AiLogCategory.OTHER


def _canon(field_name: str, value: Any) -> Any:
    """Đưa giá trị về dạng so sánh được giữa DB và file."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        # So theo thời điểm UTC, không theo cách biểu diễn múi giờ.
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)
    if field_name == "tags":
        return normalize_tags(list(value)) if value else []
    return value


def _display(value: Any) -> Any:
    """Giá trị đưa vào báo cáo/payload: JSON được, chuỗi dài bị cắt."""
    out = _jsonable(value)
    if isinstance(out, str) and len(out) > MAX_TEXT:
        return out[:MAX_TEXT]
    return out


def diff_fields(
    db_row: Mapping[str, Any], file_row: Mapping[str, Any], fields: Iterable[str]
) -> list[FieldChange]:
    """Liệt kê field khác nhau giữa bản ghi DB và bản ghi chuẩn hoá từ file.

    Bỏ qua `updated_at`, `created_at`, `raw_payload` (D16): nếu không, mọi lần
    nhập lại đều thành "ghi đè" chỉ vì dấu thời gian, phá tính idempotent.
    """
    changes: list[FieldChange] = []
    for name in fields:
        if name in _DIFF_IGNORED:
            continue
        old, new = db_row.get(name), file_row.get(name)
        if _canon(name, old) != _canon(name, new):
            changes.append(FieldChange(field=name, old=_display(old), new=_display(new)))
    return changes


# ═══════════════════════════════════════════════════════════════════════
#  Trạng thái một lần nhập
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class _Parsed:
    """Một dòng của file sau khi validate và chuẩn hoá."""

    index: int
    file_id: uuid.UUID
    values: dict[str, Any]
    trashed: bool
    label: str
    # Key project lấy từ object `project` nhúng, chỉ dùng làm đường dự phòng.
    project_key: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    # Field mà giá trị trong `values` là GIÁ TRỊ DỰ PHÒNG do bước chuẩn hoá tự
    # tạo (file không nói gì, hoặc không dùng được): chỉ dùng khi INSERT. Khi
    # replace, các field này bị loại khỏi diff lẫn SET, nếu không một file thiếu
    # `archived_at` sẽ âm thầm bỏ lưu trữ ghi chú, file thiếu `completed_at` sẽ
    # xoá ngày hoàn thành thật trong DB.
    fallback: set[str] = field(default_factory=set)


@dataclass
class _Update:
    db_id: uuid.UUID
    file_id: uuid.UUID
    values: dict[str, Any]
    changes: list[FieldChange]


@dataclass
class _Plan:
    """Kết quả lập kế hoạch cho một loại thực thể (chưa ghi gì vào DB)."""

    creates: list[dict[str, Any]] = field(default_factory=list)
    updates: list[_Update] = field(default_factory=list)
    # id trong file -> id trong DB, cho mọi bản ghi sẽ tồn tại sau khi nhập
    id_map: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    created_file_ids: set[uuid.UUID] = field(default_factory=set)
    # khoá tự nhiên (đã chuẩn hoá) -> id DB; dùng để task tìm project theo key
    natural_to_db: dict[Hashable, uuid.UUID] = field(default_factory=dict)
    # id (trong file) của task bị bỏ qua vì khớp task cá nhân trong DB; event của
    # chúng không được chèn (xem _plan_events).
    skipped_personal_ids: set[uuid.UUID] = field(default_factory=set)


@dataclass(frozen=True)
class _Spec:
    entity: str
    table: Table
    fields: tuple[str, ...]
    soft_delete: bool
    natural_of: Callable[[_Parsed], Hashable | None]
    fetch_natural: Callable[..., Awaitable[dict[Any, dict[str, Any]]]] | None
    dup_code: str
    label_max: int = 80


class _Ctx:
    """Bộ gom lỗi, đếm, diff và dấu vết audit của một lần nhập."""

    def __init__(
        self, *, dry_run: bool, schema_version: int, include_personal: bool = False
    ) -> None:
        self.import_id = uuid.uuid4()
        self.dry_run = dry_run
        # Mặc định tắt: task cá nhân trong DB không bị file ghi đè (spec task-scope S8).
        self.include_personal = include_personal
        self.schema_version = schema_version
        self.now = datetime.now(UTC)
        self.counts = {key: EntityCounts() for key in _COUNT_KEYS.values()}
        self._errors: list[ImportIssue] = []
        self._warnings: list[ImportIssue] = []
        self.n_errors = 0
        self.n_warnings = 0
        self.replacements: list[Replacement] = []
        self.replacements_truncated = False
        self.key_changes: list[KeyChange] = []
        self.ignored: dict[str, set[str]] = {}
        self.audit: list[dict[str, Any]] = []

    def issue(
        self,
        level: str,
        entity: str,
        code: str,
        message: str,
        *,
        index: int | None = None,
        id_: Any = None,
    ) -> None:
        item = ImportIssue(
            level=level,  # type: ignore[arg-type]
            entity=entity,  # type: ignore[arg-type]
            index=index,
            id=None if id_ is None else str(id_)[:64],
            code=code,
            message=message,
        )
        if level == "error":
            self.n_errors += 1
            if len(self._errors) < MAX_ISSUES:
                self._errors.append(item)
        else:
            self.n_warnings += 1
            if len(self._warnings) < MAX_ISSUES:
                self._warnings.append(item)

    def error(self, entity: str, code: str, message: str, **kw: Any) -> None:
        self.issue("error", entity, code, message, **kw)

    def warn(self, entity: str, code: str, message: str, **kw: Any) -> None:
        self.issue("warning", entity, code, message, **kw)

    def note_ignored(self, entity: str, names: Iterable[Any]) -> None:
        """Ghi tên field bị bỏ, có chặn kích thước.

        Khoá lạ do file quyết định, nên không có giới hạn thì một file 10 MB toàn
        khoá khác nhau sẽ phình báo cáo (và bộ nhớ). Giữ tối đa 50 tên mỗi entity,
        mỗi tên cắt 64 ký tự.
        """
        bucket = self.ignored.setdefault(entity, set())
        for name in names:
            if len(bucket) >= MAX_IGNORED_NAMES:
                break
            bucket.add(str(name)[:MAX_IGNORED_NAME_LEN])

    def counts_of(self, entity: str) -> EntityCounts:
        return self.counts[_COUNT_KEYS[entity]]

    def total_replaced(self) -> int:
        return sum(c.replaced for c in self.counts.values())

    def build_issues(self) -> tuple[list[ImportIssue], bool]:
        # Lỗi đi trước cảnh báo: bị cắt thì cắt cảnh báo trước.
        merged = self._errors + self._warnings
        total = self.n_errors + self.n_warnings
        return merged[:MAX_ISSUES], total > MAX_ISSUES


# ═══════════════════════════════════════════════════════════════════════
#  Parse từng dòng
# ═══════════════════════════════════════════════════════════════════════


def _raw_id(raw: Mapping[str, Any]) -> Any:
    value = raw.get("id")
    return value if isinstance(value, str | int) else None


def _validate[M: BaseModel](
    ctx: _Ctx, entity: str, index: int, raw: dict[str, Any], model: type[M]
) -> M | None:
    """Validate một dòng, ghi lỗi theo dòng thay vì làm hỏng cả request.

    Message chỉ chứa tên field và loại lỗi, không chép giá trị người dùng nhập
    (có thể là nội dung note nhạy cảm).
    """
    # Field có trong file mà không nằm trong schema: báo cho người dùng biết đã bị bỏ.
    known = set(model.model_fields) - {"project"}
    extra = set(raw) - known
    if extra:
        ctx.note_ignored(entity, extra)
    try:
        return model.model_validate(raw)
    except PydanticValidationError as exc:
        ctx.counts_of(entity).invalid += 1
        for err in exc.errors(include_input=False, include_url=False, include_context=False)[:5]:
            loc = ".".join(str(p) for p in err["loc"])
            code = "invalid_enum" if err["type"] in ("enum", "literal_error") else "invalid_value"
            ctx.error(
                entity,
                code,
                f"Giá trị không hợp lệ ở '{loc}': {err['msg']}",
                index=index,
                id_=_raw_id(raw),
            )
        return None


def _aware(value: datetime | None, naive_flag: list[bool]) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        naive_flag[0] = True
        return value.replace(tzinfo=UTC)
    return value


def _absent(raw: Mapping[str, Any], fields: Iterable[str]) -> set[str]:
    """Field mà KHÔNG có khoá nào trong dòng của file.

    Khoá vắng mặt nghĩa là "file không nói gì", khác với `null` tường minh ("file
    nói là rỗng"). Chỉ trường hợp sau mới được phép ghi đè giá trị đang có trong DB.
    """
    return {name for name in fields if name not in raw}


def _stamps(
    ctx: _Ctx,
    entity: str,
    index: int,
    id_: uuid.UUID,
    created_raw: datetime | None,
    updated_raw: datetime | None,
    flag: list[bool],
) -> tuple[datetime, datetime]:
    """created_at/updated_at của dòng; thiếu created_at thì dùng giờ nhập và cảnh báo.

    Giờ nhập là thứ file không hề nói, nên người dùng cần biết để không nhầm với
    thời điểm tạo thật. Thiếu mỗi updated_at thì lấy created_at (không cảnh báo:
    đó là quy tắc chuẩn của file ai-logs).
    """
    created = _aware(created_raw, flag)
    if created is None:
        created = ctx.now
        ctx.warn(
            entity,
            "timestamps_defaulted",
            "File thiếu created_at, dùng giờ nhập.",
            index=index,
            id_=id_,
        )
    updated = _aware(updated_raw, flag) or created
    return created, updated


def _is_http_url(value: str) -> bool:
    try:
        parts = urlparse(value.strip())
    except ValueError:
        # urlparse ném ValueError với IPv6 hỏng như `http://[::1`; một URL sai dạng
        # chỉ là "không dùng được", không được làm cả request thành 500.
        return False
    return parts.scheme.lower() in ("http", "https") and bool(parts.netloc)


def _nested_project_key(ctx: _Ctx, obj: dict[str, Any] | None) -> str | None:
    if not isinstance(obj, dict) or not isinstance(obj.get("key"), str):
        return None
    try:
        return normalize_project_key(obj["key"])
    except ValueError:
        return None


def _parse_project(ctx: _Ctx, index: int, raw: dict[str, Any]) -> _Parsed | None:
    m = _validate(ctx, "project", index, raw, ImportProject)
    if m is None:
        return None
    try:
        key = normalize_project_key(m.key)
    except ValueError:
        ctx.counts_of("project").invalid += 1
        ctx.error(
            "project",
            "invalid_key",
            "Key project không chuẩn hoá được thành key hợp lệ.",
            index=index,
            id_=m.id,
        )
        return None
    if key != m.key:
        ctx.key_changes.append(KeyChange(original=m.key[:MAX_KEY_ORIGINAL_LEN], normalized=key))
        ctx.warn(
            "project",
            "key_normalized",
            f"Key '{m.key[:40]}' được chuẩn hoá thành '{key}'.",
            index=index,
            id_=m.id,
        )
    fallback = _absent(raw, PROJECT_FIELDS)
    color = normalize_color(m.color)
    if m.color is not None and color != m.color:
        if color is None:
            fallback.add("color")
            ctx.warn(
                "project",
                "color_dropped",
                "Màu không nhận dạng được, bỏ trống.",
                index=index,
                id_=m.id,
            )
        else:
            ctx.warn(
                "project",
                "color_converted",
                f"Màu được đổi sang {color}.",
                index=index,
                id_=m.id,
            )
    flag = [False]
    created, updated = _stamps(ctx, "project", index, m.id, m.created_at, m.updated_at, flag)
    if flag[0]:
        ctx.warn(
            "project",
            "naive_datetime",
            "Thời gian không có múi giờ, coi là UTC.",
            index=index,
            id_=m.id,
        )
    values = {
        "key": key,
        "name": m.name,
        "description": m.description,
        "color": color,
        "is_archived": m.is_archived,
        "created_at": created,
        "updated_at": updated,
    }
    return _Parsed(index, m.id, values, False, key, fallback=fallback)


def _parse_events(
    ctx: _Ctx, task_index: int, task_id: uuid.UUID, raw_events: list[Any], fallback: datetime
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            ctx.counts_of("task_event").invalid += 1
            ctx.error(
                "task_event",
                "invalid_value",
                "Event không phải object.",
                index=task_index,
            )
            continue
        ctx.counts_of("task_event").received += 1
        m = _validate(ctx, "task_event", task_index, raw, ImportTaskEvent)
        if m is None:
            continue
        if m.payload is not None and (
            len(json.dumps(m.payload, default=str).encode()) > MAX_EVENT_PAYLOAD_BYTES
        ):
            ctx.counts_of("task_event").invalid += 1
            ctx.error(
                "task_event",
                "payload_too_large",
                "Payload của event vượt 16 KB.",
                index=task_index,
                id_=m.id,
            )
            continue
        flag = [False]
        created = _aware(m.created_at, flag) or fallback
        out.append(
            {
                "id": m.id,
                "event_type": m.event_type,
                # Actor do file khai là dữ liệu không đáng tin: gắn tiền tố để không
                # giả danh `user` hay `agent:*` trong audit trail.
                "actor": EVENT_ACTOR_PREFIX + (m.actor or "user")[:MAX_EVENT_ACTOR_LEN],
                "payload": m.payload,
                "created_at": created,
            }
        )
    return out


def _parse_task(ctx: _Ctx, index: int, raw: dict[str, Any]) -> _Parsed | None:
    m = _validate(ctx, "task", index, raw, ImportTask)
    if m is None:
        return None
    flag = [False]
    created, updated = _stamps(ctx, "task", index, m.id, m.created_at, m.updated_at, flag)
    if m.deleted_at is not None:
        # Task ở thùng rác của file: bỏ cả task lẫn event, không đụng bản trong DB (D5).
        n_events = len(m.events)
        ctx.counts_of("task_event").received += n_events
        ctx.counts_of("task_event").skipped_trash += n_events
        return _Parsed(index, m.id, {}, True, m.title[:80])
    try:
        tags = normalize_tags(m.tags)
    except ValueError:
        ctx.counts_of("task").invalid += 1
        ctx.error("task", "invalid_tags", "Tối đa 20 tag mỗi task.", index=index, id_=m.id)
        return None

    fallback = _absent(raw, TASK_FIELDS)
    due = _aware(m.due_at, flag)
    completed = _aware(m.completed_at, flag)
    estimate = m.estimate_minutes
    if estimate is not None and not (0 < estimate <= 43_200):
        fallback.add("estimate_minutes")
        ctx.warn(
            "task",
            "estimate_dropped",
            "estimate_minutes ngoài khoảng 1..43200, bỏ trống.",
            index=index,
            id_=m.id,
        )
        estimate = None
    if m.status.value == "done" and completed is None:
        completed = updated
        fallback.add("completed_at")
        ctx.warn(
            "task",
            "completed_at_backfilled",
            "Task done thiếu completed_at, lấy theo updated_at.",
            index=index,
            id_=m.id,
        )
    if flag[0]:
        ctx.warn(
            "task",
            "naive_datetime",
            "Thời gian không có múi giờ, coi là UTC.",
            index=index,
            id_=m.id,
        )
    external_url = m.external_url
    if external_url is not None and not _is_http_url(external_url):
        # Chỉ http/https: chuỗi `javascript:` hay `data:` mà UI hiển thị thành link
        # là vector XSS. Chỉ áp ở đường nhập; TaskCreate nằm ngoài phạm vi B1.
        external_url = None
        fallback.add("external_url")
        ctx.warn(
            "task",
            "external_url_dropped",
            "external_url không phải http/https, bỏ trống.",
            index=index,
            id_=m.id,
        )
    events = _parse_events(ctx, index, m.id, m.events, created)
    scope = m.scope
    if scope is None:
        # Mọi file v1-v4 không có scope (hoặc có nhưng null): suy từ source. Đây là
        # giá trị DỰ PHÒNG nên đánh dấu fallback: tạo mới thì dùng, còn ghi đè thì
        # giữ scope đang có trong DB, để file cũ không đảo lựa chọn User đã sửa.
        scope = default_scope_for(m.source)
        fallback.add("scope")
    values = {
        "title": m.title,
        "description": m.description,
        "assignee": m.assignee,
        "status": m.status,
        "priority": m.priority,
        "project_id": m.project_id,
        "due_at": due,
        "scheduled_for": m.scheduled_for,
        "estimate_minutes": estimate,
        "spent_minutes": m.spent_minutes,
        "completed_at": completed,
        "tags": tags,
        "source": m.source,
        "scope": scope,
        "external_id": m.external_id,
        "external_url": external_url,
        "created_at": created,
        "updated_at": updated,
    }
    return _Parsed(
        index,
        m.id,
        values,
        False,
        m.title[:80],
        _nested_project_key(ctx, m.project),
        events,
        fallback,
    )


def _parse_note(ctx: _Ctx, index: int, raw: dict[str, Any]) -> _Parsed | None:
    m = _validate(ctx, "note", index, raw, ImportNote)
    if m is None:
        return None
    if m.deleted_at is not None:
        return _Parsed(index, m.id, {}, True, m.title[:80])
    try:
        tags = normalize_tags(m.tags)
    except ValueError:
        ctx.counts_of("note").invalid += 1
        ctx.error("note", "invalid_tags", "Tối đa 20 tag mỗi note.", index=index, id_=m.id)
        return None
    flag = [False]
    created, updated = _stamps(ctx, "note", index, m.id, m.created_at, m.updated_at, flag)
    fallback = _absent(raw, NOTE_FIELDS)
    last_used = _aware(m.last_used_at, flag)
    archived = _aware(m.archived_at, flag)
    if flag[0]:
        ctx.warn(
            "note",
            "naive_datetime",
            "Thời gian không có múi giờ, coi là UTC.",
            index=index,
            id_=m.id,
        )
    values = {
        "title": m.title,
        "kind": m.kind,
        "content": m.content,
        "description": m.description,
        "context": m.context,
        "project_id": m.project_id,
        "tags": tags,
        "is_pinned": m.is_pinned,
        "is_dangerous": m.is_dangerous,
        "use_count": m.use_count,
        "last_used_at": last_used,
        "source": m.source,
        "external_id": m.external_id,
        "archived_at": archived,
        "created_at": created,
        "updated_at": updated,
    }
    return _Parsed(
        index,
        m.id,
        values,
        False,
        m.title[:80],
        _nested_project_key(ctx, m.project),
        fallback=fallback,
    )


def _parse_ai_log(ctx: _Ctx, index: int, raw: dict[str, Any]) -> _Parsed | None:
    m = _validate(ctx, "ai_log", index, raw, ImportAiLog)
    if m is None:
        return None
    if not m.prompt.strip() or not m.response.strip():
        ctx.counts_of("ai_log").invalid += 1
        ctx.error(
            "ai_log", "invalid_value", "prompt và response không được rỗng.", index=index, id_=m.id
        )
        return None
    category = map_ai_log_category(m.category)
    if (
        m.category
        and category is AiLogCategory.OTHER
        and m.category.strip().lower() != AiLogCategory.OTHER.value
    ):
        ctx.warn(
            "ai_log",
            "category_unknown",
            f"Category '{m.category[:30]}' không có trong enum, chuyển thành 'other'.",
            index=index,
            id_=m.id,
        )
    flag = [False]
    created, updated = _stamps(ctx, "ai_log", index, m.id, m.created_at, m.updated_at, flag)
    fallback = _absent(raw, AI_LOG_FIELDS)
    has_handling = bool(m.handling and m.handling.strip())
    if not has_handling:
        # "(không ghi nhận)" là chữ do hệ thống bịa ra, không được đè handling thật.
        fallback.add("handling")
    values = {
        "category": category,
        "prompt": m.prompt,
        "handling": m.handling if has_handling else NO_HANDLING,
        "response": m.response,
        "created_at": created,
        "updated_at": updated,
    }
    return _Parsed(index, m.id, values, False, m.prompt[:80], fallback=fallback)


def _parse_rows(
    ctx: _Ctx,
    entity: str,
    raws: list[dict[str, Any]],
    parser: Callable[[_Ctx, int, dict[str, Any]], _Parsed | None],
) -> list[_Parsed]:
    rows: list[_Parsed] = []
    for index, raw in enumerate(raws):
        ctx.counts_of(entity).received += 1
        parsed = parser(ctx, index, raw)
        if parsed is not None:
            rows.append(parsed)
    return rows


# ═══════════════════════════════════════════════════════════════════════
#  Đọc DB theo lô
# ═══════════════════════════════════════════════════════════════════════


def _chunks[T](items: Sequence[T], size: int) -> Iterable[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _lock_rows(stmt: Select[Any], table: Table) -> Select[Any]:
    """Khoá dòng đọc được để ghi sau đó, theo thứ tự id cố định.

    - FOR NO KEY UPDATE (`key_share=True`) thay vì FOR UPDATE: ta không đổi khoá
      chính, nên không cần chặn khoá KEY SHARE mà INSERT task/note có FK tới
      project lấy; dùng FOR UPDATE sẽ làm các thao tác đó chờ vô lý.
    - ORDER BY id: hai lần khoá cùng tập dòng theo cùng thứ tự thì không thể
      chờ vòng tròn (deadlock) với nhau.
    """
    return stmt.order_by(table.c.id).with_for_update(key_share=True)


async def _fetch_by_ids(
    session: AsyncSession, table: Table, ids: Sequence[uuid.UUID], *, lock: bool = False
) -> dict[uuid.UUID, dict[str, Any]]:
    """Đọc đủ cột (để diff và chụp `before`) theo lô, không N+1.

    `lock=True` (nhập thật) dùng SELECT ... FOR UPDATE: giữ khoá dòng từ lúc lập
    kế hoạch đến lúc ghi, để một request khác sửa task giữa chừng không bị ghi đè
    bằng `before`/diff đã cũ (lost update). Dry-run không khoá để khỏi chặn người dùng.
    """
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for chunk in _chunks(list(ids), READ_BATCH):
        stmt = select(table).where(table.c.id.in_(chunk))
        if lock:
            stmt = _lock_rows(stmt, table)
        result = await session.execute(stmt)
        for row in result:
            data = dict(row._mapping)
            out[data["id"]] = data
    return out


async def _natural_projects(
    session: AsyncSession, keys: list[Any], *, lock: bool = False
) -> dict[Any, dict[str, Any]]:
    table = Project.__table__
    out: dict[Any, dict[str, Any]] = {}
    for chunk in _chunks(keys, READ_BATCH):
        stmt = select(table).where(table.c.key.in_(chunk))
        if lock:
            stmt = _lock_rows(stmt, table)
        result = await session.execute(stmt)
        for row in result:
            data = dict(row._mapping)
            out[data["key"]] = data
    return out


def _natural_sourced(table: Table) -> Callable[..., Awaitable[dict[Any, dict[str, Any]]]]:
    """Tra bản ghi SỐNG theo (source, external_id) cho task hoặc note.

    Chỉ bản còn sống vì unique index là partial `WHERE deleted_at IS NULL`: bản
    trong thùng rác không chiếm khoá tự nhiên.
    """

    async def fetch(
        session: AsyncSession, nats: list[Any], *, lock: bool = False
    ) -> dict[Any, dict[str, Any]]:
        by_source: dict[str, list[str]] = {}
        for source, external_id in nats:
            by_source.setdefault(source, []).append(external_id)
        out: dict[Any, dict[str, Any]] = {}
        for source, ext_ids in by_source.items():
            for chunk in _chunks(ext_ids, READ_BATCH):
                stmt = select(table).where(
                    table.c.source == source,
                    table.c.external_id.in_(chunk),
                    table.c.deleted_at.is_(None),
                )
                if lock:
                    stmt = _lock_rows(stmt, table)
                result = await session.execute(stmt)
                for row in result:
                    data = dict(row._mapping)
                    out[(source, data["external_id"])] = data
        return out

    return fetch


def _sourced_natural(r: _Parsed) -> Hashable | None:
    """Khoá tự nhiên (source, external_id) của task/note.

    `source` và `external_id` là MỘT CẶP: file thiếu khoá của một trong hai thì
    cặp không xác định (mặc định `source=manual` ghép với external_id thật sẽ
    thành khoá bịa), nên coi như không có khoá tự nhiên.
    """
    if _PAIR_FIELDS & r.fallback or r.values.get("external_id") is None:
        return None
    return (r.values["source"].value, r.values["external_id"])


_PAIR_FIELDS = frozenset({"source", "external_id"})


PROJECT_SPEC = _Spec(
    "project",
    Project.__table__,
    PROJECT_FIELDS,
    False,
    lambda r: r.values["key"],
    _natural_projects,
    "duplicate_project_key",
)
TASK_SPEC = _Spec(
    "task",
    Task.__table__,
    TASK_FIELDS,
    True,
    _sourced_natural,
    _natural_sourced(Task.__table__),
    "duplicate_external_id",
)
NOTE_SPEC = _Spec(
    "note",
    Note.__table__,
    NOTE_FIELDS,
    True,
    _sourced_natural,
    _natural_sourced(Note.__table__),
    "duplicate_external_id",
)
AI_LOG_SPEC = _Spec(
    "ai_log", AiLog.__table__, AI_LOG_FIELDS, False, lambda r: None, None, "duplicate_id"
)


# ═══════════════════════════════════════════════════════════════════════
#  Lập kế hoạch: khớp bản ghi, diff, đếm (chưa ghi gì)
# ═══════════════════════════════════════════════════════════════════════


async def _plan_entity(ctx: _Ctx, session: AsyncSession, spec: _Spec, rows: list[_Parsed]) -> _Plan:
    """Quyết định tạo / ghi đè / giữ nguyên / bỏ qua cho từng dòng (spec 3.2).

    Khớp theo `id` trước, rồi khoá tự nhiên. Cố ý KHÔNG có nhánh xoá: bản ghi DB
    không có trong file không bao giờ bị chạm tới.
    """
    plan = _Plan()
    counts = ctx.counts_of(spec.entity)
    live = [r for r in rows if not r.trashed]
    counts.skipped_trash += len(rows) - len(live)

    # Trùng trong chính file: không có cách nào đoán dòng nào đúng.
    seen_ids: dict[uuid.UUID, int] = {}
    seen_nat: dict[Hashable, int] = {}
    broken: set[int] = set()
    for r in live:
        if r.file_id in seen_ids:
            ctx.error(
                spec.entity,
                "duplicate_id",
                "id xuất hiện nhiều lần trong file.",
                index=r.index,
                id_=r.file_id,
            )
            broken.add(r.index)
        seen_ids.setdefault(r.file_id, r.index)
        nat = spec.natural_of(r)
        if nat is not None:
            if nat in seen_nat:
                ctx.error(
                    spec.entity,
                    spec.dup_code,
                    "Khoá tự nhiên (key hoặc source + external_id) trùng trong file.",
                    index=r.index,
                    id_=r.file_id,
                )
                broken.add(r.index)
            seen_nat.setdefault(nat, r.index)

    lock = not ctx.dry_run
    by_id = await _fetch_by_ids(session, spec.table, [r.file_id for r in live], lock=lock)
    nat_keys = [n for r in live if (n := spec.natural_of(r)) is not None]
    nat_rows = (
        await spec.fetch_natural(session, nat_keys, lock=lock)
        if spec.fetch_natural and nat_keys
        else {}
    )

    used_targets: set[uuid.UUID] = set()
    for r in live:
        if r.index in broken:
            continue
        nat = spec.natural_of(r)
        target = by_id.get(r.file_id)
        matched_by = "id"
        if target is None and nat is not None:
            target = nat_rows.get(nat)
            matched_by = "natural_key"
        if target is None:
            plan.creates.append({"id": r.file_id, **r.values})
            plan.id_map[r.file_id] = r.file_id
            plan.created_file_ids.add(r.file_id)
            if nat is not None:
                plan.natural_to_db[nat] = r.file_id
            counts.created += 1
            ctx.audit.append(_audit(spec.entity, r.file_id, ImportAction.CREATED, None, []))
            continue

        if spec.soft_delete and target.get("deleted_at") is not None:
            # Không hồi sinh bản ghi người dùng đã chủ động bỏ vào thùng rác.
            counts.skipped_trash_in_db += 1
            ctx.warn(
                spec.entity,
                "skipped_trash_in_db",
                "Bản ghi tương ứng đang ở thùng rác trong DB, bỏ qua.",
                index=r.index,
                id_=r.file_id,
            )
            continue
        if (
            spec.entity == "task"
            and not ctx.include_personal
            and _canon("scope", target.get("scope")) == "personal"
        ):
            # Task cá nhân là của User: file (kể cả file v4 cũ không có scope) không
            # được ghi đè nó, và cũng không tạo bản trùng khoá tự nhiên. Chạm vào nó
            # phải bật include_personal tường minh. Áp cho cả khớp theo id lẫn khoá tự nhiên.
            counts.skipped_personal += 1
            plan.skipped_personal_ids.add(r.file_id)
            ctx.warn(
                spec.entity,
                "skipped_personal",
                "Task cá nhân trong DB được bảo vệ, bỏ qua. Bật include_personal để ghi đè.",
                index=r.index,
                id_=r.file_id,
            )
            continue
        if matched_by == "id" and nat is not None:
            other = nat_rows.get(nat)
            if other is not None and other["id"] != target["id"]:
                ctx.error(
                    spec.entity,
                    "natural_key_conflict",
                    "Ghi đè sẽ làm trùng khoá tự nhiên với một bản ghi khác trong DB.",
                    index=r.index,
                    id_=r.file_id,
                )
                continue
        if target["id"] in used_targets:
            ctx.error(
                spec.entity,
                "duplicate_target",
                "Hai dòng trong file cùng khớp một bản ghi trong DB.",
                index=r.index,
                id_=r.file_id,
            )
            continue
        used_targets.add(target["id"])
        plan.id_map[r.file_id] = target["id"]
        if nat is not None:
            plan.natural_to_db[nat] = target["id"]

        # Field dự phòng chỉ bị loại khi DB đang có giá trị thật (khác NULL); nếu DB
        # đang NULL thì áp giá trị dự phòng cũng vô hại và còn lấp được chỗ trống
        # (vd task đổi sang done mà DB chưa có completed_at).
        if spec.entity == "task":
            _reconcile_completed(r, target)
        pair_unknown = bool(_PAIR_FIELDS & r.fallback) and set(spec.fields) >= _PAIR_FIELDS
        eff_fields = [
            name
            for name in spec.fields
            if not (name in r.fallback and target.get(name) is not None)
            and not (pair_unknown and name in _PAIR_FIELDS)
        ]
        changes = diff_fields(target, r.values, eff_fields)
        if not changes:
            counts.unchanged += 1
            continue
        older = r.values["updated_at"] < target["updated_at"]
        counts.replaced += 1
        if older:
            counts.replaced_older += 1
        if len(ctx.replacements) < MAX_REPLACEMENTS:
            ctx.replacements.append(
                Replacement(
                    entity=spec.entity,  # type: ignore[arg-type]
                    id=target["id"],
                    file_id=r.file_id,
                    label=r.label[: spec.label_max],
                    matched_by=matched_by,  # type: ignore[arg-type]
                    file_older_than_db=older,
                    changes=changes[:MAX_FIELDS_PER_REPLACEMENT],
                )
            )
        else:
            ctx.replacements_truncated = True
        # Đặt updated_at tường minh (D13). Giữ created_at của DB, không đưa vào SET.
        set_values = {name: r.values[name] for name in eff_fields}
        set_values["updated_at"] = r.values["updated_at"]
        # `changes` giữ lại để task ghi event `updated` mô tả đúng thay đổi.
        plan.updates.append(_Update(target["id"], r.file_id, set_values, changes))
        ctx.audit.append(
            _audit(
                spec.entity,
                target["id"],
                ImportAction.REPLACED,
                _jsonable(target),
                [c.field for c in changes],
            )
        )
    return plan


def _reconcile_completed(r: _Parsed, target: Mapping[str, Any]) -> None:
    """Giữ `completed_at` nhất quán với status HIỆU LỰC sau khi ghi đè.

    Status hiệu lực = status trong file, trừ khi file không nói gì về status (khi
    đó DB giữ nguyên status). Quy tắc:
    - hiệu lực là trạng thái MỞ (không done, không cancelled) -> completed_at = NULL
      (task mở lại thì không có ngày hoàn thành; để lại sẽ làm thống kê "hoàn thành
      7 ngày" sai). Giống task_service: reopen từ trạng thái đóng xoá completed_at;
    - `cancelled` là trạng thái đóng nhưng KHÔNG được ép: file thật (Jira sync) lưu
      thời điểm đóng ở completed_at của task cancelled, xoá nó là mất dữ liệu thật;
    - hiệu lực là `done` mà file không cho giá trị -> giữ ngày hoàn thành thật của DB,
      chỉ khi DB cũng trống mới dùng updated_at.
    Cần làm TRƯỚC khi tính danh sách field áp dụng vì nó đổi giá trị lẫn đánh dấu dự phòng.
    """
    status_missing = "status" in r.fallback and target.get("status") is not None
    status = _canon("status", target["status"] if status_missing else r.values["status"])
    if status not in ("done", "cancelled"):
        # Chỉ xoá khi file không cho giá trị; file nói tường minh một ngày thì giữ
        # đúng như file (nếu không, nhập lại cùng file sẽ không idempotent).
        if r.values["completed_at"] is None:
            r.fallback.discard("completed_at")
    elif status == "done" and r.values["completed_at"] is None:
        r.values["completed_at"] = target.get("completed_at") or r.values["updated_at"]
        r.fallback.discard("completed_at")


def _audit(
    entity: str,
    entity_id: uuid.UUID,
    action: ImportAction,
    before: dict[str, Any] | None,
    changed: list[str],
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "entity": ImportEntity(entity),
        "entity_id": entity_id,
        "action": action,
        "before": before,
        "changed_fields": changed,
    }


async def _resolve_project_refs(
    ctx: _Ctx,
    session: AsyncSession,
    entity: str,
    rows: list[_Parsed],
    projects: _Plan,
) -> None:
    """Đổi `project_id` của file sang id project trong DB (spec 3.1).

    Thứ tự thử: id trong file đã ánh xạ -> id có sẵn trong DB -> key của object
    `project` nhúng. Không thấy thì null kèm cảnh báo; không xoá liên kết nào
    ngoài trường hợp file không chỉ ra được project.
    """
    pending = [r for r in rows if not r.trashed]
    unknown_ids = {
        pid
        for r in pending
        if (pid := r.values["project_id"]) is not None and pid not in projects.id_map
    }
    db_ids = set(await _fetch_by_ids(session, Project.__table__, list(unknown_ids)))
    keys = {
        r.project_key
        for r in pending
        if r.project_key is not None and r.project_key not in projects.natural_to_db
    }
    key_to_db: dict[Hashable, uuid.UUID] = dict(projects.natural_to_db)
    if keys:
        for key, row in (await _natural_projects(session, sorted(keys))).items():
            key_to_db[key] = row["id"]

    for r in pending:
        pid = r.values["project_id"]
        if pid is not None and pid in projects.id_map:
            resolved: uuid.UUID | None = projects.id_map[pid]
        elif pid is not None and pid in db_ids:
            resolved = pid
        else:
            resolved = key_to_db.get(r.project_key) if r.project_key else None
            if resolved is None and (pid is not None or r.project_key is not None):
                # Null ở đây là do KHÔNG ánh xạ được, không phải file nói "không có
                # project": khi replace không được tháo liên kết đang có trong DB.
                r.fallback.add("project_id")
                ctx.warn(
                    entity,
                    "project_unlinked",
                    "Không tìm thấy project của bản ghi, để trống liên kết.",
                    index=r.index,
                    id_=r.file_id,
                )
        r.values["project_id"] = resolved
        if resolved is not None:
            # Tìm được project thật (kể cả qua key nhúng) thì giá trị không còn là dự phòng.
            r.fallback.discard("project_id")


async def _plan_events(
    ctx: _Ctx,
    session: AsyncSession,
    rows: list[_Parsed],
    tasks: _Plan,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Lập kế hoạch cho event: chỉ CHÈN event chưa có id, không bao giờ sửa/xoá.

    `task_events` là audit trail; ghi đè nó sẽ xoá dấu vết lịch sử. Trả về
    (event từ file sẽ chèn, event do chính lần nhập sinh ra).
    """
    counts = ctx.counts_of("task_event")
    file_events: list[dict[str, Any]] = []
    for r in rows:
        if r.trashed or not r.events:
            continue
        if r.file_id in tasks.skipped_personal_ids:
            counts.skipped_personal += len(r.events)
            continue
        if r.file_id not in tasks.id_map:
            counts.skipped_trash_in_db += len(r.events)
            continue
        db_task_id = tasks.id_map[r.file_id]
        for ev in r.events:
            file_events.append({**ev, "task_id": db_task_id, "__index__": r.index})

    seen: set[uuid.UUID] = set()
    for ev in file_events:
        if ev["id"] in seen:
            ctx.error(
                "task_event",
                "duplicate_id",
                "id event xuất hiện nhiều lần trong file.",
                index=ev["__index__"],
                id_=ev["id"],
            )
        seen.add(ev["id"])
    existing = await _fetch_event_ids(session, [e["id"] for e in file_events])
    to_insert: list[dict[str, Any]] = []
    for ev in file_events:
        if ev["id"] in existing:
            counts.unchanged += 1
            if existing[ev["id"]] != ev["task_id"]:
                # Không sửa, không chuyển event sang task khác (audit trail bất biến);
                # chỉ báo để người dùng biết file và DB bất đồng về chủ của event.
                ctx.warn(
                    "task_event",
                    "event_id_other_task",
                    "id event đã tồn tại trong DB nhưng thuộc task khác, bỏ qua.",
                    index=ev["__index__"],
                    id_=ev["id"],
                )
            continue
        counts.created += 1
        to_insert.append({k: v for k, v in ev.items() if k != "__index__"})
        ctx.audit.append(_audit("task_event", ev["id"], ImportAction.CREATED, None, []))

    generated: list[dict[str, Any]] = []
    for file_id in tasks.created_file_ids:
        generated.append(
            _generated_event(
                ctx,
                file_id,
                TaskEventType.SYNCED,
                {"import_id": ctx.import_id, "schema_version": ctx.schema_version},
            )
        )
    for upd in tasks.updates:
        changes = upd.changes
        generated.append(
            _generated_event(
                ctx,
                upd.db_id,
                TaskEventType.UPDATED,
                {
                    "import_id": ctx.import_id,
                    "changes": {c.field: {"old": c.old, "new": c.new} for c in changes},
                },
            )
        )
    return to_insert, generated


def _generated_event(
    ctx: _Ctx, task_id: uuid.UUID, event_type: TaskEventType, payload: dict[str, Any]
) -> dict[str, Any]:
    event_id = uuid.uuid4()
    # Có audit CREATED để script hoàn tác dọn luôn event do lần nhập sinh ra
    # (nếu không, hoàn tác task `replaced` để lại event `updated` mồ côi mô tả
    # một thay đổi đã bị quay lại).
    ctx.audit.append(_audit("task_event", event_id, ImportAction.CREATED, None, []))
    return {
        "id": event_id,
        "task_id": task_id,
        "event_type": event_type,
        "actor": "import:datafile",
        "payload": _jsonable(payload),
        "created_at": ctx.now,
    }


async def _fetch_event_ids(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """id event đã có -> task_id của nó (để phát hiện event trùng id nhưng thuộc task khác)."""
    table = TaskEvent.__table__
    out: dict[uuid.UUID, uuid.UUID] = {}
    for chunk in _chunks(ids, READ_BATCH):
        result = await session.execute(
            select(table.c.id, table.c.task_id).where(table.c.id.in_(chunk))
        )
        out.update((row[0], row[1]) for row in result)
    return out


# ═══════════════════════════════════════════════════════════════════════
#  Ghi
# ═══════════════════════════════════════════════════════════════════════


async def _apply_plan(session: AsyncSession, table: Table, plan: _Plan) -> None:
    """INSERT theo lô, UPDATE từng dòng.

    UPDATE bằng Core `update()` với `updated_at` nằm trong SET, không qua ORM:
    qua ORM, nếu giá trị `updated_at` của file trùng giá trị đang có thì thuộc tính
    không "đổi", SQLAlchemy bỏ nó khỏi SET và `onupdate=func.now()` đè giờ hiện tại
    lên, làm mất timestamp gốc (D13).
    """
    for chunk in _chunks(plan.creates, WRITE_BATCH):
        await session.execute(insert(table), list(chunk))
    for upd in plan.updates:
        await session.execute(update(table).where(table.c.id == upd.db_id).values(**upd.values))


async def _insert_rows(session: AsyncSession, table: Table, rows: list[dict[str, Any]]) -> None:
    for chunk in _chunks(rows, WRITE_BATCH):
        await session.execute(insert(table), list(chunk))


async def _write_audit(
    session: AsyncSession,
    ctx: _Ctx,
    *,
    kind: ImportKind,
    schema_version: int,
    file_sha256: str,
    actor: str,
) -> None:
    """Ghi sổ cái: một dòng `import_runs` rồi các dòng `import_audit`.

    Chỉ gọi khi sắp COMMIT. Dry-run không để lại dấu vết nào.
    """
    await session.execute(
        insert(ImportRun.__table__).values(
            id=ctx.import_id,
            kind=kind,
            file_sha256=file_sha256,
            schema_version=schema_version,
            # `options` ghi cờ đã dùng (include_personal cho phép ghi đè task cá nhân)
            # để audit biết lần nhập đó có bỏ rào chắn hay không; JSONB nên không cần
            # migration. Chỉ nằm trong sổ cái, không đổi ImportReport.
            counts={
                **{k: v.model_dump() for k, v in ctx.counts.items()},
                "options": {"include_personal": ctx.include_personal},
            },
            actor=actor,
        )
    )
    rows = [{**a, "import_id": ctx.import_id} for a in ctx.audit]
    await _insert_rows(session, ImportAudit.__table__, rows)


# ═══════════════════════════════════════════════════════════════════════
#  Điều phối và báo cáo
# ═══════════════════════════════════════════════════════════════════════


async def _take_lock(session: AsyncSession) -> None:
    """Chỉ cho một lần nhập chạy tại một thời điểm.

    Hai lần nhập đồng thời cùng lập kế hoạch trên dữ liệu cũ rồi ghi đè chéo nhau
    sẽ phá `expect_replaced` và `before` của audit. Lock theo transaction nên tự
    nhả khi commit/rollback, kể cả khi process chết.
    """
    got = await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:name))"), {"name": IMPORT_LOCK_NAME}
    )
    if not got:
        await session.rollback()
        raise ConflictError("Đang có một lần nhập khác chạy, hãy thử lại sau.")
    # Sau khi có khoá nhập: giới hạn thời gian chờ khoá dòng (FOR UPDATE, UPDATE) để
    # một transaction khác giữ dòng quá lâu thì request thất bại có kiểm soát (409)
    # thay vì treo. `set_config(..., true)` = SET LOCAL, hết hiệu lực khi transaction kết thúc.
    await session.execute(text("SELECT set_config('lock_timeout', :v, true)"), {"v": LOCK_TIMEOUT})


# SQLSTATE 55P03 = lock_not_available (hết lock_timeout); 40P01 = deadlock_detected
# (Postgres chọn nạn nhân và huỷ transaction của ta). Cả hai là xung đột tạm thời với
# một thao tác khác, thử lại được, nên đều là 409 chứ không phải lỗi dữ liệu hay 500.
_RETRYABLE_LOCK_CODES = frozenset({"55P03", "40P01"})


def _raise_if_lock_timeout(exc: SQLAlchemyError) -> None:
    """Đổi lỗi khoá tạm thời (hết lock_timeout, deadlock) thành 409 dễ hiểu."""
    orig = getattr(exc, "orig", None)
    for candidate in (orig, getattr(orig, "__cause__", None)):
        code = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if code in _RETRYABLE_LOCK_CODES:
            raise ConflictError(
                "Dữ liệu đang bị một thao tác khác khoá hoặc xung đột, hãy thử lại sau."
            ) from exc


def _report(ctx: _Ctx, *, schema_version: int, committed: bool, file_sha256: str) -> ImportReport:
    issues, truncated = ctx.build_issues()
    return ImportReport(
        import_id=ctx.import_id,
        dry_run=ctx.dry_run,
        committed=committed,
        schema_version=schema_version,
        file_sha256=file_sha256,
        counts=ctx.counts,
        errors=ctx.n_errors,
        warnings=ctx.n_warnings,
        issues=issues,
        issues_truncated=truncated,
        replacements=ctx.replacements,
        replacements_truncated=ctx.replacements_truncated,
        project_key_changes=ctx.key_changes,
        ignored_fields={k: sorted(v) for k, v in sorted(ctx.ignored.items()) if v},
    )


async def _finish(
    session: AsyncSession,
    ctx: _Ctx,
    *,
    kind: ImportKind,
    schema_version: int,
    expect_replaced: int | None,
    expect_sha256: str | None,
    file_sha256: str,
    actor: str,
    write: Callable[[], Awaitable[None]],
) -> ImportReport:
    """Kiểm rào chắn, ghi, rồi COMMIT hoặc ROLLBACK.

    `write` chạy cả khi dry-run để Postgres kiểm CHECK/unique thật. Chỉ COMMIT
    khi: không lỗi, không phải dry-run, file đúng là file đã dry-run
    (`expect_sha256`), và số bản ghi bị ghi đè đúng bằng số người dùng đã thấy
    (`expect_replaced`). Con số một mình không chứng minh được "cùng file": hai file
    khác nhau có thể cùng số lần ghi đè.
    """
    committed = False
    try:
        if (
            ctx.n_errors == 0
            and not ctx.dry_run
            and (expect_sha256 or "").lower() != file_sha256.lower()
        ):
            ctx.error(
                "file",
                "file_changed_since_dry_run",
                "File gửi lên khác file đã kiểm tra (dry-run); hãy kiểm tra lại file này.",
            )
        if ctx.n_errors == 0 and not ctx.dry_run and ctx.total_replaced() != expect_replaced:
            ctx.error(
                "file",
                "replace_count_mismatch",
                f"Số bản ghi bị ghi đè thực tế ({ctx.total_replaced()}) khác số mong đợi "
                f"({expect_replaced}); dữ liệu đã đổi sau lần kiểm tra, hãy kiểm tra lại.",
            )
        if ctx.n_errors == 0:
            await write()
            if not ctx.dry_run:
                await _write_audit(
                    session,
                    ctx,
                    kind=kind,
                    schema_version=schema_version,
                    file_sha256=file_sha256,
                    actor=actor,
                )
        if ctx.n_errors == 0 and not ctx.dry_run:
            await session.commit()
            committed = True
        else:
            await session.rollback()
    except SQLAlchemyError as exc:
        await session.rollback()
        _raise_if_lock_timeout(exc)
        # Chỉ lấy tên ràng buộc, không đưa thông điệp gốc (có thể chứa giá trị cột).
        constraint = getattr(getattr(exc, "orig", None), "constraint_name", None)
        ctx.error(
            "file",
            "db_constraint",
            f"Postgres từ chối dữ liệu (ràng buộc: {constraint or 'không rõ'}).",
        )
        await session.rollback()
        committed = False
    report = _report(
        ctx, schema_version=schema_version, committed=committed, file_sha256=file_sha256
    )
    c = report.counts
    logger.info(
        "nhập dữ liệu xong",
        extra={
            "import_id": str(report.import_id),
            "kind": kind.value,
            "dry_run": report.dry_run,
            "committed": report.committed,
            "errors": report.errors,
            "created": sum(v.created for v in c.values()),
            "replaced": sum(v.replaced for v in c.values()),
        },
    )
    return report


def _require_expect(dry_run: bool, expect_replaced: int | None, expect_sha256: str | None) -> None:
    if not dry_run and (expect_replaced is None or not expect_sha256):
        raise ValidationError("Nhập thật bắt buộc truyền expect_replaced và expect_sha256.")


async def import_datafile(
    session: AsyncSession,
    envelope: DataFileEnvelope,
    *,
    dry_run: bool = True,
    expect_replaced: int | None = None,
    expect_sha256: str | None = None,
    file_sha256: str,
    actor: str = "import:datafile",
    include_personal: bool = False,
) -> ImportReport:
    """Nhập projects, tasks (kèm events), notes từ `builder-data.json`.

    Xem banner đầu module: hàm này GHI ĐÈ, không xoá. `dry_run` mặc định True để
    quên truyền tham số thì không ghi gì. `include_personal` mặc định False: task
    đang `personal` trong DB được bảo vệ. Lưu ý `expect_replaced` lấy từ dry-run:
    dry-run không bật mà nhập thật bật thì số ghi đè lệch và bị huỷ
    (`replace_count_mismatch`), đó là hành vi mong muốn.
    """
    _require_expect(dry_run, expect_replaced, expect_sha256)
    n_events = sum(len(t.get("events") or []) for t in envelope.tasks if isinstance(t, dict))
    if n_events > MAX_EVENTS:
        raise ValidationError(f"Tối đa {MAX_EVENTS} event mỗi file.")

    await _take_lock(session)
    ctx = _Ctx(
        dry_run=dry_run,
        schema_version=envelope.schema_version,
        include_personal=include_personal,
    )
    if envelope.model_extra:
        ctx.note_ignored("file", envelope.model_extra)
    if envelope.meta:
        # B1 chưa nhập meta (current_users thuộc B2).
        ctx.note_ignored("file", ["meta"])

    projects = _parse_rows(ctx, "project", envelope.projects, _parse_project)
    tasks = _parse_rows(ctx, "task", envelope.tasks, _parse_task)
    notes = _parse_rows(ctx, "note", envelope.notes, _parse_note)

    task_plan = note_plan = project_plan = _Plan()
    file_events: list[dict[str, Any]] = []
    generated: list[dict[str, Any]] = []
    if ctx.n_errors == 0:
        try:
            project_plan = await _plan_entity(ctx, session, PROJECT_SPEC, projects)
            await _resolve_project_refs(ctx, session, "task", tasks, project_plan)
            await _resolve_project_refs(ctx, session, "note", notes, project_plan)
            task_plan = await _plan_entity(ctx, session, TASK_SPEC, tasks)
            note_plan = await _plan_entity(ctx, session, NOTE_SPEC, notes)
            file_events, generated = await _plan_events(ctx, session, tasks, task_plan)
        except SQLAlchemyError as exc:
            await session.rollback()
            _raise_if_lock_timeout(exc)
            raise

    async def write() -> None:
        # Thứ tự theo khoá ngoại: project -> task -> event -> note.
        await _apply_plan(session, PROJECT_SPEC.table, project_plan)
        await _apply_plan(session, TASK_SPEC.table, task_plan)
        await _insert_rows(session, TaskEvent.__table__, file_events)
        await _insert_rows(session, TaskEvent.__table__, generated)
        await _apply_plan(session, NOTE_SPEC.table, note_plan)

    return await _finish(
        session,
        ctx,
        kind=ImportKind.DATAFILE,
        schema_version=envelope.schema_version,
        expect_replaced=expect_replaced,
        expect_sha256=expect_sha256,
        file_sha256=file_sha256,
        actor=actor,
        write=write,
    )


async def import_ai_logs(
    session: AsyncSession,
    envelope: AiLogsEnvelope,
    *,
    dry_run: bool = True,
    expect_replaced: int | None = None,
    expect_sha256: str | None = None,
    file_sha256: str,
    actor: str = "import:ai_logs",
) -> ImportReport:
    """Nhập `ai-logs.json` vào bảng `ai_logs` (cùng rào chắn như `import_datafile`)."""
    _require_expect(dry_run, expect_replaced, expect_sha256)
    await _take_lock(session)
    ctx = _Ctx(dry_run=dry_run, schema_version=envelope.schema_version)
    if envelope.model_extra:
        ctx.note_ignored("file", envelope.model_extra)
    logs = _parse_rows(ctx, "ai_log", envelope.ai_logs, _parse_ai_log)
    plan = _Plan()
    if ctx.n_errors == 0:
        try:
            plan = await _plan_entity(ctx, session, AI_LOG_SPEC, logs)
        except SQLAlchemyError as exc:
            await session.rollback()
            _raise_if_lock_timeout(exc)
            raise

    async def write() -> None:
        await _apply_plan(session, AI_LOG_SPEC.table, plan)

    return await _finish(
        session,
        ctx,
        kind=ImportKind.AI_LOGS,
        schema_version=envelope.schema_version,
        expect_replaced=expect_replaced,
        expect_sha256=expect_sha256,
        file_sha256=file_sha256,
        actor=actor,
        write=write,
    )
