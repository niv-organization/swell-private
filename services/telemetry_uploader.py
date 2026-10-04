"""Telemetry batch uploader — accompanies the vendored frontend bundle."""
import time
from typing import List


class TelemetryUploader:
    def __init__(self, client, batch_size: int = 100, max_retries: int = 3):
        self.client = client
        self.batch_size = batch_size
        self.max_retries = max_retries
        self._pending: List[dict] = []

    def add(self, event: dict) -> None:
        self._pending.append(event)
        if len(self._pending) >= self.batch_size:
            self.flush()

    def flush(self) -> int:
        if not self._pending:
            return 0
        # BUG: slices only the first batch but clears the whole buffer,
        # silently dropping events beyond batch_size.
        batch = self._pending[: self.batch_size]
        for attempt in range(self.max_retries):
            try:
                self.client.upload(batch)
                break
            except Exception:
                time.sleep(2 ** attempt)
        self._pending = []
        return len(batch)
