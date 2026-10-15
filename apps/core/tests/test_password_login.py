"""Đăng nhập bằng mật khẩu, khoá tạm, ép đổi mật khẩu, `/me/password`, chặn Google chiếm tài khoản.

Spec: docs/specs/admin-users-local-login.md mục 3, 4.1, 7.1. Cần Postgres (`db`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core import passwords, rate_limit
from app.core.auth import mint_token
from app.core.config import settings
from app.db.session import SessionFactory
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, UserRole, UserStatus
from app.models.user import User
from app.services.clock import now_utc
from app.services.errors import TooManyRequestsError
from tests.conftest import API_KEY, LocalPersona, create_local_persona, create_persona
from tests.test_task_scope import _alembic, _sql

pytestmark = pytest.mark.db

LOGIN_PW = "/api/v1/auth/login/password"
LOGIN_GOOGLE = "/api/v1/auth/login"
ME = "/api/v1/me"
CHANGE = "/api/v1/me/password"
GENERIC = "Sai thông tin đăng nhập hoặc tài khoản tạm bị khoá"
FORBIDDEN_DETAIL_KEYS = {"password", "identifier", "temporary_password", "password_hash"}


async def _login(client: httpx.AsyncClient, identifier: str, password: str) -> httpx.Response:
    return await client.post(LOGIN_PW, json={"identifier": identifier, "password": password})


async def _audit_rows() -> list[AuditLog]:
    async with SessionFactory() as s:
        rows = await s.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id))
        return list(rows.all())


async def _user(user_id: uuid.UUID) -> User:
    async with SessionFactory() as s:
        user = await s.get(User, user_id)
        assert user is not None
        return user


def _bearer(user_id: uuid.UUID, sv: int) -> dict[str, str]:
    return {"X-API-Key": API_KEY, "Authorization": f"Bearer {mint_token(user_id, sv)}"}


# ═══════════════════════════════════════════════════════════════════════
#  /auth/login/password
# ═══════════════════════════════════════════════════════════════════════


async def test_correct_password_returns_login_result_and_audits(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("c.nguyen")
    resp = await _login(anon_client, "c.nguyen", who.password)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"user_id": str(who.id), "role": "member", "session_version": 0}
    success = [r for r in await _audit_rows() if r.action == "login_success"]
    assert len(success) == 1
    assert success[0].details == {"method": "password"}
    assert (await _user(who.id)).last_login_at is not None


async def test_login_by_email_and_case_insensitive_username(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("mai.tran")
    assert (await _login(anon_client, "  MAI.Tran ", who.password)).status_code == 200
    assert (await _login(anon_client, "Mai.Tran@Test.Local", who.password)).status_code == 200


async def test_google_account_cannot_login_with_password(anon_client: httpx.AsyncClient) -> None:
    google = await create_persona("gg@test.local")
    resp = await _login(anon_client, "gg@test.local", "bat-ky-mat-khau-nao")
    assert resp.status_code == 403
    assert resp.json() == {"detail": GENERIC, "code": "invalid_credentials"}
    assert google.id  # tồn tại nhưng không đăng nhập được bằng mật khẩu


async def test_wrong_password_and_unknown_identifier_are_indistinguishable(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("c.nguyen")
    wrong = await _login(anon_client, "c.nguyen", "sai-mat-khau-sai-sai")
    unknown = await _login(anon_client, "khong.ton.tai", "sai-mat-khau-sai-sai")
    assert wrong.status_code == unknown.status_code == 403
    assert wrong.json() == unknown.json() == {"detail": GENERIC, "code": "invalid_credentials"}
    assert who.password not in wrong.text


async def test_exactly_one_argon2_verify_per_request(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = await create_local_persona("c.nguyen")
    calls: list[str] = []
    original = passwords._verify_sync

    def counting(stored_hash: str, password: str) -> passwords.VerifyResult:
        calls.append(stored_hash)
        return original(stored_hash, password)

    monkeypatch.setattr(passwords, "_verify_sync", counting)
    assert (await _login(anon_client, "khong.ton.tai", "mat-khau-nao-do-1")).status_code == 403
    assert len(calls) == 1
    assert calls[0] == passwords._DUMMY_HASH

    calls.clear()
    assert (await _login(anon_client, "c.nguyen", "mat-khau-nao-do-2")).status_code == 403
    assert len(calls) == 1
    assert calls[0] != passwords._DUMMY_HASH

    # Kể cả khi đang khoá: vẫn một lần verify, không thêm đường tắt.
    for _ in range(4):
        await _login(anon_client, "c.nguyen", "mat-khau-nao-do-3")
    calls.clear()
    assert (await _login(anon_client, "c.nguyen", who.password)).status_code == 403
    assert len(calls) == 1


async def test_five_wrong_lock_account_even_for_correct_password_until_unlocked(
    anon_client: httpx.AsyncClient,
) -> None:
    admin = await create_persona("admin@test.local", UserRole.ADMIN)
    who = await create_local_persona("c.nguyen")
    for _ in range(5):
        assert (await _login(anon_client, "c.nguyen", "sai-mat-khau-sai-sai")).status_code == 403

    user = await _user(who.id)
    assert user.locked_until is not None and user.locked_until > now_utc()
    assert user.failed_login_count == 0
    # Lần 6 với mật khẩu ĐÚNG vẫn bị từ chối, cùng thông báo.
    resp = await _login(anon_client, "c.nguyen", who.password)
    assert resp.status_code == 403
    assert resp.json() == {"detail": GENERIC, "code": "invalid_credentials"}
    actions = [r.action for r in await _audit_rows()]
    assert actions.count("login_locked") == 1
    assert actions.count("login_denied") == 6
    # Khi đang khoá không đếm thêm (kẻ đoán không gia hạn khoá mãi được).
    assert (await _user(who.id)).failed_login_count == 0

    unlock = await anon_client.post(
        f"/api/v1/admin/users/{who.id}/unlock", headers=admin.headers
    )
    assert unlock.status_code == 204
    assert (await _login(anon_client, "c.nguyen", who.password)).status_code == 200


async def test_success_resets_failed_counter(anon_client: httpx.AsyncClient) -> None:
    who = await create_local_persona("c.nguyen")
    for _ in range(4):
        await _login(anon_client, "c.nguyen", "sai-mat-khau-sai-sai")
    assert (await _user(who.id)).failed_login_count == 4
    assert (await _login(anon_client, "c.nguyen", who.password)).status_code == 200
    assert (await _user(who.id)).failed_login_count == 0


async def test_disabled_user_with_correct_password_gets_generic_error(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("c.nguyen", status=UserStatus.DISABLED)
    resp = await _login(anon_client, "c.nguyen", who.password)
    assert resp.status_code == 403
    assert resp.json() == {"detail": GENERIC, "code": "invalid_credentials"}
    denied = [r for r in await _audit_rows() if r.action == "login_denied"]
    assert denied[0].details is not None and denied[0].details["reason"] == "disabled"


async def test_temporary_password_expires_after_72_hours(anon_client: httpx.AsyncClient) -> None:
    fresh = await create_local_persona(
        "moi.tao",
        must_change_password=True,
        password_changed_at=now_utc() - timedelta(hours=71),
    )
    stale = await create_local_persona(
        "het.han",
        must_change_password=True,
        password_changed_at=now_utc() - timedelta(hours=73),
    )
    assert (await _login(anon_client, "moi.tao", fresh.password)).status_code == 200
    resp = await _login(anon_client, "het.han", stale.password)
    assert resp.status_code == 403
    assert resp.json() == {"detail": GENERIC, "code": "invalid_credentials"}


async def test_password_login_switch_off(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = await create_local_persona("c.nguyen")
    monkeypatch.setattr(settings, "password_login_enabled", False)
    resp = await _login(anon_client, "c.nguyen", who.password)
    assert resp.status_code == 403
    assert resp.json()["code"] == "password_login_disabled"


async def test_password_login_rate_limit_per_identifier(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    counts: dict[str, int] = {}
    keys: list[str] = []

    async def fake_hit(key: str) -> int:
        keys.append(key)
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(rate_limit, "_hit", fake_hit)
    for _ in range(rate_limit.PASSWORD_LOGIN_LIMIT_PER_IDENTIFIER):
        assert (await _login(anon_client, "ai.do", "sai-mat-khau-sai-sai")).status_code == 403
    resp = await _login(anon_client, "ai.do", "sai-mat-khau-sai-sai")
    assert resp.status_code == 429
    # Khoá Redis dùng hash, không chứa tên đăng nhập.
    assert not any("ai.do" in key for key in keys)
    # Identifier khác không bị ảnh hưởng bởi bucket theo identifier.
    other = await _login(anon_client, "nguoi.khac", "sai-mat-khau-sai-sai")
    assert other.status_code in (403, 429)


async def test_password_login_global_limit_is_a_loose_fuse_and_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    assert rate_limit.PASSWORD_LOGIN_LIMIT_GLOBAL == 300
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def fake_hit(key: str) -> int:
        return rate_limit.PASSWORD_LOGIN_LIMIT_GLOBAL + 1 if key == "login-pw-global" else 1

    monkeypatch.setattr(rate_limit, "_hit", fake_hit)
    with (
        caplog.at_level(logging.WARNING, logger="app.core.rate_limit"),
        pytest.raises(TooManyRequestsError),
    ):
        await rate_limit.enforce_password_login_limits("198.51.100.7", "ai.do@test.local")
    assert "login_global_limit_hit" in caplog.text
    assert "ai.do" not in caplog.text and "198.51.100.7" not in caplog.text


async def test_change_password_wrong_current_is_audited_without_secret(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("c.nguyen")
    wrong = "sai-mat-khau-hien-tai"
    resp = await anon_client.post(
        CHANGE, headers=who.headers, json={"current_password": wrong, "new_password": "x" * 12}
    )
    assert resp.status_code == 422
    async with SessionFactory() as s:
        rows = (
            await s.scalars(
                select(AuditLog).where(AuditLog.action == AuditAction.PASSWORD_CHANGE_FAILED.value)
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].actor_user_id == who.id and rows[0].target_id == who.id
    assert wrong not in str(rows[0].details) and "x" * 12 not in str(rows[0].details)


async def test_login_422_does_not_echo_password(anon_client: httpx.AsyncClient) -> None:
    secret = "mat-khau-rat-bi-mat-xyz"  # noqa: S105
    resp = await anon_client.post(
        LOGIN_PW, json={"identifier": "a", "password": secret, "khong_hop_le": 1}
    )
    assert resp.status_code == 422
    assert secret not in resp.text


async def test_audit_never_contains_identifier_or_password(anon_client: httpx.AsyncClient) -> None:
    who = await create_local_persona("c.nguyen")
    typo = "gõ-nhầm-mật-khẩu-vào-ô-tên"
    await _login(anon_client, typo, "sai-mat-khau-sai-sai")
    await _login(anon_client, "c.nguyen", "sai-mat-khau-sai-sai")
    await _login(anon_client, "c.nguyen", who.password)
    rows = await _audit_rows()
    assert rows
    blob = " ".join(str(r.details) for r in rows)
    for row in rows:
        assert not FORBIDDEN_DETAIL_KEYS & set((row.details or {}).keys())
    for needle in (typo, "sai-mat-khau-sai-sai", who.password):
        assert needle not in blob
    unknown = [
        r for r in rows if r.action == "login_denied" and r.target_id is None and r.details
    ]
    assert len(unknown) == 1
    assert len(unknown[0].details["identifier_sha256"]) == 16


# ═══════════════════════════════════════════════════════════════════════
#  Google không chiếm được tài khoản nội bộ
# ═══════════════════════════════════════════════════════════════════════


async def test_google_login_with_local_email_is_account_mismatch(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("c.nguyen")
    resp = await anon_client.post(
        LOGIN_GOOGLE,
        json={"google_sub": "sub-ke-tan-cong", "email": who.email, "email_verified": True},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "account_mismatch"
    user = await _user(who.id)
    assert user.google_sub is None
    denied = [r for r in await _audit_rows() if r.action == "login_denied"]
    assert denied[0].details is not None
    assert denied[0].details["reason"] == "provider_local"
    assert denied[0].details["provider"] == "local"


# ═══════════════════════════════════════════════════════════════════════
#  Ép đổi mật khẩu và /me/password
# ═══════════════════════════════════════════════════════════════════════

_ALLOWED_WHEN_MUST_CHANGE = {
    ("GET", "/api/v1/me"),
    ("POST", "/api/v1/me/password"),
}


def _guarded_routes() -> list[tuple[str, str]]:
    """Mọi (method, path) /api/v1 cần JWT, lấy từ OpenAPI (cùng cách `test_auth` quét route)."""
    from app.main import app

    found: list[tuple[str, str]] = []
    for template, methods in app.openapi()["paths"].items():
        if not template.startswith("/api/v1/") or template.startswith("/api/v1/auth/"):
            continue
        path = re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), template)
        for method in sorted(m.upper() for m in methods):
            if (method, template) not in _ALLOWED_WHEN_MUST_CHANGE:
                found.append((method, path))
    return found


async def test_must_change_password_blocks_every_other_route(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("c.nguyen", role=UserRole.ADMIN, must_change_password=True)
    me = await anon_client.get(ME, headers=who.headers)
    assert me.status_code == 200
    body = me.json()
    assert body["must_change_password"] is True
    assert body["auth_provider"] == "local"
    assert body["username"] == "c.nguyen"

    routes = _guarded_routes()
    assert len(routes) > 20  # đảm bảo test thật sự duyệt qua các route
    for method, path in routes:
        resp = await anon_client.request(method, path, headers=who.headers)
        assert resp.status_code == 403, (method, path, resp.status_code)
        assert resp.json()["code"] == "password_change_required", (method, path)


async def test_change_password_flow_kills_old_jwt_and_unblocks(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("c.nguyen", must_change_password=True)
    new = "mot-mat-khau-moi-dai-du"
    resp = await anon_client.post(
        CHANGE,
        headers=who.headers,
        json={"current_password": who.password, "new_password": new},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"session_version": 1}

    # JWT cũ (sv=0) chết, JWT sv mới dùng được và không còn bị chặn.
    old = await anon_client.get(ME, headers=who.headers)
    assert old.status_code == 401
    assert old.json()["code"] == "user_inactive"
    fresh = _bearer(who.id, 1)
    assert (await anon_client.get(ME, headers=fresh)).json()["must_change_password"] is False
    assert (await anon_client.get("/api/v1/tasks", headers=fresh)).status_code == 200

    assert (await _login(anon_client, "c.nguyen", new)).status_code == 200
    assert (await _login(anon_client, "c.nguyen", who.password)).status_code == 403
    changed = [r for r in await _audit_rows() if r.action == AuditAction.PASSWORD_CHANGED.value]
    assert len(changed) == 1


async def test_change_password_errors(anon_client: httpx.AsyncClient) -> None:
    who: LocalPersona = await create_local_persona("c.nguyen")
    wrong = await anon_client.post(
        CHANGE,
        headers=who.headers,
        json={"current_password": "sai-mat-khau-hien-tai", "new_password": "mot-mat-khau-moi-dai"},
    )
    # 422, KHÔNG phải 401: web coi 401 là hết phiên.
    assert wrong.status_code == 422
    assert wrong.json()["code"] == "current_password_invalid"

    weak = await anon_client.post(
        CHANGE,
        headers=who.headers,
        json={"current_password": who.password, "new_password": "password1234"},
    )
    assert weak.status_code == 422
    assert weak.json()["code"] == "weak_password"
    assert "password1234" not in weak.text

    same = await anon_client.post(
        CHANGE,
        headers=who.headers,
        json={"current_password": who.password, "new_password": who.password},
    )
    assert same.status_code == 422
    assert same.json()["code"] == "weak_password"

    google = await create_persona("gg@test.local")
    resp = await anon_client.post(
        CHANGE,
        headers=google.headers,
        json={"current_password": "x" * 12, "new_password": "mot-mat-khau-moi-dai"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "not_local_account"


async def test_change_password_rate_limit(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    who = await create_local_persona("c.nguyen")
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    seen: dict[str, int] = {}

    async def fake_window(key: str, window: int) -> int:
        seen[key] = seen.get(key, 0) + 1
        return seen[key]

    monkeypatch.setattr(rate_limit, "_hit_window", fake_window)
    body: dict[str, Any] = {"current_password": "sai-mat-khau-hien-tai", "new_password": "x" * 12}
    for _ in range(rate_limit.PASSWORD_CHANGE_LIMIT):
        resp = await anon_client.post(CHANGE, headers=who.headers, json=body)
        assert resp.status_code == 422
    resp = await anon_client.post(CHANGE, headers=who.headers, json=body)
    assert resp.status_code == 429


# ═══════════════════════════════════════════════════════════════════════
#  Migration
# ═══════════════════════════════════════════════════════════════════════


def test_migration_downgrade_disables_local_users_then_upgrades_again(migrated_db: None) -> None:
    """Hạ khi còn tài khoản nội bộ `active` không lỗi: nó thành `disabled` (CHECK cũ
    `active_has_sub` tạo lại được), phiên chết (sv+1); nâng lại vẫn sạch."""
    url = os.environ["TEST_DATABASE_URL"]
    uid = uuid.uuid4()
    try:
        asyncio.run(
            _sql(
                url,
                [
                    (
                        "INSERT INTO users (id, email, role, status, auth_provider, username, "
                        "password_hash) VALUES (:i, 'mig@test.local', 'member', 'active', "
                        "'local', 'mig.user', 'khong-phai-hash-that')",
                        {"i": uid},
                    )
                ],
            )
        )
        _alembic("downgrade", "e8a3c6f2b1d7")
        rows = asyncio.run(
            _sql(url, [("SELECT status, session_version FROM users WHERE id = :i", {"i": uid})])
        )
        assert rows[0][0] == ("disabled", 1)
        _alembic("upgrade", "head")
    finally:
        _alembic("upgrade", "head")
        asyncio.run(_sql(url, [("TRUNCATE audit_log, user_aliases, users CASCADE", {})]))
