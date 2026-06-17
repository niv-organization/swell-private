"""
Distributed cache manager with TTL support and LRU eviction.
Provides thread-safe caching with configurable eviction policies.
"""

import threading
import time
import hashlib
import logging
from collections import OrderedDict
from typing import Any, Optional, Callable, Dict, Tuple

logger = logging.getLogger(__name__)


class CacheEntry:
    __slots__ = ("value", "created_at", "ttl", "access_count", "size_bytes")

    def __init__(self, value: Any, ttl: int, size_bytes: int = 0):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl
        self.access_count = 0
        self.size_bytes = size_bytes

    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return time.time() - self.created_at > self.ttl


class CacheStats:
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.total_size_bytes = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def reset(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0


class LRUCacheManager:
    def __init__(
        self,
        max_entries: int = 1000,
        max_size_bytes: int = 50 * 1024 * 1024,
        default_ttl: int = 300,
        cleanup_interval: int = 60,
    ):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_entries = max_entries
        self._max_size_bytes = max_size_bytes
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval
        self._lock = threading.Lock()
        self._stats = CacheStats()
        self._key_locks: Dict[str, threading.Lock] = {}
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        self._running = True
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True
        )
        self._cleanup_thread.start()
        logger.info("Cache manager started with max_entries=%d", self._max_entries)

    def stop(self):
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        logger.info("Cache manager stopped")

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired():
                self._remove_entry(key)
                self._stats.misses += 1
                return None

            self._cache.move_to_end(key)
            entry.access_count += 1
            self._stats.hits += 1
            return entry.value

    def put(self, key: str, value: Any, ttl: Optional[int] = None, size_bytes: int = 0):
        effective_ttl = ttl if ttl is not None else self._default_ttl

        with self._lock:
            if key in self._cache:
                old_entry = self._cache[key]
                self._stats.total_size_bytes -= old_entry.size_bytes
                del self._cache[key]

            while len(self._cache) >= self._max_entries:
                self._evict_one()

            while self._stats.total_size_bytes + size_bytes > self._max_size_bytes:
                if not self._cache:
                    break
                self._evict_one()

            entry = CacheEntry(value, effective_ttl, size_bytes)
            self._cache[key] = entry
            self._stats.total_size_bytes += size_bytes

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                self._remove_entry(key)
                return True
            return False

    def get_or_compute(
        self, key: str, compute_fn: Callable[[], Any], ttl: Optional[int] = None
    ) -> Any:
        value = self.get(key)
        if value is not None:
            return value

        key_lock = self._get_key_lock(key)
        with key_lock:
            value = self.get(key)
            if value is not None:
                return value

            computed_value = compute_fn()
            self.put(key, computed_value, ttl)
            return computed_value

    def bulk_get(self, keys: list) -> Dict[str, Any]:
        results = {}
        with self._lock:
            for key in keys:
                entry = self._cache.get(key)
                if entry and not entry.is_expired():
                    results[key] = entry.value
                    entry.access_count += 1
                    self._stats.hits += 1
                else:
                    self._stats.misses += 1
        return results

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._stats.total_size_bytes = 0
            self._key_locks.clear()

    def get_stats(self) -> dict:
        return {
            "entries": len(self._cache),
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "evictions": self._stats.evictions,
            "hit_rate": round(self._stats.hit_rate, 4),
            "total_size_bytes": self._stats.total_size_bytes,
        }

    @staticmethod
    def compute_key(*args) -> str:
        raw = ":".join(str(a) for a in args)
        return hashlib.md5(raw.encode()).hexdigest()

    def _evict_one(self):
        if not self._cache:
            return
        key, entry = self._cache.popitem(last=True)
        self._stats.total_size_bytes -= entry.size_bytes
        self._stats.evictions += 1
        logger.debug("Evicted cache key: %s", key)

    def _remove_entry(self, key: str):
        entry = self._cache.pop(key, None)
        if entry:
            self._stats.total_size_bytes -= entry.size_bytes

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def _cleanup_loop(self):
        while self._running:
            time.sleep(self._cleanup_interval)
            self._cleanup_expired()

    def _cleanup_expired(self):
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired()
            ]
            for key in expired_keys:
                self._remove_entry(key)
            if expired_keys:
                logger.info("Cleaned up %d expired entries", len(expired_keys))


class TieredCache:
    def __init__(
        self,
        l1_max_entries: int = 100,
        l2_max_entries: int = 5000,
        l1_ttl: int = 30,
        l2_ttl: int = 600,
    ):
        self._l1 = LRUCacheManager(max_entries=l1_max_entries, default_ttl=l1_ttl)
        self._l2 = LRUCacheManager(max_entries=l2_max_entries, default_ttl=l2_ttl)

    def get(self, key: str) -> Optional[Any]:
        value = self._l1.get(key)
        if value is not None:
            return value

        value = self._l2.get(key)
        if value is not None:
            self._l1.put(key, value)
            return value

        return None

    def put(self, key: str, value: Any, promote_to_l1: bool = False):
        self._l2.put(key, value)
        if promote_to_l1:
            self._l1.put(key, value)

    def invalidate(self, key: str):
        self._l1.delete(key)

    def stats(self) -> dict:
        return {
            "l1": self._l1.get_stats(),
            "l2": self._l2.get_stats(),
        }
