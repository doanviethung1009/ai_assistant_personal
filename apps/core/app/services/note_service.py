"""Logic nghiệp vụ của sổ tay.

Đơn giản hơn task_service vì note không có vòng đời: không có status, không
có hạn, không ghi nhật ký thay đổi. Cái đáng chú ý duy nhất là xoá mềm và
ràng buộc unique khi phục hồi.

LƯU Ý AN TOÀN: `note.content` chỉ được đọc và ghi như chuỗi ký tự. Không có
chỗ nào trong file này đưa nó vào shell, vào eval, hay nối vào câu SQL. Mọi
truy vấn đều qua SQLAlchemy với tham số bind.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import NoteKind, NoteSource
from app.models.note import Note
from app.models.project import Project
from app.schemas.note import NoteCreate, NoteUpdate
from app.services.clock import now_utc
from app.services.errors import ConflictError, NotFoundError, ValidationError

SortField = Literal["updated_at", "created_at", "title", "use_count", "last_used_at"]


@dataclass(slots=True)
class NoteFilters:
    kind: list[NoteKind] | None = None
    project_id: uuid.UUID | None = None
    source: NoteSource | None = None
    tags: list[str] = field(default_factory=list)
    query: str | None = None
    pinned_only: bool = False
    limit: int = 50
    offset: int = 0
    sort_by: SortField = "updated_at"
    sort_desc: bool = True


def _alive():
    """Điều kiện note chưa bị xoá mềm.

    Phải có trong MỌI truy vấn nghiệp vụ. Thiếu nó là note trong thùng rác
    lại xuất hiện ở danh sách và ở kết quả tìm kiếm.
    """
    return Note.deleted_at.is_(None)


def _apply_filters(stmt: Select[Any], filters: NoteFilters) -> Select[Any]:
    stmt = stmt.where(_alive())

    if filters.kind:
        stmt = stmt.where(Note.kind.in_(filters.kind))
    if filters.project_id is not None:
        stmt = stmt.where(Note.project_id == filters.project_id)
    if filters.source is not None:
        stmt = stmt.where(Note.source == filters.source)
    if filters.tags:
        # contains → toán tử @> của Postgres, dùng được index GIN
        stmt = stmt.where(Note.tags.contains(filters.tags))
    if filters.pinned_only:
        stmt = stmt.where(Note.is_pinned.is_(True))
    if filters.query:
        # Tìm cả trong content, vì với sổ tay thì thường chỉ nhớ một đoạn
        # trong câu lệnh chứ không nhớ tiêu đề đã đặt là gì.
        #
        # ilike với tiền tố % nên không dùng được index. Ở quy mô cá nhân
        # (vài nghìn note) sequential scan vẫn dưới một phần mười giây. Khi
        # nào chậm thì bật pg_trgm rồi thêm GIN index, không phải đổi API.
        pattern = f"%{filters.query.strip()}%"
        stmt = stmt.where(
            or_(
                Note.title.ilike(pattern),
                Note.content.ilike(pattern),
                Note.description.ilike(pattern),
                Note.context.ilike(pattern),
            )
        )
    return stmt


def _apply_sort(stmt: Select[Any], filters: NoteFilters) -> Select[Any]:
    column: Any = getattr(Note, filters.sort_by)
    ordering = (
        column.desc().nulls_last() if filters.sort_desc else column.asc().nulls_last()
    )
    # Note đã ghim luôn đứng trước, bất kể sắp xếp theo gì. Đó là toàn bộ ý
    # nghĩa của việc ghim.
    return stmt.order_by(Note.is_pinned.desc(), ordering, Note.created_at.desc())


async def _ensure_project_exists(
    session: AsyncSession, project_id: uuid.UUID | None
) -> None:
    if project_id is None:
        return
    exists = await session.scalar(select(Project.id).where(Project.id == project_id))
    if exists is None:
        raise ValidationError(f"project_id {project_id} không tồn tại")


# ═══════════════════════════════════════════════════════════════════════
#  Đọc
# ═══════════════════════════════════════════════════════════════════════


async def list_notes(
    session: AsyncSession, filters: NoteFilters
) -> tuple[list[Note], int]:
    base = _apply_filters(select(Note), filters)

    total = await session.scalar(select(func.count()).select_from(base.subquery()))

    stmt = _apply_sort(base, filters).limit(filters.limit).offset(filters.offset)
    result = await session.execute(stmt)
    return list(result.scalars().unique().all()), int(total or 0)


async def get_note(
    session: AsyncSession, note_id: uuid.UUID, *, include_deleted: bool = False
) -> Note:
    note = await session.get(Note, note_id)
    if note is None or (note.deleted_at is not None and not include_deleted):
        raise NotFoundError(f"Không tìm thấy note {note_id}")
    return note


async def list_trash(
    session: AsyncSession, *, limit: int = 100, offset: int = 0
) -> tuple[list[Note], int]:
    base = select(Note).where(Note.deleted_at.is_not(None))

    total = await session.scalar(select(func.count()).select_from(base.subquery()))

    stmt = base.order_by(Note.deleted_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().unique().all()), int(total or 0)


async def count_by_kind(session: AsyncSession) -> dict[str, int]:
    stmt = select(Note.kind, func.count()).where(_alive()).group_by(Note.kind)
    result = await session.execute(stmt)
    return {row[0].value: row[1] for row in result.all()}


# ═══════════════════════════════════════════════════════════════════════
#  Ghi
# ═══════════════════════════════════════════════════════════════════════


async def create_note(session: AsyncSession, payload: NoteCreate) -> Note:
    await _ensure_project_exists(session, payload.project_id)

    note = Note(**payload.model_dump())
    session.add(note)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"Đã có note từ nguồn {payload.source.value} với external_id "
            f"'{payload.external_id}'"
        ) from exc
    await session.refresh(note)
    return note


async def update_note(
    session: AsyncSession, note_id: uuid.UUID, payload: NoteUpdate
) -> Note:
    note = await get_note(session, note_id)
    changes = payload.model_dump(exclude_unset=True)

    if "project_id" in changes:
        await _ensure_project_exists(session, changes["project_id"])

    for attribute, value in changes.items():
        setattr(note, attribute, value)

    await session.flush()
    await session.refresh(note)
    return note


async def mark_used(session: AsyncSession, note_id: uuid.UUID) -> Note:
    """Ghi nhận một lần dùng, để sắp xếp theo mức độ hay dùng.

    Web gọi khi người dùng bấm copy. Không phải bằng chứng là lệnh đã chạy,
    chỉ là dấu hiệu note này còn hữu ích.
    """
    note = await get_note(session, note_id)
    note.use_count += 1
    note.last_used_at = now_utc()
    await session.flush()
    await session.refresh(note)
    return note


# ═══════════════════════════════════════════════════════════════════════
#  Thùng rác
# ═══════════════════════════════════════════════════════════════════════


async def delete_note(session: AsyncSession, note_id: uuid.UUID) -> Note:
    """Xoá mềm: đưa vào thùng rác, giữ theo settings.trash_retention_days.

    Retention bằng 0 thì xoá thẳng, không qua thùng rác.
    """
    note = await get_note(session, note_id)

    if settings.trash_retention_days == 0:
        await session.delete(note)
        await session.flush()
        return note

    note.deleted_at = now_utc()
    await session.flush()
    return note


async def restore_note(session: AsyncSession, note_id: uuid.UUID) -> Note:
    """Lấy note ra khỏi thùng rác."""
    note = await get_note(session, note_id, include_deleted=True)

    if note.deleted_at is None:
        raise ValidationError(f"Note {note_id} không nằm trong thùng rác")

    # Trước khi phục hồi phải chắc chắn không đụng partial unique index.
    # Tình huống thật: xoá một note đồng bộ từ Obsidian, sync tạo lại bản mới,
    # rồi bấm phục hồi bản cũ.
    if note.external_id is not None:
        clash = await session.scalar(
            select(Note.id).where(
                Note.source == note.source,
                Note.external_id == note.external_id,
                Note.deleted_at.is_(None),
                Note.id != note.id,
            )
        )
        if clash is not None:
            raise ConflictError(
                f"Đã có note khác từ nguồn {note.source.value} với external_id "
                f"'{note.external_id}'. Xoá note đó trước khi phục hồi."
            )

    note.deleted_at = None
    await session.flush()
    await session.refresh(note)
    return note


async def purge_note(session: AsyncSession, note_id: uuid.UUID) -> None:
    """Xoá vĩnh viễn. Chỉ áp dụng cho note đang nằm trong thùng rác."""
    note = await get_note(session, note_id, include_deleted=True)

    if note.deleted_at is None:
        raise ValidationError(
            f"Note {note_id} chưa ở trong thùng rác. Xoá mềm trước, "
            f"hoặc dùng DELETE với permanent=true."
        )

    await session.delete(note)
    await session.flush()


async def purge_note_now(session: AsyncSession, note_id: uuid.UUID) -> None:
    """Xoá vĩnh viễn ngay, bỏ qua thùng rác."""
    note = await get_note(session, note_id, include_deleted=True)
    await session.delete(note)
    await session.flush()


async def purge_expired(session: AsyncSession) -> int:
    """Xoá vĩnh viễn note đã quá thời hạn giữ. Trả về số bản ghi đã xoá."""
    retention = settings.trash_retention_days
    if retention == 0:
        return 0

    cutoff = now_utc() - timedelta(days=retention)
    result = await session.execute(
        delete(Note).where(Note.deleted_at.is_not(None), Note.deleted_at < cutoff)
    )
    await session.flush()
    return int(result.rowcount or 0)


async def empty_trash(session: AsyncSession) -> int:
    """Xoá vĩnh viễn toàn bộ thùng rác, không chờ hết hạn."""
    result = await session.execute(delete(Note).where(Note.deleted_at.is_not(None)))
    await session.flush()
    return int(result.rowcount or 0)
