"""Logic nghiệp vụ của note (sổ tay) trên Postgres thật."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.models.enums import NoteKind
from app.models.note import Note
from app.schemas.note import NoteCreate, NoteUpdate
from app.services import note_service
from app.services.clock import now_utc
from app.services.errors import NotFoundError
from tests.conftest import Persona

pytestmark = pytest.mark.db


async def test_create_normalizes_tags(session: AsyncSession, default_user: Persona) -> None:
    note = await note_service.create_note(
        session,
        default_user.user,
        NoteCreate(title="lệnh", kind=NoteKind.COMMAND, content="ls -la", tags=["Docker Compose"]),
    )
    assert note.tags == ["docker-compose"]


async def test_mark_used_increments_counter(session: AsyncSession, default_user: Persona) -> None:
    note = await note_service.create_note(
        session, default_user.user, NoteCreate(title="n", kind=NoteKind.TEXT, content="c")
    )
    used = await note_service.mark_used(session, default_user.user, note.id)
    assert used.use_count == 1
    assert used.last_used_at is not None


async def test_delete_goes_to_trash_and_restore(
    session: AsyncSession, default_user: Persona
) -> None:
    note = await note_service.create_note(
        session, default_user.user, NoteCreate(title="n", kind=NoteKind.TEXT, content="c")
    )
    await note_service.delete_note(session, default_user.user, note.id)
    with pytest.raises(NotFoundError):
        await note_service.get_note(session, default_user.user, note.id)

    restored = await note_service.restore_note(session, default_user.user, note.id)
    assert restored.deleted_at is None


async def test_update_changes_only_given_fields(
    session: AsyncSession, default_user: Persona
) -> None:
    note = await note_service.create_note(
        session, default_user.user, NoteCreate(title="gốc", kind=NoteKind.TEXT, content="nội dung")
    )
    updated = await note_service.update_note(
        session, default_user.user, note.id, NoteUpdate(title="mới")
    )
    assert updated.title == "mới"
    assert updated.content == "nội dung"


# ═══════════════════════════════════════════════════════════════════════
#  Lưu trữ
# ═══════════════════════════════════════════════════════════════════════


async def _new_note(
    session: AsyncSession,
    user: CurrentUser,
    title: str = "n",
    kind: NoteKind = NoteKind.TEXT,
):
    return await note_service.create_note(
        session, user, NoteCreate(title=title, kind=kind, content="c")
    )


async def test_archive_moves_note_between_views(
    session: AsyncSession, default_user: Persona
) -> None:
    note = await _new_note(session, default_user.user)
    note_id = note.id

    archived = await note_service.archive_note(session, default_user.user, note_id)
    assert archived.archived_at is not None

    active, _ = await note_service.list_notes(
        session, default_user.user, note_service.NoteFilters()
    )
    assert note_id not in {n.id for n in active}
    arch, total = await note_service.list_notes(
        session, default_user.user, note_service.NoteFilters(archived=True)
    )
    assert note_id in {n.id for n in arch}
    assert total == 1

    await note_service.unarchive_note(session, default_user.user, note_id)
    active, _ = await note_service.list_notes(
        session, default_user.user, note_service.NoteFilters()
    )
    assert note_id in {n.id for n in active}


async def test_archive_is_idempotent_and_keeps_first_timestamp(
    session: AsyncSession, default_user: Persona
) -> None:
    note = await _new_note(session, default_user.user)
    first = (await note_service.archive_note(session, default_user.user, note.id)).archived_at
    second = (await note_service.archive_note(session, default_user.user, note.id)).archived_at
    assert first == second

    # unarchive note chưa lưu trữ cũng không lỗi
    await note_service.unarchive_note(session, default_user.user, note.id)
    again = await note_service.unarchive_note(session, default_user.user, note.id)
    assert again.archived_at is None


async def test_archive_deleted_note_not_found(session: AsyncSession, default_user: Persona) -> None:
    note = await _new_note(session, default_user.user)
    await note_service.delete_note(session, default_user.user, note.id)
    with pytest.raises(NotFoundError):
        await note_service.archive_note(session, default_user.user, note.id)


async def test_delete_then_restore_keeps_archived(
    session: AsyncSession, default_user: Persona
) -> None:
    note = await _new_note(session, default_user.user)
    note_id = note.id
    await note_service.archive_note(session, default_user.user, note_id)
    await note_service.delete_note(session, default_user.user, note_id)

    restored = await note_service.restore_note(session, default_user.user, note_id)
    assert restored.archived_at is not None
    arch, _ = await note_service.list_notes(
        session, default_user.user, note_service.NoteFilters(archived=True)
    )
    assert note_id in {n.id for n in arch}


async def test_count_by_kind_respects_archive_view(
    session: AsyncSession, default_user: Persona
) -> None:
    keep = await _new_note(session, default_user.user, "a", NoteKind.TEXT)
    gone = await _new_note(session, default_user.user, "b", NoteKind.COMMAND)
    await note_service.archive_note(session, default_user.user, gone.id)
    assert keep.id != gone.id

    assert await note_service.count_by_kind(session, default_user.user) == {"text": 1}
    assert await note_service.count_by_kind(session, default_user.user, archived=True) == {
        "command": 1
    }


async def test_archived_note_still_readable_and_usable(
    session: AsyncSession, default_user: Persona
) -> None:
    note = await _new_note(session, default_user.user)
    note_id = note.id
    await note_service.archive_note(session, default_user.user, note_id)

    got = await note_service.get_note(session, default_user.user, note_id)
    assert got.archived_at is not None
    used = await note_service.mark_used(session, default_user.user, note_id)
    assert used.use_count == 1


async def test_purge_expired_ignores_archived_alive_notes(
    session: AsyncSession, default_user: Persona
) -> None:
    note = await _new_note(session, default_user.user)
    note_id = note.id
    await note_service.archive_note(session, default_user.user, note_id)

    assert await note_service.purge_expired(session) == 0
    assert (await note_service.get_note(session, default_user.user, note_id)).id == note_id


async def test_purge_expired_removes_old_deleted_archived_note(
    session: AsyncSession, default_user: Persona
) -> None:
    """Note lưu trữ KHÔNG được miễn dọn nếu đã nằm trong thùng rác quá hạn."""
    note = await _new_note(session, default_user.user)
    note_id = note.id
    await note_service.archive_note(session, default_user.user, note_id)
    await note_service.delete_note(session, default_user.user, note_id)
    await session.execute(
        update(Note).where(Note.id == note_id).values(deleted_at=now_utc() - timedelta(days=3650))
    )

    assert await note_service.purge_expired(session) == 1
    with pytest.raises(NotFoundError):
        await note_service.get_note(session, default_user.user, note_id, include_deleted=True)


async def test_empty_trash_leaves_alive_archived_notes(
    session: AsyncSession, default_user: Persona
) -> None:
    keep = await _new_note(session, default_user.user)
    keep_id = keep.id
    await note_service.archive_note(session, default_user.user, keep_id)
    gone = await _new_note(session, default_user.user)
    await note_service.delete_note(session, default_user.user, gone.id)

    assert await note_service.empty_trash(session, default_user.user) == 1
    assert (
        await note_service.get_note(session, default_user.user, keep_id)
    ).archived_at is not None
