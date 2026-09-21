from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.errors import ConflictError, NotFoundError


async def list_projects(
    session: AsyncSession, *, include_archived: bool = False
) -> list[Project]:
    stmt = select(Project).order_by(Project.key)
    if not include_archived:
        stmt = stmt.where(Project.is_archived.is_(False))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Không tìm thấy project {project_id}")
    return project


async def create_project(session: AsyncSession, payload: ProjectCreate) -> Project:
    project = Project(**payload.model_dump())
    session.add(project)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"Project key '{payload.key}' đã tồn tại") from exc
    await session.refresh(project)
    return project


async def update_project(
    session: AsyncSession, project_id: uuid.UUID, payload: ProjectUpdate
) -> Project:
    project = await get_project(session, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.flush()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project_id: uuid.UUID) -> None:
    """Xoá project. Task thuộc project sẽ được set project_id = NULL, không bị xoá."""
    project = await get_project(session, project_id)
    await session.delete(project)
    await session.flush()


async def count_open_tasks_by_project(session: AsyncSession) -> dict[uuid.UUID, int]:
    from app.models.enums import TaskStatus
    from app.models.task import Task

    stmt = (
        select(Task.project_id, func.count())
        .where(
            Task.project_id.is_not(None),
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
        )
        .group_by(Task.project_id)
    )
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}
