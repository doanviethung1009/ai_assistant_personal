"""Chính sách URL của sync_urls (chống SSRF): hàm thuần, không cần DB.

Trọng tâm là các trường hợp ĐỐI KHÁNG: mánh khiến người đọc thấy "docs.google.com"
nhưng bộ phân giải đi chỗ khác.
"""

# Cố ý có ký tự Unicode dễ nhầm (Cyrillic, toàn chiều rộng) trong URL thử: đó chính là
# mánh giả mạo host cần kiểm chứng bị từ chối.
# ruff: noqa: RUF001, RUF003
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core import url_allowlist as ua
from app.core.config import Settings

OK_URLS = [
    "https://docs.google.com/spreadsheets/d/abc/export?format=xlsx",
    "https://DOCS.Google.COM/spreadsheets/d/abc",
    "HTTPS://docs.google.com/x",
    "https://docs.google.com:443/x",
    "https://docs.google.com",
    "https://docs.google.com?x=1",
    "https://docs.google.com#frag",
    "https://drive.google.com/uc?id=1&export=download",
    "https://doc-0c-ak-sheets.googleusercontent.com/export/abc",
    "https://a.b.googleusercontent.com/x",
    "https://contoso.sharepoint.com/sites/x/file.xlsx",
    "https://contoso-my.sharepoint.com/:x:/g/personal/u/abc",
    "https://onedrive.live.com/download?cid=1",
    "https://1drv.ms/x/s!abc",
]


@pytest.mark.parametrize("url", OK_URLS)
def test_allows_default_hosts(url: str) -> None:
    assert ua.check_sync_url(url) is None
    assert ua.is_allowed_sync_url(url)


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        # Scheme
        ("http://docs.google.com/x", ua.REASON_NOT_HTTPS),
        ("ftp://docs.google.com/x", ua.REASON_NOT_HTTPS),
        ("file:///etc/passwd", ua.REASON_NOT_HTTPS),
        ("javascript:alert(1)", ua.REASON_NOT_HTTPS),
        ("gopher://docs.google.com", ua.REASON_NOT_HTTPS),
        ("//docs.google.com/x", ua.REASON_NOT_HTTPS),
        ("docs.google.com/x", ua.REASON_NOT_HTTPS),
        # Dạng https nhưng không có `//` / netloc rỗng
        ("https:docs.google.com", ua.REASON_MALFORMED),
        ("https:/docs.google.com", ua.REASON_MALFORMED),
        ("https:///docs.google.com", ua.REASON_BAD_NETLOC),
        # Host gần giống (không khớp theo ranh giới dấu chấm)
        ("https://evilgoogleusercontent.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://evil-docs.google.com.evil.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://docs.google.com.evil.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://docs.google.com.attacker.example/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://xdocs.google.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://google.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://www.google.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://sharepoint.com/x", ua.REASON_HOST_NOT_ALLOWED),  # đuôi không gồm apex
        ("https://googleusercontent.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://evilsharepoint.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://sharepoint.com.evil.com/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://x.1drv.ms/x", ua.REASON_HOST_NOT_ALLOWED),  # 1drv.ms chỉ exact
        ("https://sub.docs.google.com/x", ua.REASON_HOST_NOT_ALLOWED),  # docs.google.com chỉ exact
        ("https://a.onedrive.live.com/x", ua.REASON_HOST_NOT_ALLOWED),
        # userinfo: mánh `docs.google.com@evil.com`
        ("https://docs.google.com@evil.com/x", ua.REASON_BAD_NETLOC),
        ("https://user:pass@docs.google.com/x", ua.REASON_BAD_NETLOC),
        ("https://user@docs.google.com/x", ua.REASON_BAD_NETLOC),
        ("https://:@docs.google.com/x", ua.REASON_BAD_NETLOC),
        ("https://evil.com#@docs.google.com/", ua.REASON_HOST_NOT_ALLOWED),
        ("https://evil.com?@docs.google.com/", ua.REASON_HOST_NOT_ALLOWED),
        ("https://evil.com/@docs.google.com/", ua.REASON_HOST_NOT_ALLOWED),
        # Cổng
        ("https://docs.google.com:8443/x", ua.REASON_BAD_NETLOC),
        ("https://docs.google.com:80/x", ua.REASON_BAD_NETLOC),
        ("https://docs.google.com:0443/x", ua.REASON_BAD_NETLOC),
        ("https://docs.google.com:/x", ua.REASON_BAD_NETLOC),
        ("https://docs.google.com:abc/x", ua.REASON_BAD_NETLOC),
        ("https://docs.google.com:65536/x", ua.REASON_BAD_NETLOC),
        # IP literal
        ("https://127.0.0.1/x", ua.REASON_IP_LITERAL),
        ("https://127.0.0.1:443/x", ua.REASON_IP_LITERAL),
        ("https://169.254.169.254/latest/meta-data", ua.REASON_IP_LITERAL),
        ("https://10.0.0.5:8080/x", ua.REASON_IP_LITERAL),
        ("https://[::1]/x", ua.REASON_IP_LITERAL),
        ("https://[::ffff:127.0.0.1]/x", ua.REASON_IP_LITERAL),
        ("https://[2001:db8::1]:443/x", ua.REASON_IP_LITERAL),
        ("https://2130706433/x", ua.REASON_IP_LITERAL),  # 127.0.0.1 dạng số nguyên
        ("https://0x7f000001/x", ua.REASON_IP_LITERAL),
        ("https://0177.0.0.1/x", ua.REASON_IP_LITERAL),
        ("https://127.1/x", ua.REASON_IP_LITERAL),
        # Tên nội bộ
        ("https://localhost/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://redis/x", ua.REASON_HOST_NOT_ALLOWED),
        ("https://core:8000/x", ua.REASON_BAD_NETLOC),
        # Dấu chấm cuối, nhãn rỗng, ký tự lạ
        ("https://docs.google.com./x", ua.REASON_BAD_NETLOC),
        ("https://docs..google.com/x", ua.REASON_BAD_NETLOC),
        ("https://.docs.google.com/x", ua.REASON_BAD_NETLOC),
        ("https://-docs.google.com/x", ua.REASON_BAD_NETLOC),
        ("https://docs_google.com/x", ua.REASON_BAD_NETLOC),
        ("https://docs.google.com%2f@evil.com/x", ua.REASON_BAD_NETLOC),
        ("https://docs.google.com%00.evil.com/x", ua.REASON_BAD_NETLOC),
        # Unicode / IDN giả mạo, viết bằng escape để người đọc thấy rõ ký tự lạ:
        # о = chữ Cyrillic trông như 'o'; ／ = dấu "/" toàn chiều rộng
        # (NFKC thành "/", urlsplit ném ValueError nên là "malformed"); ｄ = 'd' toàn chiều rộng.
        ("https://docs.gооgle.com/x", ua.REASON_BAD_NETLOC),
        ("https://docs.google.com／evil.com/x", ua.REASON_MALFORMED),
        ("https://ｄocs.google.com/x", ua.REASON_BAD_NETLOC),
        # Ký tự điều khiển, khoảng trắng, backslash
        ("https://docs.google.com/x y", ua.REASON_BAD_CHARS),
        (" https://docs.google.com/x", ua.REASON_BAD_CHARS),
        ("https://docs.google.com/x\n", ua.REASON_BAD_CHARS),
        ("https://docs.google.com/\r\nHost: evil.com", ua.REASON_BAD_CHARS),
        ("https://docs.google.com\t.evil.com/x", ua.REASON_BAD_CHARS),
        ("https://docs.google.com\\@evil.com/x", ua.REASON_BAD_CHARS),
        ("https://evil.com\\.docs.google.com/x", ua.REASON_BAD_CHARS),
        ("https://docs.google.com\x00.evil.com", ua.REASON_BAD_CHARS),
        # Rỗng / quá dài
        ("", ua.REASON_MALFORMED),
        ("https://docs.google.com/" + "a" * ua.MAX_URL_LEN, ua.REASON_TOO_LONG),
    ],
)
def test_rejects_adversarial_urls(url: str, reason: str) -> None:
    assert ua.check_sync_url(url) == reason
    assert not ua.is_allowed_sync_url(url)


def test_rejects_non_string() -> None:
    assert ua.check_sync_url(None) == ua.REASON_MALFORMED  # type: ignore[arg-type]
    assert ua.check_sync_url(123) == ua.REASON_MALFORMED  # type: ignore[arg-type]


def test_url_at_exact_length_limit_is_accepted() -> None:
    prefix = "https://docs.google.com/"
    assert ua.check_sync_url(prefix + "a" * (ua.MAX_URL_LEN - len(prefix))) is None


# ── Host bổ sung (SYNC_URL_EXTRA_HOSTS) ─────────────────────────────


def test_extra_exact_and_wildcard_hosts() -> None:
    extra = ["files.example.org", "*.cdn.example.net"]
    assert ua.check_sync_url("https://files.example.org/a.xlsx", extra) is None
    assert ua.check_sync_url("https://x.cdn.example.net/a", extra) is None
    assert ua.check_sync_url("https://a.b.cdn.example.net/a", extra) is None
    # exact không kéo theo tên miền con; wildcard không gồm apex
    assert ua.check_sync_url("https://x.files.example.org/a", extra) == ua.REASON_HOST_NOT_ALLOWED
    assert ua.check_sync_url("https://cdn.example.net/a", extra) == ua.REASON_HOST_NOT_ALLOWED
    # ranh giới dấu chấm vẫn áp dụng cho host thêm
    assert ua.check_sync_url("https://evilcdn.example.net/a", extra) == ua.REASON_HOST_NOT_ALLOWED
    assert (
        ua.check_sync_url("https://files.example.org.evil.com/a", extra)
        == ua.REASON_HOST_NOT_ALLOWED
    )
    # không có extra thì không mở
    assert ua.check_sync_url("https://files.example.org/a") == ua.REASON_HOST_NOT_ALLOWED


def test_extra_hosts_do_not_relax_other_rules() -> None:
    extra = ["files.example.org"]
    assert ua.check_sync_url("http://files.example.org/a", extra) == ua.REASON_NOT_HTTPS
    assert ua.check_sync_url("https://files.example.org:8443/a", extra) == ua.REASON_BAD_NETLOC
    assert ua.check_sync_url("https://u@files.example.org/a", extra) == ua.REASON_BAD_NETLOC


@pytest.mark.parametrize(
    "bad",
    [
        "https://files.example.org",  # scheme
        "files.example.org/path",
        "files.example.org:443",
        "10.0.0.1",
        "*.10.0.1",
        "127.0.0.1",
        "2130706433",
        "*.com",
        "*",
        "*.",
        "a b.com",
        "ex@mple.com",
        "ví-dụ.com",
        "-bad.com",
        "bad..com",
    ],
)
def test_parse_extra_hosts_rejects_bad_entries(bad: str) -> None:
    with pytest.raises(ValueError, match="SYNC_URL_EXTRA_HOSTS"):
        ua.parse_extra_hosts([bad])


def test_parse_extra_hosts_normalizes_and_skips_blank() -> None:
    exact, suffix = ua.parse_extra_hosts([" Files.Example.ORG ", "", "*.Cdn.Example.net"])
    assert exact == frozenset({"files.example.org"})
    assert suffix == frozenset({"cdn.example.net"})


def test_default_lists_are_the_documented_ones() -> None:
    exact = {
        "docs.google.com",
        "drive.google.com",
        "drive.usercontent.google.com",
        "onedrive.live.com",
        "1drv.ms",
    }
    assert set(ua.DEFAULT_EXACT_HOSTS) == exact
    assert set(ua.DEFAULT_SUFFIX_HOSTS) == {"googleusercontent.com", "sharepoint.com"}


def test_host_matches_requires_dot_boundary() -> None:
    assert ua.host_matches("a.sharepoint.com", [], ["sharepoint.com"])
    assert not ua.host_matches("asharepoint.com", [], ["sharepoint.com"])
    assert not ua.host_matches("sharepoint.com", [], ["sharepoint.com"])


# ── Cấu hình môi trường ─────────────────────────────────────────────

_BASE = {"database_url": "postgresql+asyncpg://u@h/d", "api_key": "k" * 16}


def test_settings_parses_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNC_URL_EXTRA_HOSTS", " Files.Example.org , *.cdn.example.net ,")
    cfg = Settings(**_BASE)  # type: ignore[arg-type]
    assert cfg.sync_url_extra_hosts == ["files.example.org", "*.cdn.example.net"]


def test_settings_blank_env_means_no_extra_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNC_URL_EXTRA_HOSTS", "")
    assert Settings(**_BASE).sync_url_extra_hosts == []  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["*.com", "10.0.0.1", "https://evil.com", "a b"])
def test_settings_refuses_to_start_with_bad_extra_host(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("SYNC_URL_EXTRA_HOSTS", f"ok.example.org,{bad}")
    with pytest.raises(ValidationError):
        Settings(**_BASE)  # type: ignore[arg-type]


# ── Vòng sửa sau review ─────────────────────────────────────────────


def test_drive_usercontent_host_is_exact_only() -> None:
    assert ua.check_sync_url("https://drive.usercontent.google.com/download?id=1") is None
    # Chỉ host chính xác: không tên miền con, không host cha.
    assert (
        ua.check_sync_url("https://x.drive.usercontent.google.com/d") == ua.REASON_HOST_NOT_ALLOWED
    )
    assert ua.check_sync_url("https://usercontent.google.com/d") == ua.REASON_HOST_NOT_ALLOWED
    assert ua.check_sync_url("https://drive.usercontent.google.com.evil.com/d") == (
        ua.REASON_HOST_NOT_ALLOWED
    )
    # Chưa kiểm được trên mạng thật nên chưa thêm.
    for host in ("api.onedrive.com", "x.files.1drv.com"):
        assert ua.check_sync_url(f"https://{host}/x") == ua.REASON_HOST_NOT_ALLOWED


@pytest.mark.parametrize(
    "url",
    [
        "https://K.example.org/x",  # Kelvin: .lower() thành 'k' ASCII
        "https://ſub.example.org/x",  # ſ (long s) khớp 's' khi IGNORECASE kiểu Unicode
        "https://İ.example.org/x",  # İ (I chấm)
        "https://ı.example.org/x",  # ı (i không chấm)
    ],
)
def test_unicode_case_folding_lookalikes_are_rejected(url: str) -> None:
    # Có host ASCII tương ứng trong allowlist thêm: bản Python cũ (re.IGNORECASE kiểu
    # Unicode) từng nhận Kelvin vì lower() đưa nó về 'k'.
    extra = ["k.example.org", "sub.example.org", "i.example.org"]
    assert ua.check_sync_url(url, extra) == ua.REASON_BAD_NETLOC


def test_ascii_counterparts_still_pass_with_extra() -> None:
    assert ua.check_sync_url("https://k.example.org/x", ["k.example.org"]) is None


@pytest.mark.parametrize(
    "bad",
    [chr(0x212A) + ".example.org", "*." + chr(0x17F) + "ub.example.org", chr(0x130) + ".x.org"],
)
def test_parse_extra_hosts_rejects_non_ascii_even_if_it_lowercases_to_ascii(bad: str) -> None:
    with pytest.raises(ValueError, match="ASCII"):
        ua.parse_extra_hosts([bad])


@pytest.mark.parametrize("bad", ["localhost", "api", "redis", "postgres", "core", "*.localhost"])
def test_parse_extra_hosts_rejects_dotless_hosts(bad: str) -> None:
    with pytest.raises(ValueError, match=r"dấu chấm|quá rộng"):
        ua.parse_extra_hosts([bad])


@pytest.mark.parametrize("suffix", sorted(ua.PUBLIC_SHARED_SUFFIXES))
def test_parse_extra_hosts_rejects_wildcard_on_shared_suffixes(suffix: str) -> None:
    with pytest.raises(ValueError, match="quá rộng"):
        ua.parse_extra_hosts([f"*.{suffix}"])
    # Host chính xác trong đuôi đó (một tenant cụ thể) vẫn cho phép.
    exact, _ = ua.parse_extra_hosts([f"mine.{suffix}"])
    assert exact == frozenset({f"mine.{suffix}"})


@pytest.mark.parametrize("suffix", ["co.uk", "com.au", "org.uk", "ac.jp", "gov.vn", "xx.cn"])
def test_parse_extra_hosts_rejects_two_label_country_suffix_heuristic(suffix: str) -> None:
    with pytest.raises(ValueError, match="quá rộng"):
        ua.parse_extra_hosts([f"*.{suffix}"])


def test_parse_extra_hosts_allows_ordinary_wildcards() -> None:
    _, suffix = ua.parse_extra_hosts(["*.example.co.uk", "*.cdn.example.net", "*.corp.example.org"])
    assert suffix == frozenset({"example.co.uk", "cdn.example.net", "corp.example.org"})
    assert ua.is_public_suffix("co.uk") and not ua.is_public_suffix("example.org")


def test_public_shared_suffix_set_is_the_documented_one() -> None:
    assert set(ua.PUBLIC_SHARED_SUFFIXES) == {
        "github.io", "nip.io", "sslip.io", "xip.io", "herokuapp.com", "vercel.app",
        "netlify.app", "pages.dev", "workers.dev", "ngrok.io", "ngrok-free.app",
        "blogspot.com", "azurewebsites.net", "cloudfront.net", "amazonaws.com", "appspot.com",
    }  # fmt: skip


@pytest.mark.parametrize(
    "bad", ["localhost", "*.github.io", "*.co.uk", chr(0x212A) + ".example.org"]
)
def test_settings_refuses_dotless_and_shared_suffix_hosts(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("SYNC_URL_EXTRA_HOSTS", bad)
    with pytest.raises(ValidationError):
        Settings(**_BASE)  # type: ignore[arg-type]
