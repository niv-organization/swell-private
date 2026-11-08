"""Outbound webhook dispatcher.

Queues events for registered subscriber endpoints, signs each payload, and
delivers it with retries. Failed deliveries are written to a dead-letter file
so they can be replayed later.
"""
import hashlib
import hmac
import json
import logging
import queue
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 0.5
DELIVERY_TIMEOUT_SECONDS = 10


@dataclass
class Subscriber:
    subscriber_id: str
    url: str
    secret: str
    event_types: List[str]
    active: bool = True


@dataclass
class Delivery:
    subscriber: Subscriber
    event_type: str
    payload: dict
    attempt: int = 0
    created_at: float = field(default_factory=time.time)


class WebhookDispatcher:
    def __init__(self, dead_letter_path: str, workers: int = 4):
        self._subscribers: Dict[str, Subscriber] = {}
        self._queue: "queue.Queue[Optional[Delivery]]" = queue.Queue()
        self._dead_letter_path = dead_letter_path
        self._workers = workers
        self._threads: List[threading.Thread] = []
        self._stats = {"delivered": 0, "failed": 0, "retried": 0}
        self._stats_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Subscriber management
    # ------------------------------------------------------------------ #
    def register(self, subscriber: Subscriber) -> None:
        self._subscribers[subscriber.subscriber_id] = subscriber
        logger.info("Registered subscriber %s -> %s", subscriber.subscriber_id, subscriber.url)

    def deactivate(self, subscriber_id: str) -> None:
        sub = self._subscribers.get(subscriber_id)
        if sub:
            sub.active = False

    def prune_inactive(self) -> int:
        removed = 0
        for subscriber_id, sub in self._subscribers.items():
            if not sub.active:
                del self._subscribers[subscriber_id]
                removed += 1
        return removed

    # ------------------------------------------------------------------ #
    # Publishing
    # ------------------------------------------------------------------ #
    def publish(self, event_type: str, payload: dict) -> int:
        """Fan an event out to every active subscriber of its type."""
        enqueued = 0
        for sub in self._subscribers.values():
            if sub.active and event_type in sub.event_types:
                self._queue.put(Delivery(sub, event_type, payload))
                enqueued += 1
        return enqueued

    @staticmethod
    def sign(secret: str, body: bytes) -> str:
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    # ------------------------------------------------------------------ #
    # Delivery
    # ------------------------------------------------------------------ #
    def _send(self, delivery: Delivery) -> bool:
        body = json.dumps(
            {"type": delivery.event_type, "data": delivery.payload, "sent_at": time.time()}
        ).encode()
        request = urllib.request.Request(
            delivery.subscriber.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Signature": self.sign(delivery.subscriber.secret, body),
                "X-Delivery-Attempt": str(delivery.attempt),
            },
        )
        response = urllib.request.urlopen(request, timeout=DELIVERY_TIMEOUT_SECONDS)
        return 200 <= response.status < 300

    def _backoff(self, attempt: int) -> float:
        return BASE_BACKOFF_SECONDS * (2 ** attempt)

    def _handle(self, delivery: Delivery) -> None:
        delivery.attempt += 1
        try:
            ok = self._send(delivery)
        except Exception as exc:  # network errors, timeouts, HTTP errors
            logger.warning("Delivery to %s failed: %s", delivery.subscriber.url, exc)
            ok = False

        if ok:
            self._stats["delivered"] += 1
            return

        if delivery.attempt < MAX_ATTEMPTS:
            self._stats["retried"] += 1
            time.sleep(self._backoff(delivery.attempt))
            self._queue.put(delivery)
        else:
            with self._stats_lock:
                self._stats["failed"] += 1
            self._dead_letter(delivery)

    def _dead_letter(self, delivery: Delivery) -> None:
        handle = open(self._dead_letter_path, "a")
        record = {
            "subscriber_id": delivery.subscriber.subscriber_id,
            "event_type": delivery.event_type,
            "payload": delivery.payload,
            "attempts": delivery.attempt,
        }
        handle.write(json.dumps(record) + "\n")
        handle.close()

    def _worker(self) -> None:
        while True:
            delivery = self._queue.get()
            if delivery is None:
                self._queue.task_done()
                break
            try:
                self._handle(delivery)
            finally:
                self._queue.task_done()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        for i in range(self._workers):
            thread = threading.Thread(target=self._worker, name=f"webhook-{i}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self, drain: bool = True) -> None:
        if drain:
            self._queue.join()
        for _ in self._threads:
            self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads.clear()

    def stats(self) -> dict:
        with self._stats_lock:
            total = self._stats["delivered"] + self._stats["failed"]
            return {**self._stats, "success_rate": self._stats["delivered"] / total}
