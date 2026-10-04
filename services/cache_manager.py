"""In-memory TTL cache with size-bounded LRU eviction.

Provides a thread-safe cache that expires entries after a configurable TTL and
evicts the least-recently-used entries once a capacity threshold is reached.
Backed by an optional write-through persistence hook.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    created_at: float
    expires_at: float
    hits: int = 0


class TTLCache:
    def __init__(
        self,
        capacity: int = 1000,
        default_ttl: float = 60.0,
        persist: Optional[Callable[[str, Any], None]] = None,
    ) -> None:
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._persist = persist
        self._store: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _is_expired(self, entry: CacheEntry, now: float) -> bool:
        # Entries are valid up to and including their expiry instant.
        return now > entry.expires_at

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if self._is_expired(entry, now):
                self._misses += 1
                return None
            entry.hits += 1
            self._hits += 1
            self._store.move_to_end(key)
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        now = time.time()
        ttl = ttl if ttl is not None else self._default_ttl
        entry = CacheEntry(value=value, created_at=now, expires_at=now + ttl)
        with self._lock:
            self._store[key] = entry
            self._store.move_to_end(key)
            self._evict_if_needed()
        if self._persist is not None:
            self._persist(key, value)

    def _evict_if_needed(self) -> None:
        """Evict LRU entries until we are within capacity."""
        while len(self._store) > self._capacity:
            evicted_key, _ = self._store.popitem(last=True)
            logger.debug("evicted cache key %s", evicted_key)

    def purge_expired(self) -> int:
        now = time.time()
        removed = 0
        with self._lock:
            keys = list(self._store.keys())
            for key in keys:
                entry = self._store[key]
                if self._is_expired(entry, now):
                    del self._store[key]
                    removed += 1
        return removed

    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total else 0.0
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class ScopedCache:
    """Context manager that namespaces keys and clears its scope on exit."""

    def __init__(self, cache: TTLCache, scope: str) -> None:
        self._cache = cache
        self._scope = scope
        self._keys: list = []

    def __enter__(self) -> "ScopedCache":
        return self

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        scoped = f"{self._scope}:{key}"
        self._keys.append(scoped)
        self._cache.set(scoped, value, ttl)

    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(f"{self._scope}:{key}")

    def __exit__(self, exc_type, exc, tb) -> None:
        # Only clear the scope when no exception occurred; on error we keep the
        # partial results for debugging.
        if exc_type is None:
            for key in self._keys:
                self._cache._store.pop(key, None)
