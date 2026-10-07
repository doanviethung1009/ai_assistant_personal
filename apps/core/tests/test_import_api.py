"""Endpoint /api/v1/import/* qua HTTP: xác thực, validate body, giới hạn, mặc định an toàn."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.db.session import SessionFactory, engine

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).parent / "fixtures"
DATAFILE = (FIXTURES / "datafile_sample.json").read_bytes()
AI_LOGS = (FIXTURES / "ai_logs_sample.json").read_bytes()
JSON_HEADERS = {"Content-Type": "application/json"}


async def _count(table: str) -> int:
    async with SessionFactory() as s:
        return int(await s.scalar(text(f"SELECT count(*) FROM {table}")) or 0)  # noqa: S608


async def test_requires_api_key(client: httpx.AsyncClient) -> None:
    from app.main import app

    # `client` đã gắn sẵn key đúng, nên dựng client trần để thử thiếu key.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as bare:
        missing = await bare.post("/api/v1/import/datafile", content=DATAFILE, headers=JSON_HEADERS)
    wrong = await client.post(
        "/api/v1/import/datafile", content=DATAFILE, headers={**JSON_HEADERS, "X-API-Key": "sai"}
    )
    assert missing.status_code == 401
    assert wrong.status_code == 403
    assert await _count("tasks") == 0


async def test_default_is_dry_run_and_writes_nothing(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/import/datafile", content=DATAFILE, headers=JSON_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["committed"] is False
    assert body["counts"]["tasks"]["created"] == 3
    assert await _count("tasks") == 0
    assert await _count("import_runs") == 0


async def test_real_import_needs_expect_replaced(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/import/datafile",
        params={"dry_run": "false"},
        content=DATAFILE,
        headers=JSON_HEADERS,
    )
    assert resp.status_code == 422
    assert await _count("tasks") == 0


async def test_real_import_then_rerun_is_noop(client: httpx.AsyncClient) -> None:
    params = {"dry_run": "false", "expect_replaced": "0"}
    first = await client.post(
        "/api/v1/import/datafile", params=params, content=DATAFILE, headers=JSON_HEADERS
    )
    assert first.status_code == 200
    assert first.json()["committed"] is True
    assert await _count("tasks") == 3

    again = await client.post(
        "/api/v1/import/datafile", params=params, content=DATAFILE, headers=JSON_HEADERS
    )
    body = again.json()
    assert body["committed"] is True
    assert body["counts"]["tasks"]["created"] == 0
    assert body["counts"]["tasks"]["replaced"] == 0
    assert await _count("tasks") == 3

    # Nhập xong thì API nghiệp vụ đọc được dữ liệu (không vỡ schema đọc).
    listing = await client.get("/api/v1/tasks", params={"limit": 50, "include_closed": "true"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 3


async def test_utf8_bom_is_stripped(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/import/datafile", content=b"\xef\xbb\xbf" + DATAFILE, headers=JSON_HEADERS
    )
    assert resp.status_code == 200


async def test_unsupported_schema_version_is_422(client: httpx.AsyncClient) -> None:
    data = json.loads(DATAFILE)
    data["schema_version"] = 99
    resp = await client.post("/api/v1/import/datafile", json=data)
    assert resp.status_code == 422


@pytest.mark.parametrize("body", [b"[1, 2]", b'"abc"', b"khong phai json", b"null"])
async def test_body_must_be_json_object(client: httpx.AsyncClient, body: bytes) -> None:
    resp = await client.post("/api/v1/import/datafile", content=body, headers=JSON_HEADERS)
    assert resp.status_code == 422


async def test_missing_required_arrays_is_422(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/import/datafile", json={"schema_version": 4})
    assert resp.status_code == 422


async def test_oversized_body_is_413(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/import/datafile",
        content=b"x" * (10 * 1024 * 1024 + 1),
        headers=JSON_HEADERS,
    )
    assert resp.status_code == 413


async def test_lock_held_elsewhere_is_409(client: httpx.AsyncClient) -> None:
    async with engine.connect() as other:
        await other.execute(text("SELECT pg_advisory_lock(hashtext('builder:import'))"))
        try:
            resp = await client.post(
                "/api/v1/import/datafile", content=DATAFILE, headers=JSON_HEADERS
            )
        finally:
            await other.execute(text("SELECT pg_advisory_unlock(hashtext('builder:import'))"))
    assert resp.status_code == 409


async def test_error_row_returns_200_with_report(client: httpx.AsyncClient) -> None:
    data = json.loads(DATAFILE)
    data["tasks"][0]["priority"] = "khan-cap-qua"
    resp = await client.post("/api/v1/import/datafile", json=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] >= 1
    assert body["committed"] is False
    assert any(i["code"] == "invalid_enum" for i in body["issues"])


async def test_ai_logs_import_then_list(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/import/ai-logs",
        params={"dry_run": "false", "expect_replaced": "0"},
        content=AI_LOGS,
        headers=JSON_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["committed"] is True
    listing = await client.get("/api/v1/ai-logs", params={"limit": 100})
    assert listing.status_code == 200
    page = listing.json()
    assert page["total"] == 4
    assert all(item["handling"] for item in page["items"])


async def test_ai_logs_rejects_newer_schema(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/import/ai-logs", json={"schema_version": 2, "ai_logs": []})
    assert resp.status_code == 422


async def test_openapi_documents_both_paths(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert "/api/v1/import/datafile" in schema["paths"]
    assert "/api/v1/import/ai-logs" in schema["paths"]
    assert "ImportReport" in schema["components"]["schemas"]
    assert "Replacement" in schema["components"]["schemas"]
