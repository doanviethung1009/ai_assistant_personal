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
