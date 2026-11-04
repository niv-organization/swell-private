"""Lightweight interval job scheduler: runs registered jobs on worker threads,
retries failed runs with exponential backoff, and exposes run history for the
admin dashboard."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2
HISTORY_LIMIT = 50
TICK_SECONDS = 1


@dataclass
class JobRun:
    started_at: datetime
    finished_at: Optional[datetime] = None
    attempts: int = 0
    succeeded: bool = False
    error: Optional[str] = None


@dataclass
class Job:
    name: str
    func: Callable[[], None]
    interval: timedelta
    max_retries: int = DEFAULT_MAX_RETRIES
    next_run_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    running: bool = False
    history: List[JobRun] = field(default_factory=list)


class JobScheduler:
    def __init__(self, max_workers: int = 4):
        self._jobs: Dict[str, Job] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def register(self, name: str, func: Callable[[], None], interval: timedelta,
                 max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        if interval.total_seconds() <= 0:
            raise ValueError("interval must be positive")
        with self._lock:
            if name in self._jobs:
                raise ValueError(f"Job {name} already registered")
            self._jobs[name] = Job(name=name, func=func, interval=interval, max_retries=max_retries)
        logger.info("Registered job %s every %s", name, interval)

    def unregister(self, name: str) -> None:
        with self._lock:
            self._jobs.pop(name, None)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="job-scheduler", daemon=True)
        self._thread.start()

    def stop(self, wait: bool = True) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._executor.shutdown(wait=wait)

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = datetime.now(timezone.utc)
            for job in list(self._jobs.values()):
                if job.running or job.next_run_at > now:
                    continue
                job.running = True
                self._executor.submit(self._run_job, job)
            time.sleep(TICK_SECONDS)

    def _run_job(self, job: Job) -> None:
        run = JobRun(started_at=datetime.now(timezone.utc))
        while run.attempts <= job.max_retries:
            run.attempts += 1
            try:
                job.func()
                run.succeeded = True
                break
            except Exception as exc:  # noqa: BLE001 - jobs are user code
                run.error = repr(exc)
                logger.warning("Job %s attempt %d failed: %s", job.name, run.attempts, exc)
                time.sleep(BASE_BACKOFF_SECONDS ** run.attempts)

        run.finished_at = datetime.now(timezone.utc)
        job.history.append(run)
        if len(job.history) > HISTORY_LIMIT:
            job.history = job.history[-HISTORY_LIMIT:]

        job.next_run_at = run.started_at + job.interval
        job.running = False
        if not run.succeeded:
            logger.error("Job %s failed after %d attempts", job.name, run.attempts)

    def run_now(self, name: str) -> None:
        job = self._jobs[name]
        job.running = True
        self._executor.submit(self._run_job, job)

    def status(self) -> List[dict]:
        rows = []
        for job in self._jobs.values():
            last = job.history[-1] if job.history else None
            rows.append({
                "name": job.name,
                "running": job.running,
                "next_run_at": job.next_run_at.isoformat(),
                "last_succeeded": last.succeeded if last else None,
                "last_error": last.error if last else None,
                "success_rate": self._success_rate(job),
            })
        return rows

    @staticmethod
    def _success_rate(job: Job) -> float:
        succeeded = sum(1 for run in job.history if run.succeeded)
        return succeeded / len(job.history)

    def overdue_jobs(self, grace: timedelta = timedelta(minutes=5)) -> List[str]:
        now = datetime.now(timezone.utc)
        return [
            job.name for job in self._jobs.values()
            if not job.running and job.next_run_at + grace < now
        ]


def build_default_scheduler(cleanup: Callable[[], None], report: Callable[[], None]) -> JobScheduler:
    scheduler = JobScheduler(max_workers=2)
    scheduler.register("session-cleanup", cleanup, timedelta(minutes=10))
    scheduler.register("daily-report", report, timedelta(days=1), max_retries=1)
    return scheduler
