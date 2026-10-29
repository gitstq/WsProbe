"""会话录制与回放:把 WebSocket 流量落盘为 JSONL,并可原速/加速重放。

录制文件每行是一条 JSON 记录(``ts`` / ``dir`` / ``op`` / ``size`` / ``data``),
便于用 ``jq``、文本编辑器或任何日志系统处理。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .client import Message, WebSocketClient


class Recorder:
    """把消息追加写入 JSONL 文件。"""

    def __init__(self, path: Optional[str], enabled: bool = True):
        self.path = path
        self.enabled = bool(path) and enabled
        self._handle = None
        self._first = True
        if self.enabled:
            # 以追加模式打开,避免覆盖历史会话
            self._handle = open(path, "a", encoding="utf-8")

    def write_meta(self, meta: Dict[str, Any]) -> None:
        """写入会话元信息行(``_meta`` 类型)。"""
        if not self.enabled or self._handle is None:
            return
        record = {"type": "_meta", "ts": time.time(), **meta}
        self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write(self, message: Message) -> None:
        if not self.enabled or self._handle is None:
            return
        self._handle.write(json.dumps(message.to_record(), ensure_ascii=False) + "\n")

    def flush(self) -> None:
        if self._handle is not None:
            self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def load_records(path: str) -> List[Dict[str, Any]]:
    """读取 JSONL 录制文件,跳过元信息行与坏行。"""
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") == "_meta":
                continue
            records.append(record)
    return records


def replay(
    url: str,
    records: Iterable[Dict[str, Any]],
    speed: float = 1.0,
    direction: str = "out",
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    verbose: bool = True,
) -> Dict[str, Any]:
    """把录制中指定方向的消息重放到目标地址。

    :param speed: 倍速;``speed <= 0`` 表示不做等待(全速重放)
    :return: 重放结果统计
    """
    records = list(records)
    sent = 0
    errors = 0
    with WebSocketClient(url, headers=headers, timeout=timeout) as ws:
        base_ts: Optional[float] = None
        for record in records:
            if direction != "any" and record.get("dir") != direction:
                continue
            ts = float(record.get("ts", 0) or 0)
            if base_ts is None:
                base_ts = ts
            if speed > 0 and base_ts is not None:
                delay = (ts - base_ts) / speed
                if delay > 0:
                    time.sleep(min(delay, 60.0))
            data = record.get("data", "")
            try:
                if record.get("op") == "binary":
                    ws.send_binary(bytes.fromhex(data))
                else:
                    ws.send_text(data)
                sent += 1
                if verbose:
                    print(f"[replay ->] {str(data)[:120]}")
            except Exception as exc:  # noqa: BLE001 - 单条失败不应中断整体回放
                errors += 1
                if verbose:
                    print(f"[replay ! ] {exc}")
    return {"sent": sent, "errors": errors, "total": len(records)}


def iter_preview(path: str, limit: int = 20) -> Iterator[str]:
    """生成录制文件的可读预览行。"""
    for index, record in enumerate(load_records(path)):
        if index >= limit:
            yield f"... (共 {limit}+ 条,已截断)"
            return
        arrow = "->" if record.get("dir") == "out" else "<-"
        data = str(record.get("data", ""))
        yield f"[{record.get('ts')}] {arrow} ({record.get('size')}B) {data[:160]}"
