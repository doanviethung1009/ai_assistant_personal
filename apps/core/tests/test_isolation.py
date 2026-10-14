"""Cô lập dữ liệu giữa các user và ma trận quyền (docs/specs/auth-multiuser.md mục 3, 9.1).

Bốn user: A (member, alias Alice), B (member, alias Bob), L (lead), D (admin = `default_user`).
Dữ liệu: personal của A, personal của B, work giao Alice, work giao Bob, work không giao (Jira),
note của A. Task ngoài phạm vi nhìn thấy PHẢI là 404 (không phải 403) để không lộ sự tồn tại.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from app.models.enums import UserRole
from tests.conftest import Persona, create_persona

pytestmark = pytest.mark.db

TASKS = "/api/v1/tasks"
NOTES = "/api/v1/notes"


@dataclass
class World:
    a: Persona
    b: Persona
    lead: Persona
    admin: Persona
    ids: dict[str, str]
    note_a: str


def _jira(ext: str, title: str, assignee: str | None) -> dict[str, Any]:
    item: dict[str, Any] = {"external_id": ext, "title": title}
    if assignee is not None:
        item["assignee"] = assignee
    return item


@pytest.fixture
async def world(client: httpx.AsyncClient, default_user: Persona) -> World:
    a = await create_persona("a@test.local", UserRole.MEMBER, ("Alice",))
    b = await create_persona("b@test.local", UserRole.MEMBER, ("Bob",))
    lead = await create_persona("l@test.local", UserRole.LEAD)

    ids: dict[str, str] = {}
    for name, who in (("personal_a", a), ("personal_b", b)):
        resp = await client.post(
            TASKS, json={"title": name, "source": "manual"}, headers=who.headers
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["scope"] == "personal"
        ids[name] = resp.json()["id"]

    # Task Jira (scope work, owner NULL) do lead đồng bộ vào.
    batch = {
        "source": "jira",
        "items": [
            _jira("J-1", "work_alice", "Alice"),
            _jira("J-2", "work_bob", "Bob"),
            _jira("J-3", "work_free", None),
        ],
    }
    resp = await client.post(f"{TASKS}/upsert-batch", json=batch, headers=lead.headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["added"] == 3
    listed = await client.get(TASKS, params={"view": "work", "limit": 200}, headers=lead.headers)
    for item in listed.json()["items"]:
        ids[item["title"]] = item["id"]

    resp = await client.post(
        NOTES,
        json={"title": "note_a", "kind": "text", "content": "bí mật của A"},
        headers=a.headers,
    )
    assert resp.status_code == 201, resp.text
    return World(a, b, lead, default_user, ids, resp.json()["id"])


def _titles(resp: httpx.Response) -> set[str]:
    assert resp.status_code == 200, resp.text
    return {item["title"] for item in resp.json()["items"]}


# ═══════════════════════════════════════════════════════════════════════
#  Đọc: danh sách và view
# ═══════════════════════════════════════════════════════════════════════


async def test_list_all_hides_other_users_personal(client: httpx.AsyncClient, world: World) -> None:
    got_a = _titles(
        await client.get(TASKS, params={"view": "all", "limit": 200}, headers=world.a.headers)
    )
    assert got_a == {"personal_a", "work_alice", "work_bob", "work_free"}
    got_b = _titles(
        await client.get(TASKS, params={"view": "all", "limit": 200}, headers=world.b.headers)
    )
    assert got_b == {"personal_b", "work_alice", "work_bob", "work_free"}
    # Admin cũng không đọc được task personal của người khác.
    got_d = _titles(
        await client.get(TASKS, params={"view": "all", "limit": 200}, headers=world.admin.headers)
    )
    assert got_d == {"work_alice", "work_bob", "work_free"}


async def test_view_personal_and_work_are_scoped_to_caller(
    client: httpx.AsyncClient, world: World
) -> None:
    mine = await client.get(TASKS, params={"view": "personal"}, headers=world.a.headers)
    assert _titles(mine) == {"personal_a"}
    work = await client.get(TASKS, params={"view": "work", "limit": 200}, headers=world.b.headers)
    assert _titles(work) == {"work_alice", "work_bob", "work_free"}


async def test_view_mine_is_personal_plus_work_assigned_to_my_alias(
    client: httpx.AsyncClient, world: World
) -> None:
    a = await client.get(TASKS, params={"view": "mine", "limit": 200}, headers=world.a.headers)
    assert _titles(a) == {"personal_a", "work_alice"}
    b = await client.get(TASKS, params={"view": "mine", "limit": 200}, headers=world.b.headers)
    assert _titles(b) == {"personal_b", "work_bob"}


async def test_owner_param_cannot_change_whose_tasks_are_mine(
    client: httpx.AsyncClient, world: World
) -> None:
    for path in (f"{TASKS}/agenda", TASKS, f"{TASKS}/stats"):
        plain = await client.get(path, params={"view": "mine"}, headers=world.a.headers)
        spoof = await client.get(
            path, params={"view": "mine", "owner": ["Bob"]}, headers=world.a.headers
        )
        assert plain.json() == spoof.json(), path


# ═══════════════════════════════════════════════════════════════════════
#  IDOR: mọi endpoint có {task_id}
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("who", ["b", "admin", "lead"])
async def test_every_task_endpoint_returns_404_for_someone_elses_personal(
    client: httpx.AsyncClient, world: World, who: str
) -> None:
    caller = getattr(world, who)
    url = f"{TASKS}/{world.ids['personal_a']}"
    h = caller.headers
    responses = {
        "get": await client.get(url, headers=h),
        "patch": await client.patch(url, json={"title": "chiếm"}, headers=h),
        "delete": await client.delete(url, headers=h),
        "delete_permanent": await client.delete(url, params={"permanent": "true"}, headers=h),
        "restore": await client.post(f"{url}/restore", headers=h),
        "complete": await client.post(f"{url}/complete", headers=h),
        "time": await client.post(f"{url}/time", json={"minutes": 5}, headers=h),
    }
    for name, resp in responses.items():
        assert resp.status_code == 404, (name, resp.status_code, resp.text)
    # Không có gì thay đổi với chủ.
    mine = await client.get(url, headers=world.a.headers)
    assert mine.status_code == 200
    assert mine.json()["title"] == "personal_a"
    assert mine.json()["status"] == "todo"
    assert mine.json()["spent_minutes"] == 0


async def test_404_for_hidden_task_is_identical_to_404_for_missing_task(
    client: httpx.AsyncClient, world: World
) -> None:
    import uuid

    hidden = await client.get(f"{TASKS}/{world.ids['personal_a']}", headers=world.b.headers)
    missing = await client.get(f"{TASKS}/{uuid.uuid4()}", headers=world.b.headers)
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json().keys() == missing.json().keys()


async def test_restore_of_trashed_personal_is_owner_only(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{TASKS}/{world.ids['personal_a']}"
    assert (await client.delete(url, headers=world.a.headers)).status_code == 204
    assert (await client.post(f"{url}/restore", headers=world.b.headers)).status_code == 404
    assert (await client.post(f"{url}/restore", headers=world.admin.headers)).status_code == 404
    assert (await client.post(f"{url}/restore", headers=world.a.headers)).status_code == 200


# ═══════════════════════════════════════════════════════════════════════
#  Quyền ghi trên task work
# ═══════════════════════════════════════════════════════════════════════


async def test_member_edits_only_tasks_assigned_to_own_alias(
    client: httpx.AsyncClient, world: World
) -> None:
    bob_task = f"{TASKS}/{world.ids['work_bob']}"
    denied = await client.patch(bob_task, json={"title": "x"}, headers=world.a.headers)
    assert denied.status_code == 403 and denied.json()["code"] == "forbidden"
    own = await client.patch(
        f"{TASKS}/{world.ids['work_alice']}",
        json={"status": "in_progress"},
        headers=world.a.headers,
    )
    assert own.status_code == 200
    # Lead sửa được task của người khác.
    lead = await client.patch(bob_task, json={"title": "lead sửa"}, headers=world.lead.headers)
    assert lead.status_code == 200 and lead.json()["title"] == "lead sửa"


async def test_member_cannot_delete_synced_work_even_if_assigned(
    client: httpx.AsyncClient, world: World
) -> None:
    free = f"{TASKS}/{world.ids['work_free']}"
    alice = f"{TASKS}/{world.ids['work_alice']}"
    assert (await client.delete(free, headers=world.a.headers)).status_code == 403
    assert (await client.delete(alice, headers=world.a.headers)).status_code == 403
    assert (await client.delete(free, headers=world.lead.headers)).status_code == 204


async def test_synced_work_task_cannot_become_personal(
    client: httpx.AsyncClient, world: World
) -> None:
    resp = await client.patch(
        f"{TASKS}/{world.ids['work_alice']}", json={"scope": "personal"}, headers=world.a.headers
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "shared_task_cannot_be_personal"
    # Lead cũng không: quy tắc theo task, không theo người.
    resp = await client.patch(
        f"{TASKS}/{world.ids['work_alice']}", json={"scope": "personal"}, headers=world.lead.headers
    )
    assert resp.status_code == 409


async def test_member_owns_and_manages_a_manual_work_task(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await client.post(
        TASKS, json={"title": "việc nhóm tự tạo", "scope": "work"}, headers=world.a.headers
    )
    assert created.status_code == 201
    body = created.json()
    assert body["owner_id"] == str(world.a.id)
    assert body["can_edit"] is True and body["can_delete"] is True
    url = f"{TASKS}/{body['id']}"
    # Người khác thấy nhưng không sửa/xoá được.
    assert (await client.get(url, headers=world.b.headers)).status_code == 200
    assert (
        await client.patch(url, json={"title": "x"}, headers=world.b.headers)
    ).status_code == 403
    assert (await client.delete(url, headers=world.b.headers)).status_code == 403
    # Chủ chuyển thành cá nhân: task biến mất khỏi mắt người khác.
    personal = await client.patch(url, json={"scope": "personal"}, headers=world.a.headers)
    assert personal.status_code == 200
    assert (await client.get(url, headers=world.b.headers)).status_code == 404


async def test_assignee_cannot_hijack_manual_work_task_into_personal(
    client: httpx.AsyncClient, world: World
) -> None:
    """Người được giao sửa được task, nhưng không được giấu nó khỏi người tạo và cả team."""
    created = await client.post(
        TASKS,
        json={"title": "việc lead giao", "scope": "work", "assignee": "Alice"},
        headers=world.lead.headers,
    )
    assert created.status_code == 201, created.text
    url = f"{TASKS}/{created.json()['id']}"
    assert (
        await client.patch(url, json={"title": "đổi tên"}, headers=world.a.headers)
    ).status_code == 200
    resp = await client.patch(url, json={"scope": "personal"}, headers=world.a.headers)
    assert resp.status_code == 403
    # Task vẫn là work của lead, người khác vẫn thấy.
    assert (await client.get(url, headers=world.lead.headers)).json()["scope"] == "work"
    assert (await client.get(url, headers=world.b.headers)).status_code == 200


async def test_personal_can_be_shared_by_owner_and_keeps_owner(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{TASKS}/{world.ids['personal_a']}"
    shared = await client.patch(url, json={"scope": "work"}, headers=world.a.headers)
    assert shared.status_code == 200 and shared.json()["owner_id"] == str(world.a.id)
    assert (await client.get(url, headers=world.b.headers)).status_code == 200
    # Vẫn chỉ chủ (task tự tạo) sửa được; B chỉ đọc.
    assert (
        await client.patch(url, json={"title": "x"}, headers=world.b.headers)
    ).status_code == 403


async def test_can_edit_and_can_delete_flags_match_enforcement(
    client: httpx.AsyncClient, world: World
) -> None:
    items = (await client.get(TASKS, params={"limit": 200}, headers=world.a.headers)).json()[
        "items"
    ]
    flags = {i["title"]: (i["can_edit"], i["can_delete"]) for i in items}
    assert flags == {
        "personal_a": (True, True),
        "work_alice": (True, False),
        "work_bob": (False, False),
        "work_free": (False, False),
    }
    lead_items = (
        await client.get(TASKS, params={"view": "work", "limit": 200}, headers=world.lead.headers)
    ).json()["items"]
    assert all(i["can_edit"] and i["can_delete"] for i in lead_items)


async def test_client_cannot_choose_the_owner_on_create(
    client: httpx.AsyncClient, world: World
) -> None:
    resp = await client.post(
        TASKS,
        json={"title": "đẩy sang B", "owner_id": str(world.b.id)},
        headers=world.a.headers,
    )
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == str(world.a.id)
    assert "đẩy sang B" not in _titles(
        await client.get(TASKS, params={"limit": 200}, headers=world.b.headers)
    )


async def test_patch_cannot_change_the_owner(client: httpx.AsyncClient, world: World) -> None:
    url = f"{TASKS}/{world.ids['personal_a']}"
    resp = await client.patch(url, json={"owner_id": str(world.b.id)}, headers=world.a.headers)
    assert resp.status_code == 200
    assert resp.json()["owner_id"] == str(world.a.id)
    assert (await client.get(url, headers=world.b.headers)).status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  Thống kê, thùng rác
# ═══════════════════════════════════════════════════════════════════════


async def test_stats_trash_and_minutes_are_per_user(
    client: httpx.AsyncClient, world: World
) -> None:
    # A xoá task cá nhân của mình, ghi 10 phút; B ghi 7 phút vào task work được giao.
    assert (
        await client.delete(f"{TASKS}/{world.ids['personal_a']}", headers=world.a.headers)
    ).status_code == 204
    t_alice = f"{TASKS}/{world.ids['work_alice']}/time"
    assert (
        await client.post(t_alice, json={"minutes": 10}, headers=world.a.headers)
    ).status_code == 200
    t_bob = f"{TASKS}/{world.ids['work_bob']}/time"
    assert (
        await client.post(t_bob, json={"minutes": 7}, headers=world.b.headers)
    ).status_code == 200

    stats_a = (await client.get(f"{TASKS}/stats", headers=world.a.headers)).json()
    stats_b = (await client.get(f"{TASKS}/stats", headers=world.b.headers)).json()
    assert (stats_a["trash_total"], stats_a["minutes_logged_today"]) == (1, 10)
    assert (stats_b["trash_total"], stats_b["minutes_logged_today"]) == (0, 7)


async def test_trash_and_empty_trash_only_touch_visible_deletable_tasks(
    client: httpx.AsyncClient, world: World
) -> None:
    for name, who in (("personal_a", world.a), ("personal_b", world.b)):
        resp = await client.delete(f"{TASKS}/{world.ids[name]}", headers=who.headers)
        assert resp.status_code == 204
    # Task work: A không xoá được; lead xoá một cái.
    assert (
        await client.delete(f"{TASKS}/{world.ids['work_free']}", headers=world.lead.headers)
    ).status_code == 204

    trash_a = (await client.get(f"{TASKS}/trash", headers=world.a.headers)).json()
    assert {i["title"] for i in trash_a["items"]} == {"personal_a", "work_free"}

    # A dọn thùng rác: chỉ xoá được personal_a; work_free (A không có quyền xoá) còn nguyên.
    emptied = await client.post(f"{TASKS}/trash/empty", headers=world.a.headers)
    assert emptied.status_code == 200 and emptied.json()["purged"] == 1
    trash_b = (await client.get(f"{TASKS}/trash", headers=world.b.headers)).json()
    assert {i["title"] for i in trash_b["items"]} == {"personal_b", "work_free"}


# ═══════════════════════════════════════════════════════════════════════
#  Note
# ═══════════════════════════════════════════════════════════════════════


async def test_notes_are_private_to_the_owner_even_from_admin(
    client: httpx.AsyncClient, world: World
) -> None:
    url = f"{NOTES}/{world.note_a}"
    for who in (world.b, world.lead, world.admin):
        h = who.headers
        responses = {
            "get": await client.get(url, headers=h),
            "patch": await client.patch(url, json={"title": "x"}, headers=h),
            "delete": await client.delete(url, headers=h),
            "purge": await client.delete(url, params={"permanent": "true"}, headers=h),
            "restore": await client.post(f"{url}/restore", headers=h),
            "archive": await client.post(f"{url}/archive", headers=h),
            "unarchive": await client.post(f"{url}/unarchive", headers=h),
            "use": await client.post(f"{url}/use", headers=h),
        }
        for name, resp in responses.items():
            assert resp.status_code == 404, (who.email, name, resp.status_code)
        listing = await client.get(NOTES, headers=h)
        assert listing.json()["total"] == 0
        stats = await client.get(f"{NOTES}/stats", headers=h)
        assert sum(stats.json().values()) == 0
    assert (await client.get(url, headers=world.a.headers)).status_code == 200
    stats_a = await client.get(f"{NOTES}/stats", headers=world.a.headers)
    assert sum(stats_a.json().values()) == 1


async def test_note_trash_and_empty_are_per_user(client: httpx.AsyncClient, world: World) -> None:
    url = f"{NOTES}/{world.note_a}"
    assert (await client.delete(url, headers=world.a.headers)).status_code == 204
    other = await client.post(
        NOTES, json={"title": "n_b", "kind": "text", "content": "c"}, headers=world.b.headers
    )
    assert (
        await client.delete(f"{NOTES}/{other.json()['id']}", headers=world.b.headers)
    ).status_code == 204

    assert (await client.get(f"{NOTES}/trash", headers=world.b.headers)).json()["total"] == 1
    emptied = await client.post(f"{NOTES}/trash/empty", headers=world.b.headers)
    assert emptied.json()["purged"] == 1
    # Note của A vẫn còn trong thùng rác của A.
    assert (await client.get(f"{NOTES}/trash", headers=world.a.headers)).json()["total"] == 1


async def test_client_cannot_choose_note_owner(client: httpx.AsyncClient, world: World) -> None:
    resp = await client.post(
        NOTES,
        json={"title": "n", "kind": "text", "content": "c", "owner_id": str(world.b.id)},
        headers=world.a.headers,
    )
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == str(world.a.id)
    assert (
        await client.get(f"{NOTES}/{resp.json()['id']}", headers=world.b.headers)
    ).status_code == 404


# ═══════════════════════════════════════════════════════════════════════
#  Ma trận quyền theo endpoint (spec 3.4)
# ═══════════════════════════════════════════════════════════════════════


async def test_member_is_denied_team_integration_import_and_system_endpoints(
    client: httpx.AsyncClient, world: World
) -> None:
    h = world.a.headers
    denied = {
        "participation": await client.get(f"{TASKS}/participation", headers=h),
        "assignees": await client.get(f"{TASKS}/assignees", headers=h),
        "system": await client.get("/api/v1/system/info", headers=h),
        "import": await client.post(
            "/api/v1/import/datafile",
            content=b"{}",
            headers={**h, "Content-Type": "application/json"},
        ),
        "integrations_list": await client.get("/api/v1/integrations", headers=h),
        "integrations_create": await client.post("/api/v1/integrations", json={}, headers=h),
        "sync": await client.post(
            "/api/v1/integrations/00000000-0000-0000-0000-000000000000/sync", headers=h
        ),
        "upsert": await client.post(
            f"{TASKS}/upsert-batch", json={"source": "jira", "items": []}, headers=h
        ),
        "sync_urls_get": await client.get("/api/v1/settings/sync-urls", headers=h),
        "sync_urls_put": await client.put(
            "/api/v1/settings/sync-urls", json={"urls": []}, headers=h
        ),
    }
    for name, resp in denied.items():
        assert resp.status_code == 403, (name, resp.status_code, resp.text)
        assert resp.json()["code"] == "forbidden"


async def test_lead_gets_team_and_sync_but_not_admin_endpoints(
    client: httpx.AsyncClient, world: World
) -> None:
    h = world.lead.headers
    assert (await client.get(f"{TASKS}/participation", headers=h)).status_code == 200
    assert (await client.get(f"{TASKS}/assignees", headers=h)).status_code == 200
    assert (await client.get("/api/v1/integrations", headers=h)).status_code == 200
    # Có quyền sync: kết nối không tồn tại thì 404 (đã qua cổng quyền).
    nope = await client.post(
        "/api/v1/integrations/00000000-0000-0000-0000-000000000000/sync", headers=h
    )
    assert nope.status_code == 404
    assert (await client.post("/api/v1/integrations", json={}, headers=h)).status_code == 403
    assert (await client.get("/api/v1/system/info", headers=h)).status_code == 403
    assert (
        await client.post("/api/v1/import/datafile", content=b"{}", headers=h)
    ).status_code == 403
    assert (await client.get("/api/v1/settings/sync-urls", headers=h)).status_code == 403


async def test_admin_gets_everything_in_the_matrix(client: httpx.AsyncClient, world: World) -> None:
    h = world.admin.headers
    assert (await client.get("/api/v1/system/info", headers=h)).status_code == 200
    assert (await client.get("/api/v1/integrations", headers=h)).status_code == 200
    assert (await client.get("/api/v1/settings/sync-urls", headers=h)).status_code == 200
    assert (await client.get(f"{TASKS}/participation", headers=h)).status_code == 200


# ═══════════════════════════════════════════════════════════════════════
#  Project dùng chung, sửa theo chủ
# ═══════════════════════════════════════════════════════════════════════


async def test_projects_are_shared_but_modified_by_owner_or_lead(
    client: httpx.AsyncClient, world: World
) -> None:
    created = await client.post(
        "/api/v1/projects", json={"key": "SHARED", "name": "Chung"}, headers=world.a.headers
    )
    assert created.status_code == 201
    assert created.json()["owner_id"] == str(world.a.id) and created.json()["can_edit"] is True
    url = f"/api/v1/projects/{created.json()['id']}"

    seen_by_b = await client.get(url, headers=world.b.headers)
    assert seen_by_b.status_code == 200 and seen_by_b.json()["can_edit"] is False
    assert (await client.patch(url, json={"name": "x"}, headers=world.b.headers)).status_code == 403
    assert (await client.delete(url, headers=world.b.headers)).status_code == 403
    assert (
        await client.patch(url, json={"name": "lead"}, headers=world.lead.headers)
    ).status_code == 200
    assert (
        await client.patch(url, json={"name": "chủ"}, headers=world.a.headers)
    ).status_code == 200
    listed = await client.get("/api/v1/projects", headers=world.b.headers)
    assert [p["key"] for p in listed.json()] == ["SHARED"]
    assert (await client.delete(url, headers=world.a.headers)).status_code == 204


# ═══════════════════════════════════════════════════════════════════════
#  Import: không chạm dữ liệu riêng của người khác
# ═══════════════════════════════════════════════════════════════════════


async def test_import_never_overwrites_another_users_note_or_personal_task(
    client: httpx.AsyncClient, world: World
) -> None:
    payload = {
        "schema_version": 7,
        "projects": [],
        "tasks": [
            {
                "id": world.ids["personal_a"],
                "title": "bị ghi đè?",
                "source": "manual",
                "scope": "personal",
            }
        ],
        "notes": [
            {"id": world.note_a, "title": "bị ghi đè?", "kind": "text", "content": "đã thay"}
        ],
    }
    # Admin nhập (có quyền data:import) với include_personal bật: dữ liệu riêng của A vẫn an toàn.
    resp = await client.post(
        "/api/v1/import/datafile",
        params={"include_personal": "true"},
        json=payload,
        headers=world.admin.headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["counts"]["tasks"]["replaced"] == 0
    assert body["counts"]["notes"]["replaced"] == 0
    assert {i["code"] for i in body["issues"]} >= {"skipped_other_owner"}
    # Báo cáo không lộ tiêu đề/nội dung của A.
    assert "personal_a" not in resp.text and "bí mật của A" not in resp.text
    assert (await client.get(f"{TASKS}/{world.ids['personal_a']}", headers=world.a.headers)).json()[
        "title"
    ] == "personal_a"
    assert (await client.get(f"{NOTES}/{world.note_a}", headers=world.a.headers)).json()[
        "content"
    ] == "bí mật của A"
