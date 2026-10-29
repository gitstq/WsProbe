"""WsProbe 命令行入口。

命令一览::

    wsprobe ws://host/path --send '{"cmd":"ping"}' --count 5
    wsprobe inspect wss://echo.websocket.org
    wsprobe bench ws://localhost:8765 --connections 20 --messages 200
    wsprobe script examples/script.json
    wsprobe replay session.jsonl --to ws://localhost:8765
    wsprobe serve --port 8765 --pump 1
    wsprobe selftest
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import socket
import sys
import time
from typing import Any, Dict, List, Optional

from . import __version__
from .client import Message, WebSocketClient
from .filters import MessageFilter
from .script import run_script, load_script
from .server import WsEchoServer
from .session import Recorder, iter_preview, load_records, replay

# ----------------------------------------------------------------------
# 终端着色(无 TTY 或 --no-color 时自动降级为纯文本)
# ----------------------------------------------------------------------

_COLORS = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "magenta": "\033[35m",
    "blue": "\033[34m",
}


class Palette:
    """按开关决定是否输出 ANSI 颜色。"""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def paint(self, text: str, color: str) -> str:
        if not self.enabled:
            return text
        return f"{_COLORS.get(color, '')}{text}{_COLORS['reset']}"


def default_color_enabled() -> bool:
    return sys.stdout.isatty() and sys.platform != "win32"


# ----------------------------------------------------------------------
# 参数解析
# ----------------------------------------------------------------------

COMMANDS = {"inspect", "bench", "script", "replay", "serve", "selftest", "connect", "help"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wsprobe",
        description="WsProbe — 零依赖 WebSocket 调试探针(RFC 6455 自研协议栈)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  wsprobe serve --port 8765             # 启动内置回显服务器\n"
            "  wsprobe ws://127.0.0.1:8765 --send hi # 连接并发送\n"
            "  wsprobe ws://127.0.0.1:8765 --filter '$.seq > 3'\n"
            "  wsprobe inspect wss://127.0.0.1:8765 --insecure\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"WsProbe {__version__}")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    sub = parser.add_subparsers(dest="command")

    # ---- connect(默认) ----
    c = sub.add_parser("connect", help="连接 WebSocket 并收发消息", add_help=True)
    _connect_args(c)
    sub_connect_alias = sub.add_parser("listen", help="connect 的别名")
    _connect_args(sub_connect_alias)

    # ---- inspect ----
    i = sub.add_parser("inspect", help="只做握手并输出诊断报告")
    i.add_argument("url")
    _common_net_args(i)
    i.add_argument("--json", action="store_true", help="以 JSON 输出")

    # ---- bench ----
    b = sub.add_parser("bench", help="并发压测与延迟统计")
    b.add_argument("url")
    _common_net_args(b)
    b.add_argument("--connections", type=int, default=10, help="并发连接数(默认 10)")
    b.add_argument("--messages", type=int, default=100, help="每连接消息数(默认 100)")
    b.add_argument("--payload", type=int, default=64, help="每条消息字节数(默认 64)")
    b.add_argument("--json", action="store_true", help="以 JSON 输出")

    # ---- script ----
    s = sub.add_parser("script", help="执行声明式交互脚本")
    s.add_argument("file")
    s.add_argument("--url", help="覆盖脚本中的 url")
    s.add_argument("--header", action="append", default=[], help="附加请求头 K: V")
    s.add_argument("--timeout", type=float, default=10.0)
    s.add_argument("--json", action="store_true", help="以 JSON 输出")

    # ---- replay ----
    r = sub.add_parser("replay", help="回放录制文件")
    r.add_argument("file")
    r.add_argument("--to", dest="url", required=True, help="目标 WebSocket 地址")
    r.add_argument("--speed", type=float, default=1.0, help="倍速,<=0 表示全速(默认 1.0)")
    r.add_argument("--direction", choices=["out", "in", "any"], default="out")
    r.add_argument("--header", action="append", default=[], help="附加请求头 K: V")
    r.add_argument("--timeout", type=float, default=10.0)
    r.add_argument("--preview", action="store_true", help="只预览录制内容,不真正发送")

    # ---- serve ----
    v = sub.add_parser("serve", help="启动内置回显/推送服务器")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8765)
    v.add_argument("--delay", type=float, default=0.0, help="每条消息回显前延迟(秒)")
    v.add_argument("--pump", type=float, default=0.0, help="定时推送间隔(秒),0 关闭")
    v.add_argument("--broadcast", action="store_true", help="广播模式")
    v.add_argument("--quiet", action="store_true")

    # ---- selftest ----
    sub.add_parser("selftest", help="运行内置协议自检")

    return parser


def _connect_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url", help="WebSocket 地址(ws:// 或 wss://,可省略 scheme)")
    _common_net_args(parser)
    parser.add_argument("--send", action="append", default=[], help="连接后发送的文本(可重复)")
    parser.add_argument("--send-file", help="从文件读取内容发送")
    parser.add_argument("--send-interval", type=float, default=0.0, help="多条发送之间的间隔")
    parser.add_argument("--count", type=int, help="接收 N 条消息后退出")
    parser.add_argument("--duration", type=float, help="运行 N 秒后退出")
    parser.add_argument("--filter", dest="filter_expr", help="消息过滤表达式")
    parser.add_argument("--record", help="把会话录制为 JSONL 文件")
    parser.add_argument("--stats", action="store_true", help="结束时输出统计报告")
    parser.add_argument("--json", action="store_true", help="以 JSON Lines 输出消息")
    parser.add_argument("--hex", action="store_true", help="二进制消息以十六进制展示")
    parser.add_argument("--hex-dump", action="store_true", help="以 hexdump 形式展示二进制")
    parser.add_argument("--quiet", action="store_true", help="只输出消息体,不输出提示")
    parser.add_argument("--repl", action="store_true", help="强制进入交互模式")
    parser.add_argument("--no-repl", action="store_true", help="禁止交互模式")
    parser.add_argument("--ping-interval", type=float, default=0.0, help="心跳间隔(秒)")


def _common_net_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--header", action="append", default=[], help="自定义请求头 K: V(可重复)")
    parser.add_argument("--subprotocol", action="append", default=[], help="Sec-WebSocket-Protocol")
    parser.add_argument("--proxy", help="HTTP CONNECT 代理,如 http://127.0.0.1:7890")
    parser.add_argument("--timeout", type=float, default=10.0, help="超时秒数(默认 10)")
    parser.add_argument("--max-payload", type=int, default=64 * 1024 * 1024, help="单消息上限字节")
    parser.add_argument("--insecure", action="store_true", help="跳过 TLS 证书校验")
    parser.add_argument("--no-auto-pong", action="store_true", help="不自动回应服务端 PING")
    parser.add_argument("--no-strict-accept", action="store_true", help="不校验 Sec-WebSocket-Accept")


def parse_headers(items: List[str]) -> Dict[str, str]:
    """把 ``"K: V"`` 形式的多组参数解析为字典。"""
    headers: Dict[str, str] = {}
    for item in items or []:
        if ":" not in item:
            raise SystemExit(f"错误:请求头格式应为 'K: V',收到 {item!r}")
        name, _, value = item.partition(":")
        headers[name.strip()] = value.strip()
    return headers


def normalize_argv(argv: List[str]) -> List[str]:
    """参数归一化:支持两种便利写法。

    1. 省略子命令:``wsprobe ws://host`` 等价于 ``wsprobe connect ws://host``
    2. 全局开关可出现在任意位置:``wsprobe inspect URL --no-color``
    """
    if not argv:
        return argv
    # 把全局开关提到最前,argparse 才会在顶层解析器中识别它们
    flags = [item for item in argv if item == "--no-color"]
    rest = [item for item in argv if item != "--no-color"]
    if not rest:
        return flags
    # 判断是否省略了子命令时,要看"第一个非全局开关"的参数
    first = rest[0]
    if first in COMMANDS or first.startswith("-"):
        return flags + rest
    return flags + ["connect"] + rest


# ----------------------------------------------------------------------
# 命令实现
# ----------------------------------------------------------------------


def cmd_connect(args, palette: Palette) -> int:
    headers = parse_headers(args.header)
    matcher = MessageFilter(args.filter_expr or "")
    recorder = Recorder(args.record)

    ws = WebSocketClient(
        args.url,
        headers=headers,
        subprotocols=args.subprotocol or None,
        timeout=args.timeout,
        proxy=args.proxy,
        verify_tls=not args.insecure,
        max_payload=args.max_payload,
        auto_pong=not args.no_auto_pong,
        strict_accept=not args.no_strict_accept,
    )
    try:
        ws.connect()
    except Exception as exc:  # noqa: BLE001 - CLI 边界统一收敛为可读错误
        print(palette.paint(f"✗ 连接失败: {exc}", "red"), file=sys.stderr)
        return 2

    if not args.quiet and not args.json:
        _print_handshake_summary(ws, palette)
    recorder.write_meta(ws.handshake_report())

    outgoing: List[str] = list(args.send or [])
    if args.send_file:
        try:
            with open(args.send_file, "r", encoding="utf-8") as handle:
                outgoing.append(handle.read())
        except OSError as exc:
            print(palette.paint(f"✗ 读取 --send-file 失败: {exc}", "red"), file=sys.stderr)

    exit_code = 0
    stop_at = time.time() + args.duration if args.duration else None
    last_ping = time.time()
    try:
        if outgoing:
            for index, payload in enumerate(outgoing):
                if args.send_interval > 0 and index:
                    time.sleep(args.send_interval)
                message = ws.send_text(payload)
                recorder.write(message)
                if not args.quiet and not args.json:
                    print(palette.paint("→", "cyan"), message.preview(200))
                elif args.json:
                    print(json.dumps(message.to_record(), ensure_ascii=False))
        elif not args.no_repl and (args.repl or sys.stdin.isatty()):
            _run_repl(ws, palette, recorder, args)
            return 0

        received = 0
        while True:
            if args.count is not None and received >= args.count:
                break
            if stop_at is not None and time.time() >= stop_at:
                break
            if args.ping_interval > 0 and time.time() - last_ping >= args.ping_interval:
                ws.ping(timeout=args.timeout)
                last_ping = time.time()
            try:
                window = args.timeout
                if stop_at is not None:
                    window = min(window, max(stop_at - time.time(), 0.05))
                message = ws.recv(timeout=window)
            except socket.timeout:
                if stop_at is not None and time.time() >= stop_at:
                    break
                if args.count is None and args.duration is None:
                    # 没有显式终止条件时,空闲超时即退出,避免永久挂起
                    break
                continue
            recorder.write(message)
            if matcher.match(message):
                received += 1
                _emit_message(message, palette, args)
    except KeyboardInterrupt:
        if not args.quiet:
            print(palette.paint("\n⏹ 已中断", "yellow"), file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(palette.paint(f"✗ {exc}", "red"), file=sys.stderr)
        exit_code = 1
    finally:
        ws.stats.finish()
        recorder.close()
        if args.stats:
            print(json.dumps(ws.stats.to_dict(), ensure_ascii=False, indent=2))
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass
    return exit_code


def _print_handshake_summary(ws: WebSocketClient, palette: Palette) -> None:
    report = ws.handshake_report()
    ok = report["negotiated"].get("accept_valid")
    mark = palette.paint("✓", "green") if ok else palette.paint("!", "yellow")
    print(
        f"{mark} {palette.paint('HTTP ' + str(report['status']), 'bold')} "
        f"{report['reason']} · {report['host']}:{report['port']} "
        f"{palette.paint('(' + report['resolved_ip'] + ')', 'dim')}"
    )
    if report["negotiated"].get("protocol"):
        print(f"  子协议: {report['negotiated']['protocol']}")
    if report["negotiated"].get("extensions"):
        print(f"  扩展: {report['negotiated']['extensions']}")


def _emit_message(message: Message, palette: Palette, args) -> None:
    if args.json:
        print(json.dumps(message.to_record(), ensure_ascii=False), flush=True)
        return
    stamp = time.strftime("%H:%M:%S", time.localtime(message.timestamp))
    head = palette.paint(f"[{stamp}]", "dim") + " " + palette.paint("←", "magenta")
    if message.is_binary and not args.hex:
        body = f"<binary {message.size}B>" + (f" {message.data[:24].hex()}" if args.hex else "")
        print(f"{head} {palette.paint(body, 'yellow')}", flush=True)
        return
    if args.hex or args.hex_dump:
        print(f"{head} {_hexdump(message.data) if args.hex_dump else message.data.hex()}", flush=True)
        return
    print(f"{head} {message.preview(4096)}", flush=True)


def _hexdump(data: bytes, width: int = 16) -> str:
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset:08x}  {hexpart:<{width * 3}}  |{ascii_part}|")
    return "\n" + "\n".join(lines)


def _run_repl(ws: WebSocketClient, palette: Palette, recorder: Recorder, args) -> None:
    """交互式会话:输入即发送,内置 /ping /json /quit 等命令。"""
    print(
        palette.paint("交互模式已启动:", "bold"),
        palette.paint("直接输入发送;/ping 测延迟;/quit 退出", "dim"),
    )
    while True:
        try:
            line = input(palette.paint("ws> ", "cyan"))
        except (EOFError, KeyboardInterrupt):
            print()
            break
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in ("/quit", "/exit", "/q"):
            break
        if stripped == "/ping":
            rtt = ws.ping(timeout=args.timeout)
            shown = "超时" if rtt is None else f"{rtt * 1000:.2f} ms"
            print(palette.paint(f"RTT: {shown}", "green"))
            continue
        if stripped == "/stats":
            ws.stats.finish()
            print(json.dumps(ws.stats.to_dict(), ensure_ascii=False, indent=2))
            continue
        if stripped.startswith("/wait"):
            parts = stripped.split()
            seconds = float(parts[1]) if len(parts) > 1 else 1.0
            deadline = time.time() + seconds
            while time.time() < deadline:
                try:
                    message = ws.recv(timeout=max(deadline - time.time(), 0.05))
                except socket.timeout:
                    break
                recorder.write(message)
                _emit_message(message, palette, args)
            continue
        try:
            ws.send_text(stripped)
        except OSError as exc:
            print(palette.paint(f"✗ 发送失败: {exc}", "red"))
            break
        # 等待一条回显(不阻塞太久)
        try:
            message = ws.recv(timeout=min(args.timeout, 2.0))
            recorder.write(message)
            _emit_message(message, palette, args)
        except socket.timeout:
            pass


def cmd_inspect(args, palette: Palette) -> int:
    ws = WebSocketClient(
        args.url,
        headers=parse_headers(args.header),
        subprotocols=args.subprotocol or None,
        timeout=args.timeout,
        proxy=args.proxy,
        verify_tls=not args.insecure,
        strict_accept=not args.no_strict_accept,
    )
    try:
        ws.connect()
    except Exception as exc:  # noqa: BLE001
        print(palette.paint(f"✗ 握手失败: {exc}", "red"), file=sys.stderr)
        return 2
    report = ws.handshake_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        valid = report["negotiated"].get("accept_valid")
        print(palette.paint(f"HTTP {report['status']} {report['reason']}", "bold"))
        print(f"  目标    : {report['url']}")
        print(f"  解析 IP : {report['resolved_ip']}")
        print(f"  请求 Key: {report['request_key']}")
        print(f"  预期 Acc: {report['expected_accept']}")
        print(
            f"  Accept  : {report['negotiated'].get('accept')} "
            + palette.paint("(校验通过)" if valid else "(校验失败)", "green" if valid else "red")
        )
        if report["headers"]:
            print("  响应头  :")
            for key, value in report["headers"].items():
                print(f"    {key}: {value}")
    try:
        rtt = ws.ping(timeout=args.timeout)
        if not args.json:
            shown = "超时" if rtt is None else f"{rtt * 1000:.2f} ms"
            print(f"  首包 RTT: {shown}")
        ws.close()
    except Exception:  # noqa: BLE001
        pass
    return 0


def _bench_worker(url: str, args, headers, messages: int) -> Dict[str, Any]:
    """单个压测连接:发送 N 条并等待回显,记录每条 RTT。"""
    latencies: List[float] = []
    errors = 0
    payload = "x" * max(args.payload, 1)
    try:
        with WebSocketClient(
            url,
            headers=headers,
            timeout=args.timeout,
            proxy=args.proxy,
            verify_tls=not args.insecure,
            max_payload=args.max_payload,
        ) as ws:
            for _ in range(messages):
                started = time.time()
                try:
                    ws.send_text(payload)
                    ws.recv(timeout=args.timeout)
                except (socket.timeout, OSError):
                    errors += 1
                    continue
                latencies.append(time.time() - started)
    except Exception:  # noqa: BLE001
        errors += messages
    return {"latencies": latencies, "errors": errors}


def cmd_bench(args, palette: Palette) -> int:
    headers = parse_headers(args.header)
    started = time.time()
    results: List[Dict[str, Any]] = []
    with futures.ThreadPoolExecutor(max_workers=args.connections) as pool:
        tasks = [
            pool.submit(_bench_worker, args.url, args, headers, args.messages)
            for _ in range(args.connections)
        ]
        for task in futures.as_completed(tasks):
            try:
                results.append(task.result())
            except Exception as exc:  # noqa: BLE001
                results.append({"latencies": [], "errors": args.messages, "error": str(exc)})
    elapsed = max(time.time() - started, 1e-9)

    all_latencies = sorted(sum((r["latencies"] for r in results), []))
    total_errors = sum(r["errors"] for r in results)
    total_ok = len(all_latencies)

    def pct(value: float) -> Optional[float]:
        if not all_latencies:
            return None
        index = min(int(value / 100 * (len(all_latencies) - 1)), len(all_latencies) - 1)
        return all_latencies[index]

    summary = {
        "url": args.url,
        "connections": args.connections,
        "messages_per_connection": args.messages,
        "payload_bytes": args.payload,
        "elapsed_seconds": round(elapsed, 3),
        "completed": total_ok,
        "errors": total_errors,
        "throughput_msg_per_s": round(total_ok / elapsed, 2),
        "latency_min_ms": round(all_latencies[0] * 1000, 3) if all_latencies else None,
        "latency_p50_ms": round(pct(50) * 1000, 3) if pct(50) is not None else None,
        "latency_p95_ms": round(pct(95) * 1000, 3) if pct(95) is not None else None,
        "latency_p99_ms": round(pct(99) * 1000, 3) if pct(99) is not None else None,
        "latency_max_ms": round(all_latencies[-1] * 1000, 3) if all_latencies else None,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(palette.paint("压测结果", "bold"))
        for key, value in summary.items():
            print(f"  {key:<24}: {value}")
    return 0 if total_errors == 0 else 1


def cmd_script(args, palette: Palette) -> int:
    try:
        script = load_script(args.file)
    except Exception as exc:  # noqa: BLE001
        print(palette.paint(f"✗ 脚本加载失败: {exc}", "red"), file=sys.stderr)
        return 2
    result = run_script(
        script,
        url=args.url,
        headers=parse_headers(args.header),
        timeout=args.timeout,
        verbose=not args.json,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "✓ 全部通过" if result["success"] else "✗ 存在失败步骤"
        print(palette.paint(status, "green" if result["success"] else "red"))
        for failure in result["failures"]:
            print(palette.paint(f"  {failure}", "red"))
        print(f"  收集消息: {result['messages_collected']}")
        print(f"  统计: {json.dumps(result['stats'], ensure_ascii=False)}")
    return 0 if result["success"] else 1


def cmd_replay(args, palette: Palette) -> int:
    if args.preview:
        for line in iter_preview(args.file, limit=50):
            print(line)
        return 0
    try:
        records = load_records(args.file)
    except OSError as exc:
        print(palette.paint(f"✗ 读取录制文件失败: {exc}", "red"), file=sys.stderr)
        return 2
    if not records:
        print(palette.paint("录制文件为空", "yellow"))
        return 0
    result = replay(
        args.url,
        records,
        speed=args.speed,
        direction=args.direction,
        headers=parse_headers(args.header),
        timeout=args.timeout,
    )
    print(palette.paint(f"✓ 重放完成: 发送 {result['sent']} 条,失败 {result['errors']} 条", "green"))
    return 0 if result["errors"] == 0 else 1


def cmd_serve(args, palette: Palette) -> int:
    server = WsEchoServer(
        host=args.host,
        port=args.port,
        delay=args.delay,
        pump_interval=args.pump,
        broadcast=args.broadcast,
        verbose=not args.quiet,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_selftest(args, palette: Palette) -> int:
    """端到端自检:启动内置服务端 -> 握手 -> 收发 -> 心跳 -> 关闭握手。"""
    from .selftest import run_selftest

    return run_selftest(palette=palette)


# ----------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = normalize_argv(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    palette = Palette(enabled=default_color_enabled() and not args.no_color)

    if args.command in (None, "help"):
        parser.print_help()
        return 0

    handlers = {
        "connect": cmd_connect,
        "listen": cmd_connect,
        "inspect": cmd_inspect,
        "bench": cmd_bench,
        "script": cmd_script,
        "replay": cmd_replay,
        "serve": cmd_serve,
        "selftest": cmd_selftest,
    }
    return handlers[args.command](args, palette)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
