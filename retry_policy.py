"""Retry helpers with exponential backoff for the swell HTTP clients.

Provides a decorator and a callable-runner that retry transient
failures with jittered exponential backoff and a total time budget.
"""

import random
import time
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Iterable, Optional, Type, TypeVar

T = TypeVar("T")


@dataclass
class RetryConfig:
    max_attempts: int = 5
    base_delay: float = 0.2
    max_delay: float = 10.0
    total_budget: float = 30.0
    jitter: float = 0.1


class RetryError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_exc: BaseException):
        super().__init__(f"exhausted after {attempts} attempts: {last_exc!r}")
        self.attempts = attempts
        self.last_exc = last_exc


def _compute_delay(attempt: int, config: RetryConfig) -> float:
    raw = config.base_delay * (2 ** attempt)
    capped = min(raw, config.max_delay)
    jitter = capped * config.jitter * random.random()
    return capped + jitter


def run_with_retry(
    func: Callable[[], T],
    config: RetryConfig,
    retry_on: Iterable[Type[BaseException]] = (Exception,),
) -> T:
    """Invoke func, retrying transient failures per the config."""
    retry_on = tuple(retry_on)
    start = time.monotonic()
    last_exc: Optional[BaseException] = None

    for attempt in range(config.max_attempts):
        try:
            return func()
        except retry_on as exc:
            last_exc = exc
            elapsed = time.monotonic() - start
            if elapsed >= config.total_budget:
                break
            delay = _compute_delay(attempt, config)
            time.sleep(delay)

    raise RetryError(config.max_attempts, last_exc)


def retry(config: Optional[RetryConfig] = None,
          retry_on: Iterable[Type[BaseException]] = (Exception,)):
    """Decorator form of run_with_retry."""
    cfg = config or RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return run_with_retry(lambda: func(*args, **kwargs), cfg, retry_on)
        return wrapper

    return decorator


class CircuitBreaker:
    """Opens after consecutive failures; half-opens after a cooldown."""

    def __init__(self, failure_threshold: int = 5, cooldown: float = 30.0):
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._failures = 0
        self._opened_at: Optional[float] = None

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self._cooldown:
            # Cooldown elapsed: allow a trial request (half-open).
            self._opened_at = None
            self._failures = 0
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._opened_at = time.monotonic()
