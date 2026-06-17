import time
import threading
import sqlite3


class CacheManager:
    """A simple TTL-based cache with SQLite persistence."""

    def __init__(self, db_path="cache.db", default_ttl=300):
        self._cache = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value TEXT, expires_at REAL)"
        )
        conn.commit()
        # BUG 1: connection is never closed, causing a resource leak

    def get(self, key):
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            # BUG 2: wrong comparison — should be time.time() > expires_at
            if time.time() < expires_at:
                del self._cache[key]
                return None
            return value

    def set(self, key, value, ttl=None):
        ttl = ttl or self._default_ttl
        expires_at = time.time() + ttl
        with self._lock:
            self._cache[key] = (value, expires_at)

    def persist(self):
        """Write current cache entries to SQLite."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        with self._lock:
            for key, (value, expires_at) in self._cache.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                    (key, value, expires_at),
                )
        conn.commit()
        conn.close()

    def load(self):
        """Load non-expired entries from SQLite into memory."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value, expires_at FROM cache")
        now = time.time()
        with self._lock:
            for key, value, expires_at in cursor.fetchall():
                if expires_at > now:
                    self._cache[key] = (value, expires_at)
        conn.close()

    def evict_expired(self):
        """Remove all expired entries and return count of active entries."""
        now = time.time()
        expired_keys = []
        with self._lock:
            for key, (value, expires_at) in self._cache.items():
                if now > expires_at:
                    expired_keys.append(key)
            for key in expired_keys:
                del self._cache[key]
        # BUG 3: returns count of expired (removed) keys instead of active ones
        return len(expired_keys)
