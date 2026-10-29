"""WebSocket  opening handshake(RFC 6455 第 4 章)自研实现。

包含:

* ``Sec-WebSocket-Key`` 随机密钥生成(16 字节 CSPRNG -> Base64)
* ``Sec-WebSocket-Accept`` 计算与校验(SHA-1 + 协议 GUID)
* HTTP Upgrade 请求构建(支持自定义 Header、子协议、Basic 认证、Cookie)
* HTTP 101 Switching Protocols 响应解析(支持 chunked / 分块读取)
* ``wss://`` 所需的 TLS 包装与 SNI 设置
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .frame import ProtocolError, WebSocketError

#: RFC 6455 规定的固定 GUID,用于计算 Sec-WebSocket-Accept
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

DEFAULT_PORTS = {"ws": 80, "wss": 443, "http": 80, "https": 443}

DEFAULT_USER_AGENT = "WsProbe/1.0.0 (zero-dependency WebSocket probe)"


class HandshakeError(WebSocketError):
    """握手失败(非 101 响应、Accept 校验失败、协议违规等)。"""


def generate_key() -> str:
    """生成随机的 ``Sec-WebSocket-Key``(16 随机字节的 Base64)。"""
    return base64.b64encode(os.urandom(16)).decode("ascii")


def compute_accept(key: str) -> str:
    """由客户端 Key 计算期望的 ``Sec-WebSocket-Accept`` 值。"""
    digest = hashlib.sha1((key + WEBSOCKET_GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_accept(key: str, accept: Optional[str]) -> bool:
    """校验服务端返回的 Accept 是否与本地计算值一致。"""
    if not accept:
        return False
    return compute_accept(key) == accept.strip()


class WebSocketURL:
    """解析后的 WebSocket 目标地址。"""

    __slots__ = ("scheme", "host", "port", "path", "query", "secure", "raw")

    def __init__(self, url: str):
        if "://" not in url:
            url = "ws://" + url
        parsed = urlparse(url)
        scheme = (parsed.scheme or "ws").lower()
        if scheme == "http":
            scheme = "ws"
        elif scheme == "https":
            scheme = "wss"
        if scheme not in ("ws", "wss"):
            raise HandshakeError(f"unsupported scheme: {parsed.scheme!r}")

        self.scheme = scheme
        self.secure = scheme == "wss"
        self.host = parsed.hostname or "localhost"
        if parsed.port:
            self.port = parsed.port
        else:
            self.port = 443 if self.secure else 80
        self.path = parsed.path or "/"
        if parsed.query:
            self.path += "?" + parsed.query
        self.raw = url

    @property
    def origin(self) -> str:
        http_scheme = "https" if self.secure else "http"
        default_port = 443 if self.secure else 80
        host = f"{self.host}:{self.port}" if self.port != default_port else self.host
        return f"{http_scheme}://{host}"

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"WebSocketURL({self.raw!r})"


def build_upgrade_request(
    target: WebSocketURL,
    key: str,
    headers: Optional[Dict[str, str]] = None,
    subprotocols: Optional[List[str]] = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> bytes:
    """构建 HTTP/1.1 Upgrade 请求报文字节序列。"""
    host_header = (
        f"{target.host}:{target.port}"
        if target.port not in (80, 443)
        else target.host
    )
    lines = [
        f"GET {target.path} HTTP/1.1",
        f"Host: {host_header}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
        f"Origin: {target.origin}",
        f"User-Agent: {user_agent}",
    ]
    if subprotocols:
        lines.append("Sec-WebSocket-Protocol: " + ", ".join(subprotocols))
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


def _recv_headers(sock) -> bytes:
    """读到 HTTP 响应头结束(``\\r\\n\\r\\n``)为止,返回含头部的缓冲。"""
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise HandshakeError("connection closed before handshake completed")
        buffer.extend(chunk)
        if len(buffer) > 128 * 1024:
            raise HandshakeError("handshake response header too large")
    return bytes(buffer)


def parse_http_response(buffer: bytes) -> Tuple[int, str, Dict[str, str], bytes]:
    """解析 HTTP 响应,返回 ``(status, reason, headers, leftover_bytes)``。

    响应头字段名统一小写,便于大小写不敏感查找。
    """
    head, _, leftover = buffer.partition(b"\r\n\r\n")
    try:
        text = head.decode("iso-8859-1")
    except UnicodeDecodeError:  # pragma: no cover - 理论上不会发生
        raise HandshakeError("malformed handshake response")
    lines = text.split("\r\n")
    status_line = lines[0]
    parts = status_line.split(" ", 2)
    if len(parts) < 2:
        raise HandshakeError(f"malformed status line: {status_line!r}")
    try:
        status = int(parts[1])
    except ValueError:
        raise HandshakeError(f"non-numeric status code: {parts[1]!r}")
    reason = parts[2] if len(parts) > 2 else ""

    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return status, reason, headers, leftover


def create_socket(
    target: WebSocketURL,
    timeout: float = 10.0,
    proxy: Optional[str] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
    verify_tls: bool = True,
):
    """建立底层 TCP/TLS 连接,支持 HTTP CONNECT 代理隧道。

    :return: ``(socket, leftover_bytes_from_proxy)``
    """
    connect_host = target.host
    connect_port = target.port

    if proxy:
        sock = _connect_through_proxy(proxy, connect_host, connect_port, timeout)
    else:
        sock = socket.create_connection((connect_host, connect_port), timeout=timeout)
    sock.settimeout(timeout)

    if target.secure:
        ctx = ssl_context or _default_ssl_context(verify_tls)
        try:
            sock = ctx.wrap_socket(sock, server_hostname=connect_host)
        except ssl.SSLError as exc:
            raise HandshakeError(f"TLS handshake failed: {exc}") from exc
    return sock


def _default_ssl_context(verify: bool) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _connect_through_proxy(proxy: str, host: str, port: int, timeout: float) -> socket.socket:
    """通过 HTTP CONNECT 代理建立隧道。"""
    if "://" not in proxy:
        proxy = "http://" + proxy
    parsed = urlparse(proxy)
    p_host = parsed.hostname or "127.0.0.1"
    p_port = parsed.port or 8080
    sock = socket.create_connection((p_host, p_port), timeout=timeout)
    request = (
        f"CONNECT {host}:{port} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Proxy-Connection: keep-alive\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    buffer = _recv_headers(sock)
    status, reason, _, _ = parse_http_response(buffer)
    if status != 200:
        sock.close()
        raise HandshakeError(f"proxy refused CONNECT: {status} {reason}")
    return sock


def resolve_host(host: str) -> str:
    """解析主机(用于输出诊断信息),失败时回退为原始字符串。"""
    try:
        return socket.gethostbyname(host)
    except OSError:
        return host


def check_upgrade_response(headers: Dict[str, str], key: str, strict: bool = True) -> Dict[str, str]:
    """校验服务端握手响应是否合法,返回协商结果。

    :raises HandshakeError: 缺少 Upgrade/Connection 或 Accept 校验失败
    """
    upgrade = headers.get("upgrade", "").lower()
    connection = headers.get("connection", "").lower()
    accept = headers.get("sec-websocket-accept")

    if upgrade != "websocket":
        raise HandshakeError(f"server did not upgrade: Upgrade={headers.get('upgrade')!r}")
    if "upgrade" not in connection:
        raise HandshakeError(f"missing 'Upgrade' in Connection header: {connection!r}")
    if strict and not verify_accept(key, accept):
        raise HandshakeError("Sec-WebSocket-Accept verification failed")

    result = {
        "accept": accept or "",
        "protocol": headers.get("sec-websocket-protocol", ""),
        "extensions": headers.get("sec-websocket-extensions", ""),
        "accept_valid": verify_accept(key, accept),
    }
    return result
