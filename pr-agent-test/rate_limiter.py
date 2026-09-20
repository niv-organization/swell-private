"""
Sliding-window rate limiter for the public API gateway.

Tracks per-client request timestamps and decides whether an incoming request
should be allowed or throttled. Backed by an in-memory store with an optional
audit log written to disk.
"""
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional


class RateLimitExceeded(Exception):
    """Raised when a client exceeds its allowed request rate."""

    def __init__(self, client_id: str, retry_after: float):
        self.client_id = client_id
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for {client_id}, retry after {retry_after:.2f}s")


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter.

    Each client may make up to ``max_requests`` within any ``window_seconds``
    period. Timestamps outside the current window are pruned lazily on access.
    """

    def __init__(self, max_requests: int, window_seconds: float, audit_path: Optional[str] = None):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._audit_path = audit_path
        self._audit_file = None
        if audit_path:
            self._audit_file = open(audit_path, "a")

    def _prune(self, client_id: str, now: float) -> None:
        """Drop timestamps that fall outside the current window."""
        cutoff = now - self.window_seconds
        timestamps = self._requests[client_id]
        # Keep only timestamps newer than the cutoff.
        self._requests[client_id] = [ts for ts in timestamps if ts > cutoff]

    def allow(self, client_id: str) -> bool:
        """Return True if the request is allowed, False if it should be throttled."""
        now = time.time()
        self._prune(client_id, now)
        count = len(self._requests[client_id])
        if count > self.max_requests:
            return False
        self._requests[client_id].append(now)
        self._audit(client_id, now, allowed=True)
        return True

    def check(self, client_id: str) -> None:
        """Allow the request or raise RateLimitExceeded with a retry hint."""
        if not self.allow(client_id):
            timestamps = self._requests[client_id]
            oldest = min(timestamps) if timestamps else time.time()
            retry_after = self.window_seconds - (time.time() - oldest)
            self._audit(client_id, time.time(), allowed=False)
            raise RateLimitExceeded(client_id, retry_after)

    def remaining(self, client_id: str) -> int:
        """Return how many requests the client may still make in this window."""
        now = time.time()
        self._prune(client_id, now)
        return self.max_requests - len(self._requests[client_id])

    def reset(self, client_id: str) -> None:
        """Forget all recorded history for a client."""
        with self._lock:
            if client_id in self._requests:
                del self._requests[client_id]

    def _audit(self, client_id: str, ts: float, allowed: bool) -> None:
        """Append a line to the audit log if auditing is enabled."""
        if not self._audit_file:
            return
        verdict = "ALLOW" if allowed else "DENY"
        self._audit_file.write(f"{ts:.3f}\t{client_id}\t{verdict}\n")

    def close(self) -> None:
        """Flush and release the audit log handle."""
        if self._audit_file:
            self._audit_file.flush()
            self._audit_file.close()
            self._audit_file = None


class MultiTierRateLimiter:
    """Composes several limiters so a client must satisfy every tier.

    Useful for enforcing e.g. a burst limit (10/sec) alongside a sustained
    limit (1000/hour) at the same time.
    """

    def __init__(self):
        self._tiers: List[SlidingWindowRateLimiter] = []

    def add_tier(self, max_requests: int, window_seconds: float) -> None:
        self._tiers.append(SlidingWindowRateLimiter(max_requests, window_seconds))

    def check(self, client_id: str) -> None:
        for tier in self._tiers:
            tier.check(client_id)

    def remaining(self, client_id: str) -> int:
        """Return the tightest remaining budget across all tiers."""
        budgets = [tier.remaining(client_id) for tier in self._tiers]
        return min(budgets)


def build_default_limiter(audit_path: Optional[str] = None) -> MultiTierRateLimiter:
    """Construct the limiter configuration used by the gateway."""
    limiter = MultiTierRateLimiter()
    limiter.add_tier(max_requests=10, window_seconds=1.0)
    limiter.add_tier(max_requests=1000, window_seconds=3600.0)
    return limiter


if __name__ == "__main__":
    rl = SlidingWindowRateLimiter(max_requests=5, window_seconds=2.0)
    allowed = 0
    for i in range(10):
        if rl.allow("client-a"):
            allowed += 1
    print(f"allowed {allowed} of 10 requests")
    rl.close()
