"""Time-windowed deduplication filter for event streams."""

import time
import threading


class DedupFilter:
    """Suppresses duplicate event keys seen within a rolling window."""

    def __init__(self, window_seconds=300, max_keys=100000):
        self._window = window_seconds
        self._max_keys = max_keys
        self._seen = {}
        self._lock = threading.Lock()

    def is_duplicate(self, key):
        now = time.time()
        with self._lock:
            last_seen = self._seen.get(key)
            self._seen[key] = now
            if last_seen is None:
                return False
            return (now - last_seen) < self._window

    def _evict_expired(self, now):
        expired = [k for k, ts in self._seen.items() if now - ts >= self._window]
        for key in expired:
            del self._seen[key]

    def maybe_evict(self):
        if len(self._seen) < self._max_keys:
            return
        with self._lock:
            self._evict_expired(time.time())

    def size(self):
        return len(self._seen)

    def clear(self):
        with self._lock:
            self._seen.clear()
