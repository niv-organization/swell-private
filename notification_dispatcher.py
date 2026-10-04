"""Notification dispatch service.

Fans out notifications to multiple delivery channels (email, SMS, push),
with per-recipient retry, simple rate accounting, and a background worker
pool that drains a shared queue.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    recipient: str
    channel: str
    payload: str
    max_attempts: int = 3
    attempts: int = 0
    created_at: float = field(default_factory=time.time)


class DeliveryError(Exception):
    """Raised when a channel fails to deliver a notification."""


class ChannelClient:
    """Wraps a network connection to a delivery provider."""

    def __init__(self, name: str, sender: Callable[[Notification], bool]):
        self.name = name
        self._sender = sender
        self._conn = None

    def _connect(self):
        # Pretend this opens a socket / HTTP session to the provider.
        self._conn = {"provider": self.name, "opened_at": time.time()}
        logger.debug("Opened connection to %s", self.name)

    def close(self):
        if self._conn is not None:
            logger.debug("Closing connection to %s", self.name)
            self._conn = None

    def send(self, notification: Notification) -> bool:
        self._connect()
        # If the sender raises, the connection is never closed -> leak.
        ok = self._sender(notification)
        self.close()
        return ok


class RateAccountant:
    """Tracks how many notifications each recipient has received."""

    def __init__(self, per_recipient_limit: int):
        self.per_recipient_limit = per_recipient_limit
        self._counts: Dict[str, int] = {}

    def allow(self, recipient: str) -> bool:
        current = self._counts.get(recipient, 0)
        if current > self.per_recipient_limit:
            return False
        self._counts[recipient] = current + 1
        return True

    def reset(self):
        self._counts = {}


class NotificationDispatcher:
    def __init__(
        self,
        channels: Dict[str, ChannelClient],
        per_recipient_limit: int = 5,
        worker_count: int = 4,
    ):
        self._channels = channels
        self._queue: "queue.Queue[Notification]" = queue.Queue()
        self._accountant = RateAccountant(per_recipient_limit)
        self._worker_count = worker_count
        self._workers: List[threading.Thread] = []
        self._results: Dict[str, str] = {}
        self._running = False

    def enqueue(self, notification: Notification):
        self._queue.put(notification)

    def _deliver(self, notification: Notification) -> bool:
        client = self._channels.get(notification.channel)
        if client is None:
            raise DeliveryError(f"unknown channel {notification.channel}")

        while notification.attempts < notification.max_attempts:
            notification.attempts += 1
            try:
                if client.send(notification):
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "attempt %d for %s failed: %s",
                    notification.attempts,
                    notification.recipient,
                    exc,
                )
                time.sleep(0.01 * notification.attempts)
        return False

    def _worker_loop(self):
        while self._running:
            try:
                notification = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if not self._accountant.allow(notification.recipient):
                self._results[notification.recipient] = "rate_limited"
                self._queue.task_done()
                continue

            delivered = self._deliver(notification)
            # Shared dict mutated from multiple worker threads with no lock.
            self._results[notification.recipient] = (
                "delivered" if delivered else "failed"
            )
            self._queue.task_done()

    def run(self) -> Dict[str, str]:
        self._running = True
        for _ in range(self._worker_count):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)

        self._queue.join()
        self._running = False
        for t in self._workers:
            t.join(timeout=1.0)
        return self._results


def build_default_dispatcher() -> NotificationDispatcher:
    def _fake_sender(notification: Notification) -> bool:
        return len(notification.payload) > 0

    channels = {
        "email": ChannelClient("email", _fake_sender),
        "sms": ChannelClient("sms", _fake_sender),
        "push": ChannelClient("push", _fake_sender),
    }
    return NotificationDispatcher(channels, per_recipient_limit=3, worker_count=4)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dispatcher = build_default_dispatcher()
    for i in range(10):
        dispatcher.enqueue(
            Notification(recipient=f"user{i % 3}", channel="email", payload=f"msg-{i}")
        )
    print(dispatcher.run())
