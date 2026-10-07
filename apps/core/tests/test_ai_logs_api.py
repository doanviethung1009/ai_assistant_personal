"""AI log qua HTTP: tạo, đọc, lọc, phân trang, lỗi."""

from __future__ import annotations

import uuid

import httpx
import pytest

pytestmark = pytest.mark.db


def _payload(category: str = "tool", prompt: str = "p") -> dict[str, str]:
    return {"category": category, "prompt": prompt, "handling": "h", "response": "r"}


async def test_create_and_get(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/ai-logs", json=_payload())
    assert created.status_code == 201
    body = created.json()
    assert body["category"] == "tool"

    fetched = await client.get(f"/api/v1/ai-logs/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["prompt"] == "p"


async def test_get_missing_is_404(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/ai-logs/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_invalid_category_is_422(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/ai-logs", json=_payload(category="khong-co"))
    assert resp.status_code == 422


async def test_list_filter_and_pagination(client: httpx.AsyncClient) -> None:
    for i in range(3):
        await client.post("/api/v1/ai-logs", json=_payload("web", f"w{i}"))
    await client.post("/api/v1/ai-logs", json=_payload("api", "a0"))

    page = (await client.get("/api/v1/ai-logs", params={"limit": 2})).json()
    assert page["total"] == 4
    assert len(page["items"]) == 2
    assert page["limit"] == 2

    only_web = (await client.get("/api/v1/ai-logs", params={"category": "web"})).json()
    assert only_web["total"] == 3
    assert {i["category"] for i in only_web["items"]} == {"web"}


async def test_list_is_newest_first_and_offset_skips(client: httpx.AsyncClient) -> None:
    for i in range(3):
        await client.post("/api/v1/ai-logs", json=_payload("api", f"p{i}"))

    first = (await client.get("/api/v1/ai-logs", params={"limit": 1})).json()["items"][0]
    assert first["prompt"] == "p2"  # mới nhất trước

    second = (await client.get("/api/v1/ai-logs", params={"limit": 1, "offset": 1})).json()
    assert second["items"][0]["prompt"] == "p1"
