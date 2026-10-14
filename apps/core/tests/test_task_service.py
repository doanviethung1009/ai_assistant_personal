"""Logic nghiệp vụ của task trên Postgres thật."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskEventType, TaskSource, TaskStatus
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import task_service
from app.services.errors import ConflictError, NotFoundError, ValidationError
from tests.conftest import Persona

pytestmark = pytest.mark.db


async def test_create_records_created_event(session: AsyncSession, default_user: Persona) -> None:
    task = await task_service.create_task(
        session, default_user.user, TaskCreate(title="việc A", assignee="An")
    )
    assert task.status is TaskStatus.TODO
    assert task.assignee == "An"
    assert [e.event_type for e in task.events] == [TaskEventType.CREATED]


async def test_done_sets_and_reopen_clears_completed_at(
    session: AsyncSession, default_user: Persona
) -> None:
    task = await task_service.create_task(session, default_user.user, TaskCreate(title="việc B"))
    task_id = task.id

    done = await task_service.update_task(
        session, default_user.user, task_id, TaskUpdate(status=TaskStatus.DONE)
    )
    assert done.completed_at is not None

    reopened = await task_service.update_task(
        session, default_user.user, task_id, TaskUpdate(status=TaskStatus.IN_PROGRESS)
    )
    assert reopened.completed_at is None
    # Cùng một session nên collection `events` đã nạp ở create_task còn cũ;
    # request thật mỗi lần một session mới. expire_all để đọc lại từ DB.
    session.expire_all()
    reloaded = await task_service.get_task_with_events(session, default_user.user, task_id)
    kinds = {e.event_type for e in reloaded.events}
    assert {TaskEventType.COMPLETED, TaskEventType.REOPENED} <= kinds


async def test_external_id_unique_per_source(session: AsyncSession, default_user: Persona) -> None:
    payload = TaskCreate(title="jira", source=TaskSource.JIRA, external_id="ABC-1")
    await task_service.create_task(session, default_user.user, payload)
    with pytest.raises(ConflictError):
        await task_service.create_task(session, default_user.user, payload)


async def test_soft_delete_hides_task_and_restore_brings_it_back(
    session: AsyncSession, default_user: Persona
) -> None:
    task = await task_service.create_task(session, default_user.user, TaskCreate(title="xoá mềm"))
    await task_service.delete_task(session, default_user.user, task.id)

    with pytest.raises(NotFoundError):
        await task_service.get_task(session, default_user.user, task.id)
    assert (
        await task_service.get_task(session, default_user.user, task.id, include_deleted=True)
    ).deleted_at

    restored = await task_service.restore_task(session, default_user.user, task.id)
    assert restored.deleted_at is None


async def test_restore_task_not_in_trash_is_rejected(
    session: AsyncSession, default_user: Persona
) -> None:
    task = await task_service.create_task(session, default_user.user, TaskCreate(title="còn sống"))
    with pytest.raises(ValidationError):
        await task_service.restore_task(session, default_user.user, task.id)


async def test_restore_conflicts_with_recreated_external_id(
    session: AsyncSession, default_user: Persona
) -> None:
    first = await task_service.create_task(
        session,
        default_user.user,
        TaskCreate(title="cũ", source=TaskSource.JIRA, external_id="X-9"),
    )
    await task_service.delete_task(session, default_user.user, first.id)
    await task_service.create_task(
        session,
        default_user.user,
        TaskCreate(title="mới", source=TaskSource.JIRA, external_id="X-9"),
    )
    with pytest.raises(ConflictError):
        await task_service.restore_task(session, default_user.user, first.id)


async def test_update_unknown_task_is_not_found(
    session: AsyncSession, default_user: Persona
) -> None:
    with pytest.raises(NotFoundError):
        await task_service.update_task(
            session, default_user.user, uuid.uuid4(), TaskUpdate(title="x")
        )


async def test_list_filters_by_assignee(session: AsyncSession, default_user: Persona) -> None:
    """Tham số assignee từng bị route bỏ qua, trả về mọi task."""
    await task_service.create_task(
        session, default_user.user, TaskCreate(title="của An", assignee="An")
    )
    await task_service.create_task(
        session, default_user.user, TaskCreate(title="của Bình", assignee="Bình")
    )

    items, total = await task_service.list_tasks(
        session, default_user.user, task_service.TaskFilters(assignee="An")
    )
    assert total == 1
    assert [t.title for t in items] == ["của An"]
