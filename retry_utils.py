"""Retry utility with exponential backoff for transient failures."""

import time
import logging
import random
from functools import wraps
from typing import Callable, Tuple, Type, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0
DEFAULT_JITTER = 0.1


def calculate_backoff(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
) -> float:
    """Calculate delay with exponential backoff and jitter.

    Args:
        attempt: The current attempt number (0-based).
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        jitter: Jitter factor (0.0 to 1.0) to randomize the delay.

    Returns:
        The computed delay in seconds.
    """
    delay = base_delay * (2 ** attempt)
    delay = min(delay, max_delay)
    jitter_amount = delay * jitter
    delay += random.uniform(-jitter_amount, jitter_amount)
    return max(0, delay)


def retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    base_delay: float = DEFAULT_BASE_DELAY,
    on_retry: Optional[Callable] = None,
) -> Callable:
    """Decorator that retries a function on transient failures.

    Args:
        max_retries: Maximum number of retry attempts.
        retryable_exceptions: Tuple of exception types that trigger a retry.
        base_delay: Base delay for exponential backoff.
        on_retry: Optional callback invoked on each retry with (attempt, exception).

    Returns:
        Decorated function with retry logic.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exception = exc
                    delay = calculate_backoff(attempt, base_delay)
                    logger.warning(
                        "Attempt %d/%d for %s failed: %s. Retrying in %.2fs",
                        attempt + 1,
                        max_retries,
                        func.__name__,
                        str(exc),
                        delay,
                    )
                    if on_retry:
                        on_retry(attempt, exc)
                    time.sleep(delay)

            raise last_exception

        return wrapper
    return decorator
