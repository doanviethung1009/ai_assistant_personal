"""Endpoint /api/v1/import/* qua HTTP: xác thực, validate body, giới hạn, mặc định an toàn."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.db.session import SessionFactory, engine
from tests.conftest import Persona, create_persona

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).parent / "fixtures"
DATAFILE = (FIXTURES / "datafile_sample.json").read_bytes()
JSON_HEADERS = {"Content-Type": "application/json"}
DATAFILE_SHA = hashlib.sha256(DATAFILE).hexdigest()
# Nhập thật cần: expect_replaced + expect_sha256 (từ dry-run) và quyền `data:import` (admin).
COMMIT_PARAMS = {"dry_run": "false", "expect_replaced": "0", "expect_sha256": DATAFILE_SHA}
COMMIT_HEADERS = JSON_HEADERS


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


@pytest.mark.parametrize(
    "params",
    [
        {"dry_run": "false"},
        {"dry_run": "false", "expect_replaced": "0"},
        {"dry_run": "false", "expect_sha256": DATAFILE_SHA},
    ],
)
async def test_real_import_needs_expect_replaced_and_sha(
    client: httpx.AsyncClient, params: dict[str, str]
) -> None:
    resp = await client.post(
        "/api/v1/import/datafile",
        params=params,
        content=DATAFILE,
        headers=COMMIT_HEADERS,
    )
    assert resp.status_code == 422
    assert await _count("tasks") == 0


async def test_dry_run_report_sha_matches_body(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/import/datafile", content=DATAFILE, headers=JSON_HEADERS)
    assert resp.json()["file_sha256"] == DATAFILE_SHA


async def test_commit_with_wrong_sha_is_refused(client: httpx.AsyncClient) -> None:
    params = {**COMMIT_PARAMS, "expect_sha256": "0" * 64}
    resp = await client.post(
        "/api/v1/import/datafile", params=params, content=DATAFILE, headers=COMMIT_HEADERS
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["committed"] is False
    assert "file_changed_since_dry_run" in {i["code"] for i in body["issues"]}
    assert await _count("tasks") == 0


async def test_import_requires_data_import_permission(client: httpx.AsyncClient) -> None:
    """Nhập (kể cả dry-run) chỉ dành cho admin; lead và member nhận 403, không ghi gì."""
    from app.models.enums import UserRole

    post = {"params": COMMIT_PARAMS, "content": DATAFILE}
    for role in (UserRole.MEMBER, UserRole.LEAD):
        who = await create_persona(f"{role.value}-imp@test.local", role)
        denied = await client.post(
            "/api/v1/import/datafile", headers={**JSON_HEADERS, **who.headers}, **post
        )
        dry = await client.post(
            "/api/v1/import/datafile",
            headers={**JSON_HEADERS, **who.headers},
            params={"dry_run": "true"},
            content=DATAFILE,
        )
        assert (denied.status_code, dry.status_code) == (403, 403)
        assert denied.json()["code"] == "forbidden"
    assert await _count("tasks") == 0

    ok = await client.post("/api/v1/import/datafile", headers=COMMIT_HEADERS, **post)
    assert ok.status_code == 200
    assert ok.json()["committed"] is True


async def test_malformed_external_url_is_a_warning_not_a_500(client: httpx.AsyncClient) -> None:
    data = json.loads(DATAFILE)
    data["tasks"][0]["external_url"] = "http://[::1"
    data["tasks"][1]["external_url"] = "https://[bad]x/"
    resp = await client.post("/api/v1/import/datafile", json=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == 0
    assert sum(1 for i in body["issues"] if i["code"] == "external_url_dropped") == 2


async def test_dry_run_needs_no_expect_params(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/import/datafile",
        params={"dry_run": "true"},
        content=DATAFILE,
        headers=JSON_HEADERS,
    )
    assert resp.status_code == 200


async def test_deeply_nested_json_is_422(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/import/datafile", content=b"[" * 200_000, headers=JSON_HEADERS
    )
    assert resp.status_code == 422
    deep_object = b'{"a":' * 100_000
    resp2 = await client.post("/api/v1/import/datafile", content=deep_object, headers=JSON_HEADERS)
    assert resp2.status_code == 422


async def test_real_import_then_rerun_is_noop(client: httpx.AsyncClient) -> None:
    params = COMMIT_PARAMS
    first = await client.post(
        "/api/v1/import/datafile", params=params, content=DATAFILE, headers=COMMIT_HEADERS
    )
    assert first.status_code == 200
    assert first.json()["committed"] is True
    assert await _count("tasks") == 3

    again = await client.post(
        "/api/v1/import/datafile", params=params, content=DATAFILE, headers=COMMIT_HEADERS
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


async def test_schema_version_5_to_8_accepted_and_9_rejected(client: httpx.AsyncClient) -> None:
    data = json.loads(DATAFILE)
    for version in (5, 6, 7, 8):
        data["schema_version"] = version
        ok = await client.post("/api/v1/import/datafile", json=data)
        assert ok.status_code == 200
        assert ok.json()["schema_version"] == version
    data["schema_version"] = 9
    assert (await client.post("/api/v1/import/datafile", json=data)).status_code == 422


async def test_include_personal_query_param_reaches_service(
    client: httpx.AsyncClient, default_user: Persona
) -> None:
    """Tham số route từng bị khai mà không truyền xuống service (xem test_task_api)."""
    async with SessionFactory() as s:
        await s.execute(
            text(
                "INSERT INTO tasks (id, title, source, scope, external_id, owner_id) VALUES "
                "('aaaaaaa1-0000-4000-8000-000000000001', 'Cua rieng', "
                "'jira', 'personal', 'DEMO-1', :owner)"
            ),
            {"owner": default_user.id},
        )
        await s.commit()
    blocked = (
        await client.post("/api/v1/import/datafile", content=DATAFILE, headers=JSON_HEADERS)
    ).json()
    # Mặc định dry-run: chỉ báo cáo, không ghi. T3 chưa có trong DB nên chỉ DEMO-1 bị bảo vệ.
    assert blocked["counts"]["tasks"]["skipped_personal"] == 1
    assert blocked["counts"]["tasks"]["replaced"] == 0

    allowed = (
        await client.post(
            "/api/v1/import/datafile",
            params={"include_personal": "true"},
            content=DATAFILE,
            headers=JSON_HEADERS,
        )
    ).json()
    assert allowed["counts"]["tasks"]["replaced"] == 1
    assert allowed["counts"]["tasks"]["skipped_personal"] == 0


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


async def test_openapi_documents_import_paths(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert "/api/v1/import/datafile" in schema["paths"]
    assert "/api/v1/import/ai-logs" not in schema["paths"]
    assert "ImportReport" in schema["components"]["schemas"]
    assert "Replacement" in schema["components"]["schemas"]


# ── /import/verify-secret đã gỡ ────────────────────────────────────


@pytest.mark.db
async def test_verify_secret_endpoint_is_gone(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/import/verify-secret")
    assert resp.status_code in (404, 405)
