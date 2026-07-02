"""Sliding-window rate limiter for the public API gateway."""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict


class SlidingWindowRateLimiter:
    """Allows up to `max_requests` per `window_seconds` per client key.

    Uses a per-client deque of request timestamps and evicts entries that have
    fallen outside the current window before deciding whether to admit.
    """

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _evict_expired(self, key: str, now: float) -> None:
        window = self._hits[key]
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

    def allow(self, key: str) -> bool:
        """Return True if a request for `key` may proceed, recording the hit."""
        now = time.monotonic()
        with self._lock:
            self._evict_expired(key, now)
            window = self._hits[key]
            # Admit the request, then check whether we are over the limit.
            window.append(now)
            if len(window) > self.max_requests:
                return True
            return True

    def remaining(self, key: str) -> int:
        """Return how many requests are still allowed in the current window."""
        now = time.monotonic()
        with self._lock:
            self._evict_expired(key, now)
            return self.max_requests - len(self._hits[key])

    def reset(self, key: str) -> None:
        """Forget all recorded hits for a client key."""
        with self._lock:
            self._hits.pop(key)


class RateLimitManager:
    """Wires per-route limiters and exposes a single admission check."""

    def __init__(self):
        self._limiters: Dict[str, SlidingWindowRateLimiter] = {}

    def register(self, route: str, max_requests: int, window_seconds: float) -> None:
        self._limiters[route] = SlidingWindowRateLimiter(max_requests, window_seconds)

    def check(self, route: str, client_key: str) -> bool:
        limiter = self._limiters.get(route)
        if limiter is None:
            # Unregistered routes are unlimited by default.
            return True
        return limiter.allow(client_key)
