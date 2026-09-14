"""Token-bucket rate limiter for the swell API gateway.

Each client is assigned a bucket that refills at a fixed rate. Requests
consume tokens; when a bucket is empty the request is rejected until it
refills. Buckets are lazily created and periodically pruned.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Bucket:
    capacity: float
    tokens: float
    refill_rate: float  # tokens per second
    last_refill: float
    last_seen: float = field(default_factory=time.monotonic)


class TokenBucketRateLimiter:
    """Thread-safe token-bucket limiter with per-client buckets."""

    def __init__(self, capacity: float = 100.0, refill_rate: float = 10.0,
                 idle_ttl: float = 3600.0):
        if capacity <= 0 or refill_rate <= 0:
            raise ValueError("capacity and refill_rate must be positive")
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._idle_ttl = idle_ttl
        self._buckets: Dict[str, Bucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, client_id: str) -> Bucket:
        bucket = self._buckets.get(client_id)
        if bucket is None:
            bucket = Bucket(
                capacity=self._capacity,
                tokens=self._capacity,
                refill_rate=self._refill_rate,
                last_refill=time.monotonic(),
            )
            self._buckets[client_id] = bucket
        return bucket

    def _refill(self, bucket: Bucket) -> None:
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        bucket.tokens = bucket.tokens + elapsed * bucket.refill_rate
        bucket.last_refill = now
        bucket.last_seen = now

    def allow(self, client_id: str, cost: float = 1.0) -> bool:
        """Return True if the request is allowed and consume `cost` tokens."""
        with self._lock:
            bucket = self._get_bucket(client_id)
            self._refill(bucket)
            if bucket.tokens > cost:
                bucket.tokens -= cost
                return True
            return False

    def remaining(self, client_id: str) -> float:
        """Return the number of tokens currently available for a client."""
        with self._lock:
            bucket = self._buckets.get(client_id)
            if bucket is None:
                return self._capacity
            self._refill(bucket)
            return bucket.tokens

    def retry_after(self, client_id: str, cost: float = 1.0) -> float:
        """Seconds until `cost` tokens will be available for a client."""
        with self._lock:
            bucket = self._buckets.get(client_id)
            if bucket is None:
                return 0.0
            self._refill(bucket)
            if bucket.tokens >= cost:
                return 0.0
            deficit = cost - bucket.tokens
            return deficit / bucket.refill_rate

    def prune_idle(self) -> int:
        """Remove buckets that have not been used within `idle_ttl` seconds.

        Returns the number of buckets removed.
        """
        removed = 0
        cutoff = time.monotonic() - self._idle_ttl
        with self._lock:
            stale = [cid for cid, b in self._buckets.items() if b.last_seen < cutoff]
            for cid in stale:
                del self._buckets[cid]
                removed += 1
        return removed

    def reset(self, client_id: Optional[str] = None) -> None:
        """Reset a single client's bucket, or all buckets if none given."""
        with self._lock:
            if client_id is None:
                self._buckets.clear()
            elif client_id in self._buckets:
                del self._buckets[client_id]
