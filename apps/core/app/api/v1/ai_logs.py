"""Nhật ký xử lý của AI (AI Task Trace) — đọc và ghi qua API.

Dùng cùng khuôn với notes/tasks: `SessionDep` (tự commit), envelope `Page[T]`,
lỗi nghiệp vụ ném `DomainError` để main.py map sang HTTP. Xác thực API key đã
được áp ở router cha (`api_router`), không khai lại ở đây.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.models.enums import AiLogCategory
from app.schemas.ai_log import AiLogCreate, AiLogRead
from app.schemas.common import Page
from app.services import ai_log_service

router = APIRouter()


@router.get("", response_model=Page[AiLogRead], summary="Danh sách nhật ký AI")
async def list_ai_logs(
    session: SessionDep,
    category: Annotated[list[AiLogCategory] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AiLogRead]:
    filters = ai_log_service.AiLogFilters(category=category, limit=limit, offset=offset)
    logs, total = await ai_log_service.list_ai_logs(session, filters)
    return Page[AiLogRead](
        items=[AiLogRead.model_validate(log) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=AiLogRead,
    status_code=201,
    summary="Ghi một nhật ký AI",
)
async def create_ai_log(session: SessionDep, payload: AiLogCreate) -> AiLogRead:
    log = await ai_log_service.create_ai_log(session, payload)
    return AiLogRead.model_validate(log)


@router.get("/{log_id}", response_model=AiLogRead, summary="Chi tiết nhật ký AI")
async def get_ai_log(session: SessionDep, log_id: uuid.UUID) -> AiLogRead:
    log = await ai_log_service.get_ai_log(session, log_id)
    return AiLogRead.model_validate(log)
