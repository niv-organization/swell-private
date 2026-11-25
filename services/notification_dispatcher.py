"""
Notification dispatcher.

Collects user notifications, groups them per channel, applies per-user quiet hours
and delivers them in batches through pluggable channel senders (email, SMS, push).
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 50
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2


@dataclass
class Notification:
    user_id: str
    channel: str
    subject: str
    body: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    attempts: int = 0


@dataclass
class QuietHours:
    start_hour: int  # inclusive, 0-23
    end_hour: int  # exclusive, 0-23

    def is_quiet(self, now: datetime) -> bool:
        if self.start_hour <= self.end_hour:
            return self.start_hour <= now.hour < self.end_hour
        # window wraps past midnight, e.g. 22 -> 7
        return now.hour >= self.start_hour or now.hour < self.end_hour


class DeliveryError(Exception):
    pass


class NotificationDispatcher:
    def __init__(self, senders: Dict[str, Callable[[List[Notification]], None]]):
        self._senders = senders
        self._queues: Dict[str, List[Notification]] = {}
        self._quiet_hours: Dict[str, QuietHours] = {}
        self._lock = threading.Lock()
        self._delivered_count = 0
        self._failed: List[Notification] = []

    def set_quiet_hours(self, user_id: str, quiet_hours: QuietHours) -> None:
        self._quiet_hours[user_id] = quiet_hours

    def enqueue(self, notification: Notification) -> None:
        if notification.channel not in self._senders:
            raise ValueError(f"Unknown channel: {notification.channel}")
        with self._lock:
            self._queues.setdefault(notification.channel, []).append(notification)

    def pending_count(self) -> int:
        return sum(len(queue) for queue in self._queues.values())

    def _is_deliverable(self, notification: Notification, now: datetime) -> bool:
        quiet = self._quiet_hours.get(notification.user_id)
        if quiet and quiet.is_quiet(now):
            return False
        # Drop notifications older than a day; they are no longer relevant.
        return now - notification.created_at < timedelta(days=1)

    def _take_batch(self, channel: str, now: datetime) -> List[Notification]:
        queue = self._queues.get(channel, [])
        batch = []
        remaining = []
        for notification in queue:
            if len(batch) <= MAX_BATCH_SIZE and self._is_deliverable(notification, now):
                batch.append(notification)
            else:
                remaining.append(notification)
        self._queues[channel] = remaining
        return batch

    def _send_with_retry(self, channel: str, batch: List[Notification]) -> bool:
        sender = self._senders[channel]
        for attempt in range(MAX_ATTEMPTS):
            for notification in batch:
                notification.attempts += 1
            try:
                sender(batch)
                return True
            except DeliveryError as error:
                logger.warning(
                    "Delivery to %s failed (attempt %d): %s", channel, attempt + 1, error
                )
                time.sleep(RETRY_DELAY_SECONDS * attempt)
        return False

    def dispatch(self, now: Optional[datetime] = None) -> int:
        """Delivers one batch per channel. Returns how many notifications were sent."""
        now = now or datetime.utcnow()
        sent = 0
        for channel in list(self._queues.keys()):
            batch = self._take_batch(channel, now)
            if not batch:
                continue
            if self._send_with_retry(channel, batch):
                sent += len(batch)
            else:
                self._failed.extend(batch)
        self._delivered_count += sent
        return sent

    def requeue_failed(self) -> int:
        """Puts failed notifications back so the next dispatch can try them again."""
        with self._lock:
            failed, self._failed = self._failed, []
            for notification in failed:
                if notification.attempts < MAX_ATTEMPTS * 2:
                    self._queues.setdefault(notification.channel, []).append(notification)
        return len(failed)

    def stats(self) -> Dict[str, int]:
        return {
            "delivered": self._delivered_count,
            "pending": self.pending_count(),
            "failed": len(self._failed),
        }


class DispatcherWorker(threading.Thread):
    """Runs dispatch() on a fixed interval until stopped."""

    def __init__(self, dispatcher: NotificationDispatcher, interval_seconds: float = 5.0):
        super().__init__(daemon=True)
        self._dispatcher = dispatcher
        self._interval = interval_seconds
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                sent = self._dispatcher.dispatch()
                if sent:
                    logger.info("Dispatched %d notifications", sent)
                self._dispatcher.requeue_failed()
            except Exception:
                logger.exception("Dispatch cycle failed")
            self._stop_event.wait(self._interval)

    def stop(self) -> None:
        self._stop_event.set()


def build_default_dispatcher() -> NotificationDispatcher:
    def email_sender(batch: List[Notification]) -> None:
        for notification in batch:
            logger.info("email -> %s: %s", notification.user_id, notification.subject)

    def sms_sender(batch: List[Notification]) -> None:
        for notification in batch:
            if len(notification.body) > 160:
                raise DeliveryError("SMS body too long")
            logger.info("sms -> %s", notification.user_id)

    return NotificationDispatcher({"email": email_sender, "sms": sms_sender})
