from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import SessionDep
from app.core.config import settings
from app.models.enums import TaskPriority, TaskSource, TaskStatus
from app.schemas.common import Page
from app.schemas.task import (
    AgendaResponse,
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
from app.services import settings_service, task_service
from app.services.task_service import SortField, TaskFilters

router = APIRouter(prefix="/tasks", tags=["tasks"])

ViewQuery = Annotated[
    TaskView,
    Query(
        description=(
            "Lọc theo scope. `mine` = cá nhân + công việc giao cho `owner` (hoặc không "
            "giao ai và không đến từ tích hợp). Mặc định `all` để client cũ không đổi."
        )
    ),
]
OwnerQuery = Annotated[
    list[str] | None,
    Query(description="Tên assignee của User, lặp lại để chọn nhiều. Chỉ với view=mine."),
]


# ═══════════════════════════════════════════════════════════════════════
#  Đường dẫn tĩnh phải khai báo TRƯỚC /{task_id}, nếu không FastAPI sẽ
#  khớp "agenda" thành task_id và trả 422.
# ═══════════════════════════════════════════════════════════════════════


@router.get(
    "/agenda",
    response_model=AgendaResponse,
    summary="Việc của hôm nay",
    description=(
        "Gom việc quá hạn, đã xếp lịch hôm nay, đang làm, sắp đến hạn, "
        "và đã xong trong ngày."
    ),
)
async def get_agenda(
    session: SessionDep,
    reference_date: Annotated[
        date | None, Query(description="Mặc định là hôm nay theo timezone hiển thị")
    ] = None,
    view: ViewQuery = TaskView.ALL,
    owner: OwnerQuery = None,
) -> AgendaResponse:
    owners = task_service.validate_view_params(view, owner)
    data = await task_service.get_agenda(session, reference_date, view=view, owners=owners)
    return AgendaResponse.model_validate(data)


@router.get("/stats", response_model=TaskStatsResponse, summary="Thống kê nhanh")
async def get_stats(
    session: SessionDep,
    reference_date: Annotated[date | None, Query()] = None,
    view: ViewQuery = TaskView.ALL,
    owner: OwnerQuery = None,
) -> TaskStatsResponse:
    owners = task_service.validate_view_params(view, owner)
    data = await task_service.get_stats(session, reference_date, view=view, owners=owners)
    return TaskStatsResponse.model_validate(data)


@router.get(
    "/assignees",
    response_model=list[str],
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
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TrashResponse:
    purged = await task_service.purge_expired(session)
    items, total = await task_service.list_trash(session, limit=limit, offset=offset)
    return TrashResponse(
        items=[TaskRead.model_validate(item) for item in items],
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
)
async def purge_expired(session: SessionDep) -> PurgeResponse:
    purged = await task_service.purge_expired(session)
    return PurgeResponse(
        purged=purged, retention_days=settings.trash_retention_days
    )


@router.post(
    "/trash/empty",
    response_model=PurgeResponse,
    summary="Xoá vĩnh viễn toàn bộ thùng rác",
    description="Không chờ hết hạn. Không phục hồi lại được.",
)
async def empty_trash(session: SessionDep) -> PurgeResponse:
    purged = await task_service.empty_trash(session)
    return PurgeResponse(
        purged=purged, retention_days=settings.trash_retention_days
    )


@router.get("", response_model=Page[TaskRead], summary="Danh sách task")
async def list_tasks(
    session: SessionDep,
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
    assignee: Annotated[str | None, Query()] = None,
    include_closed: Annotated[bool, Query(description="Gồm cả done và cancelled")] = False,
    view: ViewQuery = TaskView.ALL,
    owner: OwnerQuery = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort_by: Annotated[SortField, Query()] = "created_at",
    sort_desc: Annotated[bool, Query()] = True,
) -> Page[TaskRead]:
    owners = task_service.validate_view_params(view, owner)
    filters = TaskFilters(
        view=view,
        owners=owners,
        status=status_in,
        priority=priority_in,
        project_id=project_id,
        source=source,
        assignee=assignee,
        tags=tags or [],
        query=q,
        scheduled_on=scheduled_on,
        due_before=due_before,
        include_closed=include_closed,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )
    items, total = await task_service.list_tasks(session, filters)
    return Page[TaskRead](
        items=[TaskRead.model_validate(item) for item in items],
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
async def create_task(session: SessionDep, payload: TaskCreate) -> TaskDetail:
    task = await task_service.create_task(session, payload)
    return TaskDetail.model_validate(task)


@router.get("/{task_id}", response_model=TaskDetail, summary="Chi tiết task kèm nhật ký")
async def get_task(session: SessionDep, task_id: uuid.UUID) -> TaskDetail:
    task = await task_service.get_task_with_events(session, task_id)
    return TaskDetail.model_validate(task)


@router.patch("/{task_id}", response_model=TaskDetail, summary="Cập nhật bán phần")
async def update_task(
    session: SessionDep, task_id: uuid.UUID, payload: TaskUpdate
) -> TaskDetail:
    task = await task_service.update_task(session, task_id, payload)
    return TaskDetail.model_validate(task)


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
    task_id: uuid.UUID,
    permanent: Annotated[
        bool, Query(description="Xoá vĩnh viễn ngay, bỏ qua thùng rác")
    ] = False,
) -> None:
    if permanent:
        await task_service.purge_task_now(session, task_id)
    else:
        await task_service.delete_task(session, task_id)


@router.post(
    "/{task_id}/restore",
    response_model=TaskDetail,
    summary="Phục hồi task từ thùng rác",
)
async def restore_task(session: SessionDep, task_id: uuid.UUID) -> TaskDetail:
    task = await task_service.restore_task(session, task_id)
    return TaskDetail.model_validate(task)


@router.post("/{task_id}/complete", response_model=TaskDetail, summary="Đánh dấu xong")
async def complete_task(session: SessionDep, task_id: uuid.UUID) -> TaskDetail:
    task = await task_service.update_task(
        session, task_id, TaskUpdate(status=TaskStatus.DONE)
    )
    return TaskDetail.model_validate(task)


@router.post(
    "/{task_id}/time", response_model=TaskDetail, summary="Ghi thời gian đã làm"
)
async def log_time(
    session: SessionDep, task_id: uuid.UUID, payload: TimeLogRequest
) -> TaskDetail:
    task = await task_service.log_time(session, task_id, payload.minutes, payload.note)
    return TaskDetail.model_validate(task)
