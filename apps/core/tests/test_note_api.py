"""API lưu trữ note, gọi qua ASGI trên Postgres thật."""

from __future__ import annotations

import uuid

import httpx
import pytest

pytestmark = pytest.mark.db

BASE = "/api/v1/notes"


async def _create(client: httpx.AsyncClient, kind: str = "text") -> str:
    resp = await client.post(BASE, json={"title": "n", "kind": kind, "content": "c"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_archive_flow(client: httpx.AsyncClient) -> None:
    note_id = await _create(client)

    resp = await client.post(f"{BASE}/{note_id}/archive")
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None

    default = (await client.get(BASE)).json()
    assert note_id not in {n["id"] for n in default["items"]}
    archived = (await client.get(BASE, params={"archived": "true"})).json()
    assert note_id in {n["id"] for n in archived["items"]}

    stats = await client.get(f"{BASE}/stats", params={"archived": "true"})
    assert stats.status_code == 200
    assert stats.json() == {"text": 1}

    resp = await client.post(f"{BASE}/{note_id}/unarchive")
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is None
    default = (await client.get(BASE)).json()
    assert note_id in {n["id"] for n in default["items"]}


async def test_archived_param_validation(client: httpx.AsyncClient) -> None:
    assert (await client.get(BASE, params={"archived": "abc"})).status_code == 422
    assert (
        await client.get(f"{BASE}/stats", params={"archived": "abc"})
    ).status_code == 422


async def test_archive_unknown_note_404(client: httpx.AsyncClient) -> None:
    missing = uuid.uuid4()
    assert (await client.post(f"{BASE}/{missing}/archive")).status_code == 404
    assert (await client.post(f"{BASE}/{missing}/unarchive")).status_code == 404
    assert (await client.post(f"{BASE}/not-a-uuid/archive")).status_code == 422


async def test_offset_has_upper_bound(client: httpx.AsyncClient) -> None:
    """offset không trần làm Postgres lỗi int64 và trả 500; giờ phải là 422."""
    resp = await client.get("/api/v1/notes", params={"offset": 2_000_000})
    assert resp.status_code == 422
