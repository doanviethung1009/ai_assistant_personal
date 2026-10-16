"""API quản lý tag toàn cục, gọi qua ASGI trên Postgres thật."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select, text

from app.db import locks
from app.db.session import SessionFactory
from app.models.enums import TaskEventType, TaskScope, UserRole
from app.models.task import Task, TaskEvent
from tests.conftest import create_persona

pytestmark = pytest.mark.db

TAGS = "/api/v1/tags"


async def _task(client: httpx.AsyncClient, tags: list[str], scope: str = "personal") -> str:
    resp = await client.post("/api/v1/tasks", json={"title": "t", "tags": tags, "scope": scope})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _note(client: httpx.AsyncClient, tags: list[str]) -> str:
    resp = await client.post("/api/v1/notes", json={"title": "n", "content": "c", "tags": tags})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_stats_counts_tasks_and_notes(client: httpx.AsyncClient) -> None:
    await _task(client, ["a", "b"])
    await _task(client, ["a"])
    await _note(client, ["b", "c"])
    resp = await client.get(f"{TAGS}/stats")
    assert resp.status_code == 200
    assert resp.json() == [
        {"name": "a", "task_count": 2, "note_count": 0},
        {"name": "b", "task_count": 1, "note_count": 1},
        {"name": "c", "task_count": 0, "note_count": 1},
    ]


async def test_stats_skips_soft_deleted(client: httpx.AsyncClient) -> None:
    task_id = await _task(client, ["gone"])
    assert (await client.delete(f"/api/v1/tasks/{task_id}")).status_code in (200, 204)
    assert (await client.get(f"{TAGS}/stats")).json() == []


async def test_rename_merges_into_existing_tag(client: httpx.AsyncClient) -> None:
    both = await _task(client, ["old", "new"])
    only = await _task(client, ["old"])
    note = await _note(client, ["old"])
    resp = await client.patch(f"{TAGS}/old", json={"new_name": "New"})
    assert resp.status_code == 200
    assert resp.json() == {"tasks": 2, "notes": 1, "rule": None}
    assert (await client.get(f"/api/v1/tasks/{both}")).json()["tags"] == ["new"]
    assert (await client.get(f"/api/v1/tasks/{only}")).json()["tags"] == ["new"]
    assert (await client.get(f"/api/v1/notes/{note}")).json()["tags"] == ["new"]


async def test_rename_errors(client: httpx.AsyncClient) -> None:
    await _task(client, ["x"])
    assert (await client.patch(f"{TAGS}/x", json={"new_name": "x"})).status_code == 409
    assert (await client.patch(f"{TAGS}/missing", json={"new_name": "y"})).status_code == 404
    assert (await client.patch(f"{TAGS}/x", json={"new_name": "   "})).status_code == 422


async def test_delete_removes_tag(client: httpx.AsyncClient) -> None:
    task_id = await _task(client, ["a", "b"])
    resp = await client.delete(f"{TAGS}/a")
    assert resp.status_code == 200
    assert resp.json() == {"tasks": 1, "notes": 0, "rule": None}
    assert (await client.get(f"/api/v1/tasks/{task_id}")).json()["tags"] == ["b"]
    assert (await client.delete(f"{TAGS}/a")).status_code == 404


async def test_member_cannot_touch_work_tasks_or_others_data(client: httpx.AsyncClient) -> None:
    """Member đổi tên được tag của mình, nhưng không động vào task work hay note người khác."""
    await _task(client, ["shared"], scope="work")  # admin tạo task work
    await _note(client, ["shared"])  # note của admin
    member = await create_persona("member-tags@test.local", UserRole.MEMBER)

    stats = await client.get(f"{TAGS}/stats", headers=member.headers)
    assert stats.json() == [{"name": "shared", "task_count": 1, "note_count": 0}]

    resp = await client.patch(f"{TAGS}/shared", json={"new_name": "hacked"}, headers=member.headers)
    assert resp.status_code == 404  # không có gì member được phép sửa
    assert (await client.delete(f"{TAGS}/shared", headers=member.headers)).status_code == 404
    names = {t["name"] for t in (await client.get(f"{TAGS}/stats")).json()}
    assert names == {"shared"}


async def test_tag_with_slash_and_soft_deleted_untouched(client: httpx.AsyncClient) -> None:
    """Tag có `/` vẫn đổi được (route :path); task đã xoá mềm không bị đụng."""
    live = await _task(client, ["a/b"])
    dead = await _task(client, ["a/b"])
    assert (await client.delete(f"/api/v1/tasks/{dead}")).status_code in (200, 204)
    resp = await client.patch(f"{TAGS}/a%2Fb", json={"new_name": "ab"})
    assert resp.status_code == 200
    assert resp.json() == {"tasks": 1, "notes": 0, "rule": None}
    assert (await client.get(f"/api/v1/tasks/{live}")).json()["tags"] == ["ab"]


async def test_member_renames_own_tags(client: httpx.AsyncClient) -> None:
    """Member đổi được tag trên note và task personal của mình, task work của team giữ nguyên."""
    work = await _task(client, ["team"], scope="work")
    member = await create_persona("member-own@test.local", UserRole.MEMBER)
    resp = await client.post(
        "/api/v1/notes",
        json={"title": "n", "content": "c", "tags": ["team"]},
        headers=member.headers,
    )
    assert resp.status_code == 201
    resp = await client.patch(f"{TAGS}/team", json={"new_name": "mine"}, headers=member.headers)
    assert resp.status_code == 200
    assert resp.json() == {"tasks": 0, "notes": 1, "rule": None}
    assert (await client.get(f"/api/v1/tasks/{work}")).json()["tags"] == ["team"]


# ── Audit, dữ liệu cũ chưa chuẩn hoá, khoá ──────────────────────────


async def _events(task_id: str) -> list[TaskEvent]:
    async with SessionFactory() as s:
        stmt = select(TaskEvent).where(
            TaskEvent.task_id == uuid.UUID(task_id), TaskEvent.event_type == TaskEventType.UPDATED
        )
        return list((await s.execute(stmt)).scalars())


async def test_rename_and_delete_write_updated_event_per_task(client: httpx.AsyncClient) -> None:
    a = await _task(client, ["old", "keep"])
    b = await _task(client, ["old"])
    untouched = await _task(client, ["other"])
    assert (await client.patch(f"{TAGS}/old", json={"new_name": "fresh"})).status_code == 200
    for tid in (a, b):
        (ev,) = await _events(tid)
        assert ev.payload == {"tags": {"from": "old", "to": "fresh"}}
        assert ev.actor_user_id is not None
    assert await _events(untouched) == []

    assert (await client.delete(f"{TAGS}/fresh")).status_code == 200
    for tid in (a, b):
        evs = await _events(tid)
        assert len(evs) == 2
        assert {"tags": {"from": "fresh", "to": None}} in [e.payload for e in evs]


async def _insert_raw_task(tags: list[str], scope: TaskScope = TaskScope.WORK) -> str:
    """Chèn thẳng bằng DB, bỏ qua normalize_tags như dữ liệu cũ."""
    async with SessionFactory() as s:
        task = Task(title="legacy", tags=tags, scope=scope)
        s.add(task)
        await s.commit()
        return str(task.id)


async def _tags_of(task_id: str) -> list[str]:
    async with SessionFactory() as s:
        return list((await s.get(Task, uuid.UUID(task_id), populate_existing=True)).tags)  # type: ignore[union-attr]


async def test_rename_matches_unnormalized_stored_tag(client: httpx.AsyncClient) -> None:
    tid = await _insert_raw_task(["Legacy Tag", "x"])
    stats = {t["name"] for t in (await client.get(f"{TAGS}/stats")).json()}
    assert "Legacy Tag" in stats
    resp = await client.patch(f"{TAGS}/Legacy Tag", json={"new_name": "Modern Tag"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tasks"] == 1
    # Rule dùng tên chuẩn hoá làm nguồn, không phải chuỗi thô.
    assert resp.json()["rule"]["source_tag"] == "legacy-tag"
    assert resp.json()["rule"]["target_tag"] == "modern-tag"
    assert await _tags_of(tid) == ["modern-tag", "x"]


async def test_delete_matches_unnormalized_stored_tag(client: httpx.AsyncClient) -> None:
    tid = await _insert_raw_task(["Legacy Tag", "x"])
    resp = await client.delete(f"{TAGS}/Legacy Tag")
    assert resp.status_code == 200, resp.text
    assert resp.json()["rule"]["source_tag"] == "legacy-tag"
    assert resp.json()["rule"]["target_tag"] is None
    assert await _tags_of(tid) == ["x"]


async def test_rename_handles_both_raw_and_normalized_on_one_row(
    client: httpx.AsyncClient,
) -> None:
    tid = await _insert_raw_task(["Foo", "foo", "y"])
    resp = await client.patch(f"{TAGS}/Foo", json={"new_name": "bar"})
    assert resp.status_code == 200, resp.text
    assert await _tags_of(tid) == ["bar", "y"]


async def test_rename_normalizes_legacy_casing_in_place(client: httpx.AsyncClient) -> None:
    """"Foo" -> "foo" là chuẩn hoá lại dữ liệu cũ: được phép và không ghi rule tự trỏ."""
    tid = await _insert_raw_task(["Foo"])
    resp = await client.patch(f"{TAGS}/Foo", json={"new_name": "foo"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["rule"] is None
    assert await _tags_of(tid) == ["foo"]


@pytest.mark.parametrize("method", ["patch", "delete"])
async def test_tag_change_409_while_import_lock_held(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    """Có lô sync/nhập đang giữ advisory lock thì đổi tên/xoá tag là 409, không phải 500."""
    tid = await _task(client, ["x"], scope="work")
    monkeypatch.setattr(locks, "DEFAULT_LOCK_TIMEOUT", "200ms")
    async with SessionFactory() as holder:
        await holder.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:n))"), {"n": locks.IMPORT_LOCK_NAME}
        )
        try:
            if method == "patch":
                resp = await client.patch(f"{TAGS}/x", json={"new_name": "y"})
            else:
                resp = await client.delete(f"{TAGS}/x")
        finally:
            await holder.rollback()
    assert resp.status_code == 409, resp.text
    assert (await client.get(f"/api/v1/tasks/{tid}")).json()["tags"] == ["x"]
    # Nhả khoá rồi thì chạy bình thường.
    assert (await client.patch(f"{TAGS}/x", json={"new_name": "y"})).status_code == 200
