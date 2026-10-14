from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.capped import CappedBodyRoute
from app.api.deps import CurrentUserDep, SessionDep, require_permission
from app.core.auth import CurrentUser
from app.core.config import settings
from app.core.permissions import Permission
from app.models.enums import TaskPriority, TaskSource, TaskStatus
from app.models.task import Task
from app.schemas.common import Page
from app.schemas.task import (
    AgendaResponse,
    ParticipationResponse,
    PurgeResponse,
    TaskCreate,
    TaskDetail,
    TaskRead,
    TaskStatsResponse,
    TaskUpdate,
    TaskView,
    TimeLogRequest,
    TrashResponse,
)
from app.schemas.task_upsert import TaskUpsertBatch, TaskUpsertResult
from app.services import access, settings_service, task_service, task_sync_service
from app.services.task_service import SortField, TaskFilters

router = APIRouter(prefix="/tasks", tags=["tasks"])

ViewQuery = Annotated[
    TaskView,
    Query(
        description=(
            "Lọc theo scope, luôn nằm TRONG phạm vi người gọi nhìn thấy (mọi task `work` và "
            "task `personal` của chính họ). `mine` = cá nhân của tôi + công việc giao cho alias "
            "của tôi (hoặc tôi tự tạo, không giao ai, không đến từ tích hợp). Server tự suy "
            "'của tôi' từ người đăng nhập, client không chọn được. Mặc định `all`."
        )
    ),
]


def _read(task: Task, user: CurrentUser) -> TaskRead:
    """TaskRead kèm quyền ghi của người gọi (web ẩn nút theo đây, core vẫn kiểm lại khi ghi)."""
    perms = access.task_permissions(user, task)
    read = TaskRead.model_validate(task)
    read.can_edit, read.can_delete = perms.can_edit, perms.can_delete
    return read


def _detail(task: Task, user: CurrentUser) -> TaskDetail:
    perms = access.task_permissions(user, task)
    detail = TaskDetail.model_validate(task)
    detail.can_edit, detail.can_delete = perms.can_edit, perms.can_delete
    return detail


# ═══════════════════════════════════════════════════════════════════════
#  Đường dẫn tĩnh phải khai báo TRƯỚC /{task_id}, nếu không FastAPI sẽ
#  khớp "agenda" thành task_id và trả 422.
# ═══════════════════════════════════════════════════════════════════════


@router.get(
    "/agenda",
    response_model=AgendaResponse,
    summary="Việc của hôm nay",
    description=(
        "Gom việc quá hạn, đã xếp lịch hôm nay, đang làm, sắp đến hạn, và đã xong trong ngày."
    ),
)
async def get_agenda(
    session: SessionDep,
    user: CurrentUserDep,
    reference_date: Annotated[
        date | None, Query(description="Mặc định là hôm nay theo timezone hiển thị")
    ] = None,
    view: ViewQuery = TaskView.ALL,
) -> AgendaResponse:
    data = await task_service.get_agenda(session, user, reference_date, view=view)
    groups = ("overdue", "scheduled_today", "in_progress", "due_soon", "completed_today")
    for group in groups:
        data[group] = [_read(task, user) for task in data[group]]
    return AgendaResponse.model_validate(data)


@router.get("/stats", response_model=TaskStatsResponse, summary="Thống kê nhanh")
async def get_stats(
    session: SessionDep,
    user: CurrentUserDep,
    reference_date: Annotated[date | None, Query()] = None,
    view: ViewQuery = TaskView.ALL,
) -> TaskStatsResponse:
    data = await task_service.get_stats(session, user, reference_date, view=view)
    return TaskStatsResponse.model_validate(data)


@router.get(
    "/participation",
    response_model=ParticipationResponse,
    dependencies=[Depends(require_permission(Permission.TEAM_READ))],
    summary="Tỉ lệ tham dự dự án của nhóm",
    description=(
        "Với mỗi project: mỗi người được chọn gánh bao nhiêu % task của project (task công "
        "việc, chưa huỷ). `person` lặp lại để chọn nhiều người; bỏ trống = tất cả. Mẫu số là "
        "tổng task của project nên % không đổi theo danh sách chọn. `date_from`/`date_to` lọc "
        "theo ngày hoạt động (xong: ngày hoàn thành, còn lại: ngày cập nhật), áp cho cả tử "
        "lẫn mẫu số."
    ),
)
async def get_participation(
    session: SessionDep,
    user: CurrentUserDep,
    person: Annotated[
        list[str] | None,
        Query(description="Tên assignee cần phân tích, lặp lại để chọn nhiều (tối đa 50)"),
    ] = None,
    date_from: Annotated[
        date | None, Query(description="Từ ngày địa phương này (gồm cả ngày). Bỏ trống = từ đầu")
    ] = None,
    date_to: Annotated[
        date | None, Query(description="Đến ngày địa phương này (gồm cả ngày). Bỏ trống = đến nay")
    ] = None,
) -> ParticipationResponse:
    people = task_service.validate_people(person)
    task_service.validate_period(date_from, date_to)
    data = await task_service.get_participation(session, user, people, date_from, date_to)
    return ParticipationResponse.model_validate(data)


async def upsert_batch(
    session: SessionDep, user: CurrentUserDep, payload: TaskUpsertBatch
) -> TaskUpsertResult:
    return await task_sync_service.upsert_batch(
        session, payload.source, payload.items, actor_user_id=user.id
    )


# add_api_route (không phải decorator) vì cần route_class_override: trần body 20 MB đọc
# theo luồng, trả 413. Khai báo trước `/{task_id}` như mọi route tĩnh khác.
router.add_api_route(
    "/upsert-batch",
    upsert_batch,
    methods=["POST"],
    response_model=TaskUpsertResult,
    route_class_override=CappedBodyRoute,
    dependencies=[Depends(require_permission(Permission.INTEGRATION_SYNC))],
    summary="Upsert hàng loạt task từ nguồn tích hợp (idempotent)",
    description=(
        "Khớp theo (source, external_id) trên task còn sống; chỉ ghi scope=work, task "
        "personal trùng khoá bị bỏ qua (skipped_personal). Tối đa 1000 item, body tối đa "
        "20 MB (413). Đòi quyền `integration:sync` (403). `tags` được gộp, `description` chỉ "
        "điền khi task đang rỗng. "
        "`source` không được là `manual`."
    ),
)


@router.get(
    "/assignees",
    response_model=list[str],
    dependencies=[Depends(require_permission(Permission.TEAM_READ))],
    summary="Danh sách assignee của task công việc",
    description=(
        "DISTINCT assignee của task còn sống VÀ scope=work (tối đa 500, sắp theo chữ cái). "
        "Dùng cho chọn 'tôi là ai'; task cá nhân và task trong thùng rác không góp tên."
    ),
)
async def list_assignees(session: SessionDep) -> list[str]:
    return await settings_service.list_assignees(session)


@router.get(
    "/trash",
    response_model=TrashResponse,
    summary="Thùng rác",
    description=(
        "Task đã xoá mềm, còn giữ được `retention_days` ngày. Mỗi lần gọi sẽ "
        "dọn luôn những task đã quá hạn, vì hệ thống chưa có scheduler."
    ),
)
async def get_trash(
    session: SessionDep,
    user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TrashResponse:
    purged = await task_service.purge_expired(session)
    items, total = await task_service.list_trash(session, user, limit=limit, offset=offset)
    return TrashResponse(
        items=[_read(item, user) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        retention_days=settings.trash_retention_days,
        purged_now=purged,
    )


@router.post(
    "/trash/purge",
    response_model=PurgeResponse,
    summary="Dọn task quá hạn trong thùng rác",
    description="Dọn toàn hệ thống theo chính sách lưu giữ, không phải quyền của riêng ai.",
)
async def purge_expired(session: SessionDep) -> PurgeResponse:
    purged = await task_service.purge_expired(session)
    return PurgeResponse(purged=purged, retention_days=settings.trash_retention_days)


@router.post(
    "/trash/empty",
    response_model=PurgeResponse,
    summary="Xoá vĩnh viễn thùng rác của tôi",
    description=(
        "Chỉ xoá các task trong thùng rác mà người gọi được phép xoá. Không chờ hết hạn, "
        "không phục hồi lại được."
    ),
)
async def empty_trash(session: SessionDep, user: CurrentUserDep) -> PurgeResponse:
    purged = await task_service.empty_trash(session, user)
    return PurgeResponse(purged=purged, retention_days=settings.trash_retention_days)


@router.get("", response_model=Page[TaskRead], summary="Danh sách task")
async def list_tasks(
    session: SessionDep,
    user: CurrentUserDep,
    status_in: Annotated[
        list[TaskStatus] | None, Query(alias="status", description="Lặp lại để chọn nhiều")
    ] = None,
    priority_in: Annotated[list[TaskPriority] | None, Query(alias="priority")] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    source: Annotated[TaskSource | None, Query()] = None,
    tags: Annotated[list[str] | None, Query(description="Task phải có TẤT CẢ tag này")] = None,
    q: Annotated[
        str | None, Query(max_length=200, description="Tìm trong title và description")
    ] = None,
    scheduled_on: Annotated[date | None, Query()] = None,
    due_before: Annotated[datetime | None, Query()] = None,
    created_after: Annotated[
        datetime | None, Query(description="Chỉ task tạo từ thời điểm này trở đi")
    ] = None,
    assignee: Annotated[str | None, Query()] = None,
    include_closed: Annotated[bool, Query(description="Gồm cả done và cancelled")] = False,
    view: ViewQuery = TaskView.ALL,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort_by: Annotated[SortField, Query()] = "created_at",
    sort_desc: Annotated[bool, Query()] = True,
) -> Page[TaskRead]:
    filters = TaskFilters(
        view=view,
        status=status_in,
        priority=priority_in,
        project_id=project_id,
        source=source,
        assignee=assignee,
        tags=tags or [],
        query=q,
        scheduled_on=scheduled_on,
        due_before=due_before,
        created_after=created_after,
        include_closed=include_closed,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )
    items, total = await task_service.list_tasks(session, user, filters)
    return Page[TaskRead](
        items=[_read(item, user) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=TaskDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo task",
)
async def create_task(session: SessionDep, user: CurrentUserDep, payload: TaskCreate) -> TaskDetail:
    task = await task_service.create_task(session, user, payload)
    return _detail(task, user)


@router.get("/{task_id}", response_model=TaskDetail, summary="Chi tiết task kèm nhật ký")
async def get_task(session: SessionDep, user: CurrentUserDep, task_id: uuid.UUID) -> TaskDetail:
    task = await task_service.get_task_with_events(session, user, task_id)
    return _detail(task, user)


@router.patch("/{task_id}", response_model=TaskDetail, summary="Cập nhật bán phần")
async def update_task(
    session: SessionDep, user: CurrentUserDep, task_id: uuid.UUID, payload: TaskUpdate
) -> TaskDetail:
    task = await task_service.update_task(session, user, task_id, payload)
    return _detail(task, user)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xoá task",
    description=(
        "Mặc định là xoá mềm: task vào thùng rác và còn phục hồi được trong "
        "thời hạn giữ. Truyền `permanent=true` để xoá thẳng, không hoàn tác."
    ),
)
async def delete_task(
    session: SessionDep,
    user: CurrentUserDep,
    task_id: uuid.UUID,
    permanent: Annotated[bool, Query(description="Xoá vĩnh viễn ngay, bỏ qua thùng rác")] = False,
) -> None:
    if permanent:
        await task_service.purge_task_now(session, user, task_id)
    else:
        await task_service.delete_task(session, user, task_id)


@router.post(
    "/{task_id}/restore",
    response_model=TaskDetail,
    summary="Phục hồi task từ thùng rác",
)
async def restore_task(session: SessionDep, user: CurrentUserDep, task_id: uuid.UUID) -> TaskDetail:
    task = await task_service.restore_task(session, user, task_id)
    return _detail(task, user)


@router.post("/{task_id}/complete", response_model=TaskDetail, summary="Đánh dấu xong")
async def complete_task(
    session: SessionDep, user: CurrentUserDep, task_id: uuid.UUID
) -> TaskDetail:
    task = await task_service.update_task(
        session, user, task_id, TaskUpdate(status=TaskStatus.DONE)
    )
    return _detail(task, user)


@router.post("/{task_id}/time", response_model=TaskDetail, summary="Ghi thời gian đã làm")
async def log_time(
    session: SessionDep, user: CurrentUserDep, task_id: uuid.UUID, payload: TimeLogRequest
) -> TaskDetail:
    task = await task_service.log_time(session, user, task_id, payload.minutes, payload.note)
    return _detail(task, user)
