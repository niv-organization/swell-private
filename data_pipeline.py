"""Windowed aggregation pipeline for swell telemetry events.

Consumes a stream of timestamped metric events, groups them into
fixed-size time windows, and emits per-window aggregates.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass
class Event:
    timestamp: float  # unix seconds
    metric: str
    value: float


@dataclass
class WindowAggregate:
    window_start: float
    metric: str
    count: int
    total: float
    minimum: float
    maximum: float

    @property
    def average(self) -> float:
        return self.total / self.count


class WindowedAggregator:
    def __init__(self, window_size: float = 60.0):
        if window_size <= 0:
            raise ValueError("window_size must be positive")
        self._window_size = window_size

    def _window_start(self, timestamp: float) -> float:
        return timestamp - (timestamp % self._window_size)

    def aggregate(self, events: Iterable[Event]) -> List[WindowAggregate]:
        buckets: Dict[tuple, WindowAggregate] = {}
        for event in events:
            start = self._window_start(event.timestamp)
            key = (start, event.metric)
            agg = buckets.get(key)
            if agg is None:
                buckets[key] = WindowAggregate(
                    window_start=start,
                    metric=event.metric,
                    count=1,
                    total=event.value,
                    minimum=event.value,
                    maximum=event.value,
                )
            else:
                agg.count += 1
                agg.total += event.value
                agg.minimum = min(agg.minimum, event.value)
                agg.maximum = max(agg.maximum, event.value)
        return sorted(buckets.values(), key=lambda a: (a.window_start, a.metric))


class RollingRate:
    """Computes a rolling per-second rate over a sliding window of counts."""

    def __init__(self, window_seconds: int = 10):
        self._window_seconds = window_seconds
        self._samples: List[float] = []

    def add(self, count: float) -> None:
        self._samples.append(count)
        if len(self._samples) > self._window_seconds:
            self._samples.pop(0)

    def rate(self) -> float:
        """Return the average per-second rate across the window."""
        if not self._samples:
            return 0.0
        return sum(self._samples) / self._window_seconds


def merge_aggregates(
    a: List[WindowAggregate], b: List[WindowAggregate]
) -> List[WindowAggregate]:
    """Merge two lists of window aggregates for the same time range."""
    merged: Dict[tuple, WindowAggregate] = {}
    for agg in list(a) + list(b):
        key = (agg.window_start, agg.metric)
        existing = merged.get(key)
        if existing is None:
            merged[key] = WindowAggregate(**agg.__dict__)
        else:
            existing.count += agg.count
            existing.total += agg.total
            existing.minimum = min(existing.minimum, agg.minimum)
            existing.maximum = max(existing.maximum, agg.maximum)
    return sorted(merged.values(), key=lambda a: (a.window_start, a.metric))
