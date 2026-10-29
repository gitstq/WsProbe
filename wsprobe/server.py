"""内置 WebSocket 回显/推送服务端(同样基于自研协议栈实现)。

提供这个服务端有三个目的:

1. 让用户在没有现成 WebSocket 服务时,一条命令即可体验 WsProbe;
2. 作为端到端测试的靶机(握手、掩码、分片、心跳、关闭握手全覆盖);
3. 演示**服务端侧**的帧解码(客户端帧必须带掩码,服务端帧不带掩码)。

支持并发连接、固定延迟模拟、定时推送(pump)与广播模式。
"""

from __future__ import annotations

import json
import socket
import struct
import threading
import time
from typing import Dict, List, Optional, Set

from . import handshake as hs
from .frame import (
    OP_BINARY,
    OP_CLOSE,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    ConnectionClosed,
    MessageAssembler,
    ProtocolError,
    decode_close_payload,
    encode_frame,
    read_frame,
)


def _parse_request(buffer: bytes):
    """解析 HTTP 请求行与请求头(服务端视角)。

    与 :func:`wsprobe.handshake.parse_http_response` 的区别在于首行是
    ``GET /path HTTP/1.1`` 形式的**请求行**,而非状态行。
    """
    head, _, _ = buffer.partition(b"\r\n\r\n")
    text = head.decode("iso-8859-1", "replace")
    lines = text.split("\r\n")
    parts = lines[0].split(" ") if lines else []
    method = parts[0] if parts else ""
    path = parts[1] if len(parts) > 1 else "/"
    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return method, path, headers


class ClientConnection:
    """单个已握手的客户端连接。"""

    def __init__(self, sock: socket.socket, address, server: "WsEchoServer"):
        self.sock = sock
        self.address = address
        self.server = server
        self.method = "GET"
        self.path = "/"
        self.headers: Dict[str, str] = {}
        self.alive = True
        self._assembler = MessageAssembler()

    # -- 握手 -----------------------------------------------------------

    def handshake(self) -> bool:
        try:
            buffer = hs._recv_headers(self.sock)
            method, path, headers = _parse_request(buffer)
            self.method = method
            self.path = path
            self.headers = headers
            key = headers.get("sec-websocket-key")
            if headers.get("upgrade", "").lower() != "websocket" or not key:
                self._reject(400, "Bad Request")
                return False
            accept = hs.compute_accept(key)
            protocol = headers.get("sec-websocket-protocol", "")
            lines = [
                "HTTP/1.1 101 Switching Protocols",
                "Upgrade: websocket",
                "Connection: Upgrade",
                f"Sec-WebSocket-Accept: {accept}",
            ]
            if protocol:
                # 简单起见回显客户端请求的第一个子协议
                lines.append(f"Sec-WebSocket-Protocol: {protocol.split(',')[0].strip()}")
            self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
            return True
        except (OSError, ProtocolError):
            return False

    def _reject(self, status: int, reason: str) -> None:
        body = f"{status} {reason}".encode()
        try:
            self.sock.sendall(
                f"HTTP/1.1 {status} {reason}\r\nContent-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n".encode() + body
            )
        except OSError:
            pass

    # -- 收发 -----------------------------------------------------------

    def send(self, payload: bytes, opcode: int = OP_TEXT) -> None:
        # 服务端发往客户端的帧不带掩码
        self.sock.sendall(encode_frame(payload, opcode=opcode, fin=True, mask=False))

    def send_json(self, obj) -> None:
        self.send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), OP_TEXT)

    def serve(self) -> None:
        try:
            while self.alive:
                frame = read_frame(self.sock)
                if frame.opcode == OP_PING:
                    self.sock.sendall(encode_frame(frame.payload, OP_PONG, mask=False))
                    continue
                if frame.opcode == OP_CLOSE:
                    code, reason = decode_close_payload(frame.payload)
                    self.sock.sendall(
                        encode_frame(_close_body(code or 1000), OP_CLOSE, mask=False)
                    )
                    self.server.log(f"{self.address} closed: {code} {reason}")
                    break
                merged = self._assembler.feed(frame)
                if merged is None:
                    continue
                self.server.on_message(self, merged.opcode, merged.payload)
        except (OSError, ConnectionClosed, ProtocolError):
            pass
        finally:
            self.alive = False
            self.server.unregister(self)
            try:
                self.sock.close()
            except OSError:
                pass


def _close_body(code: int) -> bytes:
    return struct.pack("!H", code)


class WsEchoServer:
    """多线程 WebSocket 回显服务端。"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        delay: float = 0.0,
        pump_interval: float = 0.0,
        broadcast: bool = False,
        verbose: bool = True,
    ):
        self.host = host
        self.port = port
        self.delay = delay
        self.pump_interval = pump_interval
        self.broadcast = broadcast
        self.verbose = verbose
        self._sock: Optional[socket.socket] = None
        self._clients: Set[ClientConnection] = set()
        self._lock = threading.Lock()
        self._pump_counter = 0

    # -- 客户端管理 -----------------------------------------------------

    def register(self, conn: ClientConnection) -> None:
        with self._lock:
            self._clients.add(conn)

    def unregister(self, conn: ClientConnection) -> None:
        with self._lock:
            self._clients.discard(conn)

    def broadcast(self, payload: bytes, opcode: int = OP_TEXT) -> None:
        with self._lock:
            targets = list(self._clients)
        for conn in targets:
            try:
                conn.send(payload, opcode)
            except OSError:
                self.unregister(conn)

    def log(self, text: str) -> None:
        if self.verbose:
            print(f"[server] {text}", flush=True)

    # -- 消息处理 -------------------------------------------------------

    def on_message(self, conn: ClientConnection, opcode: int, payload: bytes) -> None:
        if self.delay > 0:
            time.sleep(self.delay)
        if self.broadcast:
            self.broadcast(payload, opcode)
            self.log(f"broadcast {len(payload)}B to {len(self._clients)} client(s)")
            return
        # 默认回显:把原样内容发回,并附带服务端元信息便于调试
        if opcode == OP_TEXT:
            text = payload.decode("utf-8", "replace")
            self.log(f"{conn.address} -> {text[:120]}")
            conn.send(payload, OP_TEXT)
        else:
            self.log(f"{conn.address} -> binary {len(payload)}B")
            conn.send(payload, OP_BINARY)

    # -- 推送线程 -------------------------------------------------------

    def _pump_loop(self) -> None:
        while True:
            time.sleep(self.pump_interval)
            self._pump_counter += 1
            message = {
                "type": "pump",
                "seq": self._pump_counter,
                "ts": round(time.time(), 3),
                "value": round((self._pump_counter * 37) % 100 / 3, 2),
            }
            raw = json.dumps(message).encode("utf-8")
            with self._lock:
                targets = list(self._clients)
            for conn in targets:
                try:
                    conn.send(raw, OP_TEXT)
                except OSError:
                    self.unregister(conn)

    # -- 主循环 ---------------------------------------------------------

    def serve_forever(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(64)
        self.log(f"listening on ws://{self.host}:{self.port} (Ctrl+C to stop)")
        if self.pump_interval > 0:
            threading.Thread(target=self._pump_loop, daemon=True).start()
        try:
            while True:
                client, address = self._sock.accept()
                conn = ClientConnection(client, address, self)
                if conn.handshake():
                    self.register(conn)
                    self.log(f"{address} connected (path={conn.path})")
                    threading.Thread(target=conn.serve, daemon=True).start()
                else:
                    client.close()
        except (KeyboardInterrupt, OSError):
            # OSError:监听 socket 被 shutdown() 关闭(测试/程序退出时的正常路径)
            self.log("shutting down")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        with self._lock:
            clients = list(self._clients)
        for conn in clients:
            conn.alive = False
            try:
                conn.sock.close()
            except OSError:
                pass
        if self._sock:
            self._sock.close()
            self._sock = None
