"""Mã hoá token của integration (Jira...) khi lưu ở Postgres.

══════════════════════════════════════════════════════════════════════
 CẢNH BÁO: file này chạm secret. Quy tắc cứng:
 - KHÔNG log token, khoá, hay ciphertext; KHÔNG đưa chúng vào message của exception
   (message đi thẳng ra response qua DomainError).
 - `raise ... from None` khi bắt lỗi của thư viện, để traceback không kéo theo giá trị.
 - Token phải GIẢI MÃ được ở server (để gọi Jira), nên đây KHÔNG phải zero-knowledge như
   Vault. Ai có cả DB lẫn INTEGRATION_SECRET_KEY thì đọc được token.
══════════════════════════════════════════════════════════════════════

Thiếu khoá hoặc khoá sai định dạng không làm app sập lúc khởi động: các hàm ở đây
ném `SecretsUnavailableError` (503) để chỉ endpoint cần secret mới báo lỗi.
"""

from __future__ import annotations

import hmac
import json
import uuid

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings
from app.services.errors import DomainError

_PAYLOAD_VERSION = 1


class SecretsUnavailableError(DomainError):
    """Không mã hoá/giải mã được: thiếu khoá, khoá sai định dạng, hoặc đổi khoá."""

    status_code = 503


def _fernet() -> MultiFernet:
    """Khoá chính (mã hoá + giải mã) cộng các khoá cũ (chỉ giải mã) để xoay khoá.

    Đọc khoá lúc gọi (không cache ở import) để đổi env + restart là đủ, và test chỉnh được.
    """
    key = settings.integration_secret_key.get_secret_value().strip()
    if not key:
        raise SecretsUnavailableError(
            "Chưa cấu hình INTEGRATION_SECRET_KEY nên không thể lưu token. "
            "Sinh khoá bằng: python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())', đặt vào biến môi trường rồi khởi động "
            "lại core."
        )
    old = settings.integration_secret_key_old.get_secret_value()
    raw_keys = [key, *(part.strip() for part in old.split(",") if part.strip())]
    try:
        # MultiFernet mã hoá bằng khoá ĐẦU TIÊN, giải mã thử lần lượt.
        return MultiFernet([Fernet(k.encode("ascii")) for k in raw_keys])
    except (ValueError, UnicodeEncodeError):
        # Không kèm giá trị khoá hay message gốc của thư viện.
        raise SecretsUnavailableError(
            "INTEGRATION_SECRET_KEY (hoặc INTEGRATION_SECRET_KEY_OLD) sai định dạng "
            "(cần chuỗi Fernet 44 ký tự base64 url-safe). Sinh lại khoá rồi khởi động lại core."
        ) from None


def encrypt_token(token: str, *, connection_id: uuid.UUID, base_url: str) -> bytes:
    """Mã hoá token, GẮN với kết nối (id + base_url) ngay trong plaintext.

    WHY: Fernet không có AAD. Nếu ciphertext chỉ chứa token thì ai ghi được vào DB (hoặc
    PATCH) có thể chép ciphertext sang kết nối trỏ host của mình, B4b sẽ giải mã và gửi
    token Jira tới đó. Gắn id + host vào payload, kiểm lại khi giải mã, chặn việc chép.
    """
    payload = json.dumps(
        {"v": _PAYLOAD_VERSION, "id": str(connection_id), "base_url": base_url, "token": token},
        separators=(",", ":"),
    )
    return _fernet().encrypt(payload.encode("utf-8"))


def decrypt_token(ciphertext: bytes, *, connection_id: uuid.UUID, base_url: str) -> str:
    """Giải mã token của ĐÚNG kết nối này. Dành cho B4b; KHÔNG BAO GIỜ trả ra response/log.

    Raises:
        SecretsUnavailableError: khoá đã đổi/hỏng, hoặc ciphertext thuộc kết nối khác.
    """
    unusable = SecretsUnavailableError(
        "Không giải mã được token đã lưu (khoá INTEGRATION_SECRET_KEY đã đổi hoặc token "
        "không thuộc kết nối này). Hãy nhập lại token cho kết nối này."
    )
    try:
        data = json.loads(_fernet().decrypt(bytes(ciphertext)).decode("utf-8"))
        token = data["token"]
        bound_id, bound_url = data["id"], data["base_url"]
        if not all(isinstance(v, str) for v in (token, bound_id, bound_url)):
            raise unusable from None
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise unusable from None
    same = hmac.compare_digest(bound_id.encode(), str(connection_id).encode()) and (
        hmac.compare_digest(bound_url.encode(), base_url.encode())
    )
    if not same:
        raise unusable from None
    return token


def rotate_ciphertext(ciphertext: bytes) -> bytes:
    """Mã hoá lại ciphertext (khoá cũ) bằng khoá chính, giữ nguyên ràng buộc kết nối."""
    try:
        return _fernet().rotate(bytes(ciphertext))
    except InvalidToken:
        raise SecretsUnavailableError("Không giải mã được token để xoay khoá.") from None


def last4(token: str) -> str:
    """4 ký tự cuối để UI nhận ra token nào đang lưu. Schema đảm bảo token dài >= 8."""
    return token[-4:]
