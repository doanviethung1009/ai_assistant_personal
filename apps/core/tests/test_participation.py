"""Dashboard tham dự dự án: % phần việc của từng người trong từng project (task công việc)."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import text

from app.db.session import SessionFactory
from app.services.clock import local_today

pytestmark = pytest.mark.db

URL = "/api/v1/tasks/participation"


async def _project(client: httpx.AsyncClient, key: str, name: str) -> str:
    res = await client.post("/api/v1/projects", json={"key": key, "name": name})
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


async def _task(
    client: httpx.AsyncClient,
    n: int,
    project_id: str | None,
    assignee: str | None,
    status: str = "todo",
    scope: str = "work",
) -> None:
    body: dict[str, object] = {
        "title": f"t{n}",
        "source": "manual",
        "scope": scope,
        "status": status,
    }
    if project_id:
        body["project_id"] = project_id
    if assignee:
        body["assignee"] = assignee
    res = await client.post("/api/v1/tasks", json=body)
    assert res.status_code == 201, res.text


async def _dataset(client: httpx.AsyncClient) -> None:
    ops = await _project(client, "OPS", "Vận hành")
    web = await _project(client, "WEB", "Giao diện")
    # OPS: An 3 (1 xong), Bình 1, chưa giao 1, An 1 huỷ (không tính) -> tổng 5
    rows = [("An", "done"), ("An", "todo"), ("An", "todo"), ("Bình", "todo"), (None, "todo")]
    for i, (who, st) in enumerate(rows):
        await _task(client, i, ops, who, st)
    await _task(client, 50, ops, "An", "cancelled")
    # WEB: Bình 2 -> tổng 2
    await _task(client, 60, web, "Bình")
    await _task(client, 61, web, "Bình")
    # Task cá nhân không bao giờ vào dashboard của nhóm.
    await _task(client, 70, ops, "An", scope="personal")


async def test_percent_uses_whole_project_as_denominator(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    body = (await client.get(URL)).json()
    projects = {p["name"]: p for p in body["projects"]}
    ops = projects["Vận hành"]
    assert ops["total"] == 5  # huỷ và cá nhân không tính
    # (count, done, open, percent): An có 1 xong + 2 chưa xong, task huỷ không tính.
    got = {m["assignee"]: (m["count"], m["done"], m["open"], m["percent"]) for m in ops["members"]}
    assert got == {
        "An": (3, 1, 2, 60),
        "Bình": (1, 0, 1, 20),
    }
    assert projects["Giao diện"]["members"] == [
        {"assignee": "Bình", "count": 2, "done": 0, "open": 2, "percent": 100}
    ]
    # Bằng nhau (3 và 3) thì xếp theo tên để thứ tự ổn định.
    assert [a["name"] for a in body["assignees"]] == ["An", "Bình"]
    assert {a["name"]: a["total"] for a in body["assignees"]} == {"An": 3, "Bình": 3}


async def test_selecting_people_keeps_percent_and_hides_others(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    body = (await client.get(URL, params={"person": ["Bình"]})).json()
    assert body["selected"] == ["Bình"]
    ops = next(p for p in body["projects"] if p["name"] == "Vận hành")
    # % vẫn trên tổng project (5), không phải trên tổng của người được chọn.
    assert ops["members"] == [
        {"assignee": "Bình", "count": 1, "done": 0, "open": 1, "percent": 20}
    ]
    # Danh sách chọn người vẫn đủ để dựng lại ô chọn.
    assert {a["name"] for a in body["assignees"]} == {"An", "Bình"}


async def test_unknown_person_yields_no_rows_not_error(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    res = await client.get(URL, params={"person": ["Không ai"]})
    assert res.status_code == 200
    assert res.json()["projects"] == []
    assert res.json()["selected"] == ["Không ai"]


@pytest.mark.parametrize("people", [[""], ["   "], ["x" * 201], [f"n{i}" for i in range(51)]])
async def test_invalid_person_is_422(client: httpx.AsyncClient, people: list[str]) -> None:
    assert (await client.get(URL, params={"person": people})).status_code == 422


async def test_empty_database_returns_empty_lists(client: httpx.AsyncClient) -> None:
    assert (await client.get(URL)).json() == {
        "assignees": [],
        "selected": [],
        "date_from": None,
        "date_to": None,
        "projects": [],
    }


# ═══════════════════════════════════════════════════════════════════════
#  Khoảng thời gian (ngày hoạt động: xong -> completed_at, còn lại -> updated_at)
# ═══════════════════════════════════════════════════════════════════════


async def _age(title: str, days: int) -> None:
    """Đẩy cả updated_at và completed_at của một task lùi `days` ngày (SQL thô, bỏ onupdate)."""
    async with SessionFactory() as s:
        await s.execute(
            text(
                "UPDATE tasks SET updated_at = now() - make_interval(days => :d), "
                "completed_at = CASE WHEN completed_at IS NULL THEN NULL "
                "ELSE now() - make_interval(days => :d) END WHERE title = :t"
            ),
            {"d": days, "t": title},
        )
        await s.commit()


async def test_period_including_today_matches_unfiltered(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    today = local_today()
    full = (await client.get(URL)).json()
    both = {"date_from": str(today), "date_to": str(today)}
    ranged = (await client.get(URL, params=both)).json()
    # date_to là ngày CUỐI gồm cả ngày đó: task tạo hôm nay vẫn nằm trong [hôm nay, hôm nay].
    assert ranged["projects"] == full["projects"]
    assert ranged["date_from"] == str(today) and ranged["date_to"] == str(today)


async def test_period_in_the_past_excludes_today(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    old = local_today() - timedelta(days=30)
    body = (
        await client.get(
            URL, params={"date_from": str(old - timedelta(days=5)), "date_to": str(old)}
        )
    ).json()
    assert body["projects"] == []
    # Ô chọn người không bị thu hẹp theo khoảng, để lựa chọn không biến mất khi đổi khoảng.
    assert {a["name"]: a["total"] for a in body["assignees"]} == {"An": 3, "Bình": 3}


async def test_period_shrinks_numerator_and_denominator(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    await _age("t0", 60)  # An, đã xong, trong OPS -> rời khỏi khoảng 30 ngày gần nhất
    today = local_today()
    body = (
        await client.get(
            URL, params={"date_from": str(today - timedelta(days=30)), "date_to": str(today)}
        )
    ).json()
    ops = next(p for p in body["projects"] if p["name"] == "Vận hành")
    assert ops["total"] == 4  # 5 - task t0 đã cũ
    an = next(m for m in ops["members"] if m["assignee"] == "An")
    assert (an["count"], an["done"], an["open"], an["percent"]) == (2, 0, 2, 50)


async def test_period_open_ended_and_inverted(client: httpx.AsyncClient) -> None:
    await _dataset(client)
    await _age("t0", 60)
    today = local_today()
    cut = str(today - timedelta(days=30))
    only_from = (await client.get(URL, params={"date_from": cut})).json()
    only_to = (await client.get(URL, params={"date_to": cut})).json()

    def total(body: dict) -> int:  # type: ignore[type-arg]
        return int(sum(p["total"] for p in body["projects"]))

    assert total(only_from) == 7 - 1  # task công việc chưa huỷ (7) trừ t0 đã cũ
    assert total(only_to) == 1  # chỉ t0
    inverted = {"date_from": str(today), "date_to": str(today - timedelta(days=1))}
    assert (await client.get(URL, params=inverted)).status_code == 422
