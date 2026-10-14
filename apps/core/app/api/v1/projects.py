from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserDep, SessionDep
from app.core.auth import CurrentUser
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import access, project_service

router = APIRouter(prefix="/projects", tags=["projects"])


def _read(project: Project, user: CurrentUser) -> ProjectRead:
    """ProjectRead kèm quyền sửa của người gọi (web ẩn nút theo đây, core vẫn kiểm lại)."""
    read = ProjectRead.model_validate(project)
    read.can_edit = access.project_can_modify(user, project)
    return read


@router.get("", response_model=list[ProjectRead], summary="Danh sách project")
async def list_projects(
    session: SessionDep,
    user: CurrentUserDep,
    include_archived: Annotated[bool, Query()] = False,
) -> list[ProjectRead]:
    projects = await project_service.list_projects(session, include_archived=include_archived)
    return [_read(project, user) for project in projects]


@router.post(
    "", response_model=ProjectRead, status_code=status.HTTP_201_CREATED, summary="Tạo project"
)
async def create_project(
    session: SessionDep, user: CurrentUserDep, payload: ProjectCreate
) -> ProjectRead:
    project = await project_service.create_project(session, user, payload)
    return _read(project, user)


@router.get("/{project_id}", response_model=ProjectRead, summary="Chi tiết project")
async def get_project(
    session: SessionDep, user: CurrentUserDep, project_id: uuid.UUID
) -> ProjectRead:
    project = await project_service.get_project(session, project_id)
    return _read(project, user)


@router.patch("/{project_id}", response_model=ProjectRead, summary="Cập nhật project")
async def update_project(
    session: SessionDep, user: CurrentUserDep, project_id: uuid.UUID, payload: ProjectUpdate
) -> ProjectRead:
    project = await project_service.update_project(session, user, project_id, payload)
    return _read(project, user)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xoá project",
    description=(
        "Chỉ người tạo hoặc lead/admin. Task thuộc project sẽ được gỡ liên kết "
        "(project_id = null), không bị xoá theo."
    ),
)
async def delete_project(session: SessionDep, user: CurrentUserDep, project_id: uuid.UUID) -> None:
    await project_service.delete_project(session, user, project_id)
