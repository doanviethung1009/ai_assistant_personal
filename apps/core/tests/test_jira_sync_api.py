"""POST /integrations/{id}/sync (B4b): luồng đầy đủ với Jira giả, trên Postgres thật.

Không mạng thật. Hai kiểu giả:
- `httpx.MockTransport` thay `build_transport` khi chỉ cần kiểm logic.
- `PinnedTransport` thật + resolver giả + backend mạng giả khi cần kiểm chốt SSRF qua
  endpoint (DNS trả IP nội bộ, on-prem, rebinding).
"""

# ruff: noqa: S106 - next_token là con trỏ phân trang giả, không phải mật khẩu
from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpcore
import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select, text

from app.core.config import settings
from app.db.session import SessionFactory
from app.models.integration import IntegrationConnection
from app.models.task import Task, TaskEvent
from app.services import integration_sync_service, jira_client
from app.services.ssrf_guard import NETWORK_ERROR_MESSAGE, PinnedTransport, _FixedIPBackend
from tests.conftest import IMPORT_SECRET

pytestmark = pytest.mark.db

TOKEN = "ATATT3xFfGF0-fake-token-ZZ9876"  # noqa: S105
BASE = "https://acme.atlassian.net"
NAME = "Jira công ty"
SECRET_BODY = "JIRA-BODY-SECRET-DO-NOT-ECHO"  # noqa: S105
AUTH_B64 = base64.b64encode(f"me@acme.com:{TOKEN}".encode()).decode()
HEADERS = {"X-Import-Secret": IMPORT_SECRET}
PUBLIC_IP = "104.192.140.1"

Handler = Callable[[httpx.Request], Any]


def _issue(key: str, **over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "summary": f"Việc {key}",
        "status": {"name": "To Do"},
        "priority": {"name": "Medium"},
        "assignee": {"displayName": "Hùng"},
        "labels": ["be"],
        "project": {"key": "DBA", "name": "Database Admin"},
        "created": "2026-01-10T09:30:00.000+0700",
        "updated": "2026-02-01T10:00:00.000+0700",
    }
    fields.update(over)
    return {"id": "1", "key": key, "fields": fields}


def _page(*issues: dict[str, Any], next_token: str | None = None) -> httpx.Response:
    body: dict[str, Any] = {"issues": list(issues), "names": {}, "isLast": next_token is None}
    if next_token:
        body["nextPageToken"] = next_token
    return httpx.Response(200, json=body)


@pytest.fixture
def jira(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], list[httpx.Request]]:
    """Gắn một handler Jira giả vào service; trả danh sách request đã nhận."""

    def install(handler: Handler) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        async def wrapped(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path == "/rest/api/3/field":
                return httpx.Response(200, json=[])  # tra cứu custom field, không tính vào `seen`
            seen.append(request)
            result = handler(request)
            if asyncio.iscoroutine(result):
                result = await result
            return result  # type: ignore[no-any-return]

        monkeypatch.setattr(
            integration_sync_service, "build_transport", lambda host: httpx.MockTransport(wrapped)
        )
        return seen

    return install


async def _create(client: httpx.AsyncClient, **over: Any) -> str:
    body: dict[str, Any] = {
        "name": NAME,
        "base_url": BASE,
        "account_email": "me@acme.com",
        "token": TOKEN,
        "config": {"jql": "project = DBA"},
    }
    body.update(over)
    resp = await client.post("/api/v1/integrations", json=body)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def _sync_url(cid: str, since: str | None = None) -> str:
    url = f"/api/v1/integrations/{cid}/sync"
    return f"{url}?since={since}" if since else url


async def _tasks() -> list[Task]:
    async with SessionFactory() as s:
        return list((await s.execute(select(Task).order_by(Task.external_id))).scalars())


async def _last_sync(cid: str) -> Any:
    async with SessionFactory() as s:
        conn = await s.get(IntegrationConnection, uuid.UUID(cid))
        assert conn is not None
        return conn.last_sync_at


# ═══════════════════════════════════════════════════════════════════════
#  Xác thực, kiểm tra đầu vào
# ═══════════════════════════════════════════════════════════════════════


async def test_import_secret_is_required(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    seen = jira(lambda r: _page())
    cid = await _create(client)
    missing = await client.post(_sync_url(cid))
    wrong = await client.post(_sync_url(cid), headers={"X-Import-Secret": "WRONG-secret-value-000"})
    assert missing.status_code == 403 and wrong.status_code == 403
    assert "WRONG" not in wrong.text and IMPORT_SECRET not in wrong.text
    assert seen == []  # không gọi Jira khi chưa qua cổng
    # 403 đến trước cả 422 của since.
    bad = await client.post(_sync_url(cid, "garbage"))
    assert bad.status_code == 403


async def test_invalid_since_is_422_and_makes_no_jira_call(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    seen = jira(lambda r: _page())
    cid = await _create(client)
    for bad in ("yesterday", "2026-13-40", "x%22%20OR%201=1", "2000-01-01T00:00:00Zjunk"):
        resp = await client.post(_sync_url(cid, bad), headers=HEADERS)
        assert resp.status_code == 422, bad
    assert seen == []


async def test_unknown_connection_is_404(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    jira(lambda r: _page())
    resp = await client.post(_sync_url(str(uuid.uuid4())), headers=HEADERS)
    assert resp.status_code == 404


async def test_missing_token_is_409_with_guidance(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    seen = jira(lambda r: _page())
    cid = await _create(client, token=None)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 409
    assert "token" in resp.json()["detail"]
    assert seen == []


async def test_no_jql_and_no_current_users_is_422(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    seen = jira(lambda r: _page())
    cid = await _create(client, config={})
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 422 and "current_users" in resp.json()["detail"]
    assert seen == []


async def test_default_jql_uses_current_users(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    seen = jira(lambda r: _page())
    put = await client.put(
        "/api/v1/settings/current-users", json={"names": ['Hùng "Đoàn"', "x\\y"]}
    )
    assert put.status_code == 200, put.text
    cid = await _create(client, config={})
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    import json

    jql = json.loads(seen[0].content)["jql"]
    assert jql == 'assignee in ("Hùng \\"Đoàn\\"", "x\\\\y") ORDER BY updated DESC'


async def test_since_becomes_relative_window_in_jql(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    seen = jira(lambda r: _page())
    cid = await _create(client)
    resp = await client.post(_sync_url(cid, "2026-01-01"), headers=HEADERS)
    assert resp.status_code == 200
    import json

    jql = json.loads(seen[0].content)["jql"]
    assert jql.startswith("(project = DBA) AND updated >= -") and jql.endswith(
        "m ORDER BY updated DESC"
    )


# ═══════════════════════════════════════════════════════════════════════
#  Kết quả, idempotent, scope, actor
# ═══════════════════════════════════════════════════════════════════════


async def test_sync_creates_tasks_and_is_idempotent(
    client: httpx.AsyncClient, jira, caplog
) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        if "nextPageToken" not in json.loads(request.content):
            return _page(
                _issue("DBA-1", status={"name": "In Progress"}),
                _issue("DBA-2"),
                next_token="n",
            )
        return _page(
            _issue("DBA-3", status={"name": "Done"}, resolutiondate="2026-02-02T08:00:00.000+0000"),
            _issue("DBA-2"),  # lặp giữa các trang: bỏ qua êm
            {"id": "9", "key": "bad key", "fields": {}},  # issue hỏng: vào errors
        )

    jira(handler)
    cid = await _create(client)
    caplog.set_level(logging.DEBUG)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["fetched"] == 5 and data["pages"] == 2
    assert (data["added"], data["updated"], data["unchanged"]) == (3, 0, 0)
    assert data["skipped_personal"] == 0 and data["truncated"] is False
    assert [e["index"] for e in data["errors"]] == [4]
    assert "bad key" not in resp.text

    tasks = await _tasks()
    assert [t.external_id for t in tasks] == ["DBA-1", "DBA-2", "DBA-3"]
    assert tasks[0].status.value == "in_progress"
    assert tasks[2].status.value == "done" and tasks[2].completed_at is not None
    assert tasks[0].source.value == "jira" and tasks[0].scope.value == "work"
    assert tasks[0].external_url == f"{BASE}/browse/DBA-1"
    assert tasks[0].raw_payload is not None and "description" not in str(tasks[0].raw_payload)
    assert await _last_sync(cid) is not None

    again = await client.post(_sync_url(cid), headers=HEADERS)
    assert again.status_code == 200
    d2 = again.json()
    assert (d2["added"], d2["updated"], d2["unchanged"]) == (0, 0, 3)

    # Token (và dạng base64 của header) không xuất hiện ở response lẫn log, kể cả DEBUG.
    for blob in (resp.text, again.text, caplog.text):
        assert TOKEN not in blob and AUTH_B64 not in blob


async def test_events_carry_connection_name_as_actor(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    jira(lambda r: _page(_issue("DBA-1")))
    cid = await _create(client)
    await client.post(_sync_url(cid), headers=HEADERS)
    jira(lambda r: _page(_issue("DBA-1", summary="Đã đổi tên")))
    again = await client.post(_sync_url(cid), headers=HEADERS)
    assert again.json()["updated"] == 1
    async with SessionFactory() as s:
        actors = {e.actor for e in (await s.execute(select(TaskEvent))).scalars()}
    assert actors == {f"integration:{NAME}"}


async def test_personal_task_is_not_overwritten(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    jira(lambda r: _page(_issue("DBA-1")))
    cid = await _create(client)
    await client.post(_sync_url(cid), headers=HEADERS)
    async with SessionFactory() as s:
        await s.execute(text("UPDATE tasks SET scope='personal', title='Của riêng tôi'"))
        await s.commit()
    jira(lambda r: _page(_issue("DBA-1", summary="Jira đổi tên")))
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.json()["skipped_personal"] == 1 and resp.json()["added"] == 0
    assert (await _tasks())[0].title == "Của riêng tôi"


async def test_batches_of_at_most_1000(client: httpx.AsyncClient, jira, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sizes: list[int] = []
    real = integration_sync_service._write_batch

    async def spy(items, actor, owner_host):  # type: ignore[no-untyped-def]
        sizes.append(len(items))
        return await real(items, actor, owner_host)

    monkeypatch.setattr(integration_sync_service, "_write_batch", spy)
    jira(lambda r: _page(*[_issue(f"DBA-{i}") for i in range(1, 1202)]))
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 200 and resp.json()["added"] == 1201
    assert sizes == [1000, 201]


async def test_page_cap_truncates_and_keeps_last_sync_unset(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _page(_issue(f"DBA-{calls}"), next_token=f"t{calls}")

    jira(handler)
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    data = resp.json()
    assert resp.status_code == 200 and calls == 100
    assert data["pages"] == 100 and data["fetched"] == 100 and data["truncated"] is True
    assert any("trần" in w["reason"] for w in data["warnings"])
    assert await _last_sync(cid) is None


# ═══════════════════════════════════════════════════════════════════════
#  Lỗi Jira: thông báo tự viết, last_sync_at không đổi
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
async def test_jira_errors_have_own_message_and_leave_last_sync_unset(
    client: httpx.AsyncClient,
    jira,  # type: ignore[no-untyped-def]
    caplog,  # type: ignore[no-untyped-def]
    status: int,
) -> None:
    jira(lambda r: httpx.Response(status, text=f"{SECRET_BODY} {TOKEN}"))
    cid = await _create(client)
    caplog.set_level(logging.DEBUG)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert str(status) in detail
    for blob in (resp.text, caplog.text):
        assert SECRET_BODY not in blob and TOKEN not in blob and AUTH_B64 not in blob
    assert await _last_sync(cid) is None and await _tasks() == []


async def test_timeout_is_generic_network_error(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("t")

    jira(handler)
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 502 and resp.json()["detail"] == NETWORK_ERROR_MESSAGE


async def test_redirect_is_an_error_and_never_leaves_the_host(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    seen = jira(lambda r: httpx.Response(302, headers={"Location": "https://evil.example.com/x"}))
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 502 and "evil.example.com" not in resp.text
    assert [r.url.host for r in seen] == ["acme.atlassian.net"]


async def test_response_too_large(client: httpx.AsyncClient, jira, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(jira_client, "MAX_RESPONSE_BYTES", 500)
    jira(lambda r: httpx.Response(200, content=b'{"issues":[],"x":"' + b"a" * 2000 + b'"}'))
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 502 and "vượt" in resp.json()["detail"]


async def test_undecryptable_token_asks_to_re_enter(
    client: httpx.AsyncClient, jira, monkeypatch, caplog
) -> None:  # type: ignore[no-untyped-def]
    seen = jira(lambda r: _page())
    cid = await _create(client)
    monkeypatch.setattr(
        settings, "integration_secret_key", SecretStr(Fernet.generate_key().decode())
    )
    caplog.set_level(logging.DEBUG)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 503 and "nhập lại token" in resp.json()["detail"]
    assert seen == [] and TOKEN not in resp.text and TOKEN not in caplog.text
    # Khoá hỏng không làm kẹt khoá đồng thời: lần sau (đã sửa khoá) vẫn chạy được.
    monkeypatch.undo()
    jira(lambda r: _page())
    assert (await client.post(_sync_url(cid), headers=HEADERS)).status_code == 200


# ═══════════════════════════════════════════════════════════════════════
#  Đồng thời
# ═══════════════════════════════════════════════════════════════════════


async def test_concurrent_sync_of_same_connection_is_409(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        entered.set()
        await release.wait()
        return _page(_issue("DBA-1"))

    jira(handler)
    cid = await _create(client)
    first = asyncio.create_task(client.post(_sync_url(cid), headers=HEADERS))
    await asyncio.wait_for(entered.wait(), 10)
    second = await client.post(_sync_url(cid), headers=HEADERS)
    assert second.status_code == 409
    release.set()
    done = await asyncio.wait_for(first, 20)
    assert done.status_code == 200 and done.json()["added"] == 1
    # Xong thì khoá được nhả.
    third = await client.post(_sync_url(cid), headers=HEADERS)
    assert third.status_code == 200


async def test_lock_is_released_after_failure(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    jira(lambda r: httpx.Response(500))
    cid = await _create(client)
    assert (await client.post(_sync_url(cid), headers=HEADERS)).status_code == 502
    jira(lambda r: _page(_issue("DBA-1")))
    assert (await client.post(_sync_url(cid), headers=HEADERS)).status_code == 200


async def test_no_db_transaction_is_open_while_calling_jira(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    states: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        async with SessionFactory() as s:
            # Mọi phiên 'idle in transaction' của app trong lúc đang chờ Jira là vi phạm.
            n = await s.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND state LIKE 'idle in transaction%' "
                    "AND pid <> pg_backend_pid()"
                )
            )
        states.append(int(n or 0))
        return _page(_issue("DBA-1"))

    jira(handler)
    cid = await _create(client)
    assert (await client.post(_sync_url(cid), headers=HEADERS)).status_code == 200
    assert states == [0]


# ═══════════════════════════════════════════════════════════════════════
#  SSRF qua endpoint: PinnedTransport thật, resolver + backend giả
# ═══════════════════════════════════════════════════════════════════════


class Recorder(httpcore.AsyncMockBackend):
    """Mỗi kết nối TCP nhận một response riêng (GET /field rồi POST search)."""

    def __init__(self, responses: list[bytes]) -> None:
        super().__init__([])
        self._responses = list(responses)
        self.connects: list[str] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # type: ignore[no-untyped-def]  # noqa: ASYNC109
        self.connects.append(host)
        return httpcore.AsyncMockStream([self._responses.pop(0)])


def _http(status_line: str, body: bytes = b"", headers: str = "") -> bytes:
    head = f"HTTP/1.1 {status_line}\r\n{headers}Content-Length: {len(body)}\r\n\r\n"
    return head.encode() + body


def _install_pinned(monkeypatch: pytest.MonkeyPatch, answers: list[list[str]], buffer: list[bytes]):  # type: ignore[no-untyped-def]
    recorder = Recorder([_http("200 OK", b"[]"), *buffer])  # response đầu cho GET /field
    calls: list[str] = []

    async def resolver(host: str) -> list[str]:
        calls.append(host)
        return answers[min(len(calls), len(answers)) - 1]

    monkeypatch.setattr(
        integration_sync_service,
        "build_transport",
        lambda host: PinnedTransport(
            host,
            resolver=resolver,
            backend_factory=lambda ips: _FixedIPBackend(ips, inner=recorder),
        ),
    )
    return recorder, calls


_OK_BODY = b'{"issues": [], "isLast": true}'


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "169.254.169.254",
        "10.0.0.5",
        "192.168.1.10",
        "100.64.0.1",
        "::1",
        "::ffff:127.0.0.1",
        "fe80::1",
        "fd12::1",
    ],
)
async def test_dns_to_internal_address_is_blocked(
    client: httpx.AsyncClient, monkeypatch, ip: str, caplog
) -> None:  # type: ignore[no-untyped-def]
    recorder, _ = _install_pinned(monkeypatch, [[ip]], [_http("200 OK", _OK_BODY)])
    cid = await _create(client)
    caplog.set_level(logging.DEBUG)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    # Cùng một thông báo mạng cố định cho mọi nguyên nhân; không lộ IP/lý do.
    assert resp.status_code == 502 and resp.json()["detail"] == NETWORK_ERROR_MESSAGE
    assert recorder.connects == []  # không mở TCP tới đâu cả
    assert ip not in resp.text and TOKEN not in caplog.text and AUTH_B64 not in caplog.text


async def test_dns_rebinding_after_check_has_no_effect(
    client: httpx.AsyncClient, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    # Mỗi request phân giải ĐÚNG MỘT lần (GET /field, POST search = 2 lần). Lần thứ ba (nếu
    # ai đó phân giải lại lúc kết nối) sẽ trả loopback, nhưng không bao giờ xảy ra.
    recorder, calls = _install_pinned(
        monkeypatch,
        [[PUBLIC_IP], [PUBLIC_IP], ["127.0.0.1"]],
        [_http("200 OK", _OK_BODY)],
    )
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert recorder.connects == [PUBLIC_IP, PUBLIC_IP] and len(calls) == 2


async def test_rebinding_between_requests_is_blocked(
    client: httpx.AsyncClient, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    # Request đầu (GET /field) thấy IP công cộng, request sau (POST) thấy loopback: mỗi
    # request kiểm lại nên request sau bị chặn và không mở TCP.
    recorder, _ = _install_pinned(
        monkeypatch, [[PUBLIC_IP], ["127.0.0.1"]], [_http("200 OK", _OK_BODY)]
    )
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 502
    assert recorder.connects == [PUBLIC_IP]


async def test_pinned_redirect_302_is_error_and_no_second_connection(
    client: httpx.AsyncClient, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    recorder, calls = _install_pinned(
        monkeypatch,
        [[PUBLIC_IP]],
        [_http("302 Found", headers="Location: https://evil.example.com/x\r\n")],
    )
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 502 and "evil.example.com" not in resp.text
    assert recorder.connects == [PUBLIC_IP, PUBLIC_IP]
    assert calls == ["acme.atlassian.net", "acme.atlassian.net"]


async def test_pinned_end_to_end_sends_auth_only_to_saved_host(
    client: httpx.AsyncClient, monkeypatch, caplog
) -> None:  # type: ignore[no-untyped-def]
    import json as _json

    body = _json.dumps({"issues": [_issue("DBA-1")], "isLast": True}).encode()
    recorder, _ = _install_pinned(monkeypatch, [[PUBLIC_IP]], [_http("200 OK", body)])
    cid = await _create(client)
    caplog.set_level(logging.DEBUG)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 200 and resp.json()["added"] == 1
    assert recorder.connects == [PUBLIC_IP, PUBLIC_IP]
    assert TOKEN not in caplog.text and AUTH_B64 not in caplog.text


# ═══════════════════════════════════════════════════════════════════════
#  Vòng sửa: create-only, ghi theo lô khi đang tải, trần project, chéo kết nối, huỷ, audit
# ═══════════════════════════════════════════════════════════════════════


async def _patch(client: httpx.AsyncClient, task_id: str, **body: Any) -> None:
    resp = await client.patch(f"/api/v1/tasks/{task_id}", json=body)
    assert resp.status_code == 200, resp.text


async def test_user_edits_survive_resync_but_status_and_title_still_apply(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    jira(lambda r: _page(_issue("DBA-1", priority={"name": "High"}, duedate="2026-03-05")))
    cid = await _create(client)
    assert (await client.post(_sync_url(cid), headers=HEADERS)).json()["added"] == 1
    task = (await _tasks())[0]
    assert task.priority.value == "high" and task.due_at is not None
    original_project = task.project_id
    await _patch(
        client,
        str(task.id),
        priority="urgent",
        due_at="2027-01-01T00:00:00Z",
        assignee="Người khác",
    )

    # Jira đổi hết: title, status, priority, hạn, assignee, project.
    jira(
        lambda r: _page(
            _issue(
                "DBA-1",
                summary="Tên mới từ Jira",
                status={"name": "Done"},
                resolutiondate="2026-04-01T08:00:00.000+0000",
                priority={"name": "Low"},
                duedate="2026-12-12",
                assignee={"displayName": "Jira Assignee"},
                project={"key": "OTHER", "name": "Other"},
            )
        )
    )
    data = (await client.post(_sync_url(cid), headers=HEADERS)).json()
    assert data["updated"] == 1
    after = (await _tasks())[0]
    # Còn nguyên giá trị User đã sửa; task cũ không bị chuyển project.
    assert after.priority.value == "urgent"
    assert after.due_at is not None and after.due_at.year == 2027
    assert after.assignee == "Người khác"
    assert after.project_id == original_project
    # Trường thuộc nguồn vẫn được áp.
    assert after.title == "Tên mới từ Jira"
    assert after.status.value == "done" and after.completed_at is not None


async def test_batches_are_written_while_fetching_and_partial_failure_is_reported(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    counts: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if "nextPageToken" not in _json.loads(request.content):
            return _page(*[_issue(f"DBA-{i}") for i in range(1, 1001)], next_token="t")
        async with SessionFactory() as s:
            counts.append(int(await s.scalar(text("SELECT count(*) FROM tasks")) or 0))
        return httpx.Response(500, text=SECRET_BODY)

    jira(handler)
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    # Lô 1000 đã ghi TRƯỚC khi lấy trang kế (không gom hết trang vào RAM).
    assert counts == [1000]
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "Đã ghi 1000 task" in detail and "500" in detail and SECRET_BODY not in resp.text
    assert await _last_sync(cid) is None


async def test_new_project_cap(client: httpx.AsyncClient, jira, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(integration_sync_service, "MAX_NEW_PROJECTS", 2)
    jira(
        lambda r: _page(
            *[_issue(f"K{i}-1", project={"key": f"PJ{i}", "name": f"P{i}"}) for i in range(5)]
        )
    )
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    data = resp.json()
    assert resp.status_code == 200 and data["added"] == 5
    assert len([w for w in data["warnings"] if "trần" in w["reason"]]) == 3
    async with SessionFactory() as s:
        n_projects = await s.scalar(text("SELECT count(*) FROM projects"))
        unassigned = await s.scalar(text("SELECT count(*) FROM tasks WHERE project_id IS NULL"))
    assert (n_projects, unassigned) == (2, 3)


async def test_connection_cannot_overwrite_task_from_another_jira_host(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        return _page(_issue("DBA-1", summary=f"từ {request.url.host}"))

    jira(handler)
    a = await _create(client, name="A", base_url="https://acme.atlassian.net")
    b = await _create(client, name="B", base_url="https://other.atlassian.net")
    assert (await client.post(_sync_url(a), headers=HEADERS)).json()["added"] == 1
    resp = await client.post(_sync_url(b), headers=HEADERS)
    data = resp.json()
    assert data["updated"] == 0 and data["added"] == 0
    assert [e["external_id"] for e in data["errors"]] == ["DBA-1"]
    assert "kết nối khác" in data["errors"][0]["reason"]
    task = (await _tasks())[0]
    assert task.title == "từ acme.atlassian.net"
    assert task.external_url == "https://acme.atlassian.net/browse/DBA-1"


async def test_cancelled_request_does_not_leak_the_advisory_lock(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    entered = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        entered.set()
        await asyncio.sleep(60)
        return _page()

    jira(handler)
    cid = await _create(client)
    first = asyncio.create_task(client.post(_sync_url(cid), headers=HEADERS))
    await asyncio.wait_for(entered.wait(), 10)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    await asyncio.sleep(0.2)
    async with SessionFactory() as s:
        leaked = await s.scalar(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND pid <> pg_backend_pid()"
            )
        )
    assert leaked == 0
    jira(lambda r: _page(_issue("DBA-1")))
    assert (await client.post(_sync_url(cid), headers=HEADERS)).status_code == 200


async def test_compressed_jira_response_is_rejected_end_to_end(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    jira(lambda r: httpx.Response(200, content=b"x", headers={"Content-Encoding": "gzip"}))
    cid = await _create(client)
    resp = await client.post(_sync_url(cid), headers=HEADERS)
    assert resp.status_code == 502 and "nén" in resp.json()["detail"]


async def test_byte_cap_truncates_end_to_end(client: httpx.AsyncClient, jira, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(jira_client, "MAX_TOTAL_BYTES", 50)
    jira(lambda r: _page(_issue("DBA-1"), next_token="t"))
    cid = await _create(client)
    data = (await client.post(_sync_url(cid), headers=HEADERS)).json()
    assert data["truncated"] is True and data["pages"] == 1
    assert any("MB" in w["reason"] for w in data["warnings"])
    assert await _last_sync(cid) is None


async def test_duplicate_issues_across_pages_become_a_warning(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    import json as _json

    def handler(request: httpx.Request) -> httpx.Response:
        if "nextPageToken" not in _json.loads(request.content):
            return _page(_issue("DBA-1"), next_token="t")
        return _page(_issue("DBA-1"), _issue("DBA-2"))

    jira(handler)
    cid = await _create(client)
    data = (await client.post(_sync_url(cid), headers=HEADERS)).json()
    assert data["added"] == 2
    assert any("lặp" in w["reason"] for w in data["warnings"])


async def test_audit_lines_include_client_and_since_even_when_rejected(
    client: httpx.AsyncClient, jira, caplog
) -> None:  # type: ignore[no-untyped-def]
    jira(lambda r: _page())
    caplog.set_level(logging.INFO, logger="app.services.integration_sync_service")
    no_token = await _create(client, name="Không token", token=None)
    ok = await _create(client)
    await client.post(_sync_url(str(uuid.uuid4())), headers=HEADERS)  # 404
    await client.post(_sync_url(no_token), headers=HEADERS)  # 409
    await client.post(_sync_url(ok, "garbage"), headers=HEADERS)  # 422
    await client.post(_sync_url(ok, "2026-01-01"), headers=HEADERS)  # thành công
    records = [r for r in caplog.records if getattr(r, "audit", None) == "integration_sync"]
    failed = [r for r in records if r.audit_action == "failed"]  # type: ignore[attr-defined]
    assert sorted(r.status for r in failed) == [404, 409, 422]  # type: ignore[attr-defined]
    assert all(r.client == "127.0.0.1" for r in records)  # type: ignore[attr-defined]
    done = [r for r in records if r.audit_action == "done"]  # type: ignore[attr-defined]
    assert len(done) == 1 and done[0].since_minutes > 0  # type: ignore[attr-defined]
    assert TOKEN not in caplog.text and AUTH_B64 not in caplog.text


# ═══════════════════════════════════════════════════════════════════════
#  Hạn: cập nhật từ Jira chỉ khi User chưa sửa tay
# ═══════════════════════════════════════════════════════════════════════


async def _events_of(task_id: Any) -> list[TaskEvent]:
    async with SessionFactory() as s:
        stmt = select(TaskEvent).where(TaskEvent.task_id == task_id)
        return list((await s.execute(stmt)).scalars())


async def _first_sync(client: httpx.AsyncClient, jira, duedate: str | None) -> tuple[str, Task]:  # type: ignore[no-untyped-def]
    jira(lambda r: _page(_issue("DBA-1", duedate=duedate)))
    cid = await _create(client)
    assert (await client.post(_sync_url(cid), headers=HEADERS)).json()["added"] == 1
    return cid, (await _tasks())[0]


async def test_jira_due_change_applies_when_user_did_not_edit(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    cid, task = await _first_sync(client, jira, "2026-03-05")
    assert task.due_all_day is True

    jira(lambda r: _page(_issue("DBA-1", duedate="2026-04-01")))
    data = (await client.post(_sync_url(cid), headers=HEADERS)).json()
    assert data["updated"] == 1
    after = (await _tasks())[0]
    assert after.due_at == datetime(2026, 4, 1, tzinfo=UTC) and after.due_all_day is True
    changed = [e.payload.get("changes", {}) for e in await _events_of(task.id) if e.payload]
    assert any("due_at" in c for c in changed)


async def test_jira_due_change_is_ignored_after_user_edit(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    cid, task = await _first_sync(client, jira, "2026-03-05")
    await _patch(client, str(task.id), due_at="2027-01-01T09:00:00Z")

    jira(lambda r: _page(_issue("DBA-1", duedate="2026-12-12")))
    data = (await client.post(_sync_url(cid), headers=HEADERS)).json()
    after = (await _tasks())[0]
    assert after.due_at == datetime(2027, 1, 1, 9, tzinfo=UTC) and after.due_all_day is False
    assert any("Giữ hạn đã sửa tay" in w["reason"] for w in data["warnings"])


async def test_jira_removing_due_clears_it_when_user_did_not_edit(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    cid, _ = await _first_sync(client, jira, "2026-03-05")
    jira(lambda r: _page(_issue("DBA-1")))  # không còn duedate
    data = (await client.post(_sync_url(cid), headers=HEADERS)).json()
    assert data["updated"] == 1
    after = (await _tasks())[0]
    assert after.due_at is None and after.due_all_day is False


async def test_jira_due_kept_when_previous_payload_unknown(
    client: httpx.AsyncClient, jira
) -> None:  # type: ignore[no-untyped-def]
    cid, task = await _first_sync(client, jira, "2026-03-05")
    async with SessionFactory() as s:
        await s.execute(text("UPDATE tasks SET raw_payload = NULL WHERE id = :i"), {"i": task.id})
        await s.commit()
    jira(lambda r: _page(_issue("DBA-1", duedate="2026-04-01")))
    await client.post(_sync_url(cid), headers=HEADERS)
    after = (await _tasks())[0]
    assert after.due_at == datetime(2026, 3, 5, tzinfo=UTC)  # an toàn: không đoán


async def test_jira_sets_due_on_task_without_one(client: httpx.AsyncClient, jira) -> None:  # type: ignore[no-untyped-def]
    cid, task = await _first_sync(client, jira, None)
    assert task.due_at is None and task.due_all_day is False
    jira(lambda r: _page(_issue("DBA-1", duedate="2026-05-06")))
    await client.post(_sync_url(cid), headers=HEADERS)
    after = (await _tasks())[0]
    assert after.due_at == datetime(2026, 5, 6, tzinfo=UTC) and after.due_all_day is True
