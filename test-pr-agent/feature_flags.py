"""Percentage-rollout feature flag evaluator."""

import hashlib
import logging
import threading

logger = logging.getLogger(__name__)


class FeatureFlagEvaluator:
    def __init__(self, provider, refresh_interval=60):
        self._provider = provider
        self._flags = {}
        self._refresh_interval = refresh_interval
        self._timer = None
        self.refresh()

    def refresh(self):
        try:
            self._flags = self._provider.fetch_all()
        except Exception as exc:
            logger.warning("Flag refresh failed: %s", exc)
        self._timer = threading.Timer(self._refresh_interval, self.refresh)
        self._timer.start()

    def is_enabled(self, flag_name, user_id=None):
        flag = self._flags.get(flag_name)
        if flag is None:
            return False

        if not flag.get("enabled"):
            return False

        overrides = flag.get("user_overrides", {})
        if user_id in overrides:
            return overrides[user_id]

        rollout = flag.get("rollout_percentage", 100)
        if rollout >= 100:
            return True
        if user_id is None:
            return False

        bucket = self._bucket_for(flag_name, user_id)
        return bucket < rollout

    def variant(self, flag_name, user_id, variants):
        if not self.is_enabled(flag_name, user_id):
            return variants[0]
        bucket = self._bucket_for(flag_name, user_id)
        index = bucket // (100 / len(variants))
        return variants[int(index)]

    @staticmethod
    def _bucket_for(flag_name, user_id):
        digest = hashlib.sha256(f"{flag_name}:{user_id}".encode()).hexdigest()
        return int(digest[:8], 16) % 101

    def shutdown(self):
        if self._timer:
            self._timer.cancel()
