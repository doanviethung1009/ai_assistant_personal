"""`/api/v1/admin/users/**`: quyền, phân trang, tạo tài khoản nội bộ, khoá admin, xoá, alias.

Spec: docs/specs/admin-users-local-login.md mục 4.2 và 7.1. Cần Postgres (`db`).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import SessionFactory
from app.models.audit_log import AuditLog
from app.models.enums import UserRole, UserStatus
from app.models.task import Task
from app.models.user import User
from app.services import user_service
from app.services.clock import now_utc
from app.services.errors import ConflictError, ForbiddenError
from tests.conftest import Persona, create_local_persona, create_persona

pytestmark = pytest.mark.db

USERS = "/api/v1/admin/users"
LOGIN_PW = "/api/v1/auth/login/password"
SECRET_KEYS = {"password", "password_hash", "temporary_password", "hash"}


async def _admin() -> Persona:
    return await create_persona("admin@test.local", UserRole.ADMIN)


async def _audit(action: str) -> list[AuditLog]:
    async with SessionFactory() as s:
        rows = await s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at)
        )
        return list(rows.all())


async def _user(user_id: uuid.UUID) -> User:
    async with SessionFactory() as s:
        user = await s.get(User, user_id)
        assert user is not None
        return user


async def _create_local(
    client: httpx.AsyncClient, admin: Persona, username: str = "c.nguyen", **extra: str
) -> httpx.Response:
    return await client.post(
        f"{USERS}/local",
        headers=admin.headers,
        json={"username": username, "email": f"{username}@test.local", **extra},
    )


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            keys.add(str(key).lower())
            keys |= _walk_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            keys |= _walk_keys(inner)
    return keys


# ═══════════════════════════════════════════════════════════════════════
#  Quyền
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("role", [UserRole.MEMBER, UserRole.LEAD])
async def test_non_admin_gets_403_everywhere(
    anon_client: httpx.AsyncClient, role: UserRole
) -> None:
    other = await create_persona("other@test.local")
    who = await create_persona("who@test.local", role)
    some = uuid.uuid4()
    calls = [
        ("GET", USERS, None),
        ("POST", USERS, {"email": "x@test.local"}),
        ("POST", f"{USERS}/local", {"username": "abc", "email": "abc@test.local"}),
        ("GET", f"{USERS}/{other.id}", None),
        ("PATCH", f"{USERS}/{other.id}", {"name": "x"}),
        ("POST", f"{USERS}/{other.id}/reset-password", None),
        ("POST", f"{USERS}/{other.id}/unlock", None),
        ("POST", f"{USERS}/{other.id}/revoke-sessions", None),
        ("PUT", f"{USERS}/{other.id}/aliases", {"aliases": []}),
        ("DELETE", f"{USERS}/{some}", None),
        ("GET", "/api/v1/admin/audit-log", None),
    ]
    for method, path, body in calls:
        resp = await anon_client.request(method, path, headers=who.headers, json=body)
        assert resp.status_code == 403, (method, path, resp.status_code)
        assert resp.json()["code"] == "forbidden"


# ═══════════════════════════════════════════════════════════════════════
#  Danh sách
# ═══════════════════════════════════════════════════════════════════════


async def test_list_pagination_and_filters(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    async with SessionFactory() as s:
        for i in range(119):
            s.add(
                User(
                    email=f"u{i:03d}@test.local",
                    role=UserRole.LEAD if i % 10 == 0 else UserRole.MEMBER,
                    status=UserStatus.INVITED if i % 2 else UserStatus.DISABLED,
                )
            )
        await s.commit()

    first = (await anon_client.get(USERS, headers=admin.headers)).json()
    assert (first["total"], len(first["items"]), first["limit"], first["offset"]) == (
        120,
        50,
        50,
        0,
    )
    last = (await anon_client.get(f"{USERS}?limit=50&offset=100", headers=admin.headers)).json()
    assert len(last["items"]) == 20

    leads = (await anon_client.get(f"{USERS}?role=lead", headers=admin.headers)).json()
    assert leads["total"] == 12 and all(u["role"] == "lead" for u in leads["items"])
    invited = (await anon_client.get(f"{USERS}?status=invited", headers=admin.headers)).json()
    assert invited["total"] == 59
    by_q = (await anon_client.get(f"{USERS}?q=U01", headers=admin.headers)).json()
    assert by_q["total"] == 10
    # Ký tự đại diện của LIKE được escape, không khớp mọi dòng.
    percent = (await anon_client.get(f"{USERS}?q=%25", headers=admin.headers)).json()
    assert percent["total"] == 0
    local = (await anon_client.get(f"{USERS}?auth_provider=local", headers=admin.headers)).json()
    assert local["total"] == 0
    bad = await anon_client.get(f"{USERS}?limit=201", headers=admin.headers)
    assert bad.status_code == 422


async def test_list_filter_locked_and_search_username(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    locked = await create_local_persona("bi.khoa")
    await create_local_persona("binh.thuong")
    for _ in range(5):
        await anon_client.post(
            LOGIN_PW, json={"identifier": "bi.khoa", "password": "sai-mat-khau-sai-sai"}
        )
    only = (await anon_client.get(f"{USERS}?locked=true", headers=admin.headers)).json()
    assert [u["id"] for u in only["items"]] == [str(locked.id)]
    assert only["items"][0]["locked_until"] is not None
    query = f"{USERS}?locked=false&auth_provider=local"
    free = (await anon_client.get(query, headers=admin.headers)).json()
    assert [u["username"] for u in free["items"]] == ["binh.thuong"]
    found = (await anon_client.get(f"{USERS}?q=binh.th", headers=admin.headers)).json()
    assert found["total"] == 1


# ═══════════════════════════════════════════════════════════════════════
#  Tạo tài khoản nội bộ
# ═══════════════════════════════════════════════════════════════════════


async def test_create_local_returns_temp_password_once_and_it_works(
    anon_client: httpx.AsyncClient,
) -> None:
    admin = await _admin()
    resp = await _create_local(anon_client, admin, name="Cẩm Nguyễn")
    assert resp.status_code == 201, resp.text
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    temp = body["temporary_password"]
    assert len(temp) == 16
    user = body["user"]
    assert (user["username"], user["auth_provider"], user["status"]) == (
        "c.nguyen",
        "local",
        "active",
    )
    assert user["must_change_password"] is True and user["role"] == "member"
    assert SECRET_KEYS.isdisjoint(_walk_keys(user))

    got = await anon_client.get(f"{USERS}/{user['id']}", headers=admin.headers)
    assert got.status_code == 200
    assert SECRET_KEYS.isdisjoint(_walk_keys(got.json()))
    assert temp not in got.text
    listing = await anon_client.get(USERS, headers=admin.headers)
    assert temp not in listing.text and SECRET_KEYS.isdisjoint(_walk_keys(listing.json()))

    login = await anon_client.post(LOGIN_PW, json={"identifier": "c.nguyen", "password": temp})
    assert login.status_code == 200
    created = await _audit("user_created")
    assert len(created) == 1
    assert created[0].details == {"provider": "local", "role": "member", "via": "api"}
    assert temp not in str([r.details for r in await _audit("login_success")])


async def test_create_local_conflicts_and_validation(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    assert (await _create_local(anon_client, admin)).status_code == 201
    same_email = await anon_client.post(
        f"{USERS}/local",
        headers=admin.headers,
        json={"username": "khac.ten", "email": "c.nguyen@test.local"},
    )
    assert same_email.status_code == 409 and same_email.json()["code"] == "email_exists"
    same_name = await anon_client.post(
        f"{USERS}/local",
        headers=admin.headers,
        json={"username": "C.Nguyen", "email": "email.khac@test.local"},
    )
    assert same_name.status_code == 409 and same_name.json()["code"] == "username_exists"
    for bad in ("ab", "co@dau", "-bat.dau", "có dấu", "x" * 65):
        resp = await anon_client.post(
            f"{USERS}/local",
            headers=admin.headers,
            json={"username": bad, "email": "ok@test.local"},
        )
        assert resp.status_code == 422, bad


async def test_invite_google_user(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    resp = await anon_client.post(
        USERS, headers=admin.headers, json={"email": "Moi@Test.Local", "role": "lead"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["email"], body["status"], body["auth_provider"]) == (
        "moi@test.local",
        "invited",
        "google",
    )
    dup = await anon_client.post(USERS, headers=admin.headers, json={"email": "moi@test.local"})
    assert dup.status_code == 409 and dup.json()["code"] == "email_exists"
    invited = await _audit("user_invited")
    assert invited[0].details == {"role": "lead", "via": "api"}


# ═══════════════════════════════════════════════════════════════════════
#  Quy tắc khoá admin
# ═══════════════════════════════════════════════════════════════════════


async def test_cannot_demote_or_disable_or_delete_self(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    second = await create_persona("admin2@test.local", UserRole.ADMIN)
    assert second.id
    for payload in ({"role": "member"}, {"status": "disabled"}):
        resp = await anon_client.patch(f"{USERS}/{admin.id}", headers=admin.headers, json=payload)
        assert resp.status_code == 409 and resp.json()["code"] == "self_lockout", payload
    resp = await anon_client.delete(f"{USERS}/{admin.id}", headers=admin.headers)
    assert resp.status_code == 409 and resp.json()["code"] == "self_lockout"


async def test_last_active_admin_cannot_be_removed(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Qua API chỉ đụng `last_admin` khi hai admin đua nhau (test bên dưới); ở đây gọi service
    thẳng với một actor giả để kiểm quy tắc đếm, gồm cả việc admin bị khoá không được tính.

    Tắt kiểm tra actor (`_require_active_admin_actor`) vì actor giả không phải admin thật; việc
    actor bị hạ quyền được kiểm riêng ở test khác."""

    async def _no_actor_check(*_: object) -> None:
        return None

    monkeypatch.setattr(user_service, "_require_active_admin_actor", _no_actor_check)
    admin = await _admin()
    await create_persona("old@test.local", UserRole.ADMIN, status=UserStatus.DISABLED)
    actor = uuid.uuid4()
    async with SessionFactory() as s:
        with pytest.raises(ConflictError) as demote:
            await user_service.update_user(
                s, admin.id, {"role": UserRole.MEMBER}, actor_user_id=actor
            )
        assert demote.value.code == "last_admin"
    async with SessionFactory() as s:
        with pytest.raises(ConflictError) as remove:
            await user_service.delete_user(s, admin.id, actor_user_id=actor)
        assert remove.value.code == "last_admin"
    # CLI (enforce=False) không bị chặn: người có shell là chủ máy.
    async with SessionFactory() as s:
        await user_service.update_user(
            s, admin.id, {"status": "disabled"}, via="cli", enforce=False
        )
        assert await user_service.count_active_admins(s) == 0
        await s.rollback()


async def test_concurrent_cross_demotion_only_one_succeeds(anon_client: httpx.AsyncClient) -> None:
    a = await create_persona("a@test.local", UserRole.ADMIN)
    b = await create_persona("b@test.local", UserRole.ADMIN)
    first, second = await asyncio.gather(
        anon_client.patch(f"{USERS}/{b.id}", headers=a.headers, json={"role": "member"}),
        anon_client.patch(f"{USERS}/{a.id}", headers=b.headers, json={"role": "member"}),
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses in ([200, 403], [200, 409]), statuses
    async with SessionFactory() as s:
        active_admins = select(User).where(
            User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE
        )
        admins = (await s.scalars(active_admins)).all()
    assert len(admins) == 1


async def test_env_admin_cannot_be_demoted_disabled_or_deleted(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin()
    boss = await create_persona("boss@test.local", UserRole.ADMIN)
    monkeypatch.setattr(settings, "admin_emails", ["boss@test.local"])
    read = await anon_client.get(f"{USERS}/{boss.id}", headers=admin.headers)
    assert read.json()["is_env_admin"] is True
    for method, payload in (
        ("PATCH", {"role": "member"}),
        ("PATCH", {"status": "disabled"}),
        ("DELETE", None),
    ):
        resp = await anon_client.request(
            method, f"{USERS}/{boss.id}", headers=admin.headers, json=payload
        )
        assert resp.status_code == 409 and resp.json()["code"] == "env_admin", (method, payload)


# ═══════════════════════════════════════════════════════════════════════
#  PATCH, reset, unlock, revoke, delete, alias
# ═══════════════════════════════════════════════════════════════════════


async def test_patch_role_status_and_audit(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    who = await create_persona("member@test.local")
    resp = await anon_client.patch(
        f"{USERS}/{who.id}", headers=admin.headers, json={"role": "lead", "name": "  Mai  "}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["role"], resp.json()["name"]) == ("lead", "Mai")
    # Core đọc role mỗi request: có hiệu lực ngay, không đổi session_version.
    assert (await anon_client.get("/api/v1/me", headers=who.headers)).json()["role"] == "lead"

    off = await anon_client.patch(
        f"{USERS}/{who.id}", headers=admin.headers, json={"status": "disabled"}
    )
    assert off.json()["status"] == "disabled"
    assert (await anon_client.get("/api/v1/me", headers=who.headers)).status_code == 401
    assert (await _user(who.id)).session_version == 1

    assert [r.details for r in await _audit("user_role_changed")] == [
        {"from": "member", "to": "lead", "via": "api"}
    ]
    assert len(await _audit("user_status_changed")) == 1
    assert [r.details for r in await _audit("user_updated")] == [{"fields": ["name"], "via": "api"}]


async def test_patch_validation_and_not_local_account(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    google = await create_persona("gg@test.local")
    empty = await anon_client.patch(f"{USERS}/{google.id}", headers=admin.headers, json={})
    assert empty.status_code == 422
    unknown = await anon_client.patch(f"{USERS}/{google.id}", headers=admin.headers, json={"x": 1})
    assert unknown.status_code == 422
    email = await anon_client.patch(
        f"{USERS}/{google.id}", headers=admin.headers, json={"email": "moi@test.local"}
    )
    assert email.status_code == 409 and email.json()["code"] == "not_local_account"

    local = await create_local_persona("c.nguyen")
    other = await create_local_persona("khac")
    clash = await anon_client.patch(
        f"{USERS}/{local.id}", headers=admin.headers, json={"username": "khac"}
    )
    assert clash.status_code == 409 and clash.json()["code"] == "username_exists"
    clash_mail = await anon_client.patch(
        f"{USERS}/{local.id}", headers=admin.headers, json={"email": other.email}
    )
    assert clash_mail.status_code == 409 and clash_mail.json()["code"] == "email_exists"
    ok = await anon_client.patch(
        f"{USERS}/{local.id}", headers=admin.headers, json={"username": "Moi.Ten"}
    )
    assert ok.status_code == 200 and ok.json()["username"] == "moi.ten"
    # Audit chỉ ghi TÊN trường, không ghi giá trị email/username.
    assert "moi.ten" not in str([r.details for r in await _audit("user_updated")])


async def test_enable_google_without_sub_becomes_invited(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    invited = await anon_client.post(USERS, headers=admin.headers, json={"email": "moi@test.local"})
    uid = invited.json()["id"]
    resp = await anon_client.patch(
        f"{USERS}/{uid}", headers=admin.headers, json={"status": "active"}
    )
    assert resp.status_code == 200 and resp.json()["status"] == "invited"


async def test_reset_password_kills_sessions_and_forces_change(
    anon_client: httpx.AsyncClient,
) -> None:
    admin = await _admin()
    who = await create_local_persona("c.nguyen")
    resp = await anon_client.post(f"{USERS}/{who.id}/reset-password", headers=admin.headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["cache-control"] == "no-store"
    temp = resp.json()["temporary_password"]
    assert len(temp) == 16
    assert (await _user(who.id)).session_version == 1
    assert (await anon_client.get("/api/v1/me", headers=who.headers)).status_code == 401
    # Mật khẩu cũ hết hiệu lực, mật khẩu tạm đăng nhập được và buộc đổi.
    old_body = {"identifier": "c.nguyen", "password": who.password}
    old = await anon_client.post(LOGIN_PW, json=old_body)
    assert old.status_code == 403
    new = await anon_client.post(LOGIN_PW, json={"identifier": "c.nguyen", "password": temp})
    assert new.status_code == 200 and new.json()["session_version"] == 1
    assert (await _user(who.id)).must_change_password is True
    audited = await _audit("password_reset")
    assert len(audited) == 1 and temp not in str(audited[0].details)


async def test_reset_password_rejections(anon_client: httpx.AsyncClient) -> None:
    admin = await create_local_persona("quan.tri", role=UserRole.ADMIN)
    google = await create_persona("gg@test.local")
    resp = await anon_client.post(f"{USERS}/{google.id}/reset-password", headers=admin.headers)
    assert resp.status_code == 409 and resp.json()["code"] == "not_local_account"
    self_reset = await anon_client.post(f"{USERS}/{admin.id}/reset-password", headers=admin.headers)
    assert self_reset.status_code == 409 and self_reset.json()["code"] == "self_action"
    ghost = f"{USERS}/{uuid.uuid4()}/reset-password"
    missing = await anon_client.post(ghost, headers=admin.headers)
    assert missing.status_code == 404


async def test_revoke_sessions_and_unlock_audit(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    who = await create_persona("member@test.local")
    assert (
        await anon_client.post(f"{USERS}/{who.id}/revoke-sessions", headers=admin.headers)
    ).status_code == 204
    assert (await anon_client.get("/api/v1/me", headers=who.headers)).status_code == 401
    assert (
        await anon_client.post(f"{USERS}/{who.id}/unlock", headers=admin.headers)
    ).status_code == 204
    assert [r.details for r in await _audit("sessions_revoked")] == [{"via": "api"}]
    assert len(await _audit("user_unlocked")) == 1
    # Admin tự thu hồi phiên của mình được phép.
    own = await anon_client.post(f"{USERS}/{admin.id}/revoke-sessions", headers=admin.headers)
    assert own.status_code == 204


async def test_delete_user_rules(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    empty = await create_persona("trong@test.local")
    owner = await create_persona("co.task@test.local")
    async with SessionFactory() as s:
        s.add(Task(title="Việc riêng", owner_id=owner.id))
        await s.commit()
    blocked = await anon_client.delete(f"{USERS}/{owner.id}", headers=admin.headers)
    assert blocked.status_code == 409 and blocked.json()["code"] == "has_data"

    # Task trong thùng rác vẫn tính là còn dữ liệu.
    async with SessionFactory() as s:
        task = await s.scalar(select(Task).where(Task.owner_id == owner.id))
        assert task is not None
        task.deleted_at = now_utc()
        await s.commit()
    again = await anon_client.delete(f"{USERS}/{owner.id}", headers=admin.headers)
    assert again.status_code == 409 and again.json()["code"] == "has_data"

    done = await anon_client.delete(f"{USERS}/{empty.id}", headers=admin.headers)
    assert done.status_code == 204
    assert (await anon_client.get(f"{USERS}/{empty.id}", headers=admin.headers)).status_code == 404
    deleted = await _audit("user_deleted")
    assert len(deleted) == 1 and deleted[0].target_id == empty.id
    assert deleted[0].details == {"provider": "google", "role": "member", "via": "api"}


async def test_aliases_replace_and_conflict(anon_client: httpx.AsyncClient) -> None:
    admin = await _admin()
    first = await create_persona("mot@test.local")
    second = await create_persona("hai@test.local")
    resp = await anon_client.put(
        f"{USERS}/{first.id}/aliases",
        headers=admin.headers,
        json={"aliases": [{"source": "jira", "alias": "Nguyễn A"}, {"alias": "A.N"}]},
    )
    assert resp.status_code == 200, resp.text
    assert sorted(a["alias"] for a in resp.json()["aliases"]) == ["A.N", "Nguyễn A"]

    clash = await anon_client.put(
        f"{USERS}/{second.id}/aliases", headers=admin.headers, json={"aliases": [{"alias": "A.N"}]}
    )
    assert clash.status_code == 409 and clash.json()["code"] == "alias_taken"
    assert "mot@test.local" in clash.json()["detail"]

    dup = await anon_client.put(
        f"{USERS}/{second.id}/aliases",
        headers=admin.headers,
        json={"aliases": [{"alias": "x"}, {"alias": "x"}]},
    )
    assert dup.status_code == 422
    many = await anon_client.put(
        f"{USERS}/{second.id}/aliases",
        headers=admin.headers,
        json={"aliases": [{"alias": f"a{i}"} for i in range(21)]},
    )
    assert many.status_code == 422

    cleared = await anon_client.put(
        f"{USERS}/{first.id}/aliases", headers=admin.headers, json={"aliases": []}
    )
    assert cleared.json()["aliases"] == []
    audited = await _audit("user_aliases_changed")
    assert [r.details["added"] for r in audited if r.details] == [2, 0]


async def test_admin_route_requires_current_password_for_admin_too(
    anon_client: httpx.AsyncClient,
) -> None:
    admin = await create_local_persona("quan.tri", role=UserRole.ADMIN, must_change_password=True)
    resp = await anon_client.get(USERS, headers=admin.headers)
    assert resp.status_code == 403 and resp.json()["code"] == "password_change_required"


# ═══════════════════════════════════════════════════════════════════════
#  Sửa gói review: ADMIN_EMAILS, actor cũ, IntegrityError
# ═══════════════════════════════════════════════════════════════════════


async def test_sync_admin_emails_skips_local_accounts(
    anon_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    local = await create_local_persona("c.nguyen")
    google = await create_persona("gg@test.local")
    with caplog.at_level(logging.WARNING, logger="app.services.user_service"):
        async with SessionFactory() as s:
            changed = await user_service.sync_admin_emails(s, [local.email, google.email])
            await s.commit()
    assert changed == 1
    assert (await _user(local.id)).role is UserRole.MEMBER
    assert (await _user(google.id)).role is UserRole.ADMIN
    assert "nội bộ" in caplog.text
    assert local.email not in caplog.text


@pytest.mark.parametrize("how", ["demoted", "disabled"])
async def test_stale_actor_is_rejected_after_advisory_lock(
    anon_client: httpx.AsyncClient, how: str
) -> None:
    """Actor vừa bị hạ quyền/khoá sau khi qua xác thực: thao tác huỷ quyền phải 403."""
    actor = await create_persona("old.admin@test.local", UserRole.ADMIN)
    target = await create_persona("target@test.local", UserRole.ADMIN)
    await create_persona("keep@test.local", UserRole.ADMIN)
    async with SessionFactory() as s:
        row = await s.get(User, actor.id)
        assert row is not None
        if how == "demoted":
            row.role = UserRole.MEMBER
        else:
            row.status = UserStatus.DISABLED
        await s.commit()
    async with SessionFactory() as s:
        with pytest.raises(ForbiddenError):
            await user_service.update_user(
                s, target.id, {"role": UserRole.MEMBER}, actor_user_id=actor.id
            )
    async with SessionFactory() as s:
        with pytest.raises(ForbiddenError):
            await user_service.delete_user(s, target.id, actor_user_id=actor.id)
    assert (await _user(target.id)).role is UserRole.ADMIN


class _FakeDriverError(Exception):
    """Giả lỗi asyncpg: chỉ cần `sqlstate` / `constraint_name` như `app.db.locks` đọc."""

    def __init__(self, sqlstate: str | None, constraint_name: str | None) -> None:
        super().__init__("fake")
        self.sqlstate = sqlstate
        self.constraint_name = constraint_name


async def test_delete_user_fk_violation_maps_to_has_data(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin()
    victim = await create_persona("trong@test.local")

    async def boom(self: AsyncSession, *args: object, **kwargs: object) -> None:
        raise IntegrityError("DELETE", {}, _FakeDriverError("23503", "fk_something"))

    monkeypatch.setattr(AsyncSession, "flush", boom)
    async with SessionFactory() as s:
        with pytest.raises(ConflictError) as err:
            await user_service.delete_user(s, victim.id, actor_user_id=admin.id)
        assert err.value.code == "has_data"


async def test_invite_unique_violation_maps_to_email_exists(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(self: AsyncSession, *args: object, **kwargs: object) -> None:
        raise IntegrityError("INSERT", {}, _FakeDriverError("23505", "uq_users_email"))

    monkeypatch.setattr(AsyncSession, "flush", boom)
    async with SessionFactory() as s:
        with pytest.raises(ConflictError) as err:
            await user_service.invite_user(s, "moi@test.local")
        assert err.value.code == "email_exists"
