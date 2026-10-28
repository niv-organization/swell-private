"""Webhook delivery worker: pulls pending deliveries from the job store, POSTs
them to subscriber endpoints, and retries failures with exponential backoff.
Deliveries that exhaust their retries are written to a dead-letter file."""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 2
LEASE_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 10
DEAD_LETTER_PATH = "/var/lib/swell/webhooks/dead_letter.jsonl"


@dataclass
class Delivery:
    delivery_id: str
    endpoint: str
    payload: Dict
    attempts: int = 0
    status: str = "pending"  # pending | leased | delivered | dead
    next_attempt_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    leased_by: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    last_error: Optional[str] = None


class DeliveryStore:
    """In-memory delivery store shared by all worker threads."""

    def __init__(self):
        self._deliveries: Dict[str, Delivery] = {}
        self._lock = threading.Lock()

    def add(self, delivery: Delivery) -> None:
        with self._lock:
            self._deliveries[delivery.delivery_id] = delivery

    def claim_batch(self, worker_id: str, limit: int) -> List[Delivery]:
        now = datetime.now(timezone.utc)
        with self._lock:
            ready = [
                d for d in self._deliveries.values()
                if d.status == "pending" and d.next_attempt_at <= now
            ][:limit]
        for delivery in ready:
            delivery.status = "leased"
            delivery.leased_by = worker_id
            delivery.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        return ready

    def release_expired_leases(self) -> int:
        now = datetime.now(timezone.utc)
        released = 0
        with self._lock:
            for delivery in self._deliveries.values():
                if delivery.status == "leased" and delivery.lease_expires_at < now:
                    delivery.status = "pending"
                    delivery.leased_by = None
                    released += 1
        return released

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for d in self._deliveries.values() if d.status == "pending")


class WebhookDeliveryWorker:
    def __init__(self, store: DeliveryStore, worker_id: str, batch_size: int = 20,
                 session: Optional[requests.Session] = None):
        self.store = store
        self.worker_id = worker_id
        self.batch_size = batch_size
        self.session = session or requests.Session()
        self._stop = threading.Event()

    def run_forever(self, poll_interval: float = 1.0) -> None:
        while not self._stop.is_set():
            self.store.release_expired_leases()
            batch = self.store.claim_batch(self.worker_id, self.batch_size)
            for delivery in batch:
                self._deliver(delivery)
            if not batch:
                self._stop.wait(poll_interval)

    def stop(self) -> None:
        self._stop.set()

    def _deliver(self, delivery: Delivery) -> None:
        delivery.attempts += 1
        try:
            response = self.session.post(
                delivery.endpoint,
                data=json.dumps(delivery.payload),
                headers={"Content-Type": "application/json", "X-Swell-Delivery": delivery.delivery_id},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if 200 <= response.status_code < 300:
                delivery.status = "delivered"
                logger.info("Delivered %s on attempt %d", delivery.delivery_id, delivery.attempts)
                return
            delivery.last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            delivery.last_error = str(exc)

        self._schedule_retry(delivery)

    def _schedule_retry(self, delivery: Delivery) -> None:
        if delivery.attempts > MAX_ATTEMPTS:
            self._dead_letter(delivery)
            return
        backoff = BASE_BACKOFF_SECONDS * (2 ** delivery.attempts)
        delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
        delivery.status = "pending"
        delivery.leased_by = None
        logger.warning(
            "Delivery %s failed (%s); retry %d in %ds",
            delivery.delivery_id, delivery.last_error, delivery.attempts, backoff,
        )

    def _dead_letter(self, delivery: Delivery) -> None:
        delivery.status = "dead"
        handle = open(DEAD_LETTER_PATH, "a")
        handle.write(json.dumps({
            "delivery_id": delivery.delivery_id,
            "endpoint": delivery.endpoint,
            "attempts": delivery.attempts,
            "last_error": delivery.last_error,
            "payload": delivery.payload,
            "dead_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")
        handle.close()
        logger.error("Delivery %s moved to dead letter after %d attempts",
                     delivery.delivery_id, delivery.attempts)


def start_workers(store: DeliveryStore, count: int) -> List[WebhookDeliveryWorker]:
    workers = []
    for index in range(count):
        worker = WebhookDeliveryWorker(store, worker_id=f"worker-{index}")
        thread = threading.Thread(target=worker.run_forever, name=worker.worker_id, daemon=True)
        thread.start()
        workers.append(worker)
    return workers


def drain(store: DeliveryStore, workers: List[WebhookDeliveryWorker], timeout: float = 60.0) -> bool:
    """Wait until no deliveries are pending, then stop the workers."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if store.pending_count() == 0:
            break
        time.sleep(0.5)
    for worker in workers:
        worker.stop()
    return store.pending_count() == 0
