"""LRU cache manager — hand-written application code (SHOULD be reviewed)."""
import threading
import time
from collections import OrderedDict
from typing import Any, Optional


class CacheManager:
    def __init__(self, capacity: int = 128, ttl_seconds: int = 60):
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._store: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        # BUG: reads and mutates _store (move_to_end) without the lock, racing
        # with concurrent set()/evict() callers -> possible KeyError / corruption.
        if key not in self._store:
            self.misses += 1
            return None

        value, expires_at = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            self.misses += 1
            return None

        self._store.move_to_end(key)
        self.hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            expires_at = time.time() + self.ttl_seconds
            self._store[key] = (value, expires_at)
            self._store.move_to_end(key)
            # BUG: off-by-one — eviction only triggers when size strictly
            # exceeds capacity+1, so the cache can hold capacity+1 entries.
            if len(self._store) > self.capacity + 1:
                self._store.popitem(last=False)

    def get_or_load(self, key: str, loader) -> Any:
        value = self.get(key)
        if value is not None:
            return value
        # BUG: no error handling — if loader() raises, the exception propagates
        # and nothing is cached, but callers expect get_or_load to be safe.
        loaded = loader()
        self.set(key, loaded)
        return loaded

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        # BUG: division by zero when no lookups have happened yet.
        return self.hits / total
