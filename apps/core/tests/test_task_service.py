"""Logic nghiệp vụ của task trên Postgres thật."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskEventType, TaskSource, TaskStatus
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import task_service
from app.services.errors import ConflictError, NotFoundError, ValidationError

pytestmark = pytest.mark.db


async def test_create_records_created_event(session: AsyncSession) -> None:
    task = await task_service.create_task(session, TaskCreate(title="việc A", assignee="An"))
    assert task.status is TaskStatus.TODO
    assert task.assignee == "An"
    assert [e.event_type for e in task.events] == [TaskEventType.CREATED]


async def test_done_sets_and_reopen_clears_completed_at(session: AsyncSession) -> None:
    task = await task_service.create_task(session, TaskCreate(title="việc B"))
    task_id = task.id

    done = await task_service.update_task(session, task_id, TaskUpdate(status=TaskStatus.DONE))
    assert done.completed_at is not None

    reopened = await task_service.update_task(
        session, task_id, TaskUpdate(status=TaskStatus.IN_PROGRESS)
    )
    assert reopened.completed_at is None
    # Cùng một session nên collection `events` đã nạp ở create_task còn cũ;
    # request thật mỗi lần một session mới. expire_all để đọc lại từ DB.
    session.expire_all()
    reloaded = await task_service.get_task_with_events(session, task_id)
    kinds = {e.event_type for e in reloaded.events}
    assert {TaskEventType.COMPLETED, TaskEventType.REOPENED} <= kinds


async def test_external_id_unique_per_source(session: AsyncSession) -> None:
    payload = TaskCreate(title="jira", source=TaskSource.JIRA, external_id="ABC-1")
    await task_service.create_task(session, payload)
    with pytest.raises(ConflictError):
        await task_service.create_task(session, payload)


async def test_soft_delete_hides_task_and_restore_brings_it_back(session: AsyncSession) -> None:
    task = await task_service.create_task(session, TaskCreate(title="xoá mềm"))
    await task_service.delete_task(session, task.id)

    with pytest.raises(NotFoundError):
        await task_service.get_task(session, task.id)
    assert (await task_service.get_task(session, task.id, include_deleted=True)).deleted_at

    restored = await task_service.restore_task(session, task.id)
    assert restored.deleted_at is None


async def test_restore_task_not_in_trash_is_rejected(session: AsyncSession) -> None:
    task = await task_service.create_task(session, TaskCreate(title="còn sống"))
    with pytest.raises(ValidationError):
        await task_service.restore_task(session, task.id)


async def test_restore_conflicts_with_recreated_external_id(session: AsyncSession) -> None:
    first = await task_service.create_task(
        session, TaskCreate(title="cũ", source=TaskSource.JIRA, external_id="X-9")
    )
    await task_service.delete_task(session, first.id)
    await task_service.create_task(
        session, TaskCreate(title="mới", source=TaskSource.JIRA, external_id="X-9")
    )
    with pytest.raises(ConflictError):
        await task_service.restore_task(session, first.id)


async def test_update_unknown_task_is_not_found(session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await task_service.update_task(session, uuid.uuid4(), TaskUpdate(title="x"))
