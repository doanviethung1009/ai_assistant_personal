"""Thống kê `by_project`: tỉ lệ task đã xong theo project, dùng cho dải tóm tắt trang Task."""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.db


async def _project(client: httpx.AsyncClient, key: str, name: str) -> str:
    res = await client.post("/api/v1/projects", json={"key": key, "name": name})
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


async def _task(client: httpx.AsyncClient, title: str, project_id: str | None, status: str) -> None:
    body: dict[str, object] = {"title": title, "source": "manual", "status": status}
    if project_id:
        body["project_id"] = project_id
    res = await client.post("/api/v1/tasks", json=body)
    assert res.status_code == 201, res.text


async def test_by_project_percent_excludes_cancelled(client: httpx.AsyncClient) -> None:
    ops = await _project(client, "OPS", "Vận hành")
    web = await _project(client, "WEB", "Giao diện")
    # OPS: 1 xong + 3 đang mở + 1 huỷ -> 1/4 = 25% (huỷ không vào mẫu số)
    await _task(client, "o1", ops, "done")
    for i in range(3):
        await _task(client, f"o-open{i}", ops, "todo")
    await _task(client, "o-cancel", ops, "cancelled")
    # WEB: 2 xong -> 100%
    await _task(client, "w1", web, "done")
    await _task(client, "w2", web, "done")
    # Không project: 1 mở
    await _task(client, "free", None, "todo")

    body = (await client.get("/api/v1/tasks/stats", params={"view": "all"})).json()
    rows = {r["name"]: r for r in body["by_project"]}
    assert rows["Vận hành"]["total"] == 4 and rows["Vận hành"]["done"] == 1
    assert rows["Vận hành"]["open"] == 3 and rows["Vận hành"]["percent_done"] == 25
    assert rows["Giao diện"]["percent_done"] == 100 and rows["Giao diện"]["open"] == 0
    assert rows["Không có project"]["project_id"] is None
    assert rows["Không có project"]["percent_done"] == 0
    # Nhiều việc đang mở nhất lên trước.
    assert body["by_project"][0]["name"] == "Vận hành"


async def test_by_project_respects_view_and_ignores_trash(client: httpx.AsyncClient) -> None:
    pid = await _project(client, "OPS", "Vận hành")
    await _task(client, "keep", pid, "done")
    res = await client.post(
        "/api/v1/tasks", json={"title": "trash", "source": "manual", "project_id": pid}
    )
    assert (await client.delete(f"/api/v1/tasks/{res.json()['id']}")).status_code == 204

    body = (await client.get("/api/v1/tasks/stats", params={"view": "personal"})).json()
    assert [r["total"] for r in body["by_project"]] == [1]
    work = (await client.get("/api/v1/tasks/stats", params={"view": "work"})).json()
    assert work["by_project"] == []
