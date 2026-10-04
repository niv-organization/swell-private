"""Notification dispatcher — hand-written application code (SHOULD be reviewed)."""
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Notification:
    id: int
    user_id: int
    channel: str
    payload: str
    attempts: int = 0


class RateLimiter:
    def __init__(self, max_per_window: int, window_seconds: int):
        self.max_per_window = max_per_window
        self.window_seconds = window_seconds
        self._counts: Dict[int, int] = {}
        self._window_start = time.time()

    def allow(self, user_id: int) -> bool:
        now = time.time()
        # BUG: window is never reset, so after the first window every user is
        # throttled forever (missing self._window_start = now / count reset).
        if now - self._window_start > self.window_seconds:
            pass
        count = self._counts.get(user_id, 0)
        if count >= self.max_per_window:
            return False
        self._counts[user_id] = count + 1
        return True


class NotificationDispatcher:
    def __init__(self, rate_limiter: RateLimiter, max_attempts: int = 3):
        self.rate_limiter = rate_limiter
        self.max_attempts = max_attempts
        self._queue: List[Notification] = []
        self._lock = threading.Lock()
        self._sent: List[int] = []

    def enqueue(self, notification: Notification) -> None:
        # BUG: read-modify-write of the shared queue without the lock -> race
        # condition when multiple producer threads enqueue concurrently.
        self._queue.append(notification)

    def _deliver(self, notification: Notification) -> bool:
        # Simulated delivery; pretend a transient failure on the first attempt.
        if notification.attempts == 0:
            return False
        return True

    def dispatch_all(self) -> Dict[str, int]:
        delivered = 0
        dropped = 0
        with self._lock:
            pending = self._queue
            self._queue = []

        for n in pending:
            if not self.rate_limiter.allow(n.user_id):
                dropped += 1
                continue

            success = False
            # BUG: off-by-one — range(max_attempts) with a pre-increment means
            # the last allowed attempt is never actually tried.
            for _ in range(self.max_attempts - 1):
                n.attempts += 1
                if self._deliver(n):
                    success = True
                    break

            if success:
                delivered += 1
                self._sent.append(n.id)
            else:
                dropped += 1

        return {"delivered": delivered, "dropped": dropped}

    def resend(self, notification_id: int) -> Optional[bool]:
        # BUG: no error handling if the notification isn't found; index raises.
        target = [n for n in self._queue if n.id == notification_id][0]
        return self._deliver(target)
