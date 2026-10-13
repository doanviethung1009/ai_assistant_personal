"""Xác thực: JWT web->core, đăng nhập invite-only, `/me`, rate limit, CLI và migration.

Spec: docs/specs/auth-multiuser.md mục 4, 6, 7.3, 9.1. Test phân quyền theo endpoint và cô lập
dữ liệu nằm ở test_isolation.py.
"""

from __future__ import annotations

import asyncio
import os
import subprocess  # chạy CLI của chính repo để kiểm đầu-cuối
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.auth import JWT_AUDIENCE, JWT_ISSUER, mint_token, peek_subject
from app.core.config import settings
from app.core.permissions import ROLE_PERMISSIONS, Permission
from app.db.session import SessionFactory
from app.models.enums import UserRole, UserStatus
from tests.conftest import API_KEY, ROOT, Persona, create_persona
from tests.test_task_scope import _alembic, _sql

pytestmark = pytest.mark.db

ME = "/api/v1/me"
LOGIN = "/api/v1/auth/login"
SECRET = "test-core-jwt-secret-0123456789-abcdef"  # noqa: S105 - khớp tests/conftest.py


def _claims(sub: uuid.UUID, sv: int = 0, **over: Any) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": str(sub),
        "sv": sv,
        "iat": now,
        "exp": now + 60,
        "jti": uuid.uuid4().hex,
    }
    claims.update(over)
    return claims


def _bearer(token: str) -> dict[str, str]:
    return {"X-API-Key": API_KEY, "Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════
#  JWT
# ═══════════════════════════════════════════════════════════════════════


async def test_valid_token_returns_me(anon_client: httpx.AsyncClient) -> None:
    who = await create_persona("me@test.local", UserRole.LEAD, ("Mai",))
    resp = await anon_client.get(ME, headers=who.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["id"], body["email"], body["role"], body["status"]) == (
        str(who.id),
        "me@test.local",
        "lead",
        "active",
    )
    assert body["aliases"] == [{"source": "jira", "alias": "Mai"}]
    assert set(body["permissions"]) == {p.value for p in ROLE_PERMISSIONS[UserRole.LEAD]}


async def test_missing_authorization_is_401_token_invalid(anon_client: httpx.AsyncClient) -> None:
    resp = await anon_client.get(ME)
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_valid_jwt_without_api_key_is_still_rejected() -> None:
    from app.main import app

    who = await create_persona("nokey@test.local")
    token = who.headers["Authorization"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as bare:  # không có header mặc định nào
        resp = await bare.get(ME, headers={"Authorization": token})
    assert resp.status_code == 401  # thiếu X-API-Key


async def test_wrong_api_key_is_403_even_with_valid_jwt(anon_client: httpx.AsyncClient) -> None:
    who = await create_persona("wrongkey@test.local")
    resp = await anon_client.get(ME, headers={**who.headers, "X-API-Key": "sai-api-key-sai-api"})
    assert resp.status_code == 403


async def _expect_invalid(client: httpx.AsyncClient, token: str) -> None:
    resp = await client.get(ME, headers=_bearer(token))
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"] == "token_invalid"
    # Không lộ lý do chi tiết (chữ ký, hết hạn, aud...) và không echo token.
    assert token not in resp.text


async def test_bad_tokens_are_rejected(anon_client: httpx.AsyncClient) -> None:
    who = await create_persona("badtok@test.local")
    sub = who.id
    now = int(time.time())

    forged = jwt.encode(_claims(sub), "khoa-gia-mao-khoa-gia-mao-khoa-gia", algorithm="HS256")
    await _expect_invalid(anon_client, forged)

    # alg=none: dựng tay vì PyJWT từ chối ký không khoá.
    none_token = jwt.encode(_claims(sub), None, algorithm="none")
    await _expect_invalid(anon_client, none_token)

    await _expect_invalid(anon_client, jwt.encode(_claims(sub, aud="khac"), SECRET, "HS256"))
    await _expect_invalid(anon_client, jwt.encode(_claims(sub, iss="khac"), SECRET, "HS256"))
    expired = _claims(sub, iat=now - 300, exp=now - 200)
    await _expect_invalid(anon_client, jwt.encode(expired, SECRET, "HS256"))
    # Sống quá lâu (exp - iat > 120) dù chưa hết hạn: web lỗi hoặc ai đó ký token dài hạn.
    too_long = _claims(sub, iat=now, exp=now + 3600)
    await _expect_invalid(anon_client, jwt.encode(too_long, SECRET, "HS256"))
    # Thiếu claim bắt buộc.
    for missing in ("exp", "iat", "sub", "sv", "jti", "iss", "aud"):
        claims = _claims(sub)
        del claims[missing]
        await _expect_invalid(anon_client, jwt.encode(claims, SECRET, "HS256"))
    await _expect_invalid(anon_client, jwt.encode(_claims(sub, sv="0"), SECRET, "HS256"))
    await _expect_invalid(
        anon_client, jwt.encode({**_claims(sub), "sub": "khong-phai-uuid"}, SECRET, "HS256")
    )
    await _expect_invalid(anon_client, "khong.phai.jwt")


async def test_token_signed_with_other_algorithm_is_rejected(
    anon_client: httpx.AsyncClient,
) -> None:
    """Ghim algorithms=["HS256"]: token HS512 dù cùng khoá vẫn bị từ chối."""
    who = await create_persona("hs512@test.local")
    await _expect_invalid(anon_client, jwt.encode(_claims(who.id), SECRET, algorithm="HS512"))


async def test_unknown_user_is_user_inactive(anon_client: httpx.AsyncClient) -> None:
    resp = await anon_client.get(ME, headers=_bearer(mint_token(uuid.uuid4(), 0)))
    assert resp.status_code == 401 and resp.json()["code"] == "user_inactive"


async def test_disabling_a_user_takes_effect_on_the_very_next_request(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_persona("disable@test.local")
    assert (await anon_client.get(ME, headers=who.headers)).status_code == 200
    async with SessionFactory() as s:
        await s.execute(text("UPDATE users SET status = 'disabled' WHERE id = :i"), {"i": who.id})
        await s.commit()
    resp = await anon_client.get(ME, headers=who.headers)
    assert resp.status_code == 401 and resp.json()["code"] == "user_inactive"


async def test_bumping_session_version_revokes_old_tokens(anon_client: httpx.AsyncClient) -> None:
    who = await create_persona("revoke@test.local")
    old = who.headers
    assert (await anon_client.get(ME, headers=old)).status_code == 200
    async with SessionFactory() as s:
        await s.execute(
            text("UPDATE users SET session_version = session_version + 1 WHERE id = :i"),
            {"i": who.id},
        )
        await s.commit()
    resp = await anon_client.get(ME, headers=old)
    assert resp.status_code == 401 and resp.json()["code"] == "user_inactive"
    fresh = _bearer(mint_token(who.id, 1))
    assert (await anon_client.get(ME, headers=fresh)).status_code == 200


async def test_invited_user_cannot_use_api_before_first_login(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_persona("invited@test.local", status=UserStatus.INVITED)
    resp = await anon_client.get(ME, headers=who.headers)
    assert resp.status_code == 401 and resp.json()["code"] == "user_inactive"


async def test_every_user_route_requires_a_jwt(anon_client: httpx.AsyncClient) -> None:
    """Quét mọi route /api/v1 trong OpenAPI: trừ /auth/login, đều phải 401 khi thiếu JWT."""
    from app.main import app

    checked = 0
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api/v1") or path == LOGIN:
            continue
        url = path
        for name in ("task_id", "note_id", "project_id", "connection_id"):
            url = url.replace("{" + name + "}", str(uuid.uuid4()))
        for method in methods:
            resp = await anon_client.request(method.upper(), url, json={})
            assert resp.status_code == 401, (method, path, resp.status_code)
            assert resp.json()["code"] == "token_invalid", (method, path)
            checked += 1
    assert checked > 30  # đủ lớn để chắc là quét thật chứ không phải vòng lặp rỗng


def test_peek_subject_only_trusts_valid_tokens() -> None:
    sub = uuid.uuid4()
    assert peek_subject(mint_token(sub, 0)) == str(sub)
    assert (
        peek_subject(jwt.encode(_claims(sub), "khoa-gia-khoa-gia-khoa-gia-khoa-gia", "HS256"))
        is None
    )
    assert peek_subject("rac") is None


# ═══════════════════════════════════════════════════════════════════════
#  /auth/login
# ═══════════════════════════════════════════════════════════════════════


def _login(email: str, sub: str = "sub-1", **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "google_sub": sub,
        "email": email,
        "email_verified": True,
        "name": "Người Dùng",
        "client_ip": "203.0.113.7",
    }
    body.update(over)
    return body


async def _audit_rows() -> list[Any]:
    async with SessionFactory() as s:
        rows = await s.execute(
            text(
                "SELECT action, details, host(client_ip) AS ip, actor_user_id "
                "FROM audit_log ORDER BY created_at, id"
            )
        )
        return list(rows.mappings().all())


async def _invite(email: str, role: str = "member") -> uuid.UUID:
    from app.services import user_service

    async with SessionFactory() as s:
        user = await user_service.invite(s, email, UserRole(role))
        await s.commit()
        return user.id


async def test_login_requires_api_key_but_not_jwt(anon_client: httpx.AsyncClient) -> None:
    from app.main import app

    await _invite("key@test.local")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as bare:
        no_key = await bare.post(LOGIN, json=_login("key@test.local"))
    assert no_key.status_code == 401
    ok = await anon_client.post(LOGIN, json=_login("key@test.local"))
    assert ok.status_code == 200


async def test_not_invited_email_is_denied_and_audited(anon_client: httpx.AsyncClient) -> None:
    resp = await anon_client.post(LOGIN, json=_login("la@test.local"))
    assert resp.status_code == 403 and resp.json()["code"] == "not_invited"
    # Thông báo chung: không nói email có hay không trong hệ thống.
    assert "la@test.local" not in resp.text
    [row] = await _audit_rows()
    assert row["action"] == "login_denied"
    assert row["details"] == {"reason": "not_invited", "email": "la@test.local"}
    assert row["ip"] == "203.0.113.7"


async def test_unverified_email_is_denied(anon_client: httpx.AsyncClient) -> None:
    await _invite("unv@test.local")
    resp = await anon_client.post(LOGIN, json=_login("unv@test.local", email_verified=False))
    assert resp.status_code == 403 and resp.json()["code"] == "email_unverified"


async def test_invite_matches_case_insensitively_and_activates(
    anon_client: httpx.AsyncClient,
) -> None:
    uid = await _invite("X@Gmail.com")
    resp = await anon_client.post(LOGIN, json=_login("x@gmail.com", sub="sub-x"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"user_id": str(uid), "role": "member", "session_version": 0}
    async with SessionFactory() as s:
        row = (
            await s.execute(
                text("SELECT status, google_sub, name, last_login_at FROM users WHERE id = :i"),
                {"i": uid},
            )
        ).one()
    assert (row.status, row.google_sub, row.name) == ("active", "sub-x", "Người Dùng")
    assert row.last_login_at is not None
    assert [r["action"] for r in await _audit_rows()] == ["login_success"]
    # Từ giờ JWT của user này dùng được.
    assert (
        await anon_client.get(ME, headers=_bearer(mint_token(uid, body["session_version"])))
    ).status_code == 200


async def test_gmail_dots_and_plus_tags_are_not_normalized(
    anon_client: httpx.AsyncClient,
) -> None:
    await _invite("a.b@gmail.com")
    for email in ("ab@gmail.com", "a.b+tag@gmail.com"):
        resp = await anon_client.post(LOGIN, json=_login(email, sub="sub-" + email))
        assert resp.status_code == 403 and resp.json()["code"] == "not_invited"


async def test_second_login_with_same_sub_works_and_updates_changed_email(
    anon_client: httpx.AsyncClient,
) -> None:
    uid = await _invite("old@test.local")
    assert (
        await anon_client.post(LOGIN, json=_login("old@test.local", sub="s1"))
    ).status_code == 200
    again = await anon_client.post(LOGIN, json=_login("new@test.local", sub="s1"))
    assert again.status_code == 200 and again.json()["user_id"] == str(uid)
    async with SessionFactory() as s:
        email = await s.scalar(text("SELECT email FROM users WHERE id = :i"), {"i": uid})
    assert email == "new@test.local"


async def test_email_change_colliding_with_another_user_is_account_mismatch(
    anon_client: httpx.AsyncClient,
) -> None:
    await _invite("one@test.local")
    await _invite("two@test.local")
    assert (
        await anon_client.post(LOGIN, json=_login("one@test.local", sub="s1"))
    ).status_code == 200
    resp = await anon_client.post(LOGIN, json=_login("two@test.local", sub="s1"))
    assert resp.status_code == 403 and resp.json()["code"] == "account_mismatch"


async def test_other_google_account_cannot_take_over_an_activated_invite(
    anon_client: httpx.AsyncClient,
) -> None:
    await _invite("owned@test.local")
    assert (
        await anon_client.post(LOGIN, json=_login("owned@test.local", sub="real"))
    ).status_code == 200
    resp = await anon_client.post(LOGIN, json=_login("owned@test.local", sub="attacker"))
    assert resp.status_code == 403 and resp.json()["code"] == "account_mismatch"


async def test_disabled_user_cannot_login(anon_client: httpx.AsyncClient) -> None:
    uid = await _invite("dis@test.local")
    assert (
        await anon_client.post(LOGIN, json=_login("dis@test.local", sub="s1"))
    ).status_code == 200
    async with SessionFactory() as s:
        await s.execute(text("UPDATE users SET status = 'disabled' WHERE id = :i"), {"i": uid})
        await s.commit()
    # Cả đăng nhập theo sub lẫn theo email đều bị từ chối.
    by_sub = await anon_client.post(LOGIN, json=_login("dis@test.local", sub="s1"))
    assert by_sub.status_code == 403 and by_sub.json()["code"] == "disabled"
    disabled_invite = await _invite("dis2@test.local")
    async with SessionFactory() as s:
        await s.execute(
            text("UPDATE users SET status = 'disabled' WHERE id = :i"), {"i": disabled_invite}
        )
        await s.commit()
    by_email = await anon_client.post(LOGIN, json=_login("dis2@test.local", sub="s2"))
    assert by_email.status_code == 403 and by_email.json()["code"] == "disabled"


async def test_hosted_domain_allowlist(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "google_allowed_hd", ["a.com"])
    await _invite("hd@a.com")
    wrong = await anon_client.post(LOGIN, json=_login("hd@a.com", hd="b.com"))
    missing = await anon_client.post(LOGIN, json=_login("hd@a.com"))
    assert (wrong.status_code, missing.status_code) == (403, 403)
    assert wrong.json()["code"] == missing.json()["code"] == "hd_not_allowed"
    ok = await anon_client.post(LOGIN, json=_login("hd@a.com", hd="A.com"))
    assert ok.status_code == 200


async def test_malformed_login_bodies(anon_client: httpx.AsyncClient) -> None:
    for body in (
        {},
        _login("không-phải-email"),
        _login("a@b.c", google_sub=""),
        _login("a@b.c", extra_field="x"),
        {**_login("a@b.c"), "id_token": "eyJ-khong-bao-gio-duoc-gui"},
    ):
        resp = await anon_client.post(LOGIN, json=body)
        assert resp.status_code in (403, 422), body
    # 422 của route đăng nhập không echo lại claim.
    resp = await anon_client.post(LOGIN, json={**_login("a@b.c"), "id_token": "eyJ-secret-token"})
    assert "eyJ-secret-token" not in resp.text


async def test_every_login_attempt_is_audited_without_secrets(
    anon_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    await _invite("log@test.local")
    await anon_client.post(LOGIN, json=_login("nobody@test.local"))
    await anon_client.post(LOGIN, json=_login("log@test.local", sub="sub-log"))
    rows = await _audit_rows()
    assert [r["action"] for r in rows] == ["login_denied", "login_success"]
    assert "sub-log" not in str(rows)  # google_sub không vào nhật ký
    assert "sub-log" not in caplog.text


# ═══════════════════════════════════════════════════════════════════════
#  Rate limit
# ═══════════════════════════════════════════════════════════════════════


def test_rate_limit_identity_prefers_user_from_valid_jwt() -> None:
    from starlette.requests import Request

    def request(headers: dict[str, str]) -> Request:
        raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        return Request({"type": "http", "headers": raw, "client": ("1.2.3.4", 1)})

    sub = uuid.uuid4()
    with_jwt = request({"X-API-Key": "k", "Authorization": f"Bearer {mint_token(sub, 0)}"})
    assert rate_limit._identity(with_jwt) == f"user:{sub}"
    forged = jwt.encode(_claims(sub), "khoa-gia-khoa-gia-khoa-gia-khoa-gia", "HS256")
    assert (
        rate_limit._identity(request({"X-API-Key": "k", "Authorization": f"Bearer {forged}"}))
        == "key:k"
    )
    assert rate_limit._identity(request({})) == "ip:1.2.3.4"


async def test_login_limits_per_ip_and_global(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.errors import TooManyRequestsError

    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    counts: dict[str, int] = {}

    async def fake_hit(key: str) -> int:
        counts[key] = counts.get(key, 0) + 1
        return counts[key]

    monkeypatch.setattr(rate_limit, "_hit", fake_hit)
    for _ in range(rate_limit.LOGIN_LIMIT_PER_IP):
        await rate_limit.enforce_login_limits("198.51.100.1")
    with pytest.raises(TooManyRequestsError):
        await rate_limit.enforce_login_limits("198.51.100.1")
    # IP khác có bucket riêng cho tới khi chạm trần toàn cục.
    await rate_limit.enforce_login_limits("198.51.100.2")
    counts["login-global"] = rate_limit.LOGIN_LIMIT_GLOBAL
    with pytest.raises(TooManyRequestsError):
        await rate_limit.enforce_login_limits("198.51.100.3")


async def test_login_limit_returns_429_over_http(
    anon_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    async def always_over(key: str) -> int:
        return 10_000 if key.startswith("login") else 1

    monkeypatch.setattr(rate_limit, "_hit", always_over)
    resp = await anon_client.post(LOGIN, json=_login("a@test.local"))
    assert resp.status_code == 429


# ═══════════════════════════════════════════════════════════════════════
#  /me
# ═══════════════════════════════════════════════════════════════════════


def test_role_permission_matrix_matches_spec() -> None:
    P = Permission
    assert ROLE_PERMISSIONS[UserRole.MEMBER] == {P.TASK_READ_WORK}
    assert ROLE_PERMISSIONS[UserRole.LEAD] == {
        P.TASK_READ_WORK,
        P.TASK_WRITE_ANY_WORK,
        P.TEAM_READ,
        P.INTEGRATION_SYNC,
        P.PROJECT_WRITE_ANY,
    }
    assert ROLE_PERMISSIONS[UserRole.ADMIN] == set(P)


async def test_me_timezone_roundtrip(client: httpx.AsyncClient) -> None:
    resp = await client.put(f"{ME}/timezone", json={"timezone": "Asia/Tokyo"})
    assert resp.status_code == 200 and resp.json()["effective_timezone"] == "Asia/Tokyo"
    assert (await client.put(f"{ME}/timezone", json={"timezone": "Mars/Base"})).status_code == 422
    assert (await client.get(ME)).json()["timezone"] == "Asia/Tokyo"


# ═══════════════════════════════════════════════════════════════════════
#  ADMIN_EMAILS và CLI
# ═══════════════════════════════════════════════════════════════════════


async def test_sync_admin_emails_creates_and_promotes_without_touching_status(
    session: AsyncSession,
) -> None:
    from app.services import user_service

    member = await create_persona("promote@test.local", UserRole.MEMBER)
    changed = await user_service.sync_admin_emails(
        session, [" Promote@Test.local ", "new-admin@test.local", "khong-phai-email"]
    )
    await session.commit()
    assert changed == 2
    rows = (
        await session.execute(text("SELECT email, role, status FROM users ORDER BY email"))
    ).all()
    assert [tuple(r) for r in rows] == [
        ("new-admin@test.local", "admin", "invited"),
        ("promote@test.local", "admin", "active"),  # đã active: giữ nguyên status
    ]
    assert member.id  # user cũ vẫn là chính nó
    assert await user_service.sync_admin_emails(session, ["promote@test.local"]) == 0


async def test_bootstrap_assigns_owner_validates_checks_and_is_idempotent(
    session: AsyncSession, default_user: Persona, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.cli.auth import CliError, bootstrap

    # Dựng dữ liệu "trước đăng nhập": gỡ hai CHECK, chèn dòng không chủ, rồi thêm lại NOT VALID.
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    await session.execute(text("ALTER TABLE tasks DROP CONSTRAINT ck_tasks_personal_has_owner"))
    await session.execute(text("ALTER TABLE notes DROP CONSTRAINT ck_notes_owner_required"))
    task_p, task_w, note = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO tasks (id, title, scope, created_at, updated_at) VALUES "
            "(:p, 'personal cũ', 'personal', :t, :t), (:w, 'work cũ', 'work', :t, :t)"
        ),
        {"p": task_p, "w": task_w, "t": stamp},
    )
    await session.execute(
        text(
            "INSERT INTO notes (id, title, content, created_at, updated_at) "
            "VALUES (:n, 'n', 'c', :t, :t)"
        ),
        {"n": note, "t": stamp},
    )
    await session.execute(
        text(
            "INSERT INTO app_settings (key, value) VALUES "
            "('current_users', '[\"Hùng\"]'), ('display_timezone', '\"Asia/Tokyo\"')"
        )
    )
    await session.execute(
        text(
            "ALTER TABLE tasks ADD CONSTRAINT ck_tasks_personal_has_owner "
            "CHECK (scope <> 'personal' OR owner_id IS NOT NULL) NOT VALID"
        )
    )
    await session.execute(
        text(
            "ALTER TABLE notes ADD CONSTRAINT ck_notes_owner_required "
            "CHECK (owner_id IS NOT NULL) NOT VALID"
        )
    )
    await session.commit()

    monkeypatch.setattr(settings, "admin_emails", [default_user.email])
    with pytest.raises(CliError):
        await bootstrap(session, "khong-phai-admin@test.local", dry_run=False)
    await session.rollback()

    dry = await bootstrap(session, default_user.email, dry_run=True)
    await session.rollback()
    assert (dry.tasks, dry.notes) == (1, 1)
    assert await session.scalar(text("SELECT count(*) FROM tasks WHERE owner_id IS NOT NULL")) == 0
    await session.rollback()

    real = await bootstrap(session, default_user.email, dry_run=False)
    await session.commit()
    assert (real.tasks, real.notes) == (1, 1)
    assert real.aliases_added == ["Hùng"] and real.timezone_set == "Asia/Tokyo"
    owners = {
        r.title: (r.owner_id, r.updated_at)
        for r in (
            await session.execute(text("SELECT title, owner_id, updated_at FROM tasks"))
        ).all()
    }
    assert owners["personal cũ"] == (default_user.id, stamp)  # updated_at KHÔNG đổi
    assert owners["work cũ"] == (None, stamp)  # work thuộc team
    note_row = (await session.execute(text("SELECT owner_id, updated_at FROM notes"))).one()
    assert (note_row.owner_id, note_row.updated_at) == (default_user.id, stamp)
    valid = (
        await session.execute(
            text(
                "SELECT conname, convalidated FROM pg_constraint WHERE conname IN "
                "('ck_tasks_personal_has_owner', 'ck_notes_owner_required')"
            )
        )
    ).all()
    assert {r.conname: r.convalidated for r in valid} == {
        "ck_tasks_personal_has_owner": True,
        "ck_notes_owner_required": True,
    }
    audit = await session.scalar(
        text("SELECT details FROM audit_log WHERE action = 'bootstrap_backfill'")
    )
    assert audit == {"tasks": 1, "notes": 1, "aliases": 1}
    await session.rollback()

    again = await bootstrap(session, default_user.email, dry_run=False)
    await session.commit()
    assert (again.tasks, again.notes) == (0, 0)
    assert again.aliases_added == [] and again.aliases_skipped == ["Hùng"]


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Chạy CLI như người dùng (`python -m app.cli.auth ...`) với đúng env của test."""
    return subprocess.run(  # noqa: S603 - đối số là hằng của test
        [sys.executable, "-m", "app.cli.auth", *args],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


async def test_cli_invite_then_token_end_to_end(anon_client: httpx.AsyncClient) -> None:
    out = await asyncio.to_thread(_cli, "invite", "--email", "Cli@Test.local", "--role", "lead")
    assert out.returncode == 0, out.stderr
    dup = await asyncio.to_thread(_cli, "invite", "--email", "cli@test.local")
    assert dup.returncode == 2 and "đã" in dup.stderr

    # Chưa đăng nhập Google lần nào: không mint được token.
    early = await asyncio.to_thread(_cli, "token", "--email", "cli@test.local")
    assert early.returncode == 2 and early.stdout.strip() == ""

    assert (
        await anon_client.post(LOGIN, json=_login("cli@test.local", sub="cli-sub"))
    ).status_code == 200
    tok = await asyncio.to_thread(_cli, "token", "--email", "cli@test.local")
    assert tok.returncode == 0, tok.stderr
    token = tok.stdout.strip()
    assert token.count(".") == 2
    resp = await anon_client.get(ME, headers=_bearer(token))
    assert resp.status_code == 200 and resp.json()["role"] == "lead"

    too_long = await asyncio.to_thread(_cli, "token", "--email", "cli@test.local", "--ttl", "9999")
    assert too_long.returncode == 2


# ═══════════════════════════════════════════════════════════════════════
#  Migration trên dữ liệu có sẵn
# ═══════════════════════════════════════════════════════════════════════


def test_migration_on_existing_data_then_roundtrip(migrated_db: None) -> None:
    """Ở a1c9e4b7d2f8 chèn task personal, task work, note; nâng lên head không lỗi, owner NULL,
    INSERT personal thiếu chủ bị CHECK từ chối; hạ rồi nâng lại vẫn sạch."""
    from sqlalchemy.exc import IntegrityError

    url = os.environ["TEST_DATABASE_URL"]
    t_personal, t_work, n = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        _alembic("downgrade", "a1c9e4b7d2f8")
        asyncio.run(
            _sql(
                url,
                [
                    (
                        "INSERT INTO tasks (id, title, scope) "
                        "VALUES (:p, 'p', 'personal'), (:w, 'w', 'work')",
                        {"p": t_personal, "w": t_work},
                    ),
                    ("INSERT INTO notes (id, title, content) VALUES (:n, 'n', 'c')", {"n": n}),
                ],
            )
        )
        _alembic("upgrade", "head")
        rows = asyncio.run(
            _sql(
                url,
                [
                    ("SELECT count(*) FROM tasks WHERE owner_id IS NULL", {}),
                    ("SELECT count(*) FROM notes WHERE owner_id IS NULL", {}),
                    (
                        "SELECT conname, convalidated FROM pg_constraint WHERE conname IN "
                        "('ck_tasks_personal_has_owner', 'ck_notes_owner_required')",
                        {},
                    ),
                ],
            )
        )
        assert rows[0][0][0] == 2 and rows[1][0][0] == 1
        assert dict(rows[2]) == {
            "ck_tasks_personal_has_owner": False,
            "ck_notes_owner_required": False,
        }
        with pytest.raises(IntegrityError, match="ck_tasks_personal_has_owner"):
            asyncio.run(
                _sql(
                    url,
                    [
                        (
                            "INSERT INTO tasks (id, title, scope) VALUES (:i, 'x', 'personal')",
                            {"i": uuid.uuid4()},
                        )
                    ],
                )
            )
        with pytest.raises(IntegrityError, match="ck_notes_owner_required"):
            asyncio.run(
                _sql(
                    url,
                    [
                        (
                            "INSERT INTO notes (id, title, content) VALUES (:i, 'x', 'c')",
                            {"i": uuid.uuid4()},
                        )
                    ],
                )
            )
        # Hạ rồi nâng lại: dữ liệu cũ còn nguyên.
        _alembic("downgrade", "a1c9e4b7d2f8")
        left = asyncio.run(_sql(url, [("SELECT count(*) FROM tasks", {})]))[0][0][0]
        assert left == 2
        _alembic("upgrade", "head")
    finally:
        _alembic("upgrade", "head")
        asyncio.run(
            _sql(
                url,
                [
                    (
                        "TRUNCATE task_events, tasks, notes, projects, user_aliases, audit_log, "
                        "users CASCADE",
                        {},
                    )
                ],
            )
        )
