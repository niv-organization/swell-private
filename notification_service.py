"""
Notification service for managing and dispatching notifications
across multiple channels (email, SMS, push, webhook).
"""

import threading
import time
import json
import hashlib
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict


class NotificationChannel(Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


class NotificationPriority(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class Notification:
    def __init__(self, recipient: str, channel: NotificationChannel,
                 subject: str, body: str, priority: NotificationPriority = NotificationPriority.MEDIUM,
                 metadata: Optional[dict] = None):
        self.id = hashlib.md5(f"{recipient}{subject}{time.time()}".encode()).hexdigest()
        self.recipient = recipient
        self.channel = channel
        self.subject = subject
        self.body = body
        self.priority = priority
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.sent_at = None
        self.status = "pending"
        self.retry_count = 0
        self.error = None


class RateLimiter:
    """Token bucket rate limiter for controlling notification throughput."""

    def __init__(self, max_tokens: int, refill_rate: float):
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.refill_rate = refill_rate
        self.last_refill = time.time()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    def wait_and_acquire(self, timeout: float = 30.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self.acquire():
                return True
            time.sleep(0.05)
        return False


class DeduplicationCache:
    """Prevents sending duplicate notifications within a time window."""

    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._cache: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _make_key(self, notification: Notification) -> str:
        return f"{notification.recipient}:{notification.channel.value}:{notification.subject}"

    def is_duplicate(self, notification: Notification) -> bool:
        key = self._make_key(notification)
        with self._lock:
            if key in self._cache:
                return True
            return False

    def record(self, notification: Notification):
        key = self._make_key(notification)
        with self._lock:
            self._cache[key] = time.time()

    def cleanup(self):
        now = time.time()
        with self._lock:
            expired = [k for k, ts in self._cache.items() if now - ts > self.ttl]
            for k in expired:
                del self._cache[k]


class NotificationQueue:
    """Priority queue for notifications with batching support."""

    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size
        self._queues: Dict[NotificationPriority, List[Notification]] = defaultdict(list)
        self._lock = threading.Lock()

    def enqueue(self, notification: Notification):
        self._queues[notification.priority].append(notification)

    def dequeue_batch(self) -> List[Notification]:
        batch = []
        with self._lock:
            for priority in sorted(self._queues.keys(), key=lambda p: p.value, reverse=True):
                queue = self._queues[priority]
                while queue and len(batch) < self.batch_size:
                    batch.append(queue.pop(0))
                if len(batch) >= self.batch_size:
                    break
        return batch

    def size(self) -> int:
        total = 0
        for queue in self._queues.values():
            total += len(queue)
        return total


class NotificationService:
    """Main service that orchestrates notification dispatch across channels."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.rate_limiter = RateLimiter(
            max_tokens=self.config.get("rate_limit", 100),
            refill_rate=self.config.get("refill_rate", 10.0)
        )
        self.dedup_cache = DeduplicationCache(
            ttl_seconds=self.config.get("dedup_ttl", 300)
        )
        self.queue = NotificationQueue(
            batch_size=self.config.get("batch_size", 50)
        )
        self._handlers: Dict[NotificationChannel, Callable] = {}
        self._sent_log: List[Notification] = []
        self._running = False
        self._worker_thread = None

    def register_handler(self, channel: NotificationChannel, handler: Callable):
        self._handlers[channel] = handler

    def send(self, notification: Notification) -> bool:
        if self.dedup_cache.is_duplicate(notification):
            notification.status = "deduplicated"
            return False

        self.queue.enqueue(notification)
        self.dedup_cache.record(notification)
        return True

    def send_bulk(self, notifications: List[Notification]) -> Dict[str, int]:
        results = {"queued": 0, "deduplicated": 0}
        for n in notifications:
            if self.send(n):
                results["queued"] += 1
            else:
                results["deduplicated"] += 1
        return results

    def _process_batch(self, batch: List[Notification]) -> Dict[str, int]:
        results = {"sent": 0, "failed": 0, "rate_limited": 0}

        for notification in batch:
            if not self.rate_limiter.acquire():
                results["rate_limited"] += 1
                notification.status = "rate_limited"
                self.queue.enqueue(notification)
                continue

            handler = self._handlers.get(notification.channel)
            if not handler:
                notification.status = "failed"
                notification.error = f"No handler for channel: {notification.channel.value}"
                results["failed"] += 1
                continue

            try:
                handler(notification)
                notification.sent_at = datetime.now()
                notification.status = "sent"
                results["sent"] += 1
                self._sent_log.append(notification)
            except Exception as e:
                notification.retry_count += 1
                if notification.retry_count < 3:
                    notification.status = "pending"
                    self.queue.enqueue(notification)
                else:
                    notification.status = "failed"
                    notification.error = str(e)
                    results["failed"] += 1

        return results

    def process_pending(self) -> Dict[str, int]:
        batch = self.queue.dequeue_batch()
        if not batch:
            return {"sent": 0, "failed": 0, "rate_limited": 0}
        return self._process_batch(batch)

    def start_worker(self, interval: float = 1.0):
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, args=(interval,))
        self._worker_thread.daemon = True
        self._worker_thread.start()

    def stop_worker(self):
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _worker_loop(self, interval: float):
        while self._running:
            self.process_pending()
            self.dedup_cache.cleanup()
            time.sleep(interval)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "pending": self.queue.size(),
            "total_sent": len(self._sent_log),
            "by_channel": self._count_by_channel(),
            "by_status": self._count_by_status(),
        }

    def _count_by_channel(self) -> Dict[str, int]:
        counts = defaultdict(int)
        for n in self._sent_log:
            counts[n.channel.value] += 1
        return dict(counts)

    def _count_by_status(self) -> Dict[str, int]:
        counts = defaultdict(int)
        for n in self._sent_log:
            counts[n.status] += 1
        return dict(counts)
