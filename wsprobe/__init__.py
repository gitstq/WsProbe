"""WsProbe —— 零依赖 WebSocket 调试探针。

WsProbe 是一个**纯 Python 标准库**实现的 WebSocket(RFC 6455)调试工具集,
不依赖 ``websockets`` / ``websocket-client`` / ``aiohttp`` 等任何第三方库。

核心能力:

* 自研协议栈:帧编解码、掩码、分片重组、握手、心跳、关闭握手
* CLI 探针:连接、发送、过滤、录制、回放、脚本化、压测
* 库调用:``WebSocketClient`` 可直接嵌入你自己的程序

快速示例::

    from wsprobe import WebSocketClient

    with WebSocketClient("ws://localhost:8765") as ws:
        ws.send_text("hello")
        print(ws.recv().text)
"""

from __future__ import annotations

from .client import Message, WebSocketClient
from .filters import MessageFilter
from .frame import (
    CLOSE_NORMAL,
    OP_BINARY,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    ConnectionClosed,
    Frame,
    ProtocolError,
    WebSocketError,
)
from .stats import SessionStats

__version__ = "1.0.0"
__all__ = [
    "__version__",
    "WebSocketClient",
    "Message",
    "MessageFilter",
    "SessionStats",
    "Frame",
    "WebSocketError",
    "ProtocolError",
    "ConnectionClosed",
    "OP_TEXT",
    "OP_BINARY",
    "OP_PING",
    "OP_PONG",
    "CLOSE_NORMAL",
]
