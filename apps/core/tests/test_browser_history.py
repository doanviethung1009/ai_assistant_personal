"""Lịch sử duyệt web: chuẩn hoá URL/giờ (unit) và các endpoint qua HTTP (DB thật)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionFactory
from app.services.browser_history_service import (
    escape_like,
    normalize_url,
    to_utc,
    url_hash,
)
from tests.conftest import IMPORT_SECRET

BATCH = "/api/v1/browser-history/batch"
LIST = "/api/v1/browser-history"
IMPORT = "/api/v1/import/browser-history"


def _item(
    url: str, visits: int = 1, at: str = "2026-10-01T10:00:00+00:00", title: str = "T"
) -> dict:
    return {"url": url, "title": title, "visit_count": visits, "last_visit_at": at}


async def _count() -> int:
    async with SessionFactory() as s:
        return int(await s.scalar(text("SELECT count(*) FROM browser_history")) or 0)


# ── Unit (không cần DB) ─────────────────────────────────────────


def test_normalize_url_strips_query_fragment_userinfo() -> None:
    got = normalize_url("HTTPS://user:pw@Example.com:443/a/b?code=SECRET&x=1#frag")
    assert got == "https://example.com/a/b"
    assert normalize_url("http://example.com") == "http://example.com/"
    assert normalize_url("http://example.com:8080/x?y") == "http://example.com:8080/x"
    assert normalize_url("http://[::1]:3000/p") == "http://[::1]:3000/p"


@pytest.mark.parametrize(
    "bad",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "chrome://settings",
        "data:text/html,x",
        "ftp://example.com/",
        "http://",
        "not a url",
        "http://exa mple.com/",
        "http://a.com/\x00",
        "http://a.com/" + "x" * 5000,
    ],
)
def test_normalize_url_rejects_non_http(bad: str) -> None:
    assert normalize_url(bad) is None


def test_url_hash_ignores_query() -> None:
    a = normalize_url("https://a.com/p?x=1")
    b = normalize_url("https://a.com/p#y")
    assert a is not None and b is not None
    assert url_hash(a) == url_hash(b)


def test_to_utc_naive_uses_display_timezone() -> None:
    # display_timezone mặc định Asia/Ho_Chi_Minh = UTC+7, không DST.
    assert to_utc(datetime(2026, 10, 8, 14, 30)) == datetime(2026, 10, 8, 7, 30, tzinfo=UTC)
    aware = datetime(2026, 10, 8, 14, 30, tzinfo=UTC)
    assert to_utc(aware) == aware


def test_escape_like() -> None:
    assert escape_like("50%_a\\b") == "50\\%\\_a\\\\b"


# ── Endpoint ────────────────────────────────────────────────────


@pytest.mark.db
async def test_batch_is_idempotent_and_never_decreases(client: httpx.AsyncClient) -> None:
    payload = {
        "profile": "Default",
        "items": [_item("https://a.com/x?t=1", 5, "2026-10-02T00:00:00Z")],
    }
    first = (await client.post(BATCH, json=payload)).json()
    assert first == {"received": 1, "created": 1, "updated": 0, "unchanged": 0, "invalid": 0}
    again = (await client.post(BATCH, json=payload)).json()
    assert again["created"] == 0 and again["updated"] == 0 and again["unchanged"] == 1
    assert await _count() == 1

    # Lô cũ hơn/ít hơn không được làm lùi.
    older = {"profile": "Default", "items": [_item("https://a.com/x", 2, "2026-10-01T00:00:00Z")]}
    assert (await client.post(BATCH, json=older)).json()["unchanged"] == 1
    row = (await client.get(LIST)).json()["items"][0]
    assert row["visit_count"] == 5
    assert row["last_visit_at"].startswith("2026-10-02T00:00:00")
    assert row["url"] == "https://a.com/x"

    # Lô mới hơn thì tăng.
    newer = {
        "profile": "Default",
        "items": [_item("https://a.com/x#z", 9, "2026-10-03T00:00:00Z", "Mới")],
    }
    assert (await client.post(BATCH, json=newer)).json()["updated"] == 1
    row = (await client.get(LIST)).json()["items"][0]
    assert row["visit_count"] == 9 and row["title"] == "Mới"
    assert await _count() == 1


@pytest.mark.db
async def test_batch_dedupes_within_batch_and_counts_invalid(client: httpx.AsyncClient) -> None:
    payload = {
        "profile": "Default",
        "items": [
            _item("https://a.com/p?x=1", 3),
            _item("https://a.com/p?x=2", 7),
            _item("javascript:alert(1)"),
        ],
    }
    body = (await client.post(BATCH, json=payload)).json()
    assert body["received"] == 3 and body["created"] == 1 and body["invalid"] == 1
    assert (await client.get(LIST)).json()["items"][0]["visit_count"] == 7


@pytest.mark.db
async def test_batch_naive_time_is_display_timezone(client: httpx.AsyncClient) -> None:
    payload = {"profile": "Default", "items": [_item("https://a.com/", 1, "2026-10-08T14:30:00")]}
    await client.post(BATCH, json=payload)
    got = (await client.get(LIST)).json()["items"][0]["last_visit_at"]
    assert datetime.fromisoformat(got) == datetime(2026, 10, 8, 7, 30, tzinfo=UTC)


@pytest.mark.db
async def test_batch_limits_and_validation(client: httpx.AsyncClient) -> None:
    ok = {"profile": "Default", "items": [_item(f"https://a.com/{i}") for i in range(10_000)]}
    assert (await client.post(BATCH, json=ok)).status_code == 200
    assert await _count() == 10_000
    too_many = {"profile": "Default", "items": [_item(f"https://b.com/{i}") for i in range(10_001)]}
    assert (await client.post(BATCH, json=too_many)).status_code == 422
    assert await _count() == 10_000
    for profile in ["/home/u/Chrome/Default", "C:\\Users\\u", "a/b", "..", "", "x\ny"]:
        resp = await client.post(BATCH, json={"profile": profile, "items": []})
        assert resp.status_code == 422, profile
    neg = {"profile": "Default", "items": [_item("https://a.com/", -1)]}
    assert (await client.post(BATCH, json=neg)).status_code == 422


@pytest.mark.db
async def test_list_paginates_filters_and_escapes_like(client: httpx.AsyncClient) -> None:
    items = [
        _item(f"https://a.com/{i}", 1, f"2026-10-{i + 1:02d}T00:00:00Z", f"Trang {i}")
        for i in range(5)
    ]
    items.append(_item("https://a.com/100%25_off", 1, "2026-09-01T00:00:00Z", "Giam 100% _ gia"))
    await client.post(BATCH, json={"profile": "Default", "items": items})
    await client.post(BATCH, json={"profile": "Work", "items": [_item("https://w.com/", 1)]})

    page1 = (await client.get(LIST, params={"limit": 2, "offset": 0})).json()
    assert page1["total"] == 7 and len(page1["items"]) == 2
    assert page1["items"][0]["url"] == "https://a.com/4"  # mới nhất trước
    page2 = (await client.get(LIST, params={"limit": 2, "offset": 2})).json()
    assert {r["id"] for r in page1["items"]}.isdisjoint({r["id"] for r in page2["items"]})

    assert (await client.get(LIST, params={"profile": "Work"})).json()["total"] == 1
    # '%' và '_' là ký tự thường, không phải wildcard.
    assert (await client.get(LIST, params={"q": "%"})).json()["total"] == 1
    assert (await client.get(LIST, params={"q": "100% _"})).json()["total"] == 1
    assert (await client.get(LIST, params={"q": "_"})).json()["total"] == 1
    assert (await client.get(LIST, params={"q": "TRANG 3"})).json()["total"] == 1
    assert (await client.get(LIST, params={"limit": 101})).status_code == 422


@pytest.mark.db
async def test_delete_by_profile(client: httpx.AsyncClient) -> None:
    await client.post(BATCH, json={"profile": "Default", "items": [_item("https://a.com/")]})
    await client.post(BATCH, json={"profile": "Work", "items": [_item("https://a.com/")]})
    sec = {"X-Import-Secret": IMPORT_SECRET}
    assert (await client.delete(LIST, headers=sec)).status_code == 422  # profile bắt buộc
    bad = await client.delete(LIST, params={"profile": "../x"}, headers=sec)
    assert bad.status_code == 422
    resp = await client.delete(LIST, params={"profile": "Work"}, headers=sec)
    assert resp.json() == {"deleted": 1}
    assert await _count() == 1
    assert (await client.get(LIST)).json()["items"][0]["profile"] == "Default"


@pytest.mark.db
async def test_delete_requires_import_secret(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await client.post(BATCH, json={"profile": "Default", "items": [_item("https://a.com/")]})
    params = {"profile": "Default"}
    assert (await client.delete(LIST, params=params)).status_code == 403
    wrong = {"X-Import-Secret": "sai-mat-khau-sai-mat-khau"}
    assert (await client.delete(LIST, params=params, headers=wrong)).status_code == 403
    assert await _count() == 1

    # Chưa cấu hình IMPORT_COMMIT_SECRET: bị từ chối như nhập thật, kể cả gửi header.
    monkeypatch.setattr(settings, "import_commit_secret", None)
    good = {"X-Import-Secret": IMPORT_SECRET}
    assert (await client.delete(LIST, params=params, headers=good)).status_code == 403
    assert await _count() == 1
    monkeypatch.undo()

    assert (await client.delete(LIST, params=params, headers=good)).json() == {"deleted": 1}
    assert await _count() == 0


@pytest.mark.db
async def test_title_not_overwritten_by_older_or_empty(client: httpx.AsyncClient) -> None:
    u = "https://a.com/t"
    await client.post(
        BATCH, json={"profile": "Default", "items": [_item(u, 5, "2026-10-05T00:00:00Z", "Gốc")]}
    )
    # Lô cũ hơn có title khác: không đè.
    older = _item(u, 9, "2026-10-01T00:00:00Z", "Cũ")
    await client.post(BATCH, json={"profile": "Default", "items": [older]})
    row = (await client.get(LIST)).json()["items"][0]
    assert row["title"] == "Gốc" and row["visit_count"] == 9
    # Lô mới hơn nhưng title rỗng: không xoá title.
    newer = _item(u, 10, "2026-10-06T00:00:00Z", "")
    await client.post(BATCH, json={"profile": "Default", "items": [newer]})
    row = (await client.get(LIST)).json()["items"][0]
    assert row["title"] == "Gốc" and row["visit_count"] == 10


@pytest.mark.db
async def test_partial_update_keeps_last_visit(client: httpx.AsyncClient) -> None:
    u = "https://a.com/p"
    await client.post(
        BATCH, json={"profile": "Default", "items": [_item(u, 1, "2026-10-05T00:00:00Z")]}
    )
    more = {"profile": "Default", "items": [_item(u, 7, "2026-10-01T00:00:00Z")]}
    got = (await client.post(BATCH, json=more)).json()
    assert got["updated"] == 1 and got["unchanged"] == 0
    row = (await client.get(LIST)).json()["items"][0]
    assert row["visit_count"] == 7
    assert row["last_visit_at"].startswith("2026-10-05T00:00:00")


@pytest.mark.db
async def test_dry_run_and_commit_report_same_counts(client: httpx.AsyncClient) -> None:
    hdr = {"Content-Type": "application/json", "X-Import-Secret": IMPORT_SECRET}
    seed = [
        _item("https://s.com/same", 3, "2026-10-05T00:00:00Z"),
        _item("https://s.com/up", 1, "2026-10-05T00:00:00Z"),
    ]
    await client.post(BATCH, json={"profile": "Default", "items": seed})
    rows = [
        {"url": "https://s.com/same", "visit_count": 3, "last_visit_time": "2026-10-05T07:00:00"},
        {"url": "https://s.com/up", "visit_count": 4, "last_visit_time": "2026-10-06T07:00:00"},
        {"url": "https://s.com/new", "visit_count": 1, "last_visit_time": "2026-10-06T07:00:00"},
    ]
    content = json.dumps({"items": rows}).encode()
    dry = (await client.post(IMPORT, content=content, headers=hdr)).json()
    real = (
        await client.post(IMPORT, params={"dry_run": "false"}, content=content, headers=hdr)
    ).json()
    keys = ("received", "created", "updated", "unchanged", "invalid")
    assert {k: dry[k] for k in keys} == {k: real[k] for k in keys}
    assert (real["created"], real["updated"], real["unchanged"]) == (1, 1, 1)
    assert await _count() == 3


@pytest.mark.db
async def test_large_batch_mixes_insert_and_conflict(client: httpx.AsyncClient) -> None:
    first = [_item(f"https://m.com/{i}", 1, "2026-10-01T00:00:00Z") for i in range(0, 3000, 2)]
    await client.post(BATCH, json={"profile": "Default", "items": first})
    allrows = [_item(f"https://m.com/{i}", 2, "2026-10-02T00:00:00Z") for i in range(3000)]
    got = (await client.post(BATCH, json={"profile": "Default", "items": allrows})).json()
    assert got["created"] == 1500 and got["updated"] == 1500 and got["unchanged"] == 0
    assert await _count() == 3000


@pytest.mark.db
async def test_get_rejects_bad_profile(client: httpx.AsyncClient) -> None:
    assert (await client.get(LIST, params={"profile": "../x"})).status_code == 422


@pytest.mark.db
async def test_long_url_counts_invalid_and_422_hides_input(client: httpx.AsyncClient) -> None:
    long_url = "https://a.com/" + "x" * 5000
    ok = await client.post(BATCH, json={"profile": "Default", "items": [_item(long_url)]})
    assert ok.status_code == 200 and ok.json()["invalid"] == 1
    secret_url = "https://a.com/reset?token=SUPERSECRET"  # noqa: S105
    bad = {"profile": "Default", "items": [{**_item(secret_url), "visit_count": -1}]}
    resp = await client.post(BATCH, json=bad)
    assert resp.status_code == 422
    assert "SUPERSECRET" not in resp.text and "input" not in resp.text


def _chrome_file() -> bytes:
    return json.dumps(
        {
            "synced_at": "2026-10-08T07:00:00.000Z",
            "source_path": "/Users/me/Library/Application Support/Google/Chrome/Default/History",
            "items": [
                {
                    "url": "https://a.com/p?token=1",
                    "title": "A",
                    "visit_count": 4,
                    "last_visit_time": "2026-10-08 14:30:00",
                },
                {
                    "url": "chrome://settings",
                    "title": "S",
                    "visit_count": 1,
                    "last_visit_time": "2026-10-08 14:30:00",
                },
                {"url": "https://b.com/", "title": "B", "visit_count": 1, "last_visit_time": "bậy"},
            ],
        }
    ).encode()


@pytest.mark.db
async def test_import_dry_run_writes_nothing_then_commit_is_idempotent(
    client: httpx.AsyncClient,
) -> None:
    hdr = {"Content-Type": "application/json"}
    dry = await client.post(IMPORT, content=_chrome_file(), headers=hdr)
    assert dry.status_code == 200
    body = dry.json()
    assert body["dry_run"] is True and body["committed"] is False
    assert body["created"] == 1 and body["invalid"] == 2 and body["received"] == 3
    assert body["profile"] == "Default"
    assert await _count() == 0

    # Nhập thật thiếu / sai mật khẩu.
    commit = {"dry_run": "false"}
    assert (
        await client.post(IMPORT, params=commit, content=_chrome_file(), headers=hdr)
    ).status_code == 403
    bad = {**hdr, "X-Import-Secret": "sai-mat-khau-sai-mat-khau"}
    assert (
        await client.post(IMPORT, params=commit, content=_chrome_file(), headers=bad)
    ).status_code == 403
    assert await _count() == 0

    good = {**hdr, "X-Import-Secret": IMPORT_SECRET}
    real = (await client.post(IMPORT, params=commit, content=_chrome_file(), headers=good)).json()
    assert real["committed"] is True and real["created"] == 1
    again = (await client.post(IMPORT, params=commit, content=_chrome_file(), headers=good)).json()
    assert again["created"] == 0 and again["unchanged"] == 1
    assert await _count() == 1

    row = (await client.get(LIST)).json()["items"][0]
    assert row["url"] == "https://a.com/p"
    assert datetime.fromisoformat(row["last_visit_at"]) == datetime(2026, 10, 8, 7, 30, tzinfo=UTC)
    # Đường dẫn tuyệt đối trong file không được lọt vào đâu cả.
    async with SessionFactory() as s:
        dump = await s.scalar(text("SELECT string_agg(t::text, ' ') FROM browser_history t"))
    assert "Library" not in (dump or "")


@pytest.mark.db
async def test_import_rejects_bad_profile_and_non_object_body(
    client: httpx.AsyncClient,
) -> None:
    hdr = {"Content-Type": "application/json"}
    resp = await client.post(
        IMPORT, params={"profile": "/abs/path"}, content=_chrome_file(), headers=hdr
    )
    assert resp.status_code == 422
    resp = await client.post(IMPORT, content=b"[]", headers=hdr)
    assert resp.status_code == 422


@pytest.mark.db
async def test_import_rejects_oversize_body(client: httpx.AsyncClient) -> None:
    hdr = {"Content-Type": "application/json"}
    big = b'{"items": [], "pad": "' + b"x" * (10 * 1024 * 1024) + b'"}'
    resp = await client.post(IMPORT, content=big, headers=hdr)
    assert resp.status_code == 413
