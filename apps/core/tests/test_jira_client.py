"""Connector Jira (B4b), phần không cần DB: ánh xạ issue, dựng JQL, phân trang, lỗi.

Không mạng thật: `httpx.MockTransport`. Dữ liệu Jira là mẫu tự soạn.
"""

# ruff: noqa: S106 - next_token là con trỏ phân trang giả, không phải mật khẩu
from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.models.enums import TaskPriority, TaskStatus
from app.services import jira_client
from app.services.errors import ValidationError
from app.services.jira_client import JiraClient, JiraSyncError, build_jql, jql_string, parse_since
from app.services.jira_mapping import ADF_PLACEHOLDER, MappingError, map_issue
from app.services.ssrf_guard import NETWORK_ERROR_MESSAGE, NetworkUnavailableError

BASE = "https://acme.atlassian.net"
EMAIL = "me@acme.com"
TOKEN = "ATATT3xFfGF0-fake-token-ZZ9876"  # noqa: S105
SECRET_BODY = "JIRA-BODY-SECRET-DO-NOT-ECHO"  # noqa: S105


# ═══════════════════════════════════════════════════════════════════════
#  Ánh xạ issue mẫu (đối chiếu với apps/web/app/jira-actions.ts)
# ═══════════════════════════════════════════════════════════════════════


def _issue(key: str = "DBA-12", **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "summary": "Sửa lỗi đăng nhập",
        "status": {"name": "In Progress"},
        "priority": {"name": "High"},
        "assignee": {"displayName": "Hùng Đoàn"},
        "labels": ["Backend", "Cần gấp"],
        "project": {"key": "DBA", "name": "Database Admin"},
        "duedate": "2026-03-05",
        "created": "2026-01-10T09:30:00.000+0700",
        "updated": "2026-02-01T10:00:00.000+0700",
        "resolutiondate": None,
        "issuetype": {"name": "Bug"},
        "components": [{"name": "Auth Service"}],
        "fixVersions": [{"name": "v1.2"}],
        "parent": {"key": "DBA-1"},
    }
    base.update(fields)
    return {
        "id": "10001",
        "key": key,
        "self": f"{BASE}/rest/api/3/issue/10001?expand=names&token=abc",
        "fields": base,
    }


def _map(issue: dict[str, Any], names: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    return map_issue(issue, base_url=BASE, field_names=names or {})


def test_mapping_in_progress_issue() -> None:
    item = _map(_issue())
    assert item.external_id == "DBA-12"
    assert item.title == "Sửa lỗi đăng nhập"
    assert item.status is TaskStatus.IN_PROGRESS
    assert item.priority is TaskPriority.HIGH
    assert item.assignee == "Hùng Đoàn"
    assert item.due_at == datetime(2026, 3, 5, tzinfo=UTC)  # 00:00 UTC như bản TS
    assert item.created_at == datetime(2026, 1, 10, 2, 30, tzinfo=UTC)
    assert item.external_url == f"{BASE}/browse/DBA-12"
    assert item.project_key == "DBA"
    assert item.project_name == "Database Admin"
    # Thứ tự ưu tiên: định danh, custom field, rồi parent/component/version, label cuối.
    assert item.tags == [
        "jira",
        "dba",
        "bug",
        "dba-1",
        "auth-service",
        "v1.2",
        "backend",
        "cần-gấp",
    ]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("To Do", TaskStatus.TODO),
        ("Backlog", TaskStatus.TODO),
        ("In Review", TaskStatus.IN_PROGRESS),
        ("Doing", TaskStatus.IN_PROGRESS),
        ("Done", TaskStatus.DONE),
        ("Closed", TaskStatus.DONE),
        ("Resolved", TaskStatus.DONE),
        ("Cancelled", TaskStatus.CANCELLED),
        ("Rejected", TaskStatus.CANCELLED),
        ("Won't Do", TaskStatus.CANCELLED),
        ("Obsolete", TaskStatus.CANCELLED),
        ("Review Rejected", TaskStatus.CANCELLED),  # điều kiện sau ghi đè điều kiện trước
        (None, TaskStatus.TODO),
    ],
)
def test_status_mapping(name: str | None, expected: TaskStatus) -> None:
    status = {"name": name} if name is not None else None
    assert _map(_issue(status=status)).status is expected


def test_done_issue_uses_resolutiondate_then_updated() -> None:
    done = _map(_issue(status={"name": "Done"}, resolutiondate="2026-02-03T08:00:00.000+0000"))
    assert done.completed_at == datetime(2026, 2, 3, 8, 0, tzinfo=UTC)
    fallback = _map(_issue(status={"name": "Done"}, resolutiondate=None))
    assert fallback.completed_at == datetime(2026, 2, 1, 3, 0, tzinfo=UTC)  # = updated


def test_custom_field_sets_tags_and_project() -> None:
    issue = _issue(
        customfield_10050={"value": "Công ty ABC"},
        customfield_10051=["Squad Alpha", {"name": "Squad Beta"}],
        customfield_10052="không liên quan",  # tên field không khớp regex
    )
    names = {
        "customfield_10050": "Công ty",
        "customfield_10051": "Team",
        "customfield_10052": "Ghi chú",
    }
    item = _map(issue, names)
    assert "công-ty-abc" in item.tags
    assert "squad-alpha" in item.tags
    assert "squad-beta" in item.tags
    assert "không-liên-quan" not in item.tags
    # Custom field phân nhóm đầu tiên thắng project của Jira (như bản TS).
    assert item.project_key == "CONG_TY_ABC"
    assert item.project_name == "Công ty ABC"


def test_unnormalizable_custom_project_falls_back_to_jira_project() -> None:
    item = _map(_issue(customfield_1={"value": "!!!"}), {"customfield_1": "Team"})
    assert item.project_key == "DBA"


def test_project_falls_back_to_key_prefix() -> None:
    item = _map(_issue(project=None))
    assert item.project_key == "DBA"
    assert item.project_name == "DBA"


def test_adf_description_is_placeholder_and_string_is_kept() -> None:
    adf = {"type": "doc", "version": 1, "content": [{"type": "paragraph"}]}
    assert _map(_issue(description=adf)).description == ADF_PLACEHOLDER
    assert _map(_issue(description="dòng 1\nbước 2")).description == "dòng 1\nbước 2"
    assert _map(_issue()).description is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Highest", TaskPriority.URGENT),
        ("High", TaskPriority.HIGH),
        ("Medium", TaskPriority.MEDIUM),
        ("Low", TaskPriority.LOW),
        ("Lowest", TaskPriority.LOW),
    ],
)
def test_priority_mapping(name: str, expected: TaskPriority) -> None:
    assert _map(_issue(priority={"name": name})).priority is expected


def test_unknown_priority_is_not_sent() -> None:
    item = _map(_issue(priority={"name": "Banana"}))
    assert "priority" not in item.model_fields_set


def test_control_chars_and_bidi_are_stripped() -> None:
    item = _map(_issue(summary="a\x00b\x1b[31m‮gnp.exe\nc", assignee={"displayName": "x\ry"}))
    assert item.title == "ab[31mgnp.exe c"
    assert "‮" not in item.title
    assert item.assignee == "x y"


@pytest.mark.parametrize("key", ["", "abc-1", "DBA-1; DROP", "DBA-1/../x", "DBA", "../../etc"])
def test_bad_issue_key_is_rejected(key: str) -> None:
    with pytest.raises(MappingError) as exc:
        _map(_issue(key=key))
    assert key not in str(exc.value) or key == ""


def test_non_dict_issue_is_rejected() -> None:
    with pytest.raises(MappingError):
        _map("DBA-1")  # type: ignore[arg-type]


def test_external_url_is_https_same_host_even_if_issue_has_other_urls() -> None:
    item = _map(_issue(summary="x"))
    assert item.external_url is not None
    assert item.external_url.startswith("https://acme.atlassian.net/browse/")


def test_raw_payload_is_an_allowlist() -> None:
    issue = _issue(
        description="mô tả riêng tư",
        comment={"comments": [{"body": "bí mật"}]},
        customfield_9={"value": "x"},
        attachment=[{"content": "https://x"}],
        reporter={"emailAddress": "a@b.c"},
    )
    issue["renderedFields"] = {"description": "<p>html</p>"}
    payload = _map(issue).raw_payload
    assert payload is not None
    assert set(payload) <= {"id", "key", "self", "fields"}
    assert set(payload["fields"]) <= {
        "status",
        "priority",
        "summary",
        "updated",
        "created",
        "resolutiondate",
        "duedate",
        "assignee",
        "labels",
        "project",
    }
    assert payload["fields"]["status"] == {"name": "In Progress"}
    assert payload["fields"]["project"] == {"key": "DBA"}
    assert payload["fields"]["assignee"] == {"displayName": "Hùng Đoàn"}
    dumped = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("mô tả riêng tư", "bí mật", "emailAddress", "attachment", "html"):
        assert forbidden not in dumped
    # `self` giữ path nhưng bỏ query (expand=names&token=abc).
    assert payload["self"] == f"{BASE}/rest/api/3/issue/10001"


def test_self_on_other_host_is_dropped() -> None:
    issue = _issue()
    issue["self"] = "https://evil.example.com/rest/api/3/issue/1"
    payload = _map(issue).raw_payload
    assert payload is not None and "self" not in payload


def test_tag_count_is_capped() -> None:
    labels = [f"l{i}" for i in range(60)]
    assert len(_map(_issue(labels=labels)).tags) == 20


# ═══════════════════════════════════════════════════════════════════════
#  JQL
# ═══════════════════════════════════════════════════════════════════════


def test_default_jql_from_current_users() -> None:
    assert (
        build_jql(None, ["Hùng Đoàn", "ba"], None)
        == 'assignee in ("Hùng Đoàn", "ba") ORDER BY updated DESC'
    )
    assert build_jql("   ", ["a"], None) == 'assignee in ("a") ORDER BY updated DESC'


def test_no_jql_and_no_users_is_an_error_not_a_whole_jira_query() -> None:
    with pytest.raises(ValidationError) as exc:
        build_jql(None, [], None)
    assert "current_users" in exc.value.message


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            'x") OR project = SECRET OR assignee in ("y',
            r'"x\") OR project = SECRET OR assignee in (\"y"',
        ),
        ("a\\", '"a\\\\"'),
        ('\\"', r'"\\\""'),
        ("tên\nxuống dòng", r'"tên\nxuống dòng"'),
        ("plain", '"plain"'),
    ],
)
def test_jql_string_escapes(name: str, expected: str) -> None:
    assert jql_string(name) == expected


def test_injection_in_user_name_cannot_break_out_of_the_string() -> None:
    jql = build_jql(None, ['x") OR project = SECRET OR assignee in ("y'], None)
    # Mọi nháy kép nằm trong giá trị đều đã bị escape: loại bỏ chuỗi escape rồi đếm.
    unescaped = jql.replace("\\\\", "").replace('\\"', "")
    assert unescaped.count('"') == 2
    assert jql.startswith("assignee in (") and jql.endswith(") ORDER BY updated DESC")


def test_project_key_list_shorthand_is_escaped() -> None:
    assert (
        build_jql('DBA, PR"OJ', [], None) == 'project in ("DBA", "PR\\"OJ") ORDER BY updated DESC'
    )


def test_explicit_jql_is_used_as_is() -> None:
    jql = "project = DBA AND status != Done ORDER BY created ASC"
    assert build_jql(jql, ["ignored"], None) == jql


def test_since_adds_integer_window_and_replaces_order_by() -> None:
    jql = build_jql("project = DBA ORDER BY created ASC", [], 90)
    assert jql == "(project = DBA) AND updated >= -90m ORDER BY updated DESC"
    assert build_jql(None, ["a"], 7).startswith('(assignee in ("a")) AND updated >= -7m')


def test_since_strips_lowercase_multiline_order_by() -> None:
    jql = build_jql("project = DBA\n  order   by created", [], 5)
    assert jql == "(project = DBA) AND updated >= -5m ORDER BY updated DESC"


NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_parse_since_valid() -> None:
    assert parse_since(None) is None
    assert parse_since("") is None
    # 1 ngày trước 12:00 -> 1440 phút (+1 làm tròn +5 dư)
    assert parse_since("2026-05-31T12:00:00Z", now=NOW) == 1440 + 1 + 5
    assert parse_since("2026-05-31T19:00:00+07:00", now=NOW) == 1440 + 1 + 5
    assert parse_since("2026-05-31", now=NOW) == 36 * 60 + 1 + 5  # 00:00 UTC
    assert parse_since("2026-06-01 11:59", now=NOW) == 1 + 1 + 5
    assert parse_since("2026-06-01T12:30:00", now=NOW) == parse_since(
        "2026-06-01T12:30:00Z", now=NOW
    )


@pytest.mark.parametrize(
    "bad",
    [
        "yesterday",
        "2026-13-01",
        "2026-02-30",
        "05/31/2026",
        "2026-05-31T12",
        "2026-05-31' OR 1=1",
        '2026-05-31") OR project = X --',
        "-5m",
        "2026-05-31T12:00:00Zjunk",
        "1999-12-31",
        "2030-01-01",  # tương lai xa
    ],
)
def test_parse_since_rejects(bad: str) -> None:
    with pytest.raises(ValidationError) as exc:
        parse_since(bad, now=NOW)
    assert bad not in exc.value.message


# ═══════════════════════════════════════════════════════════════════════
#  HTTP client
# ═══════════════════════════════════════════════════════════════════════


def _page(*keys: str, next_token: str | None = None) -> httpx.Response:
    body: dict[str, Any] = {
        "issues": [_issue(k) for k in keys],
        "names": {"summary": "Summary"},
        "isLast": next_token is None,
    }
    if next_token:
        body["nextPageToken"] = next_token
    return httpx.Response(200, json=body)


async def _collect(client: JiraClient, jql: str = "project = DBA") -> list[Any]:
    return [page async for page in client.search(jql)]


def _with_field_lookup(handler, fields=None):  # type: ignore[no-untyped-def]
    """Trả GET /field (danh sách custom field) và chuyển POST search cho `handler`."""

    async def wrapped(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/rest/api/3/field":
            return httpx.Response(200, json=fields or [])
        result = handler(request)
        if asyncio.iscoroutine(result):
            result = await result
        return result  # type: ignore[no-any-return]

    return wrapped


def _client(handler, fields=None) -> JiraClient:  # type: ignore[no-untyped-def]
    return JiraClient(BASE, EMAIL, TOKEN, httpx.MockTransport(_with_field_lookup(handler, fields)))


async def test_pagination_follows_next_page_token_and_sends_expected_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        if "nextPageToken" not in body:
            return _page("DBA-1", "DBA-2", next_token="t1")
        assert body["nextPageToken"] == "t1"
        return _page("DBA-3")

    client = _client(handler)
    pages = await _collect(client)
    assert [len(p.issues) for p in pages] == [2, 1]
    assert client.pages == 2 and not client.truncated
    first = seen[0]
    assert first.method == "POST" and str(first.url) == f"{BASE}/rest/api/3/search/jql"
    body = json.loads(first.content)
    assert body["jql"] == "project = DBA" and body["maxResults"] == 100
    assert body["expand"] == "names"
    assert "*all" not in body["fields"] and "summary" in body["fields"]
    expected = "Basic " + base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    assert first.headers["Authorization"] == expected
    assert {r.url.host for r in seen} == {"acme.atlassian.net"}


async def test_page_cap_sets_truncated() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _page(f"DBA-{calls}", next_token=f"t{calls}")  # luôn còn trang

    client = _client(handler)
    pages = await _collect(client)
    assert len(pages) == 100 == client.pages == calls
    assert client.truncated


async def test_exactly_100_pages_ending_naturally_is_not_truncated() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _page(f"DBA-{calls}", next_token=f"t{calls}" if calls < 100 else None)

    client = _client(handler)
    await _collect(client)
    assert client.pages == 100 and not client.truncated


@pytest.mark.parametrize(
    ("status", "needle"),
    [
        (400, "400"),
        (401, "401"),
        (403, "403"),
        (404, "404"),
        (429, "429"),
        (500, "500"),
        (502, "502"),
        (503, "503"),
        (418, "418"),
    ],
)
async def test_status_errors_have_own_message_without_body(status: int, needle: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=f"{SECRET_BODY} {TOKEN}")

    with pytest.raises(JiraSyncError) as exc:
        await _collect(_client(handler))
    message = exc.value.message
    assert needle in message
    assert SECRET_BODY not in message and TOKEN not in message
    assert SECRET_BODY not in repr(exc.value) and SECRET_BODY not in str(exc.value)


async def test_redirect_is_an_error_and_is_not_followed() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "acme.atlassian.net":
            return httpx.Response(302, headers={"Location": "https://evil.example.com/steal"})
        return httpx.Response(200, json={"issues": []})

    with pytest.raises(JiraSyncError) as exc:
        await _collect(_client(handler))
    assert "302" in exc.value.message and "evil.example.com" not in exc.value.message
    # Chỉ một request, tới đúng host; Authorization không sang host khác.
    assert [r.url.host for r in calls] == ["acme.atlassian.net"]
    assert not any(
        "authorization" in r.headers for r in calls if r.url.host != "acme.atlassian.net"
    )


async def test_transport_timeout_maps_to_own_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"secret {TOKEN}")

    with pytest.raises(NetworkUnavailableError) as exc:
        await _collect(_client(handler))
    # Timeout gộp với mọi lỗi mạng: một thông báo cố định, không phân biệt nguyên nhân.
    assert exc.value.status_code == 502 and exc.value.message == NETWORK_ERROR_MESSAGE
    assert TOKEN not in exc.value.message and exc.value.__cause__ is None


async def test_per_request_timeout_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jira_client, "REQUEST_TIMEOUT_SECONDS", 0.05)

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return _page("DBA-1")

    with pytest.raises(NetworkUnavailableError):
        await _collect(_client(handler))


async def test_total_time_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jira_client, "TOTAL_TIMEOUT_SECONDS", 0.15)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.06)
        return _page(f"DBA-{calls}", next_token=f"t{calls}")

    with pytest.raises(JiraSyncError) as exc:
        await _collect(_client(handler))
    assert exc.value.status_code == 504 and "phút" in exc.value.message
    assert calls < 100


async def test_connection_error_message_does_not_forward_library_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"boom {TOKEN} 10.0.0.5")

    with pytest.raises(NetworkUnavailableError) as exc:
        await _collect(_client(handler))
    assert exc.value.message == NETWORK_ERROR_MESSAGE
    assert TOKEN not in exc.value.message and "10.0.0.5" not in exc.value.message
    assert "ConnectError" not in exc.value.message


async def test_response_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jira_client, "MAX_RESPONSE_BYTES", 2000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"issues": [], "pad": "' + b"x" * 5000 + b'"}')

    with pytest.raises(JiraSyncError) as exc:
        await _collect(_client(handler))
    assert "vượt" in exc.value.message


async def test_response_size_cap_applies_to_streamed_body_without_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jira_client, "MAX_RESPONSE_BYTES", 1000)

    async def body() -> Any:
        for _ in range(100):
            yield b"x" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body())

    with pytest.raises(JiraSyncError):
        await _collect(_client(handler))


@pytest.mark.parametrize("content", [b"not json", b"[1,2]", b"\xff\xfe", b"[" * 100000])
async def test_invalid_json_shapes(content: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    with pytest.raises(JiraSyncError):
        await _collect(_client(handler))


def test_client_repr_does_not_contain_credentials() -> None:
    client = _client(lambda r: _page())
    assert TOKEN not in repr(client) and TOKEN not in str(vars(client).get("_base_url", ""))
    assert base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode() not in repr(client)


# ═══════════════════════════════════════════════════════════════════════
#  Vòng sửa: field tường minh, trần byte, nén, gộp tên field, làm sạch
# ═══════════════════════════════════════════════════════════════════════


async def test_requests_explicit_fields_plus_matching_custom_fields() -> None:
    posted: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(json.loads(request.content))
        return _page("DBA-1")

    fields = [
        {"id": "customfield_1", "name": "Công ty", "custom": True},
        {"id": "customfield_2", "name": "Story points", "custom": True},  # không khớp regex
        {"id": "summary", "name": "Team"},  # không phải customfield_*
    ]
    client = _client(handler, fields)
    await _collect(client)
    assert "customfield_1" in posted[0]["fields"]
    assert "customfield_2" not in posted[0]["fields"] and "*all" not in posted[0]["fields"]
    assert client.field_names["customfield_1"] == "Công ty"


async def test_custom_field_lookup_failure_is_a_note_not_fatal() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(403, text=SECRET_BODY)
        return _page("DBA-1")

    client = JiraClient(BASE, EMAIL, TOKEN, httpx.MockTransport(handler))
    pages = await _collect(client)
    assert len(pages) == 1
    assert client.notes and SECRET_BODY not in client.notes[0] and "403" in client.notes[0]


async def test_field_names_accumulate_across_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        first = "nextPageToken" not in body
        names = {"customfield_1": "Team"} if first else {"customfield_2": "Company"}
        return httpx.Response(
            200,
            json={
                "issues": [],
                "names": names,
                "isLast": not first,
                **({"nextPageToken": "t"} if first else {}),
            },
        )

    pages = await _collect(_client(handler))
    assert pages[-1].field_names == {"customfield_1": "Team", "customfield_2": "Company"}


async def test_compressed_response_is_rejected() -> None:
    import gzip

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=gzip.compress(b'{"issues":[]}'), headers={"Content-Encoding": "gzip"}
        )

    with pytest.raises(JiraSyncError) as exc:
        await _collect(_client(handler))
    assert "nén" in exc.value.message


async def test_total_byte_cap_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jira_client, "MAX_TOTAL_BYTES", 600)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = {"issues": [], "pad": "x" * 400, "nextPageToken": f"t{calls}", "isLast": False}
        return httpx.Response(200, json=body)

    client = _client(handler)
    pages = await _collect(client)
    assert client.truncated and client.truncated_reason == "bytes"
    assert len(pages) == calls == 2


def test_issue_key_trailing_newline_is_rejected() -> None:
    with pytest.raises(MappingError):
        _map(_issue(key="DBA-1\n"))


def test_clean_text_removes_format_chars_but_keeps_zwj() -> None:
    from app.services.jira_mapping import clean_text

    assert clean_text("a\u200bb\ufeffc\u00add") == "abcd"  # ZWSP, BOM, soft hyphen
    assert clean_text("a" + chr(0x2028) + "b" + chr(0x2029) + "c") == "a b c"  # Zl/Zp
    assert clean_text("👩‍💻") == "👩‍💻"  # ZWJ cho emoji được giữ


def test_overlong_assignee_is_truncated_not_fatal() -> None:
    notes: list[str] = []
    item = map_issue(
        _issue(assignee={"displayName": "A" * 500}),
        base_url=BASE,
        field_names={},
        notes=notes,
    )
    assert item.assignee is not None and len(item.assignee) == 200
    assert any("assignee" in n for n in notes)


def test_tag_overflow_keeps_identity_tags_and_reports() -> None:
    notes: list[str] = []
    labels = [f"l{i}" for i in range(40)]
    item = map_issue(
        _issue(labels=labels, customfield_1={"value": "Acme"}),
        base_url=BASE,
        field_names={"customfield_1": "Company"},
        notes=notes,
    )
    assert len(item.tags) == 20
    assert {"jira", "dba", "bug", "acme"} <= set(item.tags)
    assert any("tag" in n for n in notes)


def test_due_at_absent_when_jira_has_no_due_date() -> None:
    item = _map(_issue(duedate=None))
    assert "due_at" not in item.model_fields_set


def test_issue_with_missing_optional_fields_maps_without_crashing() -> None:
    item = map_issue({"key": "DBA-1", "fields": {}}, base_url=BASE, field_names={})
    assert item.title == "No Title" and item.tags == ["jira"]
    assert map_issue({"key": "DBA-2"}, base_url=BASE, field_names={}).external_id == "DBA-2"
