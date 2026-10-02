import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.models.enums import AiLogCategory
from app.schemas.ai_log import AiLogCreate, AiLogRead
from app.schemas.pagination import PaginatedResponse, create_paginated_response
from app.services import ai_log_service

router = APIRouter()


@router.get("", response_model=PaginatedResponse[AiLogRead])
async def list_ai_logs(
    category: list[AiLogCategory] | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    filters = ai_log_service.AiLogFilters(
        category=category,
        limit=limit,
        offset=offset,
    )
    logs, total = await ai_log_service.list_ai_logs(session, filters)
    return create_paginated_response(logs, total, limit, offset)


@router.post("", response_model=AiLogRead, status_code=201)
async def create_ai_log(
    payload: AiLogCreate,
    session: AsyncSession = Depends(get_db),
):
    return await ai_log_service.create_ai_log(session, payload)


@router.get("/{log_id}", response_model=AiLogRead)
async def get_ai_log(
    log_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    return await ai_log_service.get_ai_log(session, log_id)
