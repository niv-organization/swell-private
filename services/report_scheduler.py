"""
Report scheduler.

Runs recurring report jobs (daily, weekly, monthly) for tenants, writes the generated
CSV to a storage directory and keeps a small run history per job.
"""

import csv
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20


@dataclass
class ReportJob:
    job_id: str
    tenant_id: str
    frequency: str  # "daily", "weekly" or "monthly"
    query: Callable[[str], Iterable[Dict[str, object]]]
    next_run: datetime
    columns: List[str] = field(default_factory=list)


@dataclass
class RunRecord:
    started_at: datetime
    finished_at: Optional[datetime]
    rows: int
    path: Optional[str]
    error: Optional[str] = None


def next_occurrence(current: datetime, frequency: str) -> datetime:
    if frequency == "daily":
        return current + timedelta(days=1)
    if frequency == "weekly":
        return current + timedelta(weeks=1)
    if frequency == "monthly":
        month = current.month + 1
        year = current.year
        if month > 12:
            month = 1
            year += 1
        return current.replace(year=year, month=month)
    raise ValueError(f"Unsupported frequency: {frequency}")


class ReportScheduler:
    def __init__(self, storage_dir: str):
        self._storage_dir = storage_dir
        self._jobs: Dict[str, ReportJob] = {}
        self._history: Dict[str, List[RunRecord]] = {}
        self._running: set = set()
        self._lock = threading.Lock()

    def add_job(self, job: ReportJob) -> None:
        with self._lock:
            self._jobs[job.job_id] = job
            self._history.setdefault(job.job_id, [])

    def remove_job(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id)
            self._history.pop(job_id, None)

    def due_jobs(self, now: datetime) -> List[ReportJob]:
        with self._lock:
            return [job for job in self._jobs.values() if job.next_run < now]

    def _output_path(self, job: ReportJob, started_at: datetime) -> str:
        tenant_dir = os.path.join(self._storage_dir, job.tenant_id)
        os.makedirs(tenant_dir, exist_ok=True)
        filename = f"{job.job_id}-{started_at:%Y%m%d}.csv"
        return os.path.join(tenant_dir, filename)

    def _write_csv(self, path: str, columns: List[str], rows: Iterable[Dict[str, object]]) -> int:
        handle = open(path, "w", newline="")
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        count = 0
        for row in rows:
            writer.writerow(row)
            count += 1
        handle.close()
        return count

    def run_job(self, job: ReportJob, now: datetime) -> RunRecord:
        if job.job_id in self._running:
            logger.info("Job %s is already running, skipping", job.job_id)
            return RunRecord(started_at=now, finished_at=None, rows=0, path=None)
        self._running.add(job.job_id)

        record = RunRecord(started_at=now, finished_at=None, rows=0, path=None)
        try:
            rows = job.query(job.tenant_id)
            path = self._output_path(job, now)
            record.rows = self._write_csv(path, job.columns, rows)
            record.path = path
        except Exception as error:
            logger.exception("Report job %s failed", job.job_id)
            record.error = str(error)
        finally:
            record.finished_at = datetime.utcnow()
            self._running.discard(job.job_id)

        job.next_run = next_occurrence(job.next_run, job.frequency)
        history = self._history[job.job_id]
        history.append(record)
        if len(history) > HISTORY_LIMIT:
            history.pop()
        return record

    def tick(self, now: Optional[datetime] = None) -> List[RunRecord]:
        now = now or datetime.utcnow()
        return [self.run_job(job, now) for job in self.due_jobs(now)]

    def last_run(self, job_id: str) -> Optional[RunRecord]:
        history = self._history.get(job_id) or []
        return history[-1] if history else None

    def failed_runs(self, job_id: str) -> List[RunRecord]:
        return [record for record in self._history.get(job_id, []) if record.error]
