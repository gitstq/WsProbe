"""RFC 6455 WebSocket 帧编解码层(100% 自研,零第三方依赖)。

本模块实现了 WebSocket 二进制帧的完整编解码逻辑,包括:

* 基础帧头解析(FIN / RSV1-3 / opcode / MASK / payload length)
* 扩展负载长度(7bit / 16bit / 64bit 三档)
* 客户端掩码(masking key)的生成与应用
* 控制帧合法性校验(fin 必须为 1、负载 <= 125 字节、禁止分片)
* 分片消息的重组(continuation 帧)
* 关闭帧状态码编解码

设计目标:不依赖 ``websockets`` / ``websocket-client`` 等任何第三方库,
仅使用 Python 标准库,保证可离线运行、可审计、可嵌入。
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Optional

# --------------------------------------------------------------------------
# 协议常量
# --------------------------------------------------------------------------

OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

#: 控制帧集合(不允许分片,负载不得超过 125 字节)
CONTROL_OPCODES = frozenset({OP_CLOSE, OP_PING, OP_PONG})
#: 数据帧集合(允许分片)
DATA_OPCODES = frozenset({OP_CONTINUATION, OP_TEXT, OP_BINARY})

#: 默认单帧/单消息最大负载(64 MiB),防止内存被恶意服务端打爆
DEFAULT_MAX_PAYLOAD = 64 * 1024 * 1024
#: RFC 6455 规定控制帧负载上限
MAX_CONTROL_PAYLOAD = 125

CLOSE_NORMAL = 1000
CLOSE_GOING_AWAY = 1001
CLOSE_PROTOCOL_ERROR = 1002
CLOSE_UNSUPPORTED_DATA = 1003
CLOSE_INVALID_PAYLOAD = 1007
CLOSE_POLICY_VIOLATION = 1008
CLOSE_MESSAGE_TOO_BIG = 1009
CLOSE_MANDATORY_EXTENSION = 1010
CLOSE_INTERNAL_ERROR = 1011
CLOSE_TLS_HANDSHAKE = 1015

CLOSE_REASONS = {
    CLOSE_NORMAL: "normal closure",
    CLOSE_GOING_AWAY: "going away",
    CLOSE_PROTOCOL_ERROR: "protocol error",
    CLOSE_UNSUPPORTED_DATA: "unsupported data",
    CLOSE_INVALID_PAYLOAD: "invalid payload data",
    CLOSE_POLICY_VIOLATION: "policy violation",
    CLOSE_MESSAGE_TOO_BIG: "message too big",
    CLOSE_MANDATORY_EXTENSION: "mandatory extension",
    CLOSE_INTERNAL_ERROR: "internal error",
    CLOSE_TLS_HANDSHAKE: "TLS handshake failure",
}


class WebSocketError(Exception):
    """WebSocket 领域异常基类。"""


class ProtocolError(WebSocketError):
    """服务端/客户端数据违反 RFC 6455 约束。"""


class PayloadTooLargeError(WebSocketError):
    """负载超过本地设定的安全上限。"""


class ConnectionClosed(WebSocketError):
    """连接已关闭。

    :param code: 关闭状态码,未知时为 ``None``
    :param reason: 关闭原因文本
    """

    def __init__(self, code: Optional[int] = None, reason: str = ""):
        self.code = code
        self.reason = reason
        text = f"connection closed (code={code}"
        if reason:
            text += f", reason={reason!r}"
        text += ")"
        super().__init__(text)


@dataclass
class Frame:
    """一个已解码的 WebSocket 帧。"""

    opcode: int
    payload: bytes
    fin: bool = True
    rsv1: bool = False
    rsv2: bool = False
    rsv3: bool = False

    @property
    def is_control(self) -> bool:
        return self.opcode in CONTROL_OPCODES

    @property
    def is_text(self) -> bool:
        return self.opcode == OP_TEXT

    @property
    def is_binary(self) -> bool:
        return self.opcode == OP_BINARY

    @property
    def opcode_name(self) -> str:
        return {
            OP_CONTINUATION: "continuation",
            OP_TEXT: "text",
            OP_BINARY: "binary",
            OP_CLOSE: "close",
            OP_PING: "ping",
            OP_PONG: "pong",
        }.get(self.opcode, f"reserved(0x{self.opcode:x})")


# --------------------------------------------------------------------------
# 掩码
# --------------------------------------------------------------------------


def generate_masking_key() -> bytes:
    """生成 4 字节客户端掩码密钥(使用操作系统 CSPRNG)。"""
    return os.urandom(4)


def apply_mask(data: bytes, key: bytes) -> bytes:
    """对 ``data`` 应用 XOR 掩码(RFC 6455 5.3,掩码运算自反)。"""
    if not data:
        return b""
    if len(key) != 4:
        raise ValueError("masking key must be exactly 4 bytes")
    # 将掩码扩展到与数据等长,再用大整数异或一次性完成,避免逐字节 Python 循环
    full = (key * (len(data) // 4 + 1))[: len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(full, "big")).to_bytes(
        len(data), "big"
    )


# --------------------------------------------------------------------------
# 编码
# --------------------------------------------------------------------------


def encode_frame(
    payload: bytes,
    opcode: int = OP_TEXT,
    fin: bool = True,
    mask: bool = True,
) -> bytes:
    """把一个负载编码为完整的 WebSocket 帧字节序列。

    :param payload: 负载字节
    :param opcode: 帧操作码
    :param fin: 是否为消息的最后一帧
    :param mask: 是否加掩码(RFC 要求客户端发往服务端必须加)
    """
    if opcode in CONTROL_OPCODES:
        if not fin:
            raise ProtocolError("control frames must not be fragmented")
        if len(payload) > MAX_CONTROL_PAYLOAD:
            raise ProtocolError("control frame payload exceeds 125 bytes")

    length = len(payload)
    mask_bit = 0x80 if mask else 0x00

    if length < 126:
        header = struct.pack("!BB", _first_byte(fin, opcode), mask_bit | length)
    elif length < (1 << 16):
        header = struct.pack("!BBH", _first_byte(fin, opcode), mask_bit | 126, length)
    elif length < (1 << 63):
        header = struct.pack("!BBQ", _first_byte(fin, opcode), mask_bit | 127, length)
    else:
        raise PayloadTooLargeError("payload exceeds 2^63 bytes")

    if not mask:
        return header + payload
    key = generate_masking_key()
    return header + key + apply_mask(payload, key)


def _first_byte(fin: bool, opcode: int) -> int:
    return (0x80 if fin else 0x00) | (opcode & 0x0F)


def encode_close_frame(code: int = CLOSE_NORMAL, reason: str = "") -> bytes:
    """编码关闭帧(2 字节状态码 + UTF-8 原因文本)。"""
    if code == CLOSE_TLS_HANDSHAKE:
        raise ProtocolError("1015 must not be sent on the wire")
    if not (1000 <= code <= 4999):
        raise ProtocolError("close code must be in range 1000-4999")
    body = struct.pack("!H", code)
    if reason:
        encoded = reason.encode("utf-8")
        if len(body) + len(encoded) > MAX_CONTROL_PAYLOAD:
            raise ProtocolError("close reason too long (max 123 bytes)")
        body += encoded
    return encode_frame(body, opcode=OP_CLOSE, fin=True, mask=True)


def decode_close_payload(payload: bytes) -> tuple:
    """解析关闭帧负载,返回 ``(code, reason)``。"""
    if len(payload) >= 2:
        code = struct.unpack("!H", payload[:2])[0]
        try:
            reason = payload[2:].decode("utf-8")
        except UnicodeDecodeError:
            reason = ""
        return code, reason
    if payload:
        return CLOSE_PROTOCOL_ERROR, ""
    return None, ""


# --------------------------------------------------------------------------
# 解码(自研流式读取器)
# --------------------------------------------------------------------------


def read_exact(sock, n: int) -> bytes:
    """从阻塞 socket 精确读取 ``n`` 字节,中途断开则抛 :class:`ConnectionClosed`。"""
    if n == 0:
        return b""
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            raise ConnectionClosed(None, "peer closed the transport")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(sock, max_payload: int = DEFAULT_MAX_PAYLOAD) -> Frame:
    """从 socket 读取并解码一个完整帧。

    服务端发往客户端的帧按 RFC 必须**不**带掩码;若出现掩码则视为协议违规。
    """
    header = read_exact(sock, 2)
    b0, b1 = header[0], header[1]

    fin = bool(b0 & 0x80)
    rsv1 = bool(b0 & 0x40)
    rsv2 = bool(b0 & 0x20)
    rsv3 = bool(b0 & 0x10)
    opcode = b0 & 0x0F

    if rsv1 or rsv2 or rsv3:
        raise ProtocolError("RSV bits must be 0 without negotiated extensions")
    if opcode not in DATA_OPCODES and opcode not in CONTROL_OPCODES:
        raise ProtocolError(f"unknown opcode 0x{opcode:x}")

    masked = bool(b1 & 0x80)
    length = b1 & 0x7F

    if length == 126:
        length = struct.unpack("!H", read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", read_exact(sock, 8))[0]
        if length >> 63:
            raise ProtocolError("most significant bit of 64-bit length must be 0")

    if opcode in CONTROL_OPCODES:
        if not fin:
            raise ProtocolError("control frames must not be fragmented")
        if length > MAX_CONTROL_PAYLOAD:
            raise ProtocolError("control frame payload exceeds 125 bytes")
    if length > max_payload:
        raise PayloadTooLargeError(
            f"payload of {length} bytes exceeds limit of {max_payload} bytes"
        )

    key = read_exact(sock, 4) if masked else b""
    payload = read_exact(sock, length) if length else b""
    if masked:
        payload = apply_mask(payload, key)

    if opcode == OP_TEXT and fin and payload:
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError:
            raise ProtocolError("text frame contains invalid UTF-8")

    return Frame(opcode=opcode, payload=payload, fin=fin, rsv1=rsv1, rsv2=rsv2, rsv3=rsv3)


class MessageAssembler:
    """分片消息重组器:把 continuation 帧序列拼成一条完整消息。"""

    def __init__(self, max_payload: int = DEFAULT_MAX_PAYLOAD):
        self.max_payload = max_payload
        self._opcode: Optional[int] = None
        self._buffer = bytearray()

    @property
    def in_fragments(self) -> bool:
        return self._opcode is not None

    def feed(self, frame: Frame) -> Optional[Frame]:
        """喂入一帧,若一条完整消息结束则返回合并后的 :class:`Frame`,否则返回 ``None``。"""
        if frame.opcode == OP_CONTINUATION:
            if self._opcode is None:
                raise ProtocolError("unexpected continuation frame")
            self._buffer.extend(frame.payload)
            if len(self._buffer) > self.max_payload:
                raise PayloadTooLargeError("fragmented message exceeds payload limit")
            if frame.fin:
                merged = Frame(opcode=self._opcode, payload=bytes(self._buffer), fin=True)
                self._opcode = None
                self._buffer = bytearray()
                return merged
            return None

        if self._opcode is not None:
            raise ProtocolError("expected continuation frame within fragmented message")

        if frame.fin:
            return frame

        # 数据帧起始分片
        self._opcode = frame.opcode
        self._buffer = bytearray(frame.payload)
        return None
