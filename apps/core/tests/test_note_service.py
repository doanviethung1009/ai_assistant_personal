"""Logic nghiệp vụ của note (sổ tay) trên Postgres thật."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NoteKind
from app.schemas.note import NoteCreate, NoteUpdate
from app.services import note_service
from app.services.errors import NotFoundError

pytestmark = pytest.mark.db


async def test_create_normalizes_tags(session: AsyncSession) -> None:
    note = await note_service.create_note(
        session,
        NoteCreate(title="lệnh", kind=NoteKind.COMMAND, content="ls -la", tags=["Docker Compose"]),
    )
    assert note.tags == ["docker-compose"]


async def test_mark_used_increments_counter(session: AsyncSession) -> None:
    note = await note_service.create_note(
        session, NoteCreate(title="n", kind=NoteKind.TEXT, content="c")
    )
    used = await note_service.mark_used(session, note.id)
    assert used.use_count == 1
    assert used.last_used_at is not None


async def test_delete_goes_to_trash_and_restore(session: AsyncSession) -> None:
    note = await note_service.create_note(
        session, NoteCreate(title="n", kind=NoteKind.TEXT, content="c")
    )
    await note_service.delete_note(session, note.id)
    with pytest.raises(NotFoundError):
        await note_service.get_note(session, note.id)

    restored = await note_service.restore_note(session, note.id)
    assert restored.deleted_at is None


async def test_update_changes_only_given_fields(session: AsyncSession) -> None:
    note = await note_service.create_note(
        session, NoteCreate(title="gốc", kind=NoteKind.TEXT, content="nội dung")
    )
    updated = await note_service.update_note(session, note.id, NoteUpdate(title="mới"))
    assert updated.title == "mới"
    assert updated.content == "nội dung"


# ═══════════════════════════════════════════════════════════════════════
#  Lưu trữ
# ═══════════════════════════════════════════════════════════════════════


async def _new_note(session: AsyncSession, title: str = "n", kind: NoteKind = NoteKind.TEXT):
    return await note_service.create_note(
        session, NoteCreate(title=title, kind=kind, content="c")
    )


async def test_archive_moves_note_between_views(session: AsyncSession) -> None:
    note = await _new_note(session)
    note_id = note.id

    archived = await note_service.archive_note(session, note_id)
    assert archived.archived_at is not None

    active, _ = await note_service.list_notes(session, note_service.NoteFilters())
    assert note_id not in {n.id for n in active}
    arch, total = await note_service.list_notes(
        session, note_service.NoteFilters(archived=True)
    )
    assert note_id in {n.id for n in arch}
    assert total == 1

    await note_service.unarchive_note(session, note_id)
    active, _ = await note_service.list_notes(session, note_service.NoteFilters())
    assert note_id in {n.id for n in active}


async def test_archive_is_idempotent_and_keeps_first_timestamp(
    session: AsyncSession,
) -> None:
    note = await _new_note(session)
    first = (await note_service.archive_note(session, note.id)).archived_at
    second = (await note_service.archive_note(session, note.id)).archived_at
    assert first == second

    # unarchive note chưa lưu trữ cũng không lỗi
    await note_service.unarchive_note(session, note.id)
    again = await note_service.unarchive_note(session, note.id)
    assert again.archived_at is None


async def test_archive_deleted_note_not_found(session: AsyncSession) -> None:
    note = await _new_note(session)
    await note_service.delete_note(session, note.id)
    with pytest.raises(NotFoundError):
        await note_service.archive_note(session, note.id)


async def test_delete_then_restore_keeps_archived(session: AsyncSession) -> None:
    note = await _new_note(session)
    note_id = note.id
    await note_service.archive_note(session, note_id)
    await note_service.delete_note(session, note_id)

    restored = await note_service.restore_note(session, note_id)
    assert restored.archived_at is not None
    arch, _ = await note_service.list_notes(
        session, note_service.NoteFilters(archived=True)
    )
    assert note_id in {n.id for n in arch}


async def test_count_by_kind_respects_archive_view(session: AsyncSession) -> None:
    keep = await _new_note(session, "a", NoteKind.TEXT)
    gone = await _new_note(session, "b", NoteKind.COMMAND)
    await note_service.archive_note(session, gone.id)
    assert keep.id != gone.id

    assert await note_service.count_by_kind(session) == {"text": 1}
    assert await note_service.count_by_kind(session, archived=True) == {"command": 1}


async def test_archived_note_still_readable_and_usable(session: AsyncSession) -> None:
    note = await _new_note(session)
    note_id = note.id
    await note_service.archive_note(session, note_id)

    got = await note_service.get_note(session, note_id)
    assert got.archived_at is not None
    used = await note_service.mark_used(session, note_id)
    assert used.use_count == 1


async def test_purge_expired_ignores_archived_alive_notes(session: AsyncSession) -> None:
    note = await _new_note(session)
    note_id = note.id
    await note_service.archive_note(session, note_id)

    assert await note_service.purge_expired(session) == 0
    assert (await note_service.get_note(session, note_id)).id == note_id
