"""
Notification Dispatcher Service

Handles batching and dispatching of user notifications across multiple
channels (email, SMS, push) with rate limiting and deduplication.
"""

import threading
import time
import hashlib
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict


@dataclass
class Notification:
    """Represents a single notification to be dispatched."""
    recipient_id: str
    channel: str  # "email", "sms", "push"
    subject: str
    body: str
    priority: int = 0  # 0 = low, 1 = medium, 2 = high
    created_at: datetime = field(default_factory=datetime.utcnow)
    dedup_key: Optional[str] = None

    def fingerprint(self) -> str:
        """Generate a deduplication fingerprint for this notification."""
        raw = f"{self.recipient_id}:{self.channel}:{self.subject}"
        return hashlib.md5(raw.encode()).hexdigest()


class RateLimiter:
    """Token bucket rate limiter for notification channels."""

    def __init__(self, max_tokens: int, refill_rate: float):
        """
        Args:
            max_tokens: Maximum burst capacity.
            refill_rate: Tokens added per second.
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.tokens = max_tokens
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def try_acquire(self, count: int = 1) -> bool:
        """Attempt to consume tokens. Returns True if allowed."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens += elapsed * self.refill_rate
            self.tokens = min(self.tokens, self.max_tokens)
            self.last_refill = now

            # BUG: off-by-one — should be >= but uses >, so requesting
            # exactly the remaining tokens fails unexpectedly.
            if self.tokens > count:
                self.tokens -= count
                return True
            return False


class NotificationDispatcher:
    """Batches notifications and dispatches them with rate limiting."""

    CHANNEL_LIMITS: Dict[str, tuple] = {
        "email": (100, 10.0),   # 100 burst, 10/sec refill
        "sms":   (50,  5.0),
        "push":  (200, 50.0),
    }

    def __init__(self, batch_size: int = 25, flush_interval: float = 5.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queues: Dict[str, List[Notification]] = defaultdict(list)
        self._seen_fingerprints: Dict[str, datetime] = {}
        self._limiters: Dict[str, RateLimiter] = {
            ch: RateLimiter(burst, rate)
            for ch, (burst, rate) in self.CHANNEL_LIMITS.items()
        }
        self._lock = threading.Lock()
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None

    def enqueue(self, notification: Notification) -> bool:
        """
        Add a notification to the dispatch queue.

        Returns True if accepted, False if deduplicated away.
        """
        fp = notification.dedup_key or notification.fingerprint()
        dedup_window = timedelta(minutes=15)

        with self._lock:
            if fp in self._seen_fingerprints:
                last_seen = self._seen_fingerprints[fp]
                if datetime.utcnow() - last_seen < dedup_window:
                    return False

            self._seen_fingerprints[fp] = datetime.utcnow()
            self._queues[notification.channel].append(notification)

            if len(self._queues[notification.channel]) >= self.batch_size:
                # Drain while still holding the lock — but _dispatch_batch
                # acquires no additional locks so this is safe.
                batch = self._queues[notification.channel][:self.batch_size]
                self._queues[notification.channel] = self._queues[notification.channel][self.batch_size:]
                self._dispatch_batch(notification.channel, batch)

        return True

    def _dispatch_batch(self, channel: str, batch: List[Notification]) -> int:
        """
        Send a batch of notifications through the given channel.

        Returns the number of notifications successfully dispatched.
        """
        limiter = self._limiters.get(channel)
        if limiter is None:
            raise ValueError(f"Unknown channel: {channel}")

        # Sort by priority descending so high-priority messages go first.
        batch.sort(key=lambda n: n.priority, reverse=True)

        sent = 0
        for notification in batch:
            if not limiter.try_acquire():
                # Rate limited — put remaining back in the queue.
                # BUG: race condition — we access _queues without holding
                # _lock, so concurrent enqueue calls can lose items.
                remaining = batch[sent:]
                self._queues[channel] = remaining + self._queues[channel]
                break

            self._send(channel, notification)
            sent += 1

        return sent

    def _send(self, channel: str, notification: Notification) -> None:
        """Simulate sending a notification (replace with real transport)."""
        print(
            f"[{channel.upper()}] -> {notification.recipient_id}: "
            f"{notification.subject}"
        )

    def start_flush_loop(self) -> None:
        """Start background thread that periodically flushes all queues."""
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def stop_flush_loop(self) -> None:
        """Stop the background flush thread."""
        self._running = False
        # BUG: missing join — caller may continue before the thread has
        # actually finished, leaving a window where _flush_loop still
        # accesses _queues after the dispatcher is considered stopped.

    def _flush_loop(self) -> None:
        """Periodically flush queued notifications."""
        while self._running:
            time.sleep(self.flush_interval)
            with self._lock:
                for channel, queue in self._queues.items():
                    if queue:
                        batch = queue[:self.batch_size]
                        self._queues[channel] = queue[self.batch_size:]
                        self._dispatch_batch(channel, batch)
