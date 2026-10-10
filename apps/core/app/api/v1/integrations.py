"""Kết nối tích hợp (Jira...). Token là write-only: không endpoint nào trả token.

`/{id}/sync` (B4b) là POST có hậu tố nên không đụng route PATCH/DELETE `/{id}`; mọi route
ở đây đều có tham số động, chưa có route tĩnh nào cần khai báo trước.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import Field

from app.api.deps import ImportSecretHeader, SessionDep, guard_import_secret
from app.schemas.common import Page
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationRead,
    IntegrationUpdate,
    SyncResult,
)
from app.services import integration_service as service
from app.services import integration_sync_service

# Tên người: không ký tự điều khiển (Jira sẽ trả 400 và log khó đọc).
_NAME_PATTERN = r"^[^\x00-\x1f]+$"

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


def _require_import_secret(request: Request, import_secret: ImportSecretHeader = None) -> None:
    """Sync ghi hàng loạt và gọi ra ngoài mà web không có đăng nhập: cần thêm X-Import-Secret.

    Là dependency để 403 đến trước mọi kiểm tra khác (kể cả 422 của `since`).
    """
    guard_import_secret(request, import_secret)


@router.post(
    "/{connection_id}/sync",
    response_model=SyncResult,
    dependencies=[Depends(_require_import_secret)],
    summary="Đồng bộ Jira theo yêu cầu (đòi X-Import-Secret)",
    description=(
        "Kéo issue từ Jira về task (scope=work, source=jira), idempotent. `since` (ISO "
        "8601, tuỳ chọn) chỉ lấy issue cập nhật gần đây. Tối đa 100 trang x 100 issue "
        "(chạm trần: truncated=true). 403 sai secret, 409 thiếu token hoặc đang có sync "
        "khác, 422 since/JQL sai hoặc host bị chặn (SSRF), 502/504 lỗi Jira (thông báo "
        "tự viết, không kèm nội dung Jira), 503 không giải mã được token."
    ),
)
async def sync_connection(
    request: Request,
    connection_id: uuid.UUID,
    since: Annotated[
        str | None,
        Query(max_length=40, description="ISO 8601, vd. 2024-05-01 hoặc 2024-05-01T10:00:00Z"),
    ] = None,
    assignee: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=100, pattern=_NAME_PATTERN)]] | None,
        Query(max_length=20, description="Chỉ kéo task giao cho những người này (lặp tham số)"),
    ] = None,
) -> SyncResult:
    # Cố ý KHÔNG nhận SessionDep: get_session giữ một transaction mở tới hết request, mà
    # sync gọi Jira hàng phút. Service tự mở các transaction ngắn.
    client_ip = request.client.host if request.client else None
    return await integration_sync_service.run_sync(
        connection_id, since, client_ip=client_ip, assignees=assignee
    )
