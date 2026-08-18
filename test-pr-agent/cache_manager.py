"""In-memory LRU cache with TTL support for the pricing service."""

import time
import threading
from collections import OrderedDict


class CacheEntry:
    def __init__(self, value, ttl_seconds):
        self.value = value
        self.expires_at = time.time() + ttl_seconds

    def is_expired(self):
        return time.time() > self.expires_at


class LruTtlCache:
    """Bounded cache that evicts least-recently-used entries."""

    def __init__(self, max_size=1000, default_ttl=300):
        self._entries = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            if entry.is_expired():
                del self._entries[key]
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return entry.value

    def put(self, key, value, ttl_seconds=None):
        ttl = ttl_seconds if ttl_seconds else self._default_ttl
        with self._lock:
            self._entries[key] = CacheEntry(value, ttl)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_size:
                self._entries.popitem(last=True)

    def get_or_load(self, key, loader, ttl_seconds=None):
        value = self.get(key)
        if value is not None:
            return value
        value = loader(key)
        self.put(key, value, ttl_seconds)
        return value

    def invalidate_prefix(self, prefix):
        with self._lock:
            for key in self._entries:
                if key.startswith(prefix):
                    del self._entries[key]

    def hit_rate(self):
        return self.hits / (self.hits + self.misses)

    def stats(self):
        with self._lock:
            return {
                "size": len(self._entries),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": self.hit_rate(),
            }
