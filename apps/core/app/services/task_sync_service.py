"""Upsert hàng loạt task từ nguồn tích hợp (Jira, URL sync, Excel...).

Quy tắc chính (xem docs/specs/task-scope.md):
- Khớp theo `(source, external_id)` CHỈ trên task còn sống (partial index). Task trong
  thùng rác trùng khoá thì tạo task MỚI.
- Tích hợp chỉ được ghi `scope=work`. Task trùng khoá mà đang `scope=personal` KHÔNG bị
  ghi đè, chỉ đếm vào `skipped_personal`.
- Không đổi thì không ghi (không bump `updated_at`, không sinh event): chạy hai lần liên
  tiếp là no-op.
- Ngữ nghĩa GỘP khớp chế độ file (apps/web/app/jira-actions.ts): `tags` là hợp (union) của
  tag đang có và tag từ nguồn; `description` chỉ điền khi task đang rỗng. Nhờ vậy tag User
  tự gắn và mô tả User sửa không mất sau mỗi lần sync.
- Dữ liệu của lô là UNTRUSTED: `raw_payload` bị lọc khoá/giá trị nhạy cảm, cắt kích thước.

Ranh giới lỗi: item sai SCHEMA (thiếu title, status lạ...) làm cả request 422 (lỗi client,
fail fast, ở tầng Pydantic). Item sai theo DỮ LIỆU (project_key không chuẩn hoá được,
external_id trùng trong lô, raw_payload chứa NaN/Infinity) chỉ bị báo vào `errors[]`, các
item còn lại vẫn được xử lý. `raw_payload` quá lớn/sâu/hết ngân sách lô KHÔNG phải lỗi:
task vẫn được upsert, payload bị bỏ và báo vào `warnings[]`. Lô ghi trong một transaction:
lỗi DB bất ngờ thì rollback cả lô.
"""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import locks
from app.models.enums import TaskEventType, TaskScope, TaskSource, TaskStatus
from app.models.project import Project
from app.models.task import Task, TaskEvent
from app.schemas.task_upsert import (
    TaskUpsert,
    TaskUpsertResult,
    UpsertItemError,
    UpsertItemWarning,
)
from app.services import clock
from app.services.errors import ConflictError
from app.services.import_service import normalize_project_key
from app.services.jsonable import jsonable

logger = logging.getLogger(__name__)

MAX_RAW_PAYLOAD_BYTES = 64 * 1024
# Kích thước payload THÔ (trước khi lọc). Đo cả trước lọc để payload khổng lồ gắn sau một
# khoá bị lọc không bắt server xử lý/duyệt vô ích.
MAX_RAW_PAYLOAD_PRE_FILTER_BYTES = 4 * MAX_RAW_PAYLOAD_BYTES
# Tổng payload thô của cả lô; item sau khi vượt thì mất payload (vẫn upsert).
MAX_BATCH_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_RAW_PAYLOAD_DEPTH = 32
# asyncpg giới hạn 32 767 tham số mỗi câu lệnh; IN (...) chỉ dùng 1 tham số mỗi khoá.
_FETCH_CHUNK = 500
# Giá trị chuỗi trong payload của event bị cắt: description Jira có thể rất dài.
_DIFF_STR_MAX = 300
_REDACTED = "[REDACTED]"

# Khoá (đã hạ chữ thường, bỏ ký tự không phải chữ-số) chứa một trong các mảnh này bị
# loại khỏi raw_payload ở mọi độ sâu. Khớp theo mảnh con để bắt cả `access_token`,
# `X-Api-Key`, `Set-Cookie`, `clientSecret`, `private_key`. Đổi lại: có thể loại nhầm khoá
# vô hại như `tokens_used`; chấp nhận vì raw_payload chỉ để đối soát, không phải dữ liệu
# nghiệp vụ.
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "credential",
    "token",
    "password",
    "passwd",
    "pwd",
    "secret",
    "cookie",
    "apikey",
    "privatekey",
    "session",
    "bearer",
    "jwt",
    "csrf",
    "xsrf",
    "signature",
)
# Khoá phải khớp CHÍNH XÁC (mảnh "auth" sẽ bắt nhầm "author").
_SENSITIVE_EXACT_KEYS = frozenset({"auth"})

# Giá trị chuỗi chứa secret dù khoá vô hại (header dán vào comment, URL có token...).
_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_TOKEN_QUERY_RE = re.compile(r"([?&](?:access_)?token=)[^&\s#]*", re.IGNORECASE)
_JWT_RE = re.compile(r"eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*")

# Trường nguồn ngoài sở hữu, có thể bị upsert ghi đè. Cố ý KHÔNG có spent_minutes,
# scope, completed_at do User/hệ thống quản. `tags` và `description` có luật gộp riêng
# trong `_merge_wanted`.
_SYNCED_FIELDS = (
    "title",
    "description",
    "assignee",
    "status",
    "priority",
    "due_at",
    "scheduled_for",
    "estimate_minutes",
    "tags",
    "external_url",
)

_CLOSED = (TaskStatus.DONE, TaskStatus.CANCELLED)


class PayloadDropped(ValueError):
    """raw_payload không dùng được nhưng task vẫn upsert: báo `warnings`, không phải `errors`."""


# ═══════════════════════════════════════════════════════════════════════
#  Làm sạch dữ liệu không đáng tin (hàm thuần)
# ═══════════════════════════════════════════════════════════════════════


def _is_sensitive_key(key: str) -> bool:
    folded = "".join(ch for ch in key.lower() if ch.isalnum())
    return folded in _SENSITIVE_EXACT_KEYS or any(part in folded for part in _SENSITIVE_KEY_PARTS)


def _strip_nul(text: str) -> str:
    # Postgres từ chối U+0000 trong text và JSONB, làm hỏng cả lô.
    return text.replace("\x00", "")


def _redact_string(text: str) -> str:
    text = _strip_nul(text)
    text = _BEARER_RE.sub(f"Bearer {_REDACTED}", text)
    text = _TOKEN_QUERY_RE.sub(rf"\1{_REDACTED}", text)
    return _JWT_RE.sub(_REDACTED, text)


def sanitize_payload(value: Any, _depth: int = 0) -> Any:
    """Loại khoá nhạy cảm, che giá trị chuỗi chứa secret, bỏ NUL ở mọi độ sâu; trả bản sao.

    Dict dạng `{"name": "Authorization", "value": "..."}` (header/field kiểu danh sách
    name-value) được coi `name` như một khoá: nhạy cảm thì bỏ `value`.

    Raises:
        PayloadDropped: lồng quá sâu (chống payload thù địch làm tràn đệ quy).
        ValueError: có số không hữu hạn (NaN/Infinity); JSONB của Postgres không lưu được.
    """
    if _depth > MAX_RAW_PAYLOAD_DEPTH:
        raise PayloadDropped("raw_payload lồng quá sâu")
    if isinstance(value, dict):
        name = value.get("name")
        drop_value = isinstance(name, str) and _is_sensitive_key(name)
        return {
            _strip_nul(str(k)): sanitize_payload(v, _depth + 1)
            for k, v in value.items()
            if not _is_sensitive_key(str(k)) and not (drop_value and k == "value")
        }
    if isinstance(value, list):
        return [sanitize_payload(v, _depth + 1) for v in value]
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("raw_payload chứa số không hữu hạn (NaN/Infinity)")
    return value


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except RecursionError:
        raise PayloadDropped("raw_payload lồng quá sâu") from None


def measure_payload(raw: dict[str, Any] | None) -> int:
    """Kích thước JSON của payload THÔ (0 nếu không có). Ném PayloadDropped nếu quá lớn."""
    if raw is None:
        return 0
    size = _json_size(raw)
    if size > MAX_RAW_PAYLOAD_PRE_FILTER_BYTES:
        raise PayloadDropped(f"raw_payload thô vượt {MAX_RAW_PAYLOAD_PRE_FILTER_BYTES // 1024} KB")
    return size


def prepare_payload(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Đo kích thước thô, làm sạch, rồi đo lại sau lọc.

    Raises:
        PayloadDropped: quá lớn/sâu, nên bỏ payload nhưng giữ task.
        ValueError: payload hỏng (NaN/Infinity), item vào `errors`.
    """
    if raw is None:
        return None
    measure_payload(raw)
    clean = sanitize_payload(raw)
    if _json_size(clean) > MAX_RAW_PAYLOAD_BYTES:
        raise PayloadDropped(f"raw_payload vượt {MAX_RAW_PAYLOAD_BYTES // 1024} KB")
    return clean


def _to_utc(value: datetime | None) -> datetime | None:
    """Không múi giờ = giờ địa phương theo display_timezone (cùng quy ước B3)."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=clock.display_tz())
    return value


def _short(value: Any) -> Any:
    value = jsonable(value)
    if isinstance(value, str) and len(value) > _DIFF_STR_MAX:
        return value[:_DIFF_STR_MAX] + "…"
    return value


# ═══════════════════════════════════════════════════════════════════════
#  Điều phối
# ═══════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class _Prepared:
    index: int
    item: TaskUpsert
    project_key: str | None
    payload: dict[str, Any] | None


async def _fetch_alive(
    session: AsyncSession, source: TaskSource, external_ids: Sequence[str]
) -> dict[str, Task]:
    """Task còn sống theo khoá, KHOÁ DÒNG (`FOR UPDATE OF tasks`).

    Advisory lock chỉ chặn các bên ghi hàng loạt; PATCH task của User không đi qua nó.
    Khoá dòng để User không sửa chen giữa lúc ta đọc và ghi (mất cập nhật). ORDER BY id
    cho thứ tự khoá ổn định. Quá lock_timeout (đã đặt theo transaction) thì 409.
    """
    found: dict[str, Task] = {}
    async with locks.conflict_on_lock_timeout(
        session, "Có task đang bị thao tác khác giữ, hãy thử lại sau."
    ):
        for start in range(0, len(external_ids), _FETCH_CHUNK):
            chunk = external_ids[start : start + _FETCH_CHUNK]
            stmt = (
                select(Task)
                .where(
                    Task.source == source,
                    Task.external_id.in_(chunk),
                    Task.deleted_at.is_(None),
                )
                .order_by(Task.id)
                .with_for_update(of=Task)
            )
            for task in (await session.execute(stmt)).scalars():
                if task.external_id is not None:
                    found[task.external_id] = task
    return found


async def _resolve_projects(
    session: AsyncSession, wanted: dict[str, str | None]
) -> dict[str, uuid.UUID]:
    """key -> project_id; tạo project chưa có bằng MỘT câu INSERT ... ON CONFLICT DO NOTHING.

    Không flush từng project: một lô nhiều project chỉ tốn hai câu lệnh, và nếu bên khác
    vừa tạo cùng key thì bỏ qua êm thay vì IntegrityError. Project đã có KHÔNG bị sửa
    tên/màu.
    """
    if not wanted:
        return {}
    keys = sorted(wanted)
    await session.execute(
        pg_insert(Project)
        .values([{"id": uuid.uuid4(), "key": k, "name": (wanted[k] or k)[:200]} for k in keys])
        .on_conflict_do_nothing(index_elements=["key"])
    )
    rows = await session.execute(select(Project.key, Project.id).where(Project.key.in_(keys)))
    return dict(rows.all())


def _event(task: Task, kind: TaskEventType, actor: str, payload: dict[str, Any]) -> TaskEvent:
    return TaskEvent(task_id=task.id, event_type=kind, actor=actor, payload=jsonable(payload))


def _same_host(url: str | None, host: str) -> bool:
    """True nếu `url` rỗng hoặc có host trùng `host` (không phân biệt hoa thường)."""
    if not url:
        return True
    try:
        return (urlsplit(url).hostname or "").lower() == host.lower()
    except ValueError:
        return False


def _wanted_values(
    p: _Prepared, project_ids: dict[str, uuid.UUID], create_only: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Giá trị mong muốn của các trường mà client có gửi (cho cập nhật).

    Trường trong `create_only` không bao giờ được đưa vào cập nhật (chỉ dùng khi tạo mới).
    """
    sent = p.item.model_fields_set
    values: dict[str, Any] = {}
    for name in _SYNCED_FIELDS:
        if name in sent and name not in create_only:
            value = getattr(p.item, name)
            values[name] = _to_utc(value) if name == "due_at" else value
    if "project_key" in sent and "project_key" not in create_only:
        values["project_id"] = project_ids[p.project_key] if p.project_key else None
    return values


def _merge_wanted(task: Task, wanted: dict[str, Any]) -> dict[str, Any]:
    """Áp luật gộp: tags = hợp (giữ thứ tự, bỏ trùng), description chỉ điền khi đang rỗng."""
    merged = dict(wanted)
    if "tags" in merged:
        merged["tags"] = list(dict.fromkeys([*task.tags, *merged["tags"]]))
    if "description" in merged and (task.description or "").strip():
        del merged["description"]
    return merged


async def upsert_batch(
    session: AsyncSession,
    source: TaskSource,
    items: Sequence[TaskUpsert],
    *,
    actor: str | None = None,
    create_only: frozenset[str] = frozenset(),
    owner_host: str | None = None,
) -> TaskUpsertResult:
    """Upsert một lô task của một nguồn tích hợp, idempotent, trong MỘT transaction.

    WHY có các chốt này:
    - Khoá: advisory lock chung với nhập JSON/ghi cài đặt (db/locks.py) để hai lô song
      song hay lô với lần nhập không cùng thấy "chưa có" rồi tạo trùng; sau đó
      `FOR UPDATE` trên các task khớp để PATCH của User không bị ghi đè lặng lẽ. Chờ quá
      lock_timeout (5s) thì 409; vi phạm `uq_tasks_source_external_id` lúc flush (bên
      khác chen vào) cũng 409 "thử lại". Lock chỉ lấy SAU tiền xử lý thuần Python để
      không giữ khoá lúc đang CPU-bound.
    - Giới hạn: tối đa 1000 item, body 20 MB (api/capped.py); raw_payload tối đa 64 KB
      sau lọc, 256 KB thô, 16 MB tổng lô. Vượt thì bỏ payload và báo `warnings`, KHÔNG
      loại task.
    - Luật personal: task trùng khoá mà `scope=personal` không bị ghi đè (đếm
      `skipped_personal`); tích hợp chỉ tạo `scope=work`.
    - Ngữ nghĩa gộp: tags là hợp, description chỉ điền khi rỗng; các trường khác chỉ ghi
      khi client có gửi (`model_fields_set`) và khác giá trị hiện có.
    - Mốc thời gian: task mới dùng `created_at` của nguồn nếu có; task ở trạng thái đóng
      dùng `completed_at` của nguồn, KHÔNG đặt now() (task Jira đã đóng từ năm ngoái không
      được tính vào "hoàn thành hôm nay"). Khi một task cũ chuyển sang đóng ở lần update:
      `completed_at` của nguồn nếu có, không thì now().

    `actor` là giá trị ghi vào `task_events.actor`; mặc định `integration:<source>` (route
    upsert-batch). Connector chạy trong core truyền `integration:<tên kết nối>` để sổ sự
    kiện nói rõ kết nối nào đã ghi. Chuỗi bị cắt về 100 ký tự (độ dài cột).

    `create_only`: tên trường (`priority`, `due_at`, `assignee`, `project_key`...) chỉ được
    ghi khi TẠO task, không bao giờ ghi đè task đã có. Jira sync dùng để giữ giá trị User
    đã sửa tay (cùng ngữ nghĩa chế độ file); route upsert-batch không truyền, giữ hành vi cũ.

    `owner_host`: chỉ dùng khi sync theo kết nối. Task đã có mà `external_url` thuộc host
    KHÁC thì không bị ghi (vào `errors`), để hai kết nối khác Jira không ghi đè task của
    nhau khi trùng `(source, external_id)`. Task không có external_url vẫn được cập nhật.

    Raises:
        ConflictError: 409 khi hết hạn chờ khoá hoặc va chạm unique với bên ghi khác.
    """
    actor = (actor or f"integration:{source.value}")[:100]
    errors: list[UpsertItemError] = []
    warnings: list[UpsertItemWarning] = []

    # ── Tiền xử lý từng item (thuần Python): lỗi dữ liệu chỉ loại item đó ──
    prepared: list[_Prepared] = []
    seen: set[str] = set()
    budget_used = 0
    for index, item in enumerate(items):
        if item.external_id in seen:
            errors.append(UpsertItemError(index=index, reason="external_id trùng trong lô"))
            continue
        try:
            key = normalize_project_key(item.project_key) if item.project_key else None
        except ValueError:
            errors.append(UpsertItemError(index=index, reason="project_key không hợp lệ"))
            continue
        payload: dict[str, Any] | None = None
        try:
            raw_size = measure_payload(item.raw_payload)
            if budget_used + raw_size > MAX_BATCH_PAYLOAD_BYTES:
                raise PayloadDropped(
                    f"raw_payload bị bỏ: tổng payload của lô vượt "
                    f"{MAX_BATCH_PAYLOAD_BYTES // (1024 * 1024)} MB"
                )
            budget_used += raw_size
            payload = prepare_payload(item.raw_payload)
        except PayloadDropped as exc:
            warnings.append(UpsertItemWarning(index=index, reason=str(exc)))
        except ValueError as exc:
            errors.append(UpsertItemError(index=index, reason=str(exc)))
            continue
        seen.add(item.external_id)
        prepared.append(_Prepared(index, item, key, payload))

    # ── Khoá rồi đọc: từ đây tới hết hàm là đoạn giữ khoá ───────────────
    await locks.take_import_write_lock(session)
    existing = await _fetch_alive(session, source, [p.item.external_id for p in prepared])

    wanted_projects: dict[str, str | None] = {}
    for p in prepared:
        if p.project_key and p.project_key not in wanted_projects:
            wanted_projects[p.project_key] = p.item.project_name
    project_ids = await _resolve_projects(session, wanted_projects)

    added = updated = unchanged = skipped_personal = 0
    now = clock.now_utc()
    new_events: list[TaskEvent] = []

    for p in prepared:
        task = existing.get(p.item.external_id)
        if task is None:
            task = _build_task(p, source, project_ids)
            session.add(task)
            new_events.append(
                _event(
                    task,
                    TaskEventType.SYNCED,
                    actor,
                    {"action": "created", "source": source.value, "external_id": task.external_id},
                )
            )
            added += 1
            continue

        if task.scope is not TaskScope.WORK:
            skipped_personal += 1
            continue

        if owner_host is not None and not _same_host(task.external_url, owner_host):
            errors.append(
                UpsertItemError(index=p.index, reason="task thuộc nguồn/kết nối khác, không ghi đè")
            )
            continue

        diff = _apply_changes(
            task,
            _merge_wanted(task, _wanted_values(p, project_ids, create_only)),
            p.payload,
            now,
            _to_utc(p.item.completed_at),
        )
        if not diff:
            unchanged += 1
            continue
        new_events.append(_event(task, TaskEventType.UPDATED, actor, {"changes": diff}))
        updated += 1

    # Một flush cho cả lô; task mới đã có id sẵn nên event gắn được trước khi flush.
    session.add_all(new_events)
    try:
        async with locks.conflict_on_lock_timeout(
            session, "Có task đang bị thao tác khác giữ, hãy thử lại sau."
        ):
            await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if locks.constraint_name(exc) == "uq_tasks_source_external_id":
            raise ConflictError("Có lần đồng bộ khác vừa tạo cùng task, hãy thử lại sau.") from None
        raise

    logger.info(
        "upsert-batch: source=%s added=%d updated=%d unchanged=%d skipped_personal=%d "
        "errors=%d warnings=%d",
        source.value,
        added,
        updated,
        unchanged,
        skipped_personal,
        len(errors),
        len(warnings),
    )
    return TaskUpsertResult(
        added=added,
        updated=updated,
        unchanged=unchanged,
        skipped_personal=skipped_personal,
        errors=sorted(errors, key=lambda e: e.index),
        warnings=sorted(warnings, key=lambda w: w.index),
    )


def _build_task(p: _Prepared, source: TaskSource, project_ids: dict[str, uuid.UUID]) -> Task:
    item = p.item
    status = item.status
    extra: dict[str, Any] = {}
    # Chỉ truyền khi có: gán None tường minh sẽ ghi NULL đè server_default now().
    if item.created_at is not None:
        extra["created_at"] = _to_utc(item.created_at)
    return Task(
        # id gán sẵn để TaskEvent trỏ được vào task trước khi flush.
        id=uuid.uuid4(),
        title=item.title,
        description=item.description,
        assignee=item.assignee,
        status=status,
        priority=item.priority,
        project_id=project_ids[p.project_key] if p.project_key else None,
        due_at=_to_utc(item.due_at),
        scheduled_for=item.scheduled_for,
        estimate_minutes=item.estimate_minutes,
        tags=list(item.tags),
        source=source,
        # Tích hợp chỉ ghi scope=work (task-scope.md); không phụ thuộc default theo source.
        scope=TaskScope.WORK,
        external_id=item.external_id,
        external_url=item.external_url,
        raw_payload=p.payload,
        # Đóng mà nguồn không cho mốc thì để trống, KHÔNG dùng now().
        completed_at=_to_utc(item.completed_at) if status in _CLOSED else None,
        **extra,
    )


def _apply_changes(
    task: Task,
    wanted: dict[str, Any],
    payload: dict[str, Any] | None,
    now: datetime,
    source_completed_at: datetime | None,
) -> dict[str, dict[str, Any]]:
    """Áp giá trị mới lên task, trả diff (rỗng nếu không đổi gì và KHÔNG đụng vào task).

    `raw_payload` không tính là thay đổi: payload nguồn ngoài có trường tự đổi mỗi lần
    (vd. `updated`), nếu tính thì mọi lần sync đều bump `updated_at`. Nó chỉ được làm mới
    khi có thay đổi thật khác.

    `completed_at` chỉ đổi theo trạng thái: sang đóng thì lấy mốc của nguồn (không có thì
    now), mở lại thì xoá. Task đã đóng mà chưa có mốc sẽ được điền khi nguồn cung cấp.
    """
    diff: dict[str, dict[str, Any]] = {}
    for name, new_value in wanted.items():
        old_value = getattr(task, name)
        if old_value != new_value:
            diff[name] = {"from": _short(old_value), "to": _short(new_value)}

    fill_completed = (
        "status" not in diff
        and task.status in _CLOSED
        and task.completed_at is None
        and source_completed_at is not None
    )
    if not diff and not fill_completed:
        return diff

    for name in diff:
        setattr(task, name, wanted[name])
    if "status" in diff:
        if task.status in _CLOSED:
            task.completed_at = source_completed_at or now
        else:
            task.completed_at = None
    elif fill_completed:
        task.completed_at = source_completed_at
        diff["completed_at"] = {"from": None, "to": _short(source_completed_at)}
    if payload is not None:
        task.raw_payload = payload
    return diff
