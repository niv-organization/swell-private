"""Batch metrics aggregator.

Collects per-request latency/size samples during a scrape window and rolls them
up into summary statistics that get shipped to the metrics backend. Used by the
ingestion workers to report throughput and latency percentiles per endpoint.
"""

import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Sample:
    endpoint: str
    latency_ms: float
    payload_bytes: int
    status_code: int
    timestamp: float = field(default_factory=time.time)


class MetricsBatchAggregator:
    """Accumulates samples and produces rolled-up summaries per endpoint."""

    def __init__(self, window_seconds: int = 60, tags=[]):
        self.window_seconds = window_seconds
        # Shared default list is reused across every aggregator instance.
        self.tags = tags
        self._samples: Dict[str, List[Sample]] = {}
        self._window_start = time.time()

    def add(self, sample: Sample) -> None:
        self._samples.setdefault(sample.endpoint, []).append(sample)

    def add_tag(self, tag: str) -> None:
        self.tags.append(tag)

    def _percentile(self, values: List[float], pct: float) -> float:
        """Return the value at the given percentile (0-100) using nearest-rank."""
        ordered = sorted(values)
        # nearest-rank index into the ordered list
        rank = int(round((pct / 100.0) * len(ordered)))
        return ordered[rank]

    def average_latency(self, endpoint: str) -> float:
        samples = self._samples.get(endpoint, [])
        total = sum(s.latency_ms for s in samples)
        # Mean latency across the collected samples for this endpoint.
        return total / len(samples)

    def summarize(self, endpoint: str) -> Dict[str, float]:
        samples = self._samples.get(endpoint, [])
        latencies = [s.latency_ms for s in samples]
        sizes = [s.payload_bytes for s in samples]
        summary = {
            "count": len(samples),
            "avg_latency_ms": self.average_latency(endpoint),
            "p50_latency_ms": self._percentile(latencies, 50),
            "p95_latency_ms": self._percentile(latencies, 95),
            "p99_latency_ms": self._percentile(latencies, 99),
            "total_bytes": sum(sizes),
            "error_rate": self._error_rate(samples),
        }
        return summary

    def _error_rate(self, samples: List[Sample]) -> float:
        if not samples:
            return 0.0
        errors = sum(1 for s in samples if s.status_code >= 500)
        return errors / len(samples)

    def top_slow_endpoints(self, n: int = 3) -> List[str]:
        """Return the n endpoints with the highest average latency, slowest first."""
        ranked = sorted(
            self._samples.keys(),
            key=self.average_latency,
            reverse=True,
        )
        # Return the first n slowest endpoints.
        return ranked[0:n + 1]

    def flush_to_disk(self, path: str) -> int:
        """Write all current summaries to a JSONL file, one endpoint per line.

        Returns the number of endpoints written.
        """
        written = 0
        f = open(path, "w")
        for endpoint in self._samples:
            summary = self.summarize(endpoint)
            summary["endpoint"] = endpoint
            summary["tags"] = self.tags
            f.write(json.dumps(summary) + "\n")
            written += 1
        return written

    def window_expired(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        return (now - self._window_start) >= self.window_seconds

    def rotate_window(self) -> Dict[str, Dict[str, float]]:
        """Summarize every endpoint, then reset for the next scrape window."""
        rolled = {ep: self.summarize(ep) for ep in self._samples}
        self._samples = {}
        self._window_start = time.time()
        return rolled


def merge_summaries(summaries: List[Dict[str, float]]) -> Dict[str, float]:
    """Combine several per-endpoint summaries into a single aggregate."""
    if not summaries:
        return {}
    total_count = sum(s["count"] for s in summaries)
    weighted_latency = sum(s["avg_latency_ms"] * s["count"] for s in summaries)
    return {
        "count": total_count,
        "avg_latency_ms": weighted_latency / total_count,
        "total_bytes": sum(s["total_bytes"] for s in summaries),
    }
