"""Bộ lọc secret cho hook ghi vết (trace-hook.py).

Mọi dữ liệu PHẢI đi qua đây TRƯỚC khi chạm đĩa. Transcript Claude Code chứa
nguyên văn mọi thứ agent đã đọc: file .env, token Jira, header Authorization,
email của User, dữ liệu Jira công ty. Lọc ở lúc ghi (không lọc lúc đọc) vì
file đã ghi xuống đĩa thì coi như đã lộ.

Nguyên tắc: thà che thừa còn hơn lọt. Chỉ ghi TÊN mẫu đã che
(`[REDACTED:bearer]`), không bao giờ ghi lại giá trị.

Chỉ dùng thư viện chuẩn; không gọi mạng.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

# ═════════════════════════════════════════════════════════════════════════
#  Mẫu nhận dạng
# ═════════════════════════════════════════════════════════════════════════

# Tên khoá nhạy cảm. Dùng cho cả dạng KEY=value lẫn khoá JSON.
_SENSITIVE_NAME = (
    r"api[_-]?key|import_commit_secret|integration_secret_key|postgres_password"
    r"|secret|passw(?:or)?d|passwd|credential|token|authorization|private[_-]?key"
    r"|passphrase|pwd|cookie|access[_-]?key|vault[_-]?key"
    r"|(?<![a-z])pass(?![a-z])|(?<![a-z])pw(?![a-z])"
)

# Khoá JSON là SỐ ĐẾM token (usage.input_tokens...) chứ không phải secret.
# Giữ lại vì đó là dữ liệu chi phí hữu ích khi phân tích.
_TOKEN_COUNT_KEY = re.compile(
    r"(?i)(?:^|_)(?:input|output|total|max|cache\w*|prompt|completion|thinking)_tokens$"
)
_SENSITIVE_KEY = re.compile(rf"(?i)(?:{_SENSITIVE_NAME})")

# Mẫu có hình dạng đặc trưng, không cần ngữ cảnh. Thứ tự quan trọng:
# cụ thể trước, chung sau.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Header Authorization nuốt cả scheme lẫn token (Bearer/Basic/Token/Digest).
    (
        "authorization",
        re.compile(
            r"(?i)\bauthorization\b[\"']?\s*[:=]\s*[\"']?"
            r"(?:(?:bearer|basic|token|digest)\s+)?[^\s\"',;]+"
        ),
    ),
    ("bearer", re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")),
    # API token Atlassian/Jira có tiền tố ATATT.
    ("atlassian-token", re.compile(r"\bATATT[A-Za-z0-9_=\-]{20,}")),
    ("provider-key", re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"
        r"|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})"
    )),
    ("private-key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S
    )),
    # Che CẢ userinfo của URL: mẫu "user:pw" hẹp để lọt user rỗng (redis://:pw@h)
    # và mật khẩu chứa "/" hoặc "@".
    ("url-userinfo", re.compile(r"(?<=://)[^\s/]*(?=@)")),
    # Khoá Fernet (INTEGRATION_SECRET_KEY của repo này): 43 ký tự base64url + "=".
    ("fernet-key", re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}=(?![A-Za-z0-9=])")),
    ("provider-key", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("slack-webhook", re.compile(r"hooks\.slack\.com/services/\S+")),
    # Tham số dòng lệnh: --password X, --token=X, curl -u user:pw, mysql -pMẬT_KHẨU.
    ("cli-secret", re.compile(
        r"(?i)(?<![\w-])--?(?:password|passwd|pass|pwd|token|secret|api[-_]?key"
        r"|client[-_]?secret|passphrase)[ =]\S+"
    )),
    ("cli-basic-auth", re.compile(r"(?<=\s)-u\s+\S+:\S+")),
    ("cli-mysql-password", re.compile(r"(?<=\s)-p(?!\d+\b)\S{4,}")),
    # Tiếng Việt: "mật khẩu là X".
    ("vi-password", re.compile(r"(?i)(?:mật khẩu|mat khau|mật mã)\s*(?:là|:|=)?\s*\S+")),
]

# Dãy không khoảng trắng quá dài là blob (base64, ảnh, minified): bỏ đi, đồng thời
# chặn regex chạy bậc hai (đã đo: 20k ký tự mất 0.5 s, 200k ước 55 s).
_LONG_RUN = re.compile(r"\S{4096,}")

# KEY=value | KEY: value | "key": "value". Giá trị có nháy lấy đến nháy đóng
# (cho phép khoảng trắng), không nháy thì lấy đến khoảng trắng/dấu phân cách.
_KV = re.compile(
    rf"""(?ix)
    (?<![A-Za-z0-9_.-])  # chỉ bắt đầu ở biên từ: tránh bậc hai trên chuỗi dài không dấu cách
    (?P<key>\\?[\"']?[A-Za-z0-9_.-]*(?:{_SENSITIVE_NAME})[A-Za-z0-9_.-]*\\?[\"']?)
    (?P<sep>\s*[:=]\s*)
    (?:
        \\"(?P<edq>[^"\\\n]*)\\"
      | "(?P<dq>(?:[^"\\\n]|\\.)*)"
      | '(?P<sq>(?:[^'\\\n]|\\.)*)'
      | (?P<bare>[^\s"',;]+)
    )
    """
)

# Chuỗi dài giống token đứng ngay sau từ khoá nhạy cảm ("token là abc123...").
_NEAR_KEYWORD = re.compile(
    r"(?i)(?P<k>(?:token|key|secret|passw\w*|bearer|auth\w*|credential\w*)[^\n]{0,40}?)"
    r"(?P<v>[A-Za-z0-9+/_=\-]{32,})"
)

_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# Giá trị KHÔNG phải secret: đã che rồi, tham chiếu biến, placeholder.
# Khớp TOÀN BỘ giá trị: tiền tố "$"/"<" đơn thuần từng làm lọt `PASSWORD=$ecretFake`.
# Biến shell chỉ coi là tham chiếu khi viết HOA (`$TOKEN`, `${DB_PASS}`).
_BENIGN_VALUE = re.compile(
    r"^(?:\[REDACTED[^\]]*\]|\$\{?[A-Z_][A-Z0-9_]*\}?|<[\w -]+>|\{\{.*\}\}|%s|%\(\w+\)s"
    r"|\*+|(?i:null|none|true|false))$"
)

# Biến môi trường/file .env: tên chứa từ nhạy cảm thì giá trị là secret.
_ENV_NAME_SENSITIVE = re.compile(rf"(?i)(?:{_SENSITIVE_NAME})")
_MIN_LITERAL_LEN = 6  # ngắn hơn thì dễ che nhầm chữ thường ("true", "dev").


# ═════════════════════════════════════════════════════════════════════════
#  Giá trị thật từ .env / môi trường
# ═════════════════════════════════════════════════════════════════════════

_literal_cache: list[str] | None = None


def _parse_env_file(path: Path) -> list[str]:
    """Đọc giá trị trong file .env KHÔNG kèm tên. Chỉ giữ trong RAM của hook.

    Mọi giá trị trong .env đều bị coi là nhạy cảm (không chỉ khoá có chữ
    SECRET): DATABASE_URL, JIRA_BASE_URL... đều là thông tin hạ tầng.
    """
    values: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        _, _, val = line.partition("=")
        val = val.strip()
        if val[:1] not in "'\"":
            val = re.split(r"\s+#", val, maxsplit=1)[0]  # bỏ comment cuối dòng của giá trị không nháy
        val = val.strip().strip("'\"")
        if len(val) >= _MIN_LITERAL_LEN:
            values.append(val)
    return values


def literal_secrets() -> list[str]:
    """Danh sách giá trị secret thật, dài trước để thay không bị cắt dở."""
    global _literal_cache
    if _literal_cache is not None:
        return _literal_cache
    found: set[str] = set()
    candidates = [Path.home() / ".env"]
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        root = Path(proj)
        # .env gốc và mọi .env* trong apps/* (vd apps/web/.env.local), trừ file mẫu.
        for pat in (".env", ".env.*", "apps/*/.env", "apps/*/.env.*"):
            candidates.extend(
                p for p in root.glob(pat) if p.suffix not in (".example", ".sample") and p.is_file()
            )
    for p in candidates:
        found.update(_parse_env_file(p))
    for name, val in os.environ.items():
        if _ENV_NAME_SENSITIVE.search(name) and len(val) >= _MIN_LITERAL_LEN:
            found.add(val)
    # Đường dẫn không phải secret; che chúng làm mất cwd/transcript_path và mọi chỗ nhắc file
    # (đã gặp thật: cwd của repo bị che vì một biến trong .env chứa đúng đường dẫn đó).
    found = {v for v in found if not v.startswith(("/", "~", "./", "../"))}
    _literal_cache = sorted(found, key=len, reverse=True)
    return _literal_cache


def reset_cache() -> None:
    """Dành cho test: nạp lại .env/môi trường."""
    global _literal_cache
    _literal_cache = None


# ═════════════════════════════════════════════════════════════════════════
#  API
# ═════════════════════════════════════════════════════════════════════════


def redact_text(text: str, counts: Counter[str] | None = None) -> str:
    """Che secret trong một chuỗi. `counts` (nếu có) cộng dồn số lần che theo mẫu."""

    def hit(kind: str) -> str:
        if counts is not None:
            counts[kind] += 1
        return f"[REDACTED:{kind}]"

    text = _LONG_RUN.sub(lambda m: f"[OMITTED:blob {len(m.group(0))}]", text)

    for lit in literal_secrets():
        if lit in text:
            text = text.replace(lit, hit("env-value"))

    for kind, pat in _PATTERNS:
        text = pat.sub(lambda _m, k=kind: hit(k), text)

    def kv(m: re.Match[str]) -> str:
        # Giá trị có nháy thường, nháy escape (JSON lồng trong chuỗi lệnh) hoặc không nháy.
        quote = ""
        val = m.group("bare")
        for grp, q in (("edq", '\\"'), ("dq", '"'), ("sq", "'")):
            if m.group(grp) is not None:
                val, quote = m.group(grp), q
                break
        if not val or _BENIGN_VALUE.match(val):
            return m.group(0)
        key = m.group("key").strip("\\\"'")
        if _TOKEN_COUNT_KEY.search(key):
            return m.group(0)
        return f"{m.group('key')}{m.group('sep')}{quote}{hit('secret-value')}{quote}"

    text = _KV.sub(kv, text)

    def near(m: re.Match[str]) -> str:
        v = m.group("v")
        # Phải có cả chữ và số, và không giống đường dẫn: tránh che nhầm path dài.
        if not (re.search(r"\d", v) and re.search(r"[A-Za-z]", v)) or v.count("/") >= 2:
            return m.group(0)
        return m.group("k") + hit("long-token")

    text = _NEAR_KEYWORD.sub(near, text)
    text = _EMAIL.sub(lambda _m: hit("email"), text)
    return text


def redact_obj(obj: Any, counts: Counter[str] | None = None) -> Any:
    """Che đệ quy trong cấu trúc JSON đã parse.

    Lọc trên cấu trúc (không trên chuỗi JSON thô) vì trong transcript, JSON
    lồng nhau bị escape (`\\"API_KEY\\": \\"x\\"`) làm regex KEY=value trượt.
    """
    if isinstance(obj, str):
        return redact_text(obj, counts)
    if isinstance(obj, list):
        return [redact_obj(v, counts) for v in obj]
    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        for k, v in obj.items():
            # Khoá nhạy cảm che MỌI kiểu giá trị có nội dung (chuỗi, list, dict lồng như
            # {"credentials": {...}}), chỉ chừa số/bool và số đếm token.
            if (
                isinstance(k, str)
                and _SENSITIVE_KEY.search(k)
                and not _TOKEN_COUNT_KEY.search(k)
                and (
                    (isinstance(v, str) and v and not _BENIGN_VALUE.match(v))
                    or (isinstance(v, (list, dict)) and v)
                )
            ):
                if counts is not None:
                    counts["json-key"] += 1
                out[k] = "[REDACTED:json-key]"
            else:
                out[k] = redact_obj(v, counts)
        return out
    return obj
