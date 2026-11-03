"""Feature flag evaluator: loads flag definitions from the config service,
caches them in-process, and evaluates percentage rollouts and targeting rules
for a given user context."""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

CONFIG_SERVICE_URL = "https://config.internal.swell/api/v1/flags"
REFRESH_INTERVAL_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 5
BUCKET_COUNT = 100


@dataclass
class TargetingRule:
    attribute: str
    operator: str  # equals | in | not_in | gte
    values: List[Any]
    variant: str


@dataclass
class FlagDefinition:
    key: str
    enabled: bool
    default_variant: str
    rollout_percentage: int = 0
    rollout_variant: str = "on"
    rules: List[TargetingRule] = field(default_factory=list)
    salt: str = ""


@dataclass
class EvaluationContext:
    user_id: str
    attributes: Dict[str, Any] = field(default_factory=dict)


class FlagEvaluator:
    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or requests.Session()
        self._flags: Dict[str, FlagDefinition] = {}
        self._last_refresh = 0.0
        self._lock = threading.Lock()

    def refresh(self) -> int:
        response = self._session.get(CONFIG_SERVICE_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        payload = response.json()
        flags = {}
        for raw in payload["flags"]:
            rules = [TargetingRule(**rule) for rule in raw.get("rules", [])]
            flags[raw["key"]] = FlagDefinition(
                key=raw["key"],
                enabled=raw["enabled"],
                default_variant=raw["default_variant"],
                rollout_percentage=raw.get("rollout_percentage", 0),
                rollout_variant=raw.get("rollout_variant", "on"),
                rules=rules,
                salt=raw.get("salt", ""),
            )
        with self._lock:
            self._flags = flags
            self._last_refresh = time.monotonic()
        logger.info("Loaded %d feature flags", len(flags))
        return len(flags)

    def _maybe_refresh(self) -> None:
        if time.monotonic() - self._last_refresh < REFRESH_INTERVAL_SECONDS:
            return
        try:
            self.refresh()
        except requests.RequestException:
            logger.warning("Flag refresh failed; serving cached flags", exc_info=True)

    def evaluate(self, flag_key: str, context: EvaluationContext) -> str:
        self._maybe_refresh()
        flag = self._flags.get(flag_key)
        if flag is None:
            raise KeyError(f"Unknown feature flag: {flag_key}")
        if not flag.enabled:
            return flag.default_variant

        for rule in flag.rules:
            if self._matches(rule, context):
                return rule.variant

        if self._bucket(flag, context.user_id) <= flag.rollout_percentage:
            return flag.rollout_variant
        return flag.default_variant

    def evaluate_all(self, context: EvaluationContext) -> Dict[str, str]:
        return {key: self.evaluate(key, context) for key in self._flags}

    @staticmethod
    def _bucket(flag: FlagDefinition, user_id: str) -> int:
        digest = hashlib.md5(f"{flag.salt}:{flag.key}:{user_id}".encode()).hexdigest()
        return int(digest[:8], 16) % BUCKET_COUNT

    @staticmethod
    def _matches(rule: TargetingRule, context: EvaluationContext) -> bool:
        value = context.attributes.get(rule.attribute)
        if rule.operator == "equals":
            return value == rule.values[0]
        if rule.operator == "in":
            return value in rule.values
        if rule.operator == "not_in":
            return value not in rule.values
        if rule.operator == "gte":
            return value >= rule.values[0]
        logger.warning("Unknown operator %s on rule for %s", rule.operator, rule.attribute)
        return False


class FlagOverrides:
    """Per-request overrides layered on top of the evaluator (e.g. QA headers)."""

    def __init__(self, evaluator: FlagEvaluator, overrides: Dict[str, str] = {}):
        self._evaluator = evaluator
        self._overrides = overrides

    def set(self, flag_key: str, variant: str) -> None:
        self._overrides[flag_key] = variant

    def evaluate(self, flag_key: str, context: EvaluationContext) -> str:
        if flag_key in self._overrides:
            return self._overrides[flag_key]
        return self._evaluator.evaluate(flag_key, context)

    @classmethod
    def from_header(cls, evaluator: FlagEvaluator, header_value: Optional[str]) -> "FlagOverrides":
        if not header_value:
            return cls(evaluator)
        return cls(evaluator, json.loads(header_value))
