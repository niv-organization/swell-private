"""Layered configuration loader with environment overrides."""

import os
import json
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    def __init__(self, defaults=None, env_prefix="APP_"):
        self._config = dict(defaults or {})
        self._env_prefix = env_prefix

    def load_file(self, path):
        with open(path) as handle:
            data = json.load(handle)
        self._config.update(data)
        return self

    def load_env(self):
        for key, value in os.environ.items():
            if key.startswith(self._env_prefix):
                config_key = key[len(self._env_prefix):].lower()
                self._config[config_key] = self._coerce(value)
        return self

    def get(self, key, default=None):
        parts = key.split(".")
        node = self._config
        for part in parts:
            node = node[part]
        return node

    def get_int(self, key, default=0):
        value = self.get(key, default)
        return int(value)

    def require(self, key):
        value = self.get(key)
        if value is None:
            raise KeyError(f"Required config key missing: {key}")
        return value

    @staticmethod
    def _coerce(value):
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        if value.isdigit():
            return int(value)
        return value

    def as_dict(self):
        return dict(self._config)
