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
    assert (await client.get(f"{BASE}/stats", params={"archived": "abc"})).status_code == 422


async def test_archive_unknown_note_404(client: httpx.AsyncClient) -> None:
    missing = uuid.uuid4()
    assert (await client.post(f"{BASE}/{missing}/archive")).status_code == 404
    assert (await client.post(f"{BASE}/{missing}/unarchive")).status_code == 404
    assert (await client.post(f"{BASE}/not-a-uuid/archive")).status_code == 422


async def test_offset_has_upper_bound(client: httpx.AsyncClient) -> None:
    """offset không trần làm Postgres lỗi int64 và trả 500; giờ phải là 422."""
    resp = await client.get("/api/v1/notes", params={"offset": 2_000_000})
    assert resp.status_code == 422


async def test_archive_is_idempotent_over_http(client: httpx.AsyncClient) -> None:
    note_id = await _create(client)
    first = (await client.post(f"{BASE}/{note_id}/archive")).json()["archived_at"]
    again = await client.post(f"{BASE}/{note_id}/archive")
    assert again.status_code == 200
    assert again.json()["archived_at"] == first

    unarchived = await client.post(f"{BASE}/{note_id}/unarchive")
    assert unarchived.json()["archived_at"] is None
    assert (await client.post(f"{BASE}/{note_id}/unarchive")).status_code == 200


async def test_archive_and_unarchive_trashed_note_is_404(client: httpx.AsyncClient) -> None:
    note_id = await _create(client)
    assert (await client.delete(f"{BASE}/{note_id}")).status_code in (200, 204)

    assert (await client.post(f"{BASE}/{note_id}/archive")).status_code == 404
    assert (await client.post(f"{BASE}/{note_id}/unarchive")).status_code == 404


async def test_patch_archived_note_keeps_it_archived(client: httpx.AsyncClient) -> None:
    note_id = await _create(client)
    await client.post(f"{BASE}/{note_id}/archive")

    patched = await client.patch(f"{BASE}/{note_id}", json={"title": "đổi tên"})
    assert patched.status_code == 200
    assert patched.json()["title"] == "đổi tên"
    assert patched.json()["archived_at"] is not None
