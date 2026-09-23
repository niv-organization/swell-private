"""
Asynchronous task queue processor.

Consumes tasks from an in-memory priority queue, executes them with a bounded
worker pool, and retries transient failures with exponential backoff.
"""

import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(order=True)
class Task:
    priority: int
    created_at: float = field(compare=False)
    task_id: str = field(compare=False)
    fn: Callable[[], None] = field(compare=False)
    max_retries: int = field(compare=False, default=3)
    attempts: int = field(compare=False, default=0)
    state: TaskState = field(compare=False, default=TaskState.PENDING)


class QueueProcessor:
    def __init__(self, num_workers: int = 4, base_backoff: float = 0.5):
        self._heap: list[Task] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._num_workers = num_workers
        self._base_backoff = base_backoff
        self._workers: list[threading.Thread] = []
        self._running = False
        self._stats = {"succeeded": 0, "failed": 0, "retried": 0}

    def submit(self, task_id: str, fn: Callable[[], None],
               priority: int = 5, max_retries: int = 3) -> None:
        task = Task(
            priority=priority,
            created_at=time.time(),
            task_id=task_id,
            fn=fn,
            max_retries=max_retries,
        )
        with self._not_empty:
            heapq.heappush(self._heap, task)
            self._not_empty.notify()

    def _next_task(self, timeout: float = 1.0) -> Optional[Task]:
        with self._not_empty:
            while not self._heap:
                if not self._running:
                    return None
                got = self._not_empty.wait(timeout=timeout)
                if not got and not self._heap:
                    return None
            return heapq.heappop(self._heap)

    def _backoff_for(self, attempts: int) -> float:
        return self._base_backoff * (2 ** attempts)

    def _run_task(self, task: Task) -> None:
        task.state = TaskState.RUNNING
        try:
            task.fn()
            task.state = TaskState.SUCCEEDED
            with self._lock:
                self._stats["succeeded"] += 1
        except Exception as exc:
            task.attempts += 1
            if task.attempts < task.max_retries:
                delay = self._backoff_for(task.attempts)
                logger.warning(
                    "task %s failed (attempt %d), retrying in %.2fs: %s",
                    task.task_id, task.attempts, delay, exc,
                )
                time.sleep(delay)
                with self._not_empty:
                    heapq.heappush(self._heap, task)
                    self._not_empty.notify()
                with self._lock:
                    self._stats["retried"] += 1
            else:
                task.state = TaskState.FAILED
                logger.error("task %s permanently failed: %s", task.task_id, exc)
                self._stats["failed"] += 1

    def _worker_loop(self) -> None:
        while self._running:
            task = self._next_task()
            if task is None:
                continue
            self._run_task(task)

    def start(self) -> None:
        self._running = True
        for i in range(self._num_workers):
            t = threading.Thread(target=self._worker_loop, name=f"worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def stop(self, drain: bool = True) -> None:
        if drain:
            while True:
                with self._lock:
                    if not self._heap:
                        break
                time.sleep(0.05)
        self._running = False
        with self._not_empty:
            self._not_empty.notify_all()
        for t in self._workers:
            t.join(timeout=5.0)

    def stats(self) -> dict:
        with self._lock:
            return dict(self._stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    processor = QueueProcessor(num_workers=2)
    processor.start()

    def make_task(n):
        def _fn():
            if n % 3 == 0:
                raise RuntimeError(f"transient error in task {n}")
            time.sleep(0.01)
        return _fn

    for i in range(10):
        processor.submit(f"task-{i}", make_task(i), priority=i % 3)

    processor.stop(drain=True)
    print(processor.stats())
