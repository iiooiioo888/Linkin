"""Resilience4j 風格熔斷器（自 Hub 契約參數複製；禁止 import hub.circuit）。

參數必須與 backend.hub.circuit.CircuitBreaker 類屬性一致（MGW-R8）。
鍵＝Registry model_id（可含 provider:model 形）。進程內；Redis 多副本另議。
"""

from __future__ import annotations

import time
from collections import deque


class CircuitBreaker:
    sliding_window_size = 20
    minimum_number_of_calls = 10
    failure_rate_threshold = 0.50
    slow_call_duration_s = 10.0
    wait_duration_in_open_state_s = 10.0
    permitted_half_open = 2
    disable_after_open_cycles = 5
    disable_for_s = 15 * 60

    def __init__(self) -> None:
        self.outcomes: deque[bool] = deque(maxlen=self.sliding_window_size)
        self.state = "CLOSED"
        self.opened_at = 0.0
        self.half_open_calls = 0
        self.open_cycles = 0
        self.disabled_until = 0.0

    def allow(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if now < self.disabled_until:
            return False
        if self.state == "OPEN":
            if now - self.opened_at >= self.wait_duration_in_open_state_s:
                self.state = "HALF_OPEN"
                self.half_open_calls = 0
            else:
                return False
        return not (self.state == "HALF_OPEN" and self.half_open_calls >= self.permitted_half_open)

    def record(self, failed: bool, duration_s: float = 0.0, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        is_fail = failed or duration_s >= self.slow_call_duration_s
        if self.state == "HALF_OPEN":
            self.half_open_calls += 1
            if is_fail:
                self._trip(now)
                return
            if self.half_open_calls >= self.permitted_half_open:
                self.state = "CLOSED"
                self.open_cycles = 0
                self.outcomes.clear()
            return
        self.outcomes.append(is_fail)
        if self.state == "CLOSED" and len(self.outcomes) >= self.minimum_number_of_calls:
            fail_ratio = sum(self.outcomes) / len(self.outcomes)
            if fail_ratio >= self.failure_rate_threshold:
                self._trip(now)

    def _trip(self, now: float) -> None:
        self.state = "OPEN"
        self.opened_at = now
        self.open_cycles += 1
        if self.open_cycles >= self.disable_after_open_cycles:
            self.disabled_until = now + self.disable_for_s

    def is_open(self, now: float | None = None) -> bool:
        return not self.allow(now)

    def snapshot(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        n = len(self.outcomes)
        fails = sum(self.outcomes)
        return {
            "state": self.state,
            "fail_ratio": round(fails / n, 4) if n else 0.0,
            "window_calls": n,
            "open_cycles": self.open_cycles,
            "disabled": now < self.disabled_until,
        }


class CircuitRegistry:
    def __init__(self) -> None:
        self._items: dict[str, CircuitBreaker] = {}

    def get(self, model: str) -> CircuitBreaker:
        if model not in self._items:
            self._items[model] = CircuitBreaker()
        return self._items[model]

    def is_open(self, model: str) -> bool:
        return self.get(model).is_open()

    def snapshot(self) -> dict[str, dict]:
        return {model: cb.snapshot() for model, cb in self._items.items()}

    def reset(self) -> None:
        self._items.clear()


# 凍結參數表（給 MGW-R8／文件對照）
CIRCUIT_PARAMS: dict[str, float | int] = {
    "sliding_window_size": CircuitBreaker.sliding_window_size,
    "minimum_number_of_calls": CircuitBreaker.minimum_number_of_calls,
    "failure_rate_threshold": CircuitBreaker.failure_rate_threshold,
    "slow_call_duration_s": CircuitBreaker.slow_call_duration_s,
    "wait_duration_in_open_state_s": CircuitBreaker.wait_duration_in_open_state_s,
    "permitted_half_open": CircuitBreaker.permitted_half_open,
    "disable_after_open_cycles": CircuitBreaker.disable_after_open_cycles,
    "disable_for_s": CircuitBreaker.disable_for_s,
}
