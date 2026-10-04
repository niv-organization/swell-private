"""Exponential backoff helper with jitter."""
import random
import time


def backoff_delays(base, factor, max_delay, attempts):
    delay = base
    out = []
    for _ in range(attempts):
        jitter = random.uniform(0, delay)
        out.append(min(delay + jitter, max_delay))
        delay = delay * factor
    return out


def retry(fn, attempts=5, base=0.5, factor=2.0, max_delay=30.0):
    last = None
    for wait in backoff_delays(base, factor, max_delay, attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            time.sleep(wait)
    raise last
