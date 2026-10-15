"""Mật khẩu tài khoản nội bộ: băm argon2id, chính sách, mật khẩu tạm.

Spec: docs/specs/admin-users-local-login.md mục 3. Web KHÔNG băm và KHÔNG kiểm chính sách:
mọi thứ nằm ở đây để chỉ có một nơi quyết định.

══════════════════════════════════════════════════════════════════════
 MẬT KHẨU (rõ), HASH và MẬT KHẨU TẠM KHÔNG BAO GIỜ được log, đưa vào audit, vào thông báo
 lỗi hay vào `repr`. Module này không có logger vì lý do đó.
══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import asyncio
import functools
import re
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import anyio.to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.profiles import RFC_9106_LOW_MEMORY

# ═══════════════════════════════════════════════════════════════════════
#  Hằng (không phải env, xem spec Q5)
# ═══════════════════════════════════════════════════════════════════════

MIN_LENGTH = 12
MAX_LENGTH = 128
MAX_BYTES = 512
# Đăng nhập nhận dài hơn chính sách để người dùng gõ sai độ dài vẫn nhận lỗi chung, nhưng
# chặn payload khổng lồ đốt CPU của argon2.
LOGIN_MAX_LENGTH = 1024

MAX_FAILED_LOGINS = 5
LOCK_DURATION = timedelta(minutes=15)
TEMP_PASSWORD_TTL = timedelta(hours=72)

TEMP_PASSWORD_LENGTH = 16
# Bỏ các ký tự dễ nhầm (0/O, 1/l/I) vì mật khẩu tạm được đọc/chép tay.
TEMP_PASSWORD_ALPHABET = (
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"  # noqa: S105 - bảng chữ
)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_COMMON_FILE = Path(__file__).parent / "data" / "common-passwords.txt"
# Phần đuôi hay được thêm vào mật khẩu yếu ("password" -> "Password1234!").
_TRAILING_NOISE = string.digits + string.punctuation
# Với tên/email-trước-@ ngắn hơn ngưỡng này thì không so (tránh từ chối oan, vd "an").
_MIN_IDENTITY_LEN = 4

# ═══════════════════════════════════════════════════════════════════════
#  Băm
# ═══════════════════════════════════════════════════════════════════════

# RFC 9106 "low memory": t=3, m=64 MiB, p=4. `_hasher` là biến để test thay bằng bản rẻ qua
# monkeypatch; `PRODUCTION_HASHER` luôn giữ cấu hình thật để test khẳng định profile.
PRODUCTION_HASHER = PasswordHasher.from_parameters(RFC_9106_LOW_MEMORY)
_hasher = PRODUCTION_HASHER
# Tối đa 4 phép băm đồng thời mỗi tiến trình: trần ~256 MiB RAM, chặn DoS bằng đăng nhập dồn.
_hash_slots = asyncio.Semaphore(4)

# Hash của một chuỗi ngẫu nhiên, để user không tồn tại cũng tốn đúng một lần verify (thời gian
# phản hồi như nhau, chống liệt kê tài khoản).
_DUMMY_HASH = PRODUCTION_HASHER.hash(secrets.token_urlsafe(24))


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    needs_rehash: bool = False


async def hash_password(password: str) -> str:
    """Băm argon2id (muối ngẫu nhiên mỗi lần) trong thread, không chặn event loop."""
    async with _hash_slots:
        return await anyio.to_thread.run_sync(_hasher.hash, password)


def _verify_sync(stored_hash: str, password: str) -> VerifyResult:
    try:
        _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError, UnicodeError):
        # VerifyMismatch là con của VerificationError. UnicodeError: mật khẩu có surrogate lẻ
        # (JSON hợp lệ nhưng không mã hoá được UTF-8) coi như sai.
        return VerifyResult(ok=False)
    return VerifyResult(ok=True, needs_rehash=_hasher.check_needs_rehash(stored_hash))


async def verify_password(stored_hash: str | None, password: str) -> VerifyResult:
    """So mật khẩu với hash; `stored_hash=None` thì so với hash giả và luôn trả `ok=False`.

    LUÔN chạy đúng MỘT lần argon2 (hàm này là điểm duy nhất gọi verify khi đăng nhập), nên
    request cho user không tồn tại tốn thời gian như request cho user có thật.
    """
    target = stored_hash if stored_hash is not None else _DUMMY_HASH
    async with _hash_slots:
        result = await anyio.to_thread.run_sync(_verify_sync, target, password)
    if stored_hash is None:
        return VerifyResult(ok=False)
    return result


# ═══════════════════════════════════════════════════════════════════════
#  Chính sách (NIST SP 800-63B, spec 3.2)
# ═══════════════════════════════════════════════════════════════════════


@functools.cache
def _common_passwords() -> frozenset[str]:
    """Nạp danh sách mật khẩu phổ biến một lần (chữ thường). File thiếu thì lỗi to, không im lặng
    bỏ qua kiểm tra."""
    words: set[str] = set()
    for line in _COMMON_FILE.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#"):
            words.add(word)
    return frozenset(words)


def _is_common(password: str) -> bool:
    lowered = password.lower()
    common = _common_passwords()
    if lowered in common:
        return True
    stripped = lowered.rstrip(_TRAILING_NOISE)
    return len(stripped) >= 4 and stripped in common


def policy_violations(
    password: str,
    *,
    username: str | None = None,
    email: str | None = None,
    current_password: str | None = None,
) -> list[str]:
    """Danh sách LÝ DO mật khẩu bị từ chối (rỗng = đạt). Không bao giờ echo mật khẩu.

    Không chuẩn hoá Unicode: so đúng những gì người dùng gõ. Không bắt chữ hoa/ký tự đặc biệt.
    """
    reasons: list[str] = []
    length = len(password)
    if length < MIN_LENGTH:
        reasons.append(f"phải có ít nhất {MIN_LENGTH} ký tự")
    if length > MAX_LENGTH:
        reasons.append(f"không được dài quá {MAX_LENGTH} ký tự")
    try:
        if len(password.encode("utf-8")) > MAX_BYTES:
            reasons.append(f"không được vượt {MAX_BYTES} byte")
    except UnicodeEncodeError:
        reasons.append("chứa ký tự không hợp lệ")
    if _CONTROL_CHARS.search(password):
        reasons.append("không được chứa ký tự điều khiển")
    if length >= 1 and len(set(password)) == 1:
        reasons.append("không được chỉ gồm một ký tự lặp lại")
    if _is_common(password):
        reasons.append("nằm trong danh sách mật khẩu phổ biến")

    lowered = password.lower()
    parts = [username or "", (email or "").partition("@")[0]]
    if any(len(p) >= _MIN_IDENTITY_LEN and p.lower() in lowered for p in parts):
        reasons.append("không được chứa tên đăng nhập hoặc phần đầu của email")
    if current_password is not None and password == current_password:
        reasons.append("không được trùng mật khẩu hiện tại")
    return reasons


# ═══════════════════════════════════════════════════════════════════════
#  Mật khẩu tạm
# ═══════════════════════════════════════════════════════════════════════


def generate_temporary_password() -> str:
    """16 ký tự từ bảng chữ không gây nhầm, ~92 bit entropy, bằng `secrets` (CSPRNG)."""
    return "".join(secrets.choice(TEMP_PASSWORD_ALPHABET) for _ in range(TEMP_PASSWORD_LENGTH))


def temporary_password_expired(
    must_change_password: bool, password_changed_at: datetime | None, now: datetime
) -> bool:
    """Mật khẩu tạm quá 72 giờ mà chưa đổi thì không dùng đăng nhập được nữa (admin đặt lại).

    Thiếu mốc thời gian (không nên xảy ra) coi là hết hạn: thà từ chối còn hơn mở vĩnh viễn.
    """
    if not must_change_password:
        return False
    if password_changed_at is None:
        return True
    return now - password_changed_at > TEMP_PASSWORD_TTL
