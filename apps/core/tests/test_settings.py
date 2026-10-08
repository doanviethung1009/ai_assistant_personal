"""Pha B2: app_settings, /settings/*, /tasks/assignees và nhập meta.current_users, sync_urls.

Mọi dữ liệu đều tổng hợp. Riêng test cuối chỉ ĐỌC file thật của User (mở 'rb') để suy
kỳ vọng từ nội dung file; không bao giờ ghi hay chép nó.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_config
from app.models.enums import ImportEntity, SettingKey
from app.schemas.imports import SUPPORTED_DATAFILE_VERSION, DataFileEnvelope, ImportReport
from app.schemas.settings import normalize_names, normalize_urls
from app.services import import_service, settings_service
from tests.test_import_service import _read_only_fingerprint
from tests.test_task_scope import _alembic, _sql

pytestmark = pytest.mark.db

SHEET = "https://docs.google.com/spreadsheets/d/abc/export?format=xlsx"
SHEET2 = "https://contoso.sharepoint.com/sites/x/file.xlsx"
SHA = "0" * 64


# ═══════════════════════════════════════════════════════════════════════
#  Chuẩn hoá (thuần)
# ═══════════════════════════════════════════════════════════════════════


def test_normalize_names_strips_dedupes_keeps_order() -> None:
    assert normalize_names(["  Hung ", "An", "Hung", "An "]) == ["Hung", "An"]
    assert normalize_names([]) == []


@pytest.mark.parametrize(
    "bad",
    [
        ["ok", ""],
        ["   "],
        ["x" * 201],
        [f"n{i}" for i in range(21)],
        ["a\nb"],
        [1],
        "Hung",
        None,
        {"a": 1},
    ],
)
def test_normalize_names_rejects(bad: Any) -> None:
    with pytest.raises(ValueError):
        normalize_names(bad)


def test_normalize_names_boundaries() -> None:
    assert normalize_names(["x" * 200]) == ["x" * 200]
    assert len(normalize_names([f"n{i}" for i in range(20)])) == 20


def test_normalize_urls_rejects_and_does_not_echo_url() -> None:
    leaky_url = "http://docs.google.com/spreadsheets/d/abc?token=SUPERSECRET"
    with pytest.raises(ValueError) as exc:
        normalize_urls([leaky_url])
    assert "SUPERSECRET" not in str(exc.value)
    assert "https" in str(exc.value)


def test_normalize_urls_strips_dedupes_and_caps() -> None:
    assert normalize_urls([f" {SHEET} ", SHEET, SHEET2]) == [SHEET, SHEET2]
    with pytest.raises(ValueError):
        normalize_urls([f"https://docs.google.com/{i}" for i in range(51)])


def test_normalize_urls_uses_configured_extra_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://files.example.org/a.xlsx"
    with pytest.raises(ValueError):
        normalize_urls([url])
    monkeypatch.setattr(app_config, "sync_url_extra_hosts", ["files.example.org"])
    assert normalize_urls([url]) == [url]


# ═══════════════════════════════════════════════════════════════════════
#  API /settings/*
# ═══════════════════════════════════════════════════════════════════════


async def test_settings_require_api_key(client: httpx.AsyncClient) -> None:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as bare:
        for method, path in [
            ("GET", "/api/v1/settings/current-users"),
            ("PUT", "/api/v1/settings/current-users"),
            ("GET", "/api/v1/settings/sync-urls"),
            ("PUT", "/api/v1/settings/sync-urls"),
            ("GET", "/api/v1/tasks/assignees"),
        ]:
            resp = await bare.request(method, path, json={"names": [], "urls": []})
            assert resp.status_code == 401, (method, path)


async def test_current_users_defaults_empty_and_round_trips(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/settings/current-users")).json() == {"names": []}
    put = await client.put(
        "/api/v1/settings/current-users", json={"names": [" Đoàn Việt Hưng ", "An", "An"]}
    )
    assert put.status_code == 200
    assert put.json() == {"names": ["Đoàn Việt Hưng", "An"]}
    assert (await client.get("/api/v1/settings/current-users")).json() == put.json()
    # Ghi đè hoàn toàn, kể cả về rỗng.
    assert (await client.put("/api/v1/settings/current-users", json={"names": []})).json() == {
        "names": []
    }
    assert (await client.get("/api/v1/settings/current-users")).json() == {"names": []}


@pytest.mark.parametrize(
    "body",
    [
        {"names": [f"n{i}" for i in range(21)]},
        {"names": ["ok", "  "]},
        {"names": ["x" * 201]},
        {"names": "Hung"},
        {"names": [1]},
        {"names": None},
        {},
        {"names": ["a"], "extra": 1},
    ],
)
async def test_current_users_rejects_bad_body(client: httpx.AsyncClient, body: Any) -> None:
    await client.put("/api/v1/settings/current-users", json={"names": ["giu"]})
    resp = await client.put("/api/v1/settings/current-users", json=body)
    assert resp.status_code == 422
    # Lỗi không làm mất giá trị cũ.
    assert (await client.get("/api/v1/settings/current-users")).json() == {"names": ["giu"]}


async def test_sync_urls_round_trip(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/settings/sync-urls")).json() == {"urls": []}
    put = await client.put("/api/v1/settings/sync-urls", json={"urls": [f" {SHEET} ", SHEET2]})
    assert put.status_code == 200
    assert put.json() == {"urls": [SHEET, SHEET2]}
    assert (await client.get("/api/v1/settings/sync-urls")).json() == put.json()


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.google.com/spreadsheets/d/abc",
        "https://evil.com/x",
        "https://docs.google.com.evil.com/x",
        "https://evilgoogleusercontent.com/x",
        "https://docs.google.com@evil.com/x",
        "https://user:pw@docs.google.com/x",
        "https://docs.google.com:8443/x",
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/x",
        "file:///etc/passwd",
        "ftp://docs.google.com/x",
        "https://localhost/x",
        "",
        "not a url",
    ],
)
async def test_sync_urls_rejects_unsafe_and_keeps_old_value(
    client: httpx.AsyncClient, url: str
) -> None:
    await client.put("/api/v1/settings/sync-urls", json={"urls": [SHEET]})
    resp = await client.put("/api/v1/settings/sync-urls", json={"urls": [SHEET2, url]})
    assert resp.status_code == 422
    assert (await client.get("/api/v1/settings/sync-urls")).json() == {"urls": [SHEET]}


async def test_sync_urls_rejects_more_than_50_and_bad_shape(client: httpx.AsyncClient) -> None:
    too_many = [f"https://docs.google.com/spreadsheets/d/{i}" for i in range(51)]
    assert (
        await client.put("/api/v1/settings/sync-urls", json={"urls": too_many})
    ).status_code == 422
    exactly = too_many[:50]
    assert (
        await client.put("/api/v1/settings/sync-urls", json={"urls": exactly})
    ).status_code == 200
    for body in ({"urls": "x"}, {"urls": [1]}, {"urls": None}, {}, {"urls": [], "x": 1}):
        assert (await client.put("/api/v1/settings/sync-urls", json=body)).status_code == 422


async def test_sync_urls_extra_host_env_is_honoured(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://files.example.org/a.xlsx"
    assert (await client.put("/api/v1/settings/sync-urls", json={"urls": [url]})).status_code == 422
    monkeypatch.setattr(app_config, "sync_url_extra_hosts", ["files.example.org"])
    assert (await client.put("/api/v1/settings/sync-urls", json={"urls": [url]})).status_code == 200


async def test_get_sync_urls_returns_stored_even_if_allowlist_changed(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Dòng cũ không còn hợp lệ vẫn đọc ra được để User thấy và xoá; không 500."""
    await session.execute(
        text("INSERT INTO app_settings (key, value) VALUES ('sync_urls', CAST(:v AS jsonb))"),
        {"v": json.dumps(["http://old.example.com/x"])},
    )
    await session.commit()
    resp = await client.get("/api/v1/settings/sync-urls")
    assert resp.status_code == 200
    assert resp.json() == {"urls": ["http://old.example.com/x"]}
    assert (await client.put("/api/v1/settings/sync-urls", json={"urls": []})).status_code == 200


async def test_malformed_stored_value_reads_as_empty(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await session.execute(
        text("INSERT INTO app_settings (key, value) VALUES ('current_users', '{\"a\": 1}')")
    )
    await session.commit()
    assert (await client.get("/api/v1/settings/current-users")).json() == {"names": []}


async def test_put_bumps_updated_at(client: httpx.AsyncClient, session: AsyncSession) -> None:
    await client.put("/api/v1/settings/current-users", json={"names": ["a"]})
    first = await session.scalar(
        text("SELECT updated_at FROM app_settings WHERE key = 'current_users'")
    )
    await session.rollback()
    await asyncio.sleep(0.01)
    await client.put("/api/v1/settings/current-users", json={"names": ["b"]})
    second = await session.scalar(
        text("SELECT updated_at FROM app_settings WHERE key = 'current_users'")
    )
    await session.rollback()
    assert second > first


# ═══════════════════════════════════════════════════════════════════════
#  CHECK / migration
# ═══════════════════════════════════════════════════════════════════════


async def test_check_constraint_rejects_unknown_setting_key(session: AsyncSession) -> None:
    """`alembic check` không so CHECK, nên phải thử INSERT trực tiếp."""
    with pytest.raises(IntegrityError) as exc:
        await session.execute(
            text("INSERT INTO app_settings (key, value) VALUES ('jira_token', '[]')")
        )
    assert "ck_app_settings_key_valid" in str(exc.value)
    await session.rollback()


async def test_service_never_writes_unknown_key(session: AsyncSession) -> None:
    assert {k.value for k in SettingKey} == {"current_users", "sync_urls"}
    with pytest.raises(AttributeError):
        await settings_service.put_list(session, "jira_token", [])  # type: ignore[arg-type]
    await session.rollback()


async def test_import_audit_accepts_setting_but_rejects_other_entities(
    session: AsyncSession,
) -> None:
    run_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO import_runs (id, kind, file_sha256, schema_version, counts, actor) "
            "VALUES (:i, 'datafile', :s, 6, '{}', 'test')"
        ),
        {"i": run_id, "s": SHA},
    )
    insert = (
        "INSERT INTO import_audit (id, import_id, entity, entity_id, action) "
        "VALUES (:i, :r, :e, :x, 'created')"
    )
    await session.execute(
        text(insert), {"i": uuid.uuid4(), "r": run_id, "e": "setting", "x": uuid.uuid4()}
    )
    with pytest.raises(IntegrityError) as exc:
        await session.execute(
            text(insert), {"i": uuid.uuid4(), "r": run_id, "e": "vault", "x": uuid.uuid4()}
        )
    assert "ck_import_audit_entity_valid" in str(exc.value)
    await session.rollback()


def test_import_entity_enum_matches_check_values() -> None:
    assert ImportEntity.SETTING.value == "setting"


def test_migration_round_trip_restores_old_audit_check(migrated_db: None) -> None:
    """downgrade về f6a2b4c8d1e3: bỏ app_settings, xoá audit 'setting', CHECK cũ trở lại."""
    url = os.environ["TEST_DATABASE_URL"]
    run_id = uuid.uuid4()
    try:
        asyncio.run(
            _sql(
                url,
                [
                    (
                        "INSERT INTO import_runs (id, kind, file_sha256, schema_version, "
                        "counts, actor) VALUES (:i, 'datafile', :s, 6, '{}', 'test')",
                        {"i": run_id, "s": SHA},
                    ),
                    (
                        "INSERT INTO import_audit (id, import_id, entity, entity_id, action) "
                        "VALUES (:i, :r, 'setting', :x, 'created')",
                        {"i": uuid.uuid4(), "r": run_id, "x": uuid.uuid4()},
                    ),
                    (
                        "INSERT INTO import_audit (id, import_id, entity, entity_id, action) "
                        "VALUES (:i, :r, 'task', :x, 'created')",
                        {"i": uuid.uuid4(), "r": run_id, "x": uuid.uuid4()},
                    ),
                ],
            )
        )
        _alembic("downgrade", "f6a2b4c8d1e3")
        tables = asyncio.run(_sql(url, [("SELECT to_regclass('public.app_settings')::text", {})]))[
            0
        ]
        assert tables == [(None,)]
        remaining = asyncio.run(
            _sql(url, [("SELECT entity FROM import_audit WHERE import_id = :r", {"r": run_id})])
        )[0]
        assert [r[0] for r in remaining] == ["task"]
        with pytest.raises(IntegrityError, match="ck_import_audit_entity_valid"):
            asyncio.run(
                _sql(
                    url,
                    [
                        (
                            "INSERT INTO import_audit (id, import_id, entity, entity_id, action) "
                            "VALUES (:i, :r, 'setting', :x, 'created')",
                            {"i": uuid.uuid4(), "r": run_id, "x": uuid.uuid4()},
                        )
                    ],
                )
            )
    finally:
        _alembic("upgrade", "head")
        asyncio.run(_sql(url, [("TRUNCATE import_runs CASCADE", {})]))


# ═══════════════════════════════════════════════════════════════════════
#  GET /tasks/assignees
# ═══════════════════════════════════════════════════════════════════════


async def _task(client: httpx.AsyncClient, **payload: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/tasks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_assignees_only_alive_work_distinct_sorted(client: httpx.AsyncClient) -> None:
    await _task(client, title="w1", scope="work", assignee="Bình")
    await _task(client, title="w2", scope="work", assignee="An")
    await _task(client, title="w3", scope="work", assignee="An")
    await _task(client, title="w4", scope="work")  # chưa giao
    await _task(client, title="p1", scope="personal", assignee="Chỉ Cá Nhân")
    trashed = await _task(client, title="w5", scope="work", assignee="Đã Xoá")
    assert (await client.delete(f"/api/v1/tasks/{trashed['id']}")).status_code in (200, 204)

    resp = await client.get("/api/v1/tasks/assignees")
    # Không bị route /{task_id} nuốt (sẽ là 422 vì "assignees" không phải UUID).
    assert resp.status_code == 200
    assert resp.json() == ["An", "Bình"]


async def test_assignees_empty_when_no_tasks(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/tasks/assignees")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_assignee_disappears_after_scope_moves_to_personal(
    client: httpx.AsyncClient,
) -> None:
    task = await _task(client, title="w", scope="work", assignee="An")
    assert (await client.get("/api/v1/tasks/assignees")).json() == ["An"]
    patched = await client.patch(f"/api/v1/tasks/{task['id']}", json={"scope": "personal"})
    assert patched.status_code == 200
    assert (await client.get("/api/v1/tasks/assignees")).json() == []


# ═══════════════════════════════════════════════════════════════════════
#  Nhập meta.current_users và sync_urls
# ═══════════════════════════════════════════════════════════════════════


def _file(**extra: Any) -> dict[str, Any]:
    return {
        "schema_version": SUPPORTED_DATAFILE_VERSION,
        "projects": [],
        "tasks": [],
        "notes": [],
        **extra,
    }


async def _import(
    session: AsyncSession,
    data: dict[str, Any],
    *,
    dry_run: bool = False,
    expect: int = 0,
) -> ImportReport:
    return await import_service.import_datafile(
        session,
        DataFileEnvelope.model_validate(data),
        dry_run=dry_run,
        expect_replaced=None if dry_run else expect,
        expect_sha256=None if dry_run else SHA,
        file_sha256=SHA,
    )


async def _setting(session: AsyncSession, key: str) -> Any:
    value = await session.scalar(text("SELECT value FROM app_settings WHERE key = :k"), {"k": key})
    await session.rollback()
    return value


def test_supported_version_is_6() -> None:
    assert SUPPORTED_DATAFILE_VERSION == 6


async def test_import_creates_settings_then_is_idempotent(session: AsyncSession) -> None:
    data = _file(
        meta={"current_users": [" Hung ", "An"], "minutes_logged_today": 5, "x": 1},
        sync_urls=[SHEET],
    )
    dry = await _import(session, data, dry_run=True)
    assert dry.errors == 0 and not dry.committed
    assert await _setting(session, "current_users") is None  # dry-run không ghi

    real = await _import(session, data)
    assert real.committed, real.issues
    assert real.counts["settings"].created == 2
    assert real.counts["settings"].received == 2
    # D-B2a: minutes_logged_* và khoá lạ KHÔNG được lưu, chỉ liệt kê tên.
    assert real.ignored_fields["meta"] == ["minutes_logged_today", "x"]
    assert await _setting(session, "current_users") == ["Hung", "An"]
    assert await _setting(session, "sync_urls") == [SHEET]
    audits = (
        await session.execute(text("SELECT entity, action FROM import_audit ORDER BY entity"))
    ).all()
    assert [tuple(r) for r in audits] == [("setting", "created")] * 2
    await session.rollback()

    again = await _import(session, data)
    assert again.committed
    assert again.counts["settings"].unchanged == 2
    assert again.counts["settings"].created == again.counts["settings"].replaced == 0
    assert again.replacements == []


async def test_import_replace_reports_audits_and_requires_expect(
    session: AsyncSession,
) -> None:
    await settings_service.set_current_users(session, ["Cũ"])
    await session.commit()
    data = _file(meta={"current_users": ["Mới"]})

    dry = await _import(session, data, dry_run=True)
    assert dry.counts["settings"].replaced == 1
    [rep] = dry.replacements
    assert rep.entity == "setting"
    assert rep.label == "current_users"
    assert rep.file_older_than_db is False
    assert [(c.field, c.old, c.new) for c in rep.changes] == [("value", ["Cũ"], ["Mới"])]
    assert await _setting(session, "current_users") == ["Cũ"]

    # Rào chắn B1 giữ nguyên: sai expect_replaced thì huỷ, không ghi.
    wrong = await _import(session, data, expect=0)
    assert not wrong.committed
    assert any(i.code == "replace_count_mismatch" for i in wrong.issues)
    assert await _setting(session, "current_users") == ["Cũ"]

    ok = await _import(session, data, expect=1)
    assert ok.committed
    assert await _setting(session, "current_users") == ["Mới"]
    row = (
        await session.execute(
            text("SELECT entity, action, before, changed_fields FROM import_audit")
        )
    ).one()
    assert (row.entity, row.action) == ("setting", "replaced")
    assert row.before == {"key": "current_users", "value": ["Cũ"]}
    assert row.changed_fields == ["value"]
    await session.rollback()


async def test_import_absent_or_null_keys_do_not_touch_db(session: AsyncSession) -> None:
    await settings_service.set_current_users(session, ["Giữ"])
    await settings_service.set_sync_urls(session, [SHEET])
    await session.commit()
    for data in (_file(), _file(meta={}), _file(meta={"current_users": None}, sync_urls=None)):
        report = await _import(session, data)
        assert report.committed
        assert report.counts["settings"].received == 0
    assert await _setting(session, "current_users") == ["Giữ"]
    assert await _setting(session, "sync_urls") == [SHEET]


async def test_import_empty_list_replaces_to_empty(session: AsyncSession) -> None:
    await settings_service.set_sync_urls(session, [SHEET])
    await session.commit()
    report = await _import(session, _file(sync_urls=[]), expect=1)
    assert report.committed
    assert await _setting(session, "sync_urls") == []


@pytest.mark.parametrize(
    "extra",
    [
        {"sync_urls": ["http://docs.google.com/x"]},
        {"sync_urls": ["https://evil.com/x"]},
        {"sync_urls": ["https://docs.google.com@evil.com/x"]},
        {"sync_urls": ["https://169.254.169.254/latest"]},
        {"sync_urls": "https://docs.google.com/x"},
        {"sync_urls": [1]},
        {"meta": {"current_users": [f"n{i}" for i in range(21)]}},
        {"meta": {"current_users": ["ok", ""]}},
        {"meta": {"current_users": "Hung"}},
    ],
)
async def test_import_rejects_invalid_settings_all_or_nothing(
    session: AsyncSession, extra: dict[str, Any]
) -> None:
    """Nhập file không được là cửa sau qua allowlist SSRF; lỗi thì không ghi gì."""
    project = {
        "id": str(uuid.uuid4()),
        "key": "PROJ",
        "name": "P",
    }
    data = _file(projects=[project], **extra)
    for dry_run in (True, False):
        report = await _import(session, data, dry_run=dry_run)
        assert report.errors == 1
        assert not report.committed
        assert [i.code for i in report.issues if i.level == "error"] == ["setting_invalid"]
        # Không echo giá trị gốc trong thông điệp.
        assert "evil.com" not in " ".join(i.message for i in report.issues)
    assert await session.scalar(text("SELECT count(*) FROM projects")) == 0
    assert await session.scalar(text("SELECT count(*) FROM app_settings")) == 0
    assert await session.scalar(text("SELECT count(*) FROM import_runs")) == 0
    await session.rollback()


async def test_import_old_version_file_without_settings_still_works(
    session: AsyncSession,
) -> None:
    for version in (4, 5):
        report = await _import(session, {**_file(), "schema_version": version})
        assert report.committed
        assert report.schema_version == version


async def test_import_api_accepts_v6_and_writes_settings(client: httpx.AsyncClient) -> None:
    body = json.dumps(_file(meta={"current_users": ["Hung"]}, sync_urls=[SHEET])).encode()
    sha = hashlib.sha256(body).hexdigest()
    headers = {"Content-Type": "application/json"}
    dry = await client.post("/api/v1/import/datafile", content=body, headers=headers)
    assert dry.status_code == 200
    assert dry.json()["counts"]["settings"]["created"] == 2
    from tests.conftest import IMPORT_SECRET

    real = await client.post(
        "/api/v1/import/datafile",
        params={"dry_run": "false", "expect_replaced": "0", "expect_sha256": sha},
        content=body,
        headers={**headers, "X-Import-Secret": IMPORT_SECRET},
    )
    assert real.status_code == 200 and real.json()["committed"]
    assert (await client.get("/api/v1/settings/current-users")).json() == {"names": ["Hung"]}
    assert (await client.get("/api/v1/settings/sync-urls")).json() == {"urls": [SHEET]}


# ═══════════════════════════════════════════════════════════════════════
#  File thật của User (chỉ đọc, bỏ qua khi thiếu biến môi trường)
# ═══════════════════════════════════════════════════════════════════════

REAL_DATAFILE = os.environ.get("IMPORT_REAL_DATAFILE")


@pytest.mark.skipif(not REAL_DATAFILE, reason="cần IMPORT_REAL_DATAFILE")
async def test_real_file_current_users_imported_then_unchanged(session: AsyncSession) -> None:
    assert REAL_DATAFILE
    path = Path(REAL_DATAFILE)
    # Chỉ đọc ('rb') qua helper dùng chung; không bao giờ ghi file thật.
    sha_before, mtime_before, body = _read_only_fingerprint(path)
    raw = json.loads(body)
    # Kỳ vọng suy từ nội dung file (file thật thay đổi theo thời gian).
    expected = normalize_names((raw.get("meta") or {}).get("current_users") or [])
    envelope = DataFileEnvelope.model_validate(raw)

    async def run(dry_run: bool, expect: int = 0) -> ImportReport:
        return await import_service.import_datafile(
            session,
            envelope,
            dry_run=dry_run,
            expect_replaced=None if dry_run else expect,
            expect_sha256=None if dry_run else sha_before,
            file_sha256=sha_before,
        )

    dry = await run(True)
    assert dry.errors == 0, [i for i in dry.issues if i.level == "error"][:5]
    first = await run(False)
    assert first.committed, first.issues[:5]
    if "current_users" in (raw.get("meta") or {}):
        assert first.counts["settings"].created >= 1
        assert await _setting(session, "current_users") == expected
    again = await run(False)
    assert again.committed
    assert again.counts["settings"].created == again.counts["settings"].replaced == 0
    # Chạy lại: current_users đã có thì là unchanged.
    if expected or "current_users" in (raw.get("meta") or {}):
        assert again.counts["settings"].unchanged >= 1
    await session.rollback()
    await session.execute(
        text("TRUNCATE task_events, tasks, notes, projects, app_settings CASCADE")
    )
    await session.commit()

    sha_after, mtime_after, _ = _read_only_fingerprint(path)
    assert (sha_after, mtime_after) == (sha_before, mtime_before)


# ═══════════════════════════════════════════════════════════════════════
#  Vòng sửa sau review
# ═══════════════════════════════════════════════════════════════════════


async def _hold_import_lock(session: AsyncSession) -> None:
    """Giữ advisory lock của nhập ở một transaction khác, như một lần nhập đang chạy."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:n))"), {"n": settings_service.IMPORT_LOCK_NAME}
    )


async def test_put_settings_waits_for_import_lock_then_409(
    client: httpx.AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings_service, "SETTINGS_LOCK_TIMEOUT", "200ms")
    await _hold_import_lock(session)
    try:
        for path, body in [
            ("/api/v1/settings/current-users", {"names": ["a"]}),
            ("/api/v1/settings/sync-urls", {"urls": [SHEET]}),
        ]:
            resp = await client.put(path, json=body)
            assert resp.status_code == 409, resp.text
    finally:
        await session.rollback()  # nhả khoá
    # Hết khoá thì ghi bình thường; lần 409 không để lại gì.
    assert (await client.get("/api/v1/settings/current-users")).json() == {"names": []}
    ok = await client.put("/api/v1/settings/current-users", json={"names": ["a"]})
    assert ok.status_code == 200


async def test_put_proceeds_once_import_lock_released(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """Khoá giữ ngắn hơn timeout: PUT chờ rồi thành công (không 409)."""
    await _hold_import_lock(session)
    task = asyncio.create_task(
        client.put("/api/v1/settings/current-users", json={"names": ["chờ"]})
    )
    await asyncio.sleep(0.3)
    assert not task.done()  # đang chờ khoá
    await session.rollback()
    resp = await asyncio.wait_for(task, timeout=4)
    assert resp.status_code == 200
    assert resp.json() == {"names": ["chờ"]}


def _check_values(defn: str) -> set[str]:
    """Các giá trị chuỗi trong định nghĩa CHECK do pg_get_constraintdef trả về."""
    import re

    return set(re.findall(r"'([^']+)'", defn))


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        ("ck_app_settings_key_valid", {m.value for m in SettingKey}),
        ("ck_import_audit_entity_valid", {m.value for m in ImportEntity}),
    ],
)
async def test_check_constraint_definitions_match_enums(
    session: AsyncSession, constraint: str, expected: set[str]
) -> None:
    """`alembic check` không so CHECK: thêm giá trị enum mà quên migration sẽ lộ ở đây."""
    defn = await session.scalar(
        text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n"),
        {"n": constraint},
    )
    await session.rollback()
    assert defn, constraint
    assert _check_values(defn) == expected


async def test_report_hides_url_query_but_audit_keeps_full_before(
    session: AsyncSession,
) -> None:
    old = "https://docs.google.com/spreadsheets/d/OLD/edit?usp=sharing&key=OLDTOKEN#gid=1"
    new = "https://contoso.sharepoint.com/sites/x/f.xlsx?e=NEWTOKEN&at=9"
    await settings_service.set_sync_urls(session, [old])
    await session.commit()
    data = _file(sync_urls=[new])
    dry = await _import(session, data, dry_run=True)
    [rep] = dry.replacements
    [change] = rep.changes
    assert change.old == ["https://docs.google.com/spreadsheets/d/OLD/edit"]
    assert change.new == ["https://contoso.sharepoint.com/sites/x/f.xlsx"]
    blob = dry.model_dump_json()
    assert "TOKEN" not in blob and "usp=" not in blob and "gid=1" not in blob

    real = await _import(session, data, expect=1)
    assert real.committed
    assert "TOKEN" not in real.model_dump_json()
    before = await session.scalar(text("SELECT before FROM import_audit"))
    await session.rollback()
    assert before == {"key": "sync_urls", "value": [old]}  # đầy đủ, cần cho hoàn tác


def test_redact_url_helper() -> None:
    redact = import_service._redact_url
    assert redact("https://u:p@docs.google.com:443/a?k=1#f") == "https://docs.google.com:443/a"
    assert redact("not a url") == "(URL không hợp lệ)"
    assert redact("https://[::1/x") == "(URL không hợp lệ)"
    assert redact(5) == "(không phải chuỗi)"
    assert len(redact("https://docs.google.com/" + "a" * 500)) == 200


async def test_setting_invalid_hint_for_sync_urls_without_echo(session: AsyncSession) -> None:
    report = await _import(
        session, _file(sync_urls=["https://evil.example.com/x?token=SECRET"]), dry_run=True
    )
    [err] = [i for i in report.issues if i.level == "error"]
    assert err.code == "setting_invalid"
    assert "SYNC_URL_EXTRA_HOSTS" in err.message and "xoá sync_urls" in err.message
    assert "SECRET" not in err.message and "evil.example.com" not in err.message
    names = await _import(session, _file(meta={"current_users": [""]}), dry_run=True)
    [err2] = [i for i in names.issues if i.level == "error"]
    assert "SYNC_URL_EXTRA_HOSTS" not in err2.message


async def test_settings_422_does_not_echo_input(client: httpx.AsyncClient) -> None:
    leaky = "https://evil.example.com/x?token=TOPSECRET"
    resp = await client.put("/api/v1/settings/sync-urls", json={"urls": [leaky]})
    assert resp.status_code == 422
    assert "TOPSECRET" not in resp.text and "evil.example.com" not in resp.text
    for err in resp.json()["detail"]:
        assert set(err) == {"type", "loc", "msg"}
    resp = await client.put("/api/v1/settings/current-users", json={"names": ["x", 1]})
    assert resp.status_code == 422
    assert all("input" not in e and "ctx" not in e for e in resp.json()["detail"])


async def test_other_routes_keep_default_422_shape(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/tasks", json={"title": 123})
    assert resp.status_code == 422
    assert any("input" in e for e in resp.json()["detail"])
