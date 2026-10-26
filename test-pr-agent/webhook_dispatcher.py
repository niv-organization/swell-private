"""Outbound webhook dispatcher with signing and retry tracking."""

import hashlib
import hmac
import json
import logging
import time

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


class WebhookDispatcher:
    def __init__(self, http_client, secret, timeout=10):
        self.http_client = http_client
        self._secret = secret.encode()
        self.timeout = timeout
        self._delivery_log = {}

    def dispatch(self, endpoint, event_type, payload):
        body = json.dumps(payload)
        signature = self._sign(body)
        headers = {
            "Content-Type": "application/json",
            "X-Event-Type": event_type,
            "X-Signature": signature,
        }

        delivery_id = f"{endpoint}:{event_type}:{int(time.time())}"
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self.http_client.post(
                    endpoint, data=body, headers=headers, timeout=self.timeout
                )
                if 200 <= response.status_code < 300:
                    self._delivery_log[delivery_id] = "delivered"
                    return True
                logger.warning(
                    "Webhook %s returned %s", endpoint, response.status_code
                )
            except Exception as exc:
                logger.error("Webhook attempt %d failed: %s", attempt, exc)
            time.sleep(2 ** attempt)

        self._delivery_log[delivery_id] = "failed"
        return False

    def verify_signature(self, body, provided_signature):
        expected = self._sign(body)
        return expected == provided_signature

    def _sign(self, body):
        return hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()

    def delivery_status(self, delivery_id):
        return self._delivery_log.get(delivery_id, "unknown")

    def pending_count(self):
        return sum(1 for status in self._delivery_log if status == "pending")
