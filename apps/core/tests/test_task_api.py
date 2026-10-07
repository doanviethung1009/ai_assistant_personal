"""Task qua HTTP: bắt lỗi route nhận tham số nhưng không truyền xuống service."""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.db


async def test_assignee_query_param_filters_results(client: httpx.AsyncClient) -> None:
    for title, who in (("a1", "An"), ("b1", "Bình")):
        resp = await client.post("/api/v1/tasks", json={"title": title, "assignee": who})
        assert resp.status_code == 201

    body = (await client.get("/api/v1/tasks", params={"assignee": "An"})).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "a1"
