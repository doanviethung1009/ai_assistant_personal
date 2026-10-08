"""POST /tasks/upsert-batch (B4a): idempotent, bảo vệ task personal, lọc raw_payload."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.api import capped
from app.core.config import settings
from app.db import locks
from app.db.session import SessionFactory
from app.models.project import Project
from app.models.task import Task, TaskEvent
from app.services import clock, task_sync_service
from app.services.task_sync_service import (
    MAX_RAW_PAYLOAD_BYTES,
    PayloadDropped,
    prepare_payload,
    sanitize_payload,
)

URL = "/api/v1/tasks/upsert-batch"

from tests.conftest import IMPORT_SECRET  # noqa: E402


@pytest_asyncio.fixture
async def client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Mọi test mặc định gửi mật khẩu nhập; test 403 tự gỡ header."""
    client.headers["X-Import-Secret"] = IMPORT_SECRET
    return client


def _item(ext: str, **over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"external_id": ext, "title": f"Việc {ext}"}
    item.update(over)
    return item


def _batch(items: list[dict[str, Any]], source: str = "jira") -> dict[str, Any]:
    return {"source": source, "items": items}


async def _tasks(ext: str | None = None) -> list[Task]:
    async with SessionFactory() as s:
        stmt = select(Task).order_by(Task.created_at)
        if ext:
            stmt = stmt.where(Task.external_id == ext)
        return list((await s.execute(stmt)).scalars().unique())


async def _events(task_id: Any) -> list[TaskEvent]:
    async with SessionFactory() as s:
        stmt = select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at)
        return list((await s.execute(stmt)).scalars())


# ── Hàm thuần ───────────────────────────────────────────────────────


def test_sanitize_drops_sensitive_keys_at_any_depth() -> None:
    raw = {
        "key": "OK-1",
        "Authorization": "Bearer x",
        "fields": {
            "summary": "s",
            "access_token": "t",
            "X-Api-Key": "k",
            "nested": [{"Set-Cookie": "c", "keep": 1, "clientSecret": "z"}, "txt\x00"],
            "password": "p",
        },
    }
    clean = sanitize_payload(raw)
    assert clean == {"key": "OK-1", "fields": {"summary": "s", "nested": [{"keep": 1}, "txt"]}}
    assert "Authorization" in raw  # không sửa bản gốc


def test_prepare_payload_limits_size_and_depth() -> None:
    assert prepare_payload(None) is None
    with pytest.raises(ValueError, match="KB"):
        prepare_payload({"blob": "x" * (MAX_RAW_PAYLOAD_BYTES + 1)})
    deep: dict[str, Any] = {}
    cur = deep
    for _ in range(100):
        cur["a"] = {}
        cur = cur["a"]
    with pytest.raises(ValueError, match="sâu"):
        prepare_payload(deep)
    # Kích thước tính SAU khi lọc khoá nhạy cảm.
    assert prepare_payload({"token": "x" * (MAX_RAW_PAYLOAD_BYTES * 2), "a": 1}) == {"a": 1}


# ── Endpoint ────────────────────────────────────────────────────────


@pytest.mark.db
async def test_idempotent_and_updated_at_untouched(client: httpx.AsyncClient) -> None:
    payload = _batch([_item("J-1", status="in_progress", tags=["A b"]), _item("J-2")])
    first = (await client.post(URL, json=payload)).json()
    assert first == {
        "added": 2,
        "updated": 0,
        "unchanged": 0,
        "skipped_personal": 0,
        "errors": [],
        "warnings": [],
    }
    stamps = {t.external_id: (t.updated_at, t.created_at) for t in await _tasks()}

    second = (await client.post(URL, json=payload)).json()
    assert second["added"] == 0 and second["updated"] == 0 and second["unchanged"] == 2
    assert {t.external_id: (t.updated_at, t.created_at) for t in await _tasks()} == stamps
    tasks = await _tasks()
    assert len(tasks) == 2
    assert all(t.scope.value == "work" and t.source.value == "jira" for t in tasks)
    assert tasks[0].tags == ["a-b"]
    # Không sinh thêm event ở lần chạy thứ hai.
    for t in tasks:
        assert [e.event_type.value for e in await _events(t.id)] == ["synced"]


@pytest.mark.db
async def test_events_synced_then_updated_with_diff(client: httpx.AsyncClient) -> None:
    await client.post(URL, json=_batch([_item("J-1")]))
    res = (
        await client.post(
            URL, json=_batch([_item("J-1", title="Mới", status="done", description="b")])
        )
    ).json()
    assert res["updated"] == 1 and res["added"] == 0

    (task,) = await _tasks("J-1")
    assert task.title == "Mới" and task.status.value == "done" and task.completed_at is not None
    events = await _events(task.id)
    assert [e.event_type.value for e in events] == ["synced", "updated"]
    assert all(e.actor == "integration:jira" for e in events)
    changes = events[1].payload["changes"]  # type: ignore[index]
    assert changes["title"] == {"from": "Việc J-1", "to": "Mới"}
    assert changes["status"]["to"] == "done" and changes["description"]["to"] == "b"


@pytest.mark.db
async def test_unsent_fields_are_kept_on_update(client: httpx.AsyncClient) -> None:
    await client.post(URL, json=_batch([_item("J-1", status="in_progress", priority="high")]))
    res = (
        await client.post(URL, json=_batch([{"external_id": "J-1", "title": "Việc J-1"}]))
    ).json()
    assert res["unchanged"] == 1
    (task,) = await _tasks("J-1")
    assert task.status.value == "in_progress" and task.priority.value == "high"


@pytest.mark.db
async def test_trashed_task_with_same_key_creates_new(client: httpx.AsyncClient) -> None:
    first = await client.post(URL, json=_batch([_item("J-1")]))
    assert first.json()["added"] == 1
    (old,) = await _tasks("J-1")
    assert (await client.delete(f"/api/v1/tasks/{old.id}")).status_code == 204

    res = (await client.post(URL, json=_batch([_item("J-1", title="Sau thùng rác")]))).json()
    assert res["added"] == 1 and res["updated"] == 0
    rows = await _tasks("J-1")
    assert len(rows) == 2
    assert sum(r.deleted_at is None for r in rows) == 1


@pytest.mark.db
async def test_personal_task_is_never_overwritten(client: httpx.AsyncClient) -> None:
    made = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Của riêng tôi",
            "source": "jira",
            "external_id": "J-9",
            "scope": "personal",
        },
    )
    assert made.status_code == 201, made.text
    res = (
        await client.post(URL, json=_batch([_item("J-9", title="Ghi đè?"), _item("J-10")]))
    ).json()
    assert res["skipped_personal"] == 1 and res["added"] == 1 and res["updated"] == 0
    (task,) = await _tasks("J-9")
    assert task.title == "Của riêng tôi" and task.scope.value == "personal"
    assert [e.event_type.value for e in await _events(task.id)] == ["created"]


@pytest.mark.db
async def test_work_task_from_manual_create_is_updated(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/v1/tasks",
        json={"title": "Cũ", "source": "jira", "external_id": "J-3", "scope": "work"},
    )
    res = (await client.post(URL, json=_batch([_item("J-3", title="Mới")]))).json()
    assert res["updated"] == 1


@pytest.mark.db
async def test_source_manual_and_oversize_batch_rejected(client: httpx.AsyncClient) -> None:
    manual = await client.post(URL, json=_batch([_item("J-1")], source="manual"))
    assert manual.status_code == 422
    assert (await client.post(URL, json=_batch([_item("J-1")], source="bogus"))).status_code == 422
    big = _batch([_item(f"J-{i}") for i in range(1001)])
    assert (await client.post(URL, json=big)).status_code == 422
    assert await _tasks() == []
    ok = _batch([_item(f"J-{i}") for i in range(1000)])
    resp = await client.post(URL, json=ok)
    assert resp.status_code == 200 and resp.json()["added"] == 1000


@pytest.mark.db
async def test_raw_payload_is_filtered_and_oversize_is_warning(
    client: httpx.AsyncClient,
) -> None:
    payload = {
        "key": "J-1",
        "Authorization": "Bearer SECRET-AAA",
        "fields": {"summary": "s", "api_key": "KKK", "list": [{"cookie": "c", "ok": True}]},
    }
    res = (
        await client.post(
            URL,
            json=_batch(
                [
                    _item("J-1", raw_payload=payload),
                    _item("J-2", raw_payload={"blob": "x" * (MAX_RAW_PAYLOAD_BYTES + 10)}),
                    _item("J-3"),
                ]
            ),
        )
    ).json()
    assert res["added"] == 3 and res["errors"] == []
    assert res["warnings"] == [{"index": 1, "reason": "raw_payload vượt 64 KB"}]
    (task,) = await _tasks("J-1")
    assert task.raw_payload == {
        "key": "J-1",
        "fields": {"summary": "s", "list": [{"ok": True}]},
    }
    # Task VẪN được tạo, chỉ mất payload.
    (j2,) = await _tasks("J-2")
    assert j2.raw_payload is None and j2.title == "Việc J-2"


@pytest.mark.db
async def test_duplicate_external_id_and_bad_project_key_are_item_errors(
    client: httpx.AsyncClient,
) -> None:
    res = (
        await client.post(
            URL,
            json=_batch(
                [
                    _item("J-1"),
                    _item("J-1", title="trùng"),
                    _item("J-2", project_key="!!!"),
                    _item("J-3"),
                ]
            ),
        )
    ).json()
    assert res["added"] == 2
    assert [e["index"] for e in res["errors"]] == [1, 2]
    assert (await _tasks("J-1"))[0].title == "Việc J-1"


@pytest.mark.db
async def test_projects_created_by_normalized_key(client: httpx.AsyncClient) -> None:
    items = [
        _item("J-1", project_key="ONE NEXUS", project_name="One Nexus"),
        _item("J-2", project_key="one nexus"),
    ]
    assert (await client.post(URL, json=_batch(items))).json()["added"] == 2
    async with SessionFactory() as s:
        projects = list((await s.execute(select(Project))).scalars())
        assert [p.key for p in projects] == ["ONE_NEXUS"]
        assert projects[0].name == "One Nexus"
    t1, t2 = await _tasks("J-1"), await _tasks("J-2")
    assert t1[0].project_id == t2[0].project_id == projects[0].id
    # Lần hai: không tạo project trùng, không đổi gì.
    again = (await client.post(URL, json=_batch(items))).json()
    assert again["unchanged"] == 2
    async with SessionFactory() as s:
        assert await s.scalar(select(func.count()).select_from(Project)) == 1


@pytest.mark.db
async def test_parallel_batches_do_not_duplicate(client: httpx.AsyncClient) -> None:
    payload = _batch([_item(f"J-{i}") for i in range(30)])
    results = await asyncio.gather(*(client.post(URL, json=payload) for _ in range(4)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert sum(r.json()["added"] for r in results) == 30
    assert len(await _tasks()) == 30


@pytest.mark.db
async def test_nul_characters_do_not_break_batch(client: httpx.AsyncClient) -> None:
    res = await client.post(
        URL, json=_batch([_item("J-1", title="a\u0000b", raw_payload={"k\u0000": "v\u0000"})])
    )
    assert res.status_code == 200 and res.json()["added"] == 1
    (task,) = await _tasks("J-1")
    assert task.title == "ab" and task.raw_payload == {"k": "v"}


@pytest.mark.db
async def test_validation_error_does_not_echo_input(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        URL,
        json=_batch([_item("J-1", status="bogus", raw_payload={"token": "LEAKME-123456"})]),
    )
    assert resp.status_code == 422
    assert "LEAKME-123456" not in resp.text
    assert all(set(e) == {"type", "loc", "msg"} for e in resp.json()["detail"])


@pytest.mark.db
async def test_empty_batch_is_noop(client: httpx.AsyncClient) -> None:
    res = (await client.post(URL, json=_batch([]))).json()
    assert res == {
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped_personal": 0,
        "errors": [],
        "warnings": [],
    }


# ═══════════════════════════════════════════════════════════════════════
#  Vòng sửa sau review (B4a)
# ═══════════════════════════════════════════════════════════════════════

# ── Ngữ nghĩa gộp ───────────────────────────────────────────────────


@pytest.mark.db
async def test_tags_are_unioned_and_description_only_fills_empty(
    client: httpx.AsyncClient,
) -> None:
    await client.post(URL, json=_batch([_item("J-1", tags=["jira", "a"]), _item("J-2")]))
    (t1,) = await _tasks("J-1")
    # User tự gắn tag và sửa mô tả.
    patched = await client.patch(
        f"/api/v1/tasks/{t1.id}", json={"tags": ["jira", "a", "của-tôi"], "description": "Của User"}
    )
    assert patched.status_code == 200, patched.text

    res = (
        await client.post(
            URL,
            json=_batch(
                [
                    _item("J-1", tags=["b", "a", "jira"], description="Từ Jira"),
                    _item("J-2", description="Mô tả đầu tiên"),
                ]
            ),
        )
    ).json()
    assert res["updated"] == 2
    (t1,) = await _tasks("J-1")
    assert t1.tags == ["jira", "a", "của-tôi", "b"]  # hợp, giữ thứ tự, không trùng
    assert t1.description == "Của User"  # không bị đè
    (t2,) = await _tasks("J-2")
    assert t2.description == "Mô tả đầu tiên"  # đang rỗng thì điền

    # Chạy lại: không đổi gì (idempotent với ngữ nghĩa gộp).
    again = (
        await client.post(
            URL,
            json=_batch(
                [
                    _item("J-1", tags=["b", "a", "jira"], description="Từ Jira"),
                    _item("J-2", description="Mô tả khác"),
                ]
            ),
        )
    ).json()
    assert again["unchanged"] == 2 and again["updated"] == 0


# ── completed_at / created_at từ nguồn ──────────────────────────────


@pytest.mark.db
async def test_created_and_completed_at_come_from_source(client: httpx.AsyncClient) -> None:
    res = (
        await client.post(
            URL,
            json=_batch(
                [
                    _item(
                        "J-1",
                        status="done",
                        created_at="2019-12-31T00:00:00Z",
                        completed_at="2020-01-02T03:04:05Z",
                    ),
                    _item("J-2", status="done"),  # đóng mà nguồn không cho mốc
                    _item("J-3", status="cancelled", completed_at="2020-02-02T00:00:00Z"),
                    _item("J-4", status="todo", completed_at="2020-02-02T00:00:00Z"),
                ]
            ),
        )
    ).json()
    assert res["added"] == 4
    t1, t2, t3, t4 = [(await _tasks(f"J-{i}"))[0] for i in range(1, 5)]
    assert t1.completed_at == datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert t1.created_at == datetime(2019, 12, 31, tzinfo=UTC)
    assert t2.completed_at is None  # KHÔNG đặt now()
    assert t3.completed_at == datetime(2020, 2, 2, tzinfo=UTC)
    assert t4.completed_at is None  # chưa đóng thì bỏ qua mốc
    assert t4.created_at is not None  # không gửi created_at: server_default vẫn chạy

    # Không tính vào "hoàn thành hôm nay".
    agenda = (await client.get("/api/v1/tasks/agenda", params={"view": "all"})).json()
    assert agenda["completed_today"] == []


@pytest.mark.db
async def test_completed_at_on_update_transitions(client: httpx.AsyncClient) -> None:
    await client.post(URL, json=_batch([_item("J-1"), _item("J-2")]))
    before = clock.now_utc()
    await client.post(
        URL,
        json=_batch(
            [
                _item("J-1", status="done", completed_at="2021-05-06T07:08:09Z"),
                _item("J-2", status="done"),
            ]
        ),
    )
    (t1,) = await _tasks("J-1")
    (t2,) = await _tasks("J-2")
    assert t1.completed_at == datetime(2021, 5, 6, 7, 8, 9, tzinfo=UTC)
    assert t2.completed_at is not None and t2.completed_at >= before  # không có mốc: now()
    # Đối chứng cho test "không tính hôm nay": J-2 (now) có mặt, J-1 (2021) thì không.
    agenda = (await client.get("/api/v1/tasks/agenda", params={"view": "all"})).json()
    assert [t["external_id"] for t in agenda["completed_today"]] == ["J-2"]
    # Mở lại: xoá completed_at.
    await client.post(URL, json=_batch([_item("J-1", status="todo")]))
    (t1,) = await _tasks("J-1")
    assert t1.completed_at is None


@pytest.mark.db
async def test_closed_task_without_completed_at_gets_it_filled_once(
    client: httpx.AsyncClient,
) -> None:
    await client.post(URL, json=_batch([_item("J-1", status="done")]))
    sent = _batch([_item("J-1", status="done", completed_at="2020-01-02T03:04:05Z")])
    first = (await client.post(URL, json=sent)).json()
    assert first["updated"] == 1
    (t,) = await _tasks("J-1")
    assert t.completed_at == datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    second = (await client.post(URL, json=sent)).json()
    assert second["unchanged"] == 1


@pytest.mark.db
async def test_naive_datetimes_use_display_timezone(client: httpx.AsyncClient) -> None:
    await client.post(
        URL,
        json=_batch(
            [
                _item(
                    "J-1",
                    status="done",
                    due_at="2026-03-01T09:00:00",
                    completed_at="2026-03-01T10:00:00",
                    created_at="2026-02-01T08:00:00",
                )
            ]
        ),
    )
    (t,) = await _tasks("J-1")
    tz = clock.display_tz()
    assert t.due_at == datetime(2026, 3, 1, 9, tzinfo=tz)
    assert t.completed_at == datetime(2026, 3, 1, 10, tzinfo=tz)
    assert t.created_at == datetime(2026, 2, 1, 8, tzinfo=tz)


# ── raw_payload: cảnh báo, lọc giá trị, NaN, ngân sách ──────────────


@pytest.mark.db
async def test_oversize_payload_still_updates_task_and_warns(client: httpx.AsyncClient) -> None:
    await client.post(URL, json=_batch([_item("J-1", raw_payload={"v": 1})]))
    big = {"blob": "x" * (MAX_RAW_PAYLOAD_BYTES + 10)}
    res = (await client.post(URL, json=_batch([_item("J-1", title="Mới", raw_payload=big)]))).json()
    assert res["updated"] == 1 and res["errors"] == []
    assert [w["index"] for w in res["warnings"]] == [0]
    (t,) = await _tasks("J-1")
    assert t.title == "Mới"
    assert t.raw_payload == {"v": 1}  # giữ payload cũ, không ghi payload hỏng


@pytest.mark.db
async def test_huge_payload_behind_sensitive_key_and_deep_payload_warn(
    client: httpx.AsyncClient,
) -> None:
    deep: dict[str, Any] = {}
    cur = deep
    for _ in range(60):
        cur["a"] = {}
        cur = cur["a"]
    res = (
        await client.post(
            URL,
            json=_batch(
                [
                    _item("J-1", raw_payload={"token": "x" * 400_000, "ok": 1}),
                    _item("J-2", raw_payload=deep),
                ]
            ),
        )
    ).json()
    assert res["added"] == 2 and res["errors"] == []
    assert [w["index"] for w in res["warnings"]] == [0, 1]
    assert "thô" in res["warnings"][0]["reason"] and "sâu" in res["warnings"][1]["reason"]
    assert (await _tasks("J-1"))[0].raw_payload is None
    assert (await _tasks("J-2"))[0].raw_payload is None


@pytest.mark.db
async def test_batch_payload_budget(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(task_sync_service, "MAX_BATCH_PAYLOAD_BYTES", 5_000)
    items = [_item(f"J-{i}", raw_payload={"d": "y" * 2_000}) for i in range(4)]
    res = (await client.post(URL, json=_batch(items))).json()
    assert res["added"] == 4 and res["errors"] == []
    assert [w["index"] for w in res["warnings"]] == [2, 3]
    assert all("lô" in w["reason"] for w in res["warnings"])
    assert (await _tasks("J-1"))[0].raw_payload is not None
    assert (await _tasks("J-2"))[0].raw_payload is None


def test_sanitize_redacts_secret_values_and_name_value_lists() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.abc_DEF-123"
    raw = {
        "comment": f"dùng header Authorization: Bearer abc.def-123 nhé; {jwt}",
        "link": "https://x.example.com/a?id=1&access_token=SEKRET&b=2 và ?token=ZZZ",
        "headers": [
            {"name": "X-Session-Id", "value": "s3ss"},
            {"name": "Accept", "value": "json"},
        ],
        "auth": "basic abc",
        "author": "me",
        "creds": {"credential": "c", "private_key": "k", "csrf": "1", "jwt": "j", "pwd": "p"},
        "meta": {"Signature": "sig", "xsrf-token": "x", "Session": "s", "keep": 1},
    }
    clean = sanitize_payload(raw)
    assert clean["comment"] == "dùng header Authorization: Bearer [REDACTED] nhé; [REDACTED]"
    assert clean["link"] == (
        "https://x.example.com/a?id=1&access_token=[REDACTED]&b=2 và ?token=[REDACTED]"
    )
    assert clean["headers"] == [{"name": "X-Session-Id"}, {"name": "Accept", "value": "json"}]
    assert "auth" not in clean and clean["author"] == "me"  # "auth" khớp chính xác
    assert clean["creds"] == {}
    assert clean["meta"] == {"keep": 1}
    blob = json.dumps(clean)
    for leak in ("abc.def-123", "SEKRET", "ZZZ", "eyJhbGci", "s3ss"):
        assert leak not in blob


@pytest.mark.db
async def test_non_finite_numbers_are_item_errors_not_500(client: httpx.AsyncClient) -> None:
    body = (
        '{"source":"jira","items":['
        '{"external_id":"J-1","title":"a","raw_payload":{"x":NaN}},'
        '{"external_id":"J-2","title":"b","raw_payload":{"y":[1,Infinity]}},'
        '{"external_id":"J-3","title":"c"}]}'
    )
    resp = await client.post(URL, content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["added"] == 1
    assert [e["index"] for e in res["errors"]] == [0, 1]
    assert await _tasks("J-1") == []


def test_prepare_payload_dropped_is_valueerror_subclass() -> None:
    assert issubclass(PayloadDropped, ValueError)
    with pytest.raises(ValueError, match="không hữu hạn") as exc:
        prepare_payload({"a": float("nan")})
    assert not isinstance(exc.value, PayloadDropped)


# ── Body, độ dài, URL ───────────────────────────────────────────────


@pytest.mark.db
async def test_body_over_cap_is_413(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capped, "MAX_UPSERT_BODY_BYTES", 2_000)
    ok = await client.post(URL, json=_batch([_item("J-1")]))
    assert ok.status_code == 200
    big = _batch([_item("J-2", raw_payload={"d": "z" * 5_000})])
    assert (await client.post(URL, json=big)).status_code == 413

    # Chunked (không có Content-Length): vẫn bị chặn theo luồng.
    async def chunks() -> Any:
        payload = json.dumps(big).encode()
        for i in range(0, len(payload), 500):
            yield payload[i : i + 500]

    resp = await client.post(URL, content=chunks(), headers={"Content-Type": "application/json"})
    assert resp.status_code == 413
    assert await _tasks("J-2") == []


@pytest.mark.db
async def test_description_and_title_length_limits(client: httpx.AsyncClient) -> None:
    ok = await client.post(URL, json=_batch([_item("J-1", description="d" * 32_000)]))
    assert ok.status_code == 200
    long_desc = await client.post(URL, json=_batch([_item("J-2", description="d" * 32_001)]))
    assert long_desc.status_code == 422
    long_title = await client.post(URL, json=_batch([_item("J-3", title="t" * 501)]))
    assert long_title.status_code == 422


@pytest.mark.db
@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<b>x</b>",
        "ftp://x.example.com/a",
        "file:///etc/passwd",
    ],
)
async def test_external_url_rejects_non_http(client: httpx.AsyncClient, url: str) -> None:
    resp = await client.post(URL, json=_batch([_item("J-1", external_url=url)]))
    assert resp.status_code == 422
    assert await _tasks() == []


@pytest.mark.db
async def test_external_url_accepts_http_and_https(client: httpx.AsyncClient) -> None:
    items = [
        _item("J-1", external_url="https://acme.atlassian.net/browse/J-1"),
        _item("J-2", external_url="http://wiki.example.com/x"),
    ]
    assert (await client.post(URL, json=_batch(items))).json()["added"] == 2


# ── Khoá, race ──────────────────────────────────────────────────────


@pytest.mark.db
async def test_batch_gets_409_while_import_holds_lock(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(locks, "DEFAULT_LOCK_TIMEOUT", "200ms")
    async with SessionFactory() as holder:
        await holder.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:n))"), {"n": locks.IMPORT_LOCK_NAME}
        )
        resp = await client.post(URL, json=_batch([_item("J-1")]))
        await holder.rollback()
    assert resp.status_code == 409, resp.text
    assert await _tasks() == []
    assert (await client.post(URL, json=_batch([_item("J-1")]))).status_code == 200


@pytest.mark.db
async def test_batch_gets_409_when_task_row_is_locked(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await client.post(URL, json=_batch([_item("J-1")]))
    (task,) = await _tasks("J-1")
    monkeypatch.setattr(locks, "DEFAULT_LOCK_TIMEOUT", "200ms")
    async with SessionFactory() as holder:
        await holder.execute(text("SELECT 1 FROM tasks WHERE id = :i FOR UPDATE"), {"i": task.id})
        resp = await client.post(URL, json=_batch([_item("J-1", title="Chen ngang")]))
        await holder.rollback()
    assert resp.status_code == 409, resp.text
    assert (await _tasks("J-1"))[0].title == "Việc J-1"


@pytest.mark.db
async def test_unique_violation_on_flush_is_409(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await client.post(URL, json=_batch([_item("J-1")]))

    async def blind(*_: Any, **__: Any) -> dict[str, Task]:
        return {}  # như thể bên khác vừa tạo J-1 sau lúc ta đọc

    monkeypatch.setattr(task_sync_service, "_fetch_alive", blind)
    resp = await client.post(URL, json=_batch([_item("J-1", title="Trùng"), _item("J-2")]))
    assert resp.status_code == 409, resp.text
    assert "thử lại" in resp.json()["detail"]
    assert len(await _tasks()) == 1  # lô bị rollback hoàn toàn


@pytest.mark.db
async def test_other_integrity_errors_are_not_reported_as_409(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CHECK title_not_blank: lỗi khác tên constraint không được nhận nhầm thành 409."""
    original = task_sync_service._build_task

    def blank_title(*args: Any, **kwargs: Any) -> Task:
        task = original(*args, **kwargs)
        task.title = "   "
        return task

    monkeypatch.setattr(task_sync_service, "_build_task", blank_title)
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await client.post(URL, json=_batch([_item("J-1")]))


@pytest.mark.db
async def test_projects_created_in_one_statement_and_race_safe(
    client: httpx.AsyncClient,
) -> None:
    items = [_item(f"J-{i}", project_key=f"P{i % 5}") for i in range(20)]
    results = await asyncio.gather(
        *(client.post(URL, json=_batch(items)) for _ in range(3)), return_exceptions=True
    )
    assert all(not isinstance(r, Exception) and r.status_code == 200 for r in results)
    async with SessionFactory() as s:
        keys = sorted((await s.execute(select(Project.key))).scalars())
    assert keys == ["P0", "P1", "P2", "P3", "P4"]


# ── Luật personal / project / project_key null ──────────────────────


@pytest.mark.db
async def test_personal_roundtrip_through_patch(client: httpx.AsyncClient) -> None:
    sent = _batch([_item("J-1", title="Từ Jira")])
    assert (await client.post(URL, json=sent)).json()["added"] == 1
    (task,) = await _tasks("J-1")
    assert task.scope.value == "work"

    assert (
        await client.patch(f"/api/v1/tasks/{task.id}", json={"scope": "personal"})
    ).status_code == 200
    changed = _batch([_item("J-1", title="Jira đổi tên")])
    for _ in range(2):
        res = (await client.post(URL, json=changed)).json()
        assert res["skipped_personal"] == 1 and res["updated"] == 0 and res["added"] == 0
    (task,) = await _tasks("J-1")
    assert task.title == "Từ Jira" and task.scope.value == "personal"
    assert len(await _tasks()) == 1

    assert (
        await client.patch(f"/api/v1/tasks/{task.id}", json={"scope": "work"})
    ).status_code == 200
    res = (await client.post(URL, json=changed)).json()
    assert res["updated"] == 1 and res["skipped_personal"] == 0
    assert (await _tasks("J-1"))[0].title == "Jira đổi tên"


@pytest.mark.db
async def test_project_key_null_detaches_project_and_absent_keeps_it(
    client: httpx.AsyncClient,
) -> None:
    await client.post(URL, json=_batch([_item("J-1", project_key="abc", project_name="ABC")]))
    assert (await _tasks("J-1"))[0].project_id is not None
    # Vắng khoá: giữ nguyên.
    await client.post(URL, json=_batch([_item("J-1", title="Mới")]))
    assert (await _tasks("J-1"))[0].project_id is not None
    # null tường minh: gỡ project.
    res = (await client.post(URL, json=_batch([_item("J-1", project_key=None)]))).json()
    assert res["updated"] == 1
    assert (await _tasks("J-1"))[0].project_id is None


@pytest.mark.db
async def test_due_at_without_timezone_uses_display_timezone(client: httpx.AsyncClient) -> None:
    await client.post(URL, json=_batch([_item("J-1", due_at="2026-03-01T09:00:00")]))
    (t,) = await _tasks("J-1")
    expected = datetime(2026, 3, 1, 9, tzinfo=clock.display_tz())
    assert t.due_at == expected
    # Cùng thời điểm nhưng ghi dạng UTC tường minh: không đổi gì.
    same = expected.astimezone(UTC).isoformat()
    assert (await client.post(URL, json=_batch([_item("J-1", due_at=same)]))).json()[
        "unchanged"
    ] == 1


# ── Mật khẩu nhập (X-Import-Secret) ─────────────────────────────────


@pytest.mark.db
async def test_upsert_requires_import_secret(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    body = _batch([_item("J-1", raw_payload={"token": "LEAKME-123456"})])
    del client.headers["X-Import-Secret"]
    missing = await client.post(URL, json=body)
    wrong = await client.post(URL, json=body, headers={"X-Import-Secret": "sai-mat-khau-WRONG-1"})
    assert missing.status_code == 403 and wrong.status_code == 403
    # 403 đến trước validate body: body hỏng cũng chỉ thấy 403.
    assert (await client.post(URL, json={"source": "bogus"})).status_code == 403
    for resp in (missing, wrong):
        assert IMPORT_SECRET not in resp.text
        assert "WRONG" not in resp.text and "LEAKME" not in resp.text
    # Đối chiếu dương tính (xem test_import_api): log cảnh báo phải tồn tại.
    assert "nhập thật bị từ chối" in caplog.text
    assert IMPORT_SECRET not in caplog.text and "WRONG" not in caplog.text
    assert await _tasks() == []

    ok = await client.post(URL, json=body, headers={"X-Import-Secret": IMPORT_SECRET})
    assert ok.status_code == 200 and ok.json()["added"] == 1


@pytest.mark.db
async def test_upsert_rejected_when_secret_not_configured(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "import_commit_secret", None)
    resp = await client.post(URL, json=_batch([_item("J-1")]))
    assert resp.status_code == 403 and "IMPORT_COMMIT_SECRET" in resp.json()["detail"]
    assert await _tasks() == []
