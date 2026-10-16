"""API quản lý tag toàn cục, gọi qua ASGI trên Postgres thật."""

from __future__ import annotations

import httpx
import pytest

from app.models.enums import UserRole
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
    assert resp.json() == {"tasks": 2, "notes": 1}
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
    assert resp.json() == {"tasks": 1, "notes": 0}
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
    assert resp.json() == {"tasks": 1, "notes": 0}
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
    assert resp.json() == {"tasks": 0, "notes": 1}
    assert (await client.get(f"/api/v1/tasks/{work}")).json()["tags"] == ["team"]
