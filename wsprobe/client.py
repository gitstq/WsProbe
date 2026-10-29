"""WsProbe WebSocket 客户端(基于 :mod:`wsprobe.frame` 自研协议栈)。

特性:

* 支持 ``ws://`` 与 ``wss://``,支持 HTTP CONNECT 代理
* 自动响应服务端 ``PING``(RFC 要求收到 ping 必须回 pong)
* 主动 ``PING`` 并测量往返时延(RTT),用于链路质量评估
* 规范的关闭握手(发送 close -> 等待 close 回应 -> 关闭 TCP)
* 分片消息自动重组、控制帧内联处理
* 内置计数器(:class:`wsprobe.stats.SessionStats`)
* 可作为上下文管理器 / 迭代器使用
"""

from __future__ import annotations

import json
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterator, List, Optional, Union

from . import handshake as hs
from .frame import (
    CLOSE_GOING_AWAY,
    CLOSE_NORMAL,
    DEFAULT_MAX_PAYLOAD,
    OP_BINARY,
    OP_CLOSE,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    ConnectionClosed,
    Frame,
    MessageAssembler,
    PayloadTooLargeError,
    ProtocolError,
    WebSocketError,
    apply_mask,
    decode_close_payload,
    encode_close_frame,
    encode_frame,
    generate_masking_key,
    read_frame,
)
from .stats import SessionStats


@dataclass
class Message:
    """一条完整的 WebSocket 消息。"""

    opcode: int
    data: bytes
    direction: str  # "in" | "out"
    timestamp: float = field(default_factory=time.time)
    index: int = 0

    @property
    def is_text(self) -> bool:
        return self.opcode == OP_TEXT

    @property
    def is_binary(self) -> bool:
        return self.opcode == OP_BINARY

    @property
    def text(self) -> str:
        """按 UTF-8 解码的文本内容(错误替换为 U+FFFD)。"""
        return self.data.decode("utf-8", errors="replace")

    @property
    def json(self) -> Any:
        """尝试把文本负载解析为 JSON,失败抛出 :class:`json.JSONDecodeError`。"""
        return json.loads(self.text)

    @property
    def size(self) -> int:
        return len(self.data)

    def preview(self, limit: int = 512) -> str:
        """生成可安全打印的预览文本。"""
        if self.is_binary:
            head = self.data[: limit // 2]
            return f"<binary {len(self.data)}B: {head.hex()}>"
        text = self.text
        return text if len(text) <= limit else text[:limit] + f"...(+{len(text) - limit})"

    def to_record(self) -> Dict[str, Any]:
        """转成可 JSON 序列化的记录(用于录制 / 机器可读输出)。"""
        record: Dict[str, Any] = {
            "ts": round(self.timestamp, 6),
            "dir": self.direction,
            "op": "text" if self.is_text else "binary",
            "size": self.size,
        }
        if self.is_text:
            record["data"] = self.text
        else:
            record["data"] = self.data.hex()
        return record


class WebSocketClient:
    """零依赖 WebSocket 客户端。

    典型用法::

        with WebSocketClient("ws://localhost:8765") as ws:
            ws.send_text("hello")
            for msg in ws:
                print(msg.text)
                break
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        subprotocols: Optional[List[str]] = None,
        timeout: float = 10.0,
        proxy: Optional[str] = None,
        verify_tls: bool = True,
        max_payload: int = DEFAULT_MAX_PAYLOAD,
        auto_pong: bool = True,
        user_agent: str = hs.DEFAULT_USER_AGENT,
        strict_accept: bool = True,
    ):
        self.url = hs.WebSocketURL(url)
        self.headers = dict(headers or {})
        self.subprotocols = list(subprotocols or [])
        self.timeout = timeout
        self.proxy = proxy
        self.verify_tls = verify_tls
        self.max_payload = max_payload
        self.auto_pong = auto_pong
        self.user_agent = user_agent
        self.strict_accept = strict_accept

        self.sock: Optional[socket.socket] = None
        self.key: str = ""
        self.response_status: int = 0
        self.response_reason: str = ""
        self.response_headers: Dict[str, str] = {}
        self.negotiated: Dict[str, str] = {}
        self.stats = SessionStats()
        self.close_code: Optional[int] = None
        self.close_reason: str = ""
        self._assembler = MessageAssembler(max_payload=max_payload)
        self._pending: Deque[Message] = deque()
        self._counter = 0
        self._closed = False
        self._leftover: bytes = b""

    # ------------------------------------------------------------------
    # 连接生命周期
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.sock is not None and not self._closed

    def connect(self) -> "WebSocketClient":
        """执行 TCP/TLS 连接 + HTTP Upgrade 握手。"""
        if self.connected:
            return self
        self.stats = SessionStats()
        self.key = hs.generate_key()
        request = hs.build_upgrade_request(
            self.url, self.key, self.headers, self.subprotocols, self.user_agent
        )
        self.sock = hs.create_socket(
            self.url, timeout=self.timeout, proxy=self.proxy, verify_tls=self.verify_tls
        )
        try:
            self.sock.sendall(request)
            buffer = hs._recv_headers(self.sock)
            status, reason, headers, leftover = hs.parse_http_response(buffer)
        except (OSError, WebSocketError):
            self._force_close()
            raise

        self.response_status = status
        self.response_reason = reason
        self.response_headers = headers
        self._leftover = leftover
        if status != 101:
            self._force_close()
            raise hs.HandshakeError(
                f"server returned HTTP {status} {reason} (expected 101 Switching Protocols)"
            )
        try:
            self.negotiated = hs.check_upgrade_response(
                headers, self.key, strict=self.strict_accept
            )
        except hs.HandshakeError:
            self._force_close()
            raise
        return self

    def close(self, code: int = CLOSE_NORMAL, reason: str = "", timeout: float = 2.0) -> None:
        """执行规范的关闭握手。"""
        if self.sock is None or self._closed:
            return
        try:
            if self.sock.fileno() != -1:
                self.sock.sendall(encode_close_frame(code, reason))
        except OSError:
            pass
        # 等待服务端回一个 close 帧(RFC 建议的 half-close 流程)
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                frame = read_frame(self.sock, max_payload=self.max_payload)
                if frame.opcode == OP_CLOSE:
                    self.close_code, self.close_reason = decode_close_payload(frame.payload)
                    break
                if frame.opcode == OP_PING and self.auto_pong:
                    self.sock.sendall(
                        encode_frame(frame.payload, opcode=OP_PONG, fin=True, mask=True)
                    )
        except (OSError, WebSocketError):
            pass
        self._force_close()

    def abort(self) -> None:
        """立即关闭底层 socket,不做关闭握手。"""
        self._force_close()

    def _force_close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self._closed = True
        self.stats.finish()

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------

    def _require_socket(self) -> socket.socket:
        if self.sock is None or self._closed:
            raise WebSocketError("client is not connected")
        return self.sock

    def send(self, data: Union[str, bytes], opcode: int = OP_TEXT) -> Message:
        """发送一条消息(``str`` 走文本帧,``bytes`` 默认走二进制帧)。"""
        sock = self._require_socket()
        if isinstance(data, str):
            payload = data.encode("utf-8")
            opcode = OP_TEXT
        else:
            payload = data
            if opcode == OP_TEXT:
                opcode = OP_BINARY
        sock.sendall(encode_frame(payload, opcode=opcode, fin=True, mask=True))
        self._counter += 1
        self.stats.record_sent(len(payload))
        return Message(opcode=opcode, data=payload, direction="out", index=self._counter)

    def send_text(self, text: str) -> Message:
        return self.send(text, opcode=OP_TEXT)

    def send_binary(self, data: bytes) -> Message:
        return self.send(data, opcode=OP_BINARY)

    def send_json(self, obj: Any) -> Message:
        return self.send_text(json.dumps(obj, ensure_ascii=False))

    def send_fragmented(self, chunks: List[bytes], opcode: int = OP_TEXT) -> Message:
        """以分片方式发送一条消息(用于验证服务端分片重组能力)。"""
        sock = self._require_socket()
        if not chunks:
            raise ValueError("chunks must not be empty")
        total = bytearray()
        last = len(chunks) - 1
        for i, chunk in enumerate(chunks):
            sock.sendall(
                encode_frame(chunk, opcode=opcode if i == 0 else 0x0, fin=(i == last), mask=True)
            )
            total.extend(chunk)
        self._counter += 1
        self.stats.record_sent(len(total))
        return Message(opcode=opcode, data=bytes(total), direction="out", index=self._counter)

    def ping(self, payload: bytes = b"wsprobe", timeout: Optional[float] = None) -> Optional[float]:
        """发送 PING 并等待对应的 PONG,返回 RTT(秒)。

        等待期间收到的普通数据消息会被缓存,后续 :meth:`recv` 仍能取到。
        """
        sock = self._require_socket()
        token = payload or b"wsprobe"
        sock.sendall(encode_frame(token, opcode=OP_PING, fin=True, mask=True))
        self.stats.pings_sent += 1
        started = time.time()
        limit = timeout if timeout is not None else self.timeout
        sock.settimeout(limit)
        try:
            while True:
                frame = read_frame(sock, max_payload=self.max_payload)
                if frame.opcode == OP_PONG:
                    rtt = time.time() - started
                    self.stats.pongs_received += 1
                    self.stats.record_rtt(rtt)
                    sock.settimeout(self.timeout)
                    return rtt
                if frame.opcode == OP_PING and self.auto_pong:
                    sock.sendall(encode_frame(frame.payload, opcode=OP_PONG, fin=True, mask=True))
                    continue
                if frame.opcode == OP_CLOSE:
                    self.close_code, self.close_reason = decode_close_payload(frame.payload)
                    sock.settimeout(self.timeout)
                    raise ConnectionClosed(self.close_code, self.close_reason)
                # 数据消息:先缓存,不打断 PING 等待
                if self._pending is not None:
                    self._counter += 1
                    self._pending.append(
                        Message(
                            opcode=frame.opcode,
                            data=frame.payload,
                            direction="in",
                            index=self._counter,
                        )
                    )
                    self.stats.record_received(frame.opcode, len(frame.payload))
        except socket.timeout:
            sock.settimeout(self.timeout)
            return None
        finally:
            sock.settimeout(self.timeout)

    # ------------------------------------------------------------------
    # 接收
    # ------------------------------------------------------------------

    def recv(self, timeout: Optional[float] = None) -> Message:
        """接收一条完整消息(自动处理 PING/PONG/CLOSE 控制帧)。"""
        if self._pending:
            return self._pending.popleft()
        sock = self._require_socket()
        limit = timeout if timeout is not None else self.timeout
        sock.settimeout(limit)
        try:
            while True:
                frame = read_frame(sock, max_payload=self.max_payload)
                if frame.opcode == OP_PING:
                    self.stats.pings_received += 1
                    if self.auto_pong:
                        sock.sendall(
                            encode_frame(frame.payload, opcode=OP_PONG, fin=True, mask=True)
                        )
                    continue
                if frame.opcode == OP_PONG:
                    self.stats.pongs_received += 1
                    continue
                if frame.opcode == OP_CLOSE:
                    self.close_code, self.close_reason = decode_close_payload(frame.payload)
                    # 回送 close 回应,完成关闭握手
                    try:
                        sock.sendall(encode_close_frame(self.close_code or CLOSE_NORMAL))
                    except OSError:
                        pass
                    self._force_close()
                    raise ConnectionClosed(self.close_code, self.close_reason)

                merged = self._assembler.feed(frame)
                if merged is None:
                    continue
                self._counter += 1
                self.stats.record_received(merged.opcode, len(merged.payload))
                return Message(
                    opcode=merged.opcode,
                    data=merged.payload,
                    direction="in",
                    index=self._counter,
                )
        except socket.timeout:
            raise
        finally:
            if self.sock is not None:
                self.sock.settimeout(self.timeout)

    def __iter__(self) -> Iterator[Message]:
        """持续迭代收到的消息,直到连接关闭。"""
        while True:
            try:
                yield self.recv()
            except (socket.timeout, TimeoutError):
                return
            except ConnectionClosed:
                return

    def iter_messages(self, count: Optional[int] = None, timeout: Optional[float] = None):
        """按条数迭代,超时或达到条数后停止。"""
        emitted = 0
        while count is None or emitted < count:
            try:
                yield self.recv(timeout=timeout)
            except (socket.timeout, TimeoutError):
                return
            except ConnectionClosed:
                return
            emitted += 1

    # ------------------------------------------------------------------
    # 上下文协议
    # ------------------------------------------------------------------

    def __enter__(self) -> "WebSocketClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 诊断信息
    # ------------------------------------------------------------------

    def handshake_report(self) -> Dict[str, Any]:
        """生成握手诊断报告(用于 ``wsprobe inspect``)。"""
        return {
            "url": self.url.raw,
            "scheme": self.url.scheme,
            "host": self.url.host,
            "port": self.url.port,
            "path": self.url.path,
            "resolved_ip": hs.resolve_host(self.url.host),
            "request_key": self.key,
            "expected_accept": hs.compute_accept(self.key),
            "status": self.response_status,
            "reason": self.response_reason,
            "headers": self.response_headers,
            "negotiated": self.negotiated,
            "proxy": self.proxy,
        }
