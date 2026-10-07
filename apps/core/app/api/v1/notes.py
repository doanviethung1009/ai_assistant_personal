from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import SessionDep
from app.core.config import settings
from app.models.enums import NoteKind, NoteSource
from app.schemas.common import Page
from app.schemas.note import (
    NoteCreate,
    NotePurgeResponse,
    NoteRead,
    NoteTrashResponse,
    NoteUpdate,
)
from app.services import note_service
from app.services.note_service import NoteFilters, SortField

router = APIRouter(prefix="/notes", tags=["notes"])


# ═══════════════════════════════════════════════════════════════════════
#  Đường dẫn tĩnh phải khai báo TRƯỚC /{note_id}, nếu không FastAPI sẽ
#  khớp "trash" thành note_id và trả 422.
# ═══════════════════════════════════════════════════════════════════════


@router.get(
    "/trash",
    response_model=NoteTrashResponse,
    summary="Note trong thùng rác",
    description=(
        "Dọn luôn những note đã quá thời hạn giữ rồi mới trả danh sách. "
        "Chưa có scheduler nên đây là một trong các điểm dọn tự động."
    ),
)
async def list_note_trash(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NoteTrashResponse:
    purged = await note_service.purge_expired(session)
    notes, total = await note_service.list_trash(session, limit=limit, offset=offset)
    return NoteTrashResponse(
        items=[NoteRead.model_validate(note) for note in notes],
        total=total,
        limit=limit,
        offset=offset,
        retention_days=settings.trash_retention_days,
        purged_now=purged,
    )


@router.post(
    "/trash/purge",
    response_model=NotePurgeResponse,
    summary="Dọn note đã quá thời hạn giữ",
)
async def purge_expired_notes(session: SessionDep) -> NotePurgeResponse:
    purged = await note_service.purge_expired(session)
    return NotePurgeResponse(
        purged=purged, retention_days=settings.trash_retention_days
    )


@router.post(
    "/trash/empty",
    response_model=NotePurgeResponse,
    summary="Xoá vĩnh viễn toàn bộ thùng rác note",
    description="Không chờ hết hạn. Không hoàn tác được.",
)
async def empty_note_trash(session: SessionDep) -> NotePurgeResponse:
    purged = await note_service.empty_trash(session)
    return NotePurgeResponse(
        purged=purged, retention_days=settings.trash_retention_days
    )


@router.get(
    "/stats",
    response_model=dict[str, int],
    summary="Số note theo từng loại",
    description="Đếm trong view đang chọn: archived=false (mặc định) hoặc true.",
)
async def note_stats(
    session: SessionDep, archived: Annotated[bool, Query()] = False
) -> dict[str, int]:
    return await note_service.count_by_kind(session, archived=archived)


# ── Collection ─────────────────────────────────────────────────────────


@router.get("", response_model=Page[NoteRead], summary="Danh sách note")
async def list_notes(
    session: SessionDep,
    kind: Annotated[list[NoteKind] | None, Query()] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    source: Annotated[NoteSource | None, Query()] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    pinned_only: Annotated[bool, Query()] = False,
    archived: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort_by: Annotated[SortField, Query()] = "updated_at",
    sort_desc: Annotated[bool, Query()] = True,
) -> Page[NoteRead]:
    filters = NoteFilters(
        kind=kind,
        project_id=project_id,
        source=source,
        tags=tags or [],
        query=q,
        pinned_only=pinned_only,
        archived=archived,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )
    notes, total = await note_service.list_notes(session, filters)
    return Page[NoteRead](
        items=[NoteRead.model_validate(note) for note in notes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo note",
    description=(
        "Trường `content` được lưu nguyên văn và KHÔNG BAO GIỜ được thực thi. "
        "Một note chứa câu lệnh phá hoại chỉ là chuỗi ký tự trong database."
    ),
)
async def create_note(session: SessionDep, payload: NoteCreate) -> NoteRead:
    note = await note_service.create_note(session, payload)
    return NoteRead.model_validate(note)


# ── Từng note ──────────────────────────────────────────────────────────


@router.get("/{note_id}", response_model=NoteRead, summary="Chi tiết note")
async def get_note(session: SessionDep, note_id: uuid.UUID) -> NoteRead:
    note = await note_service.get_note(session, note_id)
    return NoteRead.model_validate(note)


@router.patch("/{note_id}", response_model=NoteRead, summary="Cập nhật note")
async def update_note(
    session: SessionDep, note_id: uuid.UUID, payload: NoteUpdate
) -> NoteRead:
    note = await note_service.update_note(session, note_id, payload)
    return NoteRead.model_validate(note)


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xoá note",
    description=(
        "Mặc định là xoá mềm: note vào thùng rác và còn phục hồi được. "
        "Truyền permanent=true để xoá thẳng, không hoàn tác."
    ),
)
async def delete_note(
    session: SessionDep,
    note_id: uuid.UUID,
    permanent: Annotated[bool, Query()] = False,
) -> None:
    if permanent:
        await note_service.purge_note_now(session, note_id)
        return
    await note_service.delete_note(session, note_id)


@router.post(
    "/{note_id}/restore",
    response_model=NoteRead,
    summary="Phục hồi note từ thùng rác",
)
async def restore_note(session: SessionDep, note_id: uuid.UUID) -> NoteRead:
    note = await note_service.restore_note(session, note_id)
    return NoteRead.model_validate(note)


@router.post(
    "/{note_id}/archive",
    response_model=NoteRead,
    summary="Lưu trữ note",
    description=(
        "Ẩn khỏi danh sách mặc định, không bị dọn như thùng rác. Idempotent: "
        "note đã lưu trữ giữ nguyên archived_at cũ."
    ),
)
async def archive_note(session: SessionDep, note_id: uuid.UUID) -> NoteRead:
    note = await note_service.archive_note(session, note_id)
    return NoteRead.model_validate(note)


@router.post(
    "/{note_id}/unarchive",
    response_model=NoteRead,
    summary="Bỏ lưu trữ note",
)
async def unarchive_note(session: SessionDep, note_id: uuid.UUID) -> NoteRead:
    note = await note_service.unarchive_note(session, note_id)
    return NoteRead.model_validate(note)


@router.post(
    "/{note_id}/use",
    response_model=NoteRead,
    summary="Ghi nhận một lần dùng note",
    description=(
        "Tăng use_count và cập nhật last_used_at. Web gọi khi người dùng bấm "
        "copy. Đây chỉ là dấu hiệu note còn hữu ích, không phải bằng chứng "
        "lệnh đã được chạy."
    ),
)
async def mark_note_used(session: SessionDep, note_id: uuid.UUID) -> NoteRead:
    note = await note_service.mark_used(session, note_id)
    return NoteRead.model_validate(note)
