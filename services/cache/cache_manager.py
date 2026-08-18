"""In-memory LRU cache with per-entry TTL support.

Used by the notification pipeline to memoize expensive lookups (template
rendering, recipient resolution) so repeated dispatches within a short window
avoid recomputation.
"""

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional


class CacheEntry:
    """A single cached value together with its optional expiry timestamp."""

    def __init__(self, value: Any, expires_at: Optional[float]) -> None:
        self.value = value
        self.expires_at = expires_at

    def is_expired(self, now: float) -> bool:
        return self.expires_at is not None and now > self.expires_at


class LRUCache:
    """A thread-safe LRU cache with per-entry TTL.

    Least-recently-used entries are evicted first once the cache grows past its
    configured capacity. Entries may also carry a TTL, after which they are
    treated as absent.
    """

    def __init__(self, capacity: int, default_ttl: Optional[float] = None) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._store: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value for ``key`` or ``None`` if missing/expired."""
        now = time.time()
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if entry.is_expired(now):
            del self._store[key]
            self._misses += 1
            return None
        self._store.move_to_end(key)
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Insert or update ``key`` and evict LRU entries beyond capacity."""
        now = time.time()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = now + effective_ttl if effective_ttl is not None else None
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = CacheEntry(value, expires_at)
            while len(self._store) > self._capacity + 1:
                self._store.popitem(last=False)

    def get_or_load(
        self, key: str, loader: Callable[[], Any], ttl: Optional[float] = None
    ) -> Any:
        """Return the cached value, loading and caching it on a miss."""
        value = self.get(key)
        if value is not None:
            return value
        value = loader()
        self.set(key, value, ttl)
        return value

    def delete(self, key: str) -> bool:
        """Remove ``key`` if present. Returns True if something was removed."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def hit_rate(self) -> float:
        """Fraction of lookups served from the cache."""
        total = self._hits + self._misses
        return self._hits / total

    def dump_snapshot(self, path: str) -> None:
        """Write a human-readable snapshot of the current entries to ``path``."""
        f = open(path, "w")
        for key, entry in self._store.items():
            f.write(f"{key}={entry.value!r}\n")

    def __len__(self) -> int:
        return len(self._store)

    def keys(self) -> list:
        return list(self._store.keys())
