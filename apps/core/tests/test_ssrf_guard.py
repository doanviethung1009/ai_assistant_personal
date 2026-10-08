"""Chốt SSRF của connector (B4b): phân loại IP, ghim IP, chống DNS rebinding.

Không mạng thật: resolver giả và backend mạng giả của httpcore.
"""

# ruff: noqa: ASYNC109 - chữ ký connect_tcp của httpcore bắt buộc có tham số `timeout`
from __future__ import annotations

from collections.abc import Sequence

import httpcore
import httpx
import pytest

from app.core.config import settings
from app.services.ssrf_guard import (
    HostBlockedError,
    HostUnresolvableError,
    NetworkUnavailableError,
    PinnedTransport,
    _FixedIPBackend,
    check_host,
    classify_ip,
)

PUBLIC = "104.192.140.1"


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.255.255.254",
        "::1",
        "169.254.169.254",  # metadata cloud
        "169.254.0.1",
        "fe80::1",
        "fe80::a00:27ff:fe4e:66a1%eth0",
        "224.0.0.1",
        "239.255.255.250",
        "ff02::1",
        "0.0.0.0",  # noqa: S104
        "0.1.2.3",
        "::",
        "240.0.0.1",
        "255.255.255.255",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "::ffff:10.0.0.1",
        "::127.0.0.1",
        "64:ff9b::7f00:1",  # NAT64 của 127.0.0.1
        "64:ff9b::a9fe:a9fe",  # NAT64 của 169.254.169.254
        "10.1.2.3",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "100.64.0.1",
        "100.127.255.254",
        "fc00::1",
        "fd12:3456::1",
        "192.0.2.1",  # TEST-NET
        "198.18.0.1",  # benchmark
        "2002:7f00:1::1",  # 6to4 của 127.0.0.1
        "not-an-ip",
        "",
    ],
)
def test_blocked_by_default(address: str) -> None:
    assert classify_ip(address) is not None


@pytest.mark.parametrize(
    "address",
    [
        "104.192.140.1",
        "8.8.8.8",
        "172.32.0.1",
        "100.128.0.1",
        "2606:4700:4700::1111",
        "64:ff9b::808:808",
    ],
)
def test_public_addresses_allowed(address: str) -> None:
    assert classify_ip(address) is None


@pytest.mark.parametrize(
    "address",
    [
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "100.64.0.1",
        "100.100.100.200",  # metadata Alibaba
        "fd12:3456::1",
        "fd00:ec2::254",  # metadata AWS IPv6
        "::ffff:8.8.8.8",  # IPv4-mapped bị chặn hẳn, kể cả khi IPv4 bên trong là công cộng
        "fec0::1",  # site-local
        "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo
        "64:ff9b:1::1",  # NAT64 local-use
        "2002:808:808::1",  # 6to4 của IP công cộng
    ],
)
def test_private_and_special_ranges_are_always_blocked(address: str) -> None:
    # Jira là cloud: không còn cờ nới mạng nội bộ.
    assert classify_ip(address) is not None


def _resolver(*answers: Sequence[str]):
    """Resolver giả trả lần lượt từng đáp án; ghi số lần gọi."""
    calls: list[str] = []

    async def resolve(host: str) -> list[str]:
        calls.append(host)
        return list(answers[min(len(calls), len(answers)) - 1])

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


async def test_check_host_blocks_if_any_address_is_bad() -> None:
    # Kẻ điều khiển DNS trộn một bản ghi công cộng với một bản ghi nội bộ.
    resolver = _resolver([PUBLIC, "169.254.169.254"])
    with pytest.raises(HostBlockedError) as exc:
        await check_host("jira.example.com", resolver=resolver)
    # Thông báo không lộ IP đã phân giải.
    assert "169.254" not in exc.value.message


async def test_check_host_returns_deduplicated_checked_addresses() -> None:
    resolver = _resolver([PUBLIC, PUBLIC, "2606:4700:4700::1111"])
    got = await check_host("jira.example.com", resolver=resolver)
    assert got == [PUBLIC, "2606:4700:4700::1111"]


async def test_check_host_unresolvable() -> None:
    async def boom(host: str) -> list[str]:
        raise OSError("dns down")

    with pytest.raises(HostUnresolvableError):
        await check_host("jira.example.com", resolver=boom)
    with pytest.raises(HostUnresolvableError):
        await check_host("jira.example.com", resolver=_resolver([]))


async def test_all_network_failures_share_one_message() -> None:
    # Không phân biệt "không phân giải được" / "IP bị chặn" (không thành oracle dò mạng).
    async def boom(host: str) -> list[str]:
        raise OSError("dns down")

    messages = set()
    for resolver in (boom, _resolver([]), _resolver(["127.0.0.1"]), _resolver(["10.0.0.5"])):
        with pytest.raises(NetworkUnavailableError) as exc:
            await check_host("jira.example.com", resolver=resolver)
        messages.add(exc.value.message)
    assert len(messages) == 1
    assert "nội bộ" not in messages.pop()


def test_private_networks_flag_no_longer_exists() -> None:
    assert not hasattr(settings, "integration_allow_private_networks")


# ═══════════════════════════════════════════════════════════════════════
#  Ghim IP: backend ghi lại điểm đến TCP thật
# ═══════════════════════════════════════════════════════════════════════

_OK = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"


class RecordingBackend(httpcore.AsyncMockBackend):
    def __init__(self, buffer: list[bytes]) -> None:
        super().__init__(buffer)
        self.connects: list[tuple[str, int]] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # type: ignore[no-untyped-def]
        self.connects.append((host, port))
        return await super().connect_tcp(host, port, timeout, local_address, socket_options)


def _transport(resolver, recorder: RecordingBackend, host: str = "jira.example.com"):  # type: ignore[no-untyped-def]
    return PinnedTransport(
        host,
        resolver=resolver,
        backend_factory=lambda ips: _FixedIPBackend(ips, inner=recorder),
    )


async def _get(
    transport: PinnedTransport, url: str = "https://jira.example.com/x"
) -> httpx.Response:
    async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
        return await client.get(url)


async def test_connects_to_checked_ip_not_hostname() -> None:
    recorder = RecordingBackend([_OK])
    resolver = _resolver([PUBLIC])
    resp = await _get(_transport(resolver, recorder))
    assert resp.status_code == 200
    # TCP tới IP đã kiểm, không phải tên miền; cổng 443.
    assert recorder.connects == [(PUBLIC, 443)]
    assert len(resolver.calls) == 1  # type: ignore[attr-defined]


async def test_dns_rebinding_second_answer_has_no_effect_within_a_request() -> None:
    # Lần phân giải thứ hai (nếu ai đó phân giải lại lúc kết nối) sẽ trả loopback. Vì ta
    # chỉ phân giải MỘT lần rồi ghim, kết nối vẫn tới IP công cộng đã kiểm.
    recorder = RecordingBackend([_OK])
    resolver = _resolver([PUBLIC], ["127.0.0.1"])
    await _get(_transport(resolver, recorder))
    assert recorder.connects == [(PUBLIC, 443)]
    assert len(resolver.calls) == 1  # type: ignore[attr-defined]


async def test_each_request_is_rechecked_and_rebinding_between_requests_is_blocked() -> None:
    recorder = RecordingBackend([_OK, _OK])
    resolver = _resolver([PUBLIC], ["127.0.0.1"])
    transport = _transport(resolver, recorder)
    await _get(transport)
    with pytest.raises(HostBlockedError):
        await _get(transport)
    assert recorder.connects == [(PUBLIC, 443)]  # request thứ hai không bao giờ mở TCP


@pytest.mark.parametrize(
    "bad_ip", ["127.0.0.1", "169.254.169.254", "10.0.0.5", "::1", "::ffff:127.0.0.1", "fe80::1"]
)
async def test_blocked_ip_never_opens_a_connection(bad_ip: str) -> None:
    recorder = RecordingBackend([_OK])
    with pytest.raises(HostBlockedError):
        await _get(_transport(_resolver([bad_ip]), recorder))
    assert recorder.connects == []


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.com/x",  # host khác (vd. sau redirect)
        "http://jira.example.com/x",  # không phải https
        "https://jira.example.com:8443/x",  # cổng lạ
    ],
)
async def test_transport_only_talks_to_the_saved_host_over_https_443(url: str) -> None:
    recorder = RecordingBackend([_OK])
    resolver = _resolver([PUBLIC])
    with pytest.raises(httpx.UnsupportedProtocol):
        await _get(_transport(resolver, recorder), url)
    assert recorder.connects == []
    assert resolver.calls == []  # type: ignore[attr-defined]


async def test_fixed_backend_tries_next_checked_ip_and_ignores_requested_host() -> None:
    class Flaky(httpcore.AsyncMockBackend):
        def __init__(self) -> None:
            super().__init__([_OK])
            self.tried: list[str] = []

        async def connect_tcp(
            self,
            host,
            port,
            timeout=None,
            local_address=None,
            socket_options=None,
        ):  # type: ignore[no-untyped-def]
            self.tried.append(host)
            if host == "104.192.140.2":
                raise httpcore.ConnectError("x")
            return await super().connect_tcp(host, port, timeout, local_address, socket_options)

    inner = Flaky()
    backend = _FixedIPBackend(["104.192.140.2", "104.192.140.3"], inner=inner)
    await backend.connect_tcp("evil-rebind.example.com", 443)
    assert inner.tried == ["104.192.140.2", "104.192.140.3"]
