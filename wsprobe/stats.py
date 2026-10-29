"""会话统计:吞吐、字节量、往返延迟分位数。

所有计算仅依赖标准库,不使用 numpy 等重型依赖。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def percentile(values: List[float], pct: float) -> Optional[float]:
    """线性插值分位数计算(最近秩法的平滑版本)。

    :param values: 已排序的数值列表
    :param pct: 0-100 之间的百分位
    """
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = (pct / 100.0) * (len(values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    weight = rank - lower
    return values[lower] * (1 - weight) + values[upper] * weight


@dataclass
class SessionStats:
    """一次 WebSocket 会话的计数器集合。"""

    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    messages_received: int = 0
    messages_sent: int = 0
    bytes_received: int = 0
    bytes_sent: int = 0
    text_frames: int = 0
    binary_frames: int = 0
    pings_sent: int = 0
    pongs_received: int = 0
    pings_received: int = 0
    rtt_samples: List[float] = field(default_factory=list)
    errors: int = 0

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------

    def record_received(self, opcode: int, size: int) -> None:
        self.messages_received += 1
        self.bytes_received += size
        if opcode == 0x1:
            self.text_frames += 1
        elif opcode == 0x2:
            self.binary_frames += 1

    def record_sent(self, size: int) -> None:
        self.messages_sent += 1
        self.bytes_sent += size

    def record_rtt(self, seconds: float) -> None:
        self.rtt_samples.append(seconds)

    def record_error(self) -> None:
        self.errors += 1

    def finish(self) -> None:
        if self.end_time is None:
            self.end_time = time.time()

    # ------------------------------------------------------------------
    # 派生指标
    # ------------------------------------------------------------------

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return max(end - self.start_time, 1e-9)

    @property
    def messages_per_second(self) -> float:
        return self.messages_received / self.duration

    @property
    def sorted_rtt(self) -> List[float]:
        return sorted(self.rtt_samples)

    def rtt_percentile(self, pct: float) -> Optional[float]:
        return percentile(self.sorted_rtt, pct)

    def to_dict(self) -> Dict[str, object]:
        """生成可 JSON 序列化的统计快照。"""
        samples = self.sorted_rtt
        return {
            "duration_seconds": round(self.duration, 4),
            "messages_received": self.messages_received,
            "messages_sent": self.messages_sent,
            "bytes_received": self.bytes_received,
            "bytes_sent": self.bytes_sent,
            "text_frames": self.text_frames,
            "binary_frames": self.binary_frames,
            "pings_sent": self.pings_sent,
            "pongs_received": self.pongs_received,
            "pings_received": self.pings_received,
            "messages_per_second": round(self.messages_per_second, 3),
            "rtt_samples": len(samples),
            "rtt_min_ms": _ms(samples[0]) if samples else None,
            "rtt_p50_ms": _ms(percentile(samples, 50)) if samples else None,
            "rtt_p95_ms": _ms(percentile(samples, 95)) if samples else None,
            "rtt_p99_ms": _ms(percentile(samples, 99)) if samples else None,
            "rtt_max_ms": _ms(samples[-1]) if samples else None,
            "errors": self.errors,
        }


def _ms(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value * 1000.0, 3)
