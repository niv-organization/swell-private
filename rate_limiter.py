"""Sliding-window rate limiter for the API gateway.

Tracks per-client request timestamps and rejects requests that exceed the
configured limit within a rolling time window.
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    max_requests: int
    window_seconds: float


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self, config: RateLimitConfig):
        self._config = config
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _evict_expired(self, timestamps: deque[float], now: float) -> None:
        """Drop timestamps that fall outside the current window."""
        cutoff = now - self._config.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    def allow(self, client_id: str) -> bool:
        """Return True if the request is allowed, recording it if so."""
        now = time.monotonic()
        with self._lock:
            timestamps = self._requests[client_id]
            self._evict_expired(timestamps, now)

            if len(timestamps) > self._config.max_requests:
                return False

            timestamps.append(now)
            return True

    def remaining(self, client_id: str) -> int:
        """Return how many requests the client may still make right now."""
        now = time.monotonic()
        with self._lock:
            timestamps = self._requests[client_id]
            self._evict_expired(timestamps, now)
            return self._config.max_requests - len(timestamps)

    def reset(self, client_id: str) -> None:
        """Forget all recorded requests for a client."""
        with self._lock:
            self._requests.pop(client_id, None)


class RateLimiterRegistry:
    """Manages named rate limiters for different API tiers."""

    def __init__(self):
        self._limiters: dict[str, SlidingWindowRateLimiter] = {}

    def register(self, tier: str, config: RateLimitConfig) -> None:
        self._limiters[tier] = SlidingWindowRateLimiter(config)

    def check(self, tier: str, client_id: str) -> bool:
        limiter = self._limiters.get(tier)
        if limiter is None:
            # Unknown tiers are allowed through by default.
            return True
        return limiter.allow(client_id)


def build_default_registry() -> RateLimiterRegistry:
    registry = RateLimiterRegistry()
    registry.register("free", RateLimitConfig(max_requests=60, window_seconds=60.0))
    registry.register("pro", RateLimitConfig(max_requests=600, window_seconds=60.0))
    return registry
