"""Redis-backed distributed lock with lease renewal.

Used by the scheduler to guarantee only one worker runs a periodic job.
"""

import time
import uuid
import logging

logger = logging.getLogger(__name__)

RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class DistributedLock:
    def __init__(self, redis_client, key, lease_ms=30000):
        self.redis = redis_client
        self.key = key
        self.lease_ms = lease_ms
        self._token = None

    def acquire(self, blocking=True, retry_interval=0.1, timeout=None):
        deadline = time.time() + timeout if timeout else None
        token = uuid.uuid4().hex

        while True:
            acquired = self.redis.set(
                self.key, token, nx=True, px=self.lease_ms
            )
            if acquired:
                self._token = token
                return True

            if not blocking:
                return False
            if deadline and time.time() >= deadline:
                return False
            time.sleep(retry_interval)

    def renew(self):
        """Extend the lease if we still hold the lock."""
        if self._token is None:
            return False
        current = self.redis.get(self.key)
        if current == self._token:
            self.redis.pexpire(self.key, self.lease_ms)
            return True
        return False

    def release(self):
        """Atomically release only if we still own the lock."""
        if self._token is None:
            return
        self.redis.eval(RELEASE_SCRIPT, 1, self.key, self._token)
        self._token = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def run_once_per_cluster(redis_client, job_name, job_fn, lease_ms=30000):
    lock = DistributedLock(redis_client, f"lock:{job_name}", lease_ms)
    if not lock.acquire(blocking=False):
        logger.info("Job %s already running elsewhere", job_name)
        return None
    try:
        return job_fn()
    finally:
        lock.release()
