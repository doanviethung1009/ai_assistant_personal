from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import ColumnElement, Integer, Select, and_, case, cast, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.enums import (
    TaskEventType,
    TaskPriority,
    TaskScope,
    TaskSource,
    TaskStatus,
    default_scope_for,
)
from app.models.project import Project
from app.models.task import Task, TaskEvent
from app.schemas.task import MAX_OWNER_LEN, MAX_OWNERS, TaskCreate, TaskUpdate, TaskView
from app.services import clock
from app.services.clock import local_day_bounds_utc, local_today, now_utc, today_all_day_cutoff
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.jsonable import jsonable

# Tên cũ, giữ để quy ước "payload event qua _jsonable()" trong tài liệu vẫn đúng.
_jsonable = jsonable

CLOSED_STATUSES = (TaskStatus.DONE, TaskStatus.CANCELLED)

SortField = Literal["created_at", "updated_at", "due_at", "priority", "title", "scheduled_for"]

# Field mà thay đổi sẽ được ghi vào task_events
_TRACKED_FIELDS = (
    "title",
    "description",
    "priority",
    "project_id",
    "due_at",
    "scheduled_for",
    "estimate_minutes",
    "tags",
    "scope",
)


@dataclass(slots=True)
class TaskFilters:
    status: list[TaskStatus] | None = None
    priority: list[TaskPriority] | None = None
    project_id: uuid.UUID | None = None
    source: TaskSource | None = None
    assignee: str | None = None
    tags: list[str] = field(default_factory=list)
    query: str | None = None
    scheduled_on: date | None = None
    due_before: datetime | None = None
    include_closed: bool = False
    view: TaskView = TaskView.ALL
    owners: list[str] = field(default_factory=list)
    limit: int = 50
    offset: int = 0
    sort_by: SortField = "created_at"
    sort_desc: bool = True


def _alive():
    """Điều kiện task chưa bị xoá mềm.

    Phải có trong MỌI truy vấn nghiệp vụ. Thiếu nó là task trong thùng rác
    lại xuất hiện trong agenda và thống kê.
    """
    return Task.deleted_at.is_(None)


def validate_view_params(view: TaskView, owners: list[str] | None) -> list[str]:
    """Chuẩn hoá và kiểm `owner` đi kèm `view`; trả danh sách tên đã strip.

    `owner` chỉ có nghĩa với view=mine. Đi kèm view khác thì từ chối (422) thay vì
    lặng lẽ bỏ qua, để lỗi gọi API lộ ra ngay. Tên chỉ dùng trong `IN (...)` có bind
    param, không bao giờ nối vào chuỗi SQL.
    """
    if not owners:
        return []
    if view is not TaskView.MINE:
        raise ValidationError("owner chỉ hợp lệ khi view=mine")
    if len(owners) > MAX_OWNERS:
        raise ValidationError(f"owner tối đa {MAX_OWNERS} tên")
    cleaned = [name.strip() for name in owners]
    if any(not name or len(name) > MAX_OWNER_LEN for name in cleaned):
        raise ValidationError(f"mỗi owner phải dài 1-{MAX_OWNER_LEN} ký tự")
    return cleaned


def _view_clause(view: TaskView, owners: Sequence[str] = ()) -> ColumnElement[bool] | None:
    """Điều kiện scope cho một view; None nghĩa là không lọc (view=all).

    Nguồn DUY NHẤT của định nghĩa "việc của tôi" ở backend (list, agenda, stats cùng
    dùng). Web có bản sao ở lib/task-scope.ts (`matchesView`), hai bản phải khớp.
    Nhánh `assignee IS NULL AND external_id IS NULL` giữ task công việc User tự tạo
    (không giao ai, không đến từ tích hợp) hiện ở "Hôm nay"; task Jira chưa ai nhận
    thì không hiện. So khớp assignee CHÍNH XÁC (phân biệt hoa thường). Chuỗi rỗng và
    khoảng trắng thừa đã được chuẩn hoá khi ghi (rỗng -> NULL, strip), nên ở đây chỉ
    cần xét NULL; web chế độ file cũng nên coi '' như null.
    """
    if view is TaskView.ALL:
        return None
    if view is TaskView.PERSONAL:
        return Task.scope == TaskScope.PERSONAL
    if view is TaskView.WORK:
        return Task.scope == TaskScope.WORK
    work_mine = [Task.assignee.is_(None) & Task.external_id.is_(None)]
    if owners:
        work_mine.append(Task.assignee.in_(list(owners)))
    return or_(
        Task.scope == TaskScope.PERSONAL,
        and_(Task.scope == TaskScope.WORK, or_(*work_mine)),
    )


def _priority_rank():
    """Ưu tiên lưu dạng VARCHAR nên phải map sang số để sắp xếp đúng thứ tự."""
    return case(
        {
            TaskPriority.URGENT.value: 3,
            TaskPriority.HIGH.value: 2,
            TaskPriority.MEDIUM.value: 1,
            TaskPriority.LOW.value: 0,
        },
        value=Task.priority,
        else_=0,
    )


def _apply_filters(stmt: Select[Any], filters: TaskFilters) -> Select[Any]:
    stmt = stmt.where(_alive())

    view_clause = _view_clause(filters.view, filters.owners)
    if view_clause is not None:
        stmt = stmt.where(view_clause)

    if filters.status:
        stmt = stmt.where(Task.status.in_(filters.status))
    elif not filters.include_closed:
        stmt = stmt.where(Task.status.notin_(CLOSED_STATUSES))

    if filters.priority:
        stmt = stmt.where(Task.priority.in_(filters.priority))
    if filters.project_id is not None:
        stmt = stmt.where(Task.project_id == filters.project_id)
    if filters.source is not None:
        stmt = stmt.where(Task.source == filters.source)
    if filters.assignee:
        stmt = stmt.where(Task.assignee == filters.assignee)
    if filters.tags:
        # contains → toán tử @> của Postgres, dùng được index GIN
        stmt = stmt.where(Task.tags.contains(filters.tags))
    if filters.scheduled_on is not None:
        stmt = stmt.where(Task.scheduled_for == filters.scheduled_on)
    if filters.due_before is not None:
        stmt = stmt.where(Task.due_at.is_not(None), Task.due_at < filters.due_before)
    if filters.query:
        pattern = f"%{filters.query.strip()}%"
        stmt = stmt.where(
            or_(Task.title.ilike(pattern), Task.description.ilike(pattern))
        )
    return stmt


def _apply_sort(stmt: Select[Any], filters: TaskFilters) -> Select[Any]:
    column: Any = (
        _priority_rank() if filters.sort_by == "priority" else getattr(Task, filters.sort_by)
    )

    # nulls_last để task không có due_at/scheduled_for không chen lên đầu
    ordering = column.desc().nulls_last() if filters.sort_desc else column.asc().nulls_last()
    # Task.id là khoá phụ DUY NHẤT: nhiều task cùng created_at (nhập hàng loạt) mà
    # thiếu nó thì thứ tự giữa các trang không ổn định, task bị lặp hoặc sót.
    return stmt.order_by(ordering, Task.created_at.desc(), Task.id.desc())


async def _ensure_project_exists(session: AsyncSession, project_id: uuid.UUID | None) -> None:
    if project_id is None:
        return
    exists = await session.scalar(select(Project.id).where(Project.id == project_id))
    if exists is None:
        raise ValidationError(f"project_id {project_id} không tồn tại")


def _record_event(
    session: AsyncSession,
    task: Task,
    event_type: TaskEventType,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        TaskEvent(
            task_id=task.id,
            event_type=event_type,
            actor=actor,
            payload=jsonable(payload) if payload is not None else None,
        )
    )


# ═══════════════════════════════════════════════════════════════════════
#  Đọc
# ═══════════════════════════════════════════════════════════════════════


async def list_tasks(
    session: AsyncSession, filters: TaskFilters
) -> tuple[list[Task], int]:
    base = _apply_filters(select(Task), filters)

    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )

    stmt = _apply_sort(base, filters).limit(filters.limit).offset(filters.offset)
    result = await session.execute(stmt)
    return list(result.scalars().unique().all()), int(total or 0)


async def get_task(
    session: AsyncSession, task_id: uuid.UUID, *, include_deleted: bool = False
) -> Task:
    task = await session.get(Task, task_id)
    if task is None or (task.deleted_at is not None and not include_deleted):
        raise NotFoundError(f"Không tìm thấy task {task_id}")
    return task


async def get_task_with_events(
    session: AsyncSession, task_id: uuid.UUID, *, include_deleted: bool = False
) -> Task:
    stmt = (
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.events), selectinload(Task.project))
    )
    if not include_deleted:
        stmt = stmt.where(_alive())

    task = (await session.execute(stmt)).scalars().unique().one_or_none()
    if task is None:
        raise NotFoundError(f"Không tìm thấy task {task_id}")
    return task


# ═══════════════════════════════════════════════════════════════════════
#  Ghi
# ═══════════════════════════════════════════════════════════════════════


async def create_task(
    session: AsyncSession, payload: TaskCreate, *, actor: str = "user"
) -> Task:
    await _ensure_project_exists(session, payload.project_id)

    data = payload.model_dump()
    # Phải tự quyết scope ở đây: model cố ý không có default Python (xem models/task.py).
    data["scope"] = payload.scope or default_scope_for(payload.source)
    task = Task(**data)
    if task.status is TaskStatus.DONE:
        task.completed_at = now_utc()

    session.add(task)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"Task từ nguồn {payload.source} với external_id "
            f"'{payload.external_id}' đã tồn tại"
        ) from exc

    _record_event(
        session,
        task,
        TaskEventType.CREATED,
        actor,
        {
            "title": task.title,
            "status": task.status.value,
            "source": task.source.value,
            "scope": task.scope.value,
        },
    )
    await session.flush()
    return await get_task_with_events(session, task.id)


async def update_task(
    session: AsyncSession, task_id: uuid.UUID, payload: TaskUpdate, *, actor: str = "user"
) -> Task:
    task = await get_task(session, task_id)
    changes = payload.model_dump(exclude_unset=True)

    if "project_id" in changes:
        await _ensure_project_exists(session, changes["project_id"])

    old_status = task.status
    diff: dict[str, dict[str, Any]] = {}

    for field_name, new_value in changes.items():
        old_value = getattr(task, field_name)
        if old_value == new_value:
            continue
        setattr(task, field_name, new_value)
        if field_name == "due_at":
            # Hạn sửa tay luôn là thời điểm cụ thể; hạn cả ngày chỉ do đồng bộ Jira tạo ra.
            task.due_all_day = False
        if field_name in _TRACKED_FIELDS:
            diff[field_name] = {"from": old_value, "to": new_value}

    new_status = task.status

    # Side effect của chuyển trạng thái
    if new_status is not old_status:
        if new_status is TaskStatus.DONE:
            task.completed_at = now_utc()
            _record_event(
                session, task, TaskEventType.COMPLETED, actor,
                {"from": old_status.value},
            )
        elif old_status in CLOSED_STATUSES and new_status not in CLOSED_STATUSES:
            task.completed_at = None
            _record_event(
                session, task, TaskEventType.REOPENED, actor,
                {"from": old_status.value, "to": new_status.value},
            )
        else:
            _record_event(
                session, task, TaskEventType.STATUS_CHANGED, actor,
                {"from": old_status.value, "to": new_status.value},
            )

    if diff:
        _record_event(session, task, TaskEventType.UPDATED, actor, {"changes": diff})

    await session.flush()
    return await get_task_with_events(session, task.id)


async def delete_task(
    session: AsyncSession, task_id: uuid.UUID, *, actor: str = "user"
) -> Task:
    """Xoá mềm: đưa vào thùng rác, giữ lại theo settings.trash_retention_days.

    Nếu retention đặt 0 thì xoá thẳng, không qua thùng rác.
    """
    task = await get_task(session, task_id)

    if settings.trash_retention_days == 0:
        await session.delete(task)
        await session.flush()
        return task

    task.deleted_at = now_utc()
    _record_event(
        session,
        task,
        TaskEventType.DELETED,
        actor,
        {"retention_days": settings.trash_retention_days},
    )
    await session.flush()
    return task


async def restore_task(
    session: AsyncSession, task_id: uuid.UUID, *, actor: str = "user"
) -> Task:
    """Lấy task ra khỏi thùng rác."""
    task = await get_task(session, task_id, include_deleted=True)

    if task.deleted_at is None:
        raise ValidationError(f"Task {task_id} không nằm trong thùng rác")

    # Trước khi phục hồi phải chắc chắn không đụng partial unique index.
    # Tình huống thật: xoá một issue Jira, sync tạo lại, rồi bấm phục hồi.
    if task.external_id is not None:
        clash = await session.scalar(
            select(Task.id).where(
                Task.source == task.source,
                Task.external_id == task.external_id,
                Task.deleted_at.is_(None),
                Task.id != task.id,
            )
        )
        if clash is not None:
            raise ConflictError(
                f"Đã có task khác từ nguồn {task.source.value} với external_id "
                f"'{task.external_id}'. Xoá task đó trước khi phục hồi."
            )

    deleted_at = task.deleted_at
    task.deleted_at = None
    _record_event(
        session, task, TaskEventType.RESTORED, actor, {"deleted_at": deleted_at}
    )
    await session.flush()
    return await get_task_with_events(session, task.id)


async def purge_task(session: AsyncSession, task_id: uuid.UUID) -> None:
    """Xoá vĩnh viễn. Chỉ áp dụng cho task đang nằm trong thùng rác."""
    task = await get_task(session, task_id, include_deleted=True)

    if task.deleted_at is None:
        raise ValidationError(
            f"Task {task_id} chưa ở trong thùng rác. Xoá mềm trước, "
            f"hoặc dùng DELETE với permanent=true."
        )

    await session.delete(task)
    await session.flush()


async def purge_task_now(session: AsyncSession, task_id: uuid.UUID) -> None:
    """Xoá vĩnh viễn ngay, bỏ qua thùng rác."""
    task = await get_task(session, task_id, include_deleted=True)
    await session.delete(task)
    await session.flush()


async def log_time(
    session: AsyncSession,
    task_id: uuid.UUID,
    minutes: int,
    note: str | None = None,
    *,
    actor: str = "user",
) -> Task:
    task = await get_task(session, task_id)
    task.spent_minutes += minutes
    _record_event(
        session,
        task,
        TaskEventType.TIME_LOGGED,
        actor,
        {"minutes": minutes, "note": note, "total": task.spent_minutes},
    )
    await session.flush()
    return await get_task_with_events(session, task.id)


# ═══════════════════════════════════════════════════════════════════════
#  View theo dõi hàng ngày
# ═══════════════════════════════════════════════════════════════════════


async def _fetch(session: AsyncSession, stmt: Select[Any]) -> list[Task]:
    result = await session.execute(stmt.options(selectinload(Task.project)))
    return list(result.scalars().unique().all())


def _alive_in_view(view: TaskView, owners: Sequence[str]) -> ColumnElement[bool]:
    """`_alive()` AND điều kiện view, để agenda/stats áp view ở một chỗ."""
    clause = _view_clause(view, owners)
    return _alive() if clause is None else and_(_alive(), clause)


def _overdue_clause(now: datetime, cutoff: datetime) -> ColumnElement[bool]:
    """Quá hạn: task có giờ so `now`; task cả ngày so ngày hạn < hôm nay (`cutoff`).

    NGUỒN DUY NHẤT của luật quá hạn phía SQL (agenda, stats); bản Python là
    `TaskRead.is_overdue`. Xem services/clock.py::today_all_day_cutoff.
    """
    return and_(
        Task.due_at.is_not(None),
        or_(
            and_(Task.due_all_day.is_(False), Task.due_at < now),
            and_(Task.due_all_day.is_(True), Task.due_at < cutoff),
        ),
    )


def _due_soon_clause(now: datetime, cutoff: datetime) -> ColumnElement[bool]:
    """Sắp đến hạn trong 7 ngày; hạn cả ngày của hôm nay tính là sắp đến hạn, chưa quá hạn."""
    week = timedelta(days=7)
    return and_(
        Task.due_at.is_not(None),
        or_(
            and_(Task.due_all_day.is_(False), Task.due_at >= now, Task.due_at < now + week),
            and_(Task.due_all_day.is_(True), Task.due_at >= cutoff, Task.due_at < cutoff + week),
        ),
    )


async def get_agenda(
    session: AsyncSession,
    reference: date | None = None,
    *,
    view: TaskView = TaskView.ALL,
    owners: Sequence[str] = (),
) -> dict[str, Any]:
    """Việc của hôm nay. View áp cho cả 5 nhóm TRƯỚC bước loại trùng in_progress."""
    today = reference or local_today()
    now = now_utc()
    # Quá hạn luôn tính theo hôm nay THẬT (như `now`), không theo `reference`.
    cutoff = today_all_day_cutoff(local_today())
    day_start, day_end = local_day_bounds_utc(today)
    open_only = Task.status.notin_(CLOSED_STATUSES)
    alive = _alive_in_view(view, owners)

    overdue = await _fetch(
        session,
        select(Task)
        .where(alive, open_only, _overdue_clause(now, cutoff))
        .order_by(Task.due_at.asc()),
    )

    scheduled_today = await _fetch(
        session,
        select(Task)
        .where(alive, open_only, Task.scheduled_for == today)
        .order_by(_priority_rank().desc(), Task.due_at.asc().nulls_last()),
    )

    in_progress = await _fetch(
        session,
        select(Task)
        .where(alive, Task.status == TaskStatus.IN_PROGRESS)
        .order_by(Task.updated_at.desc()),
    )

    due_soon = await _fetch(
        session,
        select(Task)
        .where(
            alive,
            open_only,
            Task.scheduled_for.is_(None),
            _due_soon_clause(now, cutoff),
        )
        .order_by(Task.due_at.asc()),
    )

    completed_today = await _fetch(
        session,
        select(Task)
        .where(
            alive,
            Task.status == TaskStatus.DONE,
            Task.completed_at.is_not(None),
            Task.completed_at >= day_start,
            Task.completed_at < day_end,
        )
        .order_by(Task.completed_at.desc()),
    )

    # in_progress đã xuất hiện ở nhóm riêng, bỏ khỏi scheduled_today cho gọn
    in_progress_ids = {task.id for task in in_progress}
    scheduled_today = [t for t in scheduled_today if t.id not in in_progress_ids]
    overdue = [t for t in overdue if t.id not in in_progress_ids]

    return {
        "reference_date": today,
        "overdue": overdue,
        "scheduled_today": scheduled_today,
        "in_progress": in_progress,
        "due_soon": due_soon,
        "completed_today": completed_today,
    }


async def get_stats(
    session: AsyncSession,
    reference: date | None = None,
    *,
    view: TaskView = TaskView.ALL,
    owners: Sequence[str] = (),
) -> dict[str, Any]:
    """Thống kê nhanh. `view` áp cho mọi số trừ `trash_total` và `minutes_logged_today`.

    Hai số đó cố ý không lọc theo view: thùng rác thuộc trang riêng, còn chế độ file
    chỉ có một bộ đếm phút chung; lọc ở đây sẽ làm hai chế độ cho kết quả khác nhau.
    """
    today = reference or local_today()
    now = now_utc()
    # Quá hạn luôn tính theo hôm nay THẬT (như `now`), không theo `reference`.
    cutoff = today_all_day_cutoff(local_today())
    day_start, day_end = local_day_bounds_utc(today)

    alive = _alive_in_view(view, owners)

    status_rows = await session.execute(
        select(Task.status, func.count()).where(alive).group_by(Task.status)
    )
    by_status = {row[0].value: row[1] for row in status_rows.all()}

    priority_rows = await session.execute(
        select(Task.priority, func.count())
        .where(alive, Task.status.notin_(CLOSED_STATUSES))
        .group_by(Task.priority)
    )
    by_priority = {row[0].value: row[1] for row in priority_rows.all()}

    window_start, _ = local_day_bounds_utc(today - timedelta(days=6))
    completed_rows = await session.execute(
        select(
            # Phải quy về timezone hiển thị trước khi lấy date, nếu không
            # key sẽ là ngày UTC và lệch với reference_date (ngày địa phương).
            func.date(func.timezone(clock.display_tz().key, Task.completed_at)).label("day"),
            func.count(),
        )
        .where(
            alive,
            Task.status == TaskStatus.DONE,
            Task.completed_at.is_not(None),
            Task.completed_at >= window_start,
            Task.completed_at < day_end,
        )
        .group_by("day")
        .order_by("day")
    )
    completed_last_7_days = {str(row[0]): row[1] for row in completed_rows.all()}

    open_total = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(alive, Task.status.notin_(CLOSED_STATUSES))
    )
    overdue_total = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            alive,
            Task.status.notin_(CLOSED_STATUSES),
            _overdue_clause(now, cutoff),
        )
    )
    trash_total = await session.scalar(
        select(func.count()).select_from(Task).where(Task.deleted_at.is_not(None))
    )

    minutes_today = await session.scalar(
        select(func.coalesce(func.sum(cast(TaskEvent.payload["minutes"].astext, Integer)), 0))
        .where(
            TaskEvent.event_type == TaskEventType.TIME_LOGGED,
            TaskEvent.created_at >= day_start,
            TaskEvent.created_at < day_end,
        )
    )

    return {
        "reference_date": today,
        "by_status": by_status,
        "by_priority": by_priority,
        "completed_last_7_days": completed_last_7_days,
        "open_total": int(open_total or 0),
        "overdue_total": int(overdue_total or 0),
        "minutes_logged_today": int(minutes_today or 0),
        "trash_total": int(trash_total or 0),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Thùng rác
# ═══════════════════════════════════════════════════════════════════════


def _purge_cutoff() -> datetime:
    """Task xoá trước mốc này là đã hết hạn giữ."""
    return now_utc() - timedelta(days=settings.trash_retention_days)


async def list_trash(
    session: AsyncSession, *, limit: int = 100, offset: int = 0
) -> tuple[list[Task], int]:
    """Task trong thùng rác, mới xoá lên trước."""
    base = select(Task).where(Task.deleted_at.is_not(None))

    total = await session.scalar(select(func.count()).select_from(base.subquery()))

    stmt = (
        base.options(selectinload(Task.project))
        .order_by(Task.deleted_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().unique().all()), int(total or 0)


async def purge_expired(session: AsyncSession) -> int:
    """Xoá vĩnh viễn task đã quá thời hạn giữ. Trả về số bản ghi đã xoá.

    Hiện chưa có scheduler nên hàm này được gọi khi mở thùng rác và qua
    endpoint POST /tasks/trash/purge. Khi có scheduler ở Phase 2 thì cho nó
    gọi định kỳ mỗi ngày.
    """
    if settings.trash_retention_days == 0:
        return 0

    cutoff = _purge_cutoff()
    result = await session.execute(
        delete(Task).where(
            Task.deleted_at.is_not(None), Task.deleted_at < cutoff
        )
    )
    await session.flush()
    return int(result.rowcount or 0)


async def empty_trash(session: AsyncSession) -> int:
    """Xoá vĩnh viễn toàn bộ thùng rác, không chờ hết hạn."""
    result = await session.execute(delete(Task).where(Task.deleted_at.is_not(None)))
    await session.flush()
    return int(result.rowcount or 0)
