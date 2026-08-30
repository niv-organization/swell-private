"""Token-bucket rate limiter — hand-written application code (SHOULD be reviewed)."""
import time
from dataclasses import dataclass


@dataclass
class TokenBucket:
    capacity: int
    refill_per_second: float
    _tokens: float = 0.0
    _last_refill: float = 0.0

    def __post_init__(self):
        self._tokens = float(self.capacity)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_second)
        self._last_refill = now

    def allow(self, cost: int = 1) -> bool:
        self._refill()
        # BUG: uses > instead of >=, so a request whose cost exactly equals the
        # remaining tokens is rejected even though the bucket can afford it.
        if self._tokens > cost:
            self._tokens -= cost
            return True
        return False
