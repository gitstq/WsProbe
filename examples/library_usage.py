#!/usr/bin/env python3
"""把 WsProbe 当作库使用的完整示例。

运行前置条件:另开一个终端执行 ``wsprobe serve --port 8765``。
"""

import json
import sys

from wsprobe import WebSocketClient
from wsprobe.filters import MessageFilter

URL = "ws://127.0.0.1:8765"


def demo_basic() -> None:
    """最简往返:发送文本并读取回显。"""
    with WebSocketClient(URL, timeout=5) as ws:
        ws.send_text("hello wsprobe")
        print("echo:", ws.recv(timeout=5).text)


def demo_json_and_filter() -> None:
    """发送 JSON,并用过滤表达式筛选感兴趣的消息。"""
    matcher = MessageFilter("value >= 10")
    with WebSocketClient(URL, timeout=5) as ws:
        for index in (3, 42, 7):
            ws.send_json({"seq": index, "value": index})
            message = ws.recv(timeout=5)
            if matcher.match(message):
                print("命中:", message.text)


def demo_binary_and_ping() -> None:
    """二进制帧与心跳测量。"""
    with WebSocketClient(URL, timeout=5) as ws:
        ws.send_binary(bytes(range(32)))
        message = ws.recv(timeout=5)
        print("二进制回显长度:", message.size)
        rtt = ws.ping(timeout=5)
        print("RTT(ms):", None if rtt is None else round(rtt * 1000, 3))


def demo_stats() -> None:
    """会话结束后的统计快照。"""
    with WebSocketClient(URL, timeout=5) as ws:
        for index in range(20):
            ws.send_text(f"m-{index}")
            ws.recv(timeout=5)
        ws.stats.finish()
        print(json.dumps(ws.stats.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        demo_basic()
        demo_json_and_filter()
        demo_binary_and_ping()
        demo_stats()
    except OSError as exc:
        print(f"连接失败,请先运行 `wsprobe serve --port 8765`: {exc}", file=sys.stderr)
        raise SystemExit(1)
