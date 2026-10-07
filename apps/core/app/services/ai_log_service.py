import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AiLog
from app.models.enums import AiLogCategory
from app.schemas.ai_log import AiLogCreate
from app.services.errors import NotFoundError


@dataclass(slots=True)
class AiLogFilters:
    category: list[AiLogCategory] | None = None
    limit: int = 50
    offset: int = 0


def _apply_filters(stmt: Select[Any], filters: AiLogFilters) -> Select[Any]:
    if filters.category:
        stmt = stmt.where(AiLog.category.in_(filters.category))
    return stmt


async def list_ai_logs(
    session: AsyncSession, filters: AiLogFilters
) -> tuple[list[AiLog], int]:
    base = _apply_filters(select(AiLog), filters)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))

    stmt = base.order_by(AiLog.created_at.desc()).limit(filters.limit).offset(filters.offset)
    result = await session.execute(stmt)
    return list(result.scalars().unique().all()), int(total or 0)


async def get_ai_log(session: AsyncSession, log_id: uuid.UUID) -> AiLog:
    log = await session.get(AiLog, log_id)
    if log is None:
        raise NotFoundError(f"Không tìm thấy AiLog {log_id}")
    return log


async def create_ai_log(session: AsyncSession, payload: AiLogCreate) -> AiLog:
    log = AiLog(**payload.model_dump())
    session.add(log)
    await session.flush()
    await session.refresh(log)
    return log
