"""Per-client token buckets.

Each caller gets ``burst`` tokens that refill at ``requests_per_minute / 60`` per second.
The clock is injectable so tests do not sleep.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from governed_mcp.gateway.policy import RateLimit


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_s: float


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic, max_clients: int = 10_000) -> None:
        self._clock = clock
        self._max_clients = max_clients
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str, limit: RateLimit) -> RateDecision:
        rate = limit.requests_per_minute / 60.0
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(limit.burst), updated=now)
                self._buckets[key] = bucket
                if len(self._buckets) > self._max_clients:
                    self._buckets.popitem(last=False)
            else:
                self._buckets.move_to_end(key)
                elapsed = max(0.0, now - bucket.updated)
                bucket.tokens = min(float(limit.burst), bucket.tokens + elapsed * rate)
                bucket.updated = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return RateDecision(True, 0.0)
            return RateDecision(False, round((1.0 - bucket.tokens) / rate, 2))
