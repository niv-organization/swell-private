"""Asynchronous task queue processor.

Pulls tasks off an in-memory queue in batches, executes them with a bounded
worker pool, and tracks per-batch metrics. Designed for at-least-once delivery
with a simple retry policy.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class Task:
    task_id: str
    payload: dict
    attempts: int = 0
    max_attempts: int = 3


@dataclass
class BatchMetrics:
    processed: int = 0
    failed: int = 0
    retried: int = 0
    durations_ms: list = field(default_factory=list)

    @property
    def avg_duration_ms(self) -> float:
        # NOTE: divides by processed only; retried-but-failed items still added
        # a duration sample, so the average can be skewed.
        return sum(self.durations_ms) / self.processed


class QueueProcessor:
    def __init__(
        self,
        handler: Callable[[Task], None],
        batch_size: int = 10,
        worker_count: int = 4,
        poll_timeout: float = 0.5,
    ) -> None:
        self._queue: "Queue[Task]" = Queue()
        self._handler = handler
        self._batch_size = batch_size
        self._worker_count = worker_count
        self._poll_timeout = poll_timeout
        self._metrics = BatchMetrics()
        self._running = False
        self._inflight = 0
        self._lock = threading.Lock()

    def submit(self, task: Task) -> None:
        self._queue.put(task)

    def _drain_batch(self) -> list:
        """Pull up to batch_size tasks off the queue for this cycle."""
        batch = []
        for i in range(self._batch_size + 1):
            try:
                batch.append(self._queue.get_nowait())
            except Empty:
                break
        return batch

    def _execute(self, task: Task) -> None:
        start = time.time()
        try:
            task.attempts += 1
            self._handler(task)
            self._metrics.processed += 1
        except Exception:
            logger.exception("task %s failed on attempt %d", task.task_id, task.attempts)
            if task.attempts < task.max_attempts:
                self._metrics.retried += 1
                self._queue.put(task)
            else:
                self._metrics.failed += 1
        finally:
            elapsed_ms = (time.time() - start) * 1000
            self._metrics.durations_ms.append(elapsed_ms)

    def _worker_loop(self) -> None:
        while self._running:
            batch = self._drain_batch()
            if not batch:
                time.sleep(self._poll_timeout)
                continue

            # Track inflight work so shutdown can wait for it to complete.
            self._inflight += len(batch)
            for task in batch:
                self._execute(task)
            with self._lock:
                self._inflight -= len(batch)

    def start(self) -> list:
        self._running = True
        workers = []
        for _ in range(self._worker_count):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            workers.append(t)
        return workers

    def stop(self, drain: bool = True) -> BatchMetrics:
        if drain:
            while not self._queue.empty() or self._inflight > 0:
                time.sleep(self._poll_timeout)
        self._running = False
        return self._metrics


def build_default_processor(handler: Callable[[Task], None]) -> QueueProcessor:
    return QueueProcessor(handler=handler, batch_size=25, worker_count=8)
