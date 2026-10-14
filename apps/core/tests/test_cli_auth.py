"""CLI `python -m app.cli.auth` cho tài khoản nội bộ: create-local, reset-password, unlock, enable.

Chạy CLI như người dùng (subprocess, đúng env của test). Spec: docs/specs/admin-users-local-login.md
mục 6.1 và 7.1. Cần Postgres (`db`).
"""

from __future__ import annotations

import asyncio
import os
import subprocess  # chạy CLI của chính repo để kiểm đầu-cuối
import sys

import httpx
import pytest
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models.audit_log import AuditLog
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from tests.conftest import ROOT, create_local_persona

pytestmark = pytest.mark.db

LOGIN_PW = "/api/v1/auth/login/password"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - đối số là hằng của test
        [sys.executable, "-m", "app.cli.auth", *args],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


async def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(_cli, *args)


async def _audit(action: str) -> list[AuditLog]:
    async with SessionFactory() as s:
        rows = await s.scalars(select(AuditLog).where(AuditLog.action == action))
        return list(rows.all())


async def _by_username(username: str) -> User:
    async with SessionFactory() as s:
        user = await s.scalar(select(User).where(User.username == username))
        assert user is not None
        return user


async def test_create_local_prints_one_temp_password_and_it_logs_in(
    anon_client: httpx.AsyncClient,
) -> None:
    out = await _run(
        "create-local", "--username", "Cli.User", "--email", "Cli.User@Test.local", "--role", "lead"
    )
    assert out.returncode == 0, out.stderr
    lines = out.stdout.strip().splitlines()
    temp = lines[-1]
    assert len(temp) == 16 and temp.isalnum()
    assert out.stdout.count(temp) == 1  # in đúng một lần
    assert temp not in out.stderr

    login = await anon_client.post(LOGIN_PW, json={"identifier": "cli.user", "password": temp})
    assert login.status_code == 200
    assert login.json()["role"] == "lead"

    created = await _audit("user_created")
    assert len(created) == 1 and created[0].details == {
        "provider": "local",
        "role": "lead",
        "via": "cli",
    }
    assert temp not in str(created[0].details)

    dup = await _run("create-local", "--username", "cli.user", "--email", "khac@test.local")
    assert dup.returncode == 2 and "đã" in dup.stderr


async def test_enable_local_user_becomes_active_not_invited(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("c.nguyen", status=UserStatus.DISABLED)
    out = await _run("enable", "--email", who.email)
    assert out.returncode == 0, out.stderr
    assert (await _by_username("c.nguyen")).status is UserStatus.ACTIVE
    changed = await _audit("user_status_changed")
    assert changed[0].details == {"from": "disabled", "to": "active", "via": "cli"}


async def test_disable_bumps_session_version_and_warns_when_no_admin(
    anon_client: httpx.AsyncClient,
) -> None:
    who = await create_local_persona("quan.tri", role=UserRole.ADMIN)
    out = await _run("disable", "--email", who.email)
    assert out.returncode == 0, out.stderr
    assert "CẢNH BÁO" in out.stderr  # CLI không bị chặn nhưng phải báo
    user = await _by_username("quan.tri")
    assert (user.status, user.session_version) == (UserStatus.DISABLED, 1)


async def test_reset_password_and_unlock_audit_via_cli(anon_client: httpx.AsyncClient) -> None:
    who = await create_local_persona("c.nguyen")
    for _ in range(5):
        await anon_client.post(
            LOGIN_PW, json={"identifier": "c.nguyen", "password": "sai-mat-khau-sai-sai"}
        )
    assert (await _by_username("c.nguyen")).locked_until is not None

    unlock = await _run("unlock", "--username", "c.nguyen")
    assert unlock.returncode == 0, unlock.stderr
    assert (await _by_username("c.nguyen")).locked_until is None
    assert (await _audit("user_unlocked"))[0].details == {"via": "cli"}

    reset = await _run("reset-password", "--email", who.email)
    assert reset.returncode == 0, reset.stderr
    temp = reset.stdout.strip().splitlines()[-1]
    assert len(temp) == 16
    user = await _by_username("c.nguyen")
    assert user.must_change_password is True and user.session_version == 1
    assert (await _audit("password_reset"))[0].details == {"via": "cli"}
    login = await anon_client.post(LOGIN_PW, json={"identifier": "c.nguyen", "password": temp})
    assert login.status_code == 200

    missing = await _run("reset-password", "--username", "khong.co")
    assert missing.returncode == 2
