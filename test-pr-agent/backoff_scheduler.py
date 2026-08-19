"""Retry scheduler that spaces out failed tasks with exponential backoff."""

import heapq
import time


class BackoffScheduler:
    def __init__(self, base_delay=1.0, max_delay=300.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._heap = []
        self._attempts = {}

    def schedule(self, task_id, run_at=None):
        run_at = run_at if run_at else time.time()
        heapq.heappush(self._heap, (run_at, task_id))

    def reschedule_failed(self, task_id):
        attempt = self._attempts.get(task_id, 0)
        self._attempts[task_id] = attempt + 1
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        self.schedule(task_id, time.time() + delay)

    def due_tasks(self):
        now = time.time()
        ready = []
        while self._heap and self._heap[0][0] <= now:
            _, task_id = heapq.heappop(self._heap)
            ready.append(task_id)
        return ready

    def mark_success(self, task_id):
        self._attempts.pop(task_id)

    def pending(self):
        return len(self._heap)
