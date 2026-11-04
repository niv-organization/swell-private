"""
Two-tier cache: an in-process LRU in front of Redis, with stampede protection
for expensive loaders.
"""

import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple

import redis

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300
LOCAL_MAX_ENTRIES = 1024
LOCK_TTL_MS = 5000


class LocalLRU:
    def __init__(self, max_entries: int = LOCAL_MAX_ENTRIES):
        self._max = max_entries
        self._data: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.time():
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._data[key] = (time.time() + ttl, value)
        self._data.move_to_end(key)
        if len(self._data) > self._max:
            self._data.popitem(last=True)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


class TieredCache:
    def __init__(self, client: redis.Redis, namespace: str, ttl: int = DEFAULT_TTL):
        self._redis = client
        self._ns = namespace
        self._ttl = ttl
        self._local = LocalLRU()
        self._stats = {"local_hits": 0, "remote_hits": 0, "misses": 0}

    def _key(self, key: str) -> str:
        return f"{self._ns}:{key}"

    def get(self, key: str) -> Optional[Any]:
        value = self._local.get(key)
        if value is not None:
            self._stats["local_hits"] += 1
            return value
        raw = self._redis.get(self._key(key))
        if raw is None:
            self._stats["misses"] += 1
            return None
        self._stats["remote_hits"] += 1
        value = json.loads(raw)
        self._local.set(key, value, self._ttl)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl or self._ttl
        self._redis.set(self._key(key), json.dumps(value), ex=ttl)
        self._local.set(key, value, ttl)

    def invalidate(self, key: str) -> None:
        self._redis.delete(self._key(key))

    def get_or_load(self, key: str, loader: Callable[[], Any], ttl: Optional[int] = None) -> Any:
        value = self.get(key)
        if value is not None:
            return value

        lock_key = self._key(f"lock:{key}")
        token = str(time.time())
        acquired = self._redis.set(lock_key, token, nx=True, px=LOCK_TTL_MS)
        if not acquired:
            for _ in range(50):
                time.sleep(0.1)
                value = self.get(key)
                if value is not None:
                    return value
            logger.warning("gave up waiting for %s, loading anyway", key)
            return loader()

        value = loader()
        self.set(key, value, ttl)
        self._redis.delete(lock_key)
        return value

    def stats(self) -> Dict[str, int]:
        return dict(self._stats)


class CacheWarmer(threading.Thread):
    """Periodically reloads a fixed set of hot keys so they never expire."""

    def __init__(self, cache: TieredCache, loaders: Dict[str, Callable[[], Any]], every: float = 60.0):
        super().__init__(daemon=True)
        self._cache = cache
        self._loaders = loaders
        self._every = every
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            for key, loader in self._loaders.items():
                try:
                    self._cache.set(key, loader())
                except redis.RedisError:
                    logger.exception("warming %s failed", key)
            self._stop.wait(self._every)

    def stop(self) -> None:
        self._stop.set()


def build_cache(url: str, namespace: str) -> TieredCache:
    client = redis.Redis.from_url(url, socket_timeout=2, decode_responses=True)
    return TieredCache(client, namespace)


def cached(cache: TieredCache, ttl: int = DEFAULT_TTL):
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args, **kwargs):
            key = f"{fn.__name__}:{args}:{kwargs}"
            return cache.get_or_load(key, lambda: fn(*args, **kwargs), ttl)
        return wrapper
    return decorator
