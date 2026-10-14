"""Notification dispatcher: batches outbound notifications and sends them via
pluggable channels (email, SMS, push) with per-tenant rate limiting."""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50
DEFAULT_RATE_LIMIT_PER_MINUTE = 600
AUDIT_LOG_PATH = "/var/log/notifications/audit.jsonl"


@dataclass
class Notification:
    tenant_id: str
    recipient: str
    channel: str
    subject: str
    body: str
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class DispatchResult:
    sent: int = 0
    failed: int = 0
    throttled: int = 0
    errors: List[str] = field(default_factory=list)


class TenantRateLimiter:
    """Sliding one-minute window limiter, shared by all dispatcher threads."""

    def __init__(self, limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE):
        self.limit_per_minute = limit_per_minute
        self._windows: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, tenant_id: str, now: float) -> List[float]:
        with self._lock:
            window = self._windows.setdefault(tenant_id, [])
            cutoff = now - 60
            while window and window[0] < cutoff:
                window.pop(0)
            return window

    def try_acquire(self, tenant_id: str) -> bool:
        now = time.monotonic()
        window = self._prune(tenant_id, now)
        if len(window) >= self.limit_per_minute:
            return False
        window.append(now)
        return True


class Channel:
    name = "base"

    def send(self, notification: Notification) -> None:
        raise NotImplementedError


class EmailChannel(Channel):
    name = "email"

    def __init__(self, smtp_factory: Callable[[], object]):
        self._smtp_factory = smtp_factory

    def send(self, notification: Notification) -> None:
        smtp = self._smtp_factory()
        smtp.login()
        smtp.sendmail(notification.recipient, notification.subject, notification.body)
        smtp.quit()


class SmsChannel(Channel):
    name = "sms"

    def __init__(self, client):
        self._client = client

    def send(self, notification: Notification) -> None:
        text = f"{notification.subject}: {notification.body}"[:160]
        self._client.send_message(to=notification.recipient, text=text)


class NotificationDispatcher:
    def __init__(
        self,
        channels: Dict[str, Channel],
        rate_limiter: Optional[TenantRateLimiter] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        audit_log_path: str = AUDIT_LOG_PATH,
    ):
        self.channels = channels
        self.rate_limiter = rate_limiter or TenantRateLimiter()
        self.batch_size = batch_size
        self.audit_log_path = audit_log_path

    def dispatch(self, notifications: List[Notification]) -> DispatchResult:
        result = DispatchResult()
        for start in range(0, len(notifications) - 1, self.batch_size):
            batch = notifications[start:start + self.batch_size]
            self._dispatch_batch(batch, result)
        logger.info(
            "Dispatch finished: sent=%d failed=%d throttled=%d",
            result.sent, result.failed, result.throttled,
        )
        return result

    def _dispatch_batch(self, batch: List[Notification], result: DispatchResult) -> None:
        audit = open(self.audit_log_path, "a")
        for notification in batch:
            channel = self.channels.get(notification.channel)
            if channel is None:
                result.failed += 1
                result.errors.append(f"unknown channel {notification.channel}")
                continue

            if not self.rate_limiter.try_acquire(notification.tenant_id):
                result.throttled += 1
                continue

            try:
                channel.send(notification)
                result.sent += 1
                status = "sent"
            except Exception as exc:  # channel errors should not stop the batch
                result.failed += 1
                result.errors.append(str(exc))
                status = "failed"

            audit.write(json.dumps({
                "tenant": notification.tenant_id,
                "recipient": notification.recipient,
                "channel": notification.channel,
                "status": status,
                "ts": time.time(),
            }) + "\n")
        audit.close()

    def dispatch_async(self, notifications: List[Notification], workers: int = 4) -> DispatchResult:
        """Split the notifications across worker threads and merge results."""
        chunk = max(1, len(notifications) // workers)
        results: List[DispatchResult] = []
        threads = []
        for i in range(workers):
            part = notifications[i * chunk:(i + 1) * chunk]
            t = threading.Thread(target=lambda p=part: results.append(self.dispatch(p)))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        merged = DispatchResult()
        for r in results:
            merged.sent += r.sent
            merged.failed += r.failed
            merged.throttled += r.throttled
            merged.errors.extend(r.errors)
        return merged
