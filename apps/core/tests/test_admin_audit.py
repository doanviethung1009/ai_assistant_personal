"""`GET /api/v1/admin/audit-log`: bộ lọc, thứ tự, email nối bằng LEFT JOIN, phân trang.

Spec: docs/specs/admin-users-local-login.md mục 4.2 và 7.1. Cần Postgres (`db`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete

from app.db.session import SessionFactory
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from tests.conftest import create_persona

pytestmark = pytest.mark.db

AUDIT = "/api/v1/admin/audit-log"
BASE = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


async def _seed(rows: list[AuditLog]) -> None:
    async with SessionFactory() as s:
        s.add_all(rows)
        await s.commit()


def _row(
    action: str,
    minutes: int,
    *,
    actor: uuid.UUID | None = None,
    target: uuid.UUID | None = None,
    details: dict[str, object] | None = None,
) -> AuditLog:
    return AuditLog(
        action=action,
        created_at=BASE + timedelta(minutes=minutes),
        actor_user_id=actor,
        target_type="user" if target else None,
        target_id=target,
        details=details,
    )


async def test_filters_order_and_emails(anon_client: httpx.AsyncClient) -> None:
    admin = await create_persona("admin@test.local", UserRole.ADMIN)
    other = await create_persona("other@test.local")
    await _seed(
        [
            _row("user_invited", 0, actor=admin.id, target=other.id, details={"via": "api"}),
            _row("login_success", 10, actor=other.id, target=other.id),
            _row("user_role_changed", 20, actor=admin.id, target=other.id),
            _row("login_denied", 30, details={"reason": "not_invited"}),
        ]
    )

    everything = (await anon_client.get(AUDIT, headers=admin.headers)).json()
    assert everything["total"] == 4
    minutes = [item["created_at"] for item in everything["items"]]
    assert minutes == sorted(minutes, reverse=True)
    newest = everything["items"][0]
    assert newest["action"] == "login_denied"
    assert newest["actor_email"] is None and newest["target_email"] is None

    invited = (await anon_client.get(f"{AUDIT}?action=user_invited", headers=admin.headers)).json()
    assert invited["total"] == 1
    item = invited["items"][0]
    assert item["actor_email"] == "admin@test.local"
    assert item["target_email"] == "other@test.local"
    assert item["details"] == {"via": "api"}

    by_actor = (
        await anon_client.get(f"{AUDIT}?actor_user_id={other.id}", headers=admin.headers)
    ).json()
    assert [i["action"] for i in by_actor["items"]] == ["login_success"]

    by_target = (
        await anon_client.get(f"{AUDIT}?target_id={other.id}", headers=admin.headers)
    ).json()
    assert by_target["total"] == 3

    since = (BASE + timedelta(minutes=10)).isoformat()
    until = (BASE + timedelta(minutes=20)).isoformat()
    window = (
        await anon_client.get(AUDIT, params={"since": since, "until": until}, headers=admin.headers)
    ).json()
    assert [i["action"] for i in window["items"]] == ["user_role_changed", "login_success"]


async def test_pagination_limits(anon_client: httpx.AsyncClient) -> None:
    admin = await create_persona("admin@test.local", UserRole.ADMIN)
    await _seed([_row("login_denied", i) for i in range(120)])
    page = (await anon_client.get(f"{AUDIT}?limit=50&offset=100", headers=admin.headers)).json()
    assert (page["total"], len(page["items"]), page["offset"]) == (120, 20, 100)
    too_big = await anon_client.get(f"{AUDIT}?limit=201", headers=admin.headers)
    assert too_big.status_code == 422
    bad_action = await anon_client.get(f"{AUDIT}?action=khong_co", headers=admin.headers)
    assert bad_action.status_code == 422


async def test_actor_email_is_null_after_actor_is_deleted(
    anon_client: httpx.AsyncClient,
) -> None:
    admin = await create_persona("admin@test.local", UserRole.ADMIN)
    gone = await create_persona("gone@test.local")
    await _seed([_row("user_invited", 0, actor=gone.id, target=admin.id)])
    async with SessionFactory() as s:
        await s.execute(delete(User).where(User.id == gone.id))
        await s.commit()
    body = (await anon_client.get(f"{AUDIT}?action=user_invited", headers=admin.headers)).json()
    item = body["items"][0]
    assert item["actor_user_id"] is None and item["actor_email"] is None
    assert item["target_email"] == "admin@test.local"


async def test_admin_actions_show_up_in_the_log(anon_client: httpx.AsyncClient) -> None:
    admin = await create_persona("admin@test.local", UserRole.ADMIN)
    created = await anon_client.post(
        "/api/v1/admin/users/local",
        headers=admin.headers,
        json={"username": "c.nguyen", "email": "c.nguyen@test.local"},
    )
    temp = created.json()["temporary_password"]
    uid = created.json()["user"]["id"]
    body = (await anon_client.get(f"{AUDIT}?target_id={uid}", headers=admin.headers)).json()
    assert [i["action"] for i in body["items"]] == ["user_created"]
    assert body["items"][0]["actor_email"] == "admin@test.local"
    assert temp not in str(body)


async def test_target_id_filter_also_filters_target_type(
    anon_client: httpx.AsyncClient,
) -> None:
    """Lọc target_id kèm target_type="user" (để dùng index); id trùng ở loại khác không lẫn vào."""
    admin = await create_persona("admin@test.local", UserRole.ADMIN)
    shared = uuid.uuid4()
    await _seed(
        [
            _row("user_updated", 0, actor=admin.id, target=shared),
            AuditLog(action="integration_updated", target_type="integration", target_id=shared),
        ]
    )
    body = (await anon_client.get(f"{AUDIT}?target_id={shared}", headers=admin.headers)).json()
    assert [i["action"] for i in body["items"]] == ["user_updated"]
