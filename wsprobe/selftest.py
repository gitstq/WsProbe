"""端到端自检:用内置服务端验证自研协议栈的各个环节。

覆盖:握手与 Accept 校验、文本/二进制往返、大负载(扩展长度)、
客户端分片发送、PING/PONG 往返时延、服务端 PING 自动回应、关闭握手。

用法::

    wsprobe selftest
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from typing import List, Tuple

from . import handshake as hs
from .client import WebSocketClient
from .filters import MessageFilter
from .frame import apply_mask
from .server import WsEchoServer

PASS_MARK = "✓"
FAIL_MARK = "✗"


def _free_port() -> int:
    """向操作系统申请一个空闲端口。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def run_selftest(palette=None, verbose: bool = True) -> int:
    """运行全部自检用例,返回进程退出码(0 全通过)。"""
    port = _free_port()
    server = WsEchoServer(host="127.0.0.1", port=port, verbose=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)

    url = f"ws://127.0.0.1:{port}"
    results: List[Tuple[str, bool, str]] = []

    def check(name: str, func) -> None:
        try:
            detail = func()
            results.append((name, True, detail or ""))
        except Exception as exc:  # noqa: BLE001 - 自检需要捕获一切
            results.append((name, False, f"{type(exc).__name__}: {exc}"))

    # 1. 握手
    def _handshake() -> str:
        with WebSocketClient(url, timeout=5) as ws:
            report = ws.handshake_report()
            assert report["status"] == 101, f"status={report['status']}"
            assert report["negotiated"]["accept_valid"], "accept 校验失败"
            return f"HTTP 101, accept 校验通过"

    # 2. 文本往返
    def _text() -> str:
        with WebSocketClient(url, timeout=5) as ws:
            ws.send_text("hello wsprobe")
            echoed = ws.recv(timeout=5)
            assert echoed.text == "hello wsprobe", f"got {echoed.text!r}"
            return f"回显一致 ({echoed.size}B)"

    # 3. 二进制往返
    def _binary() -> str:
        payload = bytes(range(256))
        with WebSocketClient(url, timeout=5) as ws:
            ws.send_binary(payload)
            echoed = ws.recv(timeout=5)
            assert echoed.data == payload, "二进制内容不一致"
            return f"{len(payload)}B 二进制一致"

    # 4. 大负载(触发 16bit/64bit 扩展长度)
    def _large() -> str:
        payload = "A" * 70000
        with WebSocketClient(url, timeout=10) as ws:
            ws.send_text(payload)
            echoed = ws.recv(timeout=10)
            assert len(echoed.data) == len(payload), f"{len(echoed.data)} != {len(payload)}"
            return f"{len(payload)}B 扩展长度编码正确"

    # 5. 客户端分片
    def _fragment() -> str:
        with WebSocketClient(url, timeout=5) as ws:
            ws.send_fragmented([b"frag-", b"ment-", b"ok"])
            echoed = ws.recv(timeout=5)
            assert echoed.text == "frag-ment-ok", f"got {echoed.text!r}"
            return "三片重组为 'frag-ment-ok'"

    # 6. PING/PONG
    def _ping() -> str:
        with WebSocketClient(url, timeout=5) as ws:
            rtt = ws.ping(timeout=5)
            assert rtt is not None, "PING 未收到 PONG"
            return f"RTT {rtt * 1000:.2f} ms"

    # 7. 关闭握手
    def _close() -> str:
        ws = WebSocketClient(url, timeout=5)
        ws.connect()
        ws.close(code=1000, reason="selftest")
        assert ws.close_code is not None, "未收到服务端 close 帧"
        return f"close code={ws.close_code}"

    # 8. 掩码可逆性
    def _mask() -> str:
        data = os.urandom(37)
        key = os.urandom(4)
        assert apply_mask(apply_mask(data, key), key) == data, "掩码非自反"
        return "XOR 掩码自反性正确"

    # 9. Accept 计算(RFC 6455 附录示例向量)
    def _accept_vector() -> str:
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        assert hs.compute_accept(key) == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
        return "RFC 6455 示例向量匹配"

    # 10. 过滤器
    def _filter() -> str:
        matcher = MessageFilter("data.items[*].price > 10")
        sample = {"data": {"items": [{"price": 5}, {"price": 42}]}}
        assert matcher.match(sample), "通配符 + 比较未命中"
        return "路径/通配符/比较表达式正常"

    check("HTTP Upgrade 握手", _handshake)
    check("文本消息往返", _text)
    check("二进制消息往返", _binary)
    check("扩展长度负载(70KB)", _large)
    check("客户端分片发送", _fragment)
    check("PING/PONG 心跳", _ping)
    check("关闭握手", _close)
    check("掩码可逆性", _mask)
    check("Sec-WebSocket-Accept 向量", _accept_vector)
    check("过滤表达式", _filter)

    server.shutdown()

    passed = sum(1 for _, ok, _ in results if ok)
    if verbose:
        print("WsProbe 协议自检")
        print("-" * 56)
        for name, ok, detail in results:
            mark = PASS_MARK if ok else FAIL_MARK
            print(f"  {mark} {name:<28} {detail}")
        print("-" * 56)
        print(f"  共 {len(results)} 项,通过 {passed},失败 {len(results) - passed}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_selftest())
