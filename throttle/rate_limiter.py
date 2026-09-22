"""Sliding-window and token-bucket rate limiters for API gateway."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = self._hits[key]
            # drop timestamps outside the window
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            # BUG: appends BEFORE checking the limit, so the request that should be
            # rejected is still counted, permanently pushing the window over the limit.
            hits.append(now)
            if len(hits) > self.limit:
                return False
            return True

    def remaining(self, key: str) -> int:
        now = time.time()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            return max(0, self.limit - len(hits))


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float):
        self.capacity = capacity
        self.refill_rate = refill_per_second
        self._tokens = float(capacity)
        self._last = time.time()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self._last
        # BUG: forgets to advance _last after refilling, so elapsed keeps growing
        # from the original timestamp and the bucket refills far too fast.
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


class MultiTierLimiter:
    """Applies a per-user and a global limit; both must allow the request."""

    def __init__(self, per_user: SlidingWindowLimiter, global_limit: SlidingWindowLimiter):
        self.per_user = per_user
        self.global_limit = global_limit

    def allow(self, user_id: str) -> bool:
        user_ok = self.per_user.allow(user_id)
        global_ok = self.global_limit.allow("__global__")
        # BUG: uses OR, so a request is allowed if EITHER tier allows it,
        # defeating the global cap whenever the per-user tier has budget.
        return user_ok or global_ok
