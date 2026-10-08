"""Chống SSRF cho connector gọi ra ngoài (Jira): kiểm IP đích và GHIM IP lúc kết nối.

══════════════════════════════════════════════════════════════════════
 CẢNH BÁO: file này là hàng rào SSRF và DNS-rebinding. Mọi request ra ngoài của connector
 BẮT BUỘC đi qua `PinnedTransport`. Quy tắc cứng:
 - KHÔNG bao giờ để thư viện HTTP tự phân giải tên miền lúc kết nối. Tên miền được phân
   giải MỘT lần trong `check_host`, MỌI địa chỉ trả về đều phải hợp lệ, rồi kết nối TCP tới
   đúng IP đã kiểm (`_FixedIPBackend`). Nếu để thư viện phân giải lại, kẻ điều khiển DNS trả
   IP công cộng cho lần kiểm và 127.0.0.1/169.254.169.254 cho lần kết nối (DNS rebinding).
 - Tên host trong URL vẫn được giữ nguyên cho SNI và kiểm chứng chỉ TLS (verify bật, kiểm
   hostname theo base_url); ta chỉ thay ĐIỂM ĐẾN TCP, không thay danh tính TLS.
 - Thông báo lỗi trả cho client KHÔNG chứa IP đã phân giải (tránh để dò mạng nội bộ qua
   thông báo). IP chỉ vào log của server.
 - Không proxy (client phải tạo với trust_env=False): proxy sẽ làm connect tới proxy, bỏ
   qua mọi kiểm tra ở đây.
══════════════════════════════════════════════════════════════════════

Phân loại địa chỉ (Jira là CLOUD nên KHÔNG có cờ nới mạng nội bộ):
- Chặn tuyệt đối: loopback, link-local (gồm metadata cloud 169.254.169.254), multicast,
  unspecified, 0.0.0.0/8, reserved/broadcast, RFC1918, CGNAT 100.64/10, unique-local
  fc00::/7, mọi IPv4-mapped (::ffff:0:0/96), site-local, 6to4, Teredo, NAT64 local-use;
  NAT64 `64:ff9b::/96` xét theo IPv4 bên trong.
- Các địa chỉ metadata đáng ngại (100.100.100.200 của Alibaba, fd00:ec2::254 của AWS) được
  liệt kê TƯỜNG MINH dù đã nằm trong dải trên, để không phụ thuộc vào bản Python/ipaddress.
- Còn lại phải là địa chỉ toàn cầu (`is_global`).
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Final

import httpcore
import httpx

from app.services.errors import DomainError

logger = logging.getLogger(__name__)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str], Awaitable[Sequence[str]]]
BackendFactory = Callable[[Sequence[str]], httpcore.AsyncNetworkBackend]

DNS_TIMEOUT_SECONDS: Final = 10.0
HTTPS_PORT: Final = 443

_BLOCKED = tuple(
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "100.100.100.200/32",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/96",  # gồm ::, ::1 và dạng IPv4-compatible ::a.b.c.d
        "::ffff:0:0/96",  # IPv4-mapped: chặn hẳn, không xét IPv4 bên trong
        "64:ff9b:1::/48",
        "2001::/32",  # Teredo
        "2002::/16",  # 6to4
        "fc00::/7",
        "fd00:ec2::254/128",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
    )
)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


NETWORK_ERROR_MESSAGE = "Không kết nối được tới Jira. Kiểm tra base_url và mạng rồi thử lại."


class NetworkUnavailableError(DomainError):
    """Lỗi mạng khi gọi ra ngoài. Thông báo CỐ ĐỊNH, dùng chung cho mọi nguyên nhân.

    WHY gộp: nếu "không phân giải được", "IP bị chặn" và "timeout" có thông báo khác nhau
    thì người có API key dò được host/cổng nào trong mạng nội bộ tồn tại (oracle). Nguyên
    nhân thật chỉ nằm trong log của server.
    """

    status_code = 502

    def __init__(self) -> None:
        super().__init__(NETWORK_ERROR_MESSAGE)


class HostBlockedError(NetworkUnavailableError):
    """Host phân giải tới địa chỉ không được phép."""


class HostUnresolvableError(NetworkUnavailableError):
    """Không phân giải được tên miền."""


def _in_any(
    ip: IPAddress, networks: Sequence[ipaddress.IPv4Network | ipaddress.IPv6Network]
) -> bool:
    return any(ip.version == net.version and ip in net for net in networks)


def classify_ip(address: str) -> str | None:
    """Trả `None` nếu được phép kết nối, ngược lại là tên nhóm bị chặn (chỉ để log).

    Địa chỉ không parse được cũng bị chặn (fail closed).
    """
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])  # bỏ zone id của IPv6
    except ValueError:
        return "invalid"
    # NAT64 (64:ff9b::a.b.c.d) được coi là toàn cầu nên phải xét IPv4 bên trong, nếu không
    # `64:ff9b::7f00:1` lọt qua. IPv4-mapped đã nằm trong _BLOCKED.
    if isinstance(ip, ipaddress.IPv6Address) and ip in _NAT64:
        return classify_ip(str(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)))
    if _in_any(ip, _BLOCKED) or ip.is_multicast or ip.is_unspecified or ip.is_loopback:
        return "blocked-range"
    if not ip.is_global:
        return "non-global"
    return None


async def system_resolver(host: str) -> list[str]:
    """getaddrinfo (A + AAAA) trên thread executor, tối đa DNS_TIMEOUT_SECONDS."""
    loop = asyncio.get_running_loop()
    async with asyncio.timeout(DNS_TIMEOUT_SECONDS):
        infos = await loop.getaddrinfo(host, HTTPS_PORT, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def check_host(host: str, *, resolver: Resolver | None = None) -> list[str]:
    """Phân giải `host` và trả danh sách IP ĐÃ KIỂM (bỏ trùng, giữ thứ tự).

    Chặn nếu BẤT KỲ địa chỉ nào không được phép, không chỉ cái đầu: client có thể chọn
    địa chỉ khác khi kết nối, và kẻ điều khiển DNS hay trộn một bản ghi công cộng với một
    bản ghi nội bộ.

    Raises:
        HostBlockedError: có địa chỉ bị chặn.
        HostUnresolvableError: không phân giải được hoặc không có địa chỉ.
    """
    try:
        raw = await (resolver or system_resolver)(host)
    except (OSError, TimeoutError) as exc:
        logger.warning("dns_failed host=%s error=%s", host, type(exc).__name__)
        raise HostUnresolvableError from None
    addresses = list(dict.fromkeys(a.split("%", 1)[0] for a in raw))
    if not addresses:
        raise HostUnresolvableError
    for address in addresses:
        verdict = classify_ip(address)
        if verdict is not None:
            # IP chỉ vào log của server để điều tra, không vào response.
            logger.warning(
                "ssrf_blocked host=%s address=%s reason=%s",
                host,
                address,
                verdict,
                extra={"audit": "ssrf", "host": host, "address": address, "reason": verdict},
            )
            raise HostBlockedError
    return addresses


class _FixedIPBackend(httpcore.AsyncNetworkBackend):
    """Kết nối TCP tới IP đã kiểm, BỎ QUA tên host mà httpcore đưa vào (chống rebinding).

    httpcore vẫn dùng tên host gốc cho SNI và kiểm chứng chỉ ở bước `start_tls`; ta chỉ đổi
    đích TCP. Thử lần lượt các IP đã kiểm (vd. IPv6 hỏng thì sang IPv4).
    """

    def __init__(
        self, addresses: Sequence[str], inner: httpcore.AsyncNetworkBackend | None = None
    ) -> None:
        self._addresses = list(addresses)
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - chữ ký bắt buộc của httpcore
        local_address: str | None = None,
        socket_options: Sequence[tuple[int, int, int] | tuple[int, int, int | bytes]] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        last: Exception | None = None
        for address in self._addresses:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last = exc
        raise last or httpcore.ConnectError("không có địa chỉ để kết nối")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - chữ ký bắt buộc của httpcore
        socket_options: Sequence[tuple[int, int, int] | tuple[int, int, int | bytes]] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix socket không được phép")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


_ssl_context: ssl.SSLContext | None = None


def _default_ssl_context() -> ssl.SSLContext:
    # verify bật + kiểm hostname (mặc định của httpx). Dựng một lần, dùng chung.
    global _ssl_context
    if _ssl_context is None:
        _ssl_context = httpx.create_ssl_context(verify=True)
    return _ssl_context


class _PoolStream(httpx.AsyncByteStream):
    """Thân response; đóng thân rồi đóng pool (mỗi request một pool, không giữ kết nối)."""

    def __init__(self, stream: AsyncIterator[bytes], pool: httpcore.AsyncConnectionPool) -> None:
        self._stream = stream
        self._pool = pool

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        try:
            close = getattr(self._stream, "aclose", None)
            if close is not None:
                await close()
        finally:
            await self._pool.aclose()


class PinnedTransport(httpx.AsyncBaseTransport):
    """Transport httpx: mỗi request = kiểm DNS + kết nối tới IP đã kiểm + đóng.

    - Chỉ https, cổng 443, và CHỈ host `allowed_host` (host của base_url đã lưu). Request
      tới host khác (kể cả do lỡ bật follow_redirects) bị chặn trước khi gửi, nên header
      Authorization không thể rời khỏi host đó.
    - Không giữ kết nối (keep-alive tắt): mỗi request phân giải và kiểm lại, nên một lần
      sync dài cũng không dùng IP đã cũ.
    """

    def __init__(
        self,
        allowed_host: str,
        *,
        resolver: Resolver | None = None,
        backend_factory: BackendFactory | None = None,
    ) -> None:
        self._allowed_host = allowed_host.lower()
        self._resolver = resolver
        self._backend_factory = backend_factory or (lambda ips: _FixedIPBackend(ips))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if (
            url.scheme != "https"
            or url.port not in (None, HTTPS_PORT)
            or url.host.lower() != self._allowed_host
        ):
            # Thông báo cố định, không lặp lại URL/host đích.
            raise httpx.UnsupportedProtocol("request tới host/cổng ngoài kết nối bị chặn")
        addresses = await check_host(url.host, resolver=self._resolver)
        pool = httpcore.AsyncConnectionPool(
            ssl_context=_default_ssl_context(),
            max_connections=1,
            max_keepalive_connections=0,
            keepalive_expiry=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=self._backend_factory(addresses),
        )
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=url.raw_scheme, host=url.raw_host, port=url.port, target=url.raw_path
            ),
            headers=request.headers.raw,
            content=request.stream,  # type: ignore[arg-type]
            extensions=request.extensions,
        )
        try:
            response = await pool.handle_async_request(core_request)
        except BaseException:
            await pool.aclose()
            raise
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_PoolStream(response.stream, pool),  # type: ignore[arg-type]
            extensions=response.extensions,
        )
