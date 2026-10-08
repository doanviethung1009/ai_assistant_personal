"""Lịch sử duyệt web: web đẩy lên theo lô, đọc phân trang, xoá theo profile.

Dữ liệu riêng tư nhạy cảm (xem models/browser_history.py). Route tĩnh `/batch` khai báo
trước; hiện chưa có route động nhưng giữ thứ tự để thêm `/{id}` sau không bị nuốt.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.deps import ImportSecretHeader, SessionDep, guard_import_secret
from app.schemas.browser_history import (
    BrowserHistoryBatch,
    BrowserHistoryBatchResult,
    BrowserHistoryDeleteResult,
    BrowserHistoryRead,
)
from app.schemas.common import Page
from app.services import browser_history_service as service

router = APIRouter(prefix="/browser-history", tags=["browser-history"])


@router.post(
    "/batch",
    response_model=BrowserHistoryBatchResult,
    summary="Đẩy một lô lịch sử (upsert, chỉ tăng, idempotent)",
)
async def push_batch(
    session: SessionDep, payload: BrowserHistoryBatch
) -> BrowserHistoryBatchResult:
    return await service.upsert_batch(session, payload.profile, payload.items)


@router.get(
    "",
    response_model=Page[BrowserHistoryRead],
    summary="Danh sách lịch sử, mới nhất trước",
)
async def list_history(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    profile: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[BrowserHistoryRead]:
    rows, total = await service.list_history(
        session, q=q, profile=profile, limit=limit, offset=offset
    )
    return Page[BrowserHistoryRead](
        items=[BrowserHistoryRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "",
    response_model=BrowserHistoryDeleteResult,
    summary="Xoá toàn bộ lịch sử của một profile (KHÔNG hoàn tác, cần X-Import-Secret)",
)
async def delete_history(
    request: Request,
    session: SessionDep,
    profile: Annotated[str, Query(min_length=1, max_length=200)],
    import_secret: ImportSecretHeader = None,
) -> BrowserHistoryDeleteResult:
    """Web không có đăng nhập và xoá không hoàn tác, nên đòi cùng mật khẩu như nhập thật."""
    guard_import_secret(request, import_secret)
    clean = service.normalize_profile(profile)
    return BrowserHistoryDeleteResult(deleted=await service.delete_profile(session, clean))
