"""Chính sách URL được phép đồng bộ (sync_urls): chỉ https và host trong allowlist.

══════════════════════════════════════════════════════════════════════
 VÌ SAO CÓ MODULE NÀY: `sync_urls` là URL do người dùng nhập mà server SẼ FETCH.
 Không giới hạn thì đó là SSRF: trỏ vào metadata cloud (169.254.169.254), dịch vụ
 nội bộ (redis, postgres trong mạng compose), hoặc `localhost`.

 Chính sách (D-B2b):
   - Chỉ scheme https.
   - Host phải thuộc allowlist: khớp CHÍNH XÁC, hoặc là tên miền con của một "đuôi"
     được phép (khớp theo ranh giới dấu chấm, nên `evilgoogleusercontent.com` và
     `docs.google.com.evil.com` đều bị từ chối).
   - Cấm user:pass@ (`https://docs.google.com@evil.com/` là mánh đánh lừa mắt người),
     cổng khác 443, IP literal, host không phải ASCII (IDN dễ giả mạo), dấu chấm
     cuối (`host.`), khoảng trắng và ký tự điều khiển.

 RỦI RO ĐÃ BIẾT (L2): `*.sharepoint.com` và `*.googleusercontent.com` nhận MỌI tenant /
 mọi tài khoản, kể cả của kẻ tấn công. Allowlist chặn SSRF vào mạng nội bộ, KHÔNG
 chứng minh nội dung file đáng tin; nội dung tải về vẫn là dữ liệu không đáng tin.
══════════════════════════════════════════════════════════════════════

Module là HÀM THUẦN (không đọc config, không I/O) để test được không cần môi trường
và để web đối chiếu cùng một bộ luật. Lưu ý: kiểm tra chuỗi URL KHÔNG đủ chặn SSRF
nếu bên fetch theo redirect; nơi fetch phải gọi lại hàm này cho URL cuối sau mỗi
lần redirect (hoặc tắt redirect), và nên chặn IP nội bộ sau khi phân giải DNS.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from urllib.parse import urlsplit

# Host KHỚP CHÍNH XÁC (không gồm tên miền con).
DEFAULT_EXACT_HOSTS: frozenset[str] = frozenset(
    {
        "docs.google.com",
        "drive.google.com",
        # Drive chuyển hướng 303 sang host này khi tải file (đã kiểm trên mạng thật).
        "drive.usercontent.google.com",
        "onedrive.live.com",
        "1drv.ms",
    }
)
# Đuôi miền: chấp nhận mọi tên miền con (>= 1 nhãn phía trước), KHÔNG chấp nhận chính
# đuôi đó. `*.googleusercontent.com` là nơi Google trả file đã export; `*.sharepoint.com`
# là tenant SharePoint của từng tổ chức.
DEFAULT_SUFFIX_HOSTS: frozenset[str] = frozenset(
    {
        "googleusercontent.com",
        "sharepoint.com",
    }
)

# Đuôi miền mà MỌI người đều đăng ký được tên miền con (hosting dùng chung, DNS ma thuật).
# Cho `*.github.io` là cho cả internet chứa file. Từ chối wildcard trên các đuôi này khi
# cấu hình SYNC_URL_EXTRA_HOSTS. Best-effort, phải giữ đồng bộ ý với bản TS của web.
PUBLIC_SHARED_SUFFIXES: frozenset[str] = frozenset(
    {
        "github.io",
        "nip.io",
        "sslip.io",
        "xip.io",
        "herokuapp.com",
        "vercel.app",
        "netlify.app",
        "pages.dev",
        "workers.dev",
        "ngrok.io",
        "ngrok-free.app",
        "blogspot.com",
        "azurewebsites.net",
        "cloudfront.net",
        "amazonaws.com",
        "appspot.com",
    }
)

MAX_URL_LEN = 2048
ALLOWED_PORT = 443

# Một nhãn DNS ASCII (không dấu gạch ở hai đầu) và host gồm >= 1 nhãn nối bằng dấu chấm.
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
# re.ASCII là BẮT BUỘC cùng IGNORECASE: không có nó, Python so khớp chữ hoa/thường theo
# Unicode nên U+212A (ký hiệu Kelvin), U+017F (long s) lọt qua lớp [a-z] và host giả mạo được
# chấp nhận (bản TS không có lỗ này).
_HOST_RE = re.compile(rf"^{_LABEL}(?:\.{_LABEL})*$", re.ASCII)
# netloc hợp lệ DUY NHẤT: host, tuỳ chọn ":443". Không cho user:pass@, [ipv6], cổng lạ,
# cổng rỗng (`host:`). Dùng regex trên netloc thay vì tin `urlsplit().hostname`, vì
# parser đó khoan dung với nhiều dạng bất thường.
_NETLOC_RE = re.compile(
    rf"^(?P<host>{_LABEL}(?:\.{_LABEL})*)(?::{ALLOWED_PORT})?$", re.IGNORECASE | re.ASCII
)
_FORBIDDEN_CHARS = re.compile(r"[\x00-\x20\x7f\\]")

# Mã lý do từ chối: ổn định để test và để UI chọn thông điệp.
REASON_TOO_LONG = "too_long"
REASON_BAD_CHARS = "bad_chars"
REASON_MALFORMED = "malformed"
REASON_NOT_HTTPS = "not_https"
REASON_BAD_NETLOC = "bad_netloc"
REASON_IP_LITERAL = "ip_literal"
REASON_HOST_NOT_ALLOWED = "host_not_allowed"


def _is_ip_literal(host: str) -> bool:
    """True nếu host là IP ở dạng chuẩn hoặc dạng số nguyên/hex mà resolver cũ vẫn hiểu.

    Allowlist đã đủ chặn IP, nhưng kiểm tường minh để báo đúng lý do, và phòng khi
    người vận hành thêm nhầm host kiểu số vào SYNC_URL_EXTRA_HOSTS.
    """
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    # `2130706433`, `0x7f000001`, `127.1`: inet_aton hiểu, ipaddress thì không.
    labels = host.split(".")
    return all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", part) for part in labels)


def is_public_suffix(host: str) -> bool:
    """True nếu `host` trông như đuôi miền dùng chung (không nên cho wildcard `*.host`).

    BEST-EFFORT, KHÔNG dùng Public Suffix List: chỉ gồm tập hằng PUBLIC_SHARED_SUFFIXES
    và heuristic đuôi hai nhãn dạng `co.uk`/`com.au` (nhãn đầu 2-3 ký tự, nhãn cuối đúng
    2 ký tự). Mục đích là chặn cấu hình nhầm tay, không phải bảo đảm tuyệt đối.
    """
    if host in PUBLIC_SHARED_SUFFIXES:
        return True
    labels = host.split(".")
    return len(labels) == 2 and 2 <= len(labels[0]) <= 3 and len(labels[1]) == 2


def parse_extra_hosts(raw: Iterable[str]) -> tuple[frozenset[str], frozenset[str]]:
    """Kiểm và tách danh sách host bổ sung (SYNC_URL_EXTRA_HOSTS) thành (exact, suffix).

    Cú pháp mỗi mục: `host` (khớp chính xác) hoặc `*.host` (mọi tên miền con).
    Từ chối thay vì lặng lẽ bỏ qua: cấu hình sai về bảo mật phải làm app không khởi
    động được, vì thiếu host chỉ gây bất tiện còn thừa host mở lỗ hổng. Chặn:
    scheme/đường dẫn/cổng, IP, `*` đứng riêng hay đuôi một nhãn (`*.com`).
    """
    exact: set[str] = set()
    suffix: set[str] = set()
    for item in raw:
        stripped = item.strip()
        # isascii TRƯỚC lower(): 'K' (Kelvin) hạ chữ thành 'k' ASCII và sẽ lọt qua kiểm tra.
        if not stripped.isascii():
            raise ValueError("SYNC_URL_EXTRA_HOSTS: chỉ chấp nhận ký tự ASCII")
        entry = stripped.lower()
        if not entry:
            continue
        wildcard = entry.startswith("*.")
        host = entry[2:] if wildcard else entry
        if not _HOST_RE.match(host) or len(host) > 253:
            raise ValueError(f"SYNC_URL_EXTRA_HOSTS: '{stripped[:80]}' không phải tên host hợp lệ")
        if _is_ip_literal(host):
            raise ValueError("SYNC_URL_EXTRA_HOSTS: không chấp nhận địa chỉ IP")
        if "." not in host:
            # Tên không có dấu chấm (localhost, api, redis, postgres) là host nội bộ, và
            # `*.com` sẽ mở cả một TLD.
            raise ValueError(
                f"SYNC_URL_EXTRA_HOSTS: '{host}' phải là tên miền đầy đủ (có dấu chấm)"
            )
        if wildcard and is_public_suffix(host):
            raise ValueError(
                f"SYNC_URL_EXTRA_HOSTS: '*.{host}' quá rộng (đuôi dùng chung của nhiều bên)"
            )
        (suffix if wildcard else exact).add(host)
    return frozenset(exact), frozenset(suffix)


def host_matches(host: str, exact: Iterable[str], suffix: Iterable[str]) -> bool:
    """Khớp host với allowlist theo ranh giới nhãn.

    `endswith("." + suffix)` (có dấu chấm) là điểm mấu chốt: `evilgoogleusercontent.com`
    không kết thúc bằng `.googleusercontent.com`, còn `docs.google.com.evil.com` không
    nằm trong exact lẫn kết thúc bằng đuôi nào.
    """
    if host in exact:
        return True
    return any(host.endswith("." + s) for s in suffix)


def check_sync_url(url: str, extra_hosts: Iterable[str] = ()) -> str | None:
    """Trả None nếu URL được phép, ngược lại trả MÃ LÝ DO từ chối (REASON_*).

    Không trả URL trong lý do: link chia sẻ Google/SharePoint thường chứa token trong
    query, không được lọt vào log hay thông điệp lỗi.

    `extra_hosts` cùng cú pháp với `parse_extra_hosts` (mục sai cú pháp ném ValueError).
    Hàm KHÔNG chuẩn hoá URL: người gọi lưu đúng chuỗi đã kiểm.
    """
    if not isinstance(url, str) or not url:
        return REASON_MALFORMED
    if len(url) > MAX_URL_LEN:
        return REASON_TOO_LONG
    if _FORBIDDEN_CHARS.search(url):
        return REASON_BAD_CHARS
    try:
        parts = urlsplit(url)
    except ValueError:
        return REASON_MALFORMED
    if parts.scheme.lower() != "https":
        return REASON_NOT_HTTPS
    # Bắt buộc dạng `https://host...`: `https:host`, `https:///x`, `https:/x` có netloc rỗng.
    if url[:8].lower() != "https://":
        return REASON_MALFORMED
    match = _NETLOC_RE.fullmatch(parts.netloc)
    if match is None:
        # userinfo, cổng lạ, host không ASCII, dấu chấm cuối...: gộp một mã. Riêng IP
        # (ipv6 trong ngoặc, hoặc IPv4 kèm cổng lạ) báo mã riêng cho dễ chẩn đoán.
        if "@" not in parts.netloc:
            candidate = parts.netloc.strip("[]").rsplit(":", 1)[0].strip("[]")
            if parts.netloc.startswith("[") or _is_ip_literal(candidate):
                return REASON_IP_LITERAL
        return REASON_BAD_NETLOC
    host = match.group("host").lower()
    if _is_ip_literal(host):
        return REASON_IP_LITERAL
    extra_exact, extra_suffix = parse_extra_hosts(extra_hosts)
    if host_matches(host, DEFAULT_EXACT_HOSTS | extra_exact, DEFAULT_SUFFIX_HOSTS | extra_suffix):
        return None
    return REASON_HOST_NOT_ALLOWED


def is_allowed_sync_url(url: str, extra_hosts: Iterable[str] = ()) -> bool:
    """Bản bool của `check_sync_url`, cho nơi chỉ cần có/không."""
    return check_sync_url(url, extra_hosts) is None
