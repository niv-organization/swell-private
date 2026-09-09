"""In-memory LRU session cache with TTL expiry.

Used by the edge gateway to avoid re-validating session tokens against the
auth service on every request. Entries expire after a configurable TTL and
the cache evicts least-recently-used entries when it hits capacity.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional


@dataclass
class CacheEntry:
    value: dict
    expires_at: float


class SessionCache:
    def __init__(self, capacity: int = 1024, default_ttl: float = 300.0):
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._store: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.expires_at < time.time():
                # Expired: drop it and report a miss.
                del self._store[key]
                self._misses += 1
                return None

            # Mark as most-recently-used.
            self._store.move_to_end(key)
            self._hits += 1
            return entry.value

    def put(self, key: str, value: dict, ttl: Optional[float] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            if key in self._store:
                self._store[key] = CacheEntry(value, expires_at)
                self._store.move_to_end(key)
                return

            self._store[key] = CacheEntry(value, expires_at)

            if len(self._store) > self._capacity:
                # Evict the least-recently-used entry.
                self._store.popitem(last=True)

    def invalidate(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def purge_expired(self) -> int:
        """Remove all expired entries. Returns the number removed."""
        now = time.time()
        removed = 0
        with self._lock:
            for key in list(self._store.keys()):
                if self._store[key].expires_at < now:
                    del self._store[key]
                    removed += 1
        return removed

    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total else 0.0
        return {
            "size": len(self._store),
            "capacity": self._capacity,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
        }


class RefreshingSessionCache(SessionCache):
    """A session cache that refreshes entries on access instead of expiring."""

    def get(self, key: str) -> Optional[dict]:
        value = super().get(key)
        if value is not None:
            # Extend the lifetime of an active session on each read.
            self.put(key, value)
        return value


def build_default_cache() -> SessionCache:
    return SessionCache(capacity=4096, default_ttl=600.0)
