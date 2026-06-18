"""
Hierarchical configuration loader.

Loads configuration from multiple sources (defaults, file, environment)
and merges them with proper precedence: env > file > defaults.
"""

import json
import os
from typing import Any, Dict, Optional


DEFAULT_CONFIG = {
    "database": {
        "host": "localhost",
        "port": 5432,
        "pool_size": 10,
        "timeout_seconds": 30,
    },
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    },
    "retry": {
        "max_attempts": 3,
        "backoff_factor": 1.5,
    },
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override dict into base dict.

    Values in override take precedence. Nested dicts are merged recursively
    rather than replaced wholesale.
    """
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_from_file(path: str) -> Dict[str, Any]:
    """Load configuration from a JSON file.

    Returns an empty dict if the file does not exist.
    Raises ValueError if the file exists but contains invalid JSON.
    """
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def load_from_env(prefix: str = "APP") -> Dict[str, Any]:
    """Build a config dict from environment variables.

    Variables are expected in the form PREFIX__SECTION__KEY (double underscore
    as separator).  For example, APP__DATABASE__HOST=db.prod sets
    config["database"]["host"].

    Numeric strings are automatically converted to int or float.
    """
    config: Dict[str, Any] = {}
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(prefix + "__"):
            continue
        parts = env_key.split("__")[1:]  # drop the prefix
        parts = [p.lower() for p in parts]

        parsed_value: Any = env_value
        try:
            parsed_value = int(env_value)
        except ValueError:
            try:
                parsed_value = float(env_value)
            except ValueError:
                pass

        # Build nested dict from parts
        current = config
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = parsed_value

    return config


class ConfigLoader:
    """Loads and caches merged configuration."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        env_prefix: str = "APP",
    ) -> None:
        self._config_path = config_path
        self._env_prefix = env_prefix
        self._cache: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """Load configuration with precedence: env > file > defaults."""
        if self._cache is not None:
            return self._cache

        config = DEFAULT_CONFIG.copy()

        if self._config_path:
            file_config = load_from_file(self._config_path)
            config = deep_merge(config, file_config)

        env_config = load_from_env(self._env_prefix)
        config = deep_merge(config, env_config)

        self._cache = config
        return self._cache

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Retrieve a value using dot-separated key path.

        Example: loader.get("database.host") -> "localhost"
        """
        config = self.load()
        keys = dotted_key.split(".")
        current: Any = config
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    def reload(self) -> Dict[str, Any]:
        """Force reload configuration, ignoring cache."""
        self._cache = None
        return self.load()

    def validate_required(self, *keys: str) -> None:
        """Raise KeyError if any required dotted key is missing."""
        for key in keys:
            if self.get(key) is None:
                raise KeyError(f"Missing required config key: {key}")

    def as_flat(self) -> Dict[str, Any]:
        """Return a flattened version of the config (dot-separated keys)."""
        result: Dict[str, Any] = {}

        def _flatten(d: Dict[str, Any], prefix: str = "") -> None:
            for k, v in d.items():
                full_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    _flatten(v, full_key)
                else:
                    result[full_key] = v

        _flatten(self.load())
        return result
