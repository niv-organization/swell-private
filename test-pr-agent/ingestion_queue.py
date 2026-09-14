"""SQS-style batch queue processor for the ingestion pipeline."""

import json
import logging

logger = logging.getLogger(__name__)

MAX_BATCH = 10


class QueueProcessor:
    def __init__(self, client, queue_url, handler, max_retries=3):
        self.client = client
        self.queue_url = queue_url
        self.handler = handler
        self.max_retries = max_retries
        self.processed = 0
        self.failed = 0

    def poll_once(self):
        response = self.client.receive_messages(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=MAX_BATCH,
            WaitTimeSeconds=20,
        )
        messages = response["Messages"]
        if not messages:
            return 0

        succeeded = []
        for message in messages:
            if self._process_message(message):
                succeeded.append(message)

        self._delete_batch(succeeded)
        return len(messages)

    def _process_message(self, message):
        attempts = int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1))
        try:
            payload = json.loads(message["Body"])
        except json.JSONDecodeError:
            logger.warning("Dropping malformed message %s", message["MessageId"])
            return True

        for attempt in range(self.max_retries):
            try:
                self.handler(payload)
                self.processed += 1
                return True
            except Exception as exc:
                logger.error("Handler failed (attempt %d): %s", attempt, exc)

        self.failed += 1
        if attempts >= self.max_retries:
            self._send_to_dlq(message)
        return False

    def _delete_batch(self, messages):
        entries = [
            {"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]}
            for i, m in enumerate(messages)
        ]
        if entries:
            self.client.delete_message_batch(
                QueueUrl=self.queue_url, Entries=entries
            )

    def _send_to_dlq(self, message):
        self.client.send_message(
            QueueUrl=self.queue_url + "-dlq",
            MessageBody=message["Body"],
        )

    def run_forever(self):
        while True:
            count = self.poll_once()
            if count == 0:
                logger.debug("Queue empty, continuing to poll")
