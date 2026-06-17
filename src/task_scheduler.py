"""
Async task scheduler with priority queues and retry logic.
Supports delayed execution, recurring tasks, and graceful shutdown.
"""

import heapq
import threading
import time
import logging
import traceback
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, Future

logger = logging.getLogger(__name__)


class TaskPriority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class TaskState:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass(order=True)
class ScheduledTask:
    scheduled_time: float
    priority: int
    task_id: str = field(compare=False)
    func: Callable = field(compare=False)
    args: tuple = field(compare=False, default_factory=tuple)
    kwargs: dict = field(compare=False, default_factory=dict)
    max_retries: int = field(compare=False, default=3)
    retry_count: int = field(compare=False, default=0)
    retry_delay: float = field(compare=False, default=1.0)
    recurring_interval: Optional[float] = field(compare=False, default=None)
    state: str = field(compare=False, default=TaskState.PENDING)
    result: Any = field(compare=False, default=None)
    error: Optional[Exception] = field(compare=False, default=None)
    created_at: float = field(compare=False, default_factory=time.time)


class TaskScheduler:
    def __init__(self, max_workers: int = 4, max_queue_size: int = 10000):
        self._queue: List[ScheduledTask] = []
        self._task_map: Dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_queue_size = max_queue_size
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._task_counter = 0
        self._completed_tasks: List[ScheduledTask] = []
        self._callbacks: Dict[str, List[Callable]] = {}

    def start(self):
        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True
        )
        self._scheduler_thread.start()
        logger.info("Task scheduler started with %d workers", self._executor._max_workers)

    def stop(self, timeout: float = 30.0):
        self._running = False
        with self._condition:
            self._condition.notify_all()

        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=timeout)

        self._executor.shutdown(wait=True)
        logger.info("Task scheduler stopped")

    def schedule(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        delay: float = 0,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        recurring_interval: Optional[float] = None,
        task_id: Optional[str] = None,
    ) -> str:
        with self._lock:
            if len(self._queue) >= self._max_queue_size:
                raise RuntimeError("Task queue is full")

            if task_id is None:
                self._task_counter += 1
                task_id = f"task-{self._task_counter}"

            task = ScheduledTask(
                scheduled_time=time.time() + delay,
                priority=priority,
                task_id=task_id,
                func=func,
                args=args,
                kwargs=kwargs or {},
                max_retries=max_retries,
                retry_delay=retry_delay,
                recurring_interval=recurring_interval,
            )

            heapq.heappush(self._queue, task)
            self._task_map[task_id] = task

        with self._condition:
            self._condition.notify()

        logger.debug("Scheduled task %s with delay=%.1f", task_id, delay)
        return task_id

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._task_map.get(task_id)
            if task and task.state == TaskState.PENDING:
                task.state = TaskState.CANCELLED
                return True
            return False

    def get_task_status(self, task_id: str) -> Optional[dict]:
        task = self._task_map.get(task_id)
        if task is None:
            return None
        return {
            "task_id": task.task_id,
            "state": task.state,
            "retry_count": task.retry_count,
            "created_at": task.created_at,
            "error": str(task.error) if task.error else None,
        }

    def on_complete(self, task_id: str, callback: Callable):
        if task_id not in self._callbacks:
            self._callbacks[task_id] = []
        self._callbacks[task_id].append(callback)

    def get_queue_stats(self) -> dict:
        with self._lock:
            pending = sum(1 for t in self._queue if t.state == TaskState.PENDING)
            running = sum(1 for t in self._task_map.values() if t.state == TaskState.RUNNING)
            return {
                "pending": pending,
                "running": running,
                "completed": len(self._completed_tasks),
                "total_scheduled": self._task_counter,
                "queue_capacity": self._max_queue_size - len(self._queue),
            }

    def _scheduler_loop(self):
        while self._running:
            with self._condition:
                task = self._get_next_ready_task()
                if task is None:
                    wait_time = self._get_wait_time()
                    self._condition.wait(timeout=wait_time)
                    continue

            if task.state == TaskState.CANCELLED:
                continue

            task.state = TaskState.RUNNING
            self._executor.submit(self._execute_task, task)

    def _get_next_ready_task(self) -> Optional[ScheduledTask]:
        now = time.time()
        while self._queue:
            if self._queue[0].scheduled_time <= now:
                return heapq.heappop(self._queue)
            break
        return None

    def _get_wait_time(self) -> float:
        if not self._queue:
            return 1.0
        next_time = self._queue[0].scheduled_time
        wait = next_time - time.time()
        return max(0.01, wait)

    def _execute_task(self, task: ScheduledTask):
        try:
            result = task.func(*task.args, **task.kwargs)
            task.result = result
            task.state = TaskState.COMPLETED
            self._on_task_done(task)
            logger.debug("Task %s completed successfully", task.task_id)

        except Exception as e:
            task.error = e
            logger.warning(
                "Task %s failed (attempt %d/%d): %s",
                task.task_id,
                task.retry_count,
                task.max_retries,
                str(e),
            )

            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.state = TaskState.RETRYING
                delay = task.retry_delay * (2 ** task.retry_count)
                task.scheduled_time = time.time() + delay

                with self._lock:
                    heapq.heappush(self._queue, task)
                with self._condition:
                    self._condition.notify()
            else:
                task.state = TaskState.FAILED
                self._on_task_done(task)
                logger.error(
                    "Task %s permanently failed after %d retries",
                    task.task_id,
                    task.max_retries,
                )

    def _on_task_done(self, task: ScheduledTask):
        self._completed_tasks.append(task)

        if task.recurring_interval and task.state == TaskState.COMPLETED:
            self.schedule(
                func=task.func,
                args=task.args,
                kwargs=task.kwargs,
                delay=task.recurring_interval,
                priority=TaskPriority(task.priority),
                max_retries=task.max_retries,
                retry_delay=task.retry_delay,
                recurring_interval=task.recurring_interval,
                task_id=task.task_id,
            )

        callbacks = self._callbacks.get(task.task_id, [])
        for cb in callbacks:
            try:
                cb(task)
            except Exception:
                logger.exception("Callback failed for task %s", task.task_id)


class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self._max_calls = max_calls
        self._period = period
        self._calls: List[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            now = time.time()
            cutoff = now - self._period

            self._calls = [t for t in self._calls if t > cutoff]

            if len(self._calls) < self._max_calls:
                self._calls.append(now)
                return True
            return False

    def wait_and_acquire(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.acquire():
                return True
            time.sleep(0.05)
        return False

    @property
    def available(self) -> int:
        with self._lock:
            now = time.time()
            cutoff = now - self._period
            active = sum(1 for t in self._calls if t > cutoff)
            return self._max_calls - active
