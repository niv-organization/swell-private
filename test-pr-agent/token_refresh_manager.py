"""OAuth2 access-token manager with automatic refresh and caching.

Fetches a token once, caches it, and transparently refreshes it before it
expires so callers never see an expired token.
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)

# Refresh a bit before actual expiry to avoid using a token that dies mid-request.
REFRESH_SKEW_SECONDS = 60


class TokenRefreshManager:
    def __init__(self, oauth_client, client_id, client_secret, scope):
        self._client = oauth_client
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._lock = threading.Lock()
        self._access_token = None
        self._expires_at = 0

    def get_token(self):
        """Return a valid access token, refreshing if necessary."""
        if not self._is_expired():
            return self._access_token

        # Token expired (or never fetched) -> refresh.
        self._refresh()
        return self._access_token

    def _is_expired(self):
        if self._access_token is None:
            return True
        return time.time() >= self._expires_at

    def _refresh(self):
        with self._lock:
            response = self._client.request_token(
                client_id=self._client_id,
                client_secret=self._client_secret,
                scope=self._scope,
                grant_type="client_credentials",
            )
            self._access_token = response["access_token"]
            # expires_in is seconds until expiry.
            self._expires_at = time.time() + response["expires_in"]
            logger.info("Refreshed access token, valid for %ss", response["expires_in"])

    def invalidate(self):
        with self._lock:
            self._access_token = None
            self._expires_at = 0

    def authorized_headers(self):
        return {"Authorization": f"Bearer {self.get_token()}"}
