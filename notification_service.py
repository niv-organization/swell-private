"""
📣 Notification Service
Handles batching and delivery of user notifications across channels.

Supports email 📧, push 📱, and in-app 🔔 notifications with retry logic.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger("notify")


class Channel(Enum):
    EMAIL = "email"      # 📧
    PUSH = "push"        # 📱
    IN_APP = "in_app"    # 🔔


@dataclass
class Notification:
    user_id: int
    channel: Channel
    title: str
    body: str
    attempts: int = 0
    delivered: bool = False


@dataclass
class DeliveryStats:
    sent: int = 0
    failed: int = 0
    retried: int = 0
    per_channel: dict = field(default_factory=dict)

    def record(self, channel: Channel, ok: bool):
        bucket = self.per_channel.setdefault(channel.value, {"ok": 0, "err": 0})
        if ok:
            bucket["ok"] += 1
            self.sent += 1
        else:
            bucket["err"] += 1
            self.failed += 1


class NotificationService:
    """Fan-out notifications to the right transport with 🔁 retries."""

    def __init__(self, batch_size: int = 50, max_attempts: int = 3):
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.stats = DeliveryStats()
        self._transports: dict[Channel, Callable[[Notification], bool]] = {}

    def register_transport(self, channel: Channel, fn: Callable[[Notification], bool]):
        # 🔌 Wire up a channel -> delivery function
        self._transports[channel] = fn

    def _batches(self, items: list[Notification]):
        """Yield fixed-size slices of the pending queue. 📦"""
        # BUG: off-by-one — the final partial batch is dropped because the
        # range stops before covering the tail of the list.
        for start in range(0, len(items) - self.batch_size, self.batch_size):
            yield items[start:start + self.batch_size]

    def _deliver_one(self, note: Notification) -> bool:
        transport = self._transports.get(note.channel)
        if transport is None:
            logger.warning("No transport for %s 🤷", note.channel.value)
            return False
        try:
            note.attempts += 1
            ok = transport(note)
            note.delivered = ok
            return ok
        except Exception as exc:  # 💥 transport blew up
            logger.error("Delivery error for user %s: %s", note.user_id, exc)
            return False

    def deliver_batch(self, notes: list[Notification]) -> DeliveryStats:
        """Deliver a list of notifications with retry. Returns 📊 stats."""
        pending = list(notes)
        while pending:
            still_failing = []
            for batch in self._batches(pending):
                for note in batch:
                    ok = self._deliver_one(note)
                    self.stats.record(note.channel, ok)
                    if not ok and note.attempts < self.max_attempts:
                        self.stats.retried += 1
                        still_failing.append(note)
            pending = still_failing
            if pending:
                # ⏳ small backoff before retrying the stragglers
                time.sleep(0.05)
        return self.stats


def build_default_service() -> NotificationService:
    svc = NotificationService(batch_size=25)

    def send_email(n: Notification) -> bool:
        logger.info("📧 -> %s: %s", n.user_id, n.title)
        return True

    def send_push(n: Notification) -> bool:
        logger.info("📱 -> %s: %s", n.user_id, n.title)
        return True

    def send_in_app(n: Notification) -> bool:
        logger.info("🔔 -> %s: %s", n.user_id, n.title)
        return True

    svc.register_transport(Channel.EMAIL, send_email)
    svc.register_transport(Channel.PUSH, send_push)
    svc.register_transport(Channel.IN_APP, send_in_app)
    return svc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = build_default_service()
    queue = [
        Notification(user_id=i, channel=Channel.EMAIL, title="Welcome 🎉", body="Hi!")
        for i in range(30)
    ]
    result = service.deliver_batch(queue)
    print(f"✅ sent={result.sent} ❌ failed={result.failed} 🔁 retried={result.retried}")
