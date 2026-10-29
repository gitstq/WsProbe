"""声明式交互脚本执行器:把「发送 / 等待 / 断言」编排成可复用的流程。

脚本是纯 JSON,便于纳入 CI 做回归验证::

    {
      "url": "ws://localhost:8765",
      "steps": [
        {"action": "send",    "data": "hello"},
        {"action": "expect",  "filter": "$.type == 'ack'", "timeout": 5},
        {"action": "sleep",   "seconds": 0.5},
        {"action": "send",    "data": {"cmd": "subscribe"}},
        {"action": "wait",    "count": 3, "timeout": 10},
        {"action": "ping"},
        {"action": "close"}
      ]
    }

支持的 action:

============  ==========================================================
``send``      发送文本(``data`` 为对象时自动序列化为 JSON)
``expect``    等待一条命中 ``filter`` 的消息,超时视为失败
``wait``      等待 N 条消息(不做内容断言)
``sleep``     暂停若干秒
``ping``      发送 PING 并记录 RTT
``close``     正常关闭连接
============  ==========================================================
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .client import WebSocketClient
from .filters import MessageFilter


class ScriptError(ValueError):
    """脚本结构或执行失败。"""


SUPPORTED_ACTIONS = {"send", "expect", "wait", "sleep", "ping", "close"}


def load_script(path: str) -> Dict[str, Any]:
    """从文件加载脚本,并做基本结构校验。"""
    with open(path, "r", encoding="utf-8") as handle:
        try:
            script = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ScriptError(f"invalid JSON script: {exc}") from exc
    validate_script(script)
    return script


def validate_script(script: Dict[str, Any]) -> None:
    if not isinstance(script, dict):
        raise ScriptError("script must be a JSON object")
    steps = script.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ScriptError("script must contain a non-empty 'steps' list")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ScriptError(f"step #{index + 1} must be an object")
        action = step.get("action")
        if action not in SUPPORTED_ACTIONS:
            raise ScriptError(
                f"step #{index + 1}: unknown action {action!r}, "
                f"expected one of {sorted(SUPPORTED_ACTIONS)}"
            )


def run_script(
    script: Dict[str, Any],
    url: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    on_message=None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """执行脚本,返回结构化结果(供 CLI 打印或 CI 断言)。"""
    target = url or script.get("url")
    if not target:
        raise ScriptError("no url provided (neither --url nor script.url)")

    steps: List[Dict[str, Any]] = script["steps"]
    results: List[Dict[str, Any]] = []
    failures: List[str] = []
    collected: List[Any] = []

    ws = WebSocketClient(
        target,
        headers={**(script.get("headers") or {}), **(headers or {})},
        subprotocols=script.get("subprotocols"),
        timeout=timeout,
    )
    ws.connect()
    try:
        for index, step in enumerate(steps, start=1):
            action = step["action"]
            entry: Dict[str, Any] = {"step": index, "action": action, "ok": True}
            try:
                if action == "send":
                    data = step.get("data", "")
                    if isinstance(data, (dict, list)):
                        message = ws.send_json(data)
                    else:
                        message = ws.send_text(str(data))
                    entry["sent"] = message.preview(200)
                    if verbose:
                        print(f"[{index:>2}] -> {message.preview(160)}")

                elif action == "expect":
                    expression = step.get("filter", "")
                    matcher = MessageFilter(expression)
                    limit = float(step.get("timeout", timeout))
                    deadline = time.time() + limit
                    matched = None
                    while time.time() < deadline:
                        try:
                            message = ws.recv(timeout=max(deadline - time.time(), 0.05))
                        except (TimeoutError, OSError):
                            break
                        collected.append(message)
                        if on_message:
                            on_message(message)
                        if matcher.match(message):
                            matched = message
                            break
                        if verbose:
                            print(f"[{index:>2}] .. {message.preview(160)}")
                    if matched is None:
                        entry["ok"] = False
                        entry["error"] = f"no message matched {expression!r} within {limit}s"
                        failures.append(f"step {index}: {entry['error']}")
                    else:
                        entry["matched"] = matched.preview(200)
                        if verbose:
                            print(f"[{index:>2}] <- MATCH {matched.preview(160)}")

                elif action == "wait":
                    count = int(step.get("count", 1))
                    limit = float(step.get("timeout", timeout))
                    received = 0
                    expression = step.get("filter")
                    matcher = MessageFilter(expression) if expression else None
                    for _ in range(count):
                        try:
                            message = ws.recv(timeout=limit)
                        except (TimeoutError, OSError):
                            break
                        collected.append(message)
                        if on_message:
                            on_message(message)
                        if matcher is None or matcher.match(message):
                            received += 1
                            if verbose:
                                print(f"[{index:>2}] <- {message.preview(160)}")
                    entry["received"] = received
                    if received < count:
                        entry["ok"] = False
                        entry["error"] = f"expected {count} message(s), got {received}"
                        failures.append(f"step {index}: {entry['error']}")

                elif action == "sleep":
                    seconds = float(step.get("seconds", 1))
                    time.sleep(seconds)
                    entry["seconds"] = seconds

                elif action == "ping":
                    rtt = ws.ping(timeout=float(step.get("timeout", timeout)))
                    entry["rtt_ms"] = round(rtt * 1000, 3) if rtt else None
                    if verbose:
                        shown = entry["rtt_ms"]
                        print(f"[{index:>2}] ping -> {'timeout' if shown is None else f'{shown} ms'}")

                elif action == "close":
                    ws.close(code=int(step.get("code", 1000)), reason=step.get("reason", ""))
                    entry["closed"] = True
                    if verbose:
                        print(f"[{index:>2}] connection closed")

            except Exception as exc:  # noqa: BLE001 - 单步失败不影响后续步骤汇总
                entry["ok"] = False
                entry["error"] = str(exc)
                failures.append(f"step {index}: {exc}")
            results.append(entry)
    finally:
        if ws.connected:
            ws.close()
        ws.stats.finish()

    return {
        "url": target,
        "steps": results,
        "failures": failures,
        "success": not failures,
        "messages_collected": len(collected),
        "stats": ws.stats.to_dict(),
    }
