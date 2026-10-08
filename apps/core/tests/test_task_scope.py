"""Epic task-scope: cột `tasks.scope`, tham số `view`/`owner`, migration và CHECK.

Dữ liệu thật của User không bao giờ được dùng ở đây; mọi task đều tổng hợp.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.enums import TaskScope, TaskSource, default_scope_for
from app.services.clock import local_today

pytestmark = pytest.mark.db

ROOT = Path(__file__).resolve().parents[1]


# ═══════════════════════════════════════════════════════════════════════
#  Quy tắc suy scope (thuần, không cần DB)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (TaskSource.JIRA, TaskScope.WORK),
        (TaskSource.GITHUB, TaskScope.WORK),
        (TaskSource.GITLAB, TaskScope.WORK),
        (TaskSource.MANUAL, TaskScope.PERSONAL),
        (TaskSource.CALENDAR, TaskScope.PERSONAL),
        (TaskSource.EMAIL, TaskScope.PERSONAL),
        (TaskSource.OBSIDIAN, TaskScope.PERSONAL),
        (TaskSource.AGENT, TaskScope.PERSONAL),
    ],
)
def test_default_scope_for_covers_every_source(source: TaskSource, expected: TaskScope) -> None:
    assert default_scope_for(source) is expected


def test_every_task_source_has_a_default_scope() -> None:
    # Thêm nguồn mới vào TaskSource mà quên cân nhắc scope sẽ không rơi khỏi test này
    # âm thầm: default_scope_for phải trả về một giá trị hợp lệ cho mọi nguồn.
    for source in TaskSource:
        assert default_scope_for(source) in set(TaskScope)


# ═══════════════════════════════════════════════════════════════════════
#  Mặc định khi tạo, PATCH
# ═══════════════════════════════════════════════════════════════════════


async def _create(client: httpx.AsyncClient, **payload: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/tasks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"title": "t"}, "personal"),
        ({"title": "t", "source": "manual"}, "personal"),
        ({"title": "t", "source": "jira", "external_id": "X-1"}, "work"),
        ({"title": "t", "source": "github", "external_id": "7"}, "work"),
        ({"title": "t", "source": "calendar"}, "personal"),
        ({"title": "t", "source": "manual", "scope": "work"}, "work"),
        ({"title": "t", "source": "jira", "external_id": "X-2", "scope": "personal"}, "personal"),
    ],
)
async def test_create_derives_scope_from_source(
    client: httpx.AsyncClient, payload: dict[str, Any], expected: str
) -> None:
    task = await _create(client, **payload)
    assert task["scope"] == expected
    created = task["events"][-1]
    assert created["event_type"] == "created"
    assert created["payload"]["scope"] == expected


async def test_create_rejects_unknown_scope(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/tasks", json={"title": "t", "scope": "team"})
    assert resp.status_code == 422


async def test_orm_insert_without_scope_falls_back_to_personal(session: AsyncSession) -> None:
    """Quên đặt scope thì DB rơi về 'personal': task không bị đồng bộ ghi đè."""
    from app.models.task import Task

    task = Task(title="quen scope")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    assert task.scope is TaskScope.PERSONAL


async def test_patch_scope_records_event(client: httpx.AsyncClient) -> None:
    task = await _create(client, title="t", source="jira", external_id="X-1")
    assert task["scope"] == "work"

    resp = await client.patch(f"/api/v1/tasks/{task['id']}", json={"scope": "personal"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "personal"
    updated = [e for e in body["events"] if e["event_type"] == "updated"]
    assert len(updated) == 1
    assert updated[0]["payload"]["changes"]["scope"] == {"from": "work", "to": "personal"}


async def test_patch_scope_invalid_values_are_422(client: httpx.AsyncClient) -> None:
    task = await _create(client, title="t")
    url = f"/api/v1/tasks/{task['id']}"
    assert (await client.patch(url, json={"scope": None})).status_code == 422
    assert (await client.patch(url, json={"scope": "team"})).status_code == 422
    # Không đổi gì sau các lần bị từ chối.
    assert (await client.get(url)).json()["scope"] == "personal"


async def test_patch_without_scope_keeps_it(client: httpx.AsyncClient) -> None:
    task = await _create(client, title="t", scope="work")
    resp = await client.patch(f"/api/v1/tasks/{task['id']}", json={"title": "moi"})
    assert resp.status_code == 200
    assert resp.json()["scope"] == "work"


async def test_restore_keeps_scope(client: httpx.AsyncClient) -> None:
    task = await _create(client, title="t", scope="work")
    assert (await client.delete(f"/api/v1/tasks/{task['id']}")).status_code == 204
    restored = await client.post(f"/api/v1/tasks/{task['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["scope"] == "work"


# ═══════════════════════════════════════════════════════════════════════
#  view / owner
# ═══════════════════════════════════════════════════════════════════════


async def _dataset(client: httpx.AsyncClient) -> dict[str, str]:
    """Sáu task theo spec 6.1 (một task personal nằm trong thùng rác). Trả tên -> id."""
    today = local_today().isoformat()
    spec: dict[str, dict[str, Any]] = {
        "personal": {"title": "p", "source": "manual"},
        "work_a": {"title": "wa", "source": "jira", "external_id": "J-1", "assignee": "A"},
        "work_b": {"title": "wb", "source": "jira", "external_id": "J-2", "assignee": "B"},
        "work_free_ext": {"title": "wfe", "source": "jira", "external_id": "J-3"},
        "work_free_own": {"title": "wfo", "source": "manual", "scope": "work"},
        "trashed": {"title": "tr", "source": "manual"},
    }
    ids: dict[str, str] = {}
    for name, payload in spec.items():
        created = await _create(client, scheduled_for=today, **payload)
        ids[name] = created["id"]
    assert (await client.delete(f"/api/v1/tasks/{ids['trashed']}")).status_code == 204
    # Ghi giờ ở hai task thuộc hai scope khác nhau để kiểm minutes_logged_today.
    assert (
        await client.post(f"/api/v1/tasks/{ids['work_b']}/time", json={"minutes": 10})
    ).status_code == 200
    assert (
        await client.post(f"/api/v1/tasks/{ids['personal']}/time", json={"minutes": 5})
    ).status_code == 200
    return ids


def _titles(page: dict[str, Any]) -> set[str]:
    return {item["title"] for item in page["items"]}


async def _list(client: httpx.AsyncClient, **params: Any) -> httpx.Response:
    return await client.get("/api/v1/tasks", params={"limit": 200, **params})


async def test_view_mine_with_owner(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    page = (await _list(client, view="mine", owner="A")).json()
    assert _titles(page) == {"p", "wa", "wfo"}
    assert page["total"] == 3


async def test_view_mine_without_owner(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    page = (await _list(client, view="mine")).json()
    assert _titles(page) == {"p", "wfo"}


async def test_view_mine_owner_match_is_exact(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    page = (await _list(client, view="mine", owner="a")).json()
    assert _titles(page) == {"p", "wfo"}
    page = (await _list(client, view="mine", owner=["A", "B"])).json()
    assert _titles(page) == {"p", "wa", "wb", "wfo"}


async def test_view_work_personal_all(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    assert _titles((await _list(client, view="work")).json()) == {"wa", "wb", "wfe", "wfo"}
    assert _titles((await _list(client, view="personal")).json()) == {"p"}
    everything = (await _list(client, view="all")).json()
    default = (await _list(client)).json()
    assert everything == default
    assert _titles(default) == {"p", "wa", "wb", "wfe", "wfo"}


async def test_view_combines_with_other_filters(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    page = (await _list(client, view="work", assignee="B")).json()
    assert _titles(page) == {"wb"}


async def test_agenda_respects_view(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    # /agenda?view=... không bị /{task_id} nuốt (route tĩnh khai báo trước).
    resp = await client.get("/api/v1/tasks/agenda", params={"view": "mine", "owner": "A"})
    assert resp.status_code == 200
    got = {t["title"] for t in resp.json()["scheduled_today"]}
    assert got == {"p", "wa", "wfo"}

    unfiltered = await client.get("/api/v1/tasks/agenda")
    assert {t["title"] for t in unfiltered.json()["scheduled_today"]} == {
        "p",
        "wa",
        "wb",
        "wfe",
        "wfo",
    }
    work = await client.get("/api/v1/tasks/agenda", params={"view": "work"})
    assert {t["title"] for t in work.json()["scheduled_today"]} == {"wa", "wb", "wfe", "wfo"}


async def test_agenda_filters_in_progress_group_too(client: httpx.AsyncClient) -> None:
    ids = await _dataset(client)
    for name in ("work_b", "personal"):
        resp = await client.patch(f"/api/v1/tasks/{ids[name]}", json={"status": "in_progress"})
        assert resp.status_code == 200
    body = (await client.get("/api/v1/tasks/agenda", params={"view": "personal"})).json()
    assert [t["title"] for t in body["in_progress"]] == ["p"]


async def test_stats_respects_view_but_not_trash_or_minutes(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    full = (await client.get("/api/v1/tasks/stats")).json()
    mine = (await client.get("/api/v1/tasks/stats", params={"view": "mine", "owner": "A"})).json()
    personal = (await client.get("/api/v1/tasks/stats", params={"view": "personal"})).json()
    work = (await client.get("/api/v1/tasks/stats", params={"view": "work"})).json()
    explicit_all = (await client.get("/api/v1/tasks/stats", params={"view": "all"})).json()

    assert mine["open_total"] == 3
    assert sum(mine["by_status"].values()) == 3
    assert personal["open_total"] == 1
    assert work["open_total"] == 4
    assert full["open_total"] == 5
    assert explicit_all == full
    for body in (full, mine, personal, work):
        assert body["trash_total"] == 1
        assert body["minutes_logged_today"] == 15


@pytest.mark.parametrize(
    "params",
    [
        {"view": "work", "owner": "A"},
        {"view": "all", "owner": "A"},
        {"owner": "A"},
        {"view": "mine", "owner": [f"n{i}" for i in range(21)]},
        {"view": "mine", "owner": ""},
        {"view": "mine", "owner": "   "},
        {"view": "mine", "owner": "x" * 201},
        {"view": "xyz"},
    ],
)
@pytest.mark.parametrize("path", ["/api/v1/tasks", "/api/v1/tasks/agenda", "/api/v1/tasks/stats"])
async def test_invalid_view_params_are_422(
    client: httpx.AsyncClient, path: str, params: dict[str, Any]
) -> None:
    resp = await client.get(path, params=params)
    assert resp.status_code == 422, resp.text


async def test_owner_boundaries_are_accepted(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/tasks", params={"view": "mine", "owner": [f"n{i}" for i in range(20)]}
    )
    assert resp.status_code == 200
    resp = await client.get("/api/v1/tasks", params={"view": "mine", "owner": "x" * 200})
    assert resp.status_code == 200


async def test_owner_is_bound_not_interpolated(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    resp = await _list(client, view="mine", owner="A') OR 1=1 --")
    assert resp.status_code == 200
    assert _titles(resp.json()) == {"p", "wfo"}


# ═══════════════════════════════════════════════════════════════════════
#  Migration và CHECK
# ═══════════════════════════════════════════════════════════════════════


async def test_check_constraint_rejects_unknown_scope(session: AsyncSession) -> None:
    """`alembic check` không so CHECK, nên phải thử INSERT trực tiếp."""
    with pytest.raises(IntegrityError) as exc:
        await session.execute(
            text("INSERT INTO tasks (id, title, scope) VALUES (:i, 'x', 'team')"),
            {"i": uuid.uuid4()},
        )
    assert "ck_tasks_scope_valid" in str(exc.value)
    await session.rollback()


def _alembic(action: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    getattr(command, action)(cfg, revision)


async def _sql(url: str, statements: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    """Chạy SQL bằng engine riêng: test migration chạy alembic (asyncio.run) nên không
    dùng chung engine toàn cục gắn với event loop khác."""
    engine = create_async_engine(url)
    out: list[Any] = []
    try:
        async with engine.begin() as conn:
            for sql, params in statements:
                result = await conn.execute(text(sql), params)
                out.append(result.fetchall() if result.returns_rows else None)
    finally:
        await engine.dispose()
    return out


def test_migration_backfills_by_source_and_round_trips(migrated_db: None) -> None:
    """Dữ liệu có sẵn ở e5f1a3b7c9d2: jira -> work, manual -> personal, updated_at nguyên."""
    url = os.environ["TEST_DATABASE_URL"]
    jira_id, manual_id = uuid.uuid4(), uuid.uuid4()
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    try:
        _alembic("downgrade", "e5f1a3b7c9d2")
        cols = asyncio.run(
            _sql(
                url,
                [
                    (
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'tasks' AND column_name = 'scope'",
                        {},
                    )
                ],
            )
        )[0]
        assert cols == []

        insert = (
            "INSERT INTO tasks (id, title, source, external_id, created_at, updated_at) "
            "VALUES (:i, 'x', :s, :e, :t, :t)"
        )
        asyncio.run(
            _sql(
                url,
                [
                    (insert, {"i": jira_id, "s": "jira", "e": "M-1", "t": stamp}),
                    (insert, {"i": manual_id, "s": "manual", "e": None, "t": stamp}),
                ],
            )
        )

        _alembic("upgrade", "head")
        rows = asyncio.run(
            _sql(
                url,
                [
                    (
                        "SELECT id, scope, updated_at FROM tasks WHERE id IN (:a, :b)",
                        {"a": jira_id, "b": manual_id},
                    )
                ],
            )
        )[0]
        by_id = {r[0]: r for r in rows}
        assert by_id[jira_id][1] == "work"
        assert by_id[manual_id][1] == "personal"
        # Backfill là phân loại lại dữ liệu cũ, không phải User sửa task.
        assert by_id[jira_id][2] == stamp
        assert by_id[manual_id][2] == stamp

        with pytest.raises(IntegrityError, match="ck_tasks_scope_valid"):
            asyncio.run(
                _sql(
                    url,
                    [
                        (
                            "INSERT INTO tasks (id, title, scope) VALUES (:i, 'x', 'team')",
                            {"i": uuid.uuid4()},
                        )
                    ],
                )
            )

        _alembic("downgrade", "e5f1a3b7c9d2")
        left = asyncio.run(
            _sql(
                url, [("SELECT id FROM tasks WHERE id IN (:a, :b)", {"a": jira_id, "b": manual_id})]
            )
        )[0]
        assert {r[0] for r in left} == {jira_id, manual_id}
    finally:
        # Luôn đưa schema về head để các test sau không gãy; dữ liệu do conftest TRUNCATE.
        _alembic("upgrade", "head")
        asyncio.run(_sql(url, [("TRUNCATE tasks CASCADE", {})]))


# ═══════════════════════════════════════════════════════════════════════
#  Chuẩn hoá assignee và phân trang ổn định (sau review)
# ═══════════════════════════════════════════════════════════════════════


async def test_assignee_is_stripped_and_blank_becomes_null(client: httpx.AsyncClient) -> None:
    padded = await _create(client, title="t1", assignee="  Hung ")
    blank = await _create(client, title="t2", assignee="")
    spaces = await _create(client, title="t3", assignee="   ")
    assert padded["assignee"] == "Hung"
    assert blank["assignee"] is None
    assert spaces["assignee"] is None

    # PATCH: truyền ' ' xoá, không truyền thì giữ nguyên.
    resp = await client.patch(f"/api/v1/tasks/{padded['id']}", json={"title": "moi"})
    assert resp.json()["assignee"] == "Hung"
    resp = await client.patch(f"/api/v1/tasks/{padded['id']}", json={"assignee": " "})
    assert resp.json()["assignee"] is None
    resp = await client.patch(f"/api/v1/tasks/{blank['id']}", json={"assignee": " An "})
    assert resp.json()["assignee"] == "An"


async def test_assignee_too_long_is_422(client: httpx.AsyncClient) -> None:
    assert (
        await client.post("/api/v1/tasks", json={"title": "t", "assignee": "x" * 201})
    ).status_code == 422
    ok = await client.post("/api/v1/tasks", json={"title": "t", "assignee": "x" * 200})
    assert ok.status_code == 201
    resp = await client.patch(f"/api/v1/tasks/{ok.json()['id']}", json={"assignee": "x" * 201})
    assert resp.status_code == 422


async def test_view_mine_treats_blank_assignee_as_unassigned(client: httpx.AsyncClient) -> None:
    await _create(client, title="own", source="manual", scope="work", assignee="")
    page = (await _list(client, view="mine")).json()
    assert _titles(page) == {"own"}


async def test_pagination_is_stable_with_identical_created_at(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    ids = {(await _create(client, title=f"t{i}"))["id"] for i in range(7)}
    await session.execute(text("UPDATE tasks SET created_at = '2026-01-01T00:00:00+00:00'"))
    await session.commit()

    seen: list[str] = []
    for offset in range(0, 7, 3):
        page = (await _list(client, limit=3, offset=offset)).json()
        seen += [item["id"] for item in page["items"]]
    assert len(seen) == 7
    assert set(seen) == ids
