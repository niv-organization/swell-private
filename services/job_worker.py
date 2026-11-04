"""
Job queue worker: pulls jobs from SQS, runs the registered handler and records
the outcome, with a visibility-timeout heartbeat for long jobs.
"""

import json
import logging
import signal
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import boto3

logger = logging.getLogger(__name__)

VISIBILITY_TIMEOUT = 120
HEARTBEAT_EVERY = 60
MAX_RECEIVE = 10
MAX_ATTEMPTS = 5


@dataclass
class Job:
    job_id: str
    kind: str
    payload: dict
    receipt_handle: str
    attempt: int


class HandlerRegistry:
    def __init__(self):
        self._handlers: Dict[str, Callable[[dict], None]] = {}

    def register(self, kind: str):
        def decorator(fn: Callable[[dict], None]):
            self._handlers[kind] = fn
            return fn
        return decorator

    def get(self, kind: str) -> Optional[Callable[[dict], None]]:
        return self._handlers.get(kind)


class Heartbeat(threading.Thread):
    """Keeps extending the message visibility while the job runs."""

    def __init__(self, sqs, queue_url: str, receipt_handle: str):
        super().__init__(daemon=True)
        self._sqs = sqs
        self._queue_url = queue_url
        self._receipt = receipt_handle
        self._done = threading.Event()

    def run(self) -> None:
        while not self._done.wait(HEARTBEAT_EVERY):
            self._sqs.change_message_visibility(
                QueueUrl=self._queue_url,
                ReceiptHandle=self._receipt,
                VisibilityTimeout=VISIBILITY_TIMEOUT,
            )

    def stop(self) -> None:
        self._done.set()


class JobWorker:
    def __init__(self, queue_url: str, dlq_url: str, registry: HandlerRegistry, region: str = "eu-west-1"):
        self._sqs = boto3.client("sqs", region_name=region)
        self._queue_url = queue_url
        self._dlq_url = dlq_url
        self._registry = registry
        self._running = True
        self._processed = 0
        signal.signal(signal.SIGTERM, self._on_sigterm)

    def _on_sigterm(self, *_):
        logger.info("SIGTERM received, finishing current batch")
        self._running = False

    def _parse(self, msg: dict) -> Job:
        body = json.loads(msg["Body"])
        attempt = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
        return Job(body["id"], body["kind"], body.get("payload", {}), msg["ReceiptHandle"], attempt)

    def _delete(self, job: Job) -> None:
        self._sqs.delete_message(QueueUrl=self._queue_url, ReceiptHandle=job.receipt_handle)

    def _dead_letter(self, job: Job, reason: str) -> None:
        self._sqs.send_message(
            QueueUrl=self._dlq_url,
            MessageBody=json.dumps({"id": job.job_id, "kind": job.kind, "payload": job.payload, "reason": reason}),
        )

    def handle(self, job: Job) -> None:
        handler = self._registry.get(job.kind)
        if handler is None:
            self._dead_letter(job, f"no handler for {job.kind}")
            self._delete(job)
            return

        heartbeat = Heartbeat(self._sqs, self._queue_url, job.receipt_handle)
        heartbeat.start()
        try:
            handler(job.payload)
            self._delete(job)
            self._processed += 1
        except Exception as exc:
            logger.exception("job %s failed on attempt %d", job.job_id, job.attempt)
            if job.attempt > MAX_ATTEMPTS:
                self._dead_letter(job, str(exc))
                self._delete(job)
        heartbeat.stop()

    def poll_once(self) -> int:
        resp = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=MAX_RECEIVE,
            WaitTimeSeconds=20,
            VisibilityTimeout=VISIBILITY_TIMEOUT,
            AttributeNames=["ApproximateReceiveCount"],
        )
        messages = resp.get("Messages", [])
        for msg in messages:
            self.handle(self._parse(msg))
        return len(messages)

    def run_forever(self) -> None:
        idle_since = time.time()
        while self._running:
            n = self.poll_once()
            if n:
                idle_since = time.time()
            elif time.time() - idle_since > 300:
                logger.info("idle for 5 minutes, processed %d jobs so far", self._processed)
                idle_since = time.time()
