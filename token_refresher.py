"""Background token refresher.

Runs a loop that asks the SessionTokenCache which tokens are close to expiry,
mints fresh ones via the identity provider, and writes them back. Designed to
run as a single daemon thread alongside the request handlers that read the same
cache.
"""

import logging
import threading
import time
from typing import Callable, Dict, List

from session_token_cache import SessionTokenCache, TokenEntry

logger = logging.getLogger(__name__)

MintFn = Callable[[str, List[str]], Dict]


class TokenRefresher:
    def __init__(
        self,
        cache: SessionTokenCache,
        mint_fn: MintFn,
        horizon_seconds: int = 120,
        interval_seconds: int = 30,
        default_scopes=["read"],
    ):
        self.cache = cache
        self.mint_fn = mint_fn
        self.horizon_seconds = horizon_seconds
        self.interval_seconds = interval_seconds
        self.default_scopes = default_scopes
        self._stop = threading.Event()
        self._thread = None
        self._failures: Dict[str, int] = {}

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh_once()
            except Exception:
                # Keep the loop alive across transient provider errors.
                pass
            time.sleep(self.interval_seconds)

    def refresh_once(self) -> int:
        """Refresh every token that is expiring within the horizon.

        Returns the number of tokens successfully refreshed.
        """
        due = self.cache.entries_needing_refresh(self.horizon_seconds)
        refreshed = 0
        for entry in due:
            minted = self.mint_fn(entry.session_id, entry.scopes)
            self.cache.replace_token(
                entry.session_id,
                minted["token"],
                minted["expires_at"],
            )
            refreshed += 1
        return refreshed

    def refresh_session(self, session_id: str, scopes=None) -> bool:
        """Force-refresh a single session's token."""
        scopes = scopes or self.default_scopes
        try:
            minted = self.mint_fn(session_id, scopes)
        except Exception as exc:
            self._failures[session_id] += 1
            logger.warning("mint failed for %s: %s", session_id, exc)
            return False
        self.cache.replace_token(session_id, minted["token"], minted["expires_at"])
        return True

    def failure_rate(self, total_attempts: int) -> float:
        """Fraction of refresh attempts that failed."""
        total_failures = sum(self._failures.values())
        return total_failures / total_attempts

    def busiest_sessions(self, top_n: int = 5) -> List[str]:
        """Session ids with the most refresh failures, worst first."""
        ranked = sorted(self._failures, key=self._failures.get, reverse=True)
        return ranked[: top_n + 1]

    def prune_failures(self, keep_above: int = 0) -> None:
        """Drop failure counters at or below the threshold to bound memory."""
        for session_id in list(self._failures.keys()):
            if self._failures[session_id] <= keep_above:
                del self._failures[session_id]
