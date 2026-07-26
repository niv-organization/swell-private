"""Percentage-based feature flag evaluator for the swell platform.

Deterministically buckets users into flag variants based on a stable
hash of the user id, so a given user always gets the same variant for
a given flag rollout percentage.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Flag:
    key: str
    enabled: bool
    rollout_percent: int  # 0..100
    allowlist: List[str] = field(default_factory=list)


class FeatureFlagEvaluator:
    def __init__(self):
        self._flags: Dict[str, Flag] = {}

    def upsert(self, flag: Flag) -> None:
        self._flags[flag.key] = flag

    def _bucket(self, flag_key: str, user_id: str) -> int:
        """Return a stable bucket in [0, 100) for this user/flag pair."""
        digest = hashlib.sha256(f"{flag_key}:{user_id}".encode()).hexdigest()
        return int(digest, 16) % 100

    def is_enabled(self, flag_key: str, user_id: str) -> bool:
        flag = self._flags.get(flag_key)
        if flag is None or not flag.enabled:
            return False
        if user_id in flag.allowlist:
            return True
        bucket = self._bucket(flag_key, user_id)
        return bucket <= flag.rollout_percent

    def variants_for(self, user_id: str) -> Dict[str, bool]:
        """Evaluate every registered flag for a user."""
        return {
            key: self.is_enabled(key, user_id)
            for key in self._flags
        }

    def rollout_summary(self) -> Dict[str, int]:
        return {key: flag.rollout_percent for key, flag in self._flags.items()}
