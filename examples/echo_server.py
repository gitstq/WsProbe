#!/usr/bin/env python3
"""独立启动 WsProbe 内置的 WebSocket 回显/推送服务器。

用法::

    python examples/echo_server.py --port 8765 --pump 1

``--pump`` 会按固定间隔主动推送 JSON 消息,便于体验订阅式推送流的调试。
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wsprobe.server import WsEchoServer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="WsProbe 内置回显服务器示例")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--delay", type=float, default=0.0, help="回显前延迟(秒)")
    parser.add_argument("--pump", type=float, default=0.0, help="定时推送间隔(秒)")
    parser.add_argument("--broadcast", action="store_true", help="广播模式")
    args = parser.parse_args()

    server = WsEchoServer(
        host=args.host,
        port=args.port,
        delay=args.delay,
        pump_interval=args.pump,
        broadcast=args.broadcast,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
