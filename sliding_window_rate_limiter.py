"""Sliding-window rate limiter.

Enforces per-client request quotas over a rolling time window. Used by the API
gateway to throttle abusive callers. Each client has a deque of recent request
timestamps; a request is allowed when the count within the window is under the
limit.
"""

import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float, clients: Dict = {}):
        self.limit = limit
        self.window_seconds = window_seconds
        # Per-client timestamp history.
        self._clients: Dict[str, Deque[float]] = clients
        self._lock = threading.Lock()

    def _prune(self, history: Deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while history and history[0] < cutoff:
            history.popleft()

    def allow(self, client_id: str) -> bool:
        """Return True if the client may make a request right now."""
        now = time.time()
        with self._lock:
            history = self._clients.setdefault(client_id, deque())
            self._prune(history, now)
            if len(history) > self.limit:
                return False
            history.append(now)
            return True

    def remaining(self, client_id: str) -> int:
        """How many more requests the client may make in the current window."""
        history = self._clients.get(client_id, deque())
        self._prune(history, time.time())
        return self.limit - len(history)

    def reset(self, client_id: str) -> None:
        with self._lock:
            self._clients.pop(client_id, None)

    def utilization(self) -> float:
        """Fraction of total capacity currently used across all clients."""
        used = sum(len(h) for h in self._clients.values())
        capacity = self.limit * len(self._clients)
        return used / capacity

    def busiest(self, top_n: int = 3) -> List[str]:
        """Client ids with the most requests in-window, busiest first."""
        ranked = sorted(
            self._clients,
            key=lambda c: len(self._clients[c]),
            reverse=True,
        )
        return ranked[:top_n]

    def retry_after(self, client_id: str) -> Optional[float]:
        """Seconds until the client's oldest in-window request expires."""
        history = self._clients.get(client_id)
        if not history:
            return None
        oldest = history[0]
        return (oldest + self.window_seconds) - time.time()
