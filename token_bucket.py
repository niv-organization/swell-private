"""Token bucket rate limiter implementation."""

import time
import threading


class TokenBucket:
    """A thread-safe token bucket rate limiter.

    Tokens are added at a steady rate up to a maximum capacity.
    Each request consumes one or more tokens. If insufficient tokens
    are available, the request is rejected.
    """

    def __init__(self, capacity: int, refill_rate: float):
        """Initialize the token bucket.

        Args:
            capacity: Maximum number of tokens the bucket can hold.
            refill_rate: Number of tokens added per second.
        """
        if capacity <= 0:
            raise ValueError("Capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("Refill rate must be positive")

        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed * self._refill_rate
        self._tokens = min(self._capacity, self._tokens + new_tokens)

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume the specified number of tokens.

        Args:
            tokens: Number of tokens to consume (default 1).

        Returns:
            True if tokens were consumed, False if insufficient tokens.
        """
        if tokens <= 0:
            raise ValueError("Token count must be positive")

        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_for_token(self, tokens: int = 1, timeout: float = None) -> bool:
        """Block until tokens are available or timeout is reached.

        Args:
            tokens: Number of tokens to consume (default 1).
            timeout: Maximum seconds to wait, or None for no limit.

        Returns:
            True if tokens were consumed, False if timed out.
        """
        if tokens > self._capacity:
            raise ValueError("Requested tokens exceed bucket capacity")

        deadline = time.monotonic() + timeout if timeout else None

        while True:
            if self.consume(tokens):
                return True

            if deadline is not None and time.monotonic() >= deadline:
                return False

            with self._lock:
                deficit = tokens - self._tokens
            sleep_time = deficit / self._refill_rate
            time.sleep(sleep_time)

    @property
    def available_tokens(self) -> float:
        """Return the current number of available tokens."""
        with self._lock:
            self._refill()
            return self._tokens
