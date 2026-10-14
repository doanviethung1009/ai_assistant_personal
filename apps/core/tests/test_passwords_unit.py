"""Mật khẩu: băm argon2id, chính sách, mật khẩu tạm, kiểm không lộ. Không cần DB.

Spec: docs/specs/admin-users-local-login.md mục 3 và 7.1. Fixture autouse trong conftest thay
hasher bằng bản rẻ; test cấu hình thật dùng `PRODUCTION_HASHER`.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import pytest

from app.core import passwords
from app.services.clock import now_utc

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_production_hasher_uses_argon2id_rfc9106_low_memory() -> None:
    hashed = passwords.PRODUCTION_HASHER.hash("mot-mat-khau-bat-ky")
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert len(hashed) <= 255  # vừa cột password_hash varchar(255)


async def test_hash_is_salted_and_verifies() -> None:
    first = await passwords.hash_password("correct-horse-battery")
    second = await passwords.hash_password("correct-horse-battery")
    assert first != second
    assert (await passwords.verify_password(first, "correct-horse-battery")).ok
    assert not (await passwords.verify_password(first, "correct-horse-batterz")).ok


async def test_verify_without_hash_runs_dummy_and_never_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    original = passwords._verify_sync

    def counting(stored_hash: str, password: str) -> passwords.VerifyResult:
        calls.append(stored_hash)
        return original(stored_hash, password)

    monkeypatch.setattr(passwords, "_verify_sync", counting)
    result = await passwords.verify_password(None, "bat-ky-mat-khau-nao")
    assert result.ok is False
    # Vẫn tốn đúng một lần verify, trên hash giả.
    assert calls == [passwords._DUMMY_HASH]


async def test_verify_garbage_hash_or_surrogate_is_false_not_error() -> None:
    assert not (await passwords.verify_password("khong-phai-hash", "x" * 12)).ok
    good = await passwords.hash_password("correct-horse-battery")
    assert not (await passwords.verify_password(good, "loi\ud800le")).ok


async def test_old_parameters_request_rehash() -> None:
    from argon2 import PasswordHasher

    weaker = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    # Hash tạo bằng tham số khác `_hasher` hiện hành (fast: t=1,m=8,p=1) -> cần rehash.
    stronger = PasswordHasher(time_cost=2, memory_cost=16, parallelism=1).hash("abcdefghijkl")
    assert (await passwords.verify_password(stronger, "abcdefghijkl")).needs_rehash
    same = await passwords.verify_password(weaker.hash("abcdefghijkl"), "abcdefghijkl")
    assert same.ok
    assert not same.needs_rehash


def test_policy_rejects_short_long_common_username_and_control_chars() -> None:
    assert any("ít nhất" in r for r in passwords.policy_violations("abcdefghijk"))
    assert passwords.policy_violations("x" * 129)
    assert any("phổ biến" in r for r in passwords.policy_violations("password1234"))
    assert any("phổ biến" in r for r in passwords.policy_violations("Password1234!"))
    assert any(
        "tên đăng nhập" in r
        for r in passwords.policy_violations("xin-chao-c.nguyen-99", username="c.nguyen")
    )
    assert any(
        "tên đăng nhập" in r
        for r in passwords.policy_violations("an-toan-nguyenvanb-1", email="nguyenvanb@x.vn")
    )
    assert passwords.policy_violations("mat-khau-\x00-dai-du-dai")
    same = passwords.policy_violations(
        "mat-khau-moi-123",
        current_password="mat-khau-moi-123",  # noqa: S106
    )
    assert any("trùng" in r for r in same)


def test_policy_accepts_vietnamese_passphrase_with_spaces() -> None:
    assert passwords.policy_violations("Trời nắng đẹp lắm") == []
    # 12 code point tiếng Việt có dấu cách, nhiều byte hơn 12.
    assert passwords.policy_violations("đường về nhà") == []


def test_policy_short_identity_parts_do_not_cause_false_rejection() -> None:
    assert passwords.policy_violations("ngua-van-song-mai", username="an", email="a@x.vn") == []


def test_policy_message_never_echoes_password() -> None:
    secret = "AbC-Rat-Bi-Mat-12"  # noqa: S105
    reasons = passwords.policy_violations(secret, username="abc-rat-bi-mat")
    assert reasons
    assert all(secret.lower() not in r.lower() for r in reasons)


def test_temporary_password_shape() -> None:
    seen = {passwords.generate_temporary_password() for _ in range(50)}
    assert len(seen) == 50
    for value in seen:
        assert len(value) == 16
        assert set(value) <= set(passwords.TEMP_PASSWORD_ALPHABET)
        assert not set(value) & set("0O1lI")
    # Mật khẩu tạm không bao giờ vi phạm chính sách về độ dài.
    assert len(passwords.generate_temporary_password()) >= passwords.MIN_LENGTH


def test_temporary_password_expiry() -> None:
    now = now_utc()
    assert not passwords.temporary_password_expired(False, now - timedelta(days=30), now)
    assert not passwords.temporary_password_expired(True, now - timedelta(hours=71), now)
    assert passwords.temporary_password_expired(True, now - timedelta(hours=73), now)
    assert passwords.temporary_password_expired(True, None, now)


def test_common_password_file_has_source_header() -> None:
    head = (APP_DIR / "core" / "data" / "common-passwords.txt").read_text(encoding="utf-8")[:600]
    assert "SecLists" in head
    assert "MIT" in head


def test_no_log_call_mentions_secrets() -> None:
    """Grep nghiệm thu 7.1: không dòng log nào có password / temporary_password / password_hash."""
    pattern = re.compile(
        r"log(ger)?\.(debug|info|warning|error|exception)\(.*(password|password_hash)",
        re.IGNORECASE,
    )
    offenders = [
        f"{path.relative_to(APP_DIR)}:{number}"
        for path in APP_DIR.rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert offenders == []
