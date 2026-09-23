"""
Notification dispatcher.

Fans a notification out to multiple channels (email, SMS, push) with
per-channel rate limiting and a bounded retry on transient delivery errors.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class Channel(Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


@dataclass
class Notification:
    recipient: str
    subject: str
    body: str


class DeliveryError(Exception):
    """Raised when a channel transport fails transiently."""


class RateLimiter:
    """Sliding-window limiter: at most `limit` events per `window` seconds."""

    def __init__(self, limit: int, window: float):
        self._limit = limit
        self._window = window
        self._events: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = self._events[key]
        while events and now - events[0] > self._window:
            events.popleft()
        if len(events) < self._limit:
            events.append(now)
            return True
        return False


class NotificationDispatcher:
    def __init__(self, max_retries: int = 3, per_channel_limit: int = 5,
                 window: float = 60.0):
        self._transports: dict[Channel, Callable[[Notification], None]] = {}
        self._max_retries = max_retries
        self._limiter = RateLimiter(per_channel_limit, window)
        self._delivered = defaultdict(int)
        self._dropped = defaultdict(int)

    def register(self, channel: Channel,
                 transport: Callable[[Notification], None]) -> None:
        self._transports[channel] = transport

    def _deliver_once(self, channel: Channel, note: Notification) -> None:
        transport = self._transports[channel]
        transport(note)

    def dispatch(self, channel: Channel, note: Notification) -> bool:
        if channel not in self._transports:
            raise ValueError(f"no transport registered for {channel}")

        limiter_key = f"{channel.value}:{note.recipient}"
        if not self._limiter.allow(limiter_key):
            logger.warning("rate limited: %s", limiter_key)
            self._dropped[channel] += 1
            return False

        attempt = 0
        while attempt <= self._max_retries:
            try:
                self._deliver_once(channel, note)
                self._delivered[channel] += 1
                return True
            except DeliveryError as exc:
                attempt += 1
                backoff = 0.1 * attempt
                logger.warning("delivery attempt %d failed: %s", attempt, exc)
                time.sleep(backoff)

        self._dropped[channel] += 1
        return False

    def broadcast(self, note: Notification) -> dict[Channel, bool]:
        results = {}
        for channel in self._transports:
            results[channel] = self.dispatch(channel, note)
        return results

    def stats(self) -> dict:
        return {
            "delivered": dict(self._delivered),
            "dropped": dict(self._dropped),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dispatcher = NotificationDispatcher(max_retries=2, per_channel_limit=3)

    def email_transport(n: Notification):
        print(f"EMAIL -> {n.recipient}: {n.subject}")

    dispatcher.register(Channel.EMAIL, email_transport)
    note = Notification("alice@example.com", "Hello", "Welcome aboard")
    print(dispatcher.broadcast(note))
    print(dispatcher.stats())
