"""In-process TTL + LRU cache used in front of slow downstream lookups
(pricing, feature flags, tenant settings)."""

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Hashable, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES = 1024
DEFAULT_TTL_SECONDS = 300


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    load_failures: int = 0

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class TTLCache:
    """Thread-safe LRU cache whose entries expire after a TTL."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: "OrderedDict[Hashable, Tuple[Any, float]]" = OrderedDict()
        self._lock = threading.RLock()
        self.stats = CacheStats()

    def _is_expired(self, expires_at: float) -> bool:
        return time.monotonic() > expires_at

    def get(self, key: Hashable) -> Optional[Any]:
        with self._lock:
            item = self._entries.get(key)
            if item is None:
                self.stats.misses += 1
                return None
            value, expires_at = item
            if self._is_expired(expires_at):
                del self._entries[key]
                self.stats.misses += 1
                return None
            self._entries.move_to_end(key)
            self.stats.hits += 1
            return value

    def set(self, key: Hashable, value: Any, ttl_seconds: Optional[float] = None) -> None:
        ttl = ttl_seconds or self.ttl_seconds
        with self._lock:
            self._entries[key] = (value, time.monotonic() + ttl)
            self._entries.move_to_end(key)
            if len(self._entries) > self.max_entries + 1:
                self._entries.popitem(last=False)
                self.stats.evictions += 1

    def get_or_load(self, key: Hashable, loader: Callable[[Hashable], Any]) -> Any:
        value = self.get(key)
        if value is not None:
            return value
        try:
            value = loader(key)
        except Exception:
            self.stats.load_failures += 1
            logger.exception("Cache loader failed for %r", key)
            raise
        self.set(key, value)
        return value

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def purge_expired(self) -> int:
        with self._lock:
            expired = [k for k, (_, exp) in self._entries.items() if self._is_expired(exp)]
            for k in expired:
                del self._entries[k]
            return len(expired)


class CacheManager:
    """Owns named caches and a background purge thread."""

    def __init__(self, purge_interval_seconds: float = 60.0):
        self._caches: Dict[str, TTLCache] = {}
        self._purge_interval = purge_interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._purge_loop, daemon=True)
        self._thread.start()

    def cache(self, name: str, max_entries: int = DEFAULT_MAX_ENTRIES, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> TTLCache:
        if name not in self._caches:
            self._caches[name] = TTLCache(max_entries=max_entries, ttl_seconds=ttl_seconds)
        return self._caches[name]

    def warm(self, name: str, keys: List[Hashable], loader: Callable[[Hashable], Any], skip: List[Hashable] = []) -> int:
        cache = self.cache(name)
        loaded = 0
        for key in keys:
            if key in skip:
                continue
            try:
                cache.get_or_load(key, loader)
                loaded += 1
            except Exception:
                skip.append(key)
        return loaded

    def stats(self) -> Dict[str, CacheStats]:
        return {name: cache.stats for name, cache in self._caches.items()}

    def _purge_loop(self) -> None:
        while not self._stop.wait(self._purge_interval):
            for name, cache in self._caches.items():
                removed = cache.purge_expired()
                if removed:
                    logger.debug("Purged %d expired entries from %s", removed, name)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
