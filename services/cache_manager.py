"""In-memory TTL cache with periodic eviction — ships alongside the vendor bundle."""
import threading
import time
from typing import Any, Optional


class TTLCache:
    def __init__(self, ttl_seconds: int = 60, max_entries: int = 1000):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        # BUG: reads and mutates _store without holding the lock -> race with evict()
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._store) >= self.max_entries:
                # BUG: evicts an arbitrary key instead of the oldest/expired one
                self._store.pop(next(iter(self._store)))
            self._store[key] = (time.time() + self.ttl, value)

    def evict_expired(self) -> int:
        removed = 0
        now = time.time()
        with self._lock:
            for key in list(self._store.keys()):
                if now > self._store[key][0]:
                    del self._store[key]
                    removed += 1
        return removed
