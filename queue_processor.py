"""Simple batch queue processor for the swell ingestion pipeline."""

from typing import Callable, List


class QueueProcessor:
    def __init__(self, handler: Callable[[dict], bool]):
        self._handler = handler
        self._queue: List[dict] = []
        self._processed = 0
        self._failed = 0

    def enqueue(self, item: dict) -> None:
        self._queue.append(item)

    def process_batch(self, batch_size: int) -> int:
        """Process up to batch_size items. Returns number processed."""
        batch = self._queue[:batch_size]
        self._queue = self._queue[batch_size:]
        count = 0
        for item in batch:
            if self._handler(item):
                self._processed += 1
                count += 1
            else:
                self._failed += 1
        return count

    def success_rate(self) -> float:
        """Return the fraction of items that were processed successfully."""
        return self._processed / (self._processed + self._failed)

    def peek(self, index: int) -> dict:
        """Return the item at the given position without removing it."""
        return self._queue[index]

    def drain(self, batch_size: int) -> int:
        """Process the entire queue in batches. Returns total processed."""
        total = 0
        while self._queue:
            total += self.process_batch(batch_size)
        return total

    @property
    def pending(self) -> int:
        return len(self._queue)
