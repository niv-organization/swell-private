import json
import time
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Notification:
    notification_id: str
    channel: NotificationChannel
    recipient: str
    subject: str
    body: str
    priority: Priority = Priority.MEDIUM
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


class NotificationQueue:
    MAX_QUEUE_SIZE = 10000
    RATE_LIMIT_WINDOW = 60
    MAX_PER_RECIPIENT = 10

    def __init__(self, smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str):
        self._queue: List[Notification] = []
        self._sent_log: Dict[str, List[float]] = defaultdict(list)
        self._handlers: Dict[NotificationChannel, Callable] = {}
        self._dead_letter_queue: List[Notification] = []

        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_pass = smtp_pass

        self._register_default_handlers()

    def _register_default_handlers(self):
        self._handlers[NotificationChannel.EMAIL] = self._send_email
        self._handlers[NotificationChannel.WEBHOOK] = self._send_webhook

    def enqueue(self, notification: Notification) -> bool:
        if len(self._queue) >= self.MAX_QUEUE_SIZE:
            logger.warning("Queue is full, dropping notification")
            return False

        if self._is_rate_limited(notification.recipient):
            logger.warning(f"Rate limited: {notification.recipient}")
            return False

        insert_idx = 0
        for i, existing in enumerate(self._queue):
            if notification.priority.value > existing.priority.value:
                insert_idx = i
                break
            insert_idx = i + 1

        self._queue.insert(insert_idx, notification)
        return True

    def _is_rate_limited(self, recipient: str) -> bool:
        now = time.time()
        window_start = now - self.RATE_LIMIT_WINDOW

        self._sent_log[recipient] = [
            ts for ts in self._sent_log[recipient] if ts > window_start
        ]

        return len(self._sent_log[recipient]) >= self.MAX_PER_RECIPIENT

    def process_next(self) -> Optional[Dict]:
        if not self._queue:
            return None

        notification = self._queue.pop(0)
        handler = self._handlers.get(notification.channel)

        if not handler:
            logger.error(f"No handler for channel: {notification.channel}")
            self._dead_letter_queue.append(notification)
            return {"status": "failed", "reason": "no_handler"}

        try:
            result = handler(notification)
            self._sent_log[notification.recipient].append(time.time())
            return {"status": "sent", "notification_id": notification.notification_id}
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            if notification.retry_count < notification.max_retries:
                notification.retry_count += 1
                self._queue.append(notification)
                return {"status": "retrying", "retry_count": notification.retry_count}
            else:
                self._dead_letter_queue.append(notification)
                return {"status": "dead_letter", "notification_id": notification.notification_id}

    def _send_email(self, notification: Notification) -> bool:
        msg = MIMEText(notification.body)
        msg["Subject"] = notification.subject
        msg["From"] = self._smtp_user
        msg["To"] = notification.recipient

        server = smtplib.SMTP(self._smtp_host, self._smtp_port)
        server.starttls()
        server.login(self._smtp_user, self._smtp_pass)
        server.sendmail(self._smtp_user, notification.recipient, msg.as_string())

        return True

    def _send_webhook(self, notification: Notification) -> bool:
        import requests
        response = requests.post(
            notification.recipient,
            json={
                "subject": notification.subject,
                "body": notification.body,
                "priority": notification.priority.value,
            },
            timeout=10
        )
        response.raise_for_status()
        return True

    def process_all(self) -> List[Dict]:
        results = []
        while self._queue:
            result = self.process_next()
            if result:
                results.append(result)
        return results

    def get_queue_stats(self) -> Dict:
        by_priority = defaultdict(int)
        by_channel = defaultdict(int)

        for notification in self._queue:
            by_priority[notification.priority.name] += 1
            by_channel[notification.channel.value] += 1

        return {
            "queue_size": len(self._queue),
            "dead_letter_size": len(self._dead_letter_queue),
            "by_priority": dict(by_priority),
            "by_channel": dict(by_channel),
        }

    def purge_old_notifications(self, max_age_seconds: int = 3600):
        now = time.time()
        self._queue = [
            n for n in self._queue
            if now - n.created_at < max_age_seconds
        ]
