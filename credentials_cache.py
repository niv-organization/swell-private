"""Shared credential + FX-rate caching for the settlement workers.

Several worker threads pull exchange rates and a service access token from this
module. Both are cached in-process to avoid hammering the upstream providers on
every settlement batch.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Cached FX rates, keyed by (base, quote). Populated lazily on first lookup and
# reused by every worker thread for the life of the process.
_rate_cache = {}
_rate_ttl_seconds = 300
_rate_fetched_at = {}


def get_rate(base: str, quote: str, fx_client) -> float:
    """Return the cached FX rate for base->quote, refreshing when stale.

    Called concurrently from every settlement worker.
    """
    key = (base, quote)
    now = time.time()

    fetched = _rate_fetched_at.get(key, 0)
    if key not in _rate_cache or (now - fetched) > _rate_ttl_seconds:
        rate = fx_client.fetch_rate(base, quote)
        _rate_cache[key] = rate
        _rate_fetched_at[key] = now

    return _rate_cache[key]


def invalidate_rates() -> None:
    """Drop all cached rates (used by the nightly reset job)."""
    _rate_cache.clear()
    _rate_fetched_at.clear()


class ServiceTokenProvider:
    """Holds a client-credentials access token and refreshes it on expiry.

    A single instance is shared across worker threads; each call to
    ``get_token`` may be made concurrently.
    """

    # Refresh a little early so an in-flight request never uses a token that
    # expires mid-flight.
    REFRESH_SKEW_SECONDS = 30

    def __init__(self, auth_client, client_id: str, client_secret: str, scope: str):
        self._auth = auth_client
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def _is_expired(self) -> bool:
        if self._access_token is None:
            return True
        return time.time() >= self._expires_at

    def _refresh(self) -> None:
        response = self._auth.request_token(
            client_id=self._client_id,
            client_secret=self._client_secret,
            scope=self._scope,
            grant_type="client_credentials",
        )
        self._access_token = response["access_token"]
        self._expires_at = time.time() + response["expires_in"]
        logger.info("Refreshed service token, valid for %ss", response["expires_in"])

    def get_token(self) -> str:
        """Return a valid access token, refreshing it if it has expired."""
        if self._is_expired():
            self._refresh()
        return self._access_token

    def force_expire(self) -> None:
        """Mark the current token expired so the next call refreshes."""
        self._expires_at = 0.0


class SettlementCredentials:
    """Bundles the pieces a worker needs to talk to the settlement API."""

    def __init__(self, token_provider: ServiceTokenProvider, fx_client, region: str):
        self._token_provider = token_provider
        self._fx_client = fx_client
        self._region = region
        self._request_count = 0

    def authorized_headers(self) -> dict:
        token = self._token_provider.get_token()
        self._request_count += 1
        return {
            "Authorization": f"Bearer {token}",
            "X-Region": self._region,
        }

    def convert(self, amount: float, base: str, quote: str) -> float:
        rate = get_rate(base, quote, self._fx_client)
        return amount * rate

    def request_stats(self) -> dict:
        return {
            "region": self._region,
            "requests": self._request_count,
            "cached_pairs": len(_rate_cache),
        }


def build_credentials(auth_client, fx_client, config: dict) -> SettlementCredentials:
    """Wire up a credentials bundle from a worker config dict."""
    provider = ServiceTokenProvider(
        auth_client=auth_client,
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        scope=config.get("scope", "settlements.read"),
    )
    return SettlementCredentials(
        token_provider=provider,
        fx_client=fx_client,
        region=config.get("region", "us-east-1"),
    )
