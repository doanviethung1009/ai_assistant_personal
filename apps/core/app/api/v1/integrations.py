"""Kết nối tích hợp (Jira...). Token là write-only: không endpoint nào trả token.

Chưa có `/{id}/sync` (thuộc B4b). Route động `/{connection_id}` là route duy nhất nên
chưa cần lo thứ tự khai báo.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import SessionDep
from app.schemas.common import Page
from app.schemas.integration import IntegrationCreate, IntegrationRead, IntegrationUpdate
from app.services import integration_service as service

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get(
    "",
    response_model=Page[IntegrationRead],
    summary="Danh sách kết nối (không bao giờ trả token)",
)
async def list_connections(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[IntegrationRead]:
    rows, total = await service.list_connections(session, limit=limit, offset=offset)
    return Page[IntegrationRead](
        items=[IntegrationRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=IntegrationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo kết nối (token chỉ ghi; 503 nếu thiếu INTEGRATION_SECRET_KEY)",
)
async def create_connection(session: SessionDep, payload: IntegrationCreate) -> IntegrationRead:
    conn = await service.create_connection(session, payload)
    return IntegrationRead.model_validate(conn)


@router.patch(
    "/{connection_id}",
    response_model=IntegrationRead,
    summary="Sửa kết nối (không gửi token = giữ token cũ; clear_token=true để xoá)",
)
async def update_connection(
    session: SessionDep, connection_id: uuid.UUID, payload: IntegrationUpdate
) -> IntegrationRead:
    conn = await service.update_connection(session, connection_id, payload)
    return IntegrationRead.model_validate(conn)


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xoá kết nối cùng token đã mã hoá",
)
async def delete_connection(session: SessionDep, connection_id: uuid.UUID) -> None:
    await service.delete_connection(session, connection_id)
