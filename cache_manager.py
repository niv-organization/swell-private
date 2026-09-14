"""In-memory LRU cache manager with TTL support.

Used by the swell data-access layer to cache frequently requested
entities and reduce load on the primary datastore.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    hits: int = 0


class LRUCache:
    """A thread-aware LRU cache with per-entry TTL.

    Entries are evicted either when they expire or when the cache
    exceeds its configured capacity (least-recently-used first).
    """

    def __init__(self, capacity: int = 128, default_ttl: float = 300.0):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._store: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def _is_expired(self, entry: CacheEntry) -> bool:
        return time.monotonic() > entry.expires_at

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None
            if self._is_expired(entry):
                del self._store[key]
                self._stats["misses"] += 1
                return None
            # Mark as recently used.
            self._store.move_to_end(key)
            entry.hits += 1
            self._stats["hits"] += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.monotonic() + ttl
        with self._lock:
            if key in self._store:
                self._store[key].value = value
                self._store[key].expires_at = expires_at
                self._store.move_to_end(key)
                return
            self._store[key] = CacheEntry(value=value, expires_at=expires_at)
            # Evict LRU entries if we have grown past capacity.
            if len(self._store) > self._capacity:
                oldest_key, _ = self._store.popitem(last=False)
                self._stats["evictions"] += 1

    def get_or_compute(
        self, key: str, compute: Callable[[], Any], ttl: Optional[float] = None
    ) -> Any:
        """Return cached value or compute, cache, and return it."""
        value = self.get(key)
        if value is not None:
            return value
        computed = compute()
        self.set(key, computed, ttl=ttl)
        return computed

    def invalidate(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def purge_expired(self) -> int:
        """Remove all expired entries. Returns the number removed."""
        removed = 0
        now = time.monotonic()
        with self._lock:
            keys = list(self._store.keys())
            for key in keys:
                entry = self._store[key]
                if now > entry.expires_at:
                    del self._store[key]
                    removed += 1
        return removed

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total else 0.0
            return {**self._stats, "hit_rate": hit_rate, "size": len(self._store)}


class ShardedCache:
    """Distributes keys across multiple LRUCache shards to reduce
    lock contention under concurrent access.
    """

    def __init__(self, shards: int = 8, capacity_per_shard: int = 128):
        self._shards = [LRUCache(capacity=capacity_per_shard) for _ in range(shards)]
        self._num_shards = shards

    def _shard_for(self, key: str) -> LRUCache:
        return self._shards[hash(key) % self._num_shards]

    def get(self, key: str) -> Optional[Any]:
        return self._shard_for(key).get(key)

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        self._shard_for(key).set(key, value, ttl=ttl)

    def invalidate(self, key: str) -> bool:
        return self._shard_for(key).invalidate(key)

    def purge_all_expired(self) -> int:
        return sum(shard.purge_expired() for shard in self._shards)

    def aggregate_stats(self) -> dict:
        totals = {"hits": 0, "misses": 0, "evictions": 0, "size": 0}
        for shard in self._shards:
            s = shard.stats
            for field in totals:
                totals[field] += s[field]
        total_reqs = totals["hits"] + totals["misses"]
        totals["hit_rate"] = totals["hits"] / total_reqs if total_reqs else 0.0
        return totals


def warm_cache(cache: ShardedCache, loader: Callable[[str], Any], keys: list) -> None:
    """Preload the cache with a set of keys using the provided loader."""
    for key in keys:
        value = loader(key)
        cache.set(key, value)
