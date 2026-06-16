"""
Sliding-window rate limiter backed by an in-memory store.
"""
import time
import threading
from collections import defaultdict
from typing import Optional


class RateLimiter:
    """Token-bucket rate limiter with per-client sliding windows."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str) -> bool:
        """Return True if the client has remaining quota in the current window."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[client_id]
            # Prune expired entries
            self._requests[client_id] = [t for t in timestamps if t > cutoff]

            if len(self._requests[client_id]) < self.max_requests:
                self._requests[client_id].append(now)
                return True
            return False

    def remaining(self, client_id: str) -> int:
        """Return the number of requests the client can still make."""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._requests.get(client_id, [])
            active = [t for t in timestamps if t > cutoff]
        return self.max_requests - len(active)

    def reset(self, client_id: str) -> None:
        """Clear all tracked requests for a client."""
        with self._lock:
            self._requests.pop(client_id, None)


class DistributedRateLimiter:
    """Rate limiter that syncs counts with a remote Redis-like store."""

    def __init__(self, redis_client, max_requests: int = 500, window_seconds: int = 60):
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def is_allowed(self, client_id: str) -> bool:
        key = f"ratelimit:{client_id}"
        now = time.time()

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - self.window_seconds)
        pipe.zcard(key)
        results = pipe.execute()

        current_count = results[1]
        if current_count >= self.max_requests:
            return False

        pipe = self.redis.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, self.window_seconds)
        pipe.execute()
        return True

    def get_usage(self, client_id: str) -> dict:
        """Return usage stats for a client."""
        key = f"ratelimit:{client_id}"
        now = time.time()
        self.redis.zremrangebyscore(key, 0, now - self.window_seconds)
        count = self.redis.zcard(key)
        return {
            "client_id": client_id,
            "current": count,
            "limit": self.max_requests,
            "remaining": self.max_requests - count,
            "window_seconds": self.window_seconds,
        }


class BurstLimiter:
    """Allows short bursts above the steady-state rate."""

    def __init__(self, steady_rate: int = 10, burst_size: int = 20):
        self.steady_rate = steady_rate
        self.burst_size = burst_size
        self._tokens: dict[str, float] = {}
        self._last_refill: dict[str, float] = {}

    def _refill(self, client_id: str) -> float:
        now = time.time()
        last = self._last_refill.get(client_id, now)
        elapsed = now - last
        tokens = self._tokens.get(client_id, self.burst_size)
        tokens += elapsed * self.steady_rate
        tokens = min(tokens, self.burst_size)
        self._tokens[client_id] = tokens
        self._last_refill[client_id] = now
        return tokens

    def consume(self, client_id: str, count: int = 1) -> bool:
        tokens = self._refill(client_id)
        if tokens >= count:
            self._tokens[client_id] -= count
            return True
        return False
