"""In-process API and pipeline telemetry (stdlib only)."""

from __future__ import annotations

import threading
import time
from collections import deque
from statistics import median


class Metrics:
    def __init__(self) -> None:
        self._latencies: deque[float] = deque(maxlen=1000)
        self._lock = threading.Lock()
        self.request_count = 0
        self.error_count = 0
        self.last_cycle_ms = 0.0
        self.last_cycle_at = ""
        self.process_started = time.time()

    def record(self, milliseconds: float) -> None:
        with self._lock:
            self._latencies.append(milliseconds)
            self.request_count += 1

    def record_error(self) -> None:
        with self._lock:
            self.error_count += 1

    def record_cycle(self, milliseconds: float, at: str) -> None:
        self.last_cycle_ms = round(milliseconds, 1)
        self.last_cycle_at = at

    def percentile(self, value: float) -> float:
        with self._lock:
            data = sorted(self._latencies)
        if not data:
            return 0.0
        index = min(len(data) - 1, int(round((value / 100) * (len(data) - 1))))
        return round(data[index], 1)

    def stats(self) -> dict:
        with self._lock:
            count = len(self._latencies)
            p50 = round(median(self._latencies), 1) if self._latencies else 0.0
        return {
            "requests": self.request_count,
            "errors": self.error_count,
            "latencySamples": count,
            "p50Ms": p50,
            "p95Ms": self.percentile(95),
            "p99Ms": self.percentile(99),
            "playlistBuildMs": self.last_cycle_ms,
            "playlistBuildAt": self.last_cycle_at,
            "uptimeSeconds": int(time.time() - self.process_started),
            "uptimePct7d": 99.98,
            "uptimeIsSimulated": True,
        }


metrics = Metrics()